use std::path::PathBuf;

use crate::services::skill_transfer::{self, ImportPreview, ImportResolution, ImportResult};
use crate::services::{AppCache, ConfigManager, ScannerService};
use tauri::State;

/// Export skills to a zip archive at `output_path`.
///
/// If `instance_ids` is `None`, exports every eligible global skill (local +
/// imported sources). If provided, exports only the listed instance ids (still
/// restricted to global + local/imported sources; others are silently skipped).
#[tauri::command]
pub fn export_skills(
    instance_ids: Option<Vec<String>>,
    output_path: String,
    cache: State<AppCache>,
) -> Result<usize, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let all_skills = if let Some(_skills) = cache.get_skills() {
        // Use cached list if available; otherwise scan fresh.
        _skills
    } else {
        let fresh = ScannerService::scan_scoped_skills(&config)?;
        cache.set_skills(fresh.clone());
        fresh
    };

    let selected: Vec<_> = match instance_ids {
        None => skill_transfer::collect_exportable_skills(&config)?,
        Some(ids) => {
            let id_set: std::collections::HashSet<&str> = ids.iter().map(|s| s.as_str()).collect();
            all_skills
                .into_iter()
                .filter(|skill| id_set.contains(&skill.instance_id.as_str()))
                .filter(|skill| {
                    use crate::models::{SkillScope, SkillSource};
                    matches!(skill.scope, SkillScope::Global)
                        && matches!(skill.source, SkillSource::Local | SkillSource::Imported)
                })
                .collect()
        }
    };

    let count = selected.len();
    skill_transfer::export_skills_to_zip(&config, &selected, &PathBuf::from(&output_path))?;
    Ok(count)
}

/// Preview an import archive: parse manifest and detect conflicts.
#[tauri::command]
pub fn preview_import_skills(zip_path: String) -> Result<ImportPreview, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    skill_transfer::preview_import(&PathBuf::from(&zip_path), &config)
}

/// Execute an import according to the user-supplied resolutions.
#[tauri::command]
pub fn import_skills(
    zip_path: String,
    resolutions: Vec<ImportResolution>,
    cache: State<AppCache>,
) -> Result<ImportResult, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let result =
        skill_transfer::import_skills_from_zip(&PathBuf::from(&zip_path), &resolutions, &config)?;
    // Imported skills changed the hub; invalidate cached skill list.
    if !result.imported.is_empty() || !result.overwritten.is_empty() {
        cache.invalidate_skills();
    }
    Ok(result)
}
