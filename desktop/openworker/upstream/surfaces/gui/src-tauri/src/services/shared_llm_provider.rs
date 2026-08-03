use crate::models::LlmProvider;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use std::collections::HashMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Default, Deserialize)]
struct DesktopPreferences {
    #[serde(default)]
    default_model: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize)]
struct DesktopProviderProfile {
    #[serde(default)]
    api_key: Option<String>,
    #[serde(default)]
    base_url: Option<String>,
}

type DesktopSecrets = HashMap<String, DesktopProviderProfile>;

/// Resolve the same state directory used by coworker.secrets.state_dir().
pub fn state_dir() -> PathBuf {
    if let Ok(path) = env::var("COWORKER_STATE_DIR") {
        return expand_user(PathBuf::from(path));
    }

    #[cfg(windows)]
    if let Ok(appdata) = env::var("APPDATA") {
        return PathBuf::from(appdata).join("coworker");
    }

    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".config")
        .join("coworker")
}

fn expand_user(path: PathBuf) -> PathBuf {
    let Some(raw) = path.to_str() else {
        return path;
    };
    let Some(rest) = raw.strip_prefix('~') else {
        return path;
    };
    let Some(home) = dirs::home_dir() else {
        return path;
    };
    home.join(rest.trim_start_matches(['/', '\\']))
}

fn read_json_if_present<T: DeserializeOwned>(path: &Path) -> Result<Option<T>, String> {
    let content = match fs::read_to_string(path) {
        Ok(content) => content,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(format!("Failed to read {}: {error}", path.display())),
    };

    serde_json::from_str(&content)
        .map(Some)
        .map_err(|error| format!("Failed to parse {}: {error}", path.display()))
}

fn resolve_value(value: &str, dotenv: &HashMap<String, String>) -> String {
    let mut resolved = String::with_capacity(value.len());
    let mut remainder = value;

    loop {
        let Some(start) = remainder.find('$') else {
            resolved.push_str(remainder);
            break;
        };
        resolved.push_str(&remainder[..start]);

        let after_dollar = &remainder[start + 1..];
        if !after_dollar.starts_with('{') {
            resolved.push('$');
            remainder = after_dollar;
            continue;
        }
        let after_start = &after_dollar[1..];
        let Some(end) = after_start.find('}') else {
            resolved.push('$');
            resolved.push('{');
            resolved.push_str(after_start);
            break;
        };

        let name = &after_start[..end];
        let replacement = env::var(name)
            .ok()
            .or_else(|| dotenv.get(name).cloned())
            .unwrap_or_else(|| format!("{}{}{}{}", '$', '{', name, '}'));
        resolved.push_str(&replacement);
        remainder = &after_start[end + 1..];
    }

    resolved
}

fn load_dotenv(path: &Path) -> HashMap<String, String> {
    let Ok(content) = fs::read_to_string(path) else {
        return HashMap::new();
    };

    content
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                return None;
            }
            let (key, value) = line.split_once('=')?;
            Some((
                key.trim().to_string(),
                value.trim().trim_matches(['"', '\'']).to_string(),
            ))
        })
        .collect()
}

fn provider_from_model<'a>(model: &'a str, secrets: &DesktopSecrets) -> (&'a str, &'a str) {
    let trimmed = model.trim();
    let Some((candidate, bare_model)) = trimmed.split_once(':') else {
        return ("openai", trimmed);
    };

    let candidate = candidate.trim();
    let bare_model = bare_model.trim();
    if candidate.is_empty() || bare_model.is_empty() {
        return ("openai", trimmed);
    }

    let profile_key = format!("provider:{candidate}");
    if secrets.contains_key(&profile_key) || known_provider(candidate) {
        (candidate, bare_model)
    } else {
        ("openai", trimmed)
    }
}

fn known_provider(name: &str) -> bool {
    matches!(
        name,
        "openai"
            | "anthropic"
            | "gemini"
            | "bedrock"
            | "vertex"
            | "zai"
            | "deepseek"
            | "kimi"
            | "minimax"
            | "qwen"
            | "xai"
            | "mistral"
            | "meta"
            | "together"
            | "fireworks"
            | "openrouter"
            | "ollama"
            | "relay"
    )
}

fn default_base_url(provider: &str) -> Option<&'static str> {
    match provider {
        "openai" => Some("https://api.openai.com/v1"),
        "zai" => Some("https://api.z.ai/api/paas/v4"),
        "deepseek" => Some("https://api.deepseek.com"),
        "kimi" => Some("https://api.moonshot.ai/v1"),
        "minimax" => Some("https://api.minimax.io/v1"),
        "qwen" => Some("https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        "xai" => Some("https://api.x.ai/v1"),
        "mistral" => Some("https://api.mistral.ai/v1"),
        "meta" => Some("https://api.meta.ai/v1"),
        "together" => Some("https://api.together.xyz/v1"),
        "fireworks" => Some("https://api.fireworks.ai/inference/v1"),
        "openrouter" => Some("https://openrouter.ai/api/v1"),
        "ollama" => Some("http://localhost:11434/v1"),
        _ => None,
    }
}

fn env_key(provider: &str) -> Option<&'static str> {
    match provider {
        "openai" => Some("OPENAI_API_KEY"),
        "anthropic" => Some("ANTHROPIC_API_KEY"),
        "gemini" => Some("GEMINI_API_KEY"),
        "relay" => Some("RELAY_API_KEY"),
        "zai" => Some("ZAI_API_KEY"),
        "deepseek" => Some("DEEPSEEK_API_KEY"),
        "kimi" => Some("MOONSHOT_API_KEY"),
        "minimax" => Some("MINIMAX_API_KEY"),
        "qwen" => Some("DASHSCOPE_API_KEY"),
        "xai" => Some("XAI_API_KEY"),
        "mistral" => Some("MISTRAL_API_KEY"),
        "meta" => Some("META_API_KEY"),
        "together" => Some("TOGETHER_API_KEY"),
        "fireworks" => Some("FIREWORKS_API_KEY"),
        "openrouter" => Some("OPENROUTER_API_KEY"),
        _ => None,
    }
}

fn normalize_ollama_url(url: &str) -> String {
    let trimmed = url.trim().trim_end_matches('/');
    if trimmed.ends_with("/v1") {
        trimmed.to_string()
    } else {
        format!("{trimmed}/v1")
    }
}

/// Load the Desktop app's current default model and its provider credentials.
///
/// The returned provider stays inside the Rust process. Frontend callers that only need to
/// display capability state should use is_llm_provider_configured instead.
pub fn load_provider() -> Result<Option<LlmProvider>, String> {
    let directory = state_dir();
    let prefs: DesktopPreferences = match read_json_if_present(&directory.join("prefs.json"))? {
        Some(prefs) => prefs,
        None => return Ok(None),
    };
    let model = prefs
        .default_model
        .as_deref()
        .map(str::trim)
        .filter(|model| !model.is_empty());
    let Some(model) = model else {
        return Ok(None);
    };

    let secrets: DesktopSecrets =
        read_json_if_present(&directory.join("secrets.json"))?.unwrap_or_default();
    let dotenv = load_dotenv(&directory.join(".env"));
    let (provider_name, model_name) = provider_from_model(model, &secrets);
    let profile = secrets
        .get(&format!("provider:{provider_name}"))
        .cloned()
        .unwrap_or_default();

    let api_key = profile
        .api_key
        .as_deref()
        .map(|value| resolve_value(value.trim(), &dotenv))
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            env_key(provider_name)
                .and_then(|key| env::var(key).ok())
                .filter(|value| !value.trim().is_empty())
        })
        .or_else(|| (provider_name == "ollama").then(|| "ollama".to_string()));

    let Some(api_key) = api_key else {
        return Ok(None);
    };

    let base_url = profile
        .base_url
        .as_deref()
        .map(|value| resolve_value(value.trim(), &dotenv))
        .filter(|value| !value.trim().is_empty())
        .or_else(|| default_base_url(provider_name).map(str::to_string));
    let Some(mut base_url) = base_url else {
        return Ok(None);
    };

    if provider_name == "ollama" {
        base_url = normalize_ollama_url(&base_url);
    }

    Ok(Some(LlmProvider {
        base_url,
        api_key,
        model: model_name.to_string(),
        temperature: None,
        max_tokens: None,
        timeout_secs: Some(120),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::with_temp_home;
    use std::fs;

    #[test]
    fn resolves_desktop_provider_and_strips_model_prefix() {
        with_temp_home(|home| {
            let directory = home.join(".config/coworker");
            fs::create_dir_all(&directory).unwrap();
            fs::write(
                directory.join("prefs.json"),
                r#"{"default_model":"deepseek:deepseek-v4-flash"}"#,
            )
            .unwrap();
            fs::write(
                directory.join("secrets.json"),
                r#"{"provider:deepseek":{"api_key":"key","base_url":"https://api.deepseek.com"}}"#,
            )
            .unwrap();

            let provider = load_provider().unwrap().unwrap();
            assert_eq!(provider.model, "deepseek-v4-flash");
            assert_eq!(provider.base_url, "https://api.deepseek.com");
            assert_eq!(provider.api_key, "key");
            assert_eq!(provider.timeout_secs, Some(120));
        });
    }

    #[test]
    fn resolves_ollama_base_url_and_keyless_profile() {
        with_temp_home(|home| {
            let directory = home.join(".config/coworker");
            fs::create_dir_all(&directory).unwrap();
            fs::write(
                directory.join("prefs.json"),
                r#"{"default_model":"ollama:qwen3-coder:30b"}"#,
            )
            .unwrap();
            fs::write(
                directory.join("secrets.json"),
                r#"{"provider:ollama":{"base_url":"http://localhost:11434"}}"#,
            )
            .unwrap();

            let provider = load_provider().unwrap().unwrap();
            assert_eq!(provider.model, "qwen3-coder:30b");
            assert_eq!(provider.base_url, "http://localhost:11434/v1");
            assert_eq!(provider.api_key, "ollama");
        });
    }

    #[test]
    fn missing_credentials_are_not_configured() {
        with_temp_home(|home| {
            let directory = home.join(".config/coworker");
            fs::create_dir_all(&directory).unwrap();
            fs::write(
                directory.join("prefs.json"),
                r#"{"default_model":"deepseek:deepseek-v4-flash"}"#,
            )
            .unwrap();
            fs::write(directory.join("secrets.json"), "{}").unwrap();

            assert!(load_provider().unwrap().is_none());
        });
    }
}
