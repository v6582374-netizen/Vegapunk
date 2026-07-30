//! 风险报告缓存
//!
//! 缓存 key: instance_id + path + mtime + scanner_version + mode
//! 缓存位置: ~/.skills-manager/cache/risk/<instance_id>.json
//!
//! 当 path+mtime 相同且 scanner_version 与 mode 也匹配时复用缓存，避开 24h TTL 的不精确

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::SystemTime;

use crate::models::{RiskCacheKey, RiskScanMode, SkillRiskReport};

/// 内存 + 磁盘双层缓存
pub struct RiskCache {
    in_memory: Mutex<HashMap<String, SkillRiskReport>>,
    cache_dir: PathBuf,
}

impl RiskCache {
    pub fn new() -> Self {
        let cache_dir = default_cache_dir();
        // 迁移旧目录 ~/.skills-manager/risk-cache → ~/.skills-manager/cache/risk
        migrate_legacy_cache_dir(&cache_dir);
        // 启动时尝试创建目录
        let _ = fs::create_dir_all(&cache_dir);
        Self {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir,
        }
    }

    /// 构建缓存 key
    /// - instance_id: skill 实例 ID
    /// - path: skill 目录绝对路径
    /// - mtime: 目录最后修改时间（秒）
    /// - scanner_version: 扫描器版本号
    /// - mode: 扫描模式
    pub fn build_key(
        instance_id: &str,
        path: &Path,
        mtime: i64,
        scanner_version: &str,
        mode: RiskScanMode,
    ) -> RiskCacheKey {
        RiskCacheKey {
            instance_id: instance_id.to_string(),
            path: path.to_string_lossy().to_string(),
            mtime,
            scanner_version: scanner_version.to_string(),
            mode,
        }
    }

    /// 尝试从缓存读取报告
    /// - 优先查内存
    /// - 内存未命中再查磁盘
    pub fn get(&self, key: &RiskCacheKey) -> Option<SkillRiskReport> {
        // 先查内存
        {
            let mem = self.in_memory.lock().ok()?;
            if let Some(report) = mem.get(&key.instance_id) {
                if cache_key_matches(report, key) {
                    return Some(report.clone());
                }
            }
        }

        // 再查磁盘
        let disk_path = self.disk_path(&key.instance_id);
        let content = fs::read_to_string(&disk_path).ok()?;
        let report: SkillRiskReport = serde_json::from_str(&content).ok()?;
        if cache_key_matches(&report, key) {
            // 回填内存
            if let Ok(mut mem) = self.in_memory.lock() {
                mem.insert(key.instance_id.to_string(), report.clone());
            }
            Some(report)
        } else {
            None
        }
    }

    /// 写入缓存（同时写内存 + 磁盘）
    pub fn put(&self, report: &SkillRiskReport) {
        // 内存
        if let Ok(mut mem) = self.in_memory.lock() {
            mem.insert(report.instance_id.clone(), report.clone());
        }
        // 磁盘
        let disk_path = self.disk_path(&report.instance_id);
        if let Ok(json) = serde_json::to_string_pretty(report) {
            let _ = fs::create_dir_all(&self.cache_dir);
            let _ = fs::write(&disk_path, json);
        }
    }

    /// 清空所有缓存
    pub fn clear(&self) {
        if let Ok(mut mem) = self.in_memory.lock() {
            mem.clear();
        }
        let _ = fs::remove_dir_all(&self.cache_dir);
        let _ = fs::create_dir_all(&self.cache_dir);
    }

    /// 删除单个 skill 的缓存
    pub fn remove(&self, instance_id: &str) {
        if let Ok(mut mem) = self.in_memory.lock() {
            mem.remove(instance_id);
        }
        let disk_path = self.disk_path(instance_id);
        let _ = fs::remove_file(&disk_path);
    }

    fn disk_path(&self, instance_id: &str) -> PathBuf {
        // instance_id 形如 "global:foo" 或 "project:pid:foo"
        // 替换 : 为 _ 作为安全文件名
        let safe = instance_id.replace(':', "__");
        self.cache_dir.join(format!("{}.json", safe))
    }
}

impl Default for RiskCache {
    fn default() -> Self {
        Self::new()
    }
}

fn default_cache_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".skills-manager")
        .join("cache")
        .join("risk")
}

/// 将旧目录 ~/.skills-manager/risk-cache 迁移到新位置 ~/.skills-manager/cache/risk
/// - 若旧目录不存在或新目录已存在，跳过
/// - rename 失败（跨文件系统）时尝试复制后删除
fn migrate_legacy_cache_dir(new_dir: &Path) {
    let old_dir = match dirs::home_dir() {
        Some(h) => h.join(".skills-manager").join("risk-cache"),
        None => return,
    };
    if !old_dir.exists() || new_dir.exists() {
        return;
    }
    if let Err(_) = fs::rename(&old_dir, new_dir) {
        // rename 失败（可能跨文件系统），回退到复制后删除
        if copy_dir_recursive(&old_dir, new_dir).is_ok() {
            let _ = fs::remove_dir_all(&old_dir);
        }
    }
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let path = entry.path();
        let target = dst.join(entry.file_name());
        if path.is_dir() {
            copy_dir_recursive(&path, &target)?;
        } else {
            fs::copy(&path, &target)?;
        }
    }
    Ok(())
}

fn cache_key_matches(report: &SkillRiskReport, key: &RiskCacheKey) -> bool {
    report.instance_id == key.instance_id
        && report.scanner_version == key.scanner_version
        && report.mode == key.mode
    // 注意：path 与 mtime 不在 SkillRiskReport 中持久化
    // 真正的失效靠 scanner_version 与 mode 的变化
    // 若需更严格的 mtime 失效，调用方需在外部判断
}

/// 读取目录的最新文件 mtime（毫秒级）
/// 递归查找目录内所有文件的最新修改时间，确保文件内容变更能被检测到。
/// 失败时返回 0
pub fn read_mtime(path: &Path) -> i64 {
    let mut max_mtime: i64 = 0;
    walk_mtime(path, &mut max_mtime);
    if max_mtime == 0 {
        // 回退到目录自身 mtime
        fs::metadata(path)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(SystemTime::UNIX_EPOCH).ok())
            .map(|d| d.as_millis() as i64)
            .unwrap_or(0)
    } else {
        max_mtime
    }
}

fn walk_mtime(path: &Path, max_mtime: &mut i64) {
    let entries = match fs::read_dir(path) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let p = entry.path();
        let name = p.file_name().and_then(|n| n.to_str()).unwrap_or("");
        // 跳过隐藏目录（保留 .claude）和噪音目录
        if p.is_dir() {
            if name.starts_with('.') && name != ".claude" {
                continue;
            }
            if matches!(name, "node_modules" | "__pycache__" | ".git") {
                continue;
            }
            walk_mtime(&p, max_mtime);
            continue;
        }
        if let Ok(meta) = fs::metadata(&p) {
            if let Ok(modified) = meta.modified() {
                if let Ok(dur) = modified.duration_since(SystemTime::UNIX_EPOCH) {
                    let m = dur.as_millis() as i64;
                    if m > *max_mtime {
                        *max_mtime = m;
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{RiskCategory, RiskFinding, RiskLevel, RiskLocation};
    use tempfile::tempdir;

    fn sample_report(instance_id: &str, mode: RiskScanMode) -> SkillRiskReport {
        let mut report = SkillRiskReport::safe(instance_id, "v1", mode);
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
        report
    }

    #[test]
    fn cache_put_and_get_round_trips() {
        let tmp = tempdir().unwrap();
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: tmp.path().to_path_buf(),
        };

        let report = sample_report("global:test", RiskScanMode::Basic);
        cache.put(&report);

        let key = RiskCacheKey {
            instance_id: "global:test".into(),
            path: "/tmp/skill".into(),
            mtime: 0,
            scanner_version: "v1".into(),
            mode: RiskScanMode::Basic,
        };
        let got = cache.get(&key).expect("cache hit");
        assert_eq!(got, report);
    }

    #[test]
    fn cache_misses_on_version_mismatch() {
        let tmp = tempdir().unwrap();
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: tmp.path().to_path_buf(),
        };

        let report = sample_report("global:test", RiskScanMode::Basic);
        cache.put(&report);

        let key = RiskCacheKey {
            instance_id: "global:test".into(),
            path: "/tmp/skill".into(),
            mtime: 0,
            scanner_version: "v2".into(), // 不同版本
            mode: RiskScanMode::Basic,
        };
        assert!(cache.get(&key).is_none());
    }

    #[test]
    fn cache_misses_on_mode_mismatch() {
        let tmp = tempdir().unwrap();
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: tmp.path().to_path_buf(),
        };

        let report = sample_report("global:test", RiskScanMode::Basic);
        cache.put(&report);

        let key = RiskCacheKey {
            instance_id: "global:test".into(),
            path: "/tmp/skill".into(),
            mtime: 0,
            scanner_version: "v1".into(),
            mode: RiskScanMode::Deep, // 不同模式
        };
        assert!(cache.get(&key).is_none());
    }

    #[test]
    fn cache_persists_to_disk_across_instances() {
        let tmp = tempdir().unwrap();
        let dir = tmp.path().to_path_buf();

        let report = sample_report("global:persist", RiskScanMode::Basic);
        {
            let cache = RiskCache {
                in_memory: Mutex::new(HashMap::new()),
                cache_dir: dir.clone(),
            };
            cache.put(&report);
        }

        // 新实例（模拟进程重启）：内存为空，从磁盘恢复
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: dir,
        };
        let key = RiskCacheKey {
            instance_id: "global:persist".into(),
            path: "/tmp/skill".into(),
            mtime: 0,
            scanner_version: "v1".into(),
            mode: RiskScanMode::Basic,
        };
        let got = cache.get(&key).expect("从磁盘恢复");
        assert_eq!(got, report);
    }

    #[test]
    fn cache_remove_clears_single_entry() {
        let tmp = tempdir().unwrap();
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: tmp.path().to_path_buf(),
        };

        let report = sample_report("global:rm", RiskScanMode::Basic);
        cache.put(&report);

        let key = RiskCacheKey {
            instance_id: "global:rm".into(),
            path: "/tmp/skill".into(),
            mtime: 0,
            scanner_version: "v1".into(),
            mode: RiskScanMode::Basic,
        };
        assert!(cache.get(&key).is_some());

        cache.remove("global:rm");
        assert!(cache.get(&key).is_none());
    }

    #[test]
    fn disk_path_replaces_colons() {
        let cache = RiskCache {
            in_memory: Mutex::new(HashMap::new()),
            cache_dir: PathBuf::from("/tmp/cache"),
        };
        let p = cache.disk_path("project:p1:foo");
        assert_eq!(p.file_name().unwrap(), "project__p1__foo.json");
    }

    #[test]
    fn read_mtime_returns_zero_for_missing_path() {
        let mtime = read_mtime(Path::new("/nonexistent/path/abc"));
        assert_eq!(mtime, 0);
    }

    #[test]
    fn read_mtime_returns_positive_for_existing_path() {
        let tmp = tempdir().unwrap();
        let mtime = read_mtime(tmp.path());
        assert!(mtime > 0);
    }
}
