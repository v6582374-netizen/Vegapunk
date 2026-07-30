use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct MarketplaceSource {
    pub id: String,
    pub name: String,
    pub url: String,
    pub source_type: SourceType,
    pub enabled: bool,
    pub builtin: bool,
    pub api_key: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SourceType {
    GithubRepo,
    Api,
    Crawler,
    Manual,
    ClawhubApi,
    #[serde(other)]
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketplaceSkill {
    pub id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub slug: Option<String>,
    pub name: String,
    pub description: Option<String>,
    pub author: Option<String>,
    pub source_id: String,
    pub source_name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub install_count: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub install_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub created_at: Option<u64>,
    pub repo_url: Option<String>,
    pub skill_path: Option<String>,
    pub external_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remote_revision: Option<String>,
    pub tags: Vec<String>,
    pub install_status: InstallStatus,
    // clawhub.ai 专用字段：clawhub 源的 skill 用 slug+owner+version 定位与下载
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clawhub_slug: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clawhub_owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clawhub_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketplaceSkillsResponse {
    pub skills: Vec<MarketplaceSkill>,
    pub has_more: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum InstallStatus {
    NotInstalled,
    Installed,
    UpdateAvailable,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillFileNode {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub download_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sha: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub children: Option<Vec<SkillFileNode>>,
}

/// fetch_clawhub_skill_files 的返回结构。
/// 除文件树外，还携带从详情端点解析出的 owner/version，
/// 供前端补全 skill 元数据并构造正确的外部链接。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClawhubSkillFilesResponse {
    pub tree: SkillFileNode,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resolved_owner: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub resolved_version: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallResult {
    pub success: bool,
    pub skill_id: String,
    pub message: Option<String>,
    pub installed_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketplaceSyncResult {
    pub checked: usize,
    pub updated: usize,
    pub failed: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketplaceUpdateCheckResult {
    pub performed: bool,
    pub checked: usize,
    pub update_available: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitHubContent {
    pub name: String,
    pub path: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub download_url: Option<String>,
    pub url: Option<String>,
    pub size: Option<u64>,
}

#[cfg(test)]
mod tests {
    use super::SourceType;

    #[test]
    fn source_type_deserialize_unknown_value_to_unknown_variant() {
        let value: SourceType =
            serde_json::from_str("\"legacy_provider\"").expect("should deserialize");
        assert_eq!(value, SourceType::Unknown);
    }
}
