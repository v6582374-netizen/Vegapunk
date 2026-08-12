"""Fixed External data connection settings.

This module owns the Settings > External data connection boundary. Credentials are kept in the
existing SecretStore and are never included in public responses. Only the NLR registry metadata
and connection status are projected into a Discovery Launch snapshot; retrieval remains in the
runtime worker seam.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse

import httpx

from .secrets import SecretStore

_MISSING = object()
_PROFILE_PREFIX = "api-service:"
_USER_AGENT = "Vegapunk/1.0 (local API Services settings)"
_SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS = 1.1
_semantic_scholar_rate_lock = threading.Lock()
_semantic_scholar_next_request_at: dict[str, float] = {}


@dataclass(frozen=True)
class ApiServiceDescriptor:
    name: str
    title: str
    description: str
    credential_label: str
    credential_kind: str
    endpoint: str | None
    test_url: str | None
    docs_url: str | None
    docs_url_editable: bool
    environment_variables: tuple[str, ...]
    default_enabled: bool
    requires_credential: bool
    external_data_api_id: str | None
    external_data_source: str | None
    external_data_description: str | None

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "credential_label": self.credential_label,
            "credential_kind": self.credential_kind,
            "endpoint": self.endpoint,
            "docs_url": self.docs_url,
            "docs_url_editable": self.docs_url_editable,
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
        docs_url=None,
        docs_url_editable=False,
        environment_variables=("ARXIV_EMAIL",),
        default_enabled=True,
        requires_credential=False,
        external_data_api_id=None,
        external_data_source=None,
        external_data_description=None,
    ),
    ApiServiceDescriptor(
        name="semantic-scholar",
        title="Semantic Scholar",
        description="Citation graph",
        credential_label="API key",
        credential_kind="api_key",
        endpoint="https://api.semanticscholar.org/graph/v1",
        test_url="https://api.semanticscholar.org/graph/v1/paper/search?query=transformer&limit=1",
        docs_url=None,
        docs_url_editable=False,
        environment_variables=("SEMANTIC_SCHOLAR_API_KEY", "S2_API_KEY"),
        default_enabled=True,
        requires_credential=False,
        external_data_api_id=None,
        external_data_source=None,
        external_data_description=None,
    ),
    ApiServiceDescriptor(
        name="crossref",
        title="Crossref",
        description="Metadata registry",
        credential_label="Contact email",
        credential_kind="email",
        endpoint="https://api.crossref.org/works",
        test_url="https://api.crossref.org/works",
        docs_url=None,
        docs_url_editable=False,
        environment_variables=("CROSSREF_EMAIL",),
        default_enabled=True,
        requires_credential=False,
        external_data_api_id=None,
        external_data_source=None,
        external_data_description=None,
    ),
    ApiServiceDescriptor(
        name="core",
        title="CORE",
        description="Open access index",
        credential_label="API key",
        credential_kind="api_key",
        endpoint="https://api.core.ac.uk/v3/search/works",
        test_url="https://api.core.ac.uk/v3/search/works/?q=test&page=1&pageSize=1",
        docs_url=None,
        docs_url_editable=False,
        environment_variables=("CORE_API_KEY",),
        default_enabled=False,
        requires_credential=True,
        external_data_api_id=None,
        external_data_source=None,
        external_data_description=None,
    ),
    ApiServiceDescriptor(
        name="nlr_developer_network",
        title="NLR",
        description="Official research data",
        credential_label="API key",
        credential_kind="api_key",
        endpoint=None,
        test_url=None,
        docs_url="https://developer.nlr.gov/docs/",
        docs_url_editable=True,
        environment_variables=("NLR_API_KEY",),
        default_enabled=False,
        requires_credential=True,
        external_data_api_id="nlr_developer_network",
        external_data_source="NLR",
        external_data_description=(
            "Use the official NLR API documentation to select the endpoint and "
            "fields needed for the research question; the configured API key is "
            "available as NLR_API_KEY in this run's environment; never print the "
            "credential or copy it into an artifact."
        ),
    ),
)

_CATALOG = {service.name: service for service in PAPER_SERVICE_CATALOG}


def _descriptor(name: str) -> ApiServiceDescriptor | None:
    return _CATALOG.get(name)


def external_data_descriptor(api_id: str) -> ApiServiceDescriptor | None:
    """Return the static runtime binding for one external-data API identity."""

    return next(
        (
            service
            for service in PAPER_SERVICE_CATALOG
            if service.external_data_api_id == api_id
        ),
        None,
    )


def _profile_key(name: str) -> str:
    return f"{_PROFILE_PREFIX}{name}"


def _env_credential(
    service: ApiServiceDescriptor,
    environment: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if environment is None else environment
    for variable in service.environment_variables:
        value = str(source.get(variable, "") or "").strip()
        if value:
            return value
    return ""


def _effective_credential(
    service: ApiServiceDescriptor,
    profile: Mapping[str, Any],
    *,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, str | None]:
    stored_value = str(profile.get("credential") or "").strip()
    if stored_value:
        return stored_value, "stored"
    environment_value = _env_credential(service, environment)
    return (environment_value, "environment") if environment_value else ("", None)


def get_runtime_api_service_environment(
    secrets: SecretStore,
    *,
    inherited_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve enabled paper-service credentials for a trusted child process.

    The returned mapping contains only environment variables needed by the fixed
    paper-service adapters. Values come from the SecretStore first, then from the
    inherited environment. Semantic Scholar receives both of its historical names
    so old and new PaperOrchestra/runtime call sites share one configured credential.
    """

    inherited = (
        dict(os.environ)
        if inherited_environment is None
        else dict(inherited_environment)
    )
    resolved: dict[str, str] = {}
    for service in PAPER_SERVICE_CATALOG:
        if service.external_data_api_id is not None:
            continue
        profile = secrets.get(_profile_key(service.name)) or {}
        if not bool(profile.get("enabled", service.default_enabled)):
            continue
        credential, _ = _effective_credential(
            service,
            profile,
            environment=inherited,
        )
        if not credential:
            continue
        for variable in service.environment_variables:
            resolved[variable] = credential
    return resolved


def _credential_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validated_docs_url(service: ApiServiceDescriptor, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Enter an HTTP(S) API documentation address for {service.title}.")
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{service.title} API documentation address must be HTTP(S).")
    return normalized


def _effective_docs_url(
    service: ApiServiceDescriptor,
    profile: Mapping[str, Any],
    *,
    override: str | None = None,
) -> str | None:
    if override is not None:
        return override.strip() or None
    configured = profile.get("docs_url")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return service.docs_url


def _wait_for_test_request_slot(service: ApiServiceDescriptor, credential: str) -> None:
    """Keep this process below Semantic Scholar's one-request-per-second key limit."""

    if service.name != "semantic-scholar":
        return
    credential_id = _credential_hash(credential)
    with _semantic_scholar_rate_lock:
        now = time.monotonic()
        next_request_at = _semantic_scholar_next_request_at.get(credential_id, now)
        wait_seconds = max(0.0, next_request_at - now)
        _semantic_scholar_next_request_at[credential_id] = (
            max(now, next_request_at) + _SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS
        )
    if wait_seconds:
        time.sleep(wait_seconds)


def _send_test_request(service: ApiServiceDescriptor, credential: str) -> httpx.Response:
    if not service.test_url:
        raise ValueError(f"{service.title} does not expose a fixed test endpoint.")
    _wait_for_test_request_slot(service, credential)
    return httpx.get(
        service.test_url,
        headers=_request_headers(service, credential),
        timeout=10.0,
    )


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
        "docs_url": _effective_docs_url(service, profile),
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
    docs_url: str | None | object = _MISSING,
) -> dict[str, Any]:
    """Save one service profile without changing any other service or runtime setting."""

    service = _descriptor(name)
    if service is None:
        return {"ok": False, "error": f"unknown API service: {name}"}
    if docs_url is not _MISSING and not service.docs_url_editable:
        return {"ok": False, "error": f"{service.title} API documentation address is fixed."}
    profile = dict(secrets.get(_profile_key(name)) or {})
    profile["enabled"] = bool(enabled)
    docs_url_changed = False
    if docs_url is not _MISSING:
        value = str(docs_url or "").strip()
        if value:
            try:
                profile["docs_url"] = _validated_docs_url(service, value)
            except ValueError as error:
                return {"ok": False, "error": str(error)}
        else:
            profile.pop("docs_url", None)
        docs_url_changed = True
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
    if docs_url_changed:
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
    docs_url: str | None | object = _MISSING,
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

    if docs_url is _MISSING:
        effective_docs_url = _effective_docs_url(service, profile)
    else:
        try:
            effective_docs_url = _validated_docs_url(service, docs_url)
        except ValueError as error:
            return {"ok": False, "status": "error", "error": str(error)}
    if service.docs_url_editable and not effective_docs_url:
        return {
            "ok": False,
            "status": "not_configured",
            "error": f"Enter an API documentation address to test {service.title}.",
        }

    # NLR intentionally has no hard-coded endpoint or field mapping. A test for it
    # validates only the locally configured credential and documentation URL; the
    # Connector discovers endpoint details from the official documentation at run time.
    if service.test_url is None:
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

    error: str | None = None
    try:
        response = _send_test_request(service, value)
        # A request made outside this process can still consume the key's single slot.
        # Wait for one fresh slot and retry this read-only probe once.
        if service.name == "semantic-scholar" and response.status_code == 429:
            response = _send_test_request(service, value)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if service.name == "semantic-scholar" and status_code == 429:
            error = "Semantic Scholar rate limited this API key. Wait one second and try again."
        elif status_code in {401, 403}:
            error = f"{service.title} rejected the configured credential."
        else:
            error = f"{service.title} returned HTTP {status_code}."
    except httpx.TimeoutException:
        error = f"{service.title} timed out after 10 seconds."
    except httpx.HTTPError:
        error = f"{service.title} could not be reached."

    if error is not None:
        checked_at = _checked_at()
        profile.update(
            {
                "last_test_at": checked_at,
                "last_test_ok": False,
                "last_test_error": error,
                "last_test_credential_hash": _credential_hash(value),
            }
        )
        secrets.put(_profile_key(name), profile)
        return {
            "ok": False,
            "status": "error",
            "checked_at": checked_at,
            "error": error,
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


def get_external_data_registry(secrets: SecretStore) -> list[dict[str, Any]]:
    """Build the non-sensitive Connector catalog from enabled API service profiles."""

    registry: list[dict[str, Any]] = []
    for service in PAPER_SERVICE_CATALOG:
        if service.external_data_api_id is None:
            continue
        profile = secrets.get(_profile_key(service.name)) or {}
        if not bool(profile.get("enabled", service.default_enabled)):
            continue
        docs_url = _effective_docs_url(service, profile)
        registry.append(
            {
                "api_id": service.external_data_api_id,
                "source": service.external_data_source or service.title,
                "description": service.external_data_description or service.description,
                "official_docs_url": docs_url,
            }
        )
    return registry


def get_external_data_snapshot(secrets: SecretStore) -> dict[str, Any]:
    """Return launch-safe API metadata plus the current non-sensitive status map."""

    statuses: dict[str, str] = {}
    for service in PAPER_SERVICE_CATALOG:
        if service.external_data_api_id is None:
            continue
        public = _public_service(service, secrets.get(_profile_key(service.name)) or {})
        statuses[service.external_data_api_id] = str(public["status"])
    return {
        "api_registry": get_external_data_registry(secrets),
        "provider_status": statuses,
    }
