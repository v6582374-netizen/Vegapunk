use rayon::prelude::*;
use std::env;
use std::process::Command; // Enable parallel processing

use crate::models::{
    CustomToolConfig, Tool, ToolConfig, ToolDefinition, ToolSource, SUPPORTED_TOOLS,
};
use crate::services::linker::normalize_path;
use crate::services::ConfigManager;

pub struct DetectorService;

impl DetectorService {
    pub fn detect_all() -> Vec<Tool> {
        let manager = ConfigManager::new();
        let saved_config = manager.load().ok();

        let mut tools: Vec<Tool> = Vec::new();

        // Use parallel iterator to detect all tools simultaneously
        // This prevents one slow detection (e.g. checking a network path) from blocking the UI
        let builtin_tools: Vec<Tool> = SUPPORTED_TOOLS
            .par_iter()
            .map(|def| Self::detect_tool(def, &saved_config))
            .collect();

        tools.extend(builtin_tools);

        if let Some(config) = saved_config {
            let mut custom_tools: Vec<(String, CustomToolConfig)> =
                config.custom_tools.into_iter().collect();

            custom_tools.sort_by(|(id_a, a), (id_b, b)| {
                let name_a = a.name.to_lowercase();
                let name_b = b.name.to_lowercase();
                name_a.cmp(&name_b).then_with(|| id_a.cmp(id_b))
            });

            for (id, custom) in custom_tools {
                tools.push(Self::detect_custom_tool(&id, &custom));
            }
        }

        tools
    }

    pub fn detect_tool(
        definition: &ToolDefinition,
        saved_config: &Option<crate::models::AppConfig>,
    ) -> Tool {
        let home_dir = dirs::home_dir().unwrap_or_default();

        // Prioritize saved custom paths, fallback to defaults
        let (config_path, skills_path) = if let Some(saved) = saved_config
            .as_ref()
            .and_then(|c| c.tools.get(definition.id))
        {
            // Normalize saved paths in case they contain mixed separators
            (
                normalize_path(&saved.config_path),
                normalize_path(&saved.skills_path),
            )
        } else {
            // Normalize after join to fix mixed separators (e.g. ".config/opencode" on Windows)
            let mut config_dir = normalize_path(&home_dir.join(definition.config_dir));

            // Prioritize default config_dir, but check alternatives if it doesn't exist
            if !config_dir.exists() {
                for alt in definition.alt_config_dirs {
                    let alt_dir = normalize_path(&home_dir.join(alt));
                    if alt_dir.exists() {
                        config_dir = alt_dir;
                        break;
                    }
                }
            }

            (config_dir.clone(), config_dir.join("skills"))
        };

        let dir_exists = config_path.exists();
        let cli_available = Self::check_cli_available(definition.cli_command);

        // Get saved enabled state from config, default to false
        let enabled = saved_config
            .as_ref()
            .and_then(|c| c.tools.get(definition.id))
            .map(|tc| tc.enabled)
            .unwrap_or(false);

        let tool_config = ToolConfig {
            enabled,
            detected: dir_exists,
            skills_path,
            config_path,
        };

        Tool {
            id: definition.id.to_string(),
            name: definition.name.to_string(),
            detected: dir_exists,
            cli_available,
            config: tool_config,
            source: ToolSource::Builtin,
            icon_path: None,
        }
    }

    pub fn check_cli_available(cli_command: &str) -> bool {
        // Optimized: Check PATH environment variable directly instead of spawning a process
        if let Ok(path_var) = env::var("PATH") {
            for path_str in env::split_paths(&path_var) {
                let full_path = path_str.join(cli_command);

                #[cfg(target_os = "windows")]
                {
                    // On Windows, checking extensionless file isn't enough, we need to check extensions
                    // Only check extensions if the command doesn't already have one
                    if full_path.extension().is_some() && full_path.is_file() {
                        return true;
                    }

                    let extensions = [".exe", ".cmd", ".bat"];
                    for ext in extensions {
                        let path_with_ext = path_str.join(format!("{}{}", cli_command, ext));
                        if path_with_ext.is_file() {
                            return true;
                        }
                    }
                }

                #[cfg(not(target_os = "windows"))]
                {
                    use std::os::unix::fs::PermissionsExt;
                    if full_path.is_file() {
                        // On Unix, check if executable bit is set
                        if let Ok(metadata) = full_path.metadata() {
                            if metadata.permissions().mode() & 0o111 != 0 {
                                return true;
                            }
                        }
                    }
                }
            }
        }

        // Fallback to process spawning if PATH check fails (unlikely but safe)
        // This is kept for edge cases where the tool might be available via aliases or other shell mechanisms
        Self::check_cli_available_fallback(cli_command)
    }

    fn check_cli_available_fallback(cli_command: &str) -> bool {
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            let result = Command::new("where")
                .arg(cli_command)
                .creation_flags(0x08000000) // CREATE_NO_WINDOW
                .output();
            match result {
                Ok(output) => output.status.success(),
                Err(_) => false,
            }
        }

        #[cfg(not(target_os = "windows"))]
        {
            let result = Command::new("which").arg(cli_command).output();
            match result {
                Ok(output) => output.status.success(),
                Err(_) => false,
            }
        }
    }

    pub fn get_tool_by_id(tool_id: &str) -> Option<Tool> {
        let manager = ConfigManager::new();
        let saved_config = manager.load().ok();

        if let Some(tool) = SUPPORTED_TOOLS
            .iter()
            .find(|def| def.id == tool_id)
            .map(|def| Self::detect_tool(def, &saved_config))
        {
            return Some(tool);
        }

        saved_config
            .and_then(|config| config.custom_tools.get(tool_id).cloned())
            .map(|custom| Self::detect_custom_tool(tool_id, &custom))
    }

    fn detect_custom_tool(id: &str, custom: &CustomToolConfig) -> Tool {
        let detected = custom.config_path.exists();

        let tool_config = ToolConfig {
            enabled: custom.enabled,
            detected,
            skills_path: custom.skills_path.clone(),
            config_path: custom.config_path.clone(),
        };

        Tool {
            id: id.to_string(),
            name: custom.name.clone(),
            detected,
            cli_available: false,
            config: tool_config,
            source: ToolSource::Custom,
            icon_path: custom.icon_path.clone(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::DetectorService;
    use crate::test_support::with_temp_home;
    use serde_json::json;
    use std::fs;
    use std::path::Path;

    fn write_config(home_dir: &Path) {
        let config_dir = home_dir.join(".skills-manager");
        let config_path = config_dir.join("config.json");
        fs::create_dir_all(&config_dir).unwrap();

        let custom_config_dir = home_dir.join(".my-tool");
        fs::create_dir_all(&custom_config_dir).unwrap();

        let config_json = json!({
            "version": "1.0.2",
            "skills_dir": home_dir.join(".skills-manager").join("skills").to_string_lossy(),
            "tools": {},
            "custom_tools": {
                "my-tool": {
                    "name": "My Tool",
                    "config_path": custom_config_dir.to_string_lossy(),
                    "skills_path": custom_config_dir.join("skills").to_string_lossy(),
                    "enabled": true,
                    "icon_path": null
                }
            },
            "initialized": true
        });

        fs::write(
            &config_path,
            serde_json::to_string_pretty(&config_json).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn detect_all_includes_custom_tools_from_config() {
        with_temp_home(|home_dir| {
            write_config(home_dir);

            let tools = DetectorService::detect_all();

            let found = tools.iter().any(|tool| tool.id == "my-tool");
            assert!(found, "expected custom tool to be detected");
        });
    }
}
