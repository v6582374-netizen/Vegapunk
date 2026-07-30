use crate::models::{DetectedEditor, EDITOR_DEFINITIONS};
use std::env;
use std::fs;
use std::path::Path;
use std::process::Command;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "macos")]
use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};

pub fn detect_editors() -> Vec<DetectedEditor> {
    // Use sequential iterator to ensure stable ordering
    // Parallel detection caused random order which led to icon display issues
    EDITOR_DEFINITIONS
        .iter()
        .filter_map(|def| {
            // Check command line tool
            let cmd_path = if !def.detect_cmd.is_empty() {
                get_command_path(def.detect_cmd)
            } else {
                None
            };

            let cmd_exists = cmd_path.is_some();

            // Check macOS app and get path
            #[cfg(target_os = "macos")]
            let app_path = if !def.app_name.is_empty() {
                find_app_path(def.app_name)
            } else {
                None
            };

            #[cfg(not(target_os = "macos"))]
            let app_path: Option<String> = None;

            // Determine final path for icon extraction
            let effective_path = if cfg!(target_os = "windows") {
                cmd_path.clone().or(app_path.clone())
            } else {
                app_path.clone()
            };

            let available = def.always_available || cmd_exists || app_path.is_some();

            if available {
                // Try to extract icon from app bundle or executable
                let icon_data = effective_path
                    .as_ref()
                    .and_then(|p| extract_app_icon(p))
                    .or_else(|| {
                        // For always_available system apps, try to get from system locations if not found above
                        if def.always_available && !def.id.is_empty() && def.id != "builtin" {
                            #[cfg(target_os = "macos")]
                            {
                                let system_app = match def.id {
                                    "terminal" => Some("/System/Applications/Utilities/Terminal.app"),
                                    "finder" => Some("/System/Library/CoreServices/Finder.app"),
                                    _ => None,
                                };
                                system_app.and_then(|p| extract_app_icon(p))
                            }
                            #[cfg(target_os = "windows")]
                            {
                                // On Windows, try to find standard paths if detection failed
                                let system_app = match def.id {
                                    "terminal" => Some("C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"),
                                    "finder" => Some("C:\\Windows\\explorer.exe"),
                                    _ => None,
                                };
                                system_app.and_then(|p| extract_app_icon(p))
                            }
                            #[cfg(not(any(target_os = "macos", target_os = "windows")))]
                            { None }
                        } else {
                            None
                        }
                    });

                Some(DetectedEditor {
                    id: def.id.to_string(),
                    name: def.name.to_string(),
                    command: def.open_cmd.to_string(),
                    available: true,
                    icon: def.icon.to_string(),
                    icon_data,
                })
            } else {
                None
            }
        })
        .collect()
}

/// On Windows, verify that a candidate file is a real executable:
/// - Reject 0-byte files: WindowsApps app execution aliases are 0-byte stubs
///   that fail with ERROR_BAD_EXE_FORMAT (os error 193) when stale or disabled.
/// - Reject `.exe` files without the MZ magic header (e.g. renamed scripts).
#[cfg(target_os = "windows")]
fn is_valid_windows_executable(path: &Path) -> bool {
    let Ok(metadata) = fs::metadata(path) else {
        return false;
    };
    if metadata.len() == 0 {
        return false;
    }
    if path
        .extension()
        .is_some_and(|ext| ext.eq_ignore_ascii_case("exe"))
    {
        use std::io::Read;
        let Ok(mut file) = fs::File::open(path) else {
            return false;
        };
        let mut magic = [0u8; 2];
        return file.read_exact(&mut magic).is_ok() && magic == *b"MZ";
    }
    true
}

/// Build a Windows `Command` for the given program, wrapping `.cmd`/`.bat`
/// scripts in `cmd /C` since they cannot be spawned directly.
#[cfg(target_os = "windows")]
fn build_windows_command(program: &str) -> Command {
    let lower = program.to_lowercase();
    if lower.ends_with(".cmd") || lower.ends_with(".bat") {
        let mut c = Command::new("cmd");
        c.arg("/C");
        c.arg(program);
        c
    } else {
        Command::new(program)
    }
}

fn get_command_path(cmd: &str) -> Option<String> {
    // Optimized: Check PATH environment variable first
    if let Ok(path_var) = env::var("PATH") {
        for path_str in env::split_paths(&path_var) {
            #[cfg(target_os = "windows")]
            {
                // Check with extensions on Windows
                let extensions = [".exe", ".cmd", ".bat"];

                // Only match without extension if the command already includes
                // one (e.g. "code.cmd"). Extension-less files on Windows (shell
                // scripts, shims) are not directly executable (os error 193).
                if cmd.contains('.') {
                    let direct = path_str.join(cmd);
                    if direct.is_file() && is_valid_windows_executable(&direct) {
                        return Some(direct.to_string_lossy().to_string());
                    }
                }

                for ext in extensions {
                    let path_with_ext = path_str.join(format!("{}{}", cmd, ext));
                    if path_with_ext.is_file() && is_valid_windows_executable(&path_with_ext) {
                        return Some(path_with_ext.to_string_lossy().to_string());
                    }
                }
            }

            #[cfg(not(target_os = "windows"))]
            {
                let full_path = path_str.join(cmd);
                if full_path.is_file() {
                    use std::os::unix::fs::PermissionsExt;
                    if let Ok(metadata) = full_path.metadata() {
                        if metadata.permissions().mode() & 0o111 != 0 {
                            return Some(full_path.to_string_lossy().to_string());
                        }
                    }
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Fallback: Check common installation locations (for VS Code, etc.)
        if cmd == "code" {
            // Check User Install: %LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd
            if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
                let path = Path::new(&local_app_data)
                    .join("Programs")
                    .join("Microsoft VS Code")
                    .join("bin")
                    .join("code.cmd");
                if path.exists() {
                    return Some(path.to_string_lossy().to_string());
                }
            }

            // Check System Install: %ProgramFiles%\Microsoft VS Code\bin\code.cmd
            if let Ok(program_files) = std::env::var("ProgramFiles") {
                let path = Path::new(&program_files)
                    .join("Microsoft VS Code")
                    .join("bin")
                    .join("code.cmd");
                if path.exists() {
                    return Some(path.to_string_lossy().to_string());
                }
            }
        }

        // Use 'where' as last resort
        let where_result = Command::new("where")
            .arg(cmd)
            .creation_flags(0x08000000)
            .output()
            .ok()
            .and_then(|output| {
                if output.status.success() {
                    let output_str = String::from_utf8_lossy(&output.stdout);
                    output_str
                        .lines()
                        .map(|s| s.trim())
                        .filter(|s| {
                            let lower = s.to_lowercase();
                            lower.ends_with(".exe")
                                || lower.ends_with(".cmd")
                                || lower.ends_with(".bat")
                        })
                        .find(|s| is_valid_windows_executable(Path::new(s)))
                        .map(|s| s.to_string())
                } else {
                    None
                }
            });

        if where_result.is_some() {
            return where_result;
        }

        None
    }
    #[cfg(not(target_os = "windows"))]
    {
        Command::new("which")
            .arg(cmd)
            .output()
            .ok()
            .and_then(|output| {
                if output.status.success() {
                    String::from_utf8_lossy(&output.stdout)
                        .lines()
                        .next()
                        .map(|s| s.trim().to_string())
                } else {
                    None
                }
            })
    }
}

#[cfg(target_os = "macos")]
fn find_app_path(app_name: &str) -> Option<String> {
    // Check /Applications folder - exact match first
    let app_path = format!("/Applications/{}.app", app_name);
    if Path::new(&app_path).exists() {
        return Some(app_path);
    }

    // Check ~/Applications folder - exact match
    if let Some(home) = dirs::home_dir() {
        let user_app_path = home.join("Applications").join(format!("{}.app", app_name));
        if user_app_path.exists() {
            return Some(user_app_path.to_string_lossy().to_string());
        }
    }

    // Search for apps with prefix match (handles variants like "Trae CN", "PyCharm CE", "PyCharm Professional")
    let search_dirs = vec![
        "/Applications".to_string(),
        dirs::home_dir()
            .map(|h| h.join("Applications").to_string_lossy().to_string())
            .unwrap_or_default(),
    ];

    // Collect all matching apps, then pick the best one (shortest name = most likely the base version)
    let mut candidates: Vec<String> = Vec::new();

    for dir in search_dirs {
        if dir.is_empty() {
            continue;
        }
        if let Ok(entries) = fs::read_dir(&dir) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.ends_with(".app") {
                    let name_without_ext = name.trim_end_matches(".app");
                    // Exact match or prefix match (for variants)
                    if name_without_ext == app_name
                        || name_without_ext.starts_with(&format!("{} ", app_name))
                        || name_without_ext.starts_with(&format!("{}-", app_name))
                    {
                        candidates.push(entry.path().to_string_lossy().to_string());
                    }
                }
            }
        }
    }

    // Sort by path length (shorter = more likely base app), then alphabetically for stability
    candidates.sort_by(|a, b| {
        let len_cmp = a.len().cmp(&b.len());
        if len_cmp == std::cmp::Ordering::Equal {
            a.cmp(b)
        } else {
            len_cmp
        }
    });

    candidates.into_iter().next()
}

fn extract_app_icon(app_path: &str) -> Option<String> {
    #[cfg(target_os = "windows")]
    {
        // Special handling for VS Code: ensure we try to get the icon from the executable, not the batch script
        let mut path_str = app_path.to_string();
        if path_str.to_lowercase().ends_with("\\bin\\code.cmd") {
            // Try to find Code.exe in the parent directory of bin
            let candidate = path_str.replace("\\bin\\code.cmd", "\\Code.exe");
            if Path::new(&candidate).exists() {
                path_str = candidate;
            }
        }

        let script = format!(
            r#"
            try {{
                Add-Type -AssemblyName System.Drawing
                $path = '{}'
                if (-not (Test-Path -Path $path)) {{ exit 1 }}

                $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
                if ($icon) {{
                    $bitmap = $icon.ToBitmap()
                    $stream = New-Object System.IO.MemoryStream
                    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
                    $base64 = [Convert]::ToBase64String($stream.ToArray())
                    Write-Output $base64
                }} else {{
                    exit 1
                }}
            }} catch {{
                exit 1
            }}
            "#,
            app_path.replace("'", "''")
        );

        let output = Command::new("powershell")
            .args(["-NoProfile", "-Command", &script])
            .creation_flags(0x08000000)
            .output()
            .ok()?;

        if !output.status.success() {
            return None;
        }

        let base64_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if base64_str.is_empty() {
            None
        } else {
            Some(format!("data:image/png;base64,{}", base64_str))
        }
    }

    #[cfg(target_os = "macos")]
    {
        // Read Info.plist to get icon file name
        let plist_path = format!("{}/Contents/Info.plist", app_path);

        // Use defaults command to read CFBundleIconFile
        let output = Command::new("defaults")
            .args(["read", &plist_path, "CFBundleIconFile"])
            .output()
            .ok()?;

        if !output.status.success() {
            return None;
        }

        let icon_name = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let icon_name = if icon_name.ends_with(".icns") {
            icon_name
        } else {
            format!("{}.icns", icon_name)
        };

        let icns_path = format!("{}/Contents/Resources/{}", app_path, icon_name);

        if !Path::new(&icns_path).exists() {
            return None;
        }

        // Create temp file for PNG output
        let temp_png = format!("/tmp/editor_icon_{}.png", std::process::id());

        // Use sips to convert icns to PNG (64x64 for retina displays)
        let sips_result = Command::new("sips")
            .args([
                "-s", "format", "png", "-z", "64", "64", &icns_path, "--out", &temp_png,
            ])
            .output();

        if sips_result.is_err() || !sips_result.as_ref().unwrap().status.success() {
            return None;
        }

        // Read PNG and convert to base64
        let png_data = fs::read(&temp_png).ok()?;
        let _ = fs::remove_file(&temp_png);

        let base64_data = BASE64.encode(&png_data);
        Some(format!("data:image/png;base64,{}", base64_data))
    }

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let _ = app_path;
        None
    }
}

pub fn open_in_external_editor(editor_id: &str, path: &str) -> Result<(), String> {
    let editor = EDITOR_DEFINITIONS
        .iter()
        .find(|e| e.id == editor_id)
        .ok_or_else(|| format!("Editor not found: {}", editor_id))?;

    if editor.open_cmd.is_empty() {
        return Err("Cannot open with built-in editor externally".to_string());
    }

    let parts: Vec<&str> = editor.open_cmd.split_whitespace().collect();
    if parts.is_empty() {
        return Err("Invalid open command".to_string());
    }

    // Try to resolve absolute path for the command
    let cmd_program = parts[0];
    let resolved_program = get_command_path(cmd_program).unwrap_or_else(|| cmd_program.to_string());

    #[cfg(target_os = "windows")]
    let mut cmd = build_windows_command(&resolved_program);

    #[cfg(not(target_os = "windows"))]
    let mut cmd = Command::new(&resolved_program);

    #[cfg(target_os = "windows")]
    {
        if editor_id != "terminal" {
            cmd.creation_flags(0x08000000);
        }
    }

    for part in parts.iter().skip(1) {
        cmd.arg(part);
    }
    cmd.arg(path);

    // Clean up environment variables that might cause issues in AppImage environments
    #[cfg(target_os = "linux")]
    {
        cmd.env_remove("PYTHONHOME");
        cmd.env_remove("PYTHONPATH");
        cmd.env_remove("LD_LIBRARY_PATH");
    }

    #[cfg(target_os = "windows")]
    {
        match cmd.spawn() {
            Ok(_) => Ok(()),
            Err(e) if e.raw_os_error() == Some(193) && resolved_program != cmd_program => {
                // ERROR_BAD_EXE_FORMAT: the resolved path is not a valid Win32
                // executable (e.g. a stale WindowsApps alias that slipped past
                // validation). Retry with the bare command name and let
                // CreateProcess perform its own resolution.
                let mut retry = build_windows_command(cmd_program);
                if editor_id != "terminal" {
                    retry.creation_flags(0x08000000);
                }
                for part in parts.iter().skip(1) {
                    retry.arg(part);
                }
                retry.arg(path);
                retry.spawn().map_err(|e| e.to_string())?;
                Ok(())
            }
            Err(e) => Err(e.to_string()),
        }
    }

    #[cfg(not(target_os = "windows"))]
    {
        cmd.spawn().map_err(|e| e.to_string())?;
        Ok(())
    }
}
