use crate::models::{LlmProvider, Skill};
use crate::services::llm::{self, LlmError};
use crate::services::scanner::ScannerService;
use crate::services::translation::{self, SkillTranslationInput, SkillTranslationOutput};
use crate::services::translation_cache::{CacheKey, TranslationCache};
use crate::services::ConfigManager;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tauri::{AppHandle, Emitter};
use tokio::sync::Semaphore;
use tokio::task::JoinSet;

#[tauri::command]
pub fn get_llm_provider() -> Result<Option<LlmProvider>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    Ok(config.llm_provider)
}

#[tauri::command]
pub fn save_llm_provider(provider: LlmProvider) -> Result<(), String> {
    if provider.base_url.trim().is_empty() {
        return Err("base_url is required".to_string());
    }
    if provider.api_key.trim().is_empty() {
        return Err("api_key is required".to_string());
    }
    if provider.model.trim().is_empty() {
        return Err("model is required".to_string());
    }
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    config.llm_provider = Some(provider);
    manager.save(&config)
}

#[tauri::command]
pub fn clear_llm_provider() -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    config.llm_provider = None;
    manager.save(&config)
}

#[tauri::command]
pub async fn test_llm_provider(provider: LlmProvider) -> Result<String, LlmError> {
    llm::test_connection(&provider).await
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketplaceTranslationInput {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub content_md: Option<String>,
}

fn load_provider_or_error() -> Result<LlmProvider, LlmError> {
    let manager = ConfigManager::new();
    let config = manager.load().map_err(|e| LlmError::NetworkError(e))?;
    config.llm_provider.ok_or(LlmError::NotConfigured)
}

fn find_skill_by_instance(skills: &[Skill], instance_id: &str) -> Option<Skill> {
    skills
        .iter()
        .find(|s| s.instance_id == instance_id)
        .cloned()
}

fn find_installed_for_marketplace(skills: &[Skill], marketplace_skill_id: &str) -> Option<Skill> {
    skills
        .iter()
        .find(|s| {
            s.marketplace_meta
                .as_ref()
                .and_then(|m| m.marketplace_skill_id.as_deref())
                == Some(marketplace_skill_id)
        })
        .cloned()
}

fn find_skill_md(dir: &Path, max_depth: u32) -> Option<PathBuf> {
    if !dir.is_dir() {
        return None;
    }
    let direct_upper = dir.join("SKILL.md");
    if direct_upper.is_file() {
        return Some(direct_upper);
    }
    let direct_lower = dir.join("skill.md");
    if direct_lower.is_file() {
        return Some(direct_lower);
    }
    if max_depth == 0 {
        return None;
    }
    if let Ok(entries) = fs::read_dir(dir) {
        for entry in entries.flatten() {
            let p = entry.path();
            if p.is_dir() {
                if let Some(found) = find_skill_md(&p, max_depth - 1) {
                    return Some(found);
                }
            }
        }
    }
    None
}

fn read_skill_md(skill: &Skill) -> Option<String> {
    find_skill_md(&skill.path, 3).and_then(|p| fs::read_to_string(&p).ok())
}

fn is_ignored_doc_dir(name: &str) -> bool {
    name.starts_with('.') || matches!(name, "node_modules" | "target" | "dist" | "build" | ".git")
}

fn is_translatable_doc_file(path: &Path) -> bool {
    path.extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| {
            matches!(
                ext.to_ascii_lowercase().as_str(),
                "md" | "mdx" | "markdown" | "txt" | "text"
            )
        })
        .unwrap_or(false)
}

fn normalize_relative_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn collect_translatable_doc_files(dir: &Path) -> Vec<PathBuf> {
    fn walk(dir: &Path, files: &mut Vec<PathBuf>) {
        let entries = match fs::read_dir(dir) {
            Ok(entries) => entries,
            Err(_) => return,
        };

        let mut paths: Vec<PathBuf> = entries
            .filter_map(|entry| entry.ok())
            .filter_map(|entry| {
                let file_type = entry.file_type().ok()?;
                if file_type.is_symlink() {
                    return None;
                }
                Some((entry.path(), file_type))
            })
            .collect::<Vec<_>>()
            .into_iter()
            .filter(|(path, file_type)| {
                let name = path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or_default();
                if file_type.is_dir() {
                    !is_ignored_doc_dir(name)
                } else {
                    file_type.is_file() && is_translatable_doc_file(path)
                }
            })
            .map(|(path, _)| path)
            .collect();

        paths.sort_by(|a, b| {
            let a_name = a
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or_default()
                .to_ascii_lowercase();
            let b_name = b
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or_default()
                .to_ascii_lowercase();
            match (a.is_dir(), b.is_dir()) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => a_name.cmp(&b_name),
            }
        });

        for path in paths {
            if path.is_dir() {
                walk(&path, files);
            } else {
                files.push(path);
            }
        }
    }

    let mut files = Vec::new();
    if dir.is_dir() {
        walk(dir, &mut files);
    }
    files.sort_by(|a, b| {
        let a_name = a
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let b_name = b
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let rank = |name: &str| match name {
            "skill.md" => 0,
            "readme.md" => 1,
            _ => 2,
        };
        rank(&a_name)
            .cmp(&rank(&b_name))
            .then_with(|| normalize_relative_path(a).cmp(&normalize_relative_path(b)))
    });
    files
}

#[tauri::command]
pub async fn translate_skill(
    instance_id: String,
    target_lang: String,
    force: Option<bool>,
) -> Result<SkillTranslationOutput, LlmError> {
    let provider = load_provider_or_error()?;
    let manager = ConfigManager::new();
    let config = manager.load().map_err(LlmError::NetworkError)?;
    let skills = ScannerService::scan_scoped_skills(&config).map_err(LlmError::NetworkError)?;
    let skill = find_skill_by_instance(&skills, &instance_id)
        .ok_or_else(|| LlmError::NetworkError(format!("skill not found: {instance_id}")))?;

    let input = SkillTranslationInput {
        name: skill.name.clone(),
        description: skill.description.clone().unwrap_or_default(),
        content_md: read_skill_md(&skill),
    };

    translation::translate_skill(&provider, &target_lang, input, force.unwrap_or(false)).await
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillFileTranslationProgress {
    pub current: usize,
    pub total: usize,
    pub instance_id: String,
    pub skill_name: String,
    pub path: String,
    pub status: String,
    pub target_lang: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillFileTranslationEntry {
    pub path: String,
    pub translation: SkillTranslationOutput,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillFileTranslationFailure {
    pub path: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct SkillFilesTranslationResult {
    pub files: Vec<SkillFileTranslationEntry>,
    pub failed: Vec<SkillFileTranslationFailure>,
}

const SKILL_FILES_PROGRESS_EVENT: &str = "llm:skill-files-progress";

fn emit_skill_file_progress(
    app: &AppHandle,
    current: usize,
    total: usize,
    skill: &Skill,
    path: &str,
    status: &str,
    target_lang: &str,
) {
    let _ = app.emit(
        SKILL_FILES_PROGRESS_EVENT,
        SkillFileTranslationProgress {
            current,
            total,
            instance_id: skill.instance_id.clone(),
            skill_name: skill.name.clone(),
            path: path.to_string(),
            status: status.to_string(),
            target_lang: target_lang.to_string(),
        },
    );
}

#[tauri::command]
pub async fn translate_skill_files(
    instance_id: String,
    target_lang: String,
    force: Option<bool>,
    app: AppHandle,
) -> Result<SkillFilesTranslationResult, LlmError> {
    let provider = load_provider_or_error()?;
    let manager = ConfigManager::new();
    let config = manager.load().map_err(LlmError::NetworkError)?;
    let skills = ScannerService::scan_scoped_skills(&config).map_err(LlmError::NetworkError)?;
    let skill = find_skill_by_instance(&skills, &instance_id)
        .ok_or_else(|| LlmError::NetworkError(format!("skill not found: {instance_id}")))?;

    let files = collect_translatable_doc_files(&skill.path);
    let total = files.len();
    let mut translated_files = Vec::new();
    let mut failed = Vec::new();
    let force_refresh = force.unwrap_or(false);

    for (idx, path) in files.into_iter().enumerate() {
        let current = idx + 1;
        let relative = path
            .strip_prefix(&skill.path)
            .map(normalize_relative_path)
            .unwrap_or_else(|_| normalize_relative_path(&path));

        emit_skill_file_progress(
            &app,
            current,
            total,
            &skill,
            &relative,
            "started",
            &target_lang,
        );

        let content = match fs::read_to_string(&path) {
            Ok(content) => content,
            Err(err) => {
                let reason = err.to_string();
                emit_skill_file_progress(
                    &app,
                    current,
                    total,
                    &skill,
                    &relative,
                    "failed",
                    &target_lang,
                );
                failed.push(SkillFileTranslationFailure {
                    path: relative,
                    reason,
                });
                continue;
            }
        };

        let is_skill_md = path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|name| name.eq_ignore_ascii_case("SKILL.md"))
            .unwrap_or(false);

        let input = if is_skill_md {
            SkillTranslationInput {
                name: skill.name.clone(),
                description: skill.description.clone().unwrap_or_default(),
                content_md: Some(content),
            }
        } else {
            SkillTranslationInput {
                name: relative.clone(),
                description: String::new(),
                content_md: Some(content),
            }
        };

        match translation::translate_skill(&provider, &target_lang, input, force_refresh).await {
            Ok(output) => {
                emit_skill_file_progress(
                    &app,
                    current,
                    total,
                    &skill,
                    &relative,
                    "completed",
                    &target_lang,
                );
                translated_files.push(SkillFileTranslationEntry {
                    path: relative,
                    translation: output,
                });
            }
            Err(err) => {
                emit_skill_file_progress(
                    &app,
                    current,
                    total,
                    &skill,
                    &relative,
                    "failed",
                    &target_lang,
                );
                failed.push(SkillFileTranslationFailure {
                    path: relative,
                    reason: err.to_string(),
                });
            }
        }
    }

    Ok(SkillFilesTranslationResult {
        files: translated_files,
        failed,
    })
}

#[tauri::command]
pub async fn translate_marketplace_skill(
    input: MarketplaceTranslationInput,
    target_lang: String,
    force: Option<bool>,
) -> Result<SkillTranslationOutput, LlmError> {
    let provider = load_provider_or_error()?;
    let manager = ConfigManager::new();
    let installed_match = manager.load().ok().and_then(|config| {
        ScannerService::scan_scoped_skills(&config)
            .ok()
            .and_then(|skills| find_installed_for_marketplace(&skills, &input.id))
    });

    let payload = if let Some(skill) = installed_match {
        SkillTranslationInput {
            name: skill.name.clone(),
            description: skill.description.clone().unwrap_or_default(),
            content_md: read_skill_md(&skill),
        }
    } else {
        SkillTranslationInput {
            name: input.name,
            description: input.description.unwrap_or_default(),
            content_md: input.content_md,
        }
    };
    translation::translate_skill(&provider, &target_lang, payload, force.unwrap_or(false)).await
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchTranslationProgress {
    pub current: usize,
    pub total: usize,
    pub instance_id: String,
    pub skill_name: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchTranslationFailure {
    pub instance_id: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchTranslationResult {
    pub succeeded: Vec<String>,
    pub failed: Vec<BatchTranslationFailure>,
}

const BATCH_PROGRESS_EVENT: &str = "llm:batch-progress";

/// 根据 provider 类型确定并发数
fn determine_concurrency(provider: &LlmProvider) -> usize {
    let url = provider.base_url.to_lowercase();

    if url.contains("openai.com") {
        5 // OpenAI TPM 限制较严
    } else if url.contains("deepseek") {
        8 // DeepSeek 速率较宽松
    } else if url.contains("localhost") || url.contains("127.0.0.1") {
        12 // 本地 Ollama 无限制
    } else if url.contains("api.anthropic.com") {
        6 // Claude API 中等限制
    } else {
        6 // 默认保守值
    }
}

#[tauri::command]
pub async fn translate_skills_batch(
    instance_ids: Vec<String>,
    target_lang: String,
    force: Option<bool>,
    app: AppHandle,
) -> Result<BatchTranslationResult, String> {
    let provider = Arc::new(load_provider_or_error().map_err(|e| e.to_string())?);
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let skills = Arc::new(ScannerService::scan_scoped_skills(&config)?);

    let total = instance_ids.len();
    let concurrency = determine_concurrency(&provider);
    let semaphore: Arc<Semaphore> = Arc::new(Semaphore::new(concurrency));

    let mut tasks: JoinSet<(usize, Result<String, String>, String)> = JoinSet::new();

    for (idx, instance_id) in instance_ids.into_iter().enumerate() {
        let permit = Arc::clone(&semaphore);
        let provider_clone = Arc::clone(&provider);
        let skills_clone = Arc::clone(&skills);
        let app_clone = app.clone();
        let target_lang_clone = target_lang.clone();
        let force_value = force.unwrap_or(false);

        tasks.spawn(async move {
            // 获取信号量许可
            let _permit = permit.acquire().await.unwrap();

            let skill = match find_skill_by_instance(&skills_clone, &instance_id) {
                Some(s) => s,
                None => {
                    return (idx, Err(instance_id.clone()), "skill not found".to_string());
                }
            };

            // 发送进度事件
            let _ = app_clone.emit(
                BATCH_PROGRESS_EVENT,
                BatchTranslationProgress {
                    current: idx + 1,
                    total,
                    instance_id: instance_id.clone(),
                    skill_name: skill.name.clone(),
                },
            );

            let input = SkillTranslationInput {
                name: skill.name.clone(),
                description: skill.description.clone().unwrap_or_default(),
                content_md: read_skill_md(&skill),
            };

            match translation::translate_skill(
                &provider_clone,
                &target_lang_clone,
                input,
                force_value,
            )
            .await
            {
                Ok(_) => (idx, Ok(instance_id), String::new()),
                Err(err) => (idx, Err(instance_id), err.to_string()),
            }
        });
    }

    // 收集结果
    let mut results = Vec::new();
    while let Some(result) = tasks.join_next().await {
        match result {
            Ok(task_result) => results.push(task_result),
            Err(e) => {
                // JoinError - task panic，记录但继续
                eprintln!("Task panicked: {:?}", e);
            }
        }
    }

    // 按 index 排序保证顺序
    results.sort_by_key(|(idx, _, _)| *idx);

    let mut succeeded = Vec::new();
    let mut failed = Vec::new();

    for (_, result, reason) in results {
        match result {
            Ok(instance_id) => succeeded.push(instance_id),
            Err(instance_id) => failed.push(BatchTranslationFailure {
                instance_id,
                reason,
            }),
        }
    }

    Ok(BatchTranslationResult { succeeded, failed })
}

#[tauri::command]
pub fn clear_translation_cache() -> Result<(), String> {
    translation::clear_cache().map_err(|e| e.to_string())
}

#[derive(Debug, Clone, Serialize)]
pub struct CachedTranslationEntry {
    pub key: String,
    pub translation: Option<SkillTranslationOutput>,
}

fn lookup_skill_cache(
    provider: &LlmProvider,
    target_lang: &str,
    skill: &Skill,
    cache: &TranslationCache,
) -> Option<SkillTranslationOutput> {
    let content_md = read_skill_md(skill);
    let description = skill.description.clone().unwrap_or_default();
    let key = CacheKey {
        base_url: &provider.base_url,
        model: &provider.model,
        target_lang,
        source_name: &skill.name,
        source_description: &description,
        source_content_md: content_md.as_deref(),
    };
    cache.get(&key).map(|hit| SkillTranslationOutput {
        name: hit.name,
        description: hit.description,
        content_md: hit.content_md,
        cached: true,
    })
}

#[tauri::command]
pub fn get_cached_skill_translations(
    instance_ids: Vec<String>,
    target_lang: String,
) -> Result<Vec<CachedTranslationEntry>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let provider = match config.llm_provider.clone() {
        Some(p) => p,
        None => {
            return Ok(instance_ids
                .into_iter()
                .map(|id| CachedTranslationEntry {
                    key: id,
                    translation: None,
                })
                .collect());
        }
    };
    let skills = ScannerService::scan_scoped_skills(&config)?;
    let cache = TranslationCache::new();
    let entries = instance_ids
        .into_iter()
        .map(|id| {
            let translation = skills
                .iter()
                .find(|s| s.instance_id == id)
                .and_then(|skill| lookup_skill_cache(&provider, &target_lang, skill, &cache));
            CachedTranslationEntry {
                key: id,
                translation,
            }
        })
        .collect();
    Ok(entries)
}

#[tauri::command]
pub fn get_cached_marketplace_translations(
    inputs: Vec<MarketplaceTranslationInput>,
    target_lang: String,
) -> Result<Vec<CachedTranslationEntry>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let provider = match config.llm_provider.clone() {
        Some(p) => p,
        None => {
            return Ok(inputs
                .into_iter()
                .map(|input| CachedTranslationEntry {
                    key: input.id,
                    translation: None,
                })
                .collect());
        }
    };
    let installed_skills = ScannerService::scan_scoped_skills(&config).unwrap_or_default();
    let cache = TranslationCache::new();
    let entries = inputs
        .into_iter()
        .map(|input| {
            let translation =
                if let Some(skill) = find_installed_for_marketplace(&installed_skills, &input.id) {
                    lookup_skill_cache(&provider, &target_lang, &skill, &cache)
                } else {
                    let description = input.description.clone().unwrap_or_default();
                    let key = CacheKey {
                        base_url: &provider.base_url,
                        model: &provider.model,
                        target_lang: &target_lang,
                        source_name: &input.name,
                        source_description: &description,
                        source_content_md: input.content_md.as_deref(),
                    };
                    cache.get(&key).map(|hit| SkillTranslationOutput {
                        name: hit.name,
                        description: hit.description,
                        content_md: hit.content_md,
                        cached: true,
                    })
                };
            CachedTranslationEntry {
                key: input.id,
                translation,
            }
        })
        .collect();
    Ok(entries)
}

#[tauri::command]
pub async fn translate_text_content(
    label: String,
    content: String,
    target_lang: String,
    force: Option<bool>,
) -> Result<SkillTranslationOutput, LlmError> {
    let provider = load_provider_or_error()?;
    let payload = SkillTranslationInput {
        name: label,
        description: String::new(),
        content_md: Some(content),
    };
    translation::translate_skill(&provider, &target_lang, payload, force.unwrap_or(false)).await
}

#[tauri::command]
pub fn get_cached_text_translation(
    label: String,
    content: String,
    target_lang: String,
) -> Result<Option<SkillTranslationOutput>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let provider = match config.llm_provider {
        Some(p) => p,
        None => return Ok(None),
    };
    let cache = TranslationCache::new();
    let key = CacheKey {
        base_url: &provider.base_url,
        model: &provider.model,
        target_lang: &target_lang,
        source_name: &label,
        source_description: "",
        source_content_md: Some(&content),
    };
    Ok(cache.get(&key).map(|hit| SkillTranslationOutput {
        name: hit.name,
        description: hit.description,
        content_md: hit.content_md,
        cached: true,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_determine_concurrency_openai() {
        let provider = LlmProvider {
            base_url: "https://api.openai.com/v1".to_string(),
            api_key: "test".to_string(),
            model: "gpt-4".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: None,
        };
        assert_eq!(determine_concurrency(&provider), 5);
    }

    #[test]
    fn test_determine_concurrency_deepseek() {
        let provider = LlmProvider {
            base_url: "https://api.deepseek.com".to_string(),
            api_key: "test".to_string(),
            model: "deepseek-chat".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: None,
        };
        assert_eq!(determine_concurrency(&provider), 8);
    }

    #[test]
    fn test_determine_concurrency_localhost() {
        let provider = LlmProvider {
            base_url: "http://localhost:11434".to_string(),
            api_key: "".to_string(),
            model: "llama2".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: None,
        };
        assert_eq!(determine_concurrency(&provider), 12);
    }

    #[test]
    fn test_determine_concurrency_anthropic() {
        let provider = LlmProvider {
            base_url: "https://api.anthropic.com".to_string(),
            api_key: "test".to_string(),
            model: "claude-3".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: None,
        };
        assert_eq!(determine_concurrency(&provider), 6);
    }

    #[test]
    fn test_determine_concurrency_default() {
        let provider = LlmProvider {
            base_url: "https://custom-api.example.com".to_string(),
            api_key: "test".to_string(),
            model: "custom-model".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: None,
        };
        assert_eq!(determine_concurrency(&provider), 6);
    }

    #[test]
    fn collect_translatable_doc_files_includes_nested_markdown() {
        let temp = tempfile::tempdir().expect("tempdir");
        let root = temp.path();
        fs::create_dir_all(root.join("references")).expect("references dir");
        fs::create_dir_all(root.join(".hidden")).expect("hidden dir");
        fs::create_dir_all(root.join("dist")).expect("dist dir");
        fs::write(root.join("SKILL.md"), "# Skill").expect("skill md");
        fs::write(root.join("README.md"), "# Readme").expect("readme");
        fs::write(
            root.join("references").join("architecture.md"),
            "# Architecture",
        )
        .expect("architecture");
        fs::write(root.join("references").join("notes.txt"), "Notes").expect("notes");
        fs::write(root.join(".hidden").join("secret.md"), "# Secret").expect("secret");
        fs::write(root.join("dist").join("bundle.md"), "# Bundle").expect("bundle");
        fs::write(root.join("references").join("image.png"), "png").expect("png");

        let files = collect_translatable_doc_files(root);
        let relative: Vec<String> = files
            .iter()
            .map(|path| normalize_relative_path(path.strip_prefix(root).expect("relative")))
            .collect();

        assert_eq!(
            relative,
            vec![
                "SKILL.md",
                "README.md",
                "references/architecture.md",
                "references/notes.txt",
            ]
        );
    }
}
