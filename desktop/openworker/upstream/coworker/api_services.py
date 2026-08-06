"""Fixed paper-service connection settings.

This module owns only the Settings > API Services boundary. It deliberately does not participate
in search execution, Discovery Launch configuration, model routing, or any running session state.
Credentials are kept in the existing SecretStore and are never included in public responses.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import httpx

from .secrets import SecretStore

_MISSING = object()
_PROFILE_PREFIX = "api-service:"
_USER_AGENT = "Vegapunk/1.0 (local API Services settings)"


@dataclass(frozen=True)
class ApiServiceDescriptor:
    name: str
    title: str
    description: str
    credential_label: str
    credential_kind: str
    endpoint: str
    test_url: str
    environment_variables: tuple[str, ...]
    default_enabled: bool
    requires_credential: bool

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "credential_label": self.credential_label,
            "credential_kind": self.credential_kind,
            "endpoint": self.endpoint,
            "requires_credential": self.requires_credential,
        }


PAPER_SERVICE_CATALOG: tuple[ApiServiceDescriptor, ...] = (
    ApiServiceDescriptor(
        name="arxiv",
        title="arXiv",
        description="Preprint discovery",
        credential_label="Contact email",
        credential_kind="email",
        endpoint="https://export.arxiv.org/api/query",
        test_url="https://export.arxiv.org/api/query?search_query=all:%22test%22&max_results=1",
        environment_variables=("ARXIV_EMAIL",),
        default_enabled=True,
        requires_credential=False,
    ),
    ApiServiceDescriptor(
        name="semantic-scholar",
        title="Semantic Scholar",
        description="Citation graph",
        credential_label="API key",
        credential_kind="api_key",
        endpoint="https://api.semanticscholar.org/graph/v1",
        test_url="https://api.semanticscholar.org/graph/v1/paper/search?query=transformer&limit=1",
        environment_variables=("SEMANTIC_SCHOLAR_API_KEY", "S2_API_KEY"),
        default_enabled=True,
        requires_credential=False,
    ),
    ApiServiceDescriptor(
        name="crossref",
        title="Crossref",
        description="Metadata registry",
        credential_label="Contact email",
        credential_kind="email",
        endpoint="https://api.crossref.org/works",
        test_url="https://api.crossref.org/works",
        environment_variables=("CROSSREF_EMAIL",),
        default_enabled=True,
        requires_credential=False,
    ),
    ApiServiceDescriptor(
        name="core",
        title="CORE",
        description="Open access index",
        credential_label="API key",
        credential_kind="api_key",
        endpoint="https://api.core.ac.uk/v3/search/works",
        test_url="https://api.core.ac.uk/v3/search/works?q=test&page=1&pageSize=1",
        environment_variables=("CORE_API_KEY",),
        default_enabled=False,
        requires_credential=True,
    ),
)

_CATALOG = {service.name: service for service in PAPER_SERVICE_CATALOG}


def _descriptor(name: str) -> ApiServiceDescriptor | None:
    return _CATALOG.get(name)


def _profile_key(name: str) -> str:
    return f"{_PROFILE_PREFIX}{name}"


def _env_credential(service: ApiServiceDescriptor) -> str:
    for variable in service.environment_variables:
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    return ""


def _effective_credential(
    service: ApiServiceDescriptor,
    profile: Mapping[str, Any],
) -> tuple[str, str | None]:
    environment_value = _env_credential(service)
    if environment_value:
        return environment_value, "environment"
    stored_value = str(profile.get("credential") or "").strip()
    return (stored_value, "stored") if stored_value else ("", None)


def _credential_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public_service(
    service: ApiServiceDescriptor,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    credential, source = _effective_credential(service, profile)
    enabled = bool(profile.get("enabled", service.default_enabled))
    last_test_hash = str(profile.get("last_test_credential_hash") or "")
    # Services with optional contact credentials can be healthy without a stored value;
    # their successful empty-credential probe should remain a real connected state.
    test_matches_current = (
        (bool(credential) or not service.requires_credential)
        and last_test_hash == _credential_hash(credential)
    )
    if not enabled:
        status = "disabled"
    elif service.requires_credential and not credential:
        status = "not_configured"
    elif test_matches_current and profile.get("last_test_ok") is True:
        status = "connected"
    elif test_matches_current and profile.get("last_test_ok") is False:
        status = "error"
    else:
        status = "not_tested"
    return {
        **service.to_public(),
        "enabled": enabled,
        "credential_configured": bool(credential),
        "credential_source": source,
        "status": status,
        "last_test_at": profile.get("last_test_at"),
        "last_error": profile.get("last_test_error") if status == "error" else None,
    }


def get_api_services(secrets: SecretStore) -> list[dict[str, Any]]:
    """Return the fixed catalog with redacted credential state."""

    return [
        _public_service(service, secrets.get(_profile_key(service.name)) or {})
        for service in PAPER_SERVICE_CATALOG
    ]


def set_api_service(
    secrets: SecretStore,
    name: str,
    *,
    enabled: bool,
    credential: str | None | object = _MISSING,
) -> dict[str, Any]:
    """Save one service profile without changing any other service or runtime setting."""

    service = _descriptor(name)
    if service is None:
        return {"ok": False, "error": f"unknown API service: {name}"}
    profile = dict(secrets.get(_profile_key(name)) or {})
    profile["enabled"] = bool(enabled)
    if credential is not _MISSING:
        value = str(credential or "").strip()
        if value:
            profile["credential"] = value
        else:
            profile.pop("credential", None)
        profile.pop("last_test_at", None)
        profile.pop("last_test_ok", None)
        profile.pop("last_test_error", None)
        profile.pop("last_test_credential_hash", None)
    secrets.put(_profile_key(name), profile)
    return {"ok": True, "service": _public_service(service, profile)}


def _request_headers(service: ApiServiceDescriptor, credential: str) -> dict[str, str]:
    headers = {"User-Agent": _USER_AGENT}
    if service.credential_kind == "email" and credential:
        headers["User-Agent"] = f"{_USER_AGENT} (mailto:{credential})"
    elif service.name == "semantic-scholar" and credential:
        headers["x-api-key"] = credential
    elif service.name == "core" and credential:
        headers["Authorization"] = f"Bearer {credential}"
    return headers


def test_api_service(
    secrets: SecretStore,
    name: str,
    *,
    credential: str | None | object = _MISSING,
) -> dict[str, Any]:
    """Run one read-only fixed-endpoint check and return a redacted result."""

    service = _descriptor(name)
    if service is None:
        return {"ok": False, "status": "error", "error": f"unknown API service: {name}"}
    profile = dict(secrets.get(_profile_key(name)) or {})
    if credential is _MISSING:
        value, _ = _effective_credential(service, profile)
    else:
        value = str(credential or "").strip()
    if service.requires_credential and not value:
        return {
            "ok": False,
            "status": "not_configured",
            "error": f"Enter an API key to test {service.title}.",
        }

    try:
        response = httpx.get(
            service.test_url,
            headers=_request_headers(service, value),
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        checked_at = _checked_at()
        profile.update(
            {
                "last_test_at": checked_at,
                "last_test_ok": False,
                "last_test_error": f"{service.title} could not be reached.",
                "last_test_credential_hash": _credential_hash(value),
            }
        )
        secrets.put(_profile_key(name), profile)
        return {
            "ok": False,
            "status": "error",
            "checked_at": checked_at,
            "error": f"{service.title} could not be reached.",
        }

    checked_at = _checked_at()
    profile.update(
        {
            "last_test_at": checked_at,
            "last_test_ok": True,
            "last_test_error": None,
            "last_test_credential_hash": _credential_hash(value),
        }
    )
    secrets.put(_profile_key(name), profile)
    return {"ok": True, "status": "connected", "checked_at": checked_at}
