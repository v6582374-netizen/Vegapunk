use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedTranslation {
    pub name: String,
    pub description: String,
    #[serde(default)]
    pub content_md: Option<String>,
}

pub struct CacheKey<'a> {
    pub base_url: &'a str,
    pub model: &'a str,
    pub target_lang: &'a str,
    pub source_name: &'a str,
    pub source_description: &'a str,
    pub source_content_md: Option<&'a str>,
}

impl<'a> CacheKey<'a> {
    pub fn digest(&self) -> String {
        let mut hasher = Sha256::new();
        hasher.update(self.base_url.as_bytes());
        hasher.update(b"|");
        hasher.update(self.model.as_bytes());
        hasher.update(b"|");
        hasher.update(self.target_lang.as_bytes());
        hasher.update(b"|");
        hasher.update(self.source_name.as_bytes());
        hasher.update(b"\x1e");
        hasher.update(self.source_description.as_bytes());
        hasher.update(b"\x1e");
        if let Some(md) = self.source_content_md {
            hasher.update(md.as_bytes());
        }
        format!("{:x}", hasher.finalize())
    }
}

pub struct TranslationCache {
    root: PathBuf,
}

impl TranslationCache {
    pub fn new() -> Self {
        let root = dirs::home_dir()
            .unwrap_or_default()
            .join(".skills-manager")
            .join("cache")
            .join("translations");
        Self { root }
    }

    #[cfg(test)]
    pub fn with_root(root: PathBuf) -> Self {
        Self { root }
    }

    fn path_for(&self, digest: &str) -> PathBuf {
        self.root.join(format!("{digest}.json"))
    }

    pub fn get(&self, key: &CacheKey<'_>) -> Option<CachedTranslation> {
        let path = self.path_for(&key.digest());
        let data = fs::read(&path).ok()?;
        serde_json::from_slice(&data).ok()
    }

    pub fn put(&self, key: &CacheKey<'_>, value: &CachedTranslation) -> std::io::Result<()> {
        fs::create_dir_all(&self.root)?;
        let path = self.path_for(&key.digest());
        let data = serde_json::to_vec_pretty(value)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
        fs::write(&path, data)
    }

    pub fn clear(&self) -> std::io::Result<()> {
        if !self.root.exists() {
            return Ok(());
        }
        for entry in fs::read_dir(&self.root)? {
            let entry = entry?;
            if entry.file_type()?.is_file() {
                fs::remove_file(entry.path())?;
            }
        }
        Ok(())
    }
}

impl Default for TranslationCache {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn make_key<'a>(name: &'a str) -> CacheKey<'a> {
        CacheKey {
            base_url: "https://api.example.com/v1",
            model: "test-model",
            target_lang: "zh",
            source_name: name,
            source_description: "desc",
            source_content_md: None,
        }
    }

    #[test]
    fn digest_is_stable_for_same_inputs() {
        let k1 = make_key("alpha");
        let k2 = make_key("alpha");
        assert_eq!(k1.digest(), k2.digest());
    }

    #[test]
    fn digest_differs_when_content_md_differs() {
        let mut a = make_key("alpha");
        let mut b = make_key("alpha");
        let md_a = "x";
        let md_b = "y";
        a.source_content_md = Some(md_a);
        b.source_content_md = Some(md_b);
        assert_ne!(a.digest(), b.digest());
    }

    #[test]
    fn digest_differs_when_target_lang_differs() {
        let mut a = make_key("alpha");
        let mut b = make_key("alpha");
        a.target_lang = "zh";
        b.target_lang = "en";
        assert_ne!(a.digest(), b.digest());
    }

    #[test]
    fn put_then_get_returns_value() {
        let tmp = TempDir::new().unwrap();
        let cache = TranslationCache::with_root(tmp.path().to_path_buf());
        let key = make_key("alpha");
        let value = CachedTranslation {
            name: "翻译名".to_string(),
            description: "翻译描述".to_string(),
            content_md: Some("# 标题".to_string()),
        };
        cache.put(&key, &value).unwrap();

        let restored = cache.get(&key).expect("hit");
        assert_eq!(restored.name, "翻译名");
        assert_eq!(restored.content_md.as_deref(), Some("# 标题"));
    }

    #[test]
    fn get_returns_none_when_missing() {
        let tmp = TempDir::new().unwrap();
        let cache = TranslationCache::with_root(tmp.path().to_path_buf());
        assert!(cache.get(&make_key("missing")).is_none());
    }

    #[test]
    fn clear_removes_entries() {
        let tmp = TempDir::new().unwrap();
        let cache = TranslationCache::with_root(tmp.path().to_path_buf());
        let key = make_key("alpha");
        cache
            .put(
                &key,
                &CachedTranslation {
                    name: "n".to_string(),
                    description: "d".to_string(),
                    content_md: None,
                },
            )
            .unwrap();
        assert!(cache.get(&key).is_some());

        cache.clear().unwrap();
        assert!(cache.get(&key).is_none());
    }
}
