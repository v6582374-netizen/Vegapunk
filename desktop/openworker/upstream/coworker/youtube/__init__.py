"""YouTube automation domain services.

The module deliberately owns the deterministic fetch pipeline instead of exposing the
pipeline as model tools.  Automation is the trigger; this package is the source of truth
for subscriptions, video discovery, captions, and user selection state.
"""

from .client import (
    CaptionUnavailable,
    YouTubeAuthError,
    YouTubeClient,
    YouTubeClientError,
)
from .service import YouTubeAutomationService, YouTubeRunResult
from .store import YouTubeStore
from .translation import (
    DEFAULT_TRANSLATION_PROMPT,
    YouTubeTranslationError,
    YouTubeTranslationService,
)

__all__ = [
    "DEFAULT_TRANSLATION_PROMPT",
    "CaptionUnavailable",
    "YouTubeAuthError",
    "YouTubeAutomationService",
    "YouTubeClient",
    "YouTubeClientError",
    "YouTubeRunResult",
    "YouTubeStore",
    "YouTubeTranslationError",
    "YouTubeTranslationService",
]
