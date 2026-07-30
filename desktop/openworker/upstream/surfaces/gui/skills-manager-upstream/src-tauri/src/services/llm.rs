use crate::models::LlmProvider;
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use std::time::Duration;

const DEFAULT_TEMPERATURE: f32 = 0.3;

#[derive(Debug, Clone, Serialize)]
pub struct ChatMessage {
    pub role: &'static str,
    pub content: String,
}

#[derive(Debug, Clone)]
pub struct ChatRequest {
    pub messages: Vec<ChatMessage>,
    pub json_mode: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case", tag = "kind", content = "info")]
pub enum LlmError {
    NotConfigured,
    BadBaseUrl,
    NetworkError(String),
    Unauthorized,
    RateLimited,
    ServerError { status: u16, body: String },
    Timeout,
    ParseError(String),
    ContentTooLarge,
}

impl std::fmt::Display for LlmError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LlmError::NotConfigured => write!(f, "LLM provider not configured"),
            LlmError::BadBaseUrl => write!(f, "Invalid base URL"),
            LlmError::NetworkError(msg) => write!(f, "Network error: {msg}"),
            LlmError::Unauthorized => write!(f, "Invalid API key"),
            LlmError::RateLimited => write!(f, "Rate limit exceeded"),
            LlmError::ServerError { status, body } => {
                write!(f, "Server error {status}: {body}")
            }
            LlmError::Timeout => write!(f, "Request timed out"),
            LlmError::ParseError(msg) => write!(f, "Bad response format: {msg}"),
            LlmError::ContentTooLarge => write!(f, "Content too large"),
        }
    }
}

impl std::error::Error for LlmError {}

fn normalize_base_url(url: &str) -> Result<String, LlmError> {
    let trimmed = url.trim();
    if trimmed.is_empty() {
        return Err(LlmError::BadBaseUrl);
    }
    if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
        return Err(LlmError::BadBaseUrl);
    }
    Ok(trimmed.trim_end_matches('/').to_string())
}

#[derive(Serialize)]
struct ChatRequestBody<'a> {
    model: &'a str,
    messages: Vec<ChatMessageBody<'a>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_tokens: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_format: Option<ResponseFormat>,
    stream: bool,
}

#[derive(Serialize)]
struct ChatMessageBody<'a> {
    role: &'a str,
    content: &'a str,
}

#[derive(Serialize)]
struct ResponseFormat {
    #[serde(rename = "type")]
    fmt_type: &'static str,
}

#[derive(Deserialize)]
struct StreamChunk {
    choices: Vec<StreamChoice>,
}

#[derive(Deserialize)]
struct StreamChoice {
    #[serde(default)]
    delta: StreamDelta,
}

#[derive(Deserialize, Default)]
struct StreamDelta {
    #[serde(default)]
    content: Option<String>,
}

pub async fn chat(provider: &LlmProvider, req: ChatRequest) -> Result<String, LlmError> {
    let base = normalize_base_url(&provider.base_url)?;
    let url = format!("{base}/chat/completions");

    let mut builder = reqwest::Client::builder();
    // 默认 60s 超时，防止流式响应不结束导致永久阻塞
    let timeout_secs = provider.timeout_secs.unwrap_or(60);
    builder = builder.timeout(Duration::from_secs(timeout_secs as u64));
    let client = builder
        .build()
        .map_err(|e| LlmError::NetworkError(e.to_string()))?;

    let body = ChatRequestBody {
        model: &provider.model,
        messages: req
            .messages
            .iter()
            .map(|m| ChatMessageBody {
                role: m.role,
                content: &m.content,
            })
            .collect(),
        temperature: Some(provider.temperature.unwrap_or(DEFAULT_TEMPERATURE)),
        max_tokens: provider.max_tokens,
        response_format: req.json_mode.then(|| ResponseFormat {
            fmt_type: "json_object",
        }),
        stream: true,
    };

    let response = client
        .post(&url)
        .header(CONTENT_TYPE, "application/json")
        .header(AUTHORIZATION, format!("Bearer {}", provider.api_key))
        .json(&body)
        .send()
        .await
        .map_err(|e| {
            if e.is_timeout() {
                LlmError::Timeout
            } else {
                LlmError::NetworkError(e.to_string())
            }
        })?;

    let status = response.status();
    if !status.is_success() {
        let text = response.text().await.unwrap_or_default();
        return Err(match status {
            StatusCode::UNAUTHORIZED | StatusCode::FORBIDDEN => LlmError::Unauthorized,
            StatusCode::TOO_MANY_REQUESTS => LlmError::RateLimited,
            s if s.is_server_error() => LlmError::ServerError {
                status: s.as_u16(),
                body: text,
            },
            s => LlmError::ServerError {
                status: s.as_u16(),
                body: text,
            },
        });
    }

    use futures_util::StreamExt;
    let mut stream = response.bytes_stream();
    let mut byte_buf: Vec<u8> = Vec::new();
    let mut buffer = String::new();
    let mut full = String::new();

    while let Some(chunk) = stream.next().await {
        let bytes = chunk.map_err(|e| LlmError::NetworkError(e.to_string()))?;
        byte_buf.extend_from_slice(&bytes);

        let valid_up_to = match std::str::from_utf8(&byte_buf) {
            Ok(_) => byte_buf.len(),
            Err(e) => e.valid_up_to(),
        };
        if valid_up_to > 0 {
            let valid = std::str::from_utf8(&byte_buf[..valid_up_to])
                .expect("valid_up_to bytes are valid utf-8");
            for ch in valid.chars() {
                if ch != '\r' {
                    buffer.push(ch);
                }
            }
            byte_buf.drain(..valid_up_to);
        }

        while let Some(idx) = buffer.find("\n\n") {
            let event: String = buffer.drain(..idx + 2).collect();
            for line in event.lines() {
                let data = match line.strip_prefix("data:") {
                    Some(d) => d.trim(),
                    None => continue,
                };
                if data.is_empty() {
                    continue;
                }
                if data == "[DONE]" {
                    return Ok(full);
                }
                if let Ok(parsed) = serde_json::from_str::<StreamChunk>(data) {
                    if let Some(choice) = parsed.choices.into_iter().next() {
                        if let Some(content) = choice.delta.content {
                            full.push_str(&content);
                        }
                    }
                }
            }
        }
    }

    if full.is_empty() {
        return Err(LlmError::ParseError("empty stream response".to_string()));
    }
    Ok(full)
}

pub async fn test_connection(provider: &LlmProvider) -> Result<String, LlmError> {
    let req = ChatRequest {
        messages: vec![
            ChatMessage {
                role: "system",
                content: "Reply with the single word: ok".to_string(),
            },
            ChatMessage {
                role: "user",
                content: "ping".to_string(),
            },
        ],
        json_mode: false,
    };
    chat(provider, req).await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn provider(base: &str) -> LlmProvider {
        LlmProvider {
            base_url: base.to_string(),
            api_key: "k".to_string(),
            model: "m".to_string(),
            temperature: None,
            max_tokens: None,
            timeout_secs: Some(1),
        }
    }

    #[test]
    fn normalize_strips_trailing_slash() {
        assert_eq!(
            normalize_base_url("https://api.example.com/v1/").unwrap(),
            "https://api.example.com/v1"
        );
    }

    #[test]
    fn normalize_rejects_missing_scheme() {
        assert!(matches!(
            normalize_base_url("api.example.com").unwrap_err(),
            LlmError::BadBaseUrl
        ));
    }

    #[test]
    fn normalize_rejects_empty() {
        assert!(matches!(
            normalize_base_url("   ").unwrap_err(),
            LlmError::BadBaseUrl
        ));
    }

    #[test]
    fn provider_builds() {
        let p = provider("https://example.com/v1");
        assert_eq!(p.base_url, "https://example.com/v1");
        assert_eq!(p.timeout_secs, Some(1));
    }
}
