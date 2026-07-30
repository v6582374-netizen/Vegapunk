use std::path::PathBuf;

use crate::models::{CustomToolConfig, Tool, SUPPORTED_TOOLS};
use crate::services::{AppCache, ConfigManager, DetectorService, LinkerService};
use tauri::State;

#[tauri::command]
pub fn detect_tools(cache: State<AppCache>) -> Result<Vec<Tool>, String> {
    // Try to get from cache first
    if let Some(tools) = cache.get_tools() {
        return Ok(tools);
    }

    // Cache miss - detect and cache
    let tools = DetectorService::detect_all();
    cache.set_tools(tools.clone());
    Ok(tools)
}

#[tauri::command]
pub fn refresh_tools(cache: State<AppCache>) -> Result<Vec<Tool>, String> {
    // Force re-detect and update cache
    let tools = DetectorService::detect_all();
    cache.set_tools(tools.clone());
    Ok(tools)
}

#[tauri::command]
pub fn get_tool_status(tool_id: String) -> Result<Tool, String> {
    DetectorService::get_tool_by_id(&tool_id).ok_or_else(|| format!("Tool not found: {}", tool_id))
}

#[tauri::command]
pub fn set_tool_enabled(
    tool_id: String,
    enabled: bool,
    cache: State<AppCache>,
) -> Result<(), String> {
    set_tool_enabled_with_cache(tool_id, enabled, &cache)
}

fn set_tool_enabled_with_cache(
    tool_id: String,
    enabled: bool,
    cache: &AppCache,
) -> Result<(), String> {
    if !enabled {
        let manager = ConfigManager::new();
        let config = manager.load()?;
        let tool_config = config
            .get_tool_config(&tool_id)
            .ok_or_else(|| format!("Tool not found: {}", tool_id))?;
        if should_remove_links_when_disabling_tool(&config) {
            remove_skill_links_for_tool(&config.skills_dir, &tool_config.skills_path, &tool_id)?;
        }
    }

    set_tool_enabled_in_config(&tool_id, enabled)?;
    cache.invalidate_tools();
    cache.invalidate_skills();
    Ok(())
}

fn should_remove_links_when_disabling_tool(config: &crate::models::AppConfig) -> bool {
    config
        .preferences
        .as_ref()
        .map(|preferences| preferences.remove_links_when_disabling_tool)
        .unwrap_or(false)
}

fn remove_skill_links_for_tool(
    hub_skills_dir: &std::path::Path,
    tool_skills_dir: &std::path::Path,
    tool_id: &str,
) -> Result<(), String> {
    if !hub_skills_dir.exists() {
        return Ok(());
    }

    for entry in std::fs::read_dir(hub_skills_dir)
        .map_err(|e| format!("Failed to read hub skills directory: {}", e))?
    {
        let entry = entry.map_err(|e| format!("Failed to read skill entry: {}", e))?;
        let skill_path = entry.path();
        if !skill_path.is_dir() {
            continue;
        }

        let Some(skill_id) = skill_path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if skill_id.starts_with('.') {
            continue;
        }

        LinkerService::disable_skill_for_tool(tool_skills_dir, skill_id, tool_id)?;
    }

    Ok(())
}

fn set_tool_enabled_in_config(tool_id: &str, enabled: bool) -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    if let Some(tool_config) = config.tools.get_mut(tool_id) {
        tool_config.enabled = enabled;
        return manager.save(&config);
    }

    if let Some(custom_tool) = config.custom_tools.get_mut(tool_id) {
        custom_tool.enabled = enabled;
        return manager.save(&config);
    }

    Err(format!("Tool not found: {}", tool_id))
}

#[tauri::command]
pub fn update_tool_paths(
    tool_id: String,
    config_path: Option<String>,
    skills_path: Option<String>,
) -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    if let Some(tool_config) = config.tools.get_mut(&tool_id) {
        if let Some(path) = config_path {
            tool_config.config_path = PathBuf::from(path);
            // Re-detect if directory exists
            tool_config.detected = tool_config.config_path.exists();
        }

        if let Some(path) = skills_path {
            tool_config.skills_path = PathBuf::from(path);
        }

        return manager.save(&config);
    }

    if let Some(custom_tool) = config.custom_tools.get_mut(&tool_id) {
        if let Some(path) = config_path {
            custom_tool.config_path = PathBuf::from(path);
        }

        if let Some(path) = skills_path {
            custom_tool.skills_path = PathBuf::from(path);
        }

        return manager.save(&config);
    }

    Err(format!("Tool not found: {}", tool_id))
}

#[tauri::command]
pub fn create_custom_tool(
    tool_id: String,
    name: String,
    config_path: String,
    skills_path: String,
    icon_path: Option<String>,
    cache: State<AppCache>,
) -> Result<(), String> {
    if tool_id.trim().is_empty() {
        return Err("Tool ID is required".to_string());
    }
    if name.trim().is_empty() {
        return Err("Tool name is required".to_string());
    }
    if config_path.trim().is_empty() || skills_path.trim().is_empty() {
        return Err("Tool paths are required".to_string());
    }

    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    let is_builtin = SUPPORTED_TOOLS.iter().any(|tool| tool.id == tool_id);
    if is_builtin || config.tools.contains_key(&tool_id) {
        return Err(format!("Tool ID already exists: {}", tool_id));
    }
    if config.custom_tools.contains_key(&tool_id) {
        return Err(format!("Tool ID already exists: {}", tool_id));
    }

    let config_path_buf = PathBuf::from(config_path);
    let enabled = config_path_buf.exists();

    let custom_tool = CustomToolConfig {
        name,
        config_path: config_path_buf,
        skills_path: PathBuf::from(skills_path),
        enabled,
        icon_path: icon_path.map(PathBuf::from),
    };

    config.custom_tools.insert(tool_id, custom_tool);
    manager.save(&config)?;
    cache.invalidate_tools();
    Ok(())
}

#[tauri::command]
pub fn update_custom_tool(
    tool_id: String,
    name: String,
    config_path: String,
    skills_path: String,
    icon_path: Option<String>,
    enabled: bool,
    cache: State<AppCache>,
) -> Result<(), String> {
    if tool_id.trim().is_empty() {
        return Err("Tool ID is required".to_string());
    }
    if name.trim().is_empty() {
        return Err("Tool name is required".to_string());
    }
    if config_path.trim().is_empty() || skills_path.trim().is_empty() {
        return Err("Tool paths are required".to_string());
    }

    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    let custom_tool = config
        .custom_tools
        .get_mut(&tool_id)
        .ok_or_else(|| format!("Custom tool not found: {}", tool_id))?;

    custom_tool.name = name;
    custom_tool.config_path = PathBuf::from(config_path);
    custom_tool.skills_path = PathBuf::from(skills_path);
    custom_tool.icon_path = icon_path.map(PathBuf::from);
    custom_tool.enabled = enabled;

    manager.save(&config)?;
    cache.invalidate_tools();
    Ok(())
}

#[tauri::command]
pub fn delete_custom_tool(tool_id: String, cache: State<AppCache>) -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;

    if config.custom_tools.remove(&tool_id).is_some() {
        manager.save(&config)?;
        cache.invalidate_tools();
        Ok(())
    } else {
        Err(format!("Custom tool not found: {}", tool_id))
    }
}

#[cfg(test)]
mod tests {
    use super::{set_tool_enabled_in_config, update_tool_paths};
    use crate::services::{AppCache, LinkerService};
    use crate::test_support::with_temp_home;
    use serde_json::json;
    use std::fs;
    use std::path::Path;

    fn write_config(home_dir: &Path, enabled: bool) -> std::path::PathBuf {
        write_config_with_remove_links_preference(home_dir, enabled, false)
    }

    fn write_config_with_remove_links_preference(
        home_dir: &Path,
        enabled: bool,
        remove_links_when_disabling_tool: bool,
    ) -> std::path::PathBuf {
        let config_dir = home_dir.join(".skills-manager");
        let config_path = config_dir.join("config.json");
        fs::create_dir_all(&config_dir).unwrap();

        let custom_config_dir = home_dir.join(".my-tool");
        let custom_skills_dir = custom_config_dir.join("skills");
        fs::create_dir_all(&custom_config_dir).unwrap();
        fs::create_dir_all(&custom_skills_dir).unwrap();

        let config_json = json!({
            "version": "1.0.2",
            "skills_dir": home_dir.join(".skills-manager").join("skills").to_string_lossy(),
            "tools": {},
            "custom_tools": {
                "my-tool": {
                    "name": "My Tool",
                    "config_path": custom_config_dir.to_string_lossy(),
                    "skills_path": custom_skills_dir.to_string_lossy(),
                    "enabled": enabled,
                    "icon_path": null
                }
            },
            "preferences": {
                "remove_links_when_disabling_tool": remove_links_when_disabling_tool
            },
            "initialized": true
        });

        fs::write(
            &config_path,
            serde_json::to_string_pretty(&config_json).unwrap(),
        )
        .unwrap();
        config_path
    }

    fn create_demo_skill_link(home_dir: &Path) -> std::path::PathBuf {
        let skill_dir = home_dir
            .join(".skills-manager")
            .join("skills")
            .join("demo-skill");
        fs::create_dir_all(&skill_dir).unwrap();
        fs::write(skill_dir.join("SKILL.md"), "# Demo\n").unwrap();

        let tool_skills_dir = home_dir.join(".my-tool").join("skills");
        LinkerService::enable_skill_for_tool(&skill_dir, &tool_skills_dir, "demo-skill", "my-tool")
            .expect("link skill");

        tool_skills_dir.join("demo-skill")
    }

    #[test]
    fn set_tool_enabled_updates_custom_tool_entry() {
        with_temp_home(|home_dir| {
            let config_path = write_config(home_dir, false);

            let result = set_tool_enabled_in_config("my-tool", true);
            assert!(result.is_ok(), "expected set_tool_enabled to succeed");

            let updated = fs::read_to_string(&config_path).unwrap();
            let json: serde_json::Value = serde_json::from_str(&updated).unwrap();
            let enabled = json["custom_tools"]["my-tool"]["enabled"].as_bool();
            assert_eq!(enabled, Some(true));
        });
    }

    #[test]
    fn update_tool_paths_updates_custom_tool_paths() {
        with_temp_home(|home_dir| {
            let config_path = write_config(home_dir, true);

            let new_config = home_dir.join(".my-tool-new");
            let new_skills = new_config.join("skills");
            fs::create_dir_all(&new_config).unwrap();
            fs::create_dir_all(&new_skills).unwrap();

            let result = update_tool_paths(
                "my-tool".to_string(),
                Some(new_config.to_string_lossy().to_string()),
                Some(new_skills.to_string_lossy().to_string()),
            );
            assert!(result.is_ok(), "expected update_tool_paths to succeed");

            let updated = fs::read_to_string(&config_path).unwrap();
            let json: serde_json::Value = serde_json::from_str(&updated).unwrap();
            let config_path_value = json["custom_tools"]["my-tool"]["config_path"].as_str();
            let skills_path_value = json["custom_tools"]["my-tool"]["skills_path"].as_str();
            assert_eq!(
                config_path_value,
                Some(new_config.to_string_lossy().as_ref())
            );
            assert_eq!(
                skills_path_value,
                Some(new_skills.to_string_lossy().as_ref())
            );
        });
    }

    #[test]
    fn set_tool_enabled_invalidates_tools_and_skills_cache() {
        with_temp_home(|home_dir| {
            write_config(home_dir, false);

            let cache = AppCache::default();
            cache.set_tools(Vec::new());
            cache.set_skills(Vec::new());

            let result = super::set_tool_enabled_with_cache("my-tool".to_string(), true, &cache);
            assert!(result.is_ok(), "expected set_tool_enabled to succeed");
            assert!(
                cache.get_tools().is_none(),
                "tools cache should be invalidated"
            );
            assert!(
                cache.get_skills().is_none(),
                "skills cache should be invalidated"
            );
        });
    }

    #[test]
    fn set_tool_enabled_disabling_tool_keeps_skill_links_by_default() {
        with_temp_home(|home_dir| {
            write_config_with_remove_links_preference(home_dir, true, false);
            let link_path = create_demo_skill_link(home_dir);
            assert!(
                link_path.exists() || link_path.symlink_metadata().is_ok(),
                "skill link should exist before disabling tool"
            );

            let cache = AppCache::default();
            let result = super::set_tool_enabled_with_cache("my-tool".to_string(), false, &cache);
            assert!(result.is_ok(), "expected set_tool_enabled to succeed");
            assert!(
                link_path.exists() || link_path.symlink_metadata().is_ok(),
                "skill link should be preserved when preference is disabled"
            );
        });
    }

    #[test]
    fn set_tool_enabled_disabling_tool_removes_skill_links_when_preference_enabled() {
        with_temp_home(|home_dir| {
            write_config_with_remove_links_preference(home_dir, true, true);
            let link_path = create_demo_skill_link(home_dir);
            assert!(
                link_path.exists() || link_path.symlink_metadata().is_ok(),
                "skill link should exist before disabling tool"
            );

            let cache = AppCache::default();
            let result = super::set_tool_enabled_with_cache("my-tool".to_string(), false, &cache);
            assert!(result.is_ok(), "expected set_tool_enabled to succeed");
            assert!(
                !link_path.exists() && link_path.symlink_metadata().is_err(),
                "skill link should be removed when preference is enabled"
            );
        });
    }
}
