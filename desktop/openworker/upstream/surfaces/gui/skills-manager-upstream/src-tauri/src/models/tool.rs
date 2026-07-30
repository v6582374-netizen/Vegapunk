use super::config::ToolConfig;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ToolSource {
    Builtin,
    Custom,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Tool {
    pub id: String,
    pub name: String,
    pub detected: bool,
    pub cli_available: bool,
    pub config: ToolConfig,
    pub source: ToolSource,
    #[serde(default)]
    pub icon_path: Option<PathBuf>,
}

impl Tool {
    #[allow(dead_code)]
    pub fn new(id: String, name: String, config: ToolConfig) -> Self {
        Self {
            id,
            name,
            detected: false,
            cli_available: false,
            config,
            source: ToolSource::Builtin,
            icon_path: None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct ToolDefinition {
    pub id: &'static str,
    pub name: &'static str,
    pub config_dir: &'static str,
    pub alt_config_dirs: &'static [&'static str],
    pub cli_command: &'static str,
}

pub const SUPPORTED_TOOLS: &[ToolDefinition] = &[
    ToolDefinition {
        id: "claude-code",
        name: "Claude Code",
        config_dir: ".claude",
        alt_config_dirs: &[],
        cli_command: "claude",
    },
    ToolDefinition {
        id: "codex",
        name: "Codex",
        config_dir: ".codex",
        alt_config_dirs: &[],
        cli_command: "codex",
    },
    ToolDefinition {
        id: "codebuddy",
        name: "CodeBuddy",
        config_dir: ".codebuddy",
        alt_config_dirs: &[],
        cli_command: "codebuddy",
    },
    ToolDefinition {
        id: "opencode",
        name: "OpenCode",
        config_dir: ".config/opencode",
        alt_config_dirs: &[".opencode"],
        cli_command: "opencode",
    },
    ToolDefinition {
        id: "cursor",
        name: "Cursor",
        config_dir: ".cursor",
        alt_config_dirs: &[],
        cli_command: "cursor",
    },
    ToolDefinition {
        id: "gemini",
        name: "Gemini CLI",
        config_dir: ".gemini",
        alt_config_dirs: &[],
        cli_command: "gemini",
    },
    ToolDefinition {
        id: "antigravity",
        name: "Antigravity",
        config_dir: ".antigravity",
        alt_config_dirs: &[],
        cli_command: "antigravity",
    },
    ToolDefinition {
        id: "windsurf",
        name: "Windsurf",
        config_dir: ".windsurf",
        alt_config_dirs: &[],
        cli_command: "windsurf",
    },
    ToolDefinition {
        id: "trae",
        name: "Trae",
        config_dir: ".trae",
        alt_config_dirs: &[],
        cli_command: "trae",
    },
    ToolDefinition {
        id: "droid",
        name: "Droid",
        config_dir: ".factory",
        alt_config_dirs: &[".droid"],
        cli_command: "droid",
    },
    ToolDefinition {
        id: "augment",
        name: "Augment",
        config_dir: ".augment",
        alt_config_dirs: &[],
        cli_command: "augment",
    },
    ToolDefinition {
        id: "openclaw",
        name: "OpenClaw",
        config_dir: ".openclaw",
        alt_config_dirs: &[],
        cli_command: "openclaw",
    },
    ToolDefinition {
        id: "cline",
        name: "Cline",
        config_dir: ".cline",
        alt_config_dirs: &[],
        cli_command: "cline",
    },
    ToolDefinition {
        id: "vercel-skills",
        name: "Vercel Skills",
        config_dir: ".agents",
        alt_config_dirs: &[".vercel", ".vercel-skills"],
        cli_command: "vercel",
    },
    ToolDefinition {
        id: "commandcode",
        name: "CommandCode",
        config_dir: ".commandcode",
        alt_config_dirs: &[],
        cli_command: "commandcode",
    },
    ToolDefinition {
        id: "continue",
        name: "Continue",
        config_dir: ".continue",
        alt_config_dirs: &[],
        cli_command: "continue",
    },
    ToolDefinition {
        id: "crush",
        name: "Crush",
        config_dir: ".config/crush",
        alt_config_dirs: &[".crush"],
        cli_command: "crush",
    },
    ToolDefinition {
        id: "goose",
        name: "Goose",
        config_dir: ".config/goose",
        alt_config_dirs: &[".goose"],
        cli_command: "goose",
    },
    ToolDefinition {
        id: "iflow",
        name: "iFlow",
        config_dir: ".iflow",
        alt_config_dirs: &[],
        cli_command: "iflow",
    },
    ToolDefinition {
        id: "junie",
        name: "Junie",
        config_dir: ".junie",
        alt_config_dirs: &[],
        cli_command: "junie",
    },
    ToolDefinition {
        id: "kilo-code",
        name: "Kilo Code",
        config_dir: ".kilocode",
        alt_config_dirs: &[],
        cli_command: "kilo",
    },
    ToolDefinition {
        id: "kiro",
        name: "Kiro",
        config_dir: ".kiro",
        alt_config_dirs: &[],
        cli_command: "kiro",
    },
    ToolDefinition {
        id: "qoder",
        name: "Qoder",
        config_dir: ".qoder",
        alt_config_dirs: &[],
        cli_command: "qoder",
    },
    ToolDefinition {
        id: "qwen-code",
        name: "Qwen Code",
        config_dir: ".qwen",
        alt_config_dirs: &[],
        cli_command: "qwen",
    },
    ToolDefinition {
        id: "roo-code",
        name: "Roo Code",
        config_dir: ".roo",
        alt_config_dirs: &[],
        cli_command: "roo",
    },
    ToolDefinition {
        id: "zencoder",
        name: "Zencoder",
        config_dir: ".zencoder",
        alt_config_dirs: &[],
        cli_command: "zencoder",
    },
    ToolDefinition {
        id: "pi",
        name: "Pi",
        config_dir: ".pi/agent",
        alt_config_dirs: &[],
        cli_command: "pi",
    },
    ToolDefinition {
        id: "trae-cn",
        name: "Trae CN",
        config_dir: ".trae-cn",
        alt_config_dirs: &[],
        cli_command: "trae",
    },
    ToolDefinition {
        id: "hermes",
        name: "Hermes",
        config_dir: ".hermes",
        alt_config_dirs: &[],
        cli_command: "hermes",
    },
    ToolDefinition {
        id: "workbuddy",
        name: "WorkBuddy",
        config_dir: ".workbuddy",
        alt_config_dirs: &[],
        cli_command: "workbuddy",
    },
    ToolDefinition {
        id: "qoderwork-cn",
        name: "QoderWork CN",
        config_dir: ".qoderworkcn",
        alt_config_dirs: &[],
        cli_command: "qoderworkcn",
    },
];

#[cfg(test)]
mod tests {
    use super::SUPPORTED_TOOLS;

    #[test]
    fn supported_tools_include_recent_builtins() {
        let ids: Vec<&str> = SUPPORTED_TOOLS.iter().map(|tool| tool.id).collect();

        assert!(ids.contains(&"droid"));
        assert!(ids.contains(&"augment"));
        assert!(ids.contains(&"openclaw"));
        assert!(ids.contains(&"cline"));
        assert!(ids.contains(&"vercel-skills"));
        assert!(ids.contains(&"commandcode"));
        assert!(ids.contains(&"continue"));
        assert!(ids.contains(&"crush"));
        assert!(ids.contains(&"goose"));
        assert!(ids.contains(&"iflow"));
        assert!(ids.contains(&"junie"));
        assert!(ids.contains(&"kilo-code"));
        assert!(ids.contains(&"kiro"));
        assert!(ids.contains(&"qoder"));
        assert!(ids.contains(&"qwen-code"));
        assert!(ids.contains(&"roo-code"));
        assert!(ids.contains(&"zencoder"));
        assert!(ids.contains(&"pi"));
        assert!(ids.contains(&"trae-cn"));
        assert!(ids.contains(&"hermes"));
        assert!(ids.contains(&"workbuddy"));
        assert!(ids.contains(&"qoderwork-cn"));
    }

    #[test]
    fn droid_and_vercel_skills_use_expected_base_directories() {
        let droid = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "droid")
            .expect("droid should exist in supported tools");
        let vercel_skills = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "vercel-skills")
            .expect("vercel-skills should exist in supported tools");

        assert_eq!(droid.config_dir, ".factory");
        assert_eq!(vercel_skills.config_dir, ".agents");
    }

    #[test]
    fn newly_added_tools_use_expected_base_directories() {
        let commandcode = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "commandcode")
            .expect("commandcode should exist in supported tools");
        let continue_tool = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "continue")
            .expect("continue should exist in supported tools");
        let crush = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "crush")
            .expect("crush should exist in supported tools");
        let goose = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "goose")
            .expect("goose should exist in supported tools");
        let iflow = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "iflow")
            .expect("iflow should exist in supported tools");

        assert_eq!(commandcode.config_dir, ".commandcode");
        assert_eq!(continue_tool.config_dir, ".continue");
        assert_eq!(crush.config_dir, ".config/crush");
        assert_eq!(goose.config_dir, ".config/goose");
        assert_eq!(iflow.config_dir, ".iflow");
    }

    #[test]
    fn newly_added_tools_batch_two_use_expected_base_directories() {
        let junie = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "junie")
            .expect("junie should exist in supported tools");
        let kilo_code = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "kilo-code")
            .expect("kilo-code should exist in supported tools");
        let kiro = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "kiro")
            .expect("kiro should exist in supported tools");
        let qoder = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "qoder")
            .expect("qoder should exist in supported tools");
        let qwen_code = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "qwen-code")
            .expect("qwen-code should exist in supported tools");
        let roo_code = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "roo-code")
            .expect("roo-code should exist in supported tools");
        let zencoder = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "zencoder")
            .expect("zencoder should exist in supported tools");
        let pi = SUPPORTED_TOOLS
            .iter()
            .find(|tool| tool.id == "pi")
            .expect("pi should exist in supported tools");

        assert_eq!(junie.config_dir, ".junie");
        assert_eq!(kilo_code.config_dir, ".kilocode");
        assert_eq!(kiro.config_dir, ".kiro");
        assert_eq!(qoder.config_dir, ".qoder");
        assert_eq!(qwen_code.config_dir, ".qwen");
        assert_eq!(roo_code.config_dir, ".roo");
        assert_eq!(zencoder.config_dir, ".zencoder");
        assert_eq!(pi.config_dir, ".pi/agent");
    }
}
