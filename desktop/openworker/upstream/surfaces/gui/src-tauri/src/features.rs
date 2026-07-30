/// Feature flags for controlling Pro functionality
///
/// This module provides a centralized way to check which features are enabled
/// based on the user's license tier.

use crate::models::config::LicenseInfo;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Edition {
    Community,
    Pro,
}

/// Feature flags that can be toggled based on license
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Feature {
    /// Cloud sync functionality (Pro only)
    CloudSync,
    /// Advanced AI translation without rate limits (Pro only)
    UnlimitedTranslation,
    /// Team collaboration features (Pro only)
    TeamCollaboration,
    /// Usage analytics and insights (Pro only)
    Analytics,
    /// Priority support (Pro only)
    PrioritySupport,
}

impl Feature {
    /// Check if this feature is available in the given edition
    pub fn is_available_in(self, edition: Edition) -> bool {
        match self {
            // Cloud sync is Pro-only
            Feature::CloudSync => matches!(edition, Edition::Pro),
            Feature::UnlimitedTranslation => matches!(edition, Edition::Pro),
            Feature::TeamCollaboration => matches!(edition, Edition::Pro),
            Feature::Analytics => matches!(edition, Edition::Pro),
            Feature::PrioritySupport => matches!(edition, Edition::Pro),
        }
    }
}

/// Get the current edition based on license info
pub fn get_edition(license: Option<&LicenseInfo>) -> Edition {
    match license {
        Some(info) if info.is_valid() => Edition::Pro,
        _ => Edition::Community,
    }
}

/// Check if a feature is enabled for the current user
pub fn is_feature_enabled(feature: Feature, license: Option<&LicenseInfo>) -> bool {
    let edition = get_edition(license);
    feature.is_available_in(edition)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn community_edition_has_no_pro_features() {
        assert!(!Feature::CloudSync.is_available_in(Edition::Community));
        assert!(!Feature::UnlimitedTranslation.is_available_in(Edition::Community));
        assert!(!Feature::TeamCollaboration.is_available_in(Edition::Community));
    }

    #[test]
    fn pro_edition_has_all_features() {
        assert!(Feature::CloudSync.is_available_in(Edition::Pro));
        assert!(Feature::UnlimitedTranslation.is_available_in(Edition::Pro));
        assert!(Feature::TeamCollaboration.is_available_in(Edition::Pro));
    }
}
