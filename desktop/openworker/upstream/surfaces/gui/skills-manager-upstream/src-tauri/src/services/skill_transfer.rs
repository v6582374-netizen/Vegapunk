use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use crate::models::{AppConfig, Skill, SkillMetadata, SkillScope, SkillSource};
use crate::services::{ConfigManager, LinkerService, ScannerService};

/// Format version of the export manifest. Bump when structure changes.
pub const MANIFEST_FORMAT_VERSION: u32 = 1;
/// Entry inside the zip archive that holds the manifest JSON.
pub const MANIFEST_ENTRY: &str = "manifest.json";
/// Directory prefix inside the zip archive that holds skill folders.
pub const SKILLS_PREFIX: &str = "skills/";

/// Top-level manifest written into every export archive.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportManifest {
    pub format_version: u32,
    pub exported_at: i64,
    pub app_version: String,
    pub skills: Vec<ExportedSkillMeta>,
}

/// Per-skill metadata recorded in the manifest.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExportedSkillMeta {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub version: String,
    /// Archive-relative folder path, e.g. `skills/my-skill`.
    pub folder: String,
    /// Tool IDs the user explicitly enabled for this skill on the source device.
    pub enabled_tools: Vec<String>,
    pub tags: Vec<String>,
    pub favorited_at: Option<i64>,
}

/// Conflict detected when previewing an import.
#[derive(Debug, Clone, Serialize)]
pub struct ImportConflict {
    pub skill_id: String,
    pub skill_name: String,
    pub local_path: String,
}

/// Result of previewing an import archive.
#[derive(Debug, Clone, Serialize)]
pub struct ImportPreview {
    pub manifest: ExportManifest,
    pub conflicts: Vec<ImportConflict>,
}

/// Strategy for resolving a same-name conflict on the target device.
#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConflictStrategy {
    Skip,
    Overwrite,
    Rename,
}

/// Per-skill resolution supplied by the caller when executing an import.
#[derive(Debug, Clone, Deserialize)]
pub struct ImportResolution {
    pub skill_id: String,
    pub strategy: ConflictStrategy,
}

/// Record of a skill successfully imported under a new id.
#[derive(Debug, Clone, Serialize)]
pub struct RenamedSkillRecord {
    pub original_id: String,
    pub new_id: String,
    pub name: String,
}

/// Record of a skill successfully imported (possibly renamed).
#[derive(Debug, Clone, Serialize)]
pub struct ImportedSkillRecord {
    pub original_id: String,
    pub final_id: String,
    pub name: String,
}

/// Record of a skill that failed to import.
#[derive(Debug, Clone, Serialize)]
pub struct ImportFailure {
    pub skill_id: String,
    pub message: String,
}

/// Aggregated result of executing an import.
#[derive(Debug, Clone, Serialize)]
pub struct ImportResult {
    pub imported: Vec<ImportedSkillRecord>,
    pub skipped: Vec<String>,
    pub overwritten: Vec<String>,
    pub renamed: Vec<RenamedSkillRecord>,
    pub failed: Vec<ImportFailure>,
}

/// Skills eligible for export (global scope, non-marketplace/vault).
pub fn collect_exportable_skills(config: &AppConfig) -> Result<Vec<Skill>, String> {
    let skills = ScannerService::scan_scoped_skills(config)?;
    Ok(skills
        .into_iter()
        .filter(|skill| matches!(skill.scope, SkillScope::Global))
        .filter(|skill| matches!(skill.source, SkillSource::Local | SkillSource::Imported))
        .collect())
}

/// Build a manifest entry for a single skill.
fn build_manifest_entry(skill: &Skill, config: &AppConfig) -> ExportedSkillMeta {
    let enabled_tools: Vec<String> = config
        .tools
        .iter()
        .filter_map(|(tool_id, _tool_config)| {
            if skill.is_enabled_for(tool_id) {
                Some(tool_id.clone())
            } else {
                None
            }
        })
        .collect();

    let (tags, favorited_at) = config
        .skill_metadata
        .get(&skill.instance_id)
        .map(|metadata| (metadata.tags.clone(), metadata.favorited_at))
        .unwrap_or_default();

    ExportedSkillMeta {
        id: skill.id.clone(),
        name: skill.name.clone(),
        description: skill.description.clone(),
        version: skill.version.clone(),
        folder: format!("{}{}", SKILLS_PREFIX, skill.id),
        enabled_tools,
        tags,
        favorited_at,
    }
}

/// Recursively add a directory tree to the zip archive.
///
/// `fs_base` is the filesystem path of the directory to walk. `archive_prefix`
/// is the path prefix to use inside the archive (e.g. `skills/my-skill`), so
/// the resulting entries look like `skills/my-skill/SKILL.md`.
fn add_dir_to_zip<W: Write + std::io::Seek>(
    zip: &mut zip::ZipWriter<W>,
    fs_base: &Path,
    archive_prefix: &str,
    options: zip::write::FileOptions,
) -> Result<(), String> {
    let entries = fs::read_dir(fs_base).map_err(|e| format!("Failed to read dir: {}", e))?;
    for entry in entries.flatten() {
        let path = entry.path();
        let rel = path
            .strip_prefix(fs_base)
            .map_err(|e| e.to_string())?;
        let rel_str = rel.to_string_lossy().replace('\\', "/");
        let archive_name = if archive_prefix.is_empty() {
            rel_str
        } else {
            format!("{}/{}", archive_prefix, rel_str)
        };

        if path.is_dir() {
            zip.add_directory(&archive_name, options)
                .map_err(|e| format!("Failed to add directory to zip: {}", e))?;
            add_dir_to_zip(zip, &path, &archive_name, options)?;
        } else if path.is_file() {
            zip.start_file(&archive_name, options)
                .map_err(|e| format!("Failed to start zip entry: {}", e))?;
            let mut f = fs::File::open(&path).map_err(|e| format!("Failed to open file: {}", e))?;
            let mut buf = Vec::new();
            f.read_to_end(&mut buf)
                .map_err(|e| format!("Failed to read file: {}", e))?;
            zip.write_all(&buf)
                .map_err(|e| format!("Failed to write zip entry: {}", e))?;
        }
    }
    Ok(())
}

/// Pack the given skills into a zip archive at `output_path`.
pub fn export_skills_to_zip(
    config: &AppConfig,
    skills: &[Skill],
    output_path: &Path,
) -> Result<(), String> {
    let file = fs::File::create(output_path)
        .map_err(|e| format!("Failed to create export file: {}", e))?;
    let mut zip = zip::ZipWriter::new(file);
    let options =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    let manifest = ExportManifest {
        format_version: MANIFEST_FORMAT_VERSION,
        exported_at: chrono_now_secs(),
        app_version: config.version.clone(),
        skills: skills
            .iter()
            .map(|skill| build_manifest_entry(skill, config))
            .collect(),
    };

    // Write manifest first so importers can read it without scanning everything.
    zip.start_file(MANIFEST_ENTRY, options)
        .map_err(|e| format!("Failed to start manifest entry: {}", e))?;
    let manifest_json = serde_json::to_string_pretty(&manifest)
        .map_err(|e| format!("Failed to serialize manifest: {}", e))?;
    zip.write_all(manifest_json.as_bytes())
        .map_err(|e| format!("Failed to write manifest: {}", e))?;

    // Pack each skill folder under `skills/<id>/` so the manifest `folder`
    // field matches the archive layout.
    for skill in skills {
        let skill_path = &skill.path;
        if !skill_path.exists() {
            // Skip missing skill folders silently — the manifest still records them.
            continue;
        }
        let archive_prefix = format!("{}{}", SKILLS_PREFIX, skill.id);
        add_dir_to_zip(&mut zip, skill_path, &archive_prefix, options)?;
    }

    zip.finish()
        .map_err(|e| format!("Failed to finalize zip archive: {}", e))?;
    Ok(())
}

/// Read the manifest from an export archive without extracting skill contents.
pub fn read_archive_manifest(zip_path: &Path) -> Result<ExportManifest, String> {
    let file = fs::File::open(zip_path).map_err(|e| format!("Failed to open archive: {}", e))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("Invalid archive: {}", e))?;

    let mut manifest_bytes = Vec::new();
    let mut found = false;
    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("Failed to read zip entry: {}", e))?;
        if entry.name() == MANIFEST_ENTRY {
            entry
                .read_to_end(&mut manifest_bytes)
                .map_err(|e| format!("Failed to read manifest: {}", e))?;
            found = true;
            break;
        }
    }

    if !found {
        return Err(format!("Manifest not found in archive: {}", MANIFEST_ENTRY));
    }

    serde_json::from_slice::<ExportManifest>(&manifest_bytes)
        .map_err(|e| format!("Failed to parse manifest: {}", e))
}

/// Preview an import: parse manifest and detect conflicts against the current hub.
pub fn preview_import(zip_path: &Path, config: &AppConfig) -> Result<ImportPreview, String> {
    let manifest = read_archive_manifest(zip_path)?;
    let mut conflicts = Vec::new();
    for skill in &manifest.skills {
        let target = config.skills_dir.join(&skill.id);
        if target.exists() {
            conflicts.push(ImportConflict {
                skill_id: skill.id.clone(),
                skill_name: skill.name.clone(),
                local_path: target.to_string_lossy().to_string(),
            });
        }
    }
    Ok(ImportPreview { manifest, conflicts })
}

/// Extract one skill folder from the archive into `dest`.
fn extract_skill_folder(
    archive: &mut zip::ZipArchive<fs::File>,
    folder_prefix: &str,
    dest: &Path,
) -> Result<(), String> {
    fs::create_dir_all(dest).map_err(|e| format!("Failed to create dest dir: {}", e))?;

    let prefix_with_slash = if folder_prefix.ends_with('/') {
        folder_prefix.to_string()
    } else {
        format!("{}/", folder_prefix)
    };

    let mut indices: Vec<usize> = Vec::new();
    for i in 0..archive.len() {
        let entry = archive
            .by_index(i)
            .map_err(|e| format!("Failed to stat zip entry: {}", e))?;
        let name = entry.name().to_string();
        if name == folder_prefix || name.starts_with(&prefix_with_slash) {
            indices.push(i);
        }
    }

    for i in indices {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| format!("Failed to open zip entry: {}", e))?;
        let entry_name = entry.name().to_string();

        // Skip directory entries — we create dirs on demand.
        if entry_name.ends_with('/') {
            continue;
        }

        let relative = entry_name
            .strip_prefix(&prefix_with_slash)
            .or_else(|| entry_name.strip_prefix(folder_prefix))
            .unwrap_or(&entry_name);
        let relative = relative.trim_start_matches('/');
        let dest_path = dest.join(relative);

        if let Some(parent) = dest_path.parent() {
            fs::create_dir_all(parent).map_err(|e| format!("Failed to create parent: {}", e))?;
        }

        let mut buf = Vec::new();
        entry
            .read_to_end(&mut buf)
            .map_err(|e| format!("Failed to read zip entry: {}", e))?;
        fs::write(&dest_path, &buf).map_err(|e| format!("Failed to write file: {}", e))?;
    }

    Ok(())
}

/// Find an available renamed id like `<base>-imported-<n>`.
fn find_renamed_id(base: &str, config: &AppConfig) -> String {
    let mut n = 1;
    loop {
        let candidate = format!("{}-imported-{}", base, n);
        if !config.skills_dir.join(&candidate).exists() {
            return candidate;
        }
        n += 1;
    }
}

/// Execute an import according to the user-supplied per-skill resolutions.
///
/// `resolutions` must cover every skill listed in the manifest; missing entries
/// are treated as `Skip`.
pub fn import_skills_from_zip(
    zip_path: &Path,
    resolutions: &[ImportResolution],
    config: &AppConfig,
) -> Result<ImportResult, String> {
    let manifest = read_archive_manifest(zip_path)?;
    let file = fs::File::open(zip_path).map_err(|e| format!("Failed to open archive: {}", e))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("Invalid archive: {}", e))?;

    let resolution_map: HashMap<String, ConflictStrategy> = resolutions
        .iter()
        .map(|r| (r.skill_id.clone(), r.strategy))
        .collect();

    let mut imported = Vec::new();
    let mut skipped = Vec::new();
    let mut overwritten = Vec::new();
    let mut renamed = Vec::new();
    let mut failed = Vec::new();

    let mut updated_metadata: HashMap<String, SkillMetadata> = config.skill_metadata.clone();

    for skill_meta in &manifest.skills {
        let strategy = resolution_map
            .get(&skill_meta.id)
            .copied()
            .unwrap_or(ConflictStrategy::Skip);

        let target_path = config.skills_dir.join(&skill_meta.id);
        let has_conflict = target_path.exists();

        let (final_id, final_path): (String, PathBuf) = match (strategy, has_conflict) {
            (ConflictStrategy::Skip, true) => {
                skipped.push(skill_meta.id.clone());
                continue;
            }
            (ConflictStrategy::Skip, false) => (skill_meta.id.clone(), target_path),
            (ConflictStrategy::Overwrite, true) => {
                fs::remove_dir_all(&target_path)
                    .map_err(|e| format!("Failed to remove existing skill: {}", e))?;
                overwritten.push(skill_meta.id.clone());
                (skill_meta.id.clone(), target_path)
            }
            (ConflictStrategy::Overwrite, false) => (skill_meta.id.clone(), target_path),
            (ConflictStrategy::Rename, true) => {
                let new_id = find_renamed_id(&skill_meta.id, config);
                let new_path = config.skills_dir.join(&new_id);
                renamed.push(RenamedSkillRecord {
                    original_id: skill_meta.id.clone(),
                    new_id: new_id.clone(),
                    name: skill_meta.name.clone(),
                });
                (new_id, new_path)
            }
            (ConflictStrategy::Rename, false) => (skill_meta.id.clone(), target_path),
        };

        // Extract the skill folder from the archive.
        if let Err(e) = extract_skill_folder(&mut archive, &skill_meta.folder, &final_path) {
            failed.push(ImportFailure {
                skill_id: skill_meta.id.clone(),
                message: e,
            });
            continue;
        }

        // Apply tool enablements only for tools that exist on this device.
        let mut enabled_tools: Vec<String> = Vec::new();
        for tool_id in &skill_meta.enabled_tools {
            if !config.tools.contains_key(tool_id) {
                continue;
            }
            match LinkerService::enable_skill_for_tool(
                &final_path,
                &config.tools[tool_id].skills_path,
                &final_id,
                tool_id,
            ) {
                Ok(_) => enabled_tools.push(tool_id.clone()),
                Err(_) => { /* best-effort; don't fail the whole import */ }
            }
        }

        // Merge metadata (tags + favorited_at) under the final instance id.
        if !skill_meta.tags.is_empty() || skill_meta.favorited_at.is_some() {
            let instance_id = Skill::global_instance_id(&final_id);
            let entry = updated_metadata
                .entry(instance_id)
                .or_insert_with(|| SkillMetadata {
                    tags: Vec::new(),
                    favorited_at: None,
                });
            // Merge tags (union, preserve case-insensitive uniqueness).
            for tag in &skill_meta.tags {
                let lower = tag.to_lowercase();
                if !entry.tags.iter().any(|existing| existing.to_lowercase() == lower) {
                    entry.tags.push(tag.clone());
                }
            }
            // Only set favorited_at if not already set (don't unfavorite).
            if entry.favorited_at.is_none() {
                entry.favorited_at = skill_meta.favorited_at;
            }
        }

        imported.push(ImportedSkillRecord {
            original_id: skill_meta.id.clone(),
            final_id,
            name: skill_meta.name.clone(),
        });
    }

    // Persist merged metadata if anything changed.
    if updated_metadata != config.skill_metadata {
        let mut new_config = config.clone();
        new_config.skill_metadata = updated_metadata;
        ConfigManager::new().save(&new_config)?;
    }

    Ok(ImportResult {
        imported,
        skipped,
        overwritten,
        renamed,
        failed,
    })
}

/// Best-effort portable "now in seconds" without pulling in chrono.
fn chrono_now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::with_temp_home;
    use std::collections::HashMap;
    use std::path::PathBuf;

    fn write_skill_md(dir: &Path, id: &str, body: &str) {
        fs::create_dir_all(dir).expect("create skill dir");
        fs::write(
            dir.join("SKILL.md"),
            format!("---\nname: {}\n---\n{}", id, body),
        )
        .expect("write SKILL.md");
    }

    fn make_config(skills_dir: PathBuf) -> AppConfig {
        let mut config = AppConfig::default();
        config.skills_dir = skills_dir;
        config.initialized = true;
        config
    }

    #[test]
    fn export_then_import_roundtrip_restores_skill_folder() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let skill_a = skills_dir.join("skill-a");
            let skill_b = skills_dir.join("skill-b");
            write_skill_md(&skill_a, "skill-a", "Body A\n");
            fs::write(skill_a.join("extra.txt"), "extra").expect("write extra");
            write_skill_md(&skill_b, "skill-b", "Body B\n");

            let config = make_config(skills_dir.clone());
            let skills = ScannerService::scan_scoped_skills(&config).expect("scan");

            let archive = home.join("export.zip");
            export_skills_to_zip(&config, &skills, &archive).expect("export");

            // Wipe hub and re-import everything.
            fs::remove_dir_all(&skills_dir).expect("wipe hub");
            fs::create_dir_all(&skills_dir).expect("recreate hub");

            let preview = preview_import(&archive, &config).expect("preview");
            assert!(preview.conflicts.is_empty());
            assert_eq!(preview.manifest.skills.len(), 2);

            let resolutions: Vec<ImportResolution> = preview
                .manifest
                .skills
                .iter()
                .map(|s| ImportResolution {
                    skill_id: s.id.clone(),
                    strategy: ConflictStrategy::Overwrite,
                })
                .collect();

            let result =
                import_skills_from_zip(&archive, &resolutions, &config).expect("import");
            assert_eq!(result.imported.len(), 2);
            assert!(result.failed.is_empty());

            let restored_a = skills_dir.join("skill-a").join("SKILL.md");
            let restored_b = skills_dir.join("skill-b").join("SKILL.md");
            assert!(restored_a.exists());
            assert!(restored_b.exists());
            assert_eq!(
                fs::read_to_string(&restored_a).unwrap(),
                "---\nname: skill-a\n---\nBody A\n"
            );
            assert_eq!(
                fs::read_to_string(skills_dir.join("skill-a").join("extra.txt")).unwrap(),
                "extra"
            );
        });
    }

    #[test]
    fn import_detects_conflicts_against_existing_skills() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            // Source skill that will be exported.
            let src_skill = skills_dir.join("shared-skill");
            write_skill_md(&src_skill, "shared-skill", "Original\n");

            let config = make_config(skills_dir.clone());
            let skills = ScannerService::scan_scoped_skills(&config).expect("scan");

            let archive = home.join("export.zip");
            export_skills_to_zip(&config, &skills, &archive).expect("export");

            // Now `shared-skill` still exists locally — preview must flag it.
            let preview = preview_import(&archive, &config).expect("preview");
            assert_eq!(preview.conflicts.len(), 1);
            assert_eq!(preview.conflicts[0].skill_id, "shared-skill");
        });
    }

    #[test]
    fn import_skip_strategy_leaves_local_skill_untouched() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let src_skill = skills_dir.join("shared-skill");
            write_skill_md(&src_skill, "shared-skill", "Local version\n");

            let config = make_config(skills_dir.clone());
            let skills = ScannerService::scan_scoped_skills(&config).expect("scan");

            let archive = home.join("export.zip");
            export_skills_to_zip(&config, &skills, &archive).expect("export");

            // Overwrite local content to simulate a divergent local copy.
            fs::write(
                src_skill.join("SKILL.md"),
                "---\nname: shared-skill\n---\nLocal diverged\n",
            )
            .expect("diverge local");

            let resolutions = vec![ImportResolution {
                skill_id: "shared-skill".to_string(),
                strategy: ConflictStrategy::Skip,
            }];
            let result =
                import_skills_from_zip(&archive, &resolutions, &config).expect("import");
            assert_eq!(result.skipped, vec!["shared-skill".to_string()]);
            assert_eq!(result.imported.len(), 0);
            assert_eq!(
                fs::read_to_string(src_skill.join("SKILL.md")).unwrap(),
                "---\nname: shared-skill\n---\nLocal diverged\n"
            );
        });
    }

    #[test]
    fn import_overwrite_strategy_replaces_local_skill() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let src_skill = skills_dir.join("shared-skill");
            write_skill_md(&src_skill, "shared-skill", "Exported\n");

            let config = make_config(skills_dir.clone());
            let skills = ScannerService::scan_scoped_skills(&config).expect("scan");

            let archive = home.join("export.zip");
            export_skills_to_zip(&config, &skills, &archive).expect("export");

            fs::write(
                src_skill.join("SKILL.md"),
                "---\nname: shared-skill\n---\nLocal diverged\n",
            )
            .expect("diverge local");

            let resolutions = vec![ImportResolution {
                skill_id: "shared-skill".to_string(),
                strategy: ConflictStrategy::Overwrite,
            }];
            let result =
                import_skills_from_zip(&archive, &resolutions, &config).expect("import");
            assert_eq!(result.overwritten, vec!["shared-skill".to_string()]);
            assert_eq!(result.imported.len(), 1);
            assert_eq!(
                fs::read_to_string(src_skill.join("SKILL.md")).unwrap(),
                "---\nname: shared-skill\n---\nExported\n"
            );
        });
    }

    #[test]
    fn import_rename_strategy_creates_new_id() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let src_skill = skills_dir.join("shared-skill");
            write_skill_md(&src_skill, "shared-skill", "Exported\n");

            let config = make_config(skills_dir.clone());
            let skills = ScannerService::scan_scoped_skills(&config).expect("scan");

            let archive = home.join("export.zip");
            export_skills_to_zip(&config, &skills, &archive).expect("export");

            let resolutions = vec![ImportResolution {
                skill_id: "shared-skill".to_string(),
                strategy: ConflictStrategy::Rename,
            }];
            let result =
                import_skills_from_zip(&archive, &resolutions, &config).expect("import");

            assert_eq!(result.renamed.len(), 1);
            assert_eq!(result.renamed[0].original_id, "shared-skill");
            assert_eq!(result.renamed[0].new_id, "shared-skill-imported-1");
            assert!(skills_dir.join("shared-skill-imported-1").exists());
            // Original is preserved.
            assert!(skills_dir.join("shared-skill").exists());
        });
    }
}
