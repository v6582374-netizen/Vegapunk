use crate::models::SkillScope;
use crate::services::config_manager::ConfigManager;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf, MAIN_SEPARATOR};

#[cfg(windows)]
use std::process::Command;

/// Normalize path separators to the platform's native separator.
/// On Windows, converts all `/` to `\`. On Unix, this is a no-op.
pub fn normalize_path(path: &Path) -> PathBuf {
    if MAIN_SEPARATOR == '\\' {
        PathBuf::from(path.to_string_lossy().replace('/', "\\"))
    } else {
        path.to_path_buf()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum LinkStatus {
    Valid,
    Broken,
    WrongTarget,
    NotALink,
    Missing,
}

const COPY_MODE_METADATA_FILE: &str = ".skills-manager-source.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CopyModeMetadata {
    skill_id: String,
    source_path: String,
}

fn copy_mode_metadata_path(target_path: &Path) -> PathBuf {
    target_path.join(COPY_MODE_METADATA_FILE)
}

fn write_copy_mode_metadata(
    target_path: &Path,
    skill_id: &str,
    skill_source: &Path,
) -> Result<(), String> {
    let metadata = CopyModeMetadata {
        skill_id: skill_id.to_string(),
        source_path: skill_source.to_string_lossy().to_string(),
    };
    let content = serde_json::to_string_pretty(&metadata)
        .map_err(|e| format!("Failed to serialize copy mode metadata: {}", e))?;
    fs::write(copy_mode_metadata_path(target_path), content)
        .map_err(|e| format!("Failed to write copy mode metadata: {}", e))
}

pub fn read_copy_mode_metadata(target_path: &Path) -> Option<(String, PathBuf)> {
    let content = fs::read_to_string(copy_mode_metadata_path(target_path)).ok()?;
    let metadata: CopyModeMetadata = serde_json::from_str(&content).ok()?;
    Some((metadata.skill_id, PathBuf::from(metadata.source_path)))
}

pub fn copy_mode_target_matches_source(
    target_path: &Path,
    skill_id: &str,
    skill_source: &Path,
) -> bool {
    match read_copy_mode_metadata(target_path) {
        Some((saved_skill_id, saved_source_path)) => {
            saved_skill_id == skill_id && saved_source_path == skill_source
        }
        None => false,
    }
}

pub fn copy_mode_metadata_exists(target_path: &Path) -> bool {
    copy_mode_metadata_path(target_path).exists()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinkResult {
    pub skill_id: String,
    pub tool_id: String,
    pub status: LinkStatus,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LinkReport {
    pub success: Vec<LinkResult>,
    pub failed: Vec<LinkResult>,
}

pub struct LinkerService;
const IFLOW_TOOL_ID: &str = "iflow";

/// Check if a path is a symlink or a Windows Junction.
/// On Unix, this is equivalent to `is_symlink()`.
/// On Windows, Junctions created by `mklink /J` are NOT reported as symlinks
/// by Rust's `FileType::is_symlink()`, so we need additional detection.
pub fn is_symlink_or_junction(path: &Path) -> bool {
    if let Ok(meta) = path.symlink_metadata() {
        if meta.file_type().is_symlink() {
            return true;
        }

        // On Windows, check for reparse points (Junctions)
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x0400;
            if meta.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
                return true;
            }
        }
    }
    false
}

/// Remove a symlink or Junction at the given path.
/// Handles both file symlinks and directory junctions correctly.
pub fn remove_symlink_or_junction(path: &Path) -> Result<(), std::io::Error> {
    // On Windows, Junctions are directory-type, so remove_file won't work.
    // Try remove_dir first (works for junctions and dir symlinks),
    // then fall back to remove_file (for file symlinks).
    #[cfg(windows)]
    {
        return fs::remove_dir(path).or_else(|_| fs::remove_file(path));
    }

    #[cfg(unix)]
    {
        // On Unix, symlinks (both file and dir) can be removed with remove_file
        fs::remove_file(path)
    }
}

impl LinkerService {
    pub fn tool_uses_copy_mode(tool_id: &str) -> bool {
        tool_id == IFLOW_TOOL_ID
    }

    pub fn enable_skill_for_tool(
        skill_source: &Path,
        tool_skills_dir: &Path,
        skill_id: &str,
        tool_id: &str,
    ) -> Result<(), String> {
        if !Self::tool_uses_copy_mode(tool_id) {
            return Self::enable_skill(skill_source, tool_skills_dir, skill_id);
        }

        if !tool_skills_dir.exists() {
            fs::create_dir_all(tool_skills_dir)
                .map_err(|e| format!("Failed to create skills directory: {}", e))?;
        }

        let target_path = tool_skills_dir.join(skill_id);
        if target_path.exists() || target_path.symlink_metadata().is_ok() {
            fs::remove_file(&target_path)
                .or_else(|_| fs::remove_dir_all(&target_path))
                .map_err(|e| format!("Failed to remove existing skill directory: {}", e))?;
        }

        if !skill_source.is_dir() {
            return Err(format!(
                "Skill source is not a directory: {}",
                skill_source.display()
            ));
        }

        copy_dir_all_include_hidden(skill_source, &target_path)?;
        write_copy_mode_metadata(&target_path, skill_id, skill_source)?;
        Ok(())
    }

    pub fn enable_skill(
        skill_source: &Path,
        tool_skills_dir: &Path,
        skill_id: &str,
    ) -> Result<(), String> {
        if !tool_skills_dir.exists() {
            fs::create_dir_all(tool_skills_dir)
                .map_err(|e| format!("Failed to create skills directory: {}", e))?;
        }

        let link_path = tool_skills_dir.join(skill_id);

        if link_path.exists() || link_path.symlink_metadata().is_ok() {
            // Safety: only replace symlinks/junctions or copy-mode managed dirs.
            if is_symlink_or_junction(&link_path) {
                remove_symlink_or_junction(&link_path)
                    .map_err(|e| format!("Failed to remove existing link: {}", e))?;
            } else if copy_mode_metadata_exists(&link_path) {
                fs::remove_dir_all(&link_path)
                    .map_err(|e| format!("Failed to remove existing copy-mode skill: {}", e))?;
            } else {
                return Err(format!(
                    "Target path exists and is not managed by Skills-Manager: {}",
                    link_path.display()
                ));
            }
        }

        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(skill_source, &link_path)
                .map_err(|e| format!("Failed to create symlink: {}", e))?;
        }

        #[cfg(windows)]
        {
            if Self::create_windows_symlink(skill_source, &link_path).is_err() {
                // Fallback: copy mode when symlink/junction creation is not permitted
                // (e.g. no admin rights, developer mode disabled)
                if !skill_source.is_dir() {
                    return Err(format!(
                        "Skill source is not a directory: {}",
                        skill_source.display()
                    ));
                }
                copy_dir_all_include_hidden(skill_source, &link_path)?;
                write_copy_mode_metadata(&link_path, skill_id, skill_source)?;
            }
        }

        Ok(())
    }

    pub fn disable_skill_for_tool(
        tool_skills_dir: &Path,
        skill_id: &str,
        _tool_id: &str,
    ) -> Result<(), String> {
        Self::disable_skill(tool_skills_dir, skill_id)
    }

    #[cfg(windows)]
    pub fn create_windows_symlink(original: &Path, link: &Path) -> Result<(), String> {
        use std::os::windows::process::CommandExt;

        // 1. 确保父目录存在
        if let Some(parent) = link.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create parent directory: {}", e))?;
        }

        // 2. 确保目标位置没有残留文件/文件夹
        if link.exists() || link.symlink_metadata().is_ok() {
            if link.is_dir() {
                std::fs::remove_dir_all(link).ok();
            } else {
                std::fs::remove_file(link).ok();
            }
        }

        // 3. 尝试创建标准 Symlink (需要管理员权限或开发者模式)
        if std::os::windows::fs::symlink_dir(original, link).is_ok() {
            return Ok(());
        }

        // 4. 规范化路径：将 / 替换为 \，这对 cmd.exe 很重要
        let link_str = link.to_string_lossy().replace("/", "\\");
        let original_str = original.to_string_lossy().replace("/", "\\");

        // 5. 如果失败，尝试创建 Junction (不需要特殊权限)
        // mklink /J <Link> <Target>
        let output = Command::new("cmd")
            .args(["/C", "mklink", "/J"])
            .arg(&link_str)
            .arg(&original_str)
            .creation_flags(0x08000000) // CREATE_NO_WINDOW
            .output()
            .map_err(|e| format!("Failed to execute mklink: {}", e))?;

        if output.status.success() {
            Ok(())
        } else {
            // 尝试转码错误信息 (GBK -> UTF8)，如果失败则保留原始信息
            let stderr_bytes = output.stderr;
            let stdout_bytes = output.stdout;

            // 简单处理：如果是非 UTF8，可能是 GBK。
            // 这里我们只做尽力而为的转换，主要依赖 path 修正解决问题
            let stderr = String::from_utf8_lossy(&stderr_bytes);
            let stdout = String::from_utf8_lossy(&stdout_bytes);

            Err(format!(
                "Failed to create junction.\nCommand: mklink /J {:?} {:?}\nError: {}\nOutput: {}",
                link_str,
                original_str,
                stderr.trim(),
                stdout.trim()
            ))
        }
    }

    pub fn disable_skill(tool_skills_dir: &Path, skill_id: &str) -> Result<(), String> {
        let link_path = tool_skills_dir.join(skill_id);

        if !link_path.exists() && link_path.symlink_metadata().is_err() {
            return Ok(());
        }

        // Safety: only remove symlinks/junctions or copy-mode managed directories.
        // Never delete real user directories that we did not create.
        if is_symlink_or_junction(&link_path) {
            return remove_symlink_or_junction(&link_path)
                .map_err(|e| format!("Failed to remove link: {}", e));
        }

        // Copy-mode managed directory (created by this app, identified by metadata file)
        if copy_mode_metadata_exists(&link_path) {
            return fs::remove_dir_all(&link_path)
                .map_err(|e| format!("Failed to remove copy-mode skill: {}", e));
        }

        // Not a symlink and not managed by us — refuse to delete external content
        Err(format!(
            "Refusing to remove non-managed path (not a symlink): {}",
            link_path.display()
        ))
    }

    pub fn check_link(skill_source: &Path, tool_skills_dir: &Path, skill_id: &str) -> LinkStatus {
        let link_path = tool_skills_dir.join(skill_id);

        if is_symlink_or_junction(&link_path) {
            match fs::read_link(&link_path) {
                Ok(target) => {
                    // Resolve relative link targets against the link parent so we can
                    // compare canonical paths and avoid false "WrongTarget" reports.
                    let resolved_target = if target.is_relative() {
                        link_path
                            .parent()
                            .map(|p| p.join(&target))
                            .unwrap_or_else(|| target.clone())
                    } else {
                        target.clone()
                    };

                    // Fast path: exact path match.
                    if resolved_target == skill_source {
                        return if skill_source.exists() {
                            LinkStatus::Valid
                        } else {
                            LinkStatus::Broken
                        };
                    }

                    // Fallback: canonicalized comparison to handle path normalization.
                    let canonical_target = resolved_target.canonicalize().ok();
                    let canonical_source = skill_source.canonicalize().ok();

                    match (canonical_target, canonical_source) {
                        (Some(t), Some(s)) if t == s => LinkStatus::Valid,
                        _ => LinkStatus::WrongTarget,
                    }
                }
                Err(_) => LinkStatus::Broken,
            }
        } else if link_path.exists() {
            LinkStatus::NotALink
        } else {
            LinkStatus::Missing
        }
    }

    #[cfg(test)]
    pub fn check_link_for_tool(
        skill_source: &Path,
        tool_skills_dir: &Path,
        skill_id: &str,
        tool_id: &str,
    ) -> LinkStatus {
        if !Self::tool_uses_copy_mode(tool_id) {
            return Self::check_link(skill_source, tool_skills_dir, skill_id);
        }

        let copied_path = tool_skills_dir.join(skill_id);
        if copied_path.exists() {
            if copied_path.is_dir() {
                if !copy_mode_target_matches_source(&copied_path, skill_id, skill_source) {
                    return LinkStatus::WrongTarget;
                }

                if skill_source.exists() {
                    LinkStatus::Valid
                } else {
                    LinkStatus::Broken
                }
            } else {
                LinkStatus::NotALink
            }
        } else {
            LinkStatus::Missing
        }
    }

    pub fn check_link_for_scoped_skill(
        skill_source: &Path,
        tool_skills_dir: &Path,
        skill_id: &str,
        tool_id: &str,
        scope: &SkillScope,
    ) -> LinkStatus {
        if !Self::tool_uses_copy_mode(tool_id) {
            return Self::check_link(skill_source, tool_skills_dir, skill_id);
        }

        let copied_path = tool_skills_dir.join(skill_id);
        if !copied_path.exists() {
            return LinkStatus::Missing;
        }
        if !copied_path.is_dir() {
            return LinkStatus::NotALink;
        }

        if copy_mode_target_matches_source(&copied_path, skill_id, skill_source) {
            return if skill_source.exists() {
                LinkStatus::Valid
            } else {
                LinkStatus::Broken
            };
        }

        if !copy_mode_metadata_exists(&copied_path) && matches!(scope, SkillScope::Global) {
            return if skill_source.exists() {
                LinkStatus::Valid
            } else {
                LinkStatus::Broken
            };
        }

        LinkStatus::WrongTarget
    }

    #[cfg(test)]
    pub fn sync_all_for_tool(
        skills: &[(String, std::path::PathBuf)],
        tool_skills_dir: &Path,
        enabled_skills: &[String],
        tool_id: &str,
    ) -> LinkReport {
        let mut report = LinkReport::default();

        for (skill_id, skill_path) in skills {
            let should_be_enabled = enabled_skills.contains(skill_id);
            let current_status =
                Self::check_link_for_tool(skill_path, tool_skills_dir, skill_id, tool_id);

            if should_be_enabled {
                if current_status == LinkStatus::Valid {
                    continue;
                }

                match Self::enable_skill_for_tool(skill_path, tool_skills_dir, skill_id, tool_id) {
                    Ok(_) => {
                        report.success.push(LinkResult {
                            skill_id: skill_id.clone(),
                            tool_id: tool_id.to_string(),
                            status: LinkStatus::Valid,
                            message: Some("Enabled successfully".to_string()),
                        });
                    }
                    Err(e) => {
                        report.failed.push(LinkResult {
                            skill_id: skill_id.clone(),
                            tool_id: tool_id.to_string(),
                            status: LinkStatus::Broken,
                            message: Some(e),
                        });
                    }
                }
            } else {
                if current_status == LinkStatus::Missing {
                    continue;
                }

                match Self::disable_skill_for_tool(tool_skills_dir, skill_id, tool_id) {
                    Ok(_) => {
                        report.success.push(LinkResult {
                            skill_id: skill_id.clone(),
                            tool_id: tool_id.to_string(),
                            status: LinkStatus::Missing,
                            message: Some("Disabled successfully".to_string()),
                        });
                    }
                    Err(e) => {
                        report.failed.push(LinkResult {
                            skill_id: skill_id.clone(),
                            tool_id: tool_id.to_string(),
                            status: LinkStatus::Broken,
                            message: Some(e),
                        });
                    }
                }
            }
        }

        report
    }

    pub fn import_to_hub(skill_path: &str) -> Result<(), String> {
        let source = PathBuf::from(skill_path);
        if !source.exists() {
            return Err(format!("Skill path does not exist: {}", skill_path));
        }

        let skill_name = source
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or("Invalid skill path")?;

        let config = ConfigManager::new().load()?;
        let hub_skills_dir = PathBuf::from(&config.skills_dir);

        // 确保 hub 目录存在
        std::fs::create_dir_all(&hub_skills_dir)
            .map_err(|e| format!("Failed to create hub directory: {}", e))?;

        let target = hub_skills_dir.join(skill_name);

        // 如果目标已存在，跳过
        if target.exists() {
            return Ok(());
        }

        // 如果源是软链接，获取真实路径（规范化处理相对路径）
        let real_source = if source.is_symlink() {
            std::fs::read_link(&source)
                .and_then(|p| {
                    if p.is_relative() {
                        source.parent().unwrap_or(&source).join(&p).canonicalize()
                    } else {
                        p.canonicalize()
                    }
                })
                .map_err(|e| format!("Failed to resolve symlink: {}", e))?
        } else {
            source.clone()
        };

        // 移动到 hub
        std::fs::rename(&real_source, &target)
            .or_else(|_| {
                // 如果跨文件系统，使用复制+删除
                copy_dir_all(&real_source, &target)?;
                std::fs::remove_dir_all(&real_source).or_else(|e| {
                    // 如果删除失败，清理已复制的目标
                    let _ = std::fs::remove_dir_all(&target);
                    Err(format!("Failed to remove source after copy: {}", e))
                })
            })
            .map_err(|e| format!("Failed to move skill: {}", e))?;

        // 在原位置创建软链接
        if source != real_source {
            // 原来就是软链接，删除旧的
            std::fs::remove_file(&source).ok();
        }

        #[cfg(unix)]
        std::os::unix::fs::symlink(&target, &source)
            .map_err(|e| format!("Failed to create symlink: {}", e))?;

        #[cfg(windows)]
        Self::create_windows_symlink(&target, &source)?;

        Ok(())
    }
}

fn copy_dir_all(src: &std::path::Path, dst: &std::path::Path) -> Result<(), String> {
    copy_dir_all_with_options(src, dst, true)
}

fn copy_dir_all_include_hidden(src: &std::path::Path, dst: &std::path::Path) -> Result<(), String> {
    copy_dir_all_with_options(src, dst, false)
}

fn copy_dir_all_with_options(
    src: &std::path::Path,
    dst: &std::path::Path,
    skip_hidden: bool,
) -> Result<(), String> {
    std::fs::create_dir_all(dst).map_err(|e| format!("Failed to create directory: {}", e))?;

    for entry in std::fs::read_dir(src).map_err(|e| format!("Failed to read directory: {}", e))? {
        let entry = entry.map_err(|e| format!("Failed to read entry: {}", e))?;
        let file_name = entry.file_name();
        let file_name_str = file_name.to_string_lossy();

        // Optionally skip hidden files/directories (starting with .)
        if skip_hidden && file_name_str.starts_with('.') {
            continue;
        }

        let ty = entry
            .file_type()
            .map_err(|e| format!("Failed to get file type: {}", e))?;

        if ty.is_dir() {
            copy_dir_all_with_options(&entry.path(), &dst.join(entry.file_name()), skip_hidden)?;
        } else {
            std::fs::copy(entry.path(), dst.join(entry.file_name()))
                .map_err(|e| format!("Failed to copy file: {}", e))?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{LinkStatus, LinkerService};
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn make_temp_dir(name: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after unix epoch")
            .as_nanos();
        let dir = std::env::temp_dir()
            .join("skills-manager-linker-tests")
            .join(format!("{}-{}-{}", name, std::process::id(), unique));
        fs::create_dir_all(&dir).expect("temp dir should be created");
        dir
    }

    #[test]
    fn iflow_enable_skill_uses_copy_mode_instead_of_symlink() {
        let root = make_temp_dir("iflow-copy");
        let source_skill = root.join("hub").join("demo-skill");
        let tool_skills_dir = root.join("iflow").join("skills");
        let target_skill = tool_skills_dir.join("demo-skill");

        fs::create_dir_all(&source_skill).expect("source skill dir should be created");
        fs::write(source_skill.join("SKILL.md"), "# Demo\n").expect("skill file should be created");
        fs::write(source_skill.join("meta.json"), "{\"name\":\"demo\"}")
            .expect("meta file should be created");
        fs::write(source_skill.join(".env"), "TOKEN=demo\n")
            .expect("hidden file should be created");
        fs::create_dir_all(source_skill.join(".github")).expect("hidden dir should be created");
        fs::write(
            source_skill.join(".github").join("workflows.yml"),
            "name: ci\n",
        )
        .expect("hidden nested file should be created");

        LinkerService::enable_skill_for_tool(
            &source_skill,
            &tool_skills_dir,
            "demo-skill",
            "iflow",
        )
        .expect("iflow enable should succeed");

        assert!(target_skill.exists(), "target directory should exist");
        assert!(target_skill.is_dir(), "target should be a directory");
        let meta = fs::symlink_metadata(&target_skill).expect("target metadata should exist");
        assert!(
            !meta.file_type().is_symlink(),
            "iflow target should be copied dir, not symlink"
        );
        assert!(
            target_skill.join("SKILL.md").exists(),
            "copied skill should contain SKILL.md"
        );
        assert!(
            target_skill.join(".env").exists(),
            "copied skill should contain hidden file"
        );
        assert!(
            target_skill.join(".github").join("workflows.yml").exists(),
            "copied skill should contain hidden directory files"
        );
        assert_eq!(
            LinkerService::check_link_for_tool(
                &source_skill,
                &tool_skills_dir,
                "demo-skill",
                "iflow"
            ),
            LinkStatus::Valid
        );

        LinkerService::disable_skill_for_tool(&tool_skills_dir, "demo-skill", "iflow")
            .expect("iflow disable should succeed");
        assert!(
            !target_skill.exists(),
            "disable should remove copied iflow skill"
        );

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn sync_all_for_tool_skips_noop_when_disabled_skill_is_already_missing() {
        let root = make_temp_dir("sync-noop-missing");
        let source_skill = root.join("hub").join("demo-skill");
        let tool_skills_dir = root.join("codex").join("skills");
        fs::create_dir_all(&source_skill).expect("source skill dir should be created");
        fs::create_dir_all(&tool_skills_dir).expect("tool skills dir should be created");

        let skills = vec![("demo-skill".to_string(), source_skill.clone())];
        let enabled_skills: Vec<String> = vec![];
        let report =
            LinkerService::sync_all_for_tool(&skills, &tool_skills_dir, &enabled_skills, "codex");

        assert_eq!(
            report.success.len(),
            0,
            "missing link should be treated as noop"
        );
        assert_eq!(report.failed.len(), 0, "noop should not produce failures");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn sync_all_for_tool_skips_noop_when_enabled_skill_is_already_valid() {
        let root = make_temp_dir("sync-noop-valid");
        let source_skill = root.join("hub").join("demo-skill");
        let tool_skills_dir = root.join("codex").join("skills");
        fs::create_dir_all(&source_skill).expect("source skill dir should be created");
        fs::write(source_skill.join("SKILL.md"), "# Demo\n").expect("skill file should be created");

        LinkerService::enable_skill_for_tool(
            &source_skill,
            &tool_skills_dir,
            "demo-skill",
            "codex",
        )
        .expect("initial enable should succeed");

        let skills = vec![("demo-skill".to_string(), source_skill.clone())];
        let enabled_skills = vec!["demo-skill".to_string()];
        let report =
            LinkerService::sync_all_for_tool(&skills, &tool_skills_dir, &enabled_skills, "codex");

        assert_eq!(
            report.success.len(),
            0,
            "valid link should be treated as noop"
        );
        assert_eq!(report.failed.len(), 0, "noop should not produce failures");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn disable_skill_refuses_to_delete_real_directory_but_removes_symlink() {
        let root = make_temp_dir("disable-safety");
        let tool_skills_dir = root.join("tool").join("skills");
        fs::create_dir_all(&tool_skills_dir).expect("tool skills dir");

        // Case 1: real directory (user-placed, not managed by us) — must NOT be deleted
        let real_dir = tool_skills_dir.join("user-skill");
        fs::create_dir_all(&real_dir).expect("create real dir");
        fs::write(real_dir.join("SKILL.md"), "# User skill\n").expect("write skill file");

        let result = LinkerService::disable_skill(&tool_skills_dir, "user-skill");
        assert!(
            result.is_err(),
            "disable_skill must refuse to delete a real directory"
        );
        assert!(
            real_dir.exists(),
            "real directory must still exist after refused delete"
        );

        // Case 2: symlink — should be removed successfully
        let source = root.join("hub").join("linked-skill");
        fs::create_dir_all(&source).expect("create source");
        let link_path = tool_skills_dir.join("linked-skill");
        std::os::unix::fs::symlink(&source, &link_path).expect("create symlink");

        let result = LinkerService::disable_skill(&tool_skills_dir, "linked-skill");
        assert!(result.is_ok(), "disable_skill should remove a symlink");
        assert!(
            !link_path.exists() && link_path.symlink_metadata().is_err(),
            "symlink should be gone"
        );
        assert!(source.exists(), "symlink target must not be deleted");

        let _ = fs::remove_dir_all(root);
    }
}
