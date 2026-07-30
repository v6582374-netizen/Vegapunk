use serde::Deserialize;
use serde_json::json;

const FEISHU_WEBHOOK_URL: &str =
    "https://open.feishu.cn/open-apis/bot/v2/hook/31a9a8c2-64a7-4e40-a854-16b2dfb458c1";

#[derive(Debug, Clone, Deserialize)]
pub struct FeedbackRequest {
    pub contact_type: String,
    pub contact_value: String,
    pub content: String,
    pub source: Option<String>,
    pub language: Option<String>,
}

fn sanitize_input(value: &str) -> String {
    value.trim().to_string()
}

fn normalized_optional(value: &Option<String>, fallback: &str) -> String {
    value
        .as_deref()
        .map(sanitize_input)
        .filter(|v| !v.is_empty())
        .unwrap_or_else(|| fallback.to_string())
}

fn validate_feedback_request(request: &FeedbackRequest) -> Result<(), String> {
    let contact_type = sanitize_input(&request.contact_type);
    if contact_type.is_empty() {
        return Err("联系渠道不能为空".to_string());
    }

    if !is_supported_contact_type(&contact_type) {
        return Err("联系渠道无效".to_string());
    }

    let contact_value = sanitize_input(&request.contact_value);
    if contact_value.is_empty() {
        return Err("联系方式不能为空".to_string());
    }

    if !is_valid_contact_value(&contact_type, &contact_value) {
        return Err("联系方式格式无效".to_string());
    }

    if sanitize_input(&request.content).is_empty() {
        return Err("反馈内容不能为空".to_string());
    }

    Ok(())
}

fn build_feedback_message_text(request: &FeedbackRequest) -> String {
    let contact_type = sanitize_input(&request.contact_type);
    let contact_value = sanitize_input(&request.contact_value);
    let content = sanitize_input(&request.content);
    let source = normalized_optional(&request.source, "desktop-feedback-page");
    let language = normalized_optional(&request.language, "unknown");

    format!(
        "Skills Manager 用户反馈\n联系渠道: {}\n联系方式: {contact_value}\n来源: {source}\n语言: {language}\n反馈内容:\n{content}",
        contact_type_label(&contact_type)
    )
}

fn build_feishu_payload(request: &FeedbackRequest) -> serde_json::Value {
    json!({
      "msg_type": "text",
      "content": {
        "text": build_feedback_message_text(request)
      }
    })
}

#[tauri::command]
pub async fn submit_feedback(request: FeedbackRequest) -> Result<(), String> {
    validate_feedback_request(&request)?;
    let payload = build_feishu_payload(&request);

    let response = reqwest::Client::new()
        .post(FEISHU_WEBHOOK_URL)
        .json(&payload)
        .send()
        .await
        .map_err(|err| format!("发送反馈失败: {err}"))?;

    if !response.status().is_success() {
        return Err(format!(
            "反馈提交失败，HTTP 状态码: {}",
            response.status().as_u16()
        ));
    }

    let body = response
        .text()
        .await
        .map_err(|err| format!("反馈提交失败: {err}"))?;

    if body.trim().is_empty() {
        return Ok(());
    }

    if let Ok(value) = serde_json::from_str::<serde_json::Value>(&body) {
        let code = value.get("code").and_then(|v| v.as_i64());
        let status_code = value.get("StatusCode").and_then(|v| v.as_i64());
        let msg = value
            .get("msg")
            .or_else(|| value.get("StatusMessage"))
            .and_then(|v| v.as_str())
            .unwrap_or("未知错误");

        if let Some(code) = code {
            if code != 0 {
                return Err(format!("反馈提交失败: {msg}"));
            }
        } else if let Some(status_code) = status_code {
            if status_code != 0 {
                return Err(format!("反馈提交失败: {msg}"));
            }
        }
    }

    Ok(())
}

fn is_supported_contact_type(contact_type: &str) -> bool {
    matches!(contact_type, "wechat" | "email" | "other")
}

fn contact_type_label(contact_type: &str) -> &'static str {
    match contact_type {
        "wechat" => "微信",
        "email" => "邮箱",
        "other" => "其他",
        _ => "未知",
    }
}

fn is_valid_contact_value(contact_type: &str, contact_value: &str) -> bool {
    match contact_type {
        "wechat" => is_valid_wechat(contact_value),
        "email" => is_valid_email(contact_value),
        "other" => is_valid_other_contact(contact_value),
        _ => false,
    }
}

fn is_valid_email(value: &str) -> bool {
    if value.chars().any(|ch| ch.is_whitespace()) {
        return false;
    }

    let mut parts = value.split('@');
    let local = parts.next().unwrap_or_default();
    let domain = parts.next().unwrap_or_default();

    if parts.next().is_some() || local.is_empty() || domain.is_empty() {
        return false;
    }

    if domain.starts_with('.') || domain.ends_with('.') || domain.contains("..") {
        return false;
    }

    domain.contains('.')
}

fn is_valid_wechat(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };

    let len = value.chars().count();
    if len < 6 || len > 20 || !(first.is_ascii_alphabetic() || first == '_') {
        return false;
    }

    chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_' || ch == '-')
}

fn is_valid_other_contact(value: &str) -> bool {
    if value.len() < 5 {
        return false;
    }

    let delimiter_index = value.find(':').or_else(|| value.find('：'));
    let Some(index) = delimiter_index else {
        return false;
    };

    let platform = value[..index].trim();
    let account = value[index + 1..].trim();

    !platform.is_empty() && platform.chars().count() <= 20 && account.chars().count() >= 2
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn build_feedback_message_text_should_include_trimmed_fields() {
        let request = FeedbackRequest {
            contact_type: "email".to_string(),
            contact_value: "  alice@example.com  ".to_string(),
            content: "  希望支持批量启用技能  ".to_string(),
            source: Some("desktop-feedback-page".to_string()),
            language: Some("zh".to_string()),
        };

        let text = build_feedback_message_text(&request);

        assert!(text.contains("Skills Manager 用户反馈"));
        assert!(text.contains("联系渠道: 邮箱"));
        assert!(text.contains("联系方式: alice@example.com"));
        assert!(text.contains("来源: desktop-feedback-page"));
        assert!(text.contains("语言: zh"));
        assert!(text.contains("反馈内容:\n希望支持批量启用技能"));
    }

    #[test]
    fn build_feishu_payload_should_wrap_message_as_text_card() {
        let request = FeedbackRequest {
            contact_type: "other".to_string(),
            contact_value: "Discord: jiweiyeah".to_string(),
            content: "Feedback body".to_string(),
            source: None,
            language: None,
        };

        let payload = build_feishu_payload(&request);
        let msg_type = payload.get("msg_type").and_then(|v| v.as_str());
        let text = payload
            .get("content")
            .and_then(|v| v.get("text"))
            .and_then(|v| v.as_str())
            .unwrap_or_default();

        assert_eq!(msg_type, Some("text"));
        assert!(text.contains("联系渠道: 其他"));
        assert!(text.contains("联系方式: Discord: jiweiyeah"));
        assert!(text.contains("Feedback body"));
    }

    #[test]
    fn validate_feedback_request_should_reject_blank_fields() {
        let blank_user = FeedbackRequest {
            contact_type: "   ".to_string(),
            contact_value: "alice@example.com".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };
        let blank_content = FeedbackRequest {
            contact_type: "email".to_string(),
            contact_value: "alice@example.com".to_string(),
            content: "   ".to_string(),
            source: None,
            language: None,
        };
        let blank_contact_value = FeedbackRequest {
            contact_type: "email".to_string(),
            contact_value: "   ".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };

        assert!(validate_feedback_request(&blank_user).is_err());
        assert!(validate_feedback_request(&blank_content).is_err());
        assert!(validate_feedback_request(&blank_contact_value).is_err());
    }

    #[test]
    fn validate_feedback_request_should_reject_invalid_contact_value() {
        let invalid_email = FeedbackRequest {
            contact_type: "email".to_string(),
            contact_value: "abc".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };
        let invalid_wechat = FeedbackRequest {
            contact_type: "wechat".to_string(),
            contact_value: "abc".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };
        let invalid_type = FeedbackRequest {
            contact_type: "github".to_string(),
            contact_value: "abc".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };
        let invalid_other = FeedbackRequest {
            contact_type: "other".to_string(),
            contact_value: "abc".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };

        assert!(validate_feedback_request(&invalid_email).is_err());
        assert!(validate_feedback_request(&invalid_wechat).is_err());
        assert!(validate_feedback_request(&invalid_type).is_err());
        assert!(validate_feedback_request(&invalid_other).is_err());
    }

    #[test]
    fn validate_feedback_request_should_accept_wechat_starting_with_underscore() {
        let request = FeedbackRequest {
            contact_type: "wechat".to_string(),
            contact_value: "_wechat1".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };

        assert!(validate_feedback_request(&request).is_ok());
    }

    #[test]
    fn validate_feedback_request_should_accept_structured_other_contact_value() {
        let request = FeedbackRequest {
            contact_type: "other".to_string(),
            contact_value: "QQ: 12345678".to_string(),
            content: "content".to_string(),
            source: None,
            language: None,
        };

        assert!(validate_feedback_request(&request).is_ok());
    }
}
