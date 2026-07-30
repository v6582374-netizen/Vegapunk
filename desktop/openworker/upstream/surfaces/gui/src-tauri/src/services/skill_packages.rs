use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::models::skill_package::{SkillPackageManifest, SkillPackageMember};
use crate::models::InstalledSkillPackage;

pub struct SkillPackageService;

impl SkillPackageService {
    pub fn packages_dir() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_default()
            .join(".skills-manager")
            .join("packages")
    }

    pub fn package_dir(package_id: &str) -> PathBuf {
        Self::packages_dir().join(package_id)
    }

    pub fn parse_manifest(content: &str) -> Result<SkillPackageManifest, String> {
        let manifest: SkillPackageManifest =
            toml::from_str(content).map_err(|e| format!("Failed to parse skill-pack.toml: {e}"))?;

        let mut member_ids = HashSet::new();
        let mut skill_ids = HashSet::new();
        for member in &manifest.members {
            if !member_ids.insert(member.member_id.clone()) {
                return Err(format!("duplicate member_id: {}", member.member_id));
            }
            if !skill_ids.insert(member.skill_id.clone()) {
                return Err(format!("duplicate skill_id: {}", member.skill_id));
            }
        }

        Ok(manifest)
    }

    pub fn read_manifest(path: &Path) -> Result<SkillPackageManifest, String> {
        let content =
            fs::read_to_string(path).map_err(|e| format!("Failed to read skill-pack.toml: {e}"))?;
        Self::parse_manifest(&content)
    }

    pub fn list_installed_packages() -> Result<Vec<InstalledSkillPackage>, String> {
        let packages_dir = Self::packages_dir();
        if !packages_dir.exists() {
            return Ok(Vec::new());
        }

        let mut packages = Vec::new();
        for entry in fs::read_dir(&packages_dir)
            .map_err(|e| format!("Failed to read packages directory: {e}"))?
        {
            let entry = entry.map_err(|e| format!("Failed to read package entry: {e}"))?;
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let state_path = path.join("state.json");
            if !state_path.exists() {
                continue;
            }
            let content = fs::read_to_string(&state_path)
                .map_err(|e| format!("Failed to read package state: {e}"))?;
            let state: InstalledSkillPackage = serde_json::from_str(&content)
                .map_err(|e| format!("Failed to parse package state: {e}"))?;
            packages.push(state);
        }

        packages.sort_by(|a, b| a.package_id.cmp(&b.package_id));
        Ok(packages)
    }

    pub fn list_discovered_packages(
        skills_dir: &Path,
    ) -> Result<Vec<InstalledSkillPackage>, String> {
        let mut packages = Self::list_installed_packages()?;
        let existing_ids: HashSet<String> = packages
            .iter()
            .map(|item| item.package_id.clone())
            .collect();

        if skills_dir.exists() {
            for entry in fs::read_dir(skills_dir).map_err(|e| {
                format!("Failed to read skills directory for package discovery: {e}")
            })? {
                let entry =
                    entry.map_err(|e| format!("Failed to read skills directory entry: {e}"))?;
                let path = entry.path();
                if !path.is_dir() {
                    continue;
                }

                let Some(package_id) = path.file_name().and_then(|name| name.to_str()) else {
                    continue;
                };
                if package_id.starts_with('.')
                    || existing_ids.contains(package_id)
                    || is_skill_dir(&path)
                {
                    continue;
                }

                let mut members = Vec::new();
                for child in fs::read_dir(&path)
                    .map_err(|e| format!("Failed to read package container directory: {e}"))?
                {
                    let child =
                        child.map_err(|e| format!("Failed to read package child entry: {e}"))?;
                    let child_path = child.path();
                    if !child_path.is_dir() || !is_skill_dir(&child_path) {
                        continue;
                    }
                    if let Some(member_id) = child_path.file_name().and_then(|name| name.to_str()) {
                        members.push(member_id.to_string());
                    }
                }

                if members.is_empty() {
                    continue;
                }

                members.sort();
                packages.push(InstalledSkillPackage {
                    package_id: package_id.to_string(),
                    name: package_id.to_string(),
                    version: String::new(),
                    installed_members: members.clone(),
                    selected_members: members,
                    path: Some(path.to_string_lossy().into_owned()),
                    manifest_hash: None,
                    installed_at: 0,
                    updated_at: 0,
                });
            }
        }

        packages.sort_by(|a, b| a.package_id.cmp(&b.package_id));
        Ok(packages)
    }

    #[cfg(test)]
    pub fn read_installed_package(package_id: &str) -> Result<InstalledSkillPackage, String> {
        let state_path = Self::package_dir(package_id).join("state.json");
        let content = fs::read_to_string(&state_path)
            .map_err(|e| format!("Failed to read package state: {e}"))?;
        serde_json::from_str(&content).map_err(|e| format!("Failed to parse package state: {e}"))
    }

    pub fn write_installed_package(state: &InstalledSkillPackage) -> Result<(), String> {
        let package_dir = Self::package_dir(&state.package_id);
        fs::create_dir_all(&package_dir)
            .map_err(|e| format!("Failed to create package directory: {e}"))?;
        let content = serde_json::to_string_pretty(state)
            .map_err(|e| format!("Failed to serialize package state: {e}"))?;
        fs::write(package_dir.join("state.json"), content)
            .map_err(|e| format!("Failed to write package state: {e}"))
    }

    pub fn install_from_local_source(
        source_dir: &Path,
        skills_dir: &Path,
    ) -> Result<InstalledSkillPackage, String> {
        let manifest = Self::read_manifest(&source_dir.join("skill-pack.toml"))?;
        fs::create_dir_all(skills_dir).map_err(|e| format!("Failed to create skills dir: {e}"))?;

        let mut installed_members = Vec::with_capacity(manifest.members.len());
        let mut selected_members = Vec::with_capacity(manifest.members.len());

        for member in &manifest.members {
            let source_member_dir = source_dir.join(&member.path);
            if !source_member_dir.is_dir() {
                return Err(format!(
                    "Member source path is not a directory: {}",
                    source_member_dir.display()
                ));
            }

            let target_dir = skills_dir.join(&member.skill_id);
            if target_dir.exists() {
                fs::remove_dir_all(&target_dir)
                    .map_err(|e| format!("Failed to replace materialized member: {e}"))?;
            }

            copy_dir_all(&source_member_dir, &target_dir)?;
            write_member_meta(&target_dir, &manifest, member)?;

            installed_members.push(member.skill_id.clone());
            selected_members.push(member.member_id.clone());
        }

        let now = current_unix_timestamp();
        let state = InstalledSkillPackage {
            package_id: manifest.package_id.clone(),
            name: manifest.name.clone(),
            version: manifest.version.clone(),
            installed_members,
            selected_members,
            path: None,
            manifest_hash: None,
            installed_at: now,
            updated_at: now,
        };
        Self::write_installed_package(&state)?;
        Ok(state)
    }

    pub fn remove_package(package_id: &str, skills_dir: &Path) -> Result<(), String> {
        let package = Self::list_discovered_packages(skills_dir)?
            .into_iter()
            .find(|item| item.package_id == package_id)
            .ok_or_else(|| format!("Skill package not found: {}", package_id))?;

        if package.path.is_some() {
            if let Some(path) = &package.path {
                let group_dir = PathBuf::from(path);
                if group_dir.exists() {
                    fs::remove_dir_all(&group_dir).map_err(|e| {
                        format!("Failed to remove discovered package directory: {e}")
                    })?;
                }
            }
        } else {
            for skill_id in &package.installed_members {
                let target_dir = skills_dir.join(skill_id);
                if target_dir.exists() {
                    fs::remove_dir_all(&target_dir)
                        .map_err(|e| format!("Failed to remove materialized member: {e}"))?;
                }
            }
        }

        let package_dir = Self::package_dir(package_id);
        if package_dir.exists() {
            fs::remove_dir_all(package_dir)
                .map_err(|e| format!("Failed to remove package directory: {e}"))?;
        }

        Ok(())
    }
}

fn copy_dir_all(src: &Path, dst: &Path) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| format!("Failed to create directory: {e}"))?;
    for entry in fs::read_dir(src).map_err(|e| format!("Failed to read directory: {e}"))? {
        let entry = entry.map_err(|e| format!("Failed to read directory entry: {e}"))?;
        let file_type = entry
            .file_type()
            .map_err(|e| format!("Failed to read file type: {e}"))?;
        let target = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_all(&entry.path(), &target)?;
        } else {
            fs::copy(entry.path(), &target).map_err(|e| format!("Failed to copy file: {e}"))?;
        }
    }
    Ok(())
}

fn write_member_meta(
    target_dir: &Path,
    manifest: &SkillPackageManifest,
    member: &SkillPackageMember,
) -> Result<(), String> {
    let meta_path = target_dir.join("meta.json");
    let mut meta: HashMap<String, serde_json::Value> = if meta_path.exists() {
        let content =
            fs::read_to_string(&meta_path).map_err(|e| format!("Failed to read meta.json: {e}"))?;
        serde_json::from_str(&content).unwrap_or_default()
    } else {
        HashMap::new()
    };

    meta.insert(
        "name".to_string(),
        serde_json::Value::String(
            member
                .name
                .clone()
                .unwrap_or_else(|| member.member_id.clone()),
        ),
    );
    meta.insert(
        "version".to_string(),
        serde_json::Value::String(manifest.version.clone()),
    );
    meta.insert(
        "package_id".to_string(),
        serde_json::Value::String(manifest.package_id.clone()),
    );
    meta.insert(
        "package_name".to_string(),
        serde_json::Value::String(manifest.name.clone()),
    );
    meta.insert(
        "package_member_id".to_string(),
        serde_json::Value::String(member.member_id.clone()),
    );
    meta.insert(
        "package_version".to_string(),
        serde_json::Value::String(manifest.version.clone()),
    );

    let content = serde_json::to_string_pretty(&meta)
        .map_err(|e| format!("Failed to serialize member meta.json: {e}"))?;
    fs::write(meta_path, content).map_err(|e| format!("Failed to write meta.json: {e}"))
}

fn current_unix_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0)
}

fn is_skill_dir(path: &Path) -> bool {
    path.join("meta.json").exists()
        || path.join("SKILL.md").exists()
        || path.join("skill.md").exists()
}

#[cfg(test)]
mod tests {
    use super::SkillPackageService;
    use crate::models::skill_package::SkillPackageInstallStrategy;
    use crate::models::{AppConfig, InstalledSkillPackage};
    use crate::services::ScannerService;
    use crate::test_support::with_temp_home;
    use serde_json::Value;
    use std::fs;

    #[test]
    fn list_installed_skill_packages_returns_empty_when_packages_dir_missing() {
        with_temp_home(|_home| {
            let packages =
                SkillPackageService::list_installed_packages().expect("list installed packages");
            assert!(packages.is_empty());
        });
    }

    #[test]
    fn write_and_read_installed_skill_package_round_trip() {
        with_temp_home(|home| {
            let state = InstalledSkillPackage {
                package_id: "superpowers".to_string(),
                name: "Superpowers".to_string(),
                version: "1.0.0".to_string(),
                installed_members: vec!["superpowers--brainstorming".to_string()],
                selected_members: vec!["brainstorming".to_string()],
                path: None,
                manifest_hash: Some("abc123".to_string()),
                installed_at: 1,
                updated_at: 2,
            };

            SkillPackageService::write_installed_package(&state).expect("write installed package");
            let stored = SkillPackageService::read_installed_package("superpowers")
                .expect("read installed package");

            assert_eq!(stored, state);
            assert!(home
                .join(".skills-manager")
                .join("packages")
                .join("superpowers")
                .join("state.json")
                .exists());
        });
    }

    #[test]
    fn parse_manifest_from_file_validates_unique_member_ids() {
        with_temp_home(|home| {
            let manifest_path = home.join("skill-pack.toml");
            fs::write(
                &manifest_path,
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--writing-plans"
path = "skills/writing-plans"
"#,
            )
            .expect("write manifest");

            let err = SkillPackageService::read_manifest(&manifest_path)
                .expect_err("duplicate member ids");
            assert!(err.contains("duplicate member_id"), "{err}");
        });
    }

    #[test]
    fn parse_manifest_from_file_validates_unique_skill_ids() {
        with_temp_home(|home| {
            let manifest_path = home.join("skill-pack.toml");
            fs::write(
                &manifest_path,
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"

[[members]]
member_id = "writing-plans"
skill_id = "superpowers--brainstorming"
path = "skills/writing-plans"
"#,
            )
            .expect("write manifest");

            let err = SkillPackageService::read_manifest(&manifest_path)
                .expect_err("duplicate skill ids");
            assert!(err.contains("duplicate skill_id"), "{err}");
        });
    }

    #[test]
    fn parse_manifest_from_file_reads_members_and_strategy() {
        with_temp_home(|home| {
            let manifest_path = home.join("skill-pack.toml");
            fs::write(
                &manifest_path,
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"
name = "brainstorming"
"#,
            )
            .expect("write manifest");

            let manifest =
                SkillPackageService::read_manifest(&manifest_path).expect("read manifest");
            assert_eq!(manifest.package_id, "superpowers");
            assert_eq!(
                manifest.install_strategy,
                SkillPackageInstallStrategy::MaterializedMembers
            );
            assert_eq!(manifest.members.len(), 1);
            assert_eq!(manifest.members[0].skill_id, "superpowers--brainstorming");
        });
    }

    #[test]
    fn list_discovered_packages_includes_legacy_skill_container_group() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(skills_dir.join("baoyu-skills").join("baoyu-translate"))
                .expect("create translate dir");
            fs::create_dir_all(skills_dir.join("baoyu-skills").join("baoyu-slide-deck"))
                .expect("create slide dir");
            fs::create_dir_all(skills_dir.join("plain-skill")).expect("create plain skill dir");
            fs::write(
                skills_dir
                    .join("baoyu-skills")
                    .join("baoyu-translate")
                    .join("SKILL.md"),
                "---\nname: baoyu-translate\n---\n",
            )
            .expect("write translate skill");
            fs::write(
                skills_dir
                    .join("baoyu-skills")
                    .join("baoyu-slide-deck")
                    .join("SKILL.md"),
                "---\nname: baoyu-slide-deck\n---\n",
            )
            .expect("write slide skill");
            fs::write(
                skills_dir.join("plain-skill").join("SKILL.md"),
                "---\nname: plain-skill\n---\n",
            )
            .expect("write plain skill");

            let packages = SkillPackageService::list_discovered_packages(&skills_dir)
                .expect("list discovered packages");

            assert_eq!(packages.len(), 1);
            assert_eq!(packages[0].package_id, "baoyu-skills");
            assert_eq!(
                packages[0].installed_members,
                vec![
                    "baoyu-slide-deck".to_string(),
                    "baoyu-translate".to_string()
                ]
            );
            assert_eq!(
                packages[0].path.as_deref(),
                Some(skills_dir.join("baoyu-skills").to_string_lossy().as_ref())
            );
        });
    }

    #[test]
    fn install_skill_package_from_local_source_materializes_members() {
        with_temp_home(|home| {
            let source_dir = home.join("source-superpowers");
            fs::create_dir_all(source_dir.join("skills").join("brainstorming"))
                .expect("create brainstorming dir");
            fs::create_dir_all(source_dir.join("skills").join("writing-plans"))
                .expect("create writing plans dir");
            fs::write(
                source_dir.join("skill-pack.toml"),
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"

[[members]]
member_id = "writing-plans"
skill_id = "superpowers--writing-plans"
path = "skills/writing-plans"
"#,
            )
            .expect("write manifest");
            fs::write(
                source_dir
                    .join("skills")
                    .join("brainstorming")
                    .join("SKILL.md"),
                "---\nname: brainstorming\n---\n",
            )
            .expect("write brainstorming skill");
            fs::write(
                source_dir
                    .join("skills")
                    .join("writing-plans")
                    .join("SKILL.md"),
                "---\nname: writing-plans\n---\n",
            )
            .expect("write writing plans skill");

            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills dir");

            let state = SkillPackageService::install_from_local_source(&source_dir, &skills_dir)
                .expect("install package");

            assert_eq!(state.package_id, "superpowers");
            assert_eq!(
                state.installed_members,
                vec![
                    "superpowers--brainstorming".to_string(),
                    "superpowers--writing-plans".to_string()
                ]
            );
            assert!(skills_dir.join("superpowers--brainstorming").exists());
            assert!(skills_dir.join("superpowers--writing-plans").exists());
        });
    }

    #[test]
    fn install_skill_package_writes_package_meta_into_member_meta_json() {
        with_temp_home(|home| {
            let source_dir = home.join("source-superpowers");
            fs::create_dir_all(source_dir.join("skills").join("brainstorming"))
                .expect("create member dir");
            fs::write(
                source_dir.join("skill-pack.toml"),
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"
"#,
            )
            .expect("write manifest");
            fs::write(
                source_dir
                    .join("skills")
                    .join("brainstorming")
                    .join("SKILL.md"),
                "---\nname: brainstorming\n---\n",
            )
            .expect("write skill");

            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills dir");

            SkillPackageService::install_from_local_source(&source_dir, &skills_dir)
                .expect("install package");

            let meta_content = fs::read_to_string(
                skills_dir
                    .join("superpowers--brainstorming")
                    .join("meta.json"),
            )
            .expect("read meta.json");
            let meta: Value = serde_json::from_str(&meta_content).expect("parse meta.json");

            assert_eq!(meta["package_id"], "superpowers");
            assert_eq!(meta["package_member_id"], "brainstorming");
            assert_eq!(meta["package_name"], "Superpowers");
            assert_eq!(meta["package_version"], "1.0.0");
        });
    }

    #[test]
    fn remove_skill_package_removes_materialized_members_only() {
        with_temp_home(|home| {
            let source_dir = home.join("source-superpowers");
            fs::create_dir_all(source_dir.join("skills").join("brainstorming"))
                .expect("create member dir");
            fs::write(
                source_dir.join("skill-pack.toml"),
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"
"#,
            )
            .expect("write manifest");
            fs::write(
                source_dir
                    .join("skills")
                    .join("brainstorming")
                    .join("SKILL.md"),
                "---\nname: brainstorming\n---\n",
            )
            .expect("write skill");

            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(skills_dir.join("plain-skill")).expect("create plain skill dir");
            fs::write(
                skills_dir.join("plain-skill").join("SKILL.md"),
                "---\nname: plain-skill\n---\n",
            )
            .expect("write plain skill");

            SkillPackageService::install_from_local_source(&source_dir, &skills_dir)
                .expect("install package");
            SkillPackageService::remove_package("superpowers", &skills_dir)
                .expect("remove package");

            assert!(!skills_dir.join("superpowers--brainstorming").exists());
            assert!(skills_dir.join("plain-skill").exists());
            assert!(!home
                .join(".skills-manager")
                .join("packages")
                .join("superpowers")
                .exists());
        });
    }

    #[test]
    fn remove_skill_package_removes_discovered_container_group() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let group_dir = skills_dir.join("team-pack");
            let member_dir = group_dir.join("member-a");
            fs::create_dir_all(&member_dir).expect("create member dir");
            fs::write(member_dir.join("SKILL.md"), "---\nname: member-a\n---\n")
                .expect("write member skill");

            SkillPackageService::remove_package("team-pack", &skills_dir)
                .expect("remove discovered group");

            assert!(!group_dir.exists());
        });
    }

    #[test]
    fn scan_skills_lists_materialized_package_members_as_plain_leaf_skills() {
        with_temp_home(|home| {
            let source_dir = home.join("source-superpowers");
            fs::create_dir_all(source_dir.join("skills").join("brainstorming"))
                .expect("create brainstorming dir");
            fs::create_dir_all(source_dir.join("skills").join("writing-plans"))
                .expect("create writing plans dir");
            fs::write(
                source_dir.join("skill-pack.toml"),
                r#"
schema_version = 1
package_id = "superpowers"
name = "Superpowers"
version = "1.0.0"
install_strategy = "materialized_members"

[[members]]
member_id = "brainstorming"
skill_id = "superpowers--brainstorming"
path = "skills/brainstorming"

[[members]]
member_id = "writing-plans"
skill_id = "superpowers--writing-plans"
path = "skills/writing-plans"
"#,
            )
            .expect("write manifest");
            fs::write(
                source_dir
                    .join("skills")
                    .join("brainstorming")
                    .join("SKILL.md"),
                "---\nname: brainstorming\n---\n",
            )
            .expect("write brainstorming skill");
            fs::write(
                source_dir
                    .join("skills")
                    .join("writing-plans")
                    .join("SKILL.md"),
                "---\nname: writing-plans\n---\n",
            )
            .expect("write writing plans skill");

            let skills_dir = home.join(".skills-manager").join("skills");
            fs::create_dir_all(&skills_dir).expect("create skills dir");

            SkillPackageService::install_from_local_source(&source_dir, &skills_dir)
                .expect("install package");

            let config = AppConfig::default();
            let mut scanned =
                ScannerService::scan_skills_with_config(&skills_dir, &config).expect("scan skills");
            scanned.sort_by(|a, b| a.id.cmp(&b.id));
            let ids: Vec<&str> = scanned.iter().map(|skill| skill.id.as_str()).collect();

            assert_eq!(
                ids,
                vec!["superpowers--brainstorming", "superpowers--writing-plans"]
            );
        });
    }
}
