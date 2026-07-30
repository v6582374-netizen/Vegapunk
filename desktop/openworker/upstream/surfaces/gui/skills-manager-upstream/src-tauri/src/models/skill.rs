use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

use crate::models::SkillPackageMeta;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Skill {
    pub id: String,
    pub instance_id: String,
    pub scope: SkillScope,
    pub project_id: Option<String>,
    pub project_name: Option<String>,
    pub name: String,
    pub description: Option<String>,
    pub version: String,
    pub source: SkillSource,
    pub marketplace_meta: Option<MarketplaceMeta>,
    pub vault_meta: Option<VaultMeta>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub package_meta: Option<SkillPackageMeta>,
    pub enabled: HashMap<String, bool>,
    pub path: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum SkillScope {
    Global,
    Project,
}

impl Default for SkillScope {
    fn default() -> Self {
        Self::Global
    }
}

impl Skill {
    pub fn global_instance_id(id: &str) -> String {
        format!("global:{}", id)
    }

    pub fn project_instance_id(project_id: &str, id: &str) -> String {
        format!("project:{}:{}", project_id, id)
    }
}

impl Skill {
    pub fn with_scope(
        mut self,
        scope: SkillScope,
        project_id: Option<String>,
        project_name: Option<String>,
    ) -> Self {
        self.scope = scope;
        self.project_id = project_id;
        self.project_name = project_name;
        self.instance_id = match (&self.scope, &self.project_id) {
            (SkillScope::Global, _) => Self::global_instance_id(&self.id),
            (SkillScope::Project, Some(project_id)) => {
                Self::project_instance_id(project_id, &self.id)
            }
            (SkillScope::Project, None) => {
                panic!("project_id is required for project-scoped skills")
            }
        };
        self
    }
}

impl Skill {
    #[cfg(test)]
    pub fn new(id: String, name: String, path: PathBuf) -> Self {
        Self {
            instance_id: Skill::global_instance_id(&id),
            scope: SkillScope::Global,
            project_id: None,
            project_name: None,
            id,
            name,
            description: None,
            version: "1.0".to_string(),
            source: SkillSource::Local,
            marketplace_meta: None,
            vault_meta: None,
            package_meta: None,
            enabled: HashMap::new(),
            path,
        }
    }

    pub fn is_enabled_for(&self, tool_id: &str) -> bool {
        self.enabled.get(tool_id).copied().unwrap_or(false)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketplaceMeta {
    pub marketplace_source_id: Option<String>,
    pub marketplace_skill_id: Option<String>,
    pub marketplace_skill_slug: Option<String>,
    pub repo_url: Option<String>,
    pub skill_path: Option<String>,
    pub remote_revision: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct VaultMeta {
    pub provider: Option<String>,
    pub user_id: Option<String>,
    pub skill_id: Option<String>,
    pub version: Option<String>,
    pub hash: Option<String>,
    pub size: Option<u64>,
    pub updated_at: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum SkillSource {
    Local,
    Imported,
    Marketplace,
    Vault,
}
