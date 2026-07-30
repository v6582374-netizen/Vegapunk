use crate::models::AppConfig;
use crate::services::ConfigManager;

#[tauri::command]
pub fn get_config() -> Result<AppConfig, String> {
    let manager = ConfigManager::new();
    manager.load()
}

#[tauri::command]
pub fn save_config(config: AppConfig) -> Result<(), String> {
    let manager = ConfigManager::new();
    manager.save(&config)
}

#[tauri::command]
pub fn is_initialized() -> bool {
    let manager = ConfigManager::new();
    manager.is_initialized()
}

#[tauri::command]
pub fn mark_initialized() -> Result<(), String> {
    let manager = ConfigManager::new();
    let mut config = manager.load()?;
    config.initialized = true;
    manager.save(&config)
}
