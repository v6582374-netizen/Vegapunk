use rayon::prelude::*;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

use crate::models::{
    AppConfig, MarketplaceMeta, ProjectBinding, Skill, SkillPackageMeta, SkillScope, SkillSource,
    VaultMeta,
};
use crate::services::detector::DetectorService;
use crate::services::linker::LinkerService;

pub struct ScannerService;

#[derive(Debug, Clone)]
pub struct SkillMeta {
    pub name: String,
    pub description: Option<String>,
    pub version: String,
    pub source: SkillSource,
    pub marketplace_meta: Option<MarketplaceMeta>,
    pub vault_meta: Option<VaultMeta>,
    pub package_meta: Option<SkillPackageMeta>,
}

impl ScannerService {
    fn is_skill_dir(path: &Path) -> bool {
        path.join("meta.json").exists()
            || path.join("SKILL.md").exists()
            || path.join("skill.md").exists()
    }

    pub fn scan_skills(skills_dir: &Path) -> Result<Vec<Skill>, String> {
        // Load config to check enabled status for each tool
        let config = crate::services::ConfigManager::new().load()?;
        Self::scan_skills_with_config(skills_dir, &config)
    }

    pub fn scan_skills_with_config(
        skills_dir: &Path,
        config: &AppConfig,
    ) -> Result<Vec<Skill>, String> {
        let mut skills = Self::scan_skills_in_root(skills_dir, config)?;
        skills.sort_by(|a, b| a.id.cmp(&b.id).then_with(|| a.path.cmp(&b.path)));
        Ok(skills)
    }

    pub fn scan_global_skills(config: &AppConfig) -> Result<Vec<Skill>, String> {
        let mut skills = Self::scan_skills_in_root(&config.skills_dir, config)?;
        skills.sort_by(|a, b| a.instance_id.cmp(&b.instance_id));
        Ok(skills)
    }

    pub fn scan_project_skills(
        project_binding: &ProjectBinding,
        config: &AppConfig,
    ) -> Result<Vec<Skill>, String> {
        let mut skills = Self::scan_skills_in_root(&project_binding.skills_dir, config)?
            .into_iter()
            .map(|skill| {
                let mut scoped_skill = skill.with_scope(
                    SkillScope::Project,
                    Some(project_binding.id.clone()),
                    Some(project_binding.name.clone()),
                );
                scoped_skill.enabled = Self::check_enabled_status_for_scope(
                    &scoped_skill.path,
                    &scoped_skill.id,
                    &scoped_skill.scope,
                    config,
                );
                scoped_skill
            })
            .collect::<Vec<_>>();
        skills.sort_by(|a, b| a.instance_id.cmp(&b.instance_id));
        Ok(skills)
    }

    pub fn scan_scoped_skills(config: &AppConfig) -> Result<Vec<Skill>, String> {
        let mut skills = Self::scan_global_skills(config)?;

        if let Some(active_project_id) = config.active_project_id.as_deref() {
            if let Some(project_binding) = config
                .projects
                .iter()
                .find(|project| project.id == active_project_id)
            {
                let mut project_skills = Self::scan_project_skills(project_binding, config)?;
                skills.append(&mut project_skills);
            }
        }

        skills.sort_by(|a, b| {
            a.instance_id
                .cmp(&b.instance_id)
                .then_with(|| a.path.cmp(&b.path))
        });
        Self::ensure_unique_instance_ids(&skills)?;
        Ok(skills)
    }

    /// Maximum recursion depth when scanning for skills in nested directories.
    /// Handles structures like skills/superpowers/skill-a/SKILL.md (depth 3).
    const MAX_SCAN_DEPTH: usize = 5;

    fn scan_skills_in_root(skills_dir: &Path, config: &AppConfig) -> Result<Vec<Skill>, String> {
        if !skills_dir.exists() {
            return Ok(Vec::new());
        }

        let skills = Self::scan_dir_recursive(skills_dir, config, 0);

        let mut skills: Vec<Skill> = skills;
        skills.sort_by(|a, b| {
            a.id.cmp(&b.id)
                .then_with(|| {
                    Self::skill_depth(&a.path, skills_dir)
                        .cmp(&Self::skill_depth(&b.path, skills_dir))
                })
                .then_with(|| a.path.cmp(&b.path))
        });
        Self::dedupe_skill_ids_preferring_shallower_paths(skills, skills_dir)
    }

    /// Recursively scan a directory for skills.
    /// - If the directory itself is a skill dir, load it and stop (no deeper recursion).
    /// - Otherwise, recurse into child directories up to MAX_SCAN_DEPTH.
    fn scan_dir_recursive(dir: &Path, config: &AppConfig, depth: usize) -> Vec<Skill> {
        if depth >= Self::MAX_SCAN_DEPTH {
            return Vec::new();
        }

        let entries: Vec<_> = match fs::read_dir(dir) {
            Ok(rd) => rd.flatten().collect(),
            Err(_) => return Vec::new(),
        };

        entries
            .par_iter()
            .flat_map_iter(|entry| {
                let path = entry.path();
                if !path.is_dir() {
                    return Vec::new();
                }

                // Skip hidden directories (e.g. .git, .skill-studio)
                if path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with('.'))
                    .unwrap_or(false)
                {
                    return Vec::new();
                }

                if Self::is_skill_dir(&path) {
                    // Found a skill — load it, do not recurse deeper
                    return Self::load_skill_with_config(&path, config)
                        .map(|skill| vec![skill])
                        .unwrap_or_default();
                }

                // Not a skill dir — recurse into children
                Self::scan_dir_recursive(&path, config, depth + 1)
            })
            .collect()
    }

    fn skill_depth(path: &Path, skills_dir: &Path) -> usize {
        path.strip_prefix(skills_dir)
            .map(|relative_path| relative_path.components().count())
            .unwrap_or(usize::MAX)
    }

    fn dedupe_skill_ids_preferring_shallower_paths(
        skills: Vec<Skill>,
        skills_dir: &Path,
    ) -> Result<Vec<Skill>, String> {
        let mut deduped = Vec::new();
        let mut iter = skills.into_iter().peekable();

        while let Some(skill) = iter.next() {
            let skill_id = skill.id.clone();
            let mut chosen = skill;
            let chosen_depth = Self::skill_depth(&chosen.path, skills_dir);

            while let Some(next) = iter.peek() {
                if next.id != skill_id {
                    break;
                }

                let next_depth = Self::skill_depth(&next.path, skills_dir);
                if next_depth == chosen_depth && next.path != chosen.path {
                    eprintln!(
                        "[skills-manager] duplicate skill id ignored: {} (keeping {}, skipping {})",
                        skill_id,
                        chosen.path.display(),
                        next.path.display()
                    );
                    iter.next();
                    continue;
                }

                if next_depth < chosen_depth {
                    chosen = iter.next().expect("peeked skill still available");
                } else {
                    iter.next();
                }
            }

            deduped.push(chosen);
        }

        Ok(deduped)
    }

    fn ensure_unique_instance_ids(skills: &[Skill]) -> Result<(), String> {
        for pair in skills.windows(2) {
            if pair[0].instance_id == pair[1].instance_id {
                return Err(format!(
                    "Duplicate skill instance id: {} ({} and {})",
                    pair[0].instance_id,
                    pair[0].path.display(),
                    pair[1].path.display()
                ));
            }
        }

        Ok(())
    }

    #[allow(dead_code)]
    pub fn load_skill(skill_path: &Path) -> Result<Skill, String> {
        let config = crate::services::ConfigManager::new().load()?;
        Self::load_skill_with_config(skill_path, &config)
    }

    pub fn load_skill_with_config(skill_path: &Path, config: &AppConfig) -> Result<Skill, String> {
        let id = skill_path
            .file_name()
            .and_then(|n| n.to_str())
            .map(|s| s.to_string())
            .ok_or("Invalid skill directory name")?;

        let meta_path = skill_path.join("meta.json");
        let skill_md_upper = skill_path.join("SKILL.md");
        let skill_md_lower = skill_path.join("skill.md");

        let mut meta = if meta_path.exists() {
            Self::load_meta(&meta_path)?
        } else if skill_md_upper.exists() {
            Self::parse_frontmatter(&skill_md_upper)?
        } else if skill_md_lower.exists() {
            Self::parse_frontmatter(&skill_md_lower)?
        } else {
            Self::generate_meta(&id)
        };
        if meta.description.is_none() {
            let fallback = if skill_md_upper.exists() {
                Self::parse_frontmatter(&skill_md_upper).ok()
            } else if skill_md_lower.exists() {
                Self::parse_frontmatter(&skill_md_lower).ok()
            } else {
                None
            };
            if let Some(fallback_meta) = fallback {
                let description = fallback_meta.description.and_then(|raw| {
                    let trimmed = raw.trim();
                    if trimmed.is_empty() {
                        None
                    } else {
                        Some(trimmed.to_string())
                    }
                });
                if description.is_some() {
                    meta.description = description;
                }
            }
        }

        // Check enabled status by looking for symlinks in each tool's skills directory
        let enabled =
            Self::check_enabled_status_for_scope(skill_path, &id, &SkillScope::Global, config);

        Ok(Skill {
            id: id.clone(),
            instance_id: Skill::global_instance_id(&id),
            scope: SkillScope::Global,
            project_id: None,
            project_name: None,
            name: meta.name,
            description: meta.description,
            version: meta.version,
            source: meta.source,
            marketplace_meta: meta.marketplace_meta,
            vault_meta: meta.vault_meta,
            package_meta: meta.package_meta,
            enabled,
            path: skill_path.to_path_buf(),
        })
    }

    /// Check if this skill is enabled for each tool by looking for symlinks
    fn check_enabled_status_for_scope(
        skill_path: &Path,
        skill_id: &str,
        scope: &SkillScope,
        config: &AppConfig,
    ) -> HashMap<String, bool> {
        let mut enabled = HashMap::new();

        for (tool_id, tool_config) in config.collect_tool_configs() {
            match LinkerService::check_link_for_scoped_skill(
                skill_path,
                &tool_config.skills_path,
                skill_id,
                &tool_id,
                scope,
            ) {
                crate::services::LinkStatus::Valid => {
                    enabled.insert(tool_id, true);
                }
                crate::services::LinkStatus::Missing => {}
                _ => {
                    enabled.insert(tool_id, false);
                }
            }
        }

        enabled
    }

    fn load_meta(meta_path: &Path) -> Result<SkillMeta, String> {
        let content = fs::read_to_string(meta_path)
            .map_err(|e| format!("Failed to read meta.json: {}", e))?;

        #[derive(serde::Deserialize)]
        struct MetaJson {
            name: Option<String>,
            description: Option<String>,
            version: Option<String>,
            source: Option<String>,
            marketplace_source_id: Option<String>,
            marketplace_skill_id: Option<String>,
            marketplace_skill_slug: Option<String>,
            repo_url: Option<String>,
            skill_path: Option<String>,
            remote_revision: Option<String>,
            vault_provider: Option<String>,
            vault_user_id: Option<String>,
            vault_skill_id: Option<String>,
            vault_version: Option<String>,
            vault_hash: Option<String>,
            vault_size: Option<u64>,
            vault_updated_at: Option<i64>,
            package_id: Option<String>,
            package_name: Option<String>,
            package_member_id: Option<String>,
            package_version: Option<String>,
        }

        let meta: MetaJson = serde_json::from_str(&content)
            .map_err(|e| format!("Failed to parse meta.json: {}", e))?;

        let name = meta.name.unwrap_or_else(|| {
            meta_path
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|n| n.to_str())
                .unwrap_or("Unknown")
                .to_string()
        });

        let source = match meta.source.as_deref() {
            Some("marketplace") => SkillSource::Marketplace,
            Some("vault") => SkillSource::Vault,
            Some("imported") => SkillSource::Imported,
            _ => SkillSource::Local,
        };

        let has_marketplace_meta = meta.marketplace_skill_id.is_some()
            || meta.marketplace_source_id.is_some()
            || meta.marketplace_skill_slug.is_some()
            || meta.repo_url.is_some()
            || meta.skill_path.is_some()
            || meta.remote_revision.is_some();
        let marketplace_meta = if source == SkillSource::Marketplace || has_marketplace_meta {
            Some(MarketplaceMeta {
                marketplace_source_id: meta.marketplace_source_id,
                marketplace_skill_id: meta.marketplace_skill_id,
                marketplace_skill_slug: meta.marketplace_skill_slug,
                repo_url: meta.repo_url,
                skill_path: meta.skill_path,
                remote_revision: meta.remote_revision,
            })
        } else {
            None
        };

        let has_vault_meta = meta.vault_skill_id.is_some()
            || meta.vault_user_id.is_some()
            || meta.vault_provider.is_some()
            || meta.vault_version.is_some()
            || meta.vault_hash.is_some()
            || meta.vault_size.is_some()
            || meta.vault_updated_at.is_some();
        let vault_meta = if source == SkillSource::Vault || has_vault_meta {
            Some(VaultMeta {
                provider: meta.vault_provider,
                user_id: meta.vault_user_id,
                skill_id: meta.vault_skill_id,
                version: meta.vault_version,
                hash: meta.vault_hash,
                size: meta.vault_size,
                updated_at: meta.vault_updated_at,
            })
        } else {
            None
        };

        let package_meta = match (meta.package_id, meta.package_member_id) {
            (Some(package_id), Some(package_member_id)) => Some(SkillPackageMeta {
                package_id,
                package_name: meta.package_name,
                package_member_id,
                package_version: meta.package_version,
            }),
            _ => None,
        };

        Ok(SkillMeta {
            name,
            description: meta.description,
            version: meta.version.unwrap_or_else(|| "1.0".to_string()),
            source,
            marketplace_meta,
            vault_meta,
            package_meta,
        })
    }

    pub fn parse_frontmatter(skill_md_path: &Path) -> Result<SkillMeta, String> {
        let content = fs::read_to_string(skill_md_path)
            .map_err(|e| format!("Failed to read skill.md: {}", e))?;

        let mut name = None;
        let mut description = None;

        if content.starts_with("---") {
            if let Some(end_idx) = content[3..].find("---") {
                let frontmatter = &content[3..3 + end_idx];
                for line in frontmatter.lines() {
                    let line = line.trim();
                    if let Some(value) = line.strip_prefix("name:") {
                        name = Some(value.trim().trim_matches('"').to_string());
                    } else if let Some(value) = line.strip_prefix("description:") {
                        description = Some(value.trim().trim_matches('"').to_string());
                    }
                }
            }
        }

        let default_name = skill_md_path
            .parent()
            .and_then(|p| p.file_name())
            .and_then(|n| n.to_str())
            .unwrap_or("Unknown")
            .to_string();

        Ok(SkillMeta {
            name: name.unwrap_or(default_name),
            description,
            version: "1.0".to_string(),
            source: SkillSource::Local,
            marketplace_meta: None,
            vault_meta: None,
            package_meta: None,
        })
    }

    pub fn generate_meta(id: &str) -> SkillMeta {
        SkillMeta {
            name: id.replace('-', " ").replace('_', " "),
            description: None,
            version: "1.0".to_string(),
            source: SkillSource::Local,
            marketplace_meta: None,
            vault_meta: None,
            package_meta: None,
        }
    }

    #[allow(dead_code)]
    pub fn save_meta(skill_path: &Path, meta: &SkillMeta) -> Result<(), String> {
        let meta_path = skill_path.join("meta.json");

        #[derive(serde::Serialize)]
        struct MetaJson<'a> {
            name: &'a str,
            description: Option<&'a str>,
            version: &'a str,
        }

        let json = MetaJson {
            name: &meta.name,
            description: meta.description.as_deref(),
            version: &meta.version,
        };

        let content = serde_json::to_string_pretty(&json)
            .map_err(|e| format!("Failed to serialize meta: {}", e))?;

        fs::write(&meta_path, content).map_err(|e| format!("Failed to write meta.json: {}", e))
    }

    pub fn scan_all_tools() -> Result<Vec<Skill>, String> {
        let mut all_skills = Vec::new();
        let tools = DetectorService::detect_all();

        for tool in tools {
            if tool.detected {
                let skills_path = &tool.config.skills_path;
                if skills_path.exists() {
                    let skills = Self::scan_skills(skills_path)?;
                    all_skills.extend(skills);
                }
            }
        }

        // De-duplicate (by skill id)
        all_skills.sort_by(|a, b| a.id.cmp(&b.id));
        all_skills.dedup_by(|a, b| a.id == b.id);

        Ok(all_skills)
    }
}

#[cfg(test)]
mod tests {
    use super::ScannerService;
    use crate::models::{AppConfig, SkillSource};
    use crate::test_support::with_temp_home;
    use serde_json::json;
    use std::fs;

    #[test]
    fn load_skill_with_config_falls_back_to_skill_md_description_when_meta_is_null() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skill_dir = home
                .join(".skills-manager")
                .join("skills")
                .join("marketplace-test-skill");
            fs::create_dir_all(&skill_dir).expect("create skill dir");

            let meta_content = r#"{
  "name": "marketplace-test-skill",
  "description": null,
  "version": "1.0"
}"#;
            fs::write(skill_dir.join("meta.json"), meta_content).expect("write meta.json");

            let skill_md = r#"---
name: marketplace-test-skill
description: "Description from SKILL.md"
---

# marketplace-test-skill
"#;
            fs::write(skill_dir.join("SKILL.md"), skill_md).expect("write SKILL.md");

            let skill =
                ScannerService::load_skill_with_config(&skill_dir, &config).expect("load skill");
            assert_eq!(
                skill.description,
                Some("Description from SKILL.md".to_string())
            );
        });
    }

    #[test]
    fn load_skill_with_config_keeps_meta_description_when_present() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skill_dir = home
                .join(".skills-manager")
                .join("skills")
                .join("marketplace-test-skill");
            fs::create_dir_all(&skill_dir).expect("create skill dir");

            let meta_content = r#"{
  "name": "marketplace-test-skill",
  "description": "Description from meta",
  "version": "1.0"
}"#;
            fs::write(skill_dir.join("meta.json"), meta_content).expect("write meta.json");

            let skill_md = r#"---
name: marketplace-test-skill
description: "Description from SKILL.md"
---

# marketplace-test-skill
"#;
            fs::write(skill_dir.join("SKILL.md"), skill_md).expect("write SKILL.md");

            let skill =
                ScannerService::load_skill_with_config(&skill_dir, &config).expect("load skill");
            assert_eq!(skill.description, Some("Description from meta".to_string()));
        });
    }

    #[test]
    fn load_skill_reads_marketplace_meta_fields() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skill_dir = home
                .join(".skills-manager")
                .join("skills")
                .join("mkt-skill");
            fs::create_dir_all(&skill_dir).expect("create skill dir");

            let meta_content = r#"{
  "name": "mkt-skill",
  "version": "1.0",
  "source": "marketplace",
  "marketplace_skill_id": "mkt-123",
  "marketplace_skill_slug": "mkt-skill",
  "marketplace_source_id": "source-1",
  "repo_url": "https://github.com/acme/repo",
  "skill_path": ".claude/skills/mkt-skill"
}"#;
            fs::write(skill_dir.join("meta.json"), meta_content).expect("write meta.json");

            let skill =
                ScannerService::load_skill_with_config(&skill_dir, &config).expect("load skill");
            assert_eq!(skill.source, SkillSource::Marketplace);
            let marketplace = skill.marketplace_meta.expect("marketplace meta");
            assert_eq!(
                marketplace.marketplace_skill_id,
                Some("mkt-123".to_string())
            );
            assert_eq!(
                marketplace.marketplace_skill_slug,
                Some("mkt-skill".to_string())
            );
            assert_eq!(
                marketplace.marketplace_source_id,
                Some("source-1".to_string())
            );
            assert_eq!(
                marketplace.repo_url,
                Some("https://github.com/acme/repo".to_string())
            );
            assert_eq!(
                marketplace.skill_path,
                Some(".claude/skills/mkt-skill".to_string())
            );
        });
    }

    #[test]
    fn load_skill_with_config_exposes_package_meta_from_meta_json() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skill_dir = home
                .join(".skills-manager")
                .join("skills")
                .join("superpowers--brainstorming");
            fs::create_dir_all(&skill_dir).expect("create skill dir");

            let meta_content = r#"{
  "name": "brainstorming",
  "description": "Use before creative work",
  "version": "1.0.0",
  "package_id": "superpowers",
  "package_name": "Superpowers",
  "package_member_id": "brainstorming",
  "package_version": "1.0.0"
}"#;
            fs::write(skill_dir.join("meta.json"), meta_content).expect("write meta.json");

            let skill =
                ScannerService::load_skill_with_config(&skill_dir, &config).expect("load skill");
            let serialized = serde_json::to_value(skill).expect("serialize skill");

            assert_eq!(
                serialized.get("package_meta"),
                Some(&json!({
                    "package_id": "superpowers",
                    "package_name": "Superpowers",
                    "package_member_id": "brainstorming",
                    "package_version": "1.0.0"
                }))
            );
        });
    }

    #[test]
    fn load_skill_with_config_keeps_package_meta_absent_for_plain_skill() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skill_dir = home
                .join(".skills-manager")
                .join("skills")
                .join("plain-skill");
            fs::create_dir_all(&skill_dir).expect("create skill dir");

            fs::write(
                skill_dir.join("meta.json"),
                r#"{
  "name": "plain-skill",
  "description": "A plain skill",
  "version": "1.0.0"
}"#,
            )
            .expect("write meta.json");

            let skill =
                ScannerService::load_skill_with_config(&skill_dir, &config).expect("load skill");
            let serialized = serde_json::to_value(skill).expect("serialize skill");

            assert_eq!(serialized.get("package_meta"), None);
        });
    }

    #[test]
    fn scan_skills_with_config_ignores_container_dirs_without_skill_files() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills root");

            let valid_skill_dir = skills_dir.join("valid-skill");
            fs::create_dir_all(&valid_skill_dir).expect("create valid skill dir");
            fs::write(
                valid_skill_dir.join("SKILL.md"),
                "---\nname: valid-skill\n---\n",
            )
            .expect("write valid SKILL.md");

            for container_dir in [".skill-studio", "learned", "superpowers"] {
                fs::create_dir_all(skills_dir.join(container_dir)).expect("create container dir");
            }

            let mut skills =
                ScannerService::scan_skills_with_config(&skills_dir, &config).expect("scan skills");
            skills.sort_by(|a, b| a.id.cmp(&b.id));

            let ids: Vec<&str> = skills.iter().map(|skill| skill.id.as_str()).collect();
            assert_eq!(ids, vec!["valid-skill"]);
        });
    }

    #[test]
    fn scan_skills_with_config_includes_legacy_group_member_skills() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills root");

            let translate_dir = skills_dir.join("baoyu-skills").join("baoyu-translate");
            fs::create_dir_all(&translate_dir).expect("create translate dir");
            fs::write(
                translate_dir.join("SKILL.md"),
                "---\nname: baoyu-translate\n---\n",
            )
            .expect("write translate skill");

            let slide_dir = skills_dir.join("baoyu-skills").join("baoyu-slide-deck");
            fs::create_dir_all(&slide_dir).expect("create slide dir");
            fs::write(
                slide_dir.join("SKILL.md"),
                "---\nname: baoyu-slide-deck\n---\n",
            )
            .expect("write slide skill");

            let mut skills =
                ScannerService::scan_skills_with_config(&skills_dir, &config).expect("scan skills");
            skills.sort_by(|a, b| a.id.cmp(&b.id));

            let ids: Vec<&str> = skills.iter().map(|skill| skill.id.as_str()).collect();
            assert_eq!(ids, vec!["baoyu-slide-deck", "baoyu-translate"]);
        });
    }

    #[test]
    fn scan_skills_with_config_returns_global_and_active_project_skill_instances() {
        with_temp_home(|home| {
            let global_skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&global_skills_dir).expect("create global skills root");

            let project_root = home.join("code").join("project-alpha");
            let project_skills_dir = project_root.join(".claude").join("skills");
            fs::create_dir_all(&project_skills_dir).expect("create project skills root");

            for skill_dir in [
                global_skills_dir.join("shared-skill"),
                global_skills_dir.join("global-only-skill"),
                project_skills_dir.join("shared-skill"),
                project_skills_dir.join("project-only-skill"),
            ] {
                fs::create_dir_all(&skill_dir).expect("create skill dir");
                let skill_name = skill_dir
                    .file_name()
                    .and_then(|name| name.to_str())
                    .expect("skill dir name");
                fs::write(
                    skill_dir.join("SKILL.md"),
                    format!("---\nname: {}\n---\n", skill_name),
                )
                .expect("write SKILL.md");
            }

            let mut config = AppConfig::default();
            config.skills_dir = global_skills_dir.clone();
            let config_value = json!({
                "version": config.version,
                "skills_dir": config.skills_dir,
                "tools": config.tools,
                "custom_tools": config.custom_tools,
                "skill_metadata": config.skill_metadata,
                "preferences": config.preferences,
                "marketplace_sources": config.marketplace_sources,
                "initialized": config.initialized,
                "projects": [
                    {
                        "id": "project-alpha",
                        "name": "Project Alpha",
                        "root_path": project_root,
                        "skills_dir": project_skills_dir
                    }
                ],
                "active_project_id": "project-alpha"
            });
            let config: AppConfig =
                serde_json::from_value(config_value).expect("deserialize config with projects");

            let mut skills =
                ScannerService::scan_scoped_skills(&config).expect("scan scoped skills");
            skills.sort_by(|a, b| a.instance_id.cmp(&b.instance_id));

            assert_eq!(skills.len(), 4);
            assert_eq!(
                skills
                    .iter()
                    .map(|skill| skill.instance_id.as_str())
                    .collect::<Vec<_>>(),
                vec![
                    "global:global-only-skill",
                    "global:shared-skill",
                    "project:project-alpha:project-only-skill",
                    "project:project-alpha:shared-skill",
                ]
            );

            let global_shared = skills
                .iter()
                .find(|skill| skill.instance_id == "global:shared-skill")
                .expect("global shared skill");
            assert_eq!(global_shared.id, "shared-skill");
            assert_eq!(
                serde_json::to_value(global_shared)
                    .expect("serialize global")
                    .get("scope"),
                Some(&json!("global"))
            );
            assert_eq!(global_shared.project_id, None);
            assert_eq!(global_shared.project_name, None);

            let project_shared = skills
                .iter()
                .find(|skill| skill.instance_id == "project:project-alpha:shared-skill")
                .expect("project shared skill");
            assert_eq!(project_shared.id, "shared-skill");
            assert_eq!(
                serde_json::to_value(project_shared)
                    .expect("serialize project")
                    .get("scope"),
                Some(&json!("project"))
            );
            assert_eq!(project_shared.project_id.as_deref(), Some("project-alpha"));
            assert_eq!(
                project_shared.project_name.as_deref(),
                Some("Project Alpha")
            );
        });
    }

    #[test]
    fn scan_scoped_skills_does_not_mark_same_id_instances_both_enabled() {
        with_temp_home(|home| {
            let global_skills_dir = home.join(".skills-manager").join("skills");
            let global_skill_dir = global_skills_dir.join("shared-skill");
            fs::create_dir_all(&global_skill_dir).expect("create global skill dir");
            fs::write(
                global_skill_dir.join("SKILL.md"),
                "---\nname: shared-skill\n---\n",
            )
            .expect("write global skill");

            let project_root = home.join("code").join("project-alpha");
            let project_skills_dir = project_root.join(".claude").join("skills");
            let project_skill_dir = project_skills_dir.join("shared-skill");
            fs::create_dir_all(&project_skill_dir).expect("create project skill dir");
            fs::write(
                project_skill_dir.join("SKILL.md"),
                "---\nname: shared-skill\n---\n",
            )
            .expect("write project skill");

            let tool_skills_dir = home.join(".claude").join("skills");
            fs::create_dir_all(&tool_skills_dir).expect("create tool skills dir");
            std::os::unix::fs::symlink(&project_skill_dir, tool_skills_dir.join("shared-skill"))
                .expect("link project skill");

            let config: AppConfig = serde_json::from_value(json!({
                "version": "2.0.1",
                "skills_dir": global_skills_dir,
                "tools": {
                    "claude": {
                        "enabled": true,
                        "detected": true,
                        "skills_path": tool_skills_dir,
                        "config_path": home.join(".claude")
                    }
                },
                "custom_tools": {},
                "projects": [{
                    "id": "project-alpha",
                    "name": "Project Alpha",
                    "root_path": project_root,
                    "skills_dir": project_skills_dir
                }],
                "active_project_id": "project-alpha",
                "initialized": true
            }))
            .expect("deserialize config");

            let skills = ScannerService::scan_scoped_skills(&config).expect("scan scoped skills");
            let global = skills
                .iter()
                .find(|skill| skill.instance_id == "global:shared-skill")
                .expect("global instance");
            let project = skills
                .iter()
                .find(|skill| skill.instance_id == "project:project-alpha:shared-skill")
                .expect("project instance");

            assert_eq!(global.enabled.get("claude").copied(), Some(false));
            assert_eq!(project.enabled.get("claude").copied(), Some(true));
        });
    }

    #[test]
    fn scan_global_skills_keeps_legacy_copy_mode_skill_enabled_without_metadata() {
        with_temp_home(|home| {
            let global_skills_dir = home.join(".skills-manager").join("skills");
            let global_skill_dir = global_skills_dir.join("shared-skill");
            fs::create_dir_all(&global_skill_dir).expect("create global skill dir");
            fs::write(
                global_skill_dir.join("SKILL.md"),
                "---\nname: shared-skill\n---\n",
            )
            .expect("write global skill");

            let iflow_skills_dir = home.join(".iflow").join("skills");
            let copied_skill_dir = iflow_skills_dir.join("shared-skill");
            fs::create_dir_all(&copied_skill_dir).expect("create copied skill dir");
            fs::write(
                copied_skill_dir.join("SKILL.md"),
                "---\nname: shared-skill\n---\n",
            )
            .expect("write copied skill");

            let config: AppConfig = serde_json::from_value(json!({
                "version": "2.0.1",
                "skills_dir": global_skills_dir,
                "tools": {
                    "iflow": {
                        "enabled": true,
                        "detected": true,
                        "skills_path": iflow_skills_dir,
                        "config_path": home.join(".iflow")
                    }
                },
                "custom_tools": {},
                "initialized": true
            }))
            .expect("deserialize config");

            let skills = ScannerService::scan_global_skills(&config).expect("scan global skills");
            let global = skills
                .iter()
                .find(|skill| skill.instance_id == "global:shared-skill")
                .expect("global skill");

            assert_eq!(global.enabled.get("iflow").copied(), Some(true));
        });
    }

    #[test]
    fn scan_skills_with_config_ignores_nested_duplicate_skill_dirs_in_container_folders() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills root");

            let top_level_dir = skills_dir.join("academic-research-writer");
            fs::create_dir_all(&top_level_dir).expect("create top level skill dir");
            fs::write(
                top_level_dir.join("SKILL.md"),
                "---\nname: academic-research-writer\n---\n",
            )
            .expect("write top level skill");

            let nested_dir = skills_dir
                .join("openclaw-imports")
                .join("academic-research-writer");
            fs::create_dir_all(&nested_dir).expect("create nested skill dir");
            fs::write(
                nested_dir.join("SKILL.md"),
                "---\nname: academic-research-writer\n---\n",
            )
            .expect("write nested skill");

            let mut skills =
                ScannerService::scan_skills_with_config(&skills_dir, &config).expect("scan skills");
            skills.sort_by(|a, b| a.id.cmp(&b.id).then_with(|| a.path.cmp(&b.path)));

            assert_eq!(skills.len(), 1);
            assert_eq!(skills[0].id, "academic-research-writer");
            assert_eq!(skills[0].path, top_level_dir);
        });
    }

    #[test]
    fn scan_skills_with_config_keeps_first_when_same_id_same_depth_different_containers() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills root");

            let a = skills_dir.join("containerA").join("dup-skill");
            fs::create_dir_all(&a).expect("create A");
            fs::write(a.join("SKILL.md"), "---\nname: dup-skill\n---\n").expect("write A");

            let b = skills_dir.join("containerB").join("dup-skill");
            fs::create_dir_all(&b).expect("create B");
            fs::write(b.join("SKILL.md"), "---\nname: dup-skill\n---\n").expect("write B");

            let skills = ScannerService::scan_skills_with_config(&skills_dir, &config)
                .expect("scan should not fail on duplicates");
            let dup_skills: Vec<_> = skills.iter().filter(|s| s.id == "dup-skill").collect();
            assert_eq!(
                dup_skills.len(),
                1,
                "expected single deduped entry, got {dup_skills:?}"
            );
        });
    }

    #[test]
    fn scan_skills_with_config_discovers_deeply_nested_skills_superpowers_pattern() {
        with_temp_home(|home| {
            let config = AppConfig::default();
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills root");

            // Simulate superpowers repo: skills/superpowers/<skill-name>/SKILL.md
            let brainstorming = skills_dir.join("superpowers").join("brainstorming");
            fs::create_dir_all(&brainstorming).expect("create brainstorming dir");
            fs::write(
                brainstorming.join("SKILL.md"),
                "---\nname: brainstorming\n---\n",
            )
            .expect("write brainstorming skill");

            let debugging = skills_dir.join("superpowers").join("debugging");
            fs::create_dir_all(&debugging).expect("create debugging dir");
            fs::write(
                debugging.join("SKILL.md"),
                "---\nname: debugging\n---\n",
            )
            .expect("write debugging skill");

            // Also a top-level skill to ensure mixed scanning works
            let top_skill = skills_dir.join("my-top-skill");
            fs::create_dir_all(&top_skill).expect("create top skill dir");
            fs::write(
                top_skill.join("SKILL.md"),
                "---\nname: my-top-skill\n---\n",
            )
            .expect("write top skill");

            let mut skills =
                ScannerService::scan_skills_with_config(&skills_dir, &config).expect("scan skills");
            skills.sort_by(|a, b| a.id.cmp(&b.id));

            let ids: Vec<&str> = skills.iter().map(|s| s.id.as_str()).collect();
            assert_eq!(ids, vec!["brainstorming", "debugging", "my-top-skill"]);
        });
    }
}
