use std::collections::{HashMap, HashSet};
use std::fs;
use std::future::Future;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use reqwest::{Client, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::models::{
    ClawhubSkillFilesResponse, GitHubContent, InstallResult, InstallStatus, MarketplaceSkill,
    MarketplaceSkillsResponse, MarketplaceSource, SkillFileNode,
};

const CACHE_TTL: Duration = Duration::from_secs(24 * 60 * 60);
const PERSISTED_CACHE_TTL: Duration = Duration::from_secs(24 * 60 * 60);
const GITHUB_API_BASE: &str = "https://api.github.com";
const CLAWHUB_API_BASE: &str = "https://clawhub.ai/api/v1";
const CLAWHUB_SITE_ORIGIN: &str = "https://clawhub.ai";
/// clawhub 列表分页大小：首屏 50 条，与前端"加载更多"行为一致
const CLAWHUB_LIST_PAGE_SIZE: u32 = 50;
/// clawhub 详情缓存条目数上限，防止内存膨胀
const CLAWHUB_DETAIL_CACHE_MAX_ENTRIES: usize = 500;
/// clawhub 归档缓存：预览文件树/文件内容时复用已下载的 ZIP，避免重复下载
const CLAWHUB_ARCHIVE_CACHE_TTL: Duration = Duration::from_secs(10 * 60);
const CLAWHUB_ARCHIVE_CACHE_MAX_ENTRIES: usize = 8;
const MAX_MARKETPLACE_CACHED_PAGES: usize = 200;
const GITHUB_TREE_CACHE_TTL: Duration = Duration::from_secs(10 * 60);
const SKILL_DESCRIPTION_CACHE_TTL: Duration = Duration::from_secs(30 * 60);
const PERSISTED_SKILL_DESCRIPTION_CACHE_TTL: Duration = Duration::from_secs(24 * 60 * 60);
pub(crate) const DIRECT_GITHUB_SOURCE_ID: &str = "github_direct";
pub(crate) const DIRECT_GITHUB_SOURCE_NAME: &str = "GitHub";
// clawhub 默认源常量（在 commands 层用于判断分发）
pub(crate) const CLAWHUB_SOURCE_ID: &str = "src_clawhub";
pub(crate) const CLAWHUB_SOURCE_NAME: &str = "ClawHub";

#[derive(Debug, Clone, Deserialize)]
struct GitHubTreeEntry {
    path: String,
    #[serde(rename = "type")]
    kind: String,
    sha: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
struct GitHubTreeResponse {
    tree: Vec<GitHubTreeEntry>,
}

#[derive(Debug, Clone)]
struct CachedGitHubTree {
    fetched_at: SystemTime,
    branch: String,
    tree: Vec<GitHubTreeEntry>,
}

#[derive(Debug, Clone)]
struct CachedSkillDescription {
    fetched_at: SystemTime,
    description: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PersistedSkillDescriptionEntry {
    fetched_at_unix_secs: u64,
    description: Option<String>,
}

static GITHUB_TREE_CACHE: OnceLock<Mutex<HashMap<String, CachedGitHubTree>>> = OnceLock::new();
static SKILL_DESCRIPTION_CACHE: OnceLock<Mutex<HashMap<String, CachedSkillDescription>>> =
    OnceLock::new();

pub struct MarketplaceCache {
    pages: Mutex<HashMap<MarketplacePageCacheKey, CachedMarketplaceState>>,
    skills_index: Mutex<HashMap<String, MarketplaceSkill>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PersistedMarketplaceCacheEntry {
    page: u32,
    query: Option<String>,
    source_filter: Option<Vec<String>>,
    fetched_at_unix_secs: u64,
    response: MarketplaceSkillsResponse,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct LegacyPersistedMarketplaceState {
    fetched_at_unix_secs: u64,
    skills: Vec<MarketplaceSkill>,
    query: Option<String>,
    has_more: bool,
    source_filter: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct PersistedMarketplaceState {
    pages: Vec<PersistedMarketplaceCacheEntry>,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct MarketplacePageCacheKey {
    page: u32,
    query: Option<String>,
    source_filter: Option<Vec<String>>,
}

#[derive(Debug, Clone)]
struct CachedMarketplaceState {
    fetched_at: SystemTime,
    response: MarketplaceSkillsResponse,
}

fn build_page_cache_key(
    page: u32,
    query: &Option<String>,
    source_filter: &Option<Vec<String>>,
) -> MarketplacePageCacheKey {
    MarketplacePageCacheKey {
        page: page.max(1),
        query: query.clone(),
        source_filter: source_filter.clone(),
    }
}

fn build_marketplace_skill_index(
    pages: &HashMap<MarketplacePageCacheKey, CachedMarketplaceState>,
) -> HashMap<String, MarketplaceSkill> {
    let mut index = HashMap::new();
    for state in pages.values() {
        for skill in &state.response.skills {
            index.insert(skill.id.clone(), skill.clone());
        }
    }
    index
}

fn sorted_marketplace_page_snapshot(
    pages: &HashMap<MarketplacePageCacheKey, CachedMarketplaceState>,
) -> Vec<(MarketplacePageCacheKey, CachedMarketplaceState)> {
    let mut snapshot: Vec<(MarketplacePageCacheKey, CachedMarketplaceState)> = pages
        .iter()
        .map(|(key, state)| (key.clone(), state.clone()))
        .collect();
    snapshot.sort_by(|a, b| b.1.fetched_at.cmp(&a.1.fetched_at));
    snapshot
}

impl Default for MarketplaceCache {
    fn default() -> Self {
        let pages = load_persisted_marketplace_cache_state();
        let skills_index = build_marketplace_skill_index(&pages);
        Self {
            pages: Mutex::new(pages),
            skills_index: Mutex::new(skills_index),
        }
    }
}

impl MarketplaceCache {
    fn rebuild_skill_index_and_persist(
        &self,
        pages: &HashMap<MarketplacePageCacheKey, CachedMarketplaceState>,
    ) {
        if let Ok(mut guard) = self.skills_index.lock() {
            *guard = build_marketplace_skill_index(pages);
        }
        persist_marketplace_cache_state(pages);
    }

    fn prune_expired_pages(pages: &mut HashMap<MarketplacePageCacheKey, CachedMarketplaceState>) {
        let expired: Vec<MarketplacePageCacheKey> = pages
            .iter()
            .filter_map(|(key, state)| {
                state
                    .fetched_at
                    .elapsed()
                    .ok()
                    .filter(|elapsed| *elapsed > CACHE_TTL)
                    .map(|_| key.clone())
            })
            .collect();
        for key in expired {
            pages.remove(&key);
        }
    }

    pub fn get_fresh_with_meta(
        &self,
        page: u32,
        query: &Option<String>,
        source_filter: &Option<Vec<String>>,
    ) -> Option<MarketplaceSkillsResponse> {
        let cache_key = build_page_cache_key(page, query, source_filter);
        let mut guard = self.pages.lock().ok()?;
        Self::prune_expired_pages(&mut guard);
        let response = guard.get(&cache_key).map(|state| state.response.clone());
        let snapshot = guard.clone();
        drop(guard);
        self.rebuild_skill_index_and_persist(&snapshot);
        response
    }

    pub fn set_page(
        &self,
        page: u32,
        query: Option<String>,
        source_filter: Option<Vec<String>>,
        response: MarketplaceSkillsResponse,
    ) {
        let cache_key = build_page_cache_key(page, &query, &source_filter);
        let snapshot = {
            let mut guard = match self.pages.lock() {
                Ok(guard) => guard,
                Err(_) => return,
            };
            Self::prune_expired_pages(&mut guard);
            guard.insert(
                cache_key,
                CachedMarketplaceState {
                    fetched_at: SystemTime::now(),
                    response,
                },
            );

            let mut ordered = sorted_marketplace_page_snapshot(&guard);
            if ordered.len() > MAX_MARKETPLACE_CACHED_PAGES {
                ordered.truncate(MAX_MARKETPLACE_CACHED_PAGES);
                guard.clear();
                for (key, state) in ordered {
                    guard.insert(key, state);
                }
            }
            guard.clone()
        };

        self.rebuild_skill_index_and_persist(&snapshot);
    }

    pub fn set(
        &self,
        skills: Vec<MarketplaceSkill>,
        query: Option<String>,
        has_more: bool,
        source_filter: Option<Vec<String>>,
    ) {
        self.set_page(
            1,
            query,
            source_filter,
            MarketplaceSkillsResponse { skills, has_more },
        );
    }

    pub fn invalidate(&self) {
        if let Ok(mut guard) = self.pages.lock() {
            guard.clear();
        }
        if let Ok(mut guard) = self.skills_index.lock() {
            guard.clear();
        }
        remove_persisted_marketplace_cache_state();
    }

    pub fn get_cached_skill(&self, skill_id: &str) -> Option<MarketplaceSkill> {
        let guard = self.skills_index.lock().ok()?;
        guard.get(skill_id).cloned()
    }

    pub fn get_any(&self) -> Option<Vec<MarketplaceSkill>> {
        let guard = self.skills_index.lock().ok()?;
        if guard.is_empty() {
            None
        } else {
            Some(guard.values().cloned().collect())
        }
    }
}

fn persisted_marketplace_cache_path() -> Option<PathBuf> {
    Some(
        dirs::home_dir()?
            .join(".skills-manager")
            .join("cache")
            .join("marketplace-skills.json"),
    )
}

fn load_persisted_marketplace_cache_state(
) -> HashMap<MarketplacePageCacheKey, CachedMarketplaceState> {
    let Some(path) = persisted_marketplace_cache_path() else {
        return HashMap::new();
    };
    let content = match fs::read_to_string(path) {
        Ok(content) => content,
        Err(_) => return HashMap::new(),
    };
    let (persisted, migrated_from_legacy): (PersistedMarketplaceState, bool) =
        match serde_json::from_str(&content) {
            Ok(persisted) => (persisted, false),
            Err(_) => {
                let legacy: LegacyPersistedMarketplaceState = match serde_json::from_str(&content) {
                    Ok(legacy) => legacy,
                    Err(_) => return HashMap::new(),
                };
                (
                    PersistedMarketplaceState {
                        pages: vec![PersistedMarketplaceCacheEntry {
                            page: 1,
                            query: legacy.query,
                            source_filter: legacy.source_filter,
                            fetched_at_unix_secs: legacy.fetched_at_unix_secs,
                            response: MarketplaceSkillsResponse {
                                skills: legacy.skills,
                                has_more: legacy.has_more,
                            },
                        }],
                    },
                    true,
                )
            }
        };

    let now = SystemTime::now();
    let pages: HashMap<MarketplacePageCacheKey, CachedMarketplaceState> = persisted
        .pages
        .into_iter()
        .filter_map(|entry| {
            let fetched_at = UNIX_EPOCH + Duration::from_secs(entry.fetched_at_unix_secs);
            let elapsed = now.duration_since(fetched_at).ok()?;
            if elapsed > PERSISTED_CACHE_TTL {
                return None;
            }

            Some((
                MarketplacePageCacheKey {
                    page: entry.page.max(1),
                    query: entry.query,
                    source_filter: entry.source_filter,
                },
                CachedMarketplaceState {
                    fetched_at,
                    response: entry.response,
                },
            ))
        })
        .collect();

    if migrated_from_legacy && !pages.is_empty() {
        persist_marketplace_cache_state(&pages);
    }

    pages
}

fn persist_marketplace_cache_state(
    pages: &HashMap<MarketplacePageCacheKey, CachedMarketplaceState>,
) {
    let Some(path) = persisted_marketplace_cache_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }
    let persisted = PersistedMarketplaceState {
        pages: sorted_marketplace_page_snapshot(pages)
            .into_iter()
            .take(MAX_MARKETPLACE_CACHED_PAGES)
            .map(|(key, state)| PersistedMarketplaceCacheEntry {
                page: key.page,
                query: key.query,
                source_filter: key.source_filter,
                fetched_at_unix_secs: state
                    .fetched_at
                    .duration_since(UNIX_EPOCH)
                    .ok()
                    .map(|duration| duration.as_secs())
                    .unwrap_or_default(),
                response: state.response,
            })
            .collect(),
    };
    if let Ok(content) = serde_json::to_string(&persisted) {
        let _ = fs::write(path, content);
    }
}

fn remove_persisted_marketplace_cache_state() {
    let Some(path) = persisted_marketplace_cache_path() else {
        return;
    };
    if path.exists() {
        let _ = fs::remove_file(path);
    }
}

// ===== clawhub.ai API 响应结构 =====
// clawhub 公开 API 无需认证，CORS 全开，Tauri 直连即可。
// 列表端点 GET /api/v1/skills?limit=&cursor=&sort= 返回 items + nextCursor。
// 注意：列表 item 不含 owner，需要用详情端点（?owner=）才能消歧 409。

/// clawhub /api/v1/skills 列表端点的 item
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubListItem {
    slug: String,
    #[serde(rename = "displayName")]
    display_name: Option<String>,
    summary: Option<String>,
    #[serde(rename = "latestVersion")]
    latest_version: Option<ClawhubVersionRef>,
    stats: Option<ClawhubStats>,
    topics: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubVersionRef {
    version: Option<String>,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubStats {
    installs: Option<u64>,
    downloads: Option<u64>,
    stars: Option<u64>,
    comments: Option<u64>,
    versions: Option<u64>,
}

/// clawhub /api/v1/skills 列表响应
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubListResponse {
    items: Vec<ClawhubListItem>,
    /// nextCursor 为 null/缺失时表示无更多页；非空时是一个不透明字符串，需原样回传
    #[serde(rename = "nextCursor", default)]
    next_cursor: Option<String>,
}

/// clawhub /api/v1/search?q= 搜索端点的 item
/// 字段比列表端点少：缺少 topics/stats.installs/latestVersion，
/// 多出 score/version/downloads/ownerHandle/owner。
/// 缺失字段在 map 时给默认值，必要时由前端拉详情补全。
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubSearchItem {
    #[allow(dead_code)]
    score: Option<f64>,
    slug: String,
    #[serde(rename = "displayName")]
    display_name: Option<String>,
    summary: Option<String>,
    #[serde(default)]
    version: Option<String>,
    #[serde(default)]
    downloads: Option<u64>,
    #[serde(rename = "ownerHandle", default)]
    owner_handle: Option<String>,
}

/// clawhub /api/v1/search 响应：不支持 cursor 分页，只返回单页 results
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubSearchResponse {
    #[serde(default)]
    results: Vec<ClawhubSearchItem>,
}

/// clawhub /api/v1/skills/{slug}?owner= 详情响应
#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ClawhubDetailResponse {
    skill: ClawhubDetailSkill,
    #[serde(rename = "latestVersion")]
    latest_version: Option<ClawhubVersionInfo>,
    owner: Option<ClawhubOwner>,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubDetailSkill {
    slug: String,
    #[serde(rename = "displayName")]
    display_name: Option<String>,
    /// 详情端点的 description 字段为完整 SKILL.md 内容
    description: Option<String>,
    summary: Option<String>,
    topics: Option<Vec<String>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubVersionInfo {
    version: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubOwner {
    handle: String,
}

/// 409 AMBIGUOUS_SKILL_SLUG 响应体，列出所有候选 owner
#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubAmbiguousResponse {
    code: String,
    #[serde(default)]
    matches: Vec<ClawhubAmbiguousMatch>,
}

#[allow(dead_code)]
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ClawhubAmbiguousMatch {
    #[serde(rename = "ownerHandle")]
    owner_handle: String,
    slug: String,
    /// ref 是 clawhub 内部版本引用（如 "pskoett/self-improving-agent/4.0.1"）
    #[serde(rename = "ref", default)]
    reference: Option<String>,
    url: Option<String>,
}

/// 详情缓存条目（避免重复请求 clawhub 详情端点）
#[derive(Debug, Clone)]
struct CachedClawhubDetail {
    fetched_at: SystemTime,
    detail: ClawhubDetailResponse,
}

static CLAWHUB_DETAIL_CACHE: OnceLock<Mutex<HashMap<String, CachedClawhubDetail>>> = OnceLock::new();

fn clawhub_detail_cache() -> &'static Mutex<HashMap<String, CachedClawhubDetail>> {
    CLAWHUB_DETAIL_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn clawhub_detail_cache_key(slug: &str, owner: Option<&str>) -> String {
    format!("{}::{}", slug, owner.unwrap_or_default())
}

fn get_cached_clawhub_detail(slug: &str, owner: Option<&str>) -> Option<ClawhubDetailResponse> {
    let mut guard = clawhub_detail_cache().lock().ok()?;
    let key = clawhub_detail_cache_key(slug, owner);
    let cached = guard.get(&key).cloned()?;
    if cached.fetched_at.elapsed().ok()? > CACHE_TTL {
        guard.remove(&key);
        return None;
    }
    Some(cached.detail)
}

fn set_cached_clawhub_detail(slug: &str, owner: Option<&str>, detail: ClawhubDetailResponse) {
    if let Ok(mut guard) = clawhub_detail_cache().lock() {
        let key = clawhub_detail_cache_key(slug, owner);
        if guard.len() >= CLAWHUB_DETAIL_CACHE_MAX_ENTRIES && !guard.contains_key(&key) {
            // 简单淘汰：删掉最早插入的一个（不是严格 LRU，但够用）
            if let Some(first_key) = guard.keys().next().cloned() {
                guard.remove(&first_key);
            }
        }
        guard.insert(
            key,
            CachedClawhubDetail {
                fetched_at: SystemTime::now(),
                detail,
            },
        );
    }
}

/// clawhub 列表分页的 cursor 缓存：page N → nextCursor
/// 因为 clawhub 用游标分页，前端用 page 翻页时需要逐页推进 cursor。
#[derive(Debug, Clone, Default)]
struct ClawhubCursorMap {
    /// page N → nextCursor（page 1 的 cursor 为 None，从首页开始）
    cursors: HashMap<u32, Option<String>>,
}

impl ClawhubCursorMap {
    fn cursor_for_page(&self, page: u32) -> Option<&Option<String>> {
        self.cursors.get(&page)
    }

    fn set_cursor(&mut self, page: u32, cursor: Option<String>) {
        self.cursors.insert(page, cursor);
    }
}

/// 全局 cursor 缓存（按 query 维度隔离）
static CLAWHUB_CURSOR_CACHE: OnceLock<Mutex<HashMap<String, ClawhubCursorMap>>> = OnceLock::new();

fn clawhub_cursor_cache() -> &'static Mutex<HashMap<String, ClawhubCursorMap>> {
    CLAWHUB_CURSOR_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn clawhub_cursor_cache_key(query: Option<&str>, sort: Option<&str>) -> String {
    format!("{}::{}", query.unwrap_or_default(), sort.unwrap_or_default())
}

/// clawhub 归档缓存条目
struct CachedClawhubArchive {
    files: Vec<(String, Vec<u8>)>,
    fetched_at: Instant,
}

/// 全局 clawhub 归档缓存（预览文件树/文件内容时复用已下载的 ZIP）
static CLAWHUB_ARCHIVE_CACHE: OnceLock<Mutex<HashMap<String, CachedClawhubArchive>>> =
    OnceLock::new();

fn clawhub_archive_cache() -> &'static Mutex<HashMap<String, CachedClawhubArchive>> {
    CLAWHUB_ARCHIVE_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn clawhub_archive_cache_key(slug: &str, owner: Option<&str>, version: &str) -> String {
    format!("{}::{}::{}", slug, owner.unwrap_or(""), version)
}

/// 从缓存中获取 clawhub 归档文件列表（未过期时返回克隆）
fn get_cached_clawhub_archive(
    slug: &str,
    owner: Option<&str>,
    version: &str,
) -> Option<Vec<(String, Vec<u8>)>> {
    let cache = clawhub_archive_cache().lock().ok()?;
    let key = clawhub_archive_cache_key(slug, owner, version);
    let entry = cache.get(&key)?;
    if entry.fetched_at.elapsed() < CLAWHUB_ARCHIVE_CACHE_TTL {
        Some(entry.files.clone())
    } else {
        None
    }
}

/// 将 clawhub 归档文件列表写入缓存（简单 LRU：满时淘汰最老条目）
fn set_cached_clawhub_archive(
    slug: &str,
    owner: Option<&str>,
    version: &str,
    files: Vec<(String, Vec<u8>)>,
) {
    let mut cache = match clawhub_archive_cache().lock() {
        Ok(c) => c,
        Err(_) => return,
    };
    let key = clawhub_archive_cache_key(slug, owner, version);
    if cache.len() >= CLAWHUB_ARCHIVE_CACHE_MAX_ENTRIES {
        if let Some(oldest_key) = cache
            .iter()
            .min_by_key(|(_, v)| v.fetched_at)
            .map(|(k, _)| k.clone())
        {
            cache.remove(&oldest_key);
        }
    }
    cache.insert(
        key,
        CachedClawhubArchive {
            files,
            fetched_at: Instant::now(),
        },
    );
}

fn clawhub_client() -> Result<Client, String> {
    Client::builder()
        .user_agent("skills-manager")
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|e| format!("无法创建 HTTP 客户端: {}", e))
}

/// 将 clawhub 列表 item 转换为 MarketplaceSkill。
/// 列表端点不返回 owner，因此 clawhub_owner 留空（在详情端点拉取时再填充）。
fn map_clawhub_list_item_to_skill(item: ClawhubListItem) -> MarketplaceSkill {
    let slug = item.slug;
    let name = item
        .display_name
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| slug.clone());
    let description = item
        .summary
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let install_count = item
        .stats
        .as_ref()
        .and_then(|stats| stats.installs)
        .or_else(|| item.stats.as_ref().and_then(|stats| stats.downloads));
    let clawhub_version = item
        .latest_version
        .as_ref()
        .and_then(|version| version.version.clone())
        .filter(|value| !value.trim().is_empty());
    let tags = item.topics.unwrap_or_default();

    MarketplaceSkill {
        id: format!("{}::{}", CLAWHUB_SOURCE_ID, slug),
        slug: Some(slug.clone()),
        name,
        description,
        author: None,
        source_id: CLAWHUB_SOURCE_ID.to_string(),
        source_name: CLAWHUB_SOURCE_NAME.to_string(),
        install_count,
        install_url: None,
        created_at: None,
        repo_url: None,
        skill_path: Some(slug.clone()),
        // 列表端点不返回 owner，无法构造正确的外部链接（需 {origin}/{owner}/skills/{slug}）。
        // external_url 留空，待详情端点解析出 owner 后由前端补全。
        external_url: None,
        remote_revision: clawhub_version.clone(),
        tags,
        install_status: InstallStatus::NotInstalled,
        clawhub_slug: Some(slug),
        clawhub_owner: None,
        clawhub_version,
    }
}

/// 将 clawhub 搜索 item 转换为 MarketplaceSkill。
/// 搜索端点不返回 topics/stats.installs/latestVersion，缺失字段给默认值。
/// 返回 owner_handle（列表端点没有），可用于直接构造 external_url。
fn map_clawhub_search_item_to_skill(item: ClawhubSearchItem) -> MarketplaceSkill {
    let slug = item.slug.clone();
    let name = item
        .display_name
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| slug.clone());
    let description = item
        .summary
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let clawhub_owner = item
        .owner_handle
        .filter(|value| !value.trim().is_empty());
    let clawhub_version = item
        .version
        .filter(|value| !value.trim().is_empty());
    // 搜索端点的 downloads 近似为 install_count（端点不返回 installs）
    let install_count = item.downloads;
    // external_url 需要 owner；有 owner 时直接构造，避免前端再拉详情
    let external_url = clawhub_owner.as_ref().map(|owner| {
        format!("{}/{}/skills/{}", CLAWHUB_SITE_ORIGIN, owner, slug)
    });

    MarketplaceSkill {
        id: format!("{}::{}", CLAWHUB_SOURCE_ID, slug),
        slug: Some(slug.clone()),
        name,
        description,
        // 用 owner 作为 author 显示（搜索端点不单独返回 author）
        author: clawhub_owner.clone(),
        source_id: CLAWHUB_SOURCE_ID.to_string(),
        source_name: CLAWHUB_SOURCE_NAME.to_string(),
        install_count,
        install_url: None,
        created_at: None,
        repo_url: None,
        skill_path: Some(slug.clone()),
        external_url,
        remote_revision: clawhub_version.clone(),
        // 搜索端点不返回 topics，tags 暂为空，详情端点可补全
        tags: Vec::new(),
        install_status: InstallStatus::NotInstalled,
        clawhub_slug: Some(slug),
        clawhub_owner,
        clawhub_version,
    }
}

pub struct MarketplaceService;

fn normalize_marketplace_query(query: Option<&str>) -> Option<String> {
    query
        .map(str::trim)
        .filter(|q| !q.is_empty())
        .map(|q| q.to_lowercase())
}

fn marketplace_skill_matches_query(skill: &MarketplaceSkill, query: &str) -> bool {
    // 分词 AND 匹配：query 按空白拆分为多个 token，每个 token 必须命中至少一个字段。
    // 这样 "email gmail" 能匹配 name="Email" + description="...Gmail..."，
    // 同时兼容单 token 场景（退化为原 OR 字段匹配）。
    let tokens: Vec<&str> = query.split_whitespace().collect();
    if tokens.is_empty() {
        return true;
    }
    tokens.iter().all(|token| skill_matches_token(skill, token))
}

/// 单个 token 是否命中 skill 的任意字段（大小写不敏感的子串包含）。
fn skill_matches_token(skill: &MarketplaceSkill, token: &str) -> bool {
    let token = token.to_lowercase();
    if token.is_empty() {
        return true;
    }
    skill.name.to_lowercase().contains(&token)
        || skill
            .slug
            .as_ref()
            .map(|slug| slug.to_lowercase().contains(&token))
            .unwrap_or(false)
        || skill
            .description
            .as_ref()
            .map(|d| d.to_lowercase().contains(&token))
            .unwrap_or(false)
        || skill
            .author
            .as_ref()
            .map(|a| a.to_lowercase().contains(&token))
            .unwrap_or(false)
        || skill.source_name.to_lowercase().contains(&token)
        || skill.tags.iter().any(|tag| tag.to_lowercase().contains(&token))
}

fn filter_marketplace_skills_by_query(
    skills: Vec<MarketplaceSkill>,
    query: Option<&str>,
) -> Vec<MarketplaceSkill> {
    let Some(normalized_query) = normalize_marketplace_query(query) else {
        return skills;
    };

    skills
        .into_iter()
        .filter(|skill| marketplace_skill_matches_query(skill, &normalized_query))
        .collect()
}

impl MarketplaceService {
    pub(crate) fn filter_marketplace_skills_by_query(
        skills: Vec<MarketplaceSkill>,
        query: Option<&str>,
    ) -> Vec<MarketplaceSkill> {
        filter_marketplace_skills_by_query(skills, query)
    }

    /// 拉取 clawhub 列表分页。clawhub 用游标分页，前端按 page 翻页时
    /// 需要逐页推进 cursor，因此这里维护一个 cursor 缓存：page N → nextCursor。
    /// 当请求的 page 在缓存中没有 cursor 时，会从最近已知的页开始向后逐页推进，
    /// 直到拿到目标页的数据。
    pub async fn fetch_marketplace_skills_page(
        skills_dir: &Path,
        query: Option<String>,
        page: u32,
    ) -> Result<MarketplaceSkillsResponse, String> {
        let page = page.max(1);
        let trimmed_query = query
            .as_deref()
            .map(str::trim)
            .filter(|q| !q.is_empty())
            .map(|q| q.to_string());

        // 有搜索词时走 /api/v1/search 真搜索（可搜全库，不受分页限制），
        // 无搜索词时走 /api/v1/skills 列表分页（按 installs 排序）。
        if let Some(q) = &trimmed_query {
            return Self::fetch_clawhub_search_page(q, skills_dir).await;
        }

        let sort = Some("installs");

        // 1. 拿到目标 page 的 cursor（必要时逐页推进）
        let cursor = Self::resolve_clawhub_cursor_for_page(&trimmed_query, sort, page).await?;

        // 2. 用 cursor 拉取目标页数据
        let client = clawhub_client()?;
        let mut req = client
            .get(format!("{}/skills", CLAWHUB_API_BASE))
            .query(&[("limit", CLAWHUB_LIST_PAGE_SIZE.to_string().as_str())]);
        if let Some(s) = sort {
            req = req.query(&[("sort", s)]);
        }
        if let Some(c) = cursor.as_deref() {
            req = req.query(&[("cursor", c)]);
        }
        let resp = req.send().await.map_err(|e| format!("技能市场请求失败: {}", e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(format!("技能市场请求失败: HTTP {status}"));
        }
        let body: ClawhubListResponse = resp
            .json()
            .await
            .map_err(|e| format!("技能市场响应解析失败: {}", e))?;

        // 3. 记录本页返回的 nextCursor，供 page+1 使用
        let has_more = body.next_cursor.is_some();
        Self::record_clawhub_cursor(&trimmed_query, sort, page, body.next_cursor.clone());

        // 4. 映射为 MarketplaceSkill
        let skills = body
            .items
            .into_iter()
            .map(map_clawhub_list_item_to_skill)
            .collect::<Vec<_>>();

        // 5. 标记安装状态
        let mut skills = skills;
        for skill in skills.iter_mut() {
            skill.install_status = Self::check_install_status(skill, skills_dir);
        }

        Ok(MarketplaceSkillsResponse { skills, has_more })
    }

    /// 通过 Clawhub /api/v1/search?q= 端点搜索全库。
    /// 该端点不支持 cursor 分页，单次返回所有命中结果（按 score 排序），
    /// 因此 has_more 永远为 false，前端不应在搜索模式下显示"加载更多"。
    async fn fetch_clawhub_search_page(
        query: &str,
        skills_dir: &Path,
    ) -> Result<MarketplaceSkillsResponse, String> {
        let client = clawhub_client()?;
        let resp = client
            .get(format!("{}/search", CLAWHUB_API_BASE))
            .query(&[("q", query)])
            .send()
            .await
            .map_err(|e| format!("技能市场搜索请求失败: {}", e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(format!("技能市场搜索请求失败: HTTP {status}"));
        }
        let body: ClawhubSearchResponse = resp
            .json()
            .await
            .map_err(|e| format!("技能市场搜索响应解析失败: {}", e))?;

        let mut skills: Vec<MarketplaceSkill> = body
            .results
            .into_iter()
            .map(map_clawhub_search_item_to_skill)
            .collect();

        for skill in skills.iter_mut() {
            skill.install_status = Self::check_install_status(skill, skills_dir);
        }

        // 搜索端点不分页，无更多页
        Ok(MarketplaceSkillsResponse {
            skills,
            has_more: false,
        })
    }

    /// 解析 page N 对应的 cursor。如果缓存中没有，从最近已知的 page 开始向后逐页推进，
    /// 直到拿到目标 page 的 cursor（或耗尽 has_more）。
    async fn resolve_clawhub_cursor_for_page(
        query: &Option<String>,
        sort: Option<&str>,
        target_page: u32,
    ) -> Result<Option<String>, String> {
        if target_page <= 1 {
            return Ok(None);
        }

        let cache_key = clawhub_cursor_cache_key(query.as_deref(), sort);
        let client = clawhub_client()?;

        // 在缓存中查找 target_page 的 cursor
        let cached_cursor = {
            let guard = clawhub_cursor_cache().lock().ok();
            if let Some(guard) = guard {
                if let Some(map) = guard.get(&cache_key) {
                    if let Some(cursor) = map.cursor_for_page(target_page) {
                        return Ok(cursor.clone());
                    }
                    // 找到最大已知 page
                    let max_known = map.cursors.keys().copied().max().unwrap_or(1);
                    if max_known >= target_page {
                        // 已知但 cursor 为 None，说明没有下一页
                        return Ok(None);
                    }
                    Some((max_known, map.cursor_for_page(max_known).cloned().flatten()))
                } else {
                    None
                }
            } else {
                None
            }
        };

        let (start_page, start_cursor) = cached_cursor.unwrap_or((1, None));

        // 从 start_page+1 开始拉取，直到拿到 target_page 的 cursor
        let mut current_cursor = start_cursor;
        let mut current_page = start_page;
        loop {
            if current_page >= target_page {
                // 已经拿到目标页 cursor（在 record_clawhub_cursor 中已记录）
                let guard = clawhub_cursor_cache().lock().ok();
                if let Some(guard) = guard {
                    if let Some(map) = guard.get(&cache_key) {
                        if let Some(cursor) = map.cursor_for_page(target_page) {
                            return Ok(cursor.clone());
                        }
                    }
                }
                return Ok(None);
            }

            let next_page = current_page + 1;
            let mut req = client
                .get(format!("{}/skills", CLAWHUB_API_BASE))
                .query(&[("limit", CLAWHUB_LIST_PAGE_SIZE.to_string().as_str())]);
            if let Some(s) = sort {
                req = req.query(&[("sort", s)]);
            }
            if let Some(c) = current_cursor.as_deref() {
                req = req.query(&[("cursor", c)]);
            }
            let resp = req.send().await.map_err(|e| format!("技能市场请求失败: {}", e))?;
            let status = resp.status();
            if !status.is_success() {
                return Err(format!("技能市场请求失败: HTTP {status}"));
            }
            let body: ClawhubListResponse = resp
                .json()
                .await
                .map_err(|e| format!("技能市场响应解析失败: {}", e))?;

            Self::record_clawhub_cursor(query, sort, next_page, body.next_cursor.clone());

            if body.next_cursor.is_none() {
                // 没有更多页了
                return Ok(None);
            }
            current_cursor = body.next_cursor;
            current_page = next_page;
        }
    }

    fn record_clawhub_cursor(
        query: &Option<String>,
        sort: Option<&str>,
        page: u32,
        cursor: Option<String>,
    ) {
        if let Ok(mut guard) = clawhub_cursor_cache().lock() {
            let key = clawhub_cursor_cache_key(query.as_deref(), sort);
            let map = guard.entry(key).or_default();
            map.set_cursor(page, cursor);
        }
    }

    /// 拉取 clawhub skill 详情。如果 slug 冲突（409），自动选择 downloads 最高的 owner 重试。
    /// 结果会缓存 24 小时，避免重复请求。
    pub async fn fetch_clawhub_skill_detail(
        slug: &str,
        owner: Option<&str>,
    ) -> Result<ClawhubDetailResponse, String> {
        if let Some(cached) = get_cached_clawhub_detail(slug, owner) {
            return Ok(cached);
        }

        let client = clawhub_client()?;
        let mut current_owner = owner.map(|o| o.to_string());

        loop {
            if let Some(cached) = get_cached_clawhub_detail(slug, current_owner.as_deref()) {
                return Ok(cached);
            }

            let mut req = client.get(format!("{}/skills/{}", CLAWHUB_API_BASE, slug));
            if let Some(o) = current_owner.as_deref() {
                req = req.query(&[("owner", o)]);
            }
            let resp = req
                .send()
                .await
                .map_err(|e| format!("技能市场详情请求失败: {}", e))?;
            let status = resp.status();

            if status == StatusCode::CONFLICT {
                // 409 AMBIGUOUS_SKILL_SLUG：自动消歧
                let body = resp.text().await.map_err(|e| format!("读取 409 响应失败: {}", e))?;
                let ambiguous: ClawhubAmbiguousResponse = serde_json::from_str(&body)
                    .map_err(|e| format!("解析 409 响应失败: {}", e))?;
                if ambiguous.matches.is_empty() {
                    return Err(format!("skill '{}' 存在多个作者但未返回候选列表", slug));
                }
                // 选择第一个候选（clawhub 通常按热度排序返回候选）
                let best_owner = ambiguous.matches[0].owner_handle.clone();
                current_owner = Some(best_owner);
                continue;
            }

            if !status.is_success() {
                return Err(format!("技能市场详情请求失败: HTTP {status}"));
            }

            let detail: ClawhubDetailResponse = resp
                .json()
                .await
                .map_err(|e| format!("技能市场详情响应解析失败: {}", e))?;

            // 用实际返回的 owner 作为缓存 key（避免缓存 key 不一致）
            let effective_owner = detail
                .owner
                .as_ref()
                .map(|o| o.handle.as_str())
                .or(current_owner.as_deref());
            set_cached_clawhub_detail(slug, effective_owner, detail.clone());

            return Ok(detail);
        }
    }

    /// 下载并解压 clawhub skill 归档（ZIP）。
    /// 返回 (相对路径, 文件字节) 列表，已过滤掉 clawhub 元数据文件（_meta.json, skill-card.md）。
    pub async fn download_clawhub_skill_archive(
        slug: &str,
        owner: Option<&str>,
        version: &str,
    ) -> Result<Vec<(String, Vec<u8>)>, String> {
        let client = clawhub_client()?;
        let mut req = client.get(format!("{}/download", CLAWHUB_API_BASE));
        req = req.query(&[("slug", slug), ("version", version)]);
        if let Some(o) = owner {
            req = req.query(&[("ownerHandle", o)]);
        }

        let resp = req.send().await.map_err(|e| format!("下载 skill 归档失败: {}", e))?;
        let status = resp.status();
        if !status.is_success() {
            return Err(format!("下载 skill 归档失败: HTTP {status}"));
        }
        let bytes = resp
            .bytes()
            .await
            .map_err(|e| format!("读取 skill 归档失败: {}", e))?;

        // 解压 ZIP
        let cursor = std::io::Cursor::new(&bytes[..]);
        let mut zip = zip::ZipArchive::new(cursor).map_err(|e| format!("解压归档失败: {}", e))?;

        let mut files = Vec::new();
        for i in 0..zip.len() {
            let mut entry = zip
                .by_index(i)
                .map_err(|e| format!("读取归档条目失败: {}", e))?;
            let name = entry.name().to_string();
            if entry.is_dir() {
                continue;
            }
            // 过滤 clawhub 元数据文件
            if name == "_meta.json" || name == "skill-card.md" {
                continue;
            }
            let mut buf = Vec::new();
            entry
                .read_to_end(&mut buf)
                .map_err(|e| format!("读取归档文件失败: {}", e))?;
            files.push((name, buf));
        }

        if files.is_empty() {
            return Err(format!("skill '{}' 归档为空", slug));
        }

        Ok(files)
    }

    /// 下载 clawhub 技能归档并构建文件树，用于详情弹窗预览。
    /// 若 owner/version 缺失，会先拉取详情端点补全。
    /// 归档会缓存 10 分钟，供后续文件内容请求复用。
    /// 返回的 ClawhubSkillFilesResponse 携带解析出的 owner/version，
    /// 供前端补全 skill 元数据并构造正确的外部链接。
    pub async fn fetch_clawhub_skill_files(
        slug: &str,
        owner: Option<&str>,
        version: Option<&str>,
    ) -> Result<ClawhubSkillFilesResponse, String> {
        let mut resolved_owner = owner.map(|o| o.to_string());
        let mut resolved_version = version.map(|v| v.to_string());

        if resolved_owner.is_none() || resolved_version.is_none() {
            let detail = Self::fetch_clawhub_skill_detail(slug, resolved_owner.as_deref()).await?;
            if resolved_owner.is_none() {
                resolved_owner = detail.owner.map(|o| o.handle);
            }
            if resolved_version.is_none() {
                resolved_version = detail.latest_version.map(|v| v.version);
            }
        }

        let version_str = resolved_version
            .ok_or_else(|| format!("clawhub skill '{}' 未返回版本号", slug))?;

        let files = if let Some(cached) =
            get_cached_clawhub_archive(slug, resolved_owner.as_deref(), &version_str)
        {
            cached
        } else {
            let downloaded = Self::download_clawhub_skill_archive(
                slug,
                resolved_owner.as_deref(),
                &version_str,
            )
            .await?;
            set_cached_clawhub_archive(
                slug,
                resolved_owner.as_deref(),
                &version_str,
                downloaded.clone(),
            );
            downloaded
        };

        let tree = build_clawhub_skill_tree(
            &files,
            slug,
            resolved_owner.as_deref(),
            &version_str,
        );

        Ok(ClawhubSkillFilesResponse {
            tree,
            resolved_owner,
            resolved_version: Some(version_str),
        })
    }

    #[allow(dead_code)]
    pub async fn fetch_github_repo(
        source: &MarketplaceSource,
        github_token: Option<&str>,
    ) -> Result<Vec<MarketplaceSkill>, String> {
        let (owner, repo) = parse_github_repo_url(&source.url)?;
        let client = github_client()?;
        let hinted_skill_dirs =
            fetch_github_root_skill_dirs_from_tree(&client, &owner, &repo, github_token).await;
        let cached_tree = get_cached_github_tree(&owner, &repo);
        let contents = match fetch_github_contents(&client, &owner, &repo, "", github_token).await {
            Ok(contents) => contents,
            Err(err) => {
                if err.contains("GitHub API 请求受限") {
                    let dirs = fetch_github_root_dirs_from_html(&client, &owner, &repo).await?;
                    dirs.into_iter()
                        .map(|dir| GitHubContent {
                            name: dir.clone(),
                            path: dir,
                            kind: "dir".to_string(),
                            download_url: None,
                            url: None,
                            size: None,
                        })
                        .collect()
                } else {
                    return Err(err);
                }
            }
        };

        let mut skills = Vec::new();
        for item in contents
            .into_iter()
            .filter(|item| should_include_github_root_dir(item, hinted_skill_dirs.as_ref()))
        {
            let skill_path = item.path.clone();
            let repo_url = Some(source.url.clone());
            let skill_path_opt = Some(skill_path.clone());
            let remote_revision = cached_tree
                .as_ref()
                .and_then(|tree| compute_skill_revision_from_tree_entries(&tree.tree, &skill_path));
            skills.push(MarketplaceSkill {
                id: make_marketplace_skill_id(&source.id, &skill_path),
                slug: Some(skill_path.clone()),
                name: item.name.clone(),
                description: None,
                author: Some(owner.clone()),
                source_id: source.id.clone(),
                source_name: source.name.clone(),
                install_count: None,
                install_url: None,
                created_at: None,
                repo_url: repo_url.clone(),
                skill_path: skill_path_opt.clone(),
                external_url: build_marketplace_external_url(
                    None,
                    repo_url.as_deref(),
                    skill_path_opt.as_deref(),
                ),
                remote_revision,
                tags: Vec::new(),
                install_status: InstallStatus::NotInstalled,
                clawhub_slug: None,
                clawhub_owner: None,
                clawhub_version: None,
            });
        }

        Ok(skills)
    }

    pub async fn fetch_skill_files(
        repo_url: &str,
        skill_path: &str,
        github_token: Option<&str>,
    ) -> Result<SkillFileNode, String> {
        let (owner, repo) = parse_github_repo_url(repo_url)?;
        let client = github_client()?;
        let candidates = build_skill_path_candidates(skill_path);
        let mut attempted_candidates: HashSet<String> = HashSet::new();
        let mut last_not_found_error: Option<String> = None;

        for candidate in candidates {
            attempted_candidates.insert(candidate.clone());
            if let Some(tree) =
                fetch_skill_files_from_tree_api(&client, &owner, &repo, &candidate, github_token)
                    .await?
            {
                return Ok(tree);
            }

            match build_github_tree(&client, &owner, &repo, &candidate, github_token).await {
                Ok(tree) => return Ok(tree),
                Err(err) => {
                    if err.contains("GitHub API 请求受限") {
                        if let Some(tree) =
                            fetch_skill_files_from_raw(&owner, &repo, &candidate).await?
                        {
                            return Ok(tree);
                        }
                        continue;
                    }
                    if is_github_not_found_error(&err) {
                        last_not_found_error = Some(err);
                        continue;
                    }
                    return Err(err);
                }
            }
        }

        let inferred_candidates = infer_skill_path_candidates_from_repo_tree(
            &client,
            &owner,
            &repo,
            skill_path,
            github_token,
        )
        .await?;

        for candidate in inferred_candidates {
            if attempted_candidates.contains(&candidate) {
                continue;
            }
            attempted_candidates.insert(candidate.clone());

            if let Some(tree) =
                fetch_skill_files_from_tree_api(&client, &owner, &repo, &candidate, github_token)
                    .await?
            {
                return Ok(tree);
            }

            match build_github_tree(&client, &owner, &repo, &candidate, github_token).await {
                Ok(tree) => return Ok(tree),
                Err(err) => {
                    if err.contains("GitHub API 请求受限") {
                        if let Some(tree) =
                            fetch_skill_files_from_raw(&owner, &repo, &candidate).await?
                        {
                            return Ok(tree);
                        }
                        continue;
                    }
                    if is_github_not_found_error(&err) {
                        last_not_found_error = Some(err);
                        continue;
                    }
                    return Err(err);
                }
            }
        }

        Err(last_not_found_error.unwrap_or_else(|| "Skill 文件不存在或路径无效".to_string()))
    }

    pub async fn fetch_skill_file_content(download_url: &str) -> Result<String, String> {
        if download_url.starts_with("clawhub:") {
            return Self::fetch_clawhub_skill_file_content(download_url).await;
        }
        let client = Client::new();
        let response = client
            .get(download_url)
            .send()
            .await
            .map_err(|e| format!("文件请求失败: {}", e))?;

        if !response.status().is_success() {
            return Err(format!("文件请求失败: HTTP {}", response.status()));
        }

        response
            .text()
            .await
            .map_err(|e| format!("文件读取失败: {}", e))
    }

    /// 从 clawhub 归档中获取单个文件内容。
    /// download_url 格式: `clawhub:{slug}|{owner}|{version}|{path}`
    async fn fetch_clawhub_skill_file_content(download_url: &str) -> Result<String, String> {
        let rest = download_url
            .strip_prefix("clawhub:")
            .ok_or("无效的 clawhub URL")?;
        let parts: Vec<&str> = rest.splitn(4, '|').collect();
        if parts.len() != 4 {
            return Err("无效的 clawhub 文件 URL".to_string());
        }
        let slug = parts[0];
        let owner = if parts[1].is_empty() { None } else { Some(parts[1]) };
        let version = parts[2];
        let file_path = parts[3];

        let files = if let Some(cached) = get_cached_clawhub_archive(slug, owner, version) {
            cached
        } else {
            let downloaded =
                Self::download_clawhub_skill_archive(slug, owner, version).await?;
            set_cached_clawhub_archive(slug, owner, version, downloaded.clone());
            downloaded
        };

        for (path, bytes) in &files {
            let stripped = strip_archive_top_level_prefix(path, slug);
            if stripped == file_path {
                return String::from_utf8(bytes.clone())
                    .map_err(|e| format!("文件不是有效的 UTF-8 文本: {}", e));
            }
        }

        Err(format!("在归档中未找到文件: {}", file_path))
    }

    pub async fn fetch_skill_description(
        repo_url: &str,
        skill_path: &str,
        github_token: Option<&str>,
    ) -> Option<String> {
        let normalized_repo_url = repo_url.trim();
        let normalized_skill_path = skill_path.trim_matches('/');
        if normalized_repo_url.is_empty() {
            return None;
        }

        let cache_key =
            make_skill_description_cache_key(normalized_repo_url, normalized_skill_path);
        if let Some(cached) = get_cached_skill_description(&cache_key) {
            return cached;
        }

        let description = Self::fetch_skill_description_uncached(
            normalized_repo_url,
            normalized_skill_path,
            github_token,
        )
        .await;

        set_cached_skill_description(&cache_key, description.clone());
        description
    }

    async fn fetch_skill_description_uncached(
        repo_url: &str,
        skill_path: &str,
        github_token: Option<&str>,
    ) -> Option<String> {
        let (owner, repo) = parse_github_repo_url(repo_url).ok()?;
        let client = github_client().ok()?;
        for candidate in build_skill_path_candidates(skill_path) {
            let mut download_url = None;
            if let Ok(Some(tree)) =
                fetch_skill_files_from_tree_api(&client, &owner, &repo, &candidate, github_token)
                    .await
            {
                download_url = find_manifest_download_url_in_tree(&tree);
            }

            if download_url.is_none() {
                download_url =
                    find_manifest_download_url_from_raw(&client, &owner, &repo, &candidate).await;
            }

            if let Some(url) = download_url {
                let markdown = Self::fetch_skill_file_content(url.as_str()).await.ok()?;
                if let Some(description) = extract_skill_description_from_markdown(&markdown) {
                    return Some(description);
                }
            }
        }

        None
    }

    pub async fn install_skill(
        skill: &MarketplaceSkill,
        skills_dir: &Path,
        github_token: Option<&str>,
    ) -> Result<InstallResult, String> {
        // 按 source_id 分发：clawhub 源走归档下载，其他源走原 GitHub 逻辑
        if skill.source_id == CLAWHUB_SOURCE_ID {
            Self::install_clawhub_skill(skill, skills_dir).await
        } else {
            Self::install_github_skill(skill, skills_dir, github_token).await
        }
    }

    /// 从 clawhub 下载 ZIP 归档并解压到本地 skills 目录。
    /// 如果 skill 的 owner/version 缺失，会先拉取详情端点补全。
    async fn install_clawhub_skill(
        skill: &MarketplaceSkill,
        skills_dir: &Path,
    ) -> Result<InstallResult, String> {
        let slug = skill
            .clawhub_slug
            .as_deref()
            .or(skill.slug.as_deref())
            .ok_or_else(|| "clawhub skill 缺少 slug，无法安装".to_string())?;

        // 补全 owner / version（详情端点会消歧 409）
        let owner = match skill.clawhub_owner.as_deref() {
            Some(value) if !value.trim().is_empty() => Some(value.to_string()),
            _ => {
                let detail = Self::fetch_clawhub_skill_detail(slug, None).await?;
                detail
                    .owner
                    .as_ref()
                    .map(|owner| owner.handle.clone())
                    .filter(|value| !value.trim().is_empty())
            }
        };

        let version = match skill.clawhub_version.as_deref() {
            Some(value) if !value.trim().is_empty() => value.to_string(),
            _ => {
                let detail = Self::fetch_clawhub_skill_detail(slug, owner.as_deref()).await?;
                detail
                    .latest_version
                    .as_ref()
                    .map(|version| version.version.clone())
                    .ok_or_else(|| format!("clawhub skill '{}' 未返回版本号", slug))?
            }
        };

        let install_dir = preferred_marketplace_install_dir(skills_dir, skill);
        let legacy_install_dir = legacy_marketplace_install_dir(skills_dir, skill);

        if install_dir.exists() {
            if !is_same_marketplace_skill(&install_dir, skill)? {
                return Err("本地已存在同名 Skill（非市场来源），请重命名".to_string());
            }
            fs::remove_dir_all(&install_dir)
                .map_err(|e| format!("无法覆盖已有 Skill: {}", e))?;
        }
        if let Some(legacy_dir) = legacy_install_dir {
            if legacy_dir.exists() && is_same_marketplace_skill(&legacy_dir, skill)? {
                fs::remove_dir_all(&legacy_dir)
                    .map_err(|e| format!("无法迁移旧版 Skill 目录: {}", e))?;
            }
        }

        if !skills_dir.exists() {
            fs::create_dir_all(skills_dir).map_err(|e| format!("无法创建 Skills 目录: {}", e))?;
        }
        fs::create_dir_all(&install_dir)
            .map_err(|e| format!("无法创建 Skill 目录: {}", e))?;

        let files = Self::download_clawhub_skill_archive(slug, owner.as_deref(), &version).await?;
        for (relative_path, bytes) in files {
            let relative_path = relative_path.trim_start_matches("./");
            // 如果归档内文件带顶层目录（如 "skill-name/SKILL.md"），剥离到 SKILL.md
            let stripped = strip_archive_top_level_prefix(relative_path, slug);
            if stripped.is_empty() || stripped == "." {
                continue;
            }
            let target_path = install_dir.join(&stripped);
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent).map_err(|e| format!("无法创建目录: {}", e))?;
            }
            fs::write(&target_path, &bytes).map_err(|e| format!("写入文件失败: {}", e))?;
        }

        let remote_revision = skill
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string())
            .or_else(|| Some(version.clone()));

        write_marketplace_meta(&install_dir, skill, remote_revision.as_deref())?;

        Ok(InstallResult {
            success: true,
            skill_id: skill.id.clone(),
            message: None,
            installed_path: Some(install_dir.to_string_lossy().to_string()),
        })
    }

    async fn install_github_skill(
        skill: &MarketplaceSkill,
        skills_dir: &Path,
        github_token: Option<&str>,
    ) -> Result<InstallResult, String> {
        let repo_url = skill.repo_url.as_deref().ok_or_else(|| {
            skill
                .install_url
                .as_ref()
                .map(|url| {
                    format!(
                        "当前 Skill 暂不支持自动安装，请通过安装链接手动安装：{}",
                        url
                    )
                })
                .unwrap_or_else(|| "Skill 缺少仓库地址，暂不支持安装".to_string())
        })?;

        let skill_path = skill.skill_path.clone().unwrap_or_default();
        let install_dir = preferred_marketplace_install_dir(skills_dir, skill);
        let legacy_install_dir = legacy_marketplace_install_dir(skills_dir, skill);

        if install_dir.exists() {
            if !is_same_marketplace_skill(&install_dir, skill)? {
                return Err("本地已存在同名 Skill（非市场来源），请重命名".to_string());
            }
            fs::remove_dir_all(&install_dir).map_err(|e| format!("无法覆盖已有 Skill: {}", e))?;
        }
        if let Some(legacy_dir) = legacy_install_dir {
            if legacy_dir.exists() && is_same_marketplace_skill(&legacy_dir, skill)? {
                fs::remove_dir_all(&legacy_dir)
                    .map_err(|e| format!("无法迁移旧版 Skill 目录: {}", e))?;
            }
        }

        if !skills_dir.exists() {
            fs::create_dir_all(skills_dir).map_err(|e| format!("无法创建 Skills 目录: {}", e))?;
        }

        let tree = Self::fetch_skill_files(repo_url, &skill_path, github_token).await?;
        let mut files = Vec::new();
        collect_file_nodes(&tree, &mut files);
        let resolved_skill_path = tree.path.trim_matches('/').to_string();
        let remote_revision = skill
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string())
            .or_else(|| compute_skill_revision_from_file_nodes(&files));

        let client = Client::new();
        for file in files {
            let download_url = match &file.download_url {
                Some(url) => url,
                None => continue,
            };

            let relative_path = normalize_local_path(&file.path, &resolved_skill_path);
            if relative_path.trim().is_empty() || relative_path == "." {
                continue;
            }

            let target_path = install_dir.join(&relative_path);
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent).map_err(|e| format!("无法创建目录: {}", e))?;
            }

            let bytes = client
                .get(download_url)
                .send()
                .await
                .map_err(|e| format!("下载文件失败: {}", e))?
                .bytes()
                .await
                .map_err(|e| format!("读取文件失败: {}", e))?;

            fs::write(&target_path, &bytes).map_err(|e| format!("写入文件失败: {}", e))?;
        }

        write_marketplace_meta(&install_dir, skill, remote_revision.as_deref())?;

        Ok(InstallResult {
            success: true,
            skill_id: skill.id.clone(),
            message: None,
            installed_path: Some(install_dir.to_string_lossy().to_string()),
        })
    }

    pub async fn hydrate_marketplace_skill(
        skill: &MarketplaceSkill,
        github_token: Option<&str>,
    ) -> Result<MarketplaceSkill, String> {
        let repo_url = skill
            .repo_url
            .as_deref()
            .ok_or_else(|| "Skill 缺少仓库地址，暂不支持安装".to_string())?;
        let requested_skill_path = skill.skill_path.as_deref().unwrap_or_default();
        let tree = Self::fetch_skill_files(repo_url, requested_skill_path, github_token).await?;
        let mut files = Vec::new();
        collect_file_nodes(&tree, &mut files);

        let remote_revision = skill
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string())
            .or_else(|| compute_skill_revision_from_file_nodes(&files));

        let mut resolved = skill.clone();
        resolved.skill_path = Some(tree.path.clone());
        resolved.remote_revision = remote_revision;
        resolved.external_url = build_marketplace_external_url(
            skill
                .external_url
                .as_deref()
                .or(skill.install_url.as_deref()),
            Some(repo_url),
            Some(tree.path.as_str()),
        );
        if resolved.name.trim().is_empty() {
            resolved.name = tree.name;
        }

        Ok(resolved)
    }

    pub fn check_install_status(skill: &MarketplaceSkill, skills_dir: &Path) -> InstallStatus {
        let Some((_, meta)) = find_installed_marketplace_skill(skills_dir, skill) else {
            return InstallStatus::NotInstalled;
        };

        let remote_revision = skill
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty());
        let local_revision = meta
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty());

        match (remote_revision, local_revision) {
            (Some(remote), Some(local)) if remote != local => InstallStatus::UpdateAvailable,
            (Some(_), None) => InstallStatus::UpdateAvailable,
            _ => InstallStatus::Installed,
        }
    }
}

fn github_client() -> Result<Client, String> {
    Client::builder()
        .user_agent("skills-manager")
        .build()
        .map_err(|e| format!("无法创建 HTTP 客户端: {}", e))
}

fn github_tree_cache() -> &'static Mutex<HashMap<String, CachedGitHubTree>> {
    GITHUB_TREE_CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

fn github_tree_cache_key(owner: &str, repo: &str) -> String {
    format!("{}/{}", owner, repo)
}

fn get_cached_github_tree(owner: &str, repo: &str) -> Option<CachedGitHubTree> {
    let mut guard = github_tree_cache().lock().ok()?;
    let key = github_tree_cache_key(owner, repo);
    let cached = guard.get(&key).cloned()?;
    if cached.fetched_at.elapsed().ok()? > GITHUB_TREE_CACHE_TTL {
        guard.remove(&key);
        return None;
    }
    Some(cached)
}

fn set_cached_github_tree(owner: &str, repo: &str, branch: &str, tree: &[GitHubTreeEntry]) {
    if let Ok(mut guard) = github_tree_cache().lock() {
        guard.insert(
            github_tree_cache_key(owner, repo),
            CachedGitHubTree {
                fetched_at: SystemTime::now(),
                branch: branch.to_string(),
                tree: tree.to_vec(),
            },
        );
    }
}

fn skill_description_cache() -> &'static Mutex<HashMap<String, CachedSkillDescription>> {
    SKILL_DESCRIPTION_CACHE.get_or_init(|| Mutex::new(load_persisted_skill_description_cache()))
}

fn make_skill_description_cache_key(repo_url: &str, skill_path: &str) -> String {
    format!("{}::{}", repo_url.trim(), skill_path.trim_matches('/'))
}

fn get_cached_skill_description(cache_key: &str) -> Option<Option<String>> {
    let mut guard = skill_description_cache().lock().ok()?;
    let cached = guard.get(cache_key).cloned()?;
    if cached.fetched_at.elapsed().ok()? > SKILL_DESCRIPTION_CACHE_TTL {
        guard.remove(cache_key);
        let snapshot = guard.clone();
        drop(guard);
        persist_skill_description_cache(&snapshot);
        return None;
    }
    Some(cached.description)
}

fn set_cached_skill_description(cache_key: &str, description: Option<String>) {
    if let Ok(mut guard) = skill_description_cache().lock() {
        guard.insert(
            cache_key.to_string(),
            CachedSkillDescription {
                fetched_at: SystemTime::now(),
                description,
            },
        );
        let snapshot = guard.clone();
        drop(guard);
        persist_skill_description_cache(&snapshot);
    }
}

fn persisted_skill_description_cache_path() -> Option<PathBuf> {
    Some(
        dirs::home_dir()?
            .join(".skills-manager")
            .join("cache")
            .join("marketplace-skill-descriptions.json"),
    )
}

fn load_persisted_skill_description_cache() -> HashMap<String, CachedSkillDescription> {
    let Some(path) = persisted_skill_description_cache_path() else {
        return HashMap::new();
    };
    let content = match fs::read_to_string(path) {
        Ok(content) => content,
        Err(_) => return HashMap::new(),
    };
    let persisted: HashMap<String, PersistedSkillDescriptionEntry> =
        match serde_json::from_str(&content) {
            Ok(persisted) => persisted,
            Err(_) => return HashMap::new(),
        };

    let now = SystemTime::now();
    persisted
        .into_iter()
        .filter_map(|(cache_key, entry)| {
            let persisted_at = UNIX_EPOCH + Duration::from_secs(entry.fetched_at_unix_secs);
            let elapsed = now.duration_since(persisted_at).ok()?;
            if elapsed > PERSISTED_SKILL_DESCRIPTION_CACHE_TTL {
                return None;
            }
            Some((
                cache_key,
                CachedSkillDescription {
                    // 使用当前时间作为内存缓存时间，避免应用重启后立即被内存 TTL 淘汰
                    fetched_at: now,
                    description: entry.description,
                },
            ))
        })
        .collect()
}

fn persist_skill_description_cache(snapshot: &HashMap<String, CachedSkillDescription>) {
    let Some(path) = persisted_skill_description_cache_path() else {
        return;
    };
    if let Some(parent) = path.parent() {
        if fs::create_dir_all(parent).is_err() {
            return;
        }
    }

    let persisted: HashMap<String, PersistedSkillDescriptionEntry> = snapshot
        .iter()
        .map(|(cache_key, entry)| {
            let fetched_at_unix_secs = entry
                .fetched_at
                .duration_since(UNIX_EPOCH)
                .ok()
                .map(|duration| duration.as_secs())
                .unwrap_or_default();
            (
                cache_key.clone(),
                PersistedSkillDescriptionEntry {
                    fetched_at_unix_secs,
                    description: entry.description.clone(),
                },
            )
        })
        .collect();

    if let Ok(content) = serde_json::to_string(&persisted) {
        let _ = fs::write(path, content);
    }
}

fn parse_github_repo_url(url: &str) -> Result<(String, String), String> {
    let trimmed = url.trim_end_matches('/').trim_end_matches(".git");
    let parts: Vec<&str> = trimmed.split('/').collect();
    if parts.len() < 2 {
        return Err(format!("无效的 GitHub 仓库地址: {}", url));
    }
    let owner = parts[parts.len() - 2].to_string();
    let repo = parts[parts.len() - 1].to_string();
    Ok((owner, repo))
}

#[allow(dead_code)]
async fn fetch_github_root_skill_dirs_from_tree(
    client: &Client,
    owner: &str,
    repo: &str,
    github_token: Option<&str>,
) -> Option<HashSet<String>> {
    if let Some(cached) = get_cached_github_tree(owner, repo) {
        let dirs = extract_root_skill_dirs_from_tree_entries(&cached.tree);
        if !dirs.is_empty() {
            return Some(dirs);
        }
    }

    let branches = ["main", "master"];

    for branch in branches {
        let url = format!(
            "{}/repos/{}/{}/git/trees/{}?recursive=1",
            GITHUB_API_BASE, owner, repo, branch
        );
        let response = match with_github_auth(client.get(url), github_token).send().await {
            Ok(resp) => resp,
            Err(_) => continue,
        };

        if response.status().as_u16() == 404 {
            continue;
        }
        if !response.status().is_success() {
            continue;
        }

        let payload = match response.json::<GitHubTreeResponse>().await {
            Ok(value) => value,
            Err(_) => continue,
        };
        set_cached_github_tree(owner, repo, branch, &payload.tree);
        let dirs = extract_root_skill_dirs_from_tree_entries(&payload.tree);
        if !dirs.is_empty() {
            return Some(dirs);
        }
    }

    None
}

async fn fetch_skill_files_from_tree_api(
    client: &Client,
    owner: &str,
    repo: &str,
    skill_path: &str,
    github_token: Option<&str>,
) -> Result<Option<SkillFileNode>, String> {
    if let Some(cached) = get_cached_github_tree(owner, repo) {
        if let Some(tree) = build_skill_tree_from_tree_entries(
            &cached.tree,
            skill_path,
            owner,
            repo,
            &cached.branch,
        ) {
            return Ok(Some(tree));
        }
    }

    let branches = ["main", "master"];
    let mut rate_limited = false;

    for branch in branches {
        let url = format!(
            "{}/repos/{}/{}/git/trees/{}?recursive=1",
            GITHUB_API_BASE, owner, repo, branch
        );
        let response = with_github_auth(client.get(url), github_token)
            .send()
            .await
            .map_err(|e| format!("GitHub 请求失败: {}", e))?;

        if response.status().as_u16() == 404 {
            continue;
        }
        if response.status().as_u16() == 403 {
            rate_limited = true;
            continue;
        }
        if !response.status().is_success() {
            continue;
        }

        let payload = response
            .json::<GitHubTreeResponse>()
            .await
            .map_err(|e| format!("GitHub 响应解析失败: {}", e))?;
        set_cached_github_tree(owner, repo, branch, &payload.tree);
        let tree =
            build_skill_tree_from_tree_entries(&payload.tree, skill_path, owner, repo, branch);
        if tree.is_some() {
            return Ok(tree);
        }
    }

    if rate_limited {
        return Ok(None);
    }

    Ok(None)
}

fn build_skill_tree_from_tree_entries(
    entries: &[GitHubTreeEntry],
    skill_path: &str,
    owner: &str,
    repo: &str,
    branch: &str,
) -> Option<SkillFileNode> {
    let normalized_skill_path = skill_path.trim_matches('/');
    let prefix = if normalized_skill_path.is_empty() {
        String::new()
    } else {
        format!("{}/", normalized_skill_path)
    };

    let mut files: Vec<(String, String, Option<String>)> = entries
        .iter()
        .filter(|entry| entry.kind == "blob")
        .filter_map(|entry| {
            let normalized_path = entry.path.trim_matches('/').to_string();
            if normalized_skill_path.is_empty() {
                return Some((normalized_path, entry.sha.clone()));
            }
            if normalized_path.starts_with(&prefix) {
                return Some((normalized_path, entry.sha.clone()));
            }
            None
        })
        .map(|(path, sha)| {
            let url = format!(
                "https://raw.githubusercontent.com/{}/{}/{}/{}",
                owner, repo, branch, path
            );
            (path, url, sha)
        })
        .collect();

    if files.is_empty() {
        return None;
    }

    files.sort_by(|a, b| a.0.cmp(&b.0));

    let root_name = if normalized_skill_path.is_empty() {
        repo.to_string()
    } else {
        repo_path_name(normalized_skill_path)
    };
    let mut root = SkillFileNode {
        name: root_name,
        path: normalized_skill_path.to_string(),
        is_dir: true,
        download_url: None,
        sha: None,
        children: Some(Vec::new()),
    };

    for (full_path, download_url, sha) in files {
        insert_file_into_skill_tree(
            &mut root,
            normalized_skill_path,
            &full_path,
            download_url,
            sha,
        );
    }

    sort_skill_tree_children(&mut root);
    Some(root)
}

fn insert_file_into_skill_tree(
    root: &mut SkillFileNode,
    root_path: &str,
    full_path: &str,
    download_url: String,
    sha: Option<String>,
) {
    let relative_path = if root_path.is_empty() {
        full_path.to_string()
    } else {
        full_path
            .strip_prefix(&format!("{}/", root_path))
            .unwrap_or(full_path)
            .to_string()
    };
    let segments: Vec<&str> = relative_path.split('/').filter(|s| !s.is_empty()).collect();
    if segments.is_empty() {
        return;
    }

    insert_segments(root, root_path, &segments, full_path, download_url, sha);
}

fn insert_segments(
    current: &mut SkillFileNode,
    current_path: &str,
    segments: &[&str],
    full_path: &str,
    download_url: String,
    sha: Option<String>,
) {
    let Some((first, rest)) = segments.split_first() else {
        return;
    };

    let children = current.children.get_or_insert_with(Vec::new);
    if rest.is_empty() {
        if !children.iter().any(|n| !n.is_dir && n.path == full_path) {
            children.push(SkillFileNode {
                name: (*first).to_string(),
                path: full_path.to_string(),
                is_dir: false,
                download_url: Some(download_url),
                sha,
                children: None,
            });
        }
        return;
    }

    let dir_path = if current_path.is_empty() {
        (*first).to_string()
    } else {
        format!("{}/{}", current_path, first)
    };

    let index = children
        .iter()
        .position(|node| node.is_dir && node.name == *first)
        .unwrap_or_else(|| {
            children.push(SkillFileNode {
                name: (*first).to_string(),
                path: dir_path.clone(),
                is_dir: true,
                download_url: None,
                sha: None,
                children: Some(Vec::new()),
            });
            children.len() - 1
        });

    if !children[index].is_dir {
        children[index] = SkillFileNode {
            name: (*first).to_string(),
            path: dir_path.clone(),
            is_dir: true,
            download_url: None,
            sha: None,
            children: Some(Vec::new()),
        };
    }

    let child = children.get_mut(index).expect("child index should exist");
    insert_segments(child, &dir_path, rest, full_path, download_url, sha);
}

fn sort_skill_tree_children(node: &mut SkillFileNode) {
    if let Some(children) = node.children.as_mut() {
        for child in children.iter_mut().filter(|child| child.is_dir) {
            sort_skill_tree_children(child);
        }
        children.sort_by(|a, b| match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        });
    }
}

#[allow(dead_code)]
fn should_include_github_root_dir(
    item: &GitHubContent,
    hinted_skill_dirs: Option<&HashSet<String>>,
) -> bool {
    if item.kind != "dir" {
        return false;
    }
    if item.name.starts_with('.') || item.path.starts_with('.') {
        return false;
    }
    if let Some(hints) = hinted_skill_dirs {
        return hints.contains(&item.path) || hints.contains(&item.name);
    }
    true
}

#[allow(dead_code)]
fn extract_root_skill_dirs_from_tree_entries(entries: &[GitHubTreeEntry]) -> HashSet<String> {
    let mut dirs = HashSet::new();
    for entry in entries {
        if entry.kind != "blob" {
            continue;
        }

        let path = entry.path.trim_matches('/');
        let mut parts = path.split('/').filter(|part| !part.is_empty());
        let Some(root) = parts.next() else {
            continue;
        };
        let Some(file) = parts.next() else {
            continue;
        };
        if parts.next().is_some() {
            continue;
        }
        if root.starts_with('.') {
            continue;
        }

        if is_skill_manifest_file(file) {
            dirs.insert(root.to_string());
        }
    }
    dirs
}

#[allow(dead_code)]
fn is_skill_manifest_file(file_name: &str) -> bool {
    matches!(
        file_name.to_ascii_lowercase().as_str(),
        "skill.md" | "readme.md"
    )
}

#[allow(dead_code)]
async fn fetch_github_root_dirs_from_html(
    client: &Client,
    owner: &str,
    repo: &str,
) -> Result<Vec<String>, String> {
    let branches = ["main", "master"];
    let mut result: HashSet<String> = HashSet::new();

    for branch in branches {
        let url = format!("https://github.com/{}/{}/tree/{}", owner, repo, branch);
        let response = client
            .get(&url)
            .send()
            .await
            .map_err(|e| format!("GitHub 页面请求失败: {}", e))?;
        if !response.status().is_success() {
            continue;
        }
        let html = response
            .text()
            .await
            .map_err(|e| format!("GitHub 页面读取失败: {}", e))?;
        extract_root_dirs_from_html(&html, owner, repo, branch, &mut result);
        if !result.is_empty() {
            break;
        }
    }

    if result.is_empty() {
        return Err("GitHub API 请求受限，且页面兜底未获取到目录".to_string());
    }

    let mut dirs: Vec<String> = result.into_iter().collect();
    dirs.sort();
    Ok(dirs)
}

#[allow(dead_code)]
fn extract_root_dirs_from_html(
    html: &str,
    owner: &str,
    repo: &str,
    branch: &str,
    out: &mut HashSet<String>,
) {
    let marker = format!("href=\"/{}/{}/tree/{}/", owner, repo, branch);
    let mut search_start = 0usize;
    while let Some(pos) = html[search_start..].find(&marker) {
        let start = search_start + pos + marker.len();
        let rest = &html[start..];
        let Some(end_quote) = rest.find('"') else {
            break;
        };
        let raw_path = &rest[..end_quote];
        if !raw_path.is_empty() && !raw_path.contains('/') {
            let decoded = raw_path.replace("%20", " ");
            if !decoded.starts_with('.') {
                out.insert(decoded);
            }
        }
        search_start = start + end_quote;
    }
}

async fn fetch_github_contents(
    client: &Client,
    owner: &str,
    repo: &str,
    path: &str,
    github_token: Option<&str>,
) -> Result<Vec<GitHubContent>, String> {
    let url = if path.is_empty() {
        format!("{}/repos/{}/{}/contents", GITHUB_API_BASE, owner, repo)
    } else {
        format!(
            "{}/repos/{}/{}/contents/{}",
            GITHUB_API_BASE, owner, repo, path
        )
    };

    let response = with_github_auth(client.get(url), github_token)
        .send()
        .await
        .map_err(|e| format!("GitHub 请求失败: {}", e))?;

    if response.status().as_u16() == 403 {
        return Err("GitHub API 请求受限，请稍后再试".to_string());
    }

    if !response.status().is_success() {
        return Err(format!("GitHub 响应错误: HTTP {}", response.status()));
    }

    let value: Value = response
        .json()
        .await
        .map_err(|e| format!("GitHub 响应解析失败: {}", e))?;

    let list = value
        .as_array()
        .ok_or_else(|| "GitHub 响应格式异常".to_string())?;

    let mut contents = Vec::new();
    for item in list {
        let parsed: GitHubContent = serde_json::from_value(item.clone())
            .map_err(|e| format!("GitHub 内容解析失败: {}", e))?;
        contents.push(parsed);
    }

    Ok(contents)
}

async fn fetch_skill_files_from_raw(
    owner: &str,
    repo: &str,
    skill_path: &str,
) -> Result<Option<SkillFileNode>, String> {
    let client = Client::new();
    let branches = ["main", "master"];
    let candidates = ["SKILL.md", "README.md", "skill.md", "readme.md"];
    let mut files: Vec<SkillFileNode> = Vec::new();

    for candidate in candidates {
        if let Some(raw_url) =
            find_raw_file_url(&client, owner, repo, skill_path, candidate, &branches).await?
        {
            files.push(SkillFileNode {
                name: candidate.to_string(),
                path: join_repo_path(skill_path, candidate),
                is_dir: false,
                download_url: Some(raw_url),
                sha: None,
                children: None,
            });
        }
    }

    if files.is_empty() {
        return Ok(None);
    }

    files.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    Ok(Some(SkillFileNode {
        name: repo_path_name(skill_path),
        path: skill_path.to_string(),
        is_dir: true,
        download_url: None,
        sha: None,
        children: Some(files),
    }))
}

async fn find_raw_file_url(
    client: &Client,
    owner: &str,
    repo: &str,
    skill_path: &str,
    file_name: &str,
    branches: &[&str],
) -> Result<Option<String>, String> {
    let path = join_repo_path(skill_path, file_name);
    for branch in branches {
        let url = format!(
            "https://raw.githubusercontent.com/{}/{}/{}/{}",
            owner, repo, branch, path
        );
        let response = client
            .get(&url)
            .send()
            .await
            .map_err(|e| format!("raw 文件请求失败: {}", e))?;
        if response.status().is_success() {
            return Ok(Some(url));
        }
    }
    Ok(None)
}

async fn find_manifest_download_url_from_raw(
    client: &Client,
    owner: &str,
    repo: &str,
    skill_path: &str,
) -> Option<String> {
    let branches = ["main", "master"];
    let candidates = ["SKILL.md", "README.md", "skill.md", "readme.md"];

    for candidate in candidates {
        if let Ok(Some(url)) =
            find_raw_file_url(client, owner, repo, skill_path, candidate, &branches).await
        {
            return Some(url);
        }
    }

    None
}

fn find_manifest_download_url_in_tree(node: &SkillFileNode) -> Option<String> {
    if !node.is_dir {
        let lower_name = node.name.to_ascii_lowercase();
        if matches!(lower_name.as_str(), "skill.md" | "readme.md") {
            return node.download_url.clone();
        }
        return None;
    }

    let children = node.children.as_ref()?;
    for candidate in ["skill.md", "readme.md"] {
        if let Some(url) = children.iter().find_map(|child| {
            if child.is_dir {
                return None;
            }
            if child.name.eq_ignore_ascii_case(candidate) {
                return child.download_url.clone();
            }
            None
        }) {
            return Some(url);
        }
    }

    for child in children {
        if let Some(url) = find_manifest_download_url_in_tree(child) {
            return Some(url);
        }
    }

    None
}

fn extract_skill_description_from_markdown(raw: &str) -> Option<String> {
    let normalized = raw.replace("\r\n", "\n");
    let (frontmatter, body) = split_frontmatter(&normalized);
    if let Some(frontmatter_block) = frontmatter {
        if let Some(description) = extract_description_from_frontmatter(frontmatter_block) {
            return Some(description);
        }
    }

    extract_first_markdown_paragraph(body)
}

fn split_frontmatter(content: &str) -> (Option<&str>, &str) {
    let Some(rest) = content.strip_prefix("---\n") else {
        return (None, content);
    };

    if let Some(index) = rest.find("\n---\n") {
        let frontmatter = &rest[..index];
        let body = &rest[index + "\n---\n".len()..];
        return (Some(frontmatter), body);
    }

    if let Some(index) = rest.find("\n---") {
        let frontmatter = &rest[..index];
        let body = &rest[index + "\n---".len()..];
        return (Some(frontmatter), body.strip_prefix('\n').unwrap_or(body));
    }

    (None, content)
}

fn extract_description_from_frontmatter(frontmatter: &str) -> Option<String> {
    for raw_line in frontmatter.lines() {
        let line = raw_line.trim_end();
        if line.is_empty() {
            continue;
        }
        if raw_line.starts_with(' ') || raw_line.starts_with('\t') {
            continue;
        }
        if let Some(value) = line.strip_prefix("description:") {
            let description = strip_yaml_value(value.trim());
            if let Some(normalized) = normalize_description(description) {
                return Some(normalized);
            }
        }
    }
    None
}

fn extract_first_markdown_paragraph(body: &str) -> Option<String> {
    let mut lines: Vec<&str> = Vec::new();
    let mut in_code_block = false;

    for raw_line in body.lines() {
        let line = raw_line.trim();
        if line.starts_with("```") {
            in_code_block = !in_code_block;
            continue;
        }
        if in_code_block {
            continue;
        }

        if line.is_empty() {
            if !lines.is_empty() {
                break;
            }
            continue;
        }

        if should_skip_markdown_line(line) {
            if !lines.is_empty() {
                break;
            }
            continue;
        }

        lines.push(line);
    }

    if lines.is_empty() {
        return None;
    }

    normalize_description(lines.join(" "))
}

fn should_skip_markdown_line(line: &str) -> bool {
    line.starts_with('#')
        || line.starts_with('>')
        || line.starts_with("- ")
        || line.starts_with("* ")
        || line.starts_with("+ ")
        || line.starts_with("|")
        || line.starts_with("![")
        || (line.starts_with('[') && line.contains("]:"))
}

fn strip_yaml_value(value: &str) -> String {
    let trimmed = value.trim();
    if (trimmed.starts_with('"') && trimmed.ends_with('"'))
        || (trimmed.starts_with('\'') && trimmed.ends_with('\''))
    {
        return trimmed[1..trimmed.len().saturating_sub(1)]
            .trim()
            .to_string();
    }
    trimmed.to_string()
}

fn normalize_description(raw: String) -> Option<String> {
    let collapsed = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    if collapsed.is_empty() {
        return None;
    }
    Some(truncate_with_ellipsis(&collapsed, 180))
}

fn truncate_with_ellipsis(text: &str, max_chars: usize) -> String {
    let mut chars = text.chars();
    let truncated: String = chars.by_ref().take(max_chars).collect();
    if chars.next().is_some() {
        format!("{}...", truncated.trim_end())
    } else {
        text.to_string()
    }
}

fn join_repo_path(base: &str, name: &str) -> String {
    if base.is_empty() {
        name.to_string()
    } else {
        format!("{}/{}", base.trim_end_matches('/'), name)
    }
}

fn repo_path_name(path: &str) -> String {
    path.split('/')
        .last()
        .filter(|s| !s.is_empty())
        .unwrap_or(path)
        .to_string()
}

fn build_skill_path_candidates(skill_path: &str) -> Vec<String> {
    let normalized = skill_path.trim_matches('/');
    if normalized.is_empty() {
        return vec![String::new()];
    }

    let mut candidates = vec![normalized.to_string()];
    if !normalized.contains('/') {
        for candidate in [
            format!("skills/{}", normalized),
            format!(".claude/skills/{}", normalized),
        ] {
            if !candidates.contains(&candidate) {
                candidates.push(candidate);
            }
        }
    }
    candidates
}

async fn infer_skill_path_candidates_from_repo_tree(
    client: &Client,
    owner: &str,
    repo: &str,
    requested_skill_path: &str,
    github_token: Option<&str>,
) -> Result<Vec<String>, String> {
    if let Some(cached) = get_cached_github_tree(owner, repo) {
        return Ok(infer_skill_path_candidates_from_tree_entries(
            &cached.tree,
            requested_skill_path,
        ));
    }

    let branches = ["main", "master"];
    let mut rate_limited = false;

    for branch in branches {
        let url = format!(
            "{}/repos/{}/{}/git/trees/{}?recursive=1",
            GITHUB_API_BASE, owner, repo, branch
        );
        let response = with_github_auth(client.get(url), github_token)
            .send()
            .await
            .map_err(|e| format!("GitHub 请求失败: {}", e))?;

        if response.status().as_u16() == 404 {
            continue;
        }
        if response.status().as_u16() == 403 {
            rate_limited = true;
            continue;
        }
        if !response.status().is_success() {
            continue;
        }

        let payload = response
            .json::<GitHubTreeResponse>()
            .await
            .map_err(|e| format!("GitHub 响应解析失败: {}", e))?;
        set_cached_github_tree(owner, repo, branch, &payload.tree);
        return Ok(infer_skill_path_candidates_from_tree_entries(
            &payload.tree,
            requested_skill_path,
        ));
    }

    if rate_limited {
        return Ok(Vec::new());
    }

    Ok(Vec::new())
}

fn infer_skill_path_candidates_from_tree_entries(
    entries: &[GitHubTreeEntry],
    requested_skill_path: &str,
) -> Vec<String> {
    let requested = requested_skill_path.trim_matches('/');
    if requested.is_empty() {
        return Vec::new();
    }

    let requested_lower = requested.to_ascii_lowercase();
    let requested_name_lower = repo_path_name(requested).to_ascii_lowercase();
    let requested_suffix = format!("/{}", requested_lower);

    let mut exact_or_suffix_matches: Vec<String> = Vec::new();
    let mut basename_matches: Vec<String> = Vec::new();

    for entry in entries.iter().filter(|entry| entry.kind == "blob") {
        let normalized_path = entry.path.trim_matches('/');
        let Some((parent_dir, file_name)) = normalized_path.rsplit_once('/') else {
            continue;
        };
        if !is_skill_manifest_file(file_name) {
            continue;
        }

        let dir = parent_dir.trim_matches('/');
        if dir.is_empty() {
            continue;
        }

        let dir_lower = dir.to_ascii_lowercase();
        if dir_lower == requested_lower || dir_lower.ends_with(&requested_suffix) {
            if !exact_or_suffix_matches.iter().any(|value| value == dir) {
                exact_or_suffix_matches.push(dir.to_string());
            }
            continue;
        }

        if repo_path_name(dir).eq_ignore_ascii_case(&requested_name_lower)
            && !basename_matches.iter().any(|value| value == dir)
        {
            basename_matches.push(dir.to_string());
        }
    }

    let sort_candidates = |candidates: &mut Vec<String>| {
        candidates.sort_by(|left, right| {
            let left_depth = left
                .split('/')
                .filter(|segment| !segment.is_empty())
                .count();
            let right_depth = right
                .split('/')
                .filter(|segment| !segment.is_empty())
                .count();
            left_depth
                .cmp(&right_depth)
                .then_with(|| left.len().cmp(&right.len()))
                .then_with(|| left.cmp(right))
        });
    };

    sort_candidates(&mut exact_or_suffix_matches);
    if !exact_or_suffix_matches.is_empty() {
        return exact_or_suffix_matches;
    }

    sort_candidates(&mut basename_matches);
    if !basename_matches.is_empty() {
        return basename_matches;
    }

    if has_root_skill_manifest(entries) {
        return vec![String::new()];
    }

    Vec::new()
}

fn has_root_skill_manifest(entries: &[GitHubTreeEntry]) -> bool {
    entries
        .iter()
        .filter(|entry| entry.kind == "blob")
        .any(|entry| entry.path.eq_ignore_ascii_case("SKILL.md"))
}

fn is_github_not_found_error(error_message: &str) -> bool {
    error_message.contains("HTTP 404")
}

fn build_github_tree<'a>(
    client: &'a Client,
    owner: &'a str,
    repo: &'a str,
    path: &'a str,
    github_token: Option<&'a str>,
) -> Pin<Box<dyn Future<Output = Result<SkillFileNode, String>> + Send + 'a>> {
    Box::pin(async move {
        let contents = fetch_github_contents(client, owner, repo, path, github_token).await?;
        let mut children = Vec::new();

        for item in contents {
            if item.kind == "dir" {
                let child =
                    build_github_tree(client, owner, repo, &item.path, github_token).await?;
                children.push(child);
            } else {
                children.push(SkillFileNode {
                    name: item.name,
                    path: item.path,
                    is_dir: false,
                    download_url: item.download_url,
                    sha: None,
                    children: None,
                });
            }
        }

        children.sort_by(|a, b| match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        });

        let name = path
            .split('/')
            .last()
            .filter(|s| !s.is_empty())
            .unwrap_or(path)
            .to_string();

        Ok(SkillFileNode {
            name,
            path: path.to_string(),
            is_dir: true,
            download_url: None,
            sha: None,
            children: Some(children),
        })
    })
}

fn normalize_github_token(github_token: Option<&str>) -> Option<String> {
    github_token
        .map(|token| token.trim().to_string())
        .filter(|token| !token.is_empty())
}

fn with_github_auth(
    request: reqwest::RequestBuilder,
    github_token: Option<&str>,
) -> reqwest::RequestBuilder {
    if let Some(token) = normalize_github_token(github_token) {
        request.bearer_auth(token)
    } else {
        request
    }
}

pub(crate) fn derive_github_repo_and_skill_path(
    install_url: Option<&str>,
    slug: &str,
) -> (Option<String>, Option<String>) {
    let slug_derived = parse_github_repo_and_path_from_slug(slug);

    if let Some(url) = install_url {
        if let Some((repo_url, path)) = parse_github_repo_and_path_from_url(url) {
            if path.is_none() {
                if let Some((slug_repo_url, slug_path)) = slug_derived.as_ref() {
                    if slug_path.is_some() && same_github_repo(repo_url.as_str(), slug_repo_url) {
                        return (Some(repo_url), slug_path.clone());
                    }
                }
            }
            return (Some(repo_url), path);
        }
    }

    slug_derived
        .map(|(repo_url, path)| (Some(repo_url), path))
        .unwrap_or((None, None))
}

fn same_github_repo(left: &str, right: &str) -> bool {
    let left = match parse_github_repo_url(left) {
        Ok((owner, repo)) => format!(
            "{}/{}",
            owner.trim().to_lowercase(),
            repo.trim().to_lowercase()
        ),
        Err(_) => return false,
    };
    let right = match parse_github_repo_url(right) {
        Ok((owner, repo)) => format!(
            "{}/{}",
            owner.trim().to_lowercase(),
            repo.trim().to_lowercase()
        ),
        Err(_) => return false,
    };
    left == right
}

fn parse_github_repo_and_path_from_url(url: &str) -> Option<(String, Option<String>)> {
    let trimmed = url.trim();
    if trimmed.is_empty() || !trimmed.contains("github.com/") {
        return None;
    }

    let without_query = trimmed
        .split('#')
        .next()?
        .split('?')
        .next()?
        .trim_end_matches('/');
    let marker = "github.com/";
    let start = without_query.find(marker)? + marker.len();
    let remainder = &without_query[start..];
    let segments: Vec<&str> = remainder
        .split('/')
        .filter(|value| !value.is_empty())
        .collect();
    if segments.len() < 2 {
        return None;
    }

    let owner = segments[0];
    let repo = segments[1].trim_end_matches(".git");
    if owner.is_empty() || repo.is_empty() {
        return None;
    }

    let repo_url = format!("https://github.com/{}/{}", owner, repo);
    let path = if segments.len() > 4 && matches!(segments[2], "tree" | "blob") {
        normalize_github_skill_path(segments[4..].join("/"))
    } else {
        None
    };

    Some((repo_url, path))
}

fn normalize_github_skill_path(path: String) -> Option<String> {
    let normalized = path.trim_matches('/').to_string();
    if normalized.is_empty() {
        return Some(String::new());
    }

    if let Some((parent, file_name)) = normalized.rsplit_once('/') {
        if is_skill_manifest_file(file_name) {
            return Some(parent.trim_matches('/').to_string());
        }
    } else if is_skill_manifest_file(normalized.as_str()) {
        return Some(String::new());
    }

    Some(normalized)
}

fn parse_github_repo_and_path_from_slug(slug: &str) -> Option<(String, Option<String>)> {
    let segments: Vec<&str> = slug
        .split('/')
        .filter(|value| !value.trim().is_empty())
        .collect();
    if segments.len() < 2 {
        return None;
    }

    let owner = segments[0].trim();
    let repo = segments[1].trim();
    if owner.is_empty() || repo.is_empty() {
        return None;
    }

    let repo_url = format!("https://github.com/{}/{}", owner, repo);
    let path = if segments.len() > 2 {
        let value = segments[2..].join("/");
        if value.trim().is_empty() {
            None
        } else {
            Some(value)
        }
    } else {
        None
    };

    Some((repo_url, path))
}

fn build_marketplace_external_url(
    raw_url: Option<&str>,
    repo_url: Option<&str>,
    skill_path: Option<&str>,
) -> Option<String> {
    if let Some(raw) = raw_url.map(str::trim).filter(|url| !url.is_empty()) {
        return Some(raw.to_string());
    }

    let repo = repo_url.map(str::trim).filter(|url| !url.is_empty())?;

    if !repo.contains("github.com") {
        return Some(repo.to_string());
    }

    let (owner, repository) = match parse_github_repo_url(repo) {
        Ok(tuple) => tuple,
        Err(_) => return Some(repo.to_string()),
    };
    let base = format!("https://github.com/{}/{}", owner, repository);

    if let Some(path) = skill_path.map(str::trim).filter(|path| !path.is_empty()) {
        return Some(format!("{}/tree/HEAD/{}", base, path.trim_matches('/')));
    }

    Some(base)
}

#[allow(dead_code)]
fn make_marketplace_skill_id(source_id: &str, raw: &str) -> String {
    let combined = format!("{}-{}", source_id, raw);
    combined
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .to_string()
}

fn collect_file_nodes(node: &SkillFileNode, files: &mut Vec<SkillFileNode>) {
    if node.is_dir {
        if let Some(children) = &node.children {
            for child in children {
                collect_file_nodes(child, files);
            }
        }
    } else {
        files.push(node.clone());
    }
}

#[allow(dead_code)]
fn compute_skill_revision_from_tree_entries(
    entries: &[GitHubTreeEntry],
    skill_path: &str,
) -> Option<String> {
    let normalized_skill_path = skill_path.trim_matches('/');
    let prefix = if normalized_skill_path.is_empty() {
        String::new()
    } else {
        format!("{}/", normalized_skill_path)
    };

    let mut fingerprints: Vec<(String, String)> = entries
        .iter()
        .filter(|entry| entry.kind == "blob")
        .filter_map(|entry| {
            let normalized_path = entry.path.trim_matches('/').to_string();
            if !normalized_skill_path.is_empty() && !normalized_path.starts_with(&prefix) {
                return None;
            }
            let sha = entry.sha.as_ref()?.trim().to_string();
            if sha.is_empty() {
                return None;
            }
            Some((normalized_path, sha))
        })
        .collect();

    compute_revision_from_pairs(&mut fingerprints)
}

fn compute_skill_revision_from_file_nodes(files: &[SkillFileNode]) -> Option<String> {
    let mut fingerprints: Vec<(String, String)> = files
        .iter()
        .filter_map(|file| {
            let sha = file.sha.as_ref()?.trim().to_string();
            if sha.is_empty() {
                return None;
            }
            Some((file.path.trim_matches('/').to_string(), sha))
        })
        .collect();

    compute_revision_from_pairs(&mut fingerprints)
}

fn compute_revision_from_pairs(pairs: &mut Vec<(String, String)>) -> Option<String> {
    if pairs.is_empty() {
        return None;
    }

    pairs.sort_by(|a, b| a.0.cmp(&b.0));
    let mut hash: u64 = 0xcbf29ce484222325;
    for (path, sha) in pairs.iter() {
        for byte in path.as_bytes() {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
        hash ^= u64::from(b':');
        hash = hash.wrapping_mul(0x100000001b3);
        for byte in sha.as_bytes() {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
        hash ^= u64::from(b'\n');
        hash = hash.wrapping_mul(0x100000001b3);
    }

    Some(format!("gh-tree-fnv64:{hash:016x}"))
}

fn normalize_local_path(path: &str, skill_path: &str) -> String {
    if skill_path.is_empty() {
        return path.to_string();
    }
    if path == skill_path {
        return ".".to_string();
    }
    let prefix = format!("{}/", skill_path.trim_end_matches('/'));
    if let Some(stripped) = path.strip_prefix(&prefix) {
        return stripped.to_string();
    }
    path.to_string()
}

/// clawhub ZIP 归档内的文件可能带顶层目录（如 "my-skill/SKILL.md"），
/// 也可能直接是文件（如 "SKILL.md"）。如果路径以 "<slug>/" 开头则剥离该前缀，
/// 否则原样返回。slug 中的 '/' 不会被作为目录分隔符处理。
/// 重复前缀（如 "my-skill/my-skill/SKILL.md"）会被全部剥离。
fn strip_archive_top_level_prefix(path: &str, slug: &str) -> String {
    let path = path.trim_start_matches("./");
    let slug = slug.trim_end_matches('/');
    if slug.is_empty() {
        return path.to_string();
    }
    let prefix = format!("{}/", slug);
    let mut result = path;
    while let Some(stripped) = result.strip_prefix(&prefix) {
        result = stripped;
    }
    result.to_string()
}

/// 递归地将文件路径插入到 SkillFileNode 树中。
fn insert_into_clawhub_tree(
    children: &mut Vec<SkillFileNode>,
    segments: &[&str],
    accumulated_path: &str,
    download_url: String,
) {
    if segments.is_empty() {
        return;
    }
    let (first, rest) = segments.split_first().unwrap();
    let current_path = if accumulated_path.is_empty() {
        first.to_string()
    } else {
        format!("{}/{}", accumulated_path, first)
    };
    let is_leaf = rest.is_empty();

    if is_leaf {
        children.push(SkillFileNode {
            name: first.to_string(),
            path: current_path,
            is_dir: false,
            download_url: Some(download_url),
            sha: None,
            children: None,
        });
    } else {
        let pos = children.iter().position(|c| c.is_dir && c.name == *first);
        match pos {
            Some(idx) => {
                let child = &mut children[idx];
                if let Some(grandchildren) = child.children.as_mut() {
                    insert_into_clawhub_tree(
                        grandchildren,
                        rest,
                        &current_path,
                        download_url,
                    );
                }
            }
            None => {
                children.push(SkillFileNode {
                    name: first.to_string(),
                    path: current_path.clone(),
                    is_dir: true,
                    download_url: None,
                    sha: None,
                    children: Some(Vec::new()),
                });
                let last_idx = children.len() - 1;
                let child = &mut children[last_idx];
                if let Some(grandchildren) = child.children.as_mut() {
                    insert_into_clawhub_tree(
                        grandchildren,
                        rest,
                        &current_path,
                        download_url,
                    );
                }
            }
        }
    }
}

/// 对 SkillFileNode 的子节点排序：目录在前，文件在后，各自按名称排序。
fn sort_skill_file_nodes(node: &mut SkillFileNode) {
    if let Some(children) = node.children.as_mut() {
        children.sort_by(|a, b| match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.cmp(&b.name),
        });
        for child in children.iter_mut() {
            sort_skill_file_nodes(child);
        }
    }
}

/// 从 clawhub ZIP 归档的扁平文件列表构建 SkillFileNode 树。
/// download_url 格式: `clawhub:{slug}|{owner}|{version}|{path}`
fn build_clawhub_skill_tree(
    files: &[(String, Vec<u8>)],
    slug: &str,
    owner: Option<&str>,
    version: &str,
) -> SkillFileNode {
    let mut root = SkillFileNode {
        name: slug.to_string(),
        path: String::new(),
        is_dir: true,
        download_url: None,
        sha: None,
        children: Some(Vec::new()),
    };

    for (raw_path, _) in files {
        let path = strip_archive_top_level_prefix(raw_path, slug);
        if path.is_empty() || path == "." {
            continue;
        }
        let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
        if segments.is_empty() {
            continue;
        }
        let download_url = format!(
            "clawhub:{}|{}|{}|{}",
            slug,
            owner.unwrap_or(""),
            version,
            path,
        );
        if let Some(children) = root.children.as_mut() {
            insert_into_clawhub_tree(children, &segments, "", download_url);
        }
    }

    sort_skill_file_nodes(&mut root);
    root
}

fn write_marketplace_meta(
    dir: &Path,
    skill: &MarketplaceSkill,
    remote_revision: Option<&str>,
) -> Result<(), String> {
    let meta = serde_json::json!({
        "name": skill.name,
        "description": skill.description,
        "version": "1.0",
        "source": "marketplace",
        "marketplace_source_id": skill.source_id,
        "marketplace_skill_id": skill.id,
        "marketplace_skill_slug": skill.slug,
        "repo_url": skill.repo_url,
        "skill_path": skill.skill_path,
        "install_url": skill.install_url,
        "created_at": skill.created_at,
        "author": skill.author,
        "tags": skill.tags,
        "remote_revision": remote_revision,
    });

    let content =
        serde_json::to_string_pretty(&meta).map_err(|e| format!("写入 meta.json 失败: {}", e))?;
    fs::write(dir.join("meta.json"), content).map_err(|e| format!("写入 meta.json 失败: {}", e))?;
    Ok(())
}

#[derive(Debug, Clone)]
struct LocalMarketplaceMeta {
    source: Option<String>,
    marketplace_source_id: Option<String>,
    marketplace_skill_id: Option<String>,
    marketplace_skill_slug: Option<String>,
    remote_revision: Option<String>,
}

fn read_marketplace_meta(dir: &Path) -> Result<LocalMarketplaceMeta, String> {
    let meta_path = dir.join("meta.json");
    if !meta_path.exists() {
        return Ok(LocalMarketplaceMeta {
            source: None,
            marketplace_source_id: None,
            marketplace_skill_id: None,
            marketplace_skill_slug: None,
            remote_revision: None,
        });
    }

    let content =
        fs::read_to_string(&meta_path).map_err(|e| format!("读取 meta.json 失败: {}", e))?;
    let value: Value =
        serde_json::from_str(&content).map_err(|e| format!("解析 meta.json 失败: {}", e))?;

    Ok(LocalMarketplaceMeta {
        source: value
            .get("source")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned),
        marketplace_source_id: value
            .get("marketplace_source_id")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned),
        marketplace_skill_id: value
            .get("marketplace_skill_id")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned),
        marketplace_skill_slug: value
            .get("marketplace_skill_slug")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned),
        remote_revision: value
            .get("remote_revision")
            .and_then(|v| v.as_str())
            .map(ToOwned::to_owned),
    })
}

fn is_same_marketplace_skill(dir: &Path, skill: &MarketplaceSkill) -> Result<bool, String> {
    let meta = read_marketplace_meta(dir)?;
    Ok(is_marketplace_meta_for_skill(&meta, skill))
}

fn is_marketplace_meta_for_skill(meta: &LocalMarketplaceMeta, skill: &MarketplaceSkill) -> bool {
    if meta.source.as_deref() != Some("marketplace") {
        return false;
    }
    if meta.marketplace_source_id.as_deref() != Some(skill.source_id.as_str()) {
        return false;
    }
    if let Some(meta_skill_id) = meta.marketplace_skill_id.as_deref() {
        return meta_skill_id == skill.id;
    }
    if let (Some(meta_slug), Some(skill_slug)) = (
        meta.marketplace_skill_slug.as_deref(),
        skill.slug.as_deref(),
    ) {
        return meta_slug == skill_slug;
    }
    true
}

fn preferred_marketplace_install_dir(skills_dir: &Path, skill: &MarketplaceSkill) -> PathBuf {
    let dir_name = sanitize_install_dir_name(skill.name.as_str())
        .or_else(|| {
            skill.slug.as_deref().and_then(|slug| {
                sanitize_install_dir_name(slug.rsplit('/').next().unwrap_or_default())
            })
        })
        .unwrap_or_else(|| {
            sanitize_install_dir_name(skill.id.as_str()).unwrap_or_else(|| "skill".to_string())
        });
    skills_dir.join(dir_name)
}

fn legacy_marketplace_install_dir(skills_dir: &Path, skill: &MarketplaceSkill) -> Option<PathBuf> {
    let legacy = skills_dir.join(&skill.id);
    let preferred = preferred_marketplace_install_dir(skills_dir, skill);
    if legacy == preferred {
        None
    } else {
        Some(legacy)
    }
}

fn find_installed_marketplace_skill(
    skills_dir: &Path,
    skill: &MarketplaceSkill,
) -> Option<(PathBuf, LocalMarketplaceMeta)> {
    let mut candidates = vec![preferred_marketplace_install_dir(skills_dir, skill)];
    if let Some(legacy) = legacy_marketplace_install_dir(skills_dir, skill) {
        candidates.push(legacy);
    }

    for dir in candidates {
        if !dir.exists() {
            continue;
        }
        let meta = match read_marketplace_meta(&dir) {
            Ok(meta) => meta,
            Err(_) => continue,
        };
        if is_marketplace_meta_for_skill(&meta, skill) {
            return Some((dir, meta));
        }
    }
    None
}

fn sanitize_install_dir_name(input: &str) -> Option<String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return None;
    }

    let mut normalized = String::with_capacity(trimmed.len());
    let mut prev_dash = false;
    for ch in trimmed.chars() {
        let unsafe_char =
            ch.is_control() || matches!(ch, '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|');
        if unsafe_char {
            if !prev_dash {
                normalized.push('-');
                prev_dash = true;
            }
            continue;
        }
        normalized.push(ch);
        prev_dash = false;
    }

    let cleaned = normalized
        .trim_matches(|c| c == '-' || c == '.')
        .to_string();
    if cleaned.is_empty() {
        None
    } else {
        Some(cleaned)
    }
}

#[cfg(test)]
mod tests {
    use super::{
        build_marketplace_external_url, build_skill_tree_from_tree_entries, collect_file_nodes,
        extract_root_skill_dirs_from_tree_entries, extract_skill_description_from_markdown,
        get_cached_github_tree, github_tree_cache, github_tree_cache_key, normalize_github_token,
        set_cached_github_tree, should_include_github_root_dir, CachedGitHubTree, GitHubContent,
        GitHubTreeEntry, InstallStatus, MarketplaceCache, MarketplaceSkill,
        MarketplaceSkillsResponse, PersistedMarketplaceCacheEntry, PersistedMarketplaceState,
        PersistedSkillDescriptionEntry, GITHUB_TREE_CACHE_TTL, PERSISTED_CACHE_TTL,
        PERSISTED_SKILL_DESCRIPTION_CACHE_TTL,
    };
    use std::collections::HashSet;
    use std::fs;
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    use crate::test_support::with_temp_home;

    #[test]
    fn normalize_github_token_returns_none_for_missing_or_blank_token() {
        assert_eq!(normalize_github_token(None), None);
        assert_eq!(normalize_github_token(Some("")), None);
        assert_eq!(normalize_github_token(Some("   ")), None);
    }

    #[test]
    fn normalize_github_token_trims_valid_token() {
        assert_eq!(
            normalize_github_token(Some("  ghp_example_token  ")),
            Some("ghp_example_token".to_string())
        );
    }

    #[test]
    fn build_marketplace_external_url_uses_skill_path_for_github_repo() {
        let link = build_marketplace_external_url(
            None,
            Some("https://github.com/foo/bar"),
            Some(".claude/skills/my-skill"),
        );
        assert_eq!(
            link,
            Some("https://github.com/foo/bar/tree/HEAD/.claude/skills/my-skill".to_string())
        );
    }

    #[test]
    fn build_marketplace_external_url_prefers_raw_link_when_available() {
        let link = build_marketplace_external_url(
            Some("https://github.com/foo/bar/tree/main/.claude/skills/my-skill"),
            Some("https://github.com/foo/bar"),
            Some(".claude/skills/my-skill"),
        );
        assert_eq!(
            link,
            Some("https://github.com/foo/bar/tree/main/.claude/skills/my-skill".to_string())
        );
    }

    #[test]
    fn build_marketplace_external_url_returns_repo_for_non_github() {
        let link = build_marketplace_external_url(
            None,
            Some("https://example.com/skills/my-skill"),
            Some(".claude/skills/my-skill"),
        );
        assert_eq!(
            link,
            Some("https://example.com/skills/my-skill".to_string())
        );
    }

    #[test]
    fn derive_github_repo_and_skill_path_prefers_install_url_tree_path() {
        let (repo_url, skill_path) = super::derive_github_repo_and_skill_path(
            Some("https://github.com/foo/bar/tree/main/.claude/skills/demo"),
            "foo/bar/other/path",
        );
        assert_eq!(repo_url, Some("https://github.com/foo/bar".to_string()));
        assert_eq!(skill_path, Some(".claude/skills/demo".to_string()));
    }

    #[test]
    fn derive_github_repo_and_skill_path_falls_back_to_slug() {
        let (repo_url, skill_path) =
            super::derive_github_repo_and_skill_path(None, "foo/bar/.claude/skills/demo");
        assert_eq!(repo_url, Some("https://github.com/foo/bar".to_string()));
        assert_eq!(skill_path, Some(".claude/skills/demo".to_string()));
    }

    #[test]
    fn derive_github_repo_and_skill_path_uses_slug_path_when_install_url_is_repo_root() {
        let (repo_url, skill_path) = super::derive_github_repo_and_skill_path(
            Some("https://github.com/anthropics/skills"),
            "anthropics/skills/skills/skill-creator",
        );
        assert_eq!(
            repo_url,
            Some("https://github.com/anthropics/skills".to_string())
        );
        assert_eq!(skill_path, Some("skills/skill-creator".to_string()));
    }

    #[test]
    fn derive_github_repo_and_skill_path_strips_manifest_file_from_blob_url() {
        let (repo_url, skill_path) = super::derive_github_repo_and_skill_path(
            Some("https://github.com/foo/bar/blob/main/skills/demo/SKILL.md"),
            "foo/bar/skills/demo",
        );
        assert_eq!(repo_url, Some("https://github.com/foo/bar".to_string()));
        assert_eq!(skill_path, Some("skills/demo".to_string()));
    }

    #[test]
    fn build_skill_path_candidates_adds_common_prefixes_for_single_segment_path() {
        let candidates = super::build_skill_path_candidates("docfactory-prd");
        assert_eq!(
            candidates,
            vec![
                "docfactory-prd".to_string(),
                "skills/docfactory-prd".to_string(),
                ".claude/skills/docfactory-prd".to_string(),
            ]
        );
    }

    #[test]
    fn build_skill_path_candidates_keeps_nested_path_without_extra_prefixes() {
        let candidates = super::build_skill_path_candidates("skills/docfactory-prd");
        assert_eq!(candidates, vec!["skills/docfactory-prd".to_string()]);
    }

    #[test]
    fn normalize_local_path_strips_resolved_skill_path_prefix() {
        let stripped = super::normalize_local_path("skills/infsh-cli/SKILL.md", "skills/infsh-cli");
        assert_eq!(stripped, "SKILL.md");

        let stripped_with_nested =
            super::normalize_local_path("skills/infsh-cli/assets/icon.png", "skills/infsh-cli");
        assert_eq!(stripped_with_nested, "assets/icon.png");

        let kept_when_no_prefix =
            super::normalize_local_path("skills/infsh-cli/SKILL.md", "infsh-cli");
        assert_eq!(kept_when_no_prefix, "skills/infsh-cli/SKILL.md");
    }

    #[test]
    fn infer_skill_path_candidates_from_tree_entries_matches_suffix_paths() {
        let entries = vec![
            GitHubTreeEntry {
                path: "skills/frameworks/nestjs/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
            GitHubTreeEntry {
                path: "skills/backend/fastify/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
        ];

        let candidates = super::infer_skill_path_candidates_from_tree_entries(&entries, "nestjs");
        assert_eq!(candidates, vec!["skills/frameworks/nestjs".to_string()]);
    }

    #[test]
    fn infer_skill_path_candidates_from_tree_entries_falls_back_to_basename_match() {
        let entries = vec![
            GitHubTreeEntry {
                path: "skills/frameworks/nestjs/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
            GitHubTreeEntry {
                path: "skills/frameworks/express/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
        ];

        let candidates =
            super::infer_skill_path_candidates_from_tree_entries(&entries, "catalog/nestjs");
        assert_eq!(candidates, vec!["skills/frameworks/nestjs".to_string()]);
    }

    #[test]
    fn infer_skill_path_candidates_from_tree_entries_falls_back_to_repo_root_skill_manifest() {
        let entries = vec![
            GitHubTreeEntry {
                path: "SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
            GitHubTreeEntry {
                path: "README.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
        ];

        let candidates =
            super::infer_skill_path_candidates_from_tree_entries(&entries, "skill-as-a-service");
        assert_eq!(candidates, vec![String::new()]);
    }

    #[test]
    fn should_include_github_root_dir_filters_hidden_dir() {
        let hidden = GitHubContent {
            name: ".claude-plugin".to_string(),
            path: ".claude-plugin".to_string(),
            kind: "dir".to_string(),
            download_url: None,
            url: None,
            size: None,
        };
        assert!(!should_include_github_root_dir(&hidden, None));
    }

    #[test]
    fn extract_root_skill_dirs_from_tree_entries_keeps_only_root_skill_dirs() {
        let entries = vec![
            GitHubTreeEntry {
                path: "activecampaign-automation/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
            GitHubTreeEntry {
                path: ".claude-plugin/README.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
            GitHubTreeEntry {
                path: "nested/path/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: None,
            },
        ];
        let dirs = extract_root_skill_dirs_from_tree_entries(&entries);
        let expected: HashSet<String> = ["activecampaign-automation".to_string()]
            .into_iter()
            .collect();
        assert_eq!(dirs, expected);
    }

    #[test]
    fn build_skill_tree_from_tree_entries_builds_nested_tree_and_download_urls() {
        let entries = vec![
            GitHubTreeEntry {
                path: "my-skill/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-skill".to_string()),
            },
            GitHubTreeEntry {
                path: "my-skill/docs/guide.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-guide".to_string()),
            },
        ];
        let tree = build_skill_tree_from_tree_entries(&entries, "my-skill", "foo", "bar", "main")
            .expect("tree should exist");

        assert_eq!(tree.name, "my-skill");
        assert_eq!(count_files(&tree), 2);

        let mut urls = Vec::new();
        collect_file_nodes(&tree, &mut urls);
        assert!(urls.iter().any(|node| node.path == "my-skill/SKILL.md"));
        assert!(urls.iter().any(|node| {
            node.download_url
                .as_ref()
                .map(|url| {
                    url.contains("raw.githubusercontent.com/foo/bar/main/my-skill/docs/guide.md")
                })
                .unwrap_or(false)
        }));
    }

    #[test]
    fn compute_skill_revision_from_tree_entries_changes_when_blob_sha_changes() {
        let entries_v1 = vec![
            GitHubTreeEntry {
                path: "alpha/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-a1".to_string()),
            },
            GitHubTreeEntry {
                path: "alpha/docs.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-a2".to_string()),
            },
        ];
        let entries_v2 = vec![
            GitHubTreeEntry {
                path: "alpha/SKILL.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-a1".to_string()),
            },
            GitHubTreeEntry {
                path: "alpha/docs.md".to_string(),
                kind: "blob".to_string(),
                sha: Some("sha-a2-updated".to_string()),
            },
        ];

        let rev1 = super::compute_skill_revision_from_tree_entries(&entries_v1, "alpha")
            .expect("revision should exist");
        let rev2 = super::compute_skill_revision_from_tree_entries(&entries_v2, "alpha")
            .expect("revision should exist");
        assert_ne!(rev1, rev2, "revision should change when blob sha changes");
    }

    #[test]
    fn check_install_status_returns_update_available_when_revision_mismatch() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let skill = sample_marketplace_skill("source-a", "alpha");
            let install_dir = skills_dir.join(&skill.id);
            fs::create_dir_all(&install_dir).expect("create install dir");

            let meta = serde_json::json!({
                "name": skill.name,
                "source": "marketplace",
                "marketplace_source_id": skill.source_id,
                "marketplace_skill_id": skill.id,
                "remote_revision": "rev-local",
            });
            fs::write(
                install_dir.join("meta.json"),
                serde_json::to_string_pretty(&meta).expect("serialize meta"),
            )
            .expect("write meta");

            let mut remote_skill = skill.clone();
            remote_skill.remote_revision = Some("rev-remote".to_string());

            let status =
                super::MarketplaceService::check_install_status(&remote_skill, &skills_dir);
            assert_eq!(status, InstallStatus::UpdateAvailable);
        });
    }

    #[test]
    fn check_install_status_detects_installation_under_skill_name_directory() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let mut skill = sample_marketplace_skill("source-a", "alpha");
            skill.name = "skill-creator".to_string();

            let install_dir = skills_dir.join("skill-creator");
            fs::create_dir_all(&install_dir).expect("create install dir");

            let meta = serde_json::json!({
                "name": skill.name,
                "source": "marketplace",
                "marketplace_source_id": skill.source_id,
                "marketplace_skill_id": skill.id,
                "remote_revision": "rev-remote",
            });
            fs::write(
                install_dir.join("meta.json"),
                serde_json::to_string_pretty(&meta).expect("serialize meta"),
            )
            .expect("write meta");

            let mut remote_skill = skill.clone();
            remote_skill.remote_revision = Some("rev-remote".to_string());

            let status =
                super::MarketplaceService::check_install_status(&remote_skill, &skills_dir);
            assert_eq!(status, InstallStatus::Installed);
        });
    }

    #[test]
    fn preferred_marketplace_install_dir_uses_skill_name() {
        with_temp_home(|home| {
            let skills_dir = home.join(".skills-manager").join("skills");
            let mut skill = sample_marketplace_skill("source-a", "alpha");
            skill.name = "skill-creator".to_string();

            let dir = super::preferred_marketplace_install_dir(&skills_dir, &skill);
            assert_eq!(dir, skills_dir.join("skill-creator"));
        });
    }

    #[test]
    fn install_revision_prefers_marketplace_revision_over_tree_hash() {
        let mut skill = sample_marketplace_skill("source-a", "alpha");
        skill.remote_revision = Some("market-api-fnv64:abcdef".to_string());

        let files = vec![super::SkillFileNode {
            name: "SKILL.md".to_string(),
            path: "alpha/SKILL.md".to_string(),
            is_dir: false,
            download_url: Some("https://example.com/SKILL.md".to_string()),
            sha: Some("sha-local".to_string()),
            children: None,
        }];

        let resolved = skill
            .remote_revision
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string())
            .or_else(|| super::compute_skill_revision_from_file_nodes(&files));

        assert_eq!(resolved.as_deref(), Some("market-api-fnv64:abcdef"));
    }

    #[test]
    fn github_tree_cache_round_trip() {
        let entries = vec![GitHubTreeEntry {
            path: "skill/SKILL.md".to_string(),
            kind: "blob".to_string(),
            sha: None,
        }];
        let owner = "cache-owner-round-trip";
        let repo = "cache-repo-round-trip";

        set_cached_github_tree(owner, repo, "main", &entries);

        let cached = get_cached_github_tree(owner, repo).expect("cache should exist");
        assert_eq!(cached.branch, "main");
        assert_eq!(cached.tree.len(), 1);
    }

    #[test]
    fn get_cached_github_tree_discards_expired_entry() {
        let owner = "cache-owner-expired";
        let repo = "cache-repo-expired";
        let key = github_tree_cache_key(owner, repo);
        {
            let mut guard = github_tree_cache().lock().expect("lock cache");
            guard.insert(
                key,
                CachedGitHubTree {
                    fetched_at: SystemTime::now() - GITHUB_TREE_CACHE_TTL - Duration::from_secs(1),
                    branch: "main".to_string(),
                    tree: vec![GitHubTreeEntry {
                        path: "skill/SKILL.md".to_string(),
                        kind: "blob".to_string(),
                        sha: None,
                    }],
                },
            );
        }

        assert!(get_cached_github_tree(owner, repo).is_none());
    }

    #[test]
    fn extract_skill_description_from_markdown_prefers_frontmatter_description() {
        let markdown = r#"---
name: test-skill
description: "来自 frontmatter 的描述"
---

# Test Skill

这是正文第一段。
"#;

        let description = extract_skill_description_from_markdown(markdown);
        assert_eq!(description, Some("来自 frontmatter 的描述".to_string()));
    }

    #[test]
    fn extract_skill_description_from_markdown_falls_back_to_first_paragraph() {
        let markdown = r#"# Test Skill

这是第一段描述，会被提取出来。

## 使用方式

- 步骤 1
"#;

        let description = extract_skill_description_from_markdown(markdown);
        assert_eq!(
            description,
            Some("这是第一段描述，会被提取出来。".to_string())
        );
    }

    #[test]
    fn marketplace_cache_persists_primary_listing_across_instances() {
        with_temp_home(|_| {
            let cache = MarketplaceCache::default();
            let expected = sample_marketplace_skill("source-a", "skill-a");
            cache.set(vec![expected.clone()], None, false, None);

            let restored = MarketplaceCache::default()
                .get_fresh_with_meta(1, &None, &None)
                .expect("expected persisted cache on new instance");

            assert_eq!(restored.skills.len(), 1);
            assert_eq!(restored.skills[0].id, expected.id);
            assert_eq!(restored.skills[0].name, expected.name);
        });
    }

    #[test]
    fn marketplace_cache_migrates_legacy_single_state_format() {
        with_temp_home(|_| {
            let now_secs = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("now should be after epoch")
                .as_secs();
            let legacy_payload = serde_json::json!({
                "fetched_at_unix_secs": now_secs,
                "skills": [sample_marketplace_skill("source-a", "legacy-skill")],
                "query": null,
                "has_more": false,
                "source_filter": null
            });

            let path = super::persisted_marketplace_cache_path().expect("cache path should exist");
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).expect("create cache dir");
            }
            fs::write(
                &path,
                serde_json::to_string(&legacy_payload).expect("serialize legacy payload"),
            )
            .expect("write legacy payload");

            let restored = MarketplaceCache::default()
                .get_fresh_with_meta(1, &None, &None)
                .expect("legacy payload should be restored");
            assert_eq!(restored.skills.len(), 1);
            assert_eq!(restored.skills[0].id, "source-a::legacy-skill");

            let migrated_content = fs::read_to_string(&path).expect("read migrated cache");
            let migrated: PersistedMarketplaceState =
                serde_json::from_str(&migrated_content).expect("parse migrated cache");
            assert_eq!(migrated.pages.len(), 1);
            assert_eq!(migrated.pages[0].page, 1);
        });
    }

    #[test]
    fn marketplace_cache_separates_pages_by_cache_key() {
        with_temp_home(|_| {
            let cache = MarketplaceCache::default();
            let page1 = sample_marketplace_skill("source-a", "page-1");
            let page2 = sample_marketplace_skill("source-a", "page-2");

            cache.set_page(
                1,
                None,
                None,
                MarketplaceSkillsResponse {
                    skills: vec![page1.clone()],
                    has_more: true,
                },
            );
            cache.set_page(
                2,
                None,
                None,
                MarketplaceSkillsResponse {
                    skills: vec![page2.clone()],
                    has_more: false,
                },
            );

            let restored_page1 = cache
                .get_fresh_with_meta(1, &None, &None)
                .expect("page 1 should be cached");
            let restored_page2 = cache
                .get_fresh_with_meta(2, &None, &None)
                .expect("page 2 should be cached");

            assert_eq!(restored_page1.skills[0].id, page1.id);
            assert_eq!(restored_page2.skills[0].id, page2.id);
        });
    }

    #[test]
    fn marketplace_cache_ignores_expired_persisted_listing() {
        with_temp_home(|_| {
            let expired_secs = (SystemTime::now() - PERSISTED_CACHE_TTL - Duration::from_secs(1))
                .duration_since(UNIX_EPOCH)
                .expect("expired timestamp should be after unix epoch")
                .as_secs();
            let persisted = PersistedMarketplaceState {
                pages: vec![PersistedMarketplaceCacheEntry {
                    page: 1,
                    query: None,
                    source_filter: None,
                    fetched_at_unix_secs: expired_secs,
                    response: MarketplaceSkillsResponse {
                        skills: vec![sample_marketplace_skill("source-a", "skill-a")],
                        has_more: false,
                    },
                }],
            };

            let path = super::persisted_marketplace_cache_path().expect("cache path should exist");
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).expect("create cache dir");
            }
            fs::write(
                &path,
                serde_json::to_string(&persisted).expect("serialize persisted cache"),
            )
            .expect("write cache file");

            let restored = MarketplaceCache::default().get_fresh_with_meta(1, &None, &None);
            assert!(
                restored.is_none(),
                "expired persisted cache should not be used"
            );
        });
    }

    #[test]
    fn marketplace_cache_invalidate_removes_persisted_listing() {
        with_temp_home(|_| {
            let cache = MarketplaceCache::default();
            cache.set(
                vec![sample_marketplace_skill("source-a", "skill-a")],
                None,
                false,
                None,
            );
            cache.invalidate();

            let restored = MarketplaceCache::default().get_fresh_with_meta(1, &None, &None);
            assert!(restored.is_none(), "cache should be empty after invalidate");
        });
    }

    #[test]
    fn skill_description_cache_persists_to_disk() {
        with_temp_home(|home| {
            if let Ok(mut guard) = super::skill_description_cache().lock() {
                guard.clear();
            }

            super::set_cached_skill_description(
                "https://github.com/example/repo::skill-a",
                Some("cached description".to_string()),
            );

            let cache_path = home
                .join(".skills-manager")
                .join("cache")
                .join("marketplace-skill-descriptions.json");
            assert!(
                cache_path.exists(),
                "description cache file should be persisted"
            );
        });
    }

    #[test]
    fn load_persisted_skill_description_cache_ignores_expired_entries() {
        with_temp_home(|home| {
            let cache_path = home
                .join(".skills-manager")
                .join("cache")
                .join("marketplace-skill-descriptions.json");
            if let Some(parent) = cache_path.parent() {
                fs::create_dir_all(parent).expect("create cache dir");
            }

            let now_secs = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("current time should be after unix epoch")
                .as_secs();
            let expired_secs =
                now_secs.saturating_sub(PERSISTED_SKILL_DESCRIPTION_CACHE_TTL.as_secs() + 1);
            let payload = std::collections::HashMap::from([
                (
                    "fresh-key".to_string(),
                    PersistedSkillDescriptionEntry {
                        fetched_at_unix_secs: now_secs,
                        description: Some("fresh".to_string()),
                    },
                ),
                (
                    "expired-key".to_string(),
                    PersistedSkillDescriptionEntry {
                        fetched_at_unix_secs: expired_secs,
                        description: Some("expired".to_string()),
                    },
                ),
            ]);

            fs::write(
                &cache_path,
                serde_json::to_string(&payload).expect("serialize payload"),
            )
            .expect("write cache file");

            let loaded = super::load_persisted_skill_description_cache();
            assert!(loaded.contains_key("fresh-key"));
            assert!(!loaded.contains_key("expired-key"));
        });
    }

    #[test]
    fn filter_marketplace_skills_by_query_matches_core_fields_case_insensitive() {
        let mut alpha = sample_marketplace_skill("source-a", "alpha-skill");
        alpha.description = Some("Zero trust workflow".to_string());
        alpha.author = Some("Alice".to_string());
        alpha.source_name = "GitHub Alpha".to_string();

        let mut beta = sample_marketplace_skill("source-b", "beta-tool");
        beta.description = Some("Data pipeline".to_string());
        beta.author = Some("Bob".to_string());
        beta.source_name = "Internal".to_string();

        let skills = vec![alpha.clone(), beta.clone()];

        let by_name = super::filter_marketplace_skills_by_query(skills.clone(), Some("ALPHA"));
        assert_eq!(by_name.len(), 1);
        assert_eq!(by_name[0].id, alpha.id);

        let by_desc = super::filter_marketplace_skills_by_query(skills.clone(), Some("workflow"));
        assert_eq!(by_desc.len(), 1);
        assert_eq!(by_desc[0].id, alpha.id);

        let by_author = super::filter_marketplace_skills_by_query(skills.clone(), Some("alice"));
        assert_eq!(by_author.len(), 1);
        assert_eq!(by_author[0].id, alpha.id);

        let by_source = super::filter_marketplace_skills_by_query(skills, Some("github alpha"));
        assert_eq!(by_source.len(), 1);
        assert_eq!(by_source[0].id, alpha.id);
    }

    #[test]
    fn filter_marketplace_skills_by_query_returns_all_for_empty_query() {
        let skills = vec![
            sample_marketplace_skill("source-a", "alpha"),
            sample_marketplace_skill("source-b", "beta"),
        ];

        let filtered_blank = super::filter_marketplace_skills_by_query(skills.clone(), Some("   "));
        assert_eq!(filtered_blank.len(), skills.len());

        let filtered_none = super::filter_marketplace_skills_by_query(skills.clone(), None);
        assert_eq!(filtered_none.len(), skills.len());
    }

    #[test]
    fn filter_marketplace_skills_by_query_matches_tags() {
        let mut alpha = sample_marketplace_skill("source-a", "alpha-skill");
        alpha.tags = vec!["email".to_string(), "gmail".to_string()];
        let mut beta = sample_marketplace_skill("source-b", "beta-tool");
        beta.tags = vec!["calendar".to_string()];

        let skills = vec![alpha.clone(), beta];

        let by_tag = super::filter_marketplace_skills_by_query(skills, Some("email"));
        assert_eq!(by_tag.len(), 1);
        assert_eq!(by_tag[0].id, alpha.id);
    }

    #[test]
    fn filter_marketplace_skills_by_query_supports_token_and_matching() {
        // 分词 AND：两个 token 都要命中（可在不同字段）
        let mut alpha = sample_marketplace_skill("source-a", "alpha-skill");
        alpha.name = "Email Manager".to_string();
        alpha.description = Some("Gmail integration".to_string());

        let mut beta = sample_marketplace_skill("source-b", "beta-tool");
        beta.name = "Email Tool".to_string();
        beta.description = Some("Calendar integration".to_string());

        let skills = vec![alpha.clone(), beta];

        // "email gmail" → alpha 命中（name 有 email，description 有 gmail）
        // beta 只有 email 没有 gmail → 不命中
        let filtered = super::filter_marketplace_skills_by_query(skills, Some("email gmail"));
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].id, alpha.id);
    }

    #[test]
    fn map_clawhub_search_item_to_skill_maps_fields_and_owner() {
        let item = super::ClawhubSearchItem {
            score: Some(2.5),
            slug: "email-skill".to_string(),
            display_name: Some("Email".to_string()),
            summary: Some("  Email management  ".to_string()),
            version: Some("1.2.0".to_string()),
            downloads: Some(8905),
            owner_handle: Some("porteden".to_string()),
        };
        let skill = super::map_clawhub_search_item_to_skill(item);
        assert_eq!(skill.slug.as_deref(), Some("email-skill"));
        assert_eq!(skill.name, "Email");
        assert_eq!(skill.description.as_deref(), Some("Email management"));
        assert_eq!(skill.author.as_deref(), Some("porteden"));
        assert_eq!(skill.clawhub_owner.as_deref(), Some("porteden"));
        assert_eq!(skill.clawhub_version.as_deref(), Some("1.2.0"));
        assert_eq!(skill.install_count, Some(8905));
        assert!(skill.external_url.as_deref().unwrap().contains("porteden"));
        assert!(skill.external_url.as_deref().unwrap().contains("email-skill"));
        assert!(skill.tags.is_empty(), "tags should default to empty");
    }

    fn sample_marketplace_skill(source_id: &str, slug: &str) -> MarketplaceSkill {
        MarketplaceSkill {
            id: format!("{}::{}", source_id, slug),
            slug: Some(slug.to_string()),
            name: slug.to_string(),
            description: None,
            author: Some("tester".to_string()),
            source_id: source_id.to_string(),
            source_name: "source".to_string(),
            install_count: None,
            install_url: Some(
                "https://github.com/example/repo/tree/main/example-skill".to_string(),
            ),
            created_at: Some(1_771_234_567),
            repo_url: Some("https://github.com/example/repo".to_string()),
            skill_path: Some(slug.to_string()),
            external_url: None,
            remote_revision: None,
            tags: vec!["test".to_string()],
            install_status: InstallStatus::NotInstalled,
            clawhub_slug: None,
            clawhub_owner: None,
            clawhub_version: None,
        }
    }

    fn count_files(node: &super::SkillFileNode) -> usize {
        if !node.is_dir {
            return 1;
        }
        node.children
            .as_ref()
            .map(|children| children.iter().map(count_files).sum())
            .unwrap_or(0)
    }

    #[test]
    fn strip_archive_top_level_prefix_removes_repeated_slug_prefixes() {
        use super::strip_archive_top_level_prefix;

        // Single prefix
        assert_eq!(
            strip_archive_top_level_prefix("my-skill/SKILL.md", "my-skill"),
            "SKILL.md"
        );
        // Repeated prefix (the #49 bug)
        assert_eq!(
            strip_archive_top_level_prefix("my-skill/my-skill/SKILL.md", "my-skill"),
            "SKILL.md"
        );
        // Triple prefix
        assert_eq!(
            strip_archive_top_level_prefix("a/a/a/file.txt", "a"),
            "file.txt"
        );
        // No prefix match — unchanged
        assert_eq!(
            strip_archive_top_level_prefix("other/SKILL.md", "my-skill"),
            "other/SKILL.md"
        );
        // Leading ./ is trimmed first
        assert_eq!(
            strip_archive_top_level_prefix("./my-skill/SKILL.md", "my-skill"),
            "SKILL.md"
        );
    }
}
