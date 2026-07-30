use crate::models::DetectedEditor;
use crate::services::{detect_editors as do_detect, open_in_external_editor, AppCache};
use tauri::State;

#[tauri::command]
pub fn detect_available_editors(cache: State<AppCache>) -> Vec<DetectedEditor> {
    // Try to get from cache first
    if let Some(editors) = cache.get_editors() {
        return editors;
    }

    // Cache miss - detect and cache
    let editors = do_detect();
    cache.set_editors(editors.clone());
    editors
}

#[tauri::command]
pub fn refresh_editors(cache: State<AppCache>) -> Vec<DetectedEditor> {
    // Force re-detect and update cache
    let editors = do_detect();
    cache.set_editors(editors.clone());
    editors
}

#[tauri::command]
pub fn get_available_editors(cache: State<AppCache>) -> Vec<DetectedEditor> {
    // Try to get from cache first
    if let Some(editors) = cache.get_editors() {
        return editors;
    }

    // Cache miss - detect and cache
    let editors = do_detect();
    cache.set_editors(editors.clone());
    editors
}

#[tauri::command]
pub fn open_in_editor(editor_id: String, path: String) -> Result<(), String> {
    open_in_external_editor(&editor_id, &path)
}
