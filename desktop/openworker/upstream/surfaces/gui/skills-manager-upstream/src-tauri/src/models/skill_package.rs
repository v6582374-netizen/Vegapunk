use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SkillPackageInstallStrategy {
    MaterializedMembers,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SkillPackageMember {
    pub member_id: String,
    pub skill_id: String,
    pub path: String,
    pub name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SkillPackageManifest {
    pub schema_version: u32,
    pub package_id: String,
    pub name: String,
    pub version: String,
    pub install_strategy: SkillPackageInstallStrategy,
    #[serde(default)]
    pub members: Vec<SkillPackageMember>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SkillPackageMeta {
    pub package_id: String,
    pub package_name: Option<String>,
    pub package_member_id: String,
    pub package_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct InstalledSkillPackage {
    pub package_id: String,
    pub name: String,
    pub version: String,
    pub installed_members: Vec<String>,
    pub selected_members: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    pub manifest_hash: Option<String>,
    pub installed_at: i64,
    pub updated_at: i64,
}
