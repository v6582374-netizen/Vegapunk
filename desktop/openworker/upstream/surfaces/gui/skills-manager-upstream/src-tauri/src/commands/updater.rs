use crate::models::update::UpdateInfo;
use crate::services::{updater, ConfigManager};

#[tauri::command]
pub async fn check_update(app_handle: tauri::AppHandle) -> Result<UpdateInfo, String> {
    let package_info = app_handle.package_info();
    let current_version = &package_info.version;
    let v_str = format!(
        "{}.{}.{}",
        current_version.major, current_version.minor, current_version.patch
    );

    let github_token = ConfigManager::new()
        .load()
        .ok()
        .and_then(|cfg| cfg.preferences.and_then(|prefs| prefs.github_token))
        .map(|token| token.trim().to_string())
        .filter(|token| !token.is_empty());

    updater::check_for_updates(&v_str, github_token.as_deref())
        .await
        .map_err(|e| e.to_string())
}
