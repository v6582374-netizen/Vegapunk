"""The first Native Desktop Discovery facade.

Issue 01 only establishes the product-owned route and navigation contract.
Preparation, launch, and history records are intentionally empty until their
dependent implementation tickets add durable state behind this facade.
"""

from __future__ import annotations

from typing import Any


DISCOVERY_CONTEXTS = (
    {
        "id": "preparation",
        "label": "Preparation",
        "description": "Gather and review research inputs before a launch.",
    },
    {
        "id": "launch",
        "label": "Current Launch",
        "description": "Observe the active Discovery launch.",
    },
    {
        "id": "history",
        "label": "History",
        "description": "Review completed and interrupted Discovery launches.",
    },
)


class DiscoveryFacade:
    """Expose the stable shell contract from the existing sidecar process."""

    def snapshot(self) -> dict[str, Any]:
        return {
            "module": "discovery",
            "schema_version": 1,
            "contexts": [dict(context) for context in DISCOVERY_CONTEXTS],
            "active_context": "preparation",
            "preparation": {"status": "empty"},
            "current_launch": None,
            "history": [],
        }
