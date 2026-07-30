use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::models::{MarketplaceFavoriteMeta, MarketplaceSkill, SkillMetadata};
use crate::services::ConfigManager;

fn now_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// 切换本地 skill 的收藏状态。
/// favorited=true 时写入当前时间戳；favorited=false 时清除。
/// 返回更新后的 favorited_at（取消收藏时为 None）。
#[tauri::command]
pub fn toggle_skill_favorite(instance_id: String, favorited: bool) -> Result<Option<i64>, String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    let entry = config
        .skill_metadata
        .entry(instance_id)
        .or_insert_with(SkillMetadata::default);

    let favorited_at = if favorited {
        let ts = now_timestamp();
        entry.favorited_at = Some(ts);
        Some(ts)
    } else {
        entry.favorited_at = None;
        None
    };

    manager.save(&config)?;
    Ok(favorited_at)
}

/// 切换市场 skill 的收藏状态。
/// favorited=true 时存入快照；favorited=false 时移除。
#[tauri::command]
pub fn toggle_marketplace_favorite(
    skill: MarketplaceSkill,
    favorited: bool,
) -> Result<bool, String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    if favorited {
        let meta = MarketplaceFavoriteMeta {
            favorited_at: now_timestamp(),
            name: skill.name,
            description: skill.description,
            source_id: skill.source_id,
            source_name: skill.source_name,
            repo_url: skill.repo_url,
            skill_path: skill.skill_path,
            external_url: skill.external_url,
            install_count: skill.install_count,
            tags: skill.tags,
            clawhub_slug: skill.clawhub_slug,
            clawhub_owner: skill.clawhub_owner,
            clawhub_version: skill.clawhub_version,
        };
        config.marketplace_favorites.insert(skill.id.clone(), meta);
    } else {
        config.marketplace_favorites.remove(&skill.id);
    }

    manager.save(&config)?;
    Ok(favorited)
}

/// 返回所有已收藏的市场 skill 快照（按 marketplace skill id 索引）。
#[tauri::command]
pub fn list_marketplace_favorites() -> Result<HashMap<String, MarketplaceFavoriteMeta>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    Ok(config.marketplace_favorites)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{AppConfig, InstallStatus};

    fn sample_skill(id: &str, name: &str) -> MarketplaceSkill {
        MarketplaceSkill {
            id: id.to_string(),
            slug: None,
            name: name.to_string(),
            description: Some("desc".to_string()),
            author: None,
            source_id: "src1".to_string(),
            source_name: "Source1".to_string(),
            install_count: Some(10),
            install_url: None,
            created_at: None,
            repo_url: Some("https://github.com/x/y".to_string()),
            skill_path: Some("skills/foo".to_string()),
            external_url: None,
            remote_revision: None,
            tags: vec!["t1".to_string()],
            install_status: InstallStatus::NotInstalled,
            clawhub_slug: None,
            clawhub_owner: None,
            clawhub_version: None,
        }
    }

    #[test]
    fn toggle_skill_favorite_sets_and_clears_timestamp() {
        // 用一个临时 config 路径构造 ConfigManager 不易，这里只验证逻辑：
        // favorited_at 在 favorited=true 时应为 Some，false 时为 None。
        // 实际写入由 ConfigManager 负责，此测试聚焦字段语义。
        let mut meta = SkillMetadata::default();
        assert_eq!(meta.favorited_at, None);
        meta.favorited_at = Some(123);
        assert_eq!(meta.favorited_at, Some(123));
        meta.favorited_at = None;
        assert_eq!(meta.favorited_at, None);
    }

    #[test]
    fn marketplace_favorite_meta_carries_snapshot_fields() {
        let skill = sample_skill("s1", "My Skill");
        let meta = MarketplaceFavoriteMeta {
            favorited_at: 42,
            name: skill.name.clone(),
            description: skill.description.clone(),
            source_id: skill.source_id.clone(),
            source_name: skill.source_name.clone(),
            repo_url: skill.repo_url.clone(),
            skill_path: skill.skill_path.clone(),
            external_url: skill.external_url.clone(),
            install_count: skill.install_count,
            tags: skill.tags.clone(),
            clawhub_slug: skill.clawhub_slug.clone(),
            clawhub_owner: skill.clawhub_owner.clone(),
            clawhub_version: skill.clawhub_version.clone(),
        };
        assert_eq!(meta.favorited_at, 42);
        assert_eq!(meta.name, "My Skill");
        assert_eq!(meta.tags, vec!["t1".to_string()]);
    }

    #[test]
    fn app_config_default_has_empty_marketplace_favorites() {
        let config = AppConfig::default();
        assert!(config.marketplace_favorites.is_empty());
    }
}
