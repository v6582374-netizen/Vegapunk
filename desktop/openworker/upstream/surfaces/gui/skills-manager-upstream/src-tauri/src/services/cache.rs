use std::sync::RwLock;

use crate::models::{DetectedEditor, Skill, Tool};

/// Application-wide cache for expensive I/O operations
pub struct AppCache {
    pub skills: RwLock<Option<Vec<Skill>>>,
    pub tools: RwLock<Option<Vec<Tool>>>,
    pub editors: RwLock<Option<Vec<DetectedEditor>>>,
}

impl Default for AppCache {
    fn default() -> Self {
        Self {
            skills: RwLock::new(None),
            tools: RwLock::new(None),
            editors: RwLock::new(None),
        }
    }
}

impl AppCache {
    /// Get cached skills if available
    pub fn get_skills(&self) -> Option<Vec<Skill>> {
        self.skills.read().ok().and_then(|guard| guard.clone())
    }

    /// Set skills cache
    pub fn set_skills(&self, data: Vec<Skill>) {
        if let Ok(mut guard) = self.skills.write() {
            *guard = Some(data);
        }
    }

    /// Invalidate skills cache
    pub fn invalidate_skills(&self) {
        if let Ok(mut guard) = self.skills.write() {
            *guard = None;
        }
    }

    /// Get cached tools if available
    pub fn get_tools(&self) -> Option<Vec<Tool>> {
        self.tools.read().ok().and_then(|guard| guard.clone())
    }

    /// Set tools cache
    pub fn set_tools(&self, data: Vec<Tool>) {
        if let Ok(mut guard) = self.tools.write() {
            *guard = Some(data);
        }
    }

    /// Invalidate tools cache
    pub fn invalidate_tools(&self) {
        if let Ok(mut guard) = self.tools.write() {
            *guard = None;
        }
    }

    /// Get cached editors if available
    pub fn get_editors(&self) -> Option<Vec<DetectedEditor>> {
        self.editors.read().ok().and_then(|guard| guard.clone())
    }

    /// Set editors cache
    pub fn set_editors(&self, data: Vec<DetectedEditor>) {
        if let Ok(mut guard) = self.editors.write() {
            *guard = Some(data);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::AppCache;

    #[test]
    fn invalidate_tools_clears_cached_tools() {
        let cache = AppCache::default();
        cache.set_tools(Vec::new());
        assert!(
            cache.get_tools().is_some(),
            "tools cache should be populated"
        );

        cache.invalidate_tools();
        assert!(
            cache.get_tools().is_none(),
            "tools cache should be invalidated"
        );
    }
}
