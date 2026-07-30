use crate::models::auth::AuthSession;
use crate::models::marketplace::{MarketplaceSource, SourceType};
use crate::models::RiskScanMode;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserPreferences {
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default = "default_font_family")]
    pub font_family: String,
    #[serde(default = "default_language")]
    pub language: String,
    #[serde(default = "default_true")]
    pub auto_sync: bool,
    #[serde(default = "default_true")]
    pub sync_on_save: bool,
    #[serde(default = "default_editor")]
    pub default_editor: String,
    #[serde(default = "default_tab_size")]
    pub tab_size: u8,
    #[serde(default = "default_true")]
    pub show_sync_notifications: bool,
    #[serde(default = "default_false")]
    pub remove_links_when_disabling_tool: bool,
    #[serde(default = "default_true")]
    pub skill_usage_monitor: bool,
    #[serde(default)]
    pub github_token: Option<String>,
    #[serde(default)]
    pub risk_scan_mode: RiskScanMode,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LlmProvider {
    pub base_url: String,
    pub api_key: String,
    pub model: String,
    #[serde(default)]
    pub temperature: Option<f32>,
    #[serde(default)]
    pub max_tokens: Option<u32>,
    #[serde(default)]
    pub timeout_secs: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct SkillMetadata {
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub favorited_at: Option<i64>,
}

/// 收藏时的市场 skill 快照，断网也能展示基本信息
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketplaceFavoriteMeta {
    pub favorited_at: i64,
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub source_id: String,
    #[serde(default)]
    pub source_name: String,
    #[serde(default)]
    pub repo_url: Option<String>,
    #[serde(default)]
    pub skill_path: Option<String>,
    #[serde(default)]
    pub external_url: Option<String>,
    #[serde(default)]
    pub install_count: Option<u64>,
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub clawhub_slug: Option<String>,
    #[serde(default)]
    pub clawhub_owner: Option<String>,
    #[serde(default)]
    pub clawhub_version: Option<String>,
}

fn default_theme() -> String {
    "system".to_string()
}
fn default_language() -> String {
    "en".to_string()
}
fn default_font_family() -> String {
    "system".to_string()
}
fn default_editor() -> String {
    "builtin".to_string()
}
fn default_tab_size() -> u8 {
    2
}
fn default_true() -> bool {
    true
}
fn default_false() -> bool {
    false
}
fn default_marketplace_sources() -> Vec<MarketplaceSource> {
    vec![MarketplaceSource {
        id: "src_clawhub".to_string(),
        name: "ClawHub".to_string(),
        url: "https://clawhub.ai".to_string(),
        source_type: SourceType::ClawhubApi,
        enabled: true,
        builtin: true,
        api_key: None,
    }]
}

impl Default for UserPreferences {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            font_family: default_font_family(),
            language: default_language(),
            auto_sync: true,
            sync_on_save: true,
            default_editor: default_editor(),
            tab_size: default_tab_size(),
            show_sync_notifications: true,
            remove_links_when_disabling_tool: false,
            skill_usage_monitor: true,
            github_token: None,
            risk_scan_mode: RiskScanMode::Off,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
struct LegacyProjectBinding {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub root_path: Option<PathBuf>,
    #[serde(default)]
    pub skills_dir: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProjectBinding {
    pub id: String,
    pub name: String,
    pub skills_dir: PathBuf,
}

impl TryFrom<LegacyProjectBinding> for ProjectBinding {
    type Error = String;

    fn try_from(value: LegacyProjectBinding) -> Result<Self, Self::Error> {
        let skills_dir = value
            .skills_dir
            .or_else(|| {
                value
                    .root_path
                    .map(|root| root.join(".claude").join("skills"))
            })
            .ok_or_else(|| "missing field `skills_dir`".to_string())?;

        Ok(Self {
            id: value.id,
            name: value.name,
            skills_dir,
        })
    }
}

impl Serialize for ProjectBinding {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        use serde::ser::SerializeStruct;
        let mut state = serializer.serialize_struct("ProjectBinding", 3)?;
        state.serialize_field("id", &self.id)?;
        state.serialize_field("name", &self.name)?;
        state.serialize_field("skills_dir", &self.skills_dir)?;
        state.end()
    }
}

impl<'de> Deserialize<'de> for ProjectBinding {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let legacy = LegacyProjectBinding::deserialize(deserializer)?;
        Self::try_from(legacy).map_err(serde::de::Error::custom)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub version: String,
    pub skills_dir: PathBuf,
    pub tools: HashMap<String, ToolConfig>,
    #[serde(default)]
    pub custom_tools: HashMap<String, CustomToolConfig>,
    #[serde(default)]
    pub skill_metadata: HashMap<String, SkillMetadata>,
    #[serde(default)]
    pub marketplace_favorites: HashMap<String, MarketplaceFavoriteMeta>,
    #[serde(default)]
    pub preferences: Option<UserPreferences>,
    #[serde(default)]
    pub marketplace_sources: Option<Vec<MarketplaceSource>>,
    #[serde(default)]
    pub projects: Vec<ProjectBinding>,
    #[serde(default)]
    pub active_project_id: Option<String>,
    #[serde(default)]
    pub llm_provider: Option<LlmProvider>,
    #[serde(default)]
    pub auth_session: Option<AuthSession>,
    #[serde(default)]
    pub initialized: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CustomToolConfig {
    pub name: String,
    pub config_path: PathBuf,
    pub skills_path: PathBuf,
    #[serde(default)]
    pub enabled: bool,
    #[serde(default)]
    pub icon_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolConfig {
    pub enabled: bool,
    pub detected: bool,
    pub skills_path: PathBuf,
    pub config_path: PathBuf,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            version: "2.1.7".to_string(),
            skills_dir: Self::default_skills_dir(),
            tools: HashMap::new(),
            custom_tools: HashMap::new(),
            skill_metadata: HashMap::new(),
            marketplace_favorites: HashMap::new(),
            preferences: Some(UserPreferences::default()),
            marketplace_sources: Some(default_marketplace_sources()),
            projects: Vec::new(),
            active_project_id: None,
            llm_provider: None,
            auth_session: None,
            initialized: false,
        }
    }
}

impl ToolConfig {
    #[allow(dead_code)]
    pub fn new(skills_path: PathBuf, config_path: PathBuf) -> Self {
        Self {
            enabled: false,
            detected: false,
            skills_path,
            config_path,
        }
    }
}

impl AppConfig {
    pub fn default_skills_dir() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_default()
            .join(".skills-manager")
            .join("skills")
    }

    pub fn get_tool_config(&self, tool_id: &str) -> Option<ToolConfig> {
        if let Some(tool) = self.tools.get(tool_id) {
            return Some(tool.clone());
        }

        self.custom_tools.get(tool_id).map(|custom| {
            let detected = custom.config_path.exists();
            ToolConfig {
                enabled: custom.enabled,
                detected,
                skills_path: custom.skills_path.clone(),
                config_path: custom.config_path.clone(),
            }
        })
    }

    pub fn collect_tool_configs(&self) -> Vec<(String, ToolConfig)> {
        let mut configs: Vec<(String, ToolConfig)> = self
            .tools
            .iter()
            .map(|(id, config)| (id.clone(), config.clone()))
            .collect();

        for (id, custom) in &self.custom_tools {
            let detected = custom.config_path.exists();
            configs.push((
                id.clone(),
                ToolConfig {
                    enabled: custom.enabled,
                    detected,
                    skills_path: custom.skills_path.clone(),
                    config_path: custom.config_path.clone(),
                },
            ));
        }

        configs
    }
}

#[cfg(test)]
mod tests {
    use super::default_marketplace_sources;
    use super::AppConfig;
    use super::SkillMetadata;
    use crate::models::SourceType;
    use std::collections::HashMap;

    #[test]
    fn default_marketplace_sources_matches_remote_source_ids() {
        let sources = default_marketplace_sources();
        assert_eq!(sources.len(), 1);
        assert_eq!(sources[0].id, "src_clawhub");
        assert_eq!(sources[0].source_type, SourceType::ClawhubApi);
    }

    #[test]
    fn font_family_preference_defaults_and_persists() {
        let config = AppConfig::default();
        let value = serde_json::to_value(&config).expect("config should serialize");
        let font_family = value
            .get("preferences")
            .and_then(|prefs| prefs.get("font_family"))
            .and_then(|value| value.as_str());
        assert_eq!(font_family, Some("system"));

        let json = serde_json::to_string(&config).expect("config should serialize");
        let restored: AppConfig = serde_json::from_str(&json).expect("config should deserialize");
        let restored_value =
            serde_json::to_value(&restored).expect("restored config should serialize");
        let restored_font_family = restored_value
            .get("preferences")
            .and_then(|prefs| prefs.get("font_family"))
            .and_then(|value| value.as_str());
        assert_eq!(restored_font_family, Some("system"));
    }

    #[test]
    fn skill_tags_default_to_empty_when_loading_legacy_config() {
        let config_json = r#"{
            "version": "2.0.1",
            "skills_dir": "/tmp/skills",
            "tools": {},
            "custom_tools": {},
            "initialized": true
        }"#;

        let config: AppConfig = serde_json::from_str(config_json).expect("deserialize config");
        assert!(config.skill_metadata.is_empty());
    }

    #[test]
    fn skill_tags_persist_through_config_serialization() {
        let mut config = AppConfig::default();
        let mut metadata = HashMap::new();
        metadata.insert(
            "react-playground".to_string(),
            SkillMetadata {
                tags: vec!["react".to_string(), "frontend".to_string()],
                ..Default::default()
            },
        );
        config.skill_metadata = metadata;

        let json = serde_json::to_string(&config).expect("serialize config");
        let restored: AppConfig = serde_json::from_str(&json).expect("deserialize config");

        assert_eq!(
            restored.skill_metadata.get("react-playground"),
            Some(&SkillMetadata {
                tags: vec!["react".to_string(), "frontend".to_string()],
                ..Default::default()
            })
        );
    }

    #[test]
    fn llm_provider_defaults_to_none() {
        let config = AppConfig::default();
        assert!(config.llm_provider.is_none());
    }

    #[test]
    fn llm_provider_persists_through_serialization() {
        let mut config = AppConfig::default();
        config.llm_provider = Some(super::LlmProvider {
            base_url: "https://api.openai.com/v1".to_string(),
            api_key: "sk-test".to_string(),
            model: "gpt-4o-mini".to_string(),
            temperature: Some(0.3),
            max_tokens: Some(4096),
            timeout_secs: Some(60),
        });

        let json = serde_json::to_string(&config).expect("serialize config");
        let restored: AppConfig = serde_json::from_str(&json).expect("deserialize config");

        let provider = restored.llm_provider.expect("llm provider restored");
        assert_eq!(provider.base_url, "https://api.openai.com/v1");
        assert_eq!(provider.api_key, "sk-test");
        assert_eq!(provider.model, "gpt-4o-mini");
        assert_eq!(provider.temperature, Some(0.3));
        assert_eq!(provider.max_tokens, Some(4096));
        assert_eq!(provider.timeout_secs, Some(60));
    }

    #[test]
    fn llm_provider_loads_from_legacy_config_without_field() {
        let config_json = r#"{
            "version": "2.0.1",
            "skills_dir": "/tmp/skills",
            "tools": {},
            "custom_tools": {},
            "initialized": true
        }"#;
        let config: AppConfig = serde_json::from_str(config_json).expect("deserialize");
        assert!(config.llm_provider.is_none());
    }
}
