use std::path::Path;

use tauri::State;

use crate::models::InstalledSkillPackage;
use crate::services::{AppCache, ConfigManager, SkillPackageService};

#[tauri::command]
pub fn list_skill_packages() -> Result<Vec<InstalledSkillPackage>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    SkillPackageService::list_discovered_packages(&config.skills_dir)
}

#[tauri::command]
pub fn install_skill_package_from_path(
    source_path: String,
    app_cache: State<'_, AppCache>,
) -> Result<InstalledSkillPackage, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let state = SkillPackageService::install_from_local_source(
        Path::new(&source_path),
        &config.skills_dir,
    )?;
    app_cache.invalidate_skills();
    Ok(state)
}

#[tauri::command]
pub fn remove_skill_package(
    package_id: String,
    app_cache: State<'_, AppCache>,
) -> Result<(), String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    SkillPackageService::remove_package(&package_id, &config.skills_dir)?;
    app_cache.invalidate_skills();
    Ok(())
}
