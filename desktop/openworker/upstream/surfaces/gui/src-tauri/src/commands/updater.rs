use crate::models::update::UpdateInfo;
use crate::services::{updater, ConfigManager};

const SKILLS_MANAGER_VERSION: &str = "2.1.7";

#[tauri::command]
pub async fn check_update(_app_handle: tauri::AppHandle) -> Result<UpdateInfo, String> {
    let github_token = ConfigManager::new()
        .load()
        .ok()
        .and_then(|cfg| cfg.preferences.and_then(|prefs| prefs.github_token))
        .map(|token| token.trim().to_string())
        .filter(|token| !token.is_empty());

    updater::check_for_updates(SKILLS_MANAGER_VERSION, github_token.as_deref())
        .await
        .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::SKILLS_MANAGER_VERSION;

    #[test]
    fn update_check_uses_the_pinned_skills_manager_version() {
        assert_eq!(SKILLS_MANAGER_VERSION, "2.1.7");
    }
}
