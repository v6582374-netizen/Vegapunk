//! 风险扫描 Tauri 命令
//!
//! 对外命令：
//! - get_risk_report: 获取单个 skill 的风险报告（命中缓存则秒回）
//! - scan_all_risks: 批量扫描所有已安装 skill
//! - rescan_skill: 强制重新扫描单个 skill
//! - clear_risk_cache: 清空所有风险缓存

use std::collections::HashMap;

use tauri::{AppHandle, Emitter};

use crate::models::{RiskScanMode, Skill, SkillRiskReport};
use crate::services::{
    clear_risk_cache, invalidate_risk_cache, scan_all_skills, scan_skill, ConfigManager,
    ScannerService,
};

/// 获取单个 skill 的风险报告
///
/// 若缓存命中则立即返回，否则同步扫描（基础模式）或异步扫描（深度模式）
#[tauri::command]
pub async fn get_risk_report(instance_id: String) -> Result<SkillRiskReport, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let mode = config
        .preferences
        .as_ref()
        .map(|p| p.risk_scan_mode)
        .unwrap_or(RiskScanMode::Off);
    let llm_provider = config.llm_provider.as_ref();

    // 找到对应的 skill
    let skills = ScannerService::scan_scoped_skills(&config)?;
    let skill = skills
        .into_iter()
        .find(|s| s.instance_id == instance_id)
        .ok_or_else(|| format!("Skill not found: {}", instance_id))?;

    let report = scan_skill(&skill, mode, llm_provider).await;
    Ok(report)
}

/// 批量扫描所有已安装 skill
///
/// 同步返回报告，扫描完成后通过 `risk-scan-completed` 事件通知前端
/// 用于前端手动触发"立即扫描"
#[tauri::command]
pub async fn scan_all_risks(app: AppHandle) -> Result<Vec<SkillRiskReport>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let mode = config
        .preferences
        .as_ref()
        .map(|p| p.risk_scan_mode)
        .unwrap_or(RiskScanMode::Off);
    let llm_provider = config.llm_provider.as_ref();

    if mode.is_off() {
        return Ok(Vec::new());
    }

    let skills = ScannerService::scan_scoped_skills(&config)?;
    let reports = scan_all_skills(&skills, mode, llm_provider).await;

    // 通知前端刷新
    let _ = app.emit("risk-scan-completed", ());

    Ok(reports)
}

/// 强制重新扫描单个 skill（清除缓存后扫描）
#[tauri::command]
pub async fn rescan_skill(instance_id: String) -> Result<SkillRiskReport, String> {
    // 先清缓存
    invalidate_risk_cache(&instance_id);

    let manager = ConfigManager::new();
    let config = manager.load()?;
    let mode = config
        .preferences
        .as_ref()
        .map(|p| p.risk_scan_mode)
        .unwrap_or(RiskScanMode::Off);
    let llm_provider = config.llm_provider.as_ref();

    let skills = ScannerService::scan_scoped_skills(&config)?;
    let skill = skills
        .into_iter()
        .find(|s| s.instance_id == instance_id)
        .ok_or_else(|| format!("Skill not found: {}", instance_id))?;

    let report = scan_skill(&skill, mode, llm_provider).await;
    Ok(report)
}

/// 清空所有风险缓存
#[tauri::command]
pub fn clear_risk_cache_command() -> Result<(), String> {
    clear_risk_cache();
    Ok(())
}

/// 获取风险扫描器版本号（用于前端展示）
#[tauri::command]
pub fn get_risk_scanner_version() -> String {
    crate::services::scanner_version().to_string()
}

/// 批量获取多个 skill 的风险报告
///
/// 用于列表页一次性加载所有 skill 的风险等级。
/// 不传 `instance_ids` 时返回所有已安装 skill 的报告。
#[tauri::command]
pub async fn get_risk_reports_batch(
    instance_ids: Option<Vec<String>>,
) -> Result<HashMap<String, SkillRiskReport>, String> {
    let manager = ConfigManager::new();
    let config = manager.load()?;
    let mode = config
        .preferences
        .as_ref()
        .map(|p| p.risk_scan_mode)
        .unwrap_or(RiskScanMode::Off);
    let llm_provider = config.llm_provider.as_ref();

    if mode.is_off() {
        return Ok(HashMap::new());
    }

    let skills = ScannerService::scan_scoped_skills(&config)?;
    let mut reports = HashMap::new();

    let target_ids: Vec<String> = instance_ids.unwrap_or_default();
    let matched: Vec<&Skill> = if target_ids.is_empty() {
        skills.iter().collect()
    } else {
        target_ids
            .iter()
            .filter_map(|id| skills.iter().find(|s| s.instance_id == *id))
            .collect()
    };

    for skill in matched {
        let report = scan_skill(skill, mode, llm_provider).await;
        reports.insert(skill.instance_id.clone(), report);
    }

    Ok(reports)
}

/// 启动时的后台批量扫描
///
/// 在 lib.rs setup 中调用，不阻塞启动
pub fn start_background_scan(app: AppHandle) {
    std::thread::spawn(move || {
        let rt = match tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
        {
            Ok(rt) => rt,
            Err(_) => return,
        };

        rt.block_on(async {
            let manager = match ConfigManager::new().load() {
                Ok(c) => c,
                Err(_) => return,
            };
            let mode = manager
                .preferences
                .as_ref()
                .map(|p| p.risk_scan_mode)
                .unwrap_or(RiskScanMode::Off);
            let llm_provider = manager.llm_provider.as_ref();

            if mode.is_off() {
                return;
            }

            let skills = match ScannerService::scan_scoped_skills(&manager) {
                Ok(s) => s,
                Err(_) => return,
            };

            let _ = scan_all_skills(&skills, mode, llm_provider).await;
            let _ = app.emit("risk-scan-completed", ());
        });
    });
}
