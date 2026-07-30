use crate::services::linker::LinkResult;
use crate::services::{ConfigManager, LinkReport, LinkStatus, LinkerService, ScannerService};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncReport {
    pub issues_count: usize,
}

fn collect_active_tool_configs(
    config: &crate::models::AppConfig,
) -> Vec<(String, crate::models::ToolConfig)> {
    config
        .collect_tool_configs()
        .into_iter()
        .filter(|(_, tool_config)| tool_config.enabled && tool_config.detected)
        .collect()
}

fn resolve_sync_status(
    skill: &crate::models::Skill,
    tool_id: &str,
    tool_config: &crate::models::ToolConfig,
) -> LinkStatus {
    LinkerService::check_link_for_scoped_skill(
        &skill.path,
        &tool_config.skills_path,
        &skill.id,
        tool_id,
        &skill.scope,
    )
}

fn should_report_sync_issue(should_be_enabled: bool, current_status: LinkStatus) -> bool {
    match (should_be_enabled, current_status) {
        (true, LinkStatus::Valid) => false,
        (false, LinkStatus::Missing) => false,
        (false, LinkStatus::WrongTarget) => false,
        // NotALink means a real directory/file exists that we did not create.
        // Never treat it as something to "fix" — that would risk deleting user content.
        (false, LinkStatus::NotALink) => false,
        _ => true,
    }
}

fn create_sync_result(
    skill_id: String,
    tool_id: String,
    status: LinkStatus,
    message: &str,
) -> LinkResult {
    LinkResult {
        skill_id,
        tool_id,
        status,
        message: Some(message.to_string()),
    }
}

fn create_sync_error(
    skill_id: String,
    tool_id: String,
    status: LinkStatus,
    message: String,
) -> LinkResult {
    LinkResult {
        skill_id,
        tool_id,
        status,
        message: Some(message),
    }
}

fn count_sync_issues(config: &crate::models::AppConfig) -> Result<usize, String> {
    let skills = ScannerService::scan_scoped_skills(config)?;

    Ok(collect_active_tool_configs(config)
        .into_iter()
        .map(|(tool_id, tool_config)| {
            skills
                .iter()
                .filter(|skill| {
                    should_report_sync_issue(
                        skill.is_enabled_for(&tool_id),
                        resolve_sync_status(skill, &tool_id, &tool_config),
                    )
                })
                .count()
        })
        .sum())
}

#[tauri::command]
pub fn check_sync_status() -> Result<SyncReport, String> {
    let config = ConfigManager::new().load()?;
    let issues_count = count_sync_issues(&config)?;

    Ok(SyncReport { issues_count })
}

#[tauri::command]
pub fn fix_sync_issues() -> Result<LinkReport, String> {
    let config = ConfigManager::new().load()?;
    let skills = ScannerService::scan_scoped_skills(&config)?;
    let mut combined_report = LinkReport::default();

    for (tool_id, tool_config) in collect_active_tool_configs(&config) {
        for skill in &skills {
            let should_be_enabled = skill.is_enabled_for(&tool_id);
            let current_status = resolve_sync_status(skill, &tool_id, &tool_config);

            if !should_report_sync_issue(should_be_enabled, current_status.clone()) {
                continue;
            }

            if should_be_enabled {
                match LinkerService::enable_skill_for_tool(
                    &skill.path,
                    &tool_config.skills_path,
                    &skill.id,
                    &tool_id,
                ) {
                    Ok(_) => combined_report.success.push(create_sync_result(
                        skill.instance_id.clone(),
                        tool_id.clone(),
                        LinkStatus::Valid,
                        "Enabled successfully",
                    )),
                    Err(e) => combined_report.failed.push(create_sync_error(
                        skill.instance_id.clone(),
                        tool_id.clone(),
                        LinkStatus::Broken,
                        e,
                    )),
                }
                continue;
            }

            // 对于应该禁用的 skill，无论当前状态如何，都尝试删除目标文件
            match LinkerService::disable_skill_for_tool(
                &tool_config.skills_path,
                &skill.id,
                &tool_id,
            ) {
                Ok(_) => combined_report.success.push(create_sync_result(
                    skill.instance_id.clone(),
                    tool_id.clone(),
                    LinkStatus::Missing,
                    "Disabled successfully",
                )),
                Err(e) => combined_report.failed.push(create_sync_error(
                    skill.instance_id.clone(),
                    tool_id.clone(),
                    current_status,
                    e,
                )),
            }
        }
    }

    Ok(combined_report)
}

#[cfg(test)]
mod tests {
    use super::{collect_active_tool_configs, count_sync_issues, should_report_sync_issue};
    use crate::models::{AppConfig, CustomToolConfig, ToolConfig};
    use crate::services::LinkStatus;
    use crate::test_support::with_temp_home;
    use std::collections::HashMap;
    use std::fs;
    use std::path::PathBuf;

    fn mk_tool(enabled: bool, detected: bool) -> ToolConfig {
        ToolConfig {
            enabled,
            detected,
            skills_path: PathBuf::from("/tmp/skills"),
            config_path: PathBuf::from("/tmp/config"),
        }
    }

    #[test]
    fn collect_active_tool_configs_only_returns_enabled_and_detected() {
        let mut config = AppConfig::default();
        config.tools = HashMap::from([
            ("active".to_string(), mk_tool(true, true)),
            ("disabled".to_string(), mk_tool(false, true)),
            ("undetected".to_string(), mk_tool(true, false)),
        ]);
        config.custom_tools = HashMap::from([(
            "custom-active".to_string(),
            CustomToolConfig {
                name: "Custom".to_string(),
                config_path: PathBuf::from("/tmp/custom"),
                skills_path: PathBuf::from("/tmp/custom/skills"),
                enabled: true,
                icon_path: None,
            },
        )]);

        let mut ids: Vec<String> = collect_active_tool_configs(&config)
            .into_iter()
            .map(|(id, _)| id)
            .collect();
        ids.sort();

        assert_eq!(ids, vec!["active".to_string()]);
    }

    #[test]
    fn should_report_sync_issue_ignores_wrong_target_for_disabled_skill() {
        assert!(!should_report_sync_issue(false, LinkStatus::WrongTarget));
        // NotALink is external content we must never touch
        assert!(!should_report_sync_issue(false, LinkStatus::NotALink));
    }

    #[cfg(unix)]
    #[test]
    fn ticket_02_broken_kiro_and_trae_gh_axi_projections_remain_sync_issues() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let gh_axi = skills_dir.join("gh-axi");
            fs::create_dir_all(&gh_axi).expect("create central gh-axi skill");
            fs::write(gh_axi.join("SKILL.md"), "# gh-axi\n").expect("write central skill");

            let mut config = AppConfig {
                skills_dir,
                ..AppConfig::default()
            };

            for tool_id in ["kiro", "trae"] {
                let config_path = home.join(format!(".{tool_id}"));
                let tool_skills_dir = config_path.join("skills");
                fs::create_dir_all(&tool_skills_dir).expect("create tool skills dir");
                std::os::unix::fs::symlink(
                    PathBuf::from("../../.agents/skills/gh-axi"),
                    tool_skills_dir.join("gh-axi"),
                )
                .expect("create observed broken projection");
                config.tools.insert(
                    tool_id.to_string(),
                    ToolConfig {
                        enabled: true,
                        detected: true,
                        skills_path: tool_skills_dir,
                        config_path,
                    },
                );
            }

            assert_eq!(count_sync_issues(&config).expect("count sync issues"), 2);
        });
    }
}
