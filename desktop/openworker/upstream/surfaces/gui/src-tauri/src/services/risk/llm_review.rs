//! LLM 二审：在规则引擎全绿但 skill 含代码块时调用 LLM 进行语义审核
//!
//! 复用 services/llm.rs 的 chat 接口，要求返回 JSON 格式结果
//! 失败时返回空 vec，不阻塞主流程

use serde::{Deserialize, Serialize};

use crate::models::{LlmProvider, RiskCategory, RiskFinding, RiskLevel, RiskLocation};
use crate::services::llm::{chat, ChatMessage, ChatRequest, LlmError};

use super::parser::CodeBlock;

/// LLM 二审请求的输入
pub struct LlmReviewInput<'a> {
    pub skill_name: &'a str,
    pub skill_description: Option<&'a str>,
    pub blocks: &'a [CodeBlock],
}

/// LLM 返回的单条 finding（JSON 反序列化）
#[derive(Debug, Deserialize, Serialize)]
struct LlmFindingRaw {
    rule_id: String,
    level: String,    // "low" | "medium" | "high" | "critical"
    category: String, // "destructive" | "network" | "privilege" | "payload"
    confidence: f32,
    message: String,
    evidence: String,
    file: String,
    line: u32,
}

/// LLM 返回的整体结构
#[derive(Debug, Deserialize)]
struct LlmReviewResponse {
    findings: Vec<LlmFindingRaw>,
}

/// 调用 LLM 进行二审
///
/// 返回 Ok(Vec<RiskFinding>) 表示成功（可能为空）
/// 返回 Err(LlmError) 表示失败，调用方应保留规则结果
pub async fn review_with_llm(
    provider: &LlmProvider,
    input: LlmReviewInput<'_>,
) -> Result<Vec<RiskFinding>, LlmError> {
    let prompt = build_prompt(input);
    let req = ChatRequest {
        messages: vec![
            ChatMessage {
                role: "system",
                content: SYSTEM_PROMPT.to_string(),
            },
            ChatMessage {
                role: "user",
                content: prompt,
            },
        ],
        json_mode: true,
    };

    let response = chat(provider, req).await?;
    parse_llm_response(&response)
}

const SYSTEM_PROMPT: &str = r#"你是一个 AI Agent 技能安全审核专家。
你的任务是审查 AI 编程助手（如 Claude Code、Codex、Cursor）使用的 Skill（SKILL.md 及附带脚本），识别规则引擎可能遗漏的语义级安全风险。

关注以下四类风险：
1. destructive: 不可逆的破坏性操作（删除数据、格式化磁盘、杀进程等）
2. network: 网络外发或下载执行（反弹 shell、外发凭据、可疑域名连接等）
3. privilege: 提权与环境修改（写 .bashrc、改 PATH、注册持久化任务等）
4. payload: 可疑载荷与混淆（base64 解码执行、eval、零宽字符、typosquatting 等）

输出要求：
- 严格的 JSON 格式
- 仅在发现真实风险时返回 findings，无风险时返回空数组
- 每条 finding 必须包含：rule_id（以 "llm." 前缀开头）、level、category、confidence（0-1）、message、evidence、file、line
- level 取值：low | medium | high | critical
- category 取值：destructive | network | privilege | payload
- 不要凭空捏造文件名和行号，必须基于实际提供的内容
- 文档说明性引用（如 .env.example、教学示例）不应判为风险

输出 JSON 结构：
{
  "findings": [
    {
      "rule_id": "llm.suspicious_intent",
      "level": "high",
      "category": "destructive",
      "confidence": 0.85,
      "message": "指令包含删除数据库的语义",
      "evidence": "delete all user data",
      "file": "SKILL.md",
      "line": 12
    }
  ]
}"#;

fn build_prompt(input: LlmReviewInput<'_>) -> String {
    let mut prompt = String::new();
    prompt.push_str(&format!("技能名称: {}\n", input.skill_name));
    if let Some(desc) = input.skill_description {
        prompt.push_str(&format!("技能描述: {}\n", desc));
    }
    prompt.push_str("\n待审核的代码块（格式：[文件:行号] 内容）：\n\n");

    // 限制总长度，避免 token 爆炸
    const MAX_BLOCKS: usize = 30;
    const MAX_CONTENT_LEN: usize = 500;

    for (idx, block) in input.blocks.iter().take(MAX_BLOCKS).enumerate() {
        let truncated = if block.content.len() > MAX_CONTENT_LEN {
            // 找到不超过 MAX_CONTENT_LEN 的最大字符边界，避免在多字节字符中间切片导致 panic
            let mut end = MAX_CONTENT_LEN;
            while end > 0 && !block.content.is_char_boundary(end) {
                end -= 1;
            }
            format!("{}...(截断)", &block.content[..end])
        } else {
            block.content.clone()
        };
        prompt.push_str(&format!(
            "[{}: {}:{}]\n{}\n\n",
            idx + 1,
            block.file,
            block.line,
            truncated
        ));
    }

    prompt.push_str("请基于以上内容进行语义级安全审核，输出 JSON：");
    prompt
}

fn parse_llm_response(response: &str) -> Result<Vec<RiskFinding>, LlmError> {
    let trimmed = response.trim();

    // 兼容带 markdown code fence 的情况
    let json_str = strip_code_fence(trimmed);

    let parsed: LlmReviewResponse = serde_json::from_str(&json_str).map_err(|e| {
        LlmError::ParseError(format!("LLM 响应解析失败: {} | 原始: {}", e, trimmed))
    })?;

    let findings = parsed
        .findings
        .into_iter()
        .filter_map(|raw| {
            let level = parse_level(&raw.level)?;
            let category = parse_category(&raw.category)?;
            // 跳过 level=safe 的项
            if level == RiskLevel::Safe {
                return None;
            }
            Some(RiskFinding {
                rule_id: raw.rule_id,
                level,
                category,
                confidence: raw.confidence,
                message: raw.message,
                evidence: raw.evidence,
                location: RiskLocation {
                    file: raw.file,
                    line: raw.line,
                    lang: None,
                    in_code_example: false,
                    in_comment: false,
                    in_docs_dir: false,
                },
                from_llm: false, // 由 merge_llm_findings 设置为 true
            })
        })
        .collect();

    Ok(findings)
}

fn strip_code_fence(s: &str) -> String {
    let s = s.trim();
    if s.starts_with("```") {
        // 去掉首行 fence
        let after_first_line = s.lines().skip(1).collect::<Vec<_>>().join("\n");
        // 去掉末尾 fence
        if let Some(stripped) = after_first_line.strip_suffix("```") {
            return stripped.trim().to_string();
        }
        return after_first_line.trim().to_string();
    }
    s.to_string()
}

fn parse_level(s: &str) -> Option<RiskLevel> {
    match s.to_lowercase().as_str() {
        "safe" | "" => Some(RiskLevel::Safe),
        "low" => Some(RiskLevel::Low),
        "medium" => Some(RiskLevel::Medium),
        "high" => Some(RiskLevel::High),
        "critical" => Some(RiskLevel::Critical),
        _ => None,
    }
}

fn parse_category(s: &str) -> Option<RiskCategory> {
    match s.to_lowercase().as_str() {
        "destructive" => Some(RiskCategory::Destructive),
        "network" => Some(RiskCategory::Network),
        "privilege" => Some(RiskCategory::Privilege),
        "payload" => Some(RiskCategory::Payload),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_level_maps_known_strings() {
        assert_eq!(parse_level("low"), Some(RiskLevel::Low));
        assert_eq!(parse_level("Medium"), Some(RiskLevel::Medium));
        assert_eq!(parse_level("HIGH"), Some(RiskLevel::High));
        assert_eq!(parse_level("critical"), Some(RiskLevel::Critical));
        assert_eq!(parse_level("safe"), Some(RiskLevel::Safe));
        assert_eq!(parse_level(""), Some(RiskLevel::Safe));
        assert_eq!(parse_level("unknown"), None);
    }

    #[test]
    fn parse_category_maps_known_strings() {
        assert_eq!(
            parse_category("destructive"),
            Some(RiskCategory::Destructive)
        );
        assert_eq!(parse_category("network"), Some(RiskCategory::Network));
        assert_eq!(parse_category("privilege"), Some(RiskCategory::Privilege));
        assert_eq!(parse_category("payload"), Some(RiskCategory::Payload));
        assert_eq!(parse_category("unknown"), None);
    }

    #[test]
    fn parse_llm_response_handles_clean_json() {
        let json = r#"{"findings":[{"rule_id":"llm.x","level":"high","category":"destructive","confidence":0.85,"message":"删除数据库","evidence":"drop database","file":"SKILL.md","line":12}]}"#;
        let findings = parse_llm_response(json).expect("parse ok");
        assert_eq!(findings.len(), 1);
        assert_eq!(findings[0].rule_id, "llm.x");
        assert_eq!(findings[0].level, RiskLevel::High);
        assert_eq!(findings[0].category, RiskCategory::Destructive);
        assert_eq!(findings[0].location.file, "SKILL.md");
        assert_eq!(findings[0].location.line, 12);
        assert!(!findings[0].from_llm); // merge 时才会设置
    }

    #[test]
    fn parse_llm_response_handles_code_fenced_json() {
        let json = "```json\n{\"findings\":[]}\n```";
        let findings = parse_llm_response(json).expect("parse ok");
        assert!(findings.is_empty());
    }

    #[test]
    fn parse_llm_response_filters_invalid_level() {
        let json = r#"{"findings":[{"rule_id":"llm.x","level":"unknown","category":"destructive","confidence":0.5,"message":"x","evidence":"x","file":"x","line":1}]}"#;
        let findings = parse_llm_response(json).expect("parse ok");
        assert!(findings.is_empty(), "未知 level 应被过滤");
    }

    #[test]
    fn parse_llm_response_filters_invalid_category() {
        let json = r#"{"findings":[{"rule_id":"llm.x","level":"high","category":"unknown","confidence":0.5,"message":"x","evidence":"x","file":"x","line":1}]}"#;
        let findings = parse_llm_response(json).expect("parse ok");
        assert!(findings.is_empty());
    }

    #[test]
    fn parse_llm_response_filters_safe_level() {
        let json = r#"{"findings":[{"rule_id":"llm.x","level":"safe","category":"destructive","confidence":0.2,"message":"x","evidence":"x","file":"x","line":1}]}"#;
        let findings = parse_llm_response(json).expect("parse ok");
        assert!(findings.is_empty(), "safe level 应被过滤");
    }

    #[test]
    fn parse_llm_response_errors_on_invalid_json() {
        let json = "not a json";
        let result = parse_llm_response(json);
        assert!(result.is_err());
    }

    #[test]
    fn build_prompt_includes_skill_info_and_blocks() {
        let blocks = vec![CodeBlock {
            file: "SKILL.md".to_string(),
            line: 5,
            lang: Some("bash".to_string()),
            in_code_example: true,
            in_comment: false,
            in_docs_dir: false,
            content: "rm -rf /".to_string(),
        }];
        let input = LlmReviewInput {
            skill_name: "test-skill",
            skill_description: Some("test desc"),
            blocks: &blocks,
        };
        let prompt = build_prompt(input);
        assert!(prompt.contains("test-skill"));
        assert!(prompt.contains("test desc"));
        assert!(prompt.contains("SKILL.md"));
        assert!(prompt.contains("5"));
        assert!(prompt.contains("rm -rf /"));
        assert!(prompt.contains("JSON"));
    }

    #[test]
    fn build_prompt_truncates_multibyte_content_without_panic() {
        // 500 字节边界落在多字节字符（如 box-drawing ─）中间时不能 panic
        let content: String = std::iter::repeat('a')
            .take(498)
            .chain(std::iter::repeat('─').take(10))
            .collect();
        assert!(content.len() > 500); // 确保触发截断分支
        let blocks = vec![CodeBlock {
            file: "SKILL.md".to_string(),
            line: 1,
            lang: Some("bash".to_string()),
            in_code_example: true,
            in_comment: false,
            in_docs_dir: false,
            content,
        }];
        let input = LlmReviewInput {
            skill_name: "test",
            skill_description: None,
            blocks: &blocks,
        };
        let prompt = build_prompt(input); // 不应 panic
        assert!(prompt.contains("...(截断)"));
    }

    #[test]
    fn strip_code_fence_handles_plain_json() {
        assert_eq!(strip_code_fence(r#"{"a":1}"#), r#"{"a":1}"#);
    }

    #[test]
    fn strip_code_fence_handles_fenced_json() {
        let input = "```json\n{\"a\":1}\n```";
        assert_eq!(strip_code_fence(input), r#"{"a":1}"#);
    }
}
