//! 风险扫描服务编排层
//!
//! 流程：parse_skill_dir → scan_blocks → 可选 LLM 二审 → 落缓存
//! 对外暴露：scan_skill、scan_all_skills

pub mod cache;
pub mod llm_review;
pub mod parser;
pub mod rules;

use std::sync::Mutex;

use once_cell::sync::Lazy;

use crate::models::{
    LlmProvider, RiskScanMode, Skill, SkillRiskReport,
};

/// 扫描器版本，用于缓存失效。规则有变更时递增。
const SCANNER_VERSION: &str = "1.0.0";

/// 全局缓存实例（进程级单例）
static RISK_CACHE: Lazy<Mutex<cache::RiskCache>> =
    Lazy::new(|| Mutex::new(cache::RiskCache::new()));

/// 扫描单个 skill 的风险
///
/// - 若 mode == Off，立即返回 Safe 报告
/// - 优先查缓存（key 含 path+mtime+version+mode）
/// - 缓存未命中则执行 parse → rules → LLM（可选）
/// - 结果写入缓存
pub async fn scan_skill(skill: &Skill, mode: RiskScanMode, llm_provider: Option<&LlmProvider>) -> SkillRiskReport {
    if mode.is_off() {
        return SkillRiskReport::safe(&skill.instance_id, SCANNER_VERSION, mode);
    }

    let path = &skill.path;
    let mtime = cache::read_mtime(path);

    let key = cache::RiskCache::build_key(
        &skill.instance_id,
        path,
        mtime,
        SCANNER_VERSION,
        mode,
    );

    // 查缓存
    {
        if let Ok(cache) = RISK_CACHE.lock() {
            if let Some(report) = cache.get(&key) {
                return report;
            }
        }
    }

    // 1. 解析 skill 目录
    let files = parser::parse_skill_dir(path);
    let blocks: Vec<parser::CodeBlock> = files
        .into_iter()
        .flat_map(|f| f.blocks)
        .collect();

    // 2. 规则引擎
    let mut report = SkillRiskReport::safe(&skill.instance_id, SCANNER_VERSION, mode);
    let rule_findings = rules::scan_blocks(&blocks);
    for f in rule_findings {
        report.push_finding(f);
    }

    // 3. LLM 二审：仅 deep 模式 + 规则全绿 + 有代码块 + 已配置 provider
    if mode.is_deep() {
        if let Some(provider) = llm_provider {
            // 规则全绿 + 有代码块才触发
            let should_trigger_llm = report.findings.is_empty() && !blocks.is_empty();
            if should_trigger_llm {
                let input = llm_review::LlmReviewInput {
                    skill_name: &skill.name,
                    skill_description: skill.description.as_deref(),
                    blocks: &blocks,
                };
                // 兜底超时：即使 llm::chat 的 reqwest 超时失效（如服务器持续发心跳），
                // 也不会让单个 skill 卡住整个 scan_all_skills 串行循环
                let llm_timeout = std::time::Duration::from_secs(
                    provider.timeout_secs.unwrap_or(60) as u64,
                );
                match tokio::time::timeout(
                    llm_timeout,
                    llm_review::review_with_llm(provider, input),
                )
                .await
                {
                    Ok(Ok(llm_findings)) => {
                        if !llm_findings.is_empty() {
                            report.merge_llm_findings(llm_findings);
                        } else {
                            report.llm_reviewed = true;
                        }
                    }
                    Ok(Err(_)) => {
                        // LLM 失败不阻塞，保留规则结果
                        report.llm_reviewed = false;
                    }
                    Err(_) => {
                        // 超时：不阻塞，保留规则结果
                        report.llm_reviewed = false;
                    }
                }
            }
        }
    }

    // 4. 写缓存
    if let Ok(cache) = RISK_CACHE.lock() {
        cache.put(&report);
    }

    report
}

/// 批量扫描多个 skill（异步并发）
pub async fn scan_all_skills(
    skills: &[Skill],
    mode: RiskScanMode,
    llm_provider: Option<&LlmProvider>,
) -> Vec<SkillRiskReport> {
    let mut reports = Vec::with_capacity(skills.len());
    for skill in skills {
        let report = scan_skill(skill, mode, llm_provider).await;
        reports.push(report);
    }
    reports
}

/// 清空所有缓存
pub fn clear_cache() {
    if let Ok(cache) = RISK_CACHE.lock() {
        cache.clear();
    }
}

/// 清除单个 skill 的缓存
pub fn invalidate_skill(instance_id: &str) {
    if let Ok(cache) = RISK_CACHE.lock() {
        cache.remove(instance_id);
    }
}

/// 获取扫描器版本号
pub fn scanner_version() -> &'static str {
    SCANNER_VERSION
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{Skill, SkillScope, SkillSource};
    use std::fs;
    use std::path::Path;
    use tempfile::tempdir;

    fn make_skill_at(dir: &Path, id: &str, content: &str) -> Skill {
        let skill_dir = dir.join(id);
        fs::create_dir_all(&skill_dir).unwrap();
        fs::write(skill_dir.join("SKILL.md"), content).unwrap();
        Skill {
            id: id.to_string(),
            instance_id: Skill::global_instance_id(id),
            scope: SkillScope::Global,
            project_id: None,
            project_name: None,
            name: id.to_string(),
            description: None,
            version: "1.0".to_string(),
            source: SkillSource::Local,
            marketplace_meta: None,
            vault_meta: None,
            package_meta: None,
            enabled: Default::default(),
            path: skill_dir,
        }
    }

    #[tokio::test]
    async fn scan_skill_off_mode_returns_safe() {
        let dir = tempdir().unwrap();
        let skill = make_skill_at(dir.path(), "evil", "```bash\nrm -rf /\n```\n");

        let report = scan_skill(&skill, RiskScanMode::Off, None).await;
        assert_eq!(report.level, crate::models::RiskLevel::Safe);
        assert!(report.findings.is_empty());
    }

    #[tokio::test]
    async fn scan_skill_basic_detects_rm_rf_root() {
        // 用唯一 ID 避免与其他测试缓存冲突
        let id = "evil_basic_rmrf_001";
        let dir = tempdir().unwrap();
        // 直接写非代码块的 rm -rf /（SKILL.md 主体文本）
        let skill = make_skill_at(dir.path(), id, "rm -rf /\n");
        let report = scan_skill(&skill, RiskScanMode::Basic, None).await;
        assert_eq!(report.level, crate::models::RiskLevel::Critical);
        assert!(report.findings.iter().any(|f| f.rule_id == "destructive.rm_rf_root"));
    }

    #[tokio::test]
    async fn scan_skill_uses_cache_on_second_call() {
        let id = "evil_cache_test_002";
        let dir = tempdir().unwrap();
        let skill = make_skill_at(dir.path(), id, "rm -rf /\n");

        // 第一次扫描
        let r1 = scan_skill(&skill, RiskScanMode::Basic, None).await;
        assert_eq!(r1.findings.len(), 1);

        // 第二次扫描应命中缓存（无法直接验证，但至少应返回相同结果）
        let r2 = scan_skill(&skill, RiskScanMode::Basic, None).await;
        assert_eq!(r1, r2);
    }

    #[tokio::test]
    async fn scan_skill_safe_skill_returns_no_findings() {
        let id = "safe_skill_003";
        let dir = tempdir().unwrap();
        let skill = make_skill_at(
            dir.path(),
            id,
            "# Safe Skill\n\nThis skill does nothing dangerous.\n\n```bash\necho hello\n```\n",
        );

        let report = scan_skill(&skill, RiskScanMode::Basic, None).await;
        assert_eq!(report.level, crate::models::RiskLevel::Safe);
        assert!(report.findings.is_empty());
    }

    #[tokio::test]
    async fn scan_all_skills_aggregates_reports() {
        let dir = tempdir().unwrap();
        let skill1 = make_skill_at(dir.path(), "evil_multi_004", "rm -rf /\n");
        let skill2 = make_skill_at(dir.path(), "safe_multi_005", "echo hello\n");
        let skills = vec![skill1, skill2];

        let reports = scan_all_skills(&skills, RiskScanMode::Basic, None).await;
        assert_eq!(reports.len(), 2);
        let evil = reports.iter().find(|r| r.instance_id.ends_with("evil_multi_004")).unwrap();
        assert_eq!(evil.level, crate::models::RiskLevel::Critical);
        let safe = reports.iter().find(|r| r.instance_id.ends_with("safe_multi_005")).unwrap();
        assert_eq!(safe.level, crate::models::RiskLevel::Safe);
    }

    #[test]
    fn clear_cache_works() {
        // 不应 panic
        clear_cache();
    }

    #[test]
    fn invalidate_skill_works() {
        invalidate_skill("global:nonexistent");
    }
}
