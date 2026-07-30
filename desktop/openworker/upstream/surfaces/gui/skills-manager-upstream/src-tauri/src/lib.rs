mod commands;
mod models;
mod services;
#[cfg(test)]
mod test_support;

use commands::{
    batch_set_skill_tools, check_marketplace_updates_if_stale,
    check_sync_status, check_update, clear_llm_provider, clear_risk_cache_command,
    clear_translation_cache, clear_usage_stats, create_custom_tool, create_directory,
    create_file, create_skill, delete_custom_tool, delete_path, delete_skill,
    detect_available_editors, detect_tools, disable_skill, enable_skill, exchange_github_auth,
    exchange_google_auth, export_skills, fetch_clawhub_skill_files, fetch_marketplace_skill_descriptions,
    fetch_marketplace_skills, fetch_skill_file_content, fetch_skill_files, fix_sync_issues,
    get_auth_profile, get_available_editors, get_cached_marketplace_translations,
    get_cached_skill_translations, get_cached_text_translation, get_config, get_llm_provider,
    get_marketplace_sources, get_risk_report, get_risk_reports_batch, get_risk_scanner_version,
    get_skill_usage_stats, get_tool_status, get_usage_hook_status, import_skills,
    import_skills_to_hub, install_marketplace_skill, install_marketplace_skill_by_ref,
    install_skill_package_from_path, install_usage_hook, is_initialized, list_marketplace_favorites,
    list_skill_packages, list_skills, logout_auth, mark_initialized, open_in_editor,
    preview_import_skills, read_directory_tree, read_file, refresh_editors, refresh_skills,
    refresh_tools, remove_skill_package, rename_path, rescan_skill, save_config, save_llm_provider,
    scan_all_risks, scan_existing_skills, set_tool_enabled, start_github_auth, start_google_auth,
    submit_feedback, sync_marketplace_installed_skills, test_llm_provider,
    toggle_marketplace_favorite, toggle_marketplace_source, toggle_skill_favorite,
    translate_marketplace_skill, translate_skill, translate_skill_files, translate_skills_batch,
    translate_text_content, uninstall_usage_hook, update_custom_tool, update_tool_paths,
    write_file,
};
use services::{AppCache, MarketplaceCache};
use tauri::{Emitter, Manager};
use tauri_plugin_deep_link::DeepLinkExt;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, mut argv, _cwd| {
            if matches!(argv.first(), Some(arg) if arg.contains("://")) {
                argv.insert(0, String::new());
            }
            let _ = app.emit("auth:deep-link-argv", argv.clone());
            app.deep_link().handle_cli_arguments(argv.into_iter());
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .setup(|app| {
            #[cfg(desktop)]
            {
                match app.deep_link().register_all() {
                    Ok(_) => {}
                    Err(_err) => {}
                }
                for scheme in ["skills-manager", "skillsmanager"] {
                    match app.deep_link().is_registered(scheme) {
                        Ok(_is_registered) => {}
                        Err(_err) => {}
                    }
                }
            }
            // Sync usage hook state with config on startup
            commands::sync_usage_hook_with_config();
            // Start watching for usage events and emit updates to frontend
            commands::usage::start_usage_watcher(app.handle().clone());
            // Start background risk scan for installed skills
            commands::start_background_scan(app.handle().clone());
            Ok(())
        })
        .manage(AppCache::default())
        .manage(MarketplaceCache::default())
        .invoke_handler(tauri::generate_handler![
            get_config,
            save_config,
            is_initialized,
            mark_initialized,
            list_skills,
            refresh_skills,
            list_skill_packages,
            enable_skill,
            disable_skill,
            batch_set_skill_tools,
            delete_skill,
            create_skill,
            install_skill_package_from_path,
            remove_skill_package,
            detect_tools,
            refresh_tools,
            get_tool_status,
            set_tool_enabled,
            update_tool_paths,
            create_custom_tool,
            update_custom_tool,
            delete_custom_tool,
            check_sync_status,
            fix_sync_issues,
            scan_existing_skills,
            import_skills_to_hub,
            export_skills,
            preview_import_skills,
            import_skills,
            detect_available_editors,
            refresh_editors,
            get_available_editors,
            open_in_editor,
            read_directory_tree,
            read_file,
            write_file,
            create_file,
            create_directory,
            delete_path,
            rename_path,
            fetch_marketplace_skills,
            fetch_marketplace_skill_descriptions,
            fetch_skill_files,
            fetch_clawhub_skill_files,
            fetch_skill_file_content,
            install_marketplace_skill,
            install_marketplace_skill_by_ref,
            sync_marketplace_installed_skills,
            check_marketplace_updates_if_stale,
            get_marketplace_sources,
            toggle_marketplace_source,
            toggle_skill_favorite,
            toggle_marketplace_favorite,
            list_marketplace_favorites,
            check_update,
            submit_feedback,
            get_llm_provider,
            save_llm_provider,
            clear_llm_provider,
            test_llm_provider,
            translate_skill,
            translate_skill_files,
            translate_marketplace_skill,
            translate_skills_batch,
            translate_text_content,
            clear_translation_cache,
            get_cached_skill_translations,
            get_cached_marketplace_translations,
            get_cached_text_translation,
            start_github_auth,
            start_google_auth,
            exchange_github_auth,
            exchange_google_auth,
            get_auth_profile,
            logout_auth,
            get_skill_usage_stats,
            install_usage_hook,
            uninstall_usage_hook,
            get_usage_hook_status,
            clear_usage_stats,
            get_risk_report,
            get_risk_reports_batch,
            get_risk_scanner_version,
            scan_all_risks,
            rescan_skill,
            clear_risk_cache_command,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
