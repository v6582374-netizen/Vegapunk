use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tauri::State;

use crate::models::{
    AppConfig, ClawhubSkillFilesResponse, InstallResult, InstallStatus, MarketplaceSkill,
    MarketplaceSkillsResponse, MarketplaceSource, MarketplaceSyncResult,
    MarketplaceUpdateCheckResult, Skill, SkillFileNode, SkillSource,
};
use crate::services::marketplace::{
    derive_github_repo_and_skill_path, DIRECT_GITHUB_SOURCE_ID, DIRECT_GITHUB_SOURCE_NAME,
};
use crate::services::{
    AppCache, ConfigManager, MarketplaceCache, MarketplaceService, ScannerService,
};

#[derive(Debug, Clone, Deserialize)]
pub struct MarketplaceSkillDescriptionRequest {
    pub id: String,
    pub repo_url: String,
    pub skill_path: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MarketplaceSkillReference {
    pub name: String,
    pub marketplace_source_id: Option<String>,
    pub marketplace_skill_id: Option<String>,
    pub marketplace_skill_slug: Option<String>,
    pub repo_url: Option<String>,
    pub skill_path: Option<String>,
    pub remote_revision: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PersistedMarketplaceUpdateCheckState {
    last_checked_at_unix_secs: u64,
}

const MARKETPLACE_UPDATE_CHECK_INTERVAL: Duration = Duration::from_secs(12 * 60 * 60);

fn github_token_from_config(config: &AppConfig) -> Option<String> {
    config
        .preferences
        .as_ref()
        .and_then(|prefs| prefs.github_token.clone())
        .map(|token| token.trim().to_string())
        .filter(|token| !token.is_empty())
}

fn normalize_source_filter(source_ids: Option<Vec<String>>) -> Option<Vec<String>> {
    let mut ids: Vec<String> = source_ids
        .unwrap_or_default()
        .into_iter()
        .map(|id| id.trim().to_string())
        .filter(|id| !id.is_empty())
        .collect();
    ids.sort();
    ids.dedup();
    if ids.is_empty() {
        None
    } else {
        Some(ids)
    }
}

fn build_marketplace_skill_from_reference(
    reference: MarketplaceSkillReference,
) -> Result<MarketplaceSkill, String> {
    let raw_repo_url = reference.repo_url.unwrap_or_default().trim().to_string();
    if raw_repo_url.is_empty() {
        return Err("repo_url is required".to_string());
    }
    let (derived_repo_url, derived_skill_path) =
        derive_github_repo_and_skill_path(Some(raw_repo_url.as_str()), "");
    let repo_url = derived_repo_url.unwrap_or_else(|| raw_repo_url.clone());
    let is_github_reference = repo_url.contains("github.com/");

    let mut skill_path = reference.skill_path.unwrap_or_default().trim().to_string();
    if skill_path.is_empty() {
        if let Some(derived) = derived_skill_path {
            skill_path = derived;
        }
    }
    if skill_path.is_empty() && !is_github_reference {
        return Err("skill_path is required".to_string());
    }
    let source_id = reference.marketplace_source_id.unwrap_or_else(|| {
        if is_github_reference {
            DIRECT_GITHUB_SOURCE_ID.to_string()
        } else {
            "marketplace".to_string()
        }
    });
    let slug = reference.marketplace_skill_slug.clone().or_else(|| {
        if skill_path.is_empty() {
            repo_url
                .rsplit('/')
                .next()
                .map(str::to_string)
                .filter(|value| !value.trim().is_empty())
        } else {
            Some(skill_path.clone())
        }
    });
    let fallback_id = build_reference_skill_id(&source_id, &repo_url, &skill_path, slug.as_deref());
    let name = reference.name.trim().to_string();
    let name = if name.is_empty() {
        skill_display_name(slug.as_deref(), &repo_url, &skill_path)
            .unwrap_or("skill")
            .to_string()
    } else {
        name
    };

    Ok(MarketplaceSkill {
        id: reference
            .marketplace_skill_id
            .clone()
            .unwrap_or(fallback_id),
        slug,
        name,
        description: None,
        author: None,
        source_id: source_id.clone(),
        source_name: source_id,
        install_count: None,
        install_url: None,
        created_at: None,
        repo_url: Some(repo_url),
        skill_path: Some(skill_path),
        external_url: Some(raw_repo_url),
        remote_revision: reference.remote_revision,
        tags: Vec::new(),
        install_status: InstallStatus::NotInstalled,
        clawhub_slug: None,
        clawhub_owner: None,
        clawhub_version: None,
    })
}

fn build_reference_skill_id(
    source_id: &str,
    repo_url: &str,
    skill_path: &str,
    slug: Option<&str>,
) -> String {
    let raw = if source_id == DIRECT_GITHUB_SOURCE_ID {
        format!("{}-{}-{}", source_id, repo_url.trim(), skill_path.trim())
    } else {
        format!("{}-{}", source_id, slug.unwrap_or(skill_path))
    };
    raw.to_lowercase()
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() { ch } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

fn is_remote_skill_manifest_name(name: &str) -> bool {
    matches!(
        name.trim().to_ascii_lowercase().as_str(),
        "skill.md" | "readme.md"
    )
}

fn expand_skill_group_reference(
    skill: &MarketplaceSkill,
    tree: &SkillFileNode,
) -> Vec<MarketplaceSkill> {
    let root_has_manifest = tree.children.as_ref().is_some_and(|children| {
        children
            .iter()
            .any(|child| !child.is_dir && is_remote_skill_manifest_name(&child.name))
    });
    if root_has_manifest {
        return Vec::new();
    }

    let Some(children) = tree.children.as_ref() else {
        return Vec::new();
    };

    children
        .iter()
        .filter(|child| child.is_dir)
        .filter(|child| {
            child.children.as_ref().is_some_and(|entries| {
                entries
                    .iter()
                    .any(|entry| !entry.is_dir && is_remote_skill_manifest_name(&entry.name))
            })
        })
        .map(|child| {
            let child_path = child.path.clone();
            MarketplaceSkill {
                id: build_reference_skill_id(
                    &skill.source_id,
                    skill.repo_url.as_deref().unwrap_or_default(),
                    &child_path,
                    Some(child_path.as_str()),
                ),
                slug: Some(child_path.clone()),
                name: child.name.clone(),
                description: None,
                author: None,
                source_id: skill.source_id.clone(),
                source_name: skill.source_name.clone(),
                install_count: None,
                install_url: skill.install_url.clone(),
                created_at: skill.created_at,
                repo_url: skill.repo_url.clone(),
                skill_path: Some(child_path),
                external_url: skill.external_url.clone(),
                remote_revision: None,
                tags: Vec::new(),
                install_status: InstallStatus::NotInstalled,
                clawhub_slug: None,
                clawhub_owner: None,
                clawhub_version: None,
            }
        })
        .collect()
}

fn skill_display_name<'a>(
    slug: Option<&'a str>,
    repo_url: &'a str,
    skill_path: &'a str,
) -> Option<&'a str> {
    if !skill_path.trim().is_empty() {
        return skill_path
            .rsplit('/')
            .next()
            .filter(|value| !value.trim().is_empty());
    }
    slug.and_then(|value| value.rsplit('/').next())
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            repo_url
                .rsplit('/')
                .next()
                .filter(|value| !value.trim().is_empty())
        })
}

fn resolve_marketplace_source_name(
    source_id: &str,
    source_name_by_id: &HashMap<String, String>,
) -> String {
    source_name_by_id
        .get(source_id)
        .cloned()
        .unwrap_or_else(|| {
            if source_id == DIRECT_GITHUB_SOURCE_ID {
                DIRECT_GITHUB_SOURCE_NAME.to_string()
            } else {
                source_id.to_string()
            }
        })
}

fn resolve_cache_source_scope(
    normalized_source_filter: &Option<Vec<String>>,
    sources: &[MarketplaceSource],
) -> Option<Vec<String>> {
    let mut enabled_ids: Vec<String> = sources
        .iter()
        .filter(|source| source.enabled)
        .map(|source| source.id.trim().to_string())
        .filter(|id| !id.is_empty())
        .collect();
    enabled_ids.sort();
    enabled_ids.dedup();

    match normalized_source_filter {
        Some(explicit_ids) => {
            let enabled_set: HashSet<&str> = enabled_ids.iter().map(String::as_str).collect();
            let mut scoped_ids: Vec<String> = explicit_ids
                .iter()
                .map(|id| id.trim().to_string())
                .filter(|id| !id.is_empty() && enabled_set.contains(id.as_str()))
                .collect();
            scoped_ids.sort();
            scoped_ids.dedup();
            Some(scoped_ids)
        }
        None => Some(enabled_ids),
    }
}

fn load_cached_or_scanned_skills(
    app_cache: &AppCache,
    skills_dir: &std::path::Path,
) -> Result<Vec<Skill>, String> {
    if let Some(skills) = app_cache.get_skills() {
        return Ok(skills);
    }

    let skills = ScannerService::scan_skills(skills_dir)?;
    app_cache.set_skills(skills.clone());
    Ok(skills)
}

fn collect_installed_marketplace_skills(
    skills: &[Skill],
    sources: &[MarketplaceSource],
    normalized_query: Option<&str>,
    normalized_source_filter: &Option<Vec<String>>,
) -> Vec<MarketplaceSkill> {
    let source_name_by_id: HashMap<String, String> = sources
        .iter()
        .map(|source| (source.id.clone(), source.name.clone()))
        .collect();
    let selected_source_ids: Option<HashSet<&str>> = normalized_source_filter
        .as_ref()
        .map(|ids| ids.iter().map(String::as_str).collect());

    let mut installed: Vec<MarketplaceSkill> = skills
        .iter()
        .filter_map(|skill| {
            if !matches!(skill.source, SkillSource::Marketplace) {
                return None;
            }

            let meta = skill.marketplace_meta.as_ref()?;
            let source_id = meta
                .marketplace_source_id
                .clone()
                .unwrap_or_else(|| "marketplace".to_string());

            if let Some(filter) = &selected_source_ids {
                if !filter.contains(source_id.as_str()) {
                    return None;
                }
            }

            Some(MarketplaceSkill {
                id: meta
                    .marketplace_skill_id
                    .clone()
                    .unwrap_or_else(|| skill.id.clone()),
                slug: meta
                    .marketplace_skill_slug
                    .clone()
                    .or_else(|| meta.skill_path.clone()),
                name: skill.name.clone(),
                description: skill.description.clone(),
                author: None,
                source_id: source_id.clone(),
                source_name: resolve_marketplace_source_name(&source_id, &source_name_by_id),
                install_count: None,
                install_url: None,
                created_at: None,
                repo_url: meta.repo_url.clone(),
                skill_path: meta.skill_path.clone(),
                external_url: meta.repo_url.clone(),
                remote_revision: meta.remote_revision.clone(),
                tags: Vec::new(),
                install_status: InstallStatus::Installed,
                clawhub_slug: None,
                clawhub_owner: None,
                clawhub_version: None,
            })
        })
        .collect();

    installed.sort_by(|a, b| {
        a.name
            .to_lowercase()
            .cmp(&b.name.to_lowercase())
            .then_with(|| a.id.cmp(&b.id))
    });

    let mut seen_ids = HashSet::new();
    installed.retain(|skill| seen_ids.insert(skill.id.clone()));

    MarketplaceService::filter_marketplace_skills_by_query(installed, normalized_query)
}

fn prepend_missing_installed_marketplace_skills(
    response: MarketplaceSkillsResponse,
    installed_skills: Vec<MarketplaceSkill>,
) -> MarketplaceSkillsResponse {
    let existing_ids: HashSet<&str> = response
        .skills
        .iter()
        .map(|skill| skill.id.as_str())
        .collect();
    let mut merged: Vec<MarketplaceSkill> = installed_skills
        .into_iter()
        .filter(|skill| !existing_ids.contains(skill.id.as_str()))
        .collect();
    merged.extend(response.skills);

    MarketplaceSkillsResponse {
        skills: merged,
        has_more: response.has_more,
    }
}

fn should_hydrate_missing_installed_marketplace_skill(skill: &MarketplaceSkill) -> bool {
    skill.source_id == DIRECT_GITHUB_SOURCE_ID
        && skill
            .repo_url
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
        && skill
            .skill_path
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty())
}

async fn merge_installed_marketplace_skills_into_page(
    response: MarketplaceSkillsResponse,
    page: u32,
    skills: &[Skill],
    sources: &[MarketplaceSource],
    normalized_query: Option<&str>,
    normalized_source_filter: &Option<Vec<String>>,
    skills_dir: &std::path::Path,
    github_token: Option<&str>,
) -> MarketplaceSkillsResponse {
    if page != 1 {
        return response;
    }

    let installed_skills = collect_installed_marketplace_skills(
        skills,
        sources,
        normalized_query,
        normalized_source_filter,
    );

    let existing_ids: HashSet<String> = response
        .skills
        .iter()
        .map(|skill| skill.id.clone())
        .collect();
    let mut hydrated_installed = Vec::new();
    for skill in installed_skills
        .into_iter()
        .filter(|skill| !existing_ids.contains(&skill.id))
    {
        let resolved = if should_hydrate_missing_installed_marketplace_skill(&skill) {
            match MarketplaceService::hydrate_marketplace_skill(&skill, github_token).await {
                Ok(resolved) => resolved,
                Err(_) => skill,
            }
        } else {
            skill
        };
        let install_status = MarketplaceService::check_install_status(&resolved, skills_dir);
        hydrated_installed.push(MarketplaceSkill {
            install_status,
            ..resolved
        });
    }

    prepend_missing_installed_marketplace_skills(response, hydrated_installed)
}

fn marketplace_update_check_state_path() -> Option<PathBuf> {
    Some(
        dirs::home_dir()?
            .join(".skills-manager")
            .join("cache")
            .join("marketplace-update-check.json"),
    )
}

fn load_last_update_check_time() -> Option<SystemTime> {
    let path = marketplace_update_check_state_path()?;
    let content = fs::read_to_string(path).ok()?;
    let state: PersistedMarketplaceUpdateCheckState = serde_json::from_str(&content).ok()?;
    Some(UNIX_EPOCH + Duration::from_secs(state.last_checked_at_unix_secs))
}

fn persist_update_check_time(checked_at: SystemTime) {
    let Some(path) = marketplace_update_check_state_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }

    let state = PersistedMarketplaceUpdateCheckState {
        last_checked_at_unix_secs: checked_at
            .duration_since(UNIX_EPOCH)
            .ok()
            .map(|duration| duration.as_secs())
            .unwrap_or_default(),
    };

    if let Ok(content) = serde_json::to_string(&state) {
        let _ = fs::write(path, content);
    }
}

fn should_run_marketplace_update_check(last_checked: Option<SystemTime>, now: SystemTime) -> bool {
    match last_checked {
        None => true,
        Some(last) => now
            .duration_since(last)
            .map(|elapsed| elapsed >= MARKETPLACE_UPDATE_CHECK_INTERVAL)
            .unwrap_or(true),
    }
}

#[tauri::command]
pub async fn fetch_marketplace_skills(
    force_refresh: bool,
    query: Option<String>,
    page: Option<u32>,
    source_ids: Option<Vec<String>>,
    cache: State<'_, MarketplaceCache>,
    app_cache: State<'_, AppCache>,
) -> Result<MarketplaceSkillsResponse, String> {
    let normalized_query = query
        .as_ref()
        .map(|q| q.trim().to_string())
        .filter(|q| !q.is_empty());
    let normalized_source_filter = normalize_source_filter(source_ids);
    let page = page.unwrap_or(1).max(1);
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);
    let cache_source_scope = resolve_cache_source_scope(
        &normalized_source_filter,
        config.marketplace_sources.as_deref().unwrap_or(&[]),
    );
    let sources = config.marketplace_sources.clone().unwrap_or_default();

    if !force_refresh {
        if let Some(cached) =
            cache.get_fresh_with_meta(page, &normalized_query, &cache_source_scope)
        {
            let installed_skills =
                load_cached_or_scanned_skills(app_cache.inner(), &config.skills_dir)?;
            return Ok(merge_installed_marketplace_skills_into_page(
                cached,
                page,
                &installed_skills,
                &sources,
                normalized_query.as_deref(),
                &cache_source_scope,
                &config.skills_dir,
                github_token.as_deref(),
            )
            .await);
        }
    }

    let runtime_cache_source_scope =
        resolve_cache_source_scope(&normalized_source_filter, &sources);

    let result = match MarketplaceService::fetch_marketplace_skills_page(
        &config.skills_dir,
        normalized_query.clone(),
        page,
    )
    .await
    {
        Ok(result) => result,
        Err(err) => {
            if page == 1 {
                if let Some(cached) = cache.get_any() {
                    let runtime_scope_ids = runtime_cache_source_scope.clone().unwrap_or_default();
                    let runtime_scope_set: HashSet<&str> =
                        runtime_scope_ids.iter().map(String::as_str).collect();
                    let filtered_by_source: Vec<MarketplaceSkill> = if !runtime_scope_set.is_empty()
                        || runtime_cache_source_scope
                            .as_ref()
                            .is_some_and(|ids| ids.is_empty())
                    {
                        cached
                            .into_iter()
                            .filter(|skill| runtime_scope_set.contains(skill.source_id.as_str()))
                            .collect()
                    } else {
                        cached
                    };
                    let filtered = MarketplaceService::filter_marketplace_skills_by_query(
                        filtered_by_source,
                        normalized_query.as_deref(),
                    );
                    let installed_skills =
                        load_cached_or_scanned_skills(app_cache.inner(), &config.skills_dir)?;
                    return Ok(merge_installed_marketplace_skills_into_page(
                        MarketplaceSkillsResponse {
                            skills: filtered,
                            has_more: false,
                        },
                        page,
                        &installed_skills,
                        &sources,
                        normalized_query.as_deref(),
                        &runtime_cache_source_scope,
                        &config.skills_dir,
                        github_token.as_deref(),
                    )
                    .await);
                }
            }
            return Err(err);
        }
    };

    cache.set_page(
        page,
        normalized_query.clone(),
        runtime_cache_source_scope.clone(),
        result.clone(),
    );

    let installed_skills = load_cached_or_scanned_skills(app_cache.inner(), &config.skills_dir)?;
    Ok(merge_installed_marketplace_skills_into_page(
        result,
        page,
        &installed_skills,
        &sources,
        normalized_query.as_deref(),
        &runtime_cache_source_scope,
        &config.skills_dir,
        github_token.as_deref(),
    )
    .await)
}

#[tauri::command]
pub async fn fetch_skill_files(
    repo_url: String,
    skill_path: String,
) -> Result<SkillFileNode, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);
    MarketplaceService::fetch_skill_files(&repo_url, &skill_path, github_token.as_deref()).await
}

#[tauri::command]
pub async fn fetch_clawhub_skill_files(
    slug: String,
    owner: Option<String>,
    version: Option<String>,
) -> Result<ClawhubSkillFilesResponse, String> {
    MarketplaceService::fetch_clawhub_skill_files(&slug, owner.as_deref(), version.as_deref()).await
}

#[tauri::command]
pub async fn fetch_skill_file_content(download_url: String) -> Result<String, String> {
    MarketplaceService::fetch_skill_file_content(&download_url).await
}

#[tauri::command]
pub async fn fetch_marketplace_skill_descriptions(
    skills: Vec<MarketplaceSkillDescriptionRequest>,
) -> Result<HashMap<String, Option<String>>, String> {
    if skills.is_empty() {
        return Ok(HashMap::new());
    }

    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);

    let mut descriptions = HashMap::with_capacity(skills.len());
    for skill in skills {
        if skill.repo_url.trim().is_empty() || skill.skill_path.trim().is_empty() {
            descriptions.insert(skill.id, None);
            continue;
        }
        let description = MarketplaceService::fetch_skill_description(
            &skill.repo_url,
            &skill.skill_path,
            github_token.as_deref(),
        )
        .await;
        descriptions.insert(skill.id, description);
    }

    Ok(descriptions)
}

#[tauri::command]
pub async fn install_marketplace_skill(
    skill_id: String,
    marketplace_cache: State<'_, MarketplaceCache>,
    app_cache: State<'_, AppCache>,
) -> Result<InstallResult, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);

    let skill = if let Some(skill) = marketplace_cache.get_cached_skill(&skill_id) {
        skill
    } else {
        return Err("未找到对应的 Skill，请先在市场列表中加载该技能后再安装".to_string());
    };

    let result =
        MarketplaceService::install_skill(&skill, &config.skills_dir, github_token.as_deref())
            .await?;

    // Invalidate caches so UI can refresh
    app_cache.invalidate_skills();
    marketplace_cache.invalidate();

    Ok(result)
}

#[tauri::command]
pub async fn install_marketplace_skill_by_ref(
    reference: MarketplaceSkillReference,
    marketplace_cache: State<'_, MarketplaceCache>,
    app_cache: State<'_, AppCache>,
) -> Result<InstallResult, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);

    let skill = build_marketplace_skill_from_reference(reference)?;
    let result = if let Some(repo_url) = skill.repo_url.as_deref() {
        let requested_path = skill.skill_path.as_deref().unwrap_or_default();
        let tree = MarketplaceService::fetch_skill_files(
            repo_url,
            requested_path,
            github_token.as_deref(),
        )
        .await?;
        let group_members = expand_skill_group_reference(&skill, &tree);

        if group_members.is_empty() {
            MarketplaceService::install_skill(&skill, &config.skills_dir, github_token.as_deref())
                .await?
        } else {
            for member in &group_members {
                MarketplaceService::install_skill(
                    member,
                    &config.skills_dir,
                    github_token.as_deref(),
                )
                .await?;
            }
            InstallResult {
                success: true,
                skill_id: skill.id.clone(),
                message: Some(format!("已安装 {} 个 Skills", group_members.len())),
                installed_path: Some(config.skills_dir.to_string_lossy().into_owned()),
            }
        }
    } else {
        MarketplaceService::install_skill(&skill, &config.skills_dir, github_token.as_deref())
            .await?
    };

    app_cache.invalidate_skills();
    marketplace_cache.invalidate();

    Ok(result)
}

#[tauri::command]
pub async fn sync_marketplace_installed_skills(
    source_ids: Option<Vec<String>>,
    marketplace_cache: State<'_, MarketplaceCache>,
    app_cache: State<'_, AppCache>,
) -> Result<MarketplaceSyncResult, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);
    let normalized_source_filter = normalize_source_filter(source_ids);
    let sources = config.marketplace_sources.clone().unwrap_or_default();

    let listing = MarketplaceService::fetch_marketplace_skills_page(
        &config.skills_dir,
        None,
        1,
    )
    .await?;
    let installed_skills = load_cached_or_scanned_skills(app_cache.inner(), &config.skills_dir)?;
    let listing = merge_installed_marketplace_skills_into_page(
        listing,
        1,
        &installed_skills,
        &sources,
        None,
        &normalized_source_filter,
        &config.skills_dir,
        github_token.as_deref(),
    )
    .await;

    let mut result = MarketplaceSyncResult {
        checked: 0,
        updated: 0,
        failed: Vec::new(),
    };

    for skill in listing
        .skills
        .into_iter()
        .filter(|skill| skill.install_status == InstallStatus::UpdateAvailable)
    {
        result.checked += 1;
        match MarketplaceService::install_skill(&skill, &config.skills_dir, github_token.as_deref())
            .await
        {
            Ok(_) => {
                result.updated += 1;
            }
            Err(err) => {
                result.failed.push(format!("{}: {}", skill.name, err));
            }
        }
    }

    if result.updated > 0 {
        app_cache.invalidate_skills();
        marketplace_cache.invalidate();
    }

    Ok(result)
}

#[tauri::command]
pub async fn check_marketplace_updates_if_stale(
    marketplace_cache: State<'_, MarketplaceCache>,
    app_cache: State<'_, AppCache>,
) -> Result<MarketplaceUpdateCheckResult, String> {
    let now = SystemTime::now();
    let last_checked = load_last_update_check_time();
    if !should_run_marketplace_update_check(last_checked, now) {
        return Ok(MarketplaceUpdateCheckResult {
            performed: false,
            checked: 0,
            update_available: 0,
        });
    }

    let manager = ConfigManager::new();
    let config = manager.load()?;
    let github_token = github_token_from_config(&config);
    let sources = config.marketplace_sources.clone().unwrap_or_default();

    let listing = MarketplaceService::fetch_marketplace_skills_page(
        &config.skills_dir,
        None,
        1,
    )
    .await?;
    let installed_skills = load_cached_or_scanned_skills(app_cache.inner(), &config.skills_dir)?;
    let merged_listing = merge_installed_marketplace_skills_into_page(
        listing.clone(),
        1,
        &installed_skills,
        &sources,
        None,
        &None,
        &config.skills_dir,
        github_token.as_deref(),
    )
    .await;

    let cache_source_scope = resolve_cache_source_scope(&None, &sources);
    marketplace_cache.set(
        listing.skills.clone(),
        None,
        listing.has_more,
        cache_source_scope,
    );
    persist_update_check_time(now);

    let checked = merged_listing
        .skills
        .iter()
        .filter(|skill| skill.install_status != InstallStatus::NotInstalled)
        .count();
    let update_available = merged_listing
        .skills
        .iter()
        .filter(|skill| skill.install_status == InstallStatus::UpdateAvailable)
        .count();

    Ok(MarketplaceUpdateCheckResult {
        performed: true,
        checked,
        update_available,
    })
}

#[tauri::command]
pub async fn get_marketplace_sources() -> Result<Vec<MarketplaceSource>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    Ok(config.marketplace_sources.clone().unwrap_or_default())
}

#[tauri::command]
pub fn toggle_marketplace_source(source_id: String, enabled: bool) -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    let sources = config
        .marketplace_sources
        .get_or_insert_with(|| AppConfig::default().marketplace_sources.unwrap_or_default());

    let mut found = false;
    for source in sources.iter_mut() {
        if source.id == source_id {
            source.enabled = enabled;
            found = true;
            break;
        }
    }

    if !found {
        return Err(format!("未找到市场源: {}", source_id));
    }

    manager.save(&config)
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::path::PathBuf;
    use std::time::{Duration, SystemTime};

    use crate::models::{
        InstallStatus, MarketplaceMeta, MarketplaceSkill, MarketplaceSkillsResponse,
        MarketplaceSource, Skill, SkillFileNode, SkillSource, SourceType,
    };
    use crate::services::marketplace::{DIRECT_GITHUB_SOURCE_ID, DIRECT_GITHUB_SOURCE_NAME};
    use crate::test_support::with_temp_home;

    use super::{
        build_marketplace_skill_from_reference, collect_installed_marketplace_skills,
        expand_skill_group_reference, load_last_update_check_time, persist_update_check_time,
        prepend_missing_installed_marketplace_skills, resolve_cache_source_scope,
        should_hydrate_missing_installed_marketplace_skill, should_run_marketplace_update_check,
        MarketplaceSkillReference, MARKETPLACE_UPDATE_CHECK_INTERVAL,
    };

    fn make_source(id: &str, enabled: bool) -> MarketplaceSource {
        MarketplaceSource {
            id: id.to_string(),
            name: id.to_string(),
            url: format!("https://{id}.example.com"),
            source_type: SourceType::Api,
            enabled,
            builtin: true,
            api_key: None,
        }
    }

    fn make_marketplace_skill(
        id: &str,
        source_id: &str,
        name: &str,
        description: Option<&str>,
    ) -> Skill {
        Skill {
            id: format!("local-{id}"),
            instance_id: Skill::global_instance_id(&format!("local-{id}")),
            scope: crate::models::SkillScope::Global,
            project_id: None,
            project_name: None,
            name: name.to_string(),
            description: description.map(str::to_string),
            version: "1.0.0".to_string(),
            source: SkillSource::Marketplace,
            marketplace_meta: Some(MarketplaceMeta {
                marketplace_source_id: Some(source_id.to_string()),
                marketplace_skill_id: Some(id.to_string()),
                marketplace_skill_slug: Some(name.to_lowercase()),
                repo_url: Some("https://github.com/example/repo".to_string()),
                skill_path: Some(format!(".claude/skills/{}", name.to_lowercase())),
                remote_revision: Some("rev-local".to_string()),
            }),
            vault_meta: None,
            package_meta: None,
            enabled: HashMap::new(),
            path: PathBuf::from(format!("/tmp/{id}")),
        }
    }

    fn make_listing_skill(id: &str, install_status: InstallStatus) -> MarketplaceSkill {
        MarketplaceSkill {
            id: id.to_string(),
            slug: Some(id.to_string()),
            name: id.to_string(),
            description: None,
            author: None,
            source_id: "src_skills".to_string(),
            source_name: "src_skills".to_string(),
            install_count: None,
            install_url: None,
            created_at: None,
            repo_url: Some("https://github.com/example/repo".to_string()),
            skill_path: Some(format!(".claude/skills/{id}")),
            external_url: None,
            remote_revision: Some("rev-remote".to_string()),
            tags: Vec::new(),
            install_status,
            clawhub_slug: None,
            clawhub_owner: None,
            clawhub_version: None,
        }
    }

    #[test]
    fn should_run_marketplace_update_check_respects_interval() {
        let now = SystemTime::now();
        let just_checked = now
            .checked_sub(Duration::from_secs(60))
            .expect("time should be valid");
        let stale_checked = now
            .checked_sub(MARKETPLACE_UPDATE_CHECK_INTERVAL + Duration::from_secs(1))
            .expect("time should be valid");

        assert!(
            !should_run_marketplace_update_check(Some(just_checked), now),
            "recent check should be skipped"
        );
        assert!(
            should_run_marketplace_update_check(Some(stale_checked), now),
            "stale check should run"
        );
        assert!(
            should_run_marketplace_update_check(None, now),
            "missing check timestamp should run"
        );
    }

    #[test]
    fn update_check_time_round_trip_persists() {
        with_temp_home(|_| {
            let now = SystemTime::now();
            persist_update_check_time(now);
            let loaded = load_last_update_check_time();
            assert!(loaded.is_some(), "expected persisted timestamp");
        });
    }

    #[test]
    fn resolve_cache_source_scope_defaults_to_enabled_sources() {
        let sources = vec![
            make_source("src_skills", true),
            make_source("src_awesome", false),
        ];

        let scope = resolve_cache_source_scope(&None, &sources);

        assert_eq!(
            scope,
            Some(vec!["src_skills".to_string()]),
            "no explicit filter should cache by enabled sources"
        );
    }

    #[test]
    fn resolve_cache_source_scope_intersects_with_enabled_sources() {
        let sources = vec![
            make_source("src_skills", true),
            make_source("src_awesome", false),
        ];
        let explicit = Some(vec![
            "src_awesome".to_string(),
            "src_skills".to_string(),
            "src_skills".to_string(),
        ]);

        let scope = resolve_cache_source_scope(&explicit, &sources);

        assert_eq!(
            scope,
            Some(vec!["src_skills".to_string()]),
            "explicit filter should drop disabled source ids and deduplicate"
        );
    }

    #[test]
    fn build_marketplace_skill_from_reference_requires_repo_url() {
        let reference = MarketplaceSkillReference {
            name: "S1".to_string(),
            marketplace_source_id: Some("source-1".to_string()),
            marketplace_skill_id: Some("source-1::s1".to_string()),
            marketplace_skill_slug: Some("s1".to_string()),
            repo_url: None,
            skill_path: Some(".claude/skills/s1".to_string()),
            remote_revision: None,
        };

        let err = build_marketplace_skill_from_reference(reference).unwrap_err();
        assert!(err.contains("repo_url"));
    }

    #[test]
    fn build_marketplace_skill_from_reference_distinguishes_github_direct_skills_by_repo() {
        let first = build_marketplace_skill_from_reference(MarketplaceSkillReference {
            name: "Demo".to_string(),
            marketplace_source_id: Some("github_direct".to_string()),
            marketplace_skill_id: None,
            marketplace_skill_slug: None,
            repo_url: Some("https://github.com/acme/skills-one".to_string()),
            skill_path: Some("skills/demo".to_string()),
            remote_revision: None,
        })
        .expect("first skill should build");

        let second = build_marketplace_skill_from_reference(MarketplaceSkillReference {
            name: "Demo".to_string(),
            marketplace_source_id: Some("github_direct".to_string()),
            marketplace_skill_id: None,
            marketplace_skill_slug: None,
            repo_url: Some("https://github.com/acme/skills-two".to_string()),
            skill_path: Some("skills/demo".to_string()),
            remote_revision: None,
        })
        .expect("second skill should build");

        assert_ne!(
            first.id, second.id,
            "direct GitHub installs must stay distinct even when skill_path matches"
        );
    }

    #[test]
    fn expand_skill_group_reference_returns_direct_child_skills_when_root_is_container() {
        let skill = MarketplaceSkill {
            id: "github-direct-baoyu-skills".to_string(),
            slug: Some("skills".to_string()),
            name: "skills".to_string(),
            description: None,
            author: None,
            source_id: DIRECT_GITHUB_SOURCE_ID.to_string(),
            source_name: DIRECT_GITHUB_SOURCE_NAME.to_string(),
            install_count: None,
            install_url: None,
            created_at: None,
            repo_url: Some("https://github.com/JimLiu/baoyu-skills".to_string()),
            skill_path: Some("skills".to_string()),
            external_url: Some(
                "https://github.com/JimLiu/baoyu-skills/tree/main/skills".to_string(),
            ),
            remote_revision: None,
            tags: Vec::new(),
            install_status: InstallStatus::NotInstalled,
            clawhub_slug: None,
            clawhub_owner: None,
            clawhub_version: None,
        };
        let tree = SkillFileNode {
            name: "skills".to_string(),
            path: "skills".to_string(),
            is_dir: true,
            download_url: None,
            sha: None,
            children: Some(vec![
                SkillFileNode {
                    name: "baoyu-translate".to_string(),
                    path: "skills/baoyu-translate".to_string(),
                    is_dir: true,
                    download_url: None,
                    sha: None,
                    children: Some(vec![SkillFileNode {
                        name: "SKILL.md".to_string(),
                        path: "skills/baoyu-translate/SKILL.md".to_string(),
                        is_dir: false,
                        download_url: Some("https://example.com/translate".to_string()),
                        sha: None,
                        children: None,
                    }]),
                },
                SkillFileNode {
                    name: "baoyu-slide-deck".to_string(),
                    path: "skills/baoyu-slide-deck".to_string(),
                    is_dir: true,
                    download_url: None,
                    sha: None,
                    children: Some(vec![SkillFileNode {
                        name: "SKILL.md".to_string(),
                        path: "skills/baoyu-slide-deck/SKILL.md".to_string(),
                        is_dir: false,
                        download_url: Some("https://example.com/slides".to_string()),
                        sha: None,
                        children: None,
                    }]),
                },
            ]),
        };

        let expanded = expand_skill_group_reference(&skill, &tree);

        assert_eq!(expanded.len(), 2);
        assert_eq!(
            expanded
                .iter()
                .map(|item| item.skill_path.as_deref().unwrap_or_default())
                .collect::<Vec<_>>(),
            vec!["skills/baoyu-translate", "skills/baoyu-slide-deck"]
        );
        assert_eq!(
            expanded
                .iter()
                .map(|item| item.name.as_str())
                .collect::<Vec<_>>(),
            vec!["baoyu-translate", "baoyu-slide-deck"]
        );
    }

    #[test]
    fn expand_skill_group_reference_returns_empty_for_regular_skill_root() {
        let skill = MarketplaceSkill {
            id: "github-direct-demo".to_string(),
            slug: Some("skills/demo".to_string()),
            name: "demo".to_string(),
            description: None,
            author: None,
            source_id: DIRECT_GITHUB_SOURCE_ID.to_string(),
            source_name: DIRECT_GITHUB_SOURCE_NAME.to_string(),
            install_count: None,
            install_url: None,
            created_at: None,
            repo_url: Some("https://github.com/example/demo".to_string()),
            skill_path: Some("skills/demo".to_string()),
            external_url: Some("https://github.com/example/demo/tree/main/skills/demo".to_string()),
            remote_revision: None,
            tags: Vec::new(),
            install_status: InstallStatus::NotInstalled,
            clawhub_slug: None,
            clawhub_owner: None,
            clawhub_version: None,
        };
        let tree = SkillFileNode {
            name: "demo".to_string(),
            path: "skills/demo".to_string(),
            is_dir: true,
            download_url: None,
            sha: None,
            children: Some(vec![SkillFileNode {
                name: "SKILL.md".to_string(),
                path: "skills/demo/SKILL.md".to_string(),
                is_dir: false,
                download_url: Some("https://example.com/demo".to_string()),
                sha: None,
                children: None,
            }]),
        };

        assert!(expand_skill_group_reference(&skill, &tree).is_empty());
    }

    #[test]
    fn collect_installed_marketplace_skills_respects_source_filter_and_query() {
        let skills = vec![
            make_marketplace_skill("src_skills::alpha", "src_skills", "Alpha", Some("useful")),
            make_marketplace_skill("src_other::beta", "src_other", "Beta", Some("other")),
            Skill {
                id: "local-only".to_string(),
                instance_id: Skill::global_instance_id("local-only"),
                scope: crate::models::SkillScope::Global,
                project_id: None,
                project_name: None,
                name: "Local".to_string(),
                description: Some("ignore".to_string()),
                version: "1.0.0".to_string(),
                source: SkillSource::Local,
                marketplace_meta: None,
                vault_meta: None,
                package_meta: None,
                enabled: HashMap::new(),
                path: PathBuf::from("/tmp/local-only"),
            },
        ];
        let sources = vec![
            make_source("src_skills", true),
            make_source("src_other", true),
        ];
        let source_filter = Some(vec!["src_skills".to_string()]);

        let collected =
            collect_installed_marketplace_skills(&skills, &sources, Some("alp"), &source_filter);

        assert_eq!(collected.len(), 1);
        assert_eq!(collected[0].id, "src_skills::alpha");
        assert_eq!(collected[0].install_status, InstallStatus::Installed);
        assert_eq!(collected[0].source_name, "src_skills");
    }

    #[test]
    fn prepend_missing_installed_marketplace_skills_prepends_only_missing_entries() {
        let response = MarketplaceSkillsResponse {
            skills: vec![
                make_listing_skill("src_skills::alpha", InstallStatus::UpdateAvailable),
                make_listing_skill("src_skills::gamma", InstallStatus::NotInstalled),
            ],
            has_more: true,
        };

        let merged = prepend_missing_installed_marketplace_skills(
            response,
            vec![
                make_listing_skill("src_skills::beta", InstallStatus::Installed),
                make_listing_skill("src_skills::alpha", InstallStatus::Installed),
            ],
        );

        assert_eq!(
            merged
                .skills
                .iter()
                .map(|skill| skill.id.as_str())
                .collect::<Vec<_>>(),
            vec!["src_skills::beta", "src_skills::alpha", "src_skills::gamma"]
        );
        assert_eq!(
            merged.skills[1].install_status,
            InstallStatus::UpdateAvailable
        );
        assert!(merged.has_more);
    }

    #[test]
    fn only_direct_github_installs_are_hydrated_when_missing_from_listing() {
        let builtin = make_listing_skill("src_skills::alpha", InstallStatus::Installed);
        assert!(
            !should_hydrate_missing_installed_marketplace_skill(&builtin),
            "builtin marketplace skills already have remote metadata in listing and should not block page load"
        );

        let direct = MarketplaceSkill {
            source_id: DIRECT_GITHUB_SOURCE_ID.to_string(),
            source_name: DIRECT_GITHUB_SOURCE_NAME.to_string(),
            repo_url: Some("https://github.com/example/repo".to_string()),
            skill_path: Some("skills/demo".to_string()),
            ..make_listing_skill("github-direct-demo", InstallStatus::Installed)
        };
        assert!(
            should_hydrate_missing_installed_marketplace_skill(&direct),
            "direct GitHub installs still need remote hydration for update tracking"
        );
    }
}
