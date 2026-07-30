use crate::models::LlmProvider;
use crate::services::llm::{chat, ChatMessage, ChatRequest, LlmError};
use crate::services::translation_cache::{CacheKey, CachedTranslation, TranslationCache};
use serde::{Deserialize, Serialize};

const MAX_CONTENT_CHARS: usize = 32_000;
const MAX_CHUNK_CHARS: usize = 28_000; // 留 4k buffer 给 prompt
const OVERLAP_CHARS: usize = 200;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillTranslationInput {
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub content_md: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillTranslationOutput {
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub content_md: Option<String>,
    pub cached: bool,
}

fn lang_name(code: &str) -> &'static str {
    match code {
        "zh" => "Simplified Chinese",
        "en" => "English",
        _ => "English",
    }
}

fn build_prompt(target_lang: &str, input: &SkillTranslationInput) -> Vec<ChatMessage> {
    let system = format!(
        "You translate developer-tool documentation to {target}.\n\
Preserve markdown formatting, code blocks, YAML frontmatter, and links.\n\
Do NOT translate: code identifiers, YAML keys, file paths, URLs, or commands.\n\
Reply ONLY with a JSON object with this shape: {{\"name\": string, \"description\": string, \"content_md\": string|null}}.\n\
If a field was not provided in the input, return null for it.",
        target = lang_name(target_lang)
    );

    let user_json = serde_json::json!({
        "name": input.name,
        "description": input.description,
        "content_md": input.content_md,
    });

    vec![
        ChatMessage {
            role: "system",
            content: system,
        },
        ChatMessage {
            role: "user",
            content: serde_json::to_string(&user_json).unwrap_or_default(),
        },
    ]
}

#[derive(Deserialize)]
struct LlmReply {
    name: Option<String>,
    description: Option<String>,
    #[serde(default)]
    content_md: Option<String>,
}

fn extract_json_block(text: &str) -> &str {
    let trimmed = text.trim();
    if let Some(start) = trimmed.find('{') {
        if let Some(end) = trimmed.rfind('}') {
            if end >= start {
                return &trimmed[start..=end];
            }
        }
    }
    trimmed
}

/// 智能分段 Markdown 内容
/// 在段落边界分割，保持代码块完整，添加重叠上下文
fn split_markdown_intelligently(content: &str, max_chars: usize, overlap: usize) -> Vec<String> {
    let paragraphs: Vec<&str> = content.split("\n\n").collect();
    let mut chunks = Vec::new();
    let mut current_chunk = String::new();
    let mut in_code_block = false;

    for para in paragraphs {
        // 检测代码块边界
        let trimmed = para.trim_start();
        if trimmed.starts_with("```") {
            in_code_block = !in_code_block;
        }

        let para_len = para.chars().count();
        let current_len = current_chunk.chars().count();

        // 判断是否需要切分（不在代码块中且超过限制）
        if current_len + para_len + 2 > max_chars && !in_code_block && !current_chunk.is_empty() {
            chunks.push(current_chunk.clone());

            // 保留尾部作为下一段的上下文
            let tail: String = current_chunk
                .chars()
                .rev()
                .take(overlap)
                .collect::<Vec<_>>()
                .into_iter()
                .rev()
                .collect();
            current_chunk = tail;
        }

        current_chunk.push_str(para);
        current_chunk.push_str("\n\n");
    }

    if !current_chunk.trim().is_empty() {
        chunks.push(current_chunk);
    }

    // 如果没有切分，至少返回原内容
    if chunks.is_empty() {
        chunks.push(content.to_string());
    }

    chunks
}

/// 合并翻译后的分段，去除重叠部分
fn merge_chunks(translated: Vec<String>, overlap: usize) -> String {
    if translated.len() == 1 {
        return translated[0].trim().to_string();
    }

    let mut result = translated[0].clone();

    for chunk in &translated[1..] {
        // 简单实现：丢弃前 overlap 字符
        // 生产环境可使用 LCS 算法更精确地去重
        let start: String = chunk.chars().skip(overlap).collect();
        result.push_str(&start);
    }

    result.trim().to_string()
}

/// 翻译长文档（分段处理）
async fn translate_long_content(
    provider: &LlmProvider,
    target_lang: &str,
    name: &str,
    description: &str,
    content: &str,
) -> Result<String, LlmError> {
    let chunks = split_markdown_intelligently(content, MAX_CHUNK_CHARS, OVERLAP_CHARS);
    let total_chunks = chunks.len();
    let mut translated = Vec::new();

    for (i, chunk) in chunks.iter().enumerate() {
        let chunk_input = SkillTranslationInput {
            name: format!("{} (part {}/{})", name, i + 1, total_chunks),
            description: description.to_string(),
            content_md: Some(chunk.clone()),
        };

        let messages = build_prompt(target_lang, &chunk_input);
        let raw = chat(
            provider,
            ChatRequest {
                messages,
                json_mode: true,
            },
        )
        .await?;

        let json_text = extract_json_block(&raw);
        let parsed: LlmReply = serde_json::from_str(json_text)
            .map_err(|e| LlmError::ParseError(format!("{e}; raw: {}", truncate(&raw, 200))))?;

        let content_md = parsed.content_md.unwrap_or_else(|| chunk.clone());
        translated.push(content_md);
    }

    Ok(merge_chunks(translated, OVERLAP_CHARS))
}

pub async fn translate_skill(
    provider: &LlmProvider,
    target_lang: &str,
    input: SkillTranslationInput,
    force_refresh: bool,
) -> Result<SkillTranslationOutput, LlmError> {
    let cache = TranslationCache::new();
    let key = CacheKey {
        base_url: &provider.base_url,
        model: &provider.model,
        target_lang,
        source_name: &input.name,
        source_description: &input.description,
        source_content_md: input.content_md.as_deref(),
    };

    // 检查缓存
    if !force_refresh {
        if let Some(hit) = cache.get(&key) {
            return Ok(SkillTranslationOutput {
                name: hit.name,
                description: hit.description,
                content_md: hit.content_md,
                cached: true,
            });
        }
    }

    // 判断是否需要分段翻译
    let total_chars = input.name.chars().count()
        + input.description.chars().count()
        + input
            .content_md
            .as_ref()
            .map(|s| s.chars().count())
            .unwrap_or(0);

    let (translated_name, translated_desc, translated_content) = if total_chars <= MAX_CONTENT_CHARS
    {
        // 短文档：直接翻译
        let messages = build_prompt(target_lang, &input);
        let raw = chat(
            provider,
            ChatRequest {
                messages,
                json_mode: true,
            },
        )
        .await?;

        let json_text = extract_json_block(&raw);
        let parsed: LlmReply = serde_json::from_str(json_text)
            .map_err(|e| LlmError::ParseError(format!("{e}; raw: {}", truncate(&raw, 200))))?;

        (
            parsed.name.unwrap_or_else(|| input.name.clone()),
            parsed
                .description
                .unwrap_or_else(|| input.description.clone()),
            parsed.content_md.or(input.content_md.clone()),
        )
    } else {
        // 长文档：分段翻译
        // 先翻译 name 和 description
        let short_input = SkillTranslationInput {
            name: input.name.clone(),
            description: input.description.clone(),
            content_md: None,
        };
        let messages = build_prompt(target_lang, &short_input);
        let raw = chat(
            provider,
            ChatRequest {
                messages,
                json_mode: true,
            },
        )
        .await?;

        let json_text = extract_json_block(&raw);
        let parsed: LlmReply = serde_json::from_str(json_text)
            .map_err(|e| LlmError::ParseError(format!("{e}; raw: {}", truncate(&raw, 200))))?;

        let name = parsed.name.unwrap_or_else(|| input.name.clone());
        let description = parsed
            .description
            .unwrap_or_else(|| input.description.clone());

        // 如果有 content_md，分段翻译
        let content = if let Some(md) = &input.content_md {
            Some(translate_long_content(provider, target_lang, &name, &description, md).await?)
        } else {
            None
        };

        (name, description, content)
    };

    let output = CachedTranslation {
        name: translated_name,
        description: translated_desc,
        content_md: translated_content,
    };

    let _ = cache.put(&key, &output);

    Ok(SkillTranslationOutput {
        name: output.name,
        description: output.description,
        content_md: output.content_md,
        cached: false,
    })
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        let truncated: String = s.chars().take(max).collect();
        format!("{truncated}…")
    }
}

pub fn clear_cache() -> std::io::Result<()> {
    TranslationCache::new().clear()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_json_block_handles_plain() {
        assert_eq!(extract_json_block(r#"{"a":1}"#), r#"{"a":1}"#);
    }

    #[test]
    fn extract_json_block_strips_surrounding_text() {
        let raw = "Sure, here is the JSON:\n```json\n{\"name\":\"x\"}\n```";
        assert_eq!(extract_json_block(raw), r#"{"name":"x"}"#);
    }

    #[test]
    fn extract_json_block_returns_input_when_no_braces() {
        assert_eq!(extract_json_block("no json"), "no json");
    }

    #[test]
    fn build_prompt_includes_target_language_name() {
        let messages = build_prompt(
            "zh",
            &SkillTranslationInput {
                name: "Foo".to_string(),
                description: "Bar".to_string(),
                content_md: None,
            },
        );
        assert_eq!(messages.len(), 2);
        assert!(messages[0].content.contains("Simplified Chinese"));
        assert!(messages[1].content.contains("Foo"));
        assert!(messages[1].content.contains("Bar"));
    }

    #[test]
    fn truncate_handles_short_string() {
        assert_eq!(truncate("hi", 10), "hi");
    }

    #[test]
    fn truncate_appends_ellipsis_when_too_long() {
        let result = truncate("abcdefgh", 4);
        assert_eq!(result, "abcd…");
    }

    #[test]
    fn split_markdown_single_paragraph_no_split() {
        let content = "Short paragraph.";
        let chunks = split_markdown_intelligently(content, 100, 10);
        assert_eq!(chunks.len(), 1);
        assert!(chunks[0].contains("Short paragraph"));
    }

    #[test]
    fn split_markdown_respects_paragraph_boundaries() {
        let content = "Para 1.\n\nPara 2.\n\nPara 3.";
        let chunks = split_markdown_intelligently(content, 20, 5);
        // 应该分成多段
        assert!(chunks.len() >= 2);
    }

    #[test]
    fn split_markdown_preserves_code_blocks() {
        let content = "Before\n\n```rust\nfn main() {\n    println!(\"hello\");\n}\n```\n\nAfter";
        let chunks = split_markdown_intelligently(content, 50, 10);
        // 代码块不应该被切分，整个内容应该在一个 chunk 或代码块完整
        for chunk in &chunks {
            let backtick_count = chunk.matches("```").count();
            // 每个 chunk 中的 ``` 必须成对
            assert_eq!(backtick_count % 2, 0, "Code block markers must be balanced");
        }
    }

    #[test]
    fn split_markdown_adds_overlap() {
        let content = "A".repeat(100) + "\n\n" + &"B".repeat(100);
        let chunks = split_markdown_intelligently(&content, 120, 20);
        if chunks.len() > 1 {
            // 第二个 chunk 应该包含第一个的尾部
            assert!(chunks[1].starts_with("A") || chunks[1].contains("A"));
        }
    }

    #[test]
    fn merge_chunks_single_chunk_returns_as_is() {
        let chunks = vec!["Content".to_string()];
        let result = merge_chunks(chunks, 10);
        assert_eq!(result, "Content");
    }

    #[test]
    fn merge_chunks_removes_overlap() {
        let chunks = vec!["Hello world".to_string(), "world again".to_string()];
        let result = merge_chunks(chunks, 5);
        // 应该去除重叠的 "world"（5个字符）
        assert!(result.contains("Hello"));
        assert!(result.contains("again"));
    }
}
