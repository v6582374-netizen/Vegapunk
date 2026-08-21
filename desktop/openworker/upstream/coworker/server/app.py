"""FastAPI app — OpenAI-compatible endpoint + WS session API + REST.

The control plane every surface (GUI/IDE/messaging) rides on. The WS carries the engine
event stream and the approval channel; `/v1/chat/completions` is the OpenAI-compatible
proxy so any OpenAI-format client can use the runtime as a backend.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Origins allowed to talk to the local sidecar. It binds to 127.0.0.1, but a page in the
# user's own browser can still reach loopback — so without an origin gate, any website they
# visit could read `GET /v1/sessions` (CORS was `*`) and drive a session over the WS (which
# CORS never covers) into shell/file tools. We pin to the desktop webview's own origins
# (`tauri://localhost`, Windows' `http(s)://tauri.localhost`) and localhost dev/browser
# builds. Requests with NO Origin header (curl, native clients, tests, server-to-server) are
# allowed — the gate targets browsers, which always attach an unforgeable Origin.
_ALLOWED_ORIGIN_RE = re.compile(
    r"^(tauri://localhost"
    r"|https?://localhost(:\d+)?"
    r"|https?://127\.0\.0\.1(:\d+)?"
    r"|https?://tauri\.localhost)$"
)


def _origin_allowed(origin: str | None, *, host: str | None = None, web_enabled: bool = False) -> bool:
    """True if a browser Origin may use the API.

    The desktop sidecar is intentionally limited to Tauri/loopback origins. A server-hosted
    Web Counterpart also needs to accept its own same-origin browser origin, while still
    rejecting a page on an unrelated host from opening the driving WebSocket.
    """
    if origin is None or bool(_ALLOWED_ORIGIN_RE.match(origin)):
        return True
    if not web_enabled or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


# Caps on inbound WebSocket traffic. The loopback socket is unauthenticated (any local
# process can reach it), so bound frames, messages, and per-connection request rate before
# building model content or starting a turn.
_WS_MAX_FRAME_BYTES = 16 * 1024 * 1024
_WS_RATE_LIMIT_COUNT = 30
_WS_RATE_LIMIT_WINDOW_SECONDS = 10.0
_MAX_MESSAGE_TEXT_CHARS = 200_000
_MAX_ATTACHMENTS_BYTES = 15_000_000  # leaves JSON overhead below the 16 MiB frame cap
_WEB_SESSION_COOKIE = "openworker_web_session"
_WEB_SESSION_MAX_AGE = 60 * 60 * 24 * 30


def _json_value_size(value: Any) -> int:
    """Conservative UTF-8 size of parsed JSON without allocating another giant string."""
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, dict):
        return sum(_json_value_size(k) + _json_value_size(v) for k, v in value.items())
    if isinstance(value, list):
        return sum(_json_value_size(v) for v in value)
    return 8  # numbers, booleans, null, separators


def _web_login_page() -> str:
    """Small same-origin gate shown before the full desktop GUI is loaded.

    This is deliberately a capability boundary, not a second product surface. Once the
    shared Web token is accepted the exact desktop bundle is served unchanged.
    """
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vegapunk Web</title><style>
:root{color-scheme:light;--paper:#f6f5f2;--panel:#fff;--line:#e4e2dc;--ink:#2c2c2a;--muted:#6f6e68;--accent:#3670b2;--bad:#b3423a}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--paper:#191918;--panel:#232322;--line:#373633;--ink:#e8e6e1;--muted:#9d9b94;--accent:#6ba3dd;--bad:#d97b74}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--paper);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px}
.card{width:min(360px,100%);padding:34px 32px 30px;background:var(--panel);border:1px solid var(--line);border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.06)}
.mark{display:flex;align-items:center;gap:8px;font-weight:650;margin-bottom:28px}.mark i{width:20px;height:20px;border-radius:6px;background:var(--accent);display:inline-block;position:relative}.mark i:after{content:"";position:absolute;inset:5px;border-radius:2px;background:conic-gradient(from 0deg,#fff 0 25%,transparent 0 50%,#fff 0 75%,transparent 0)}
h1{font-size:19px;letter-spacing:-.02em;margin:0 0 7px}p{color:var(--muted);font-size:12.5px;margin:0 0 22px}label{display:block;color:var(--muted);font-size:11px;margin-bottom:6px}input{display:block;width:100%;border:1px solid var(--line);border-radius:9px;background:var(--paper);color:var(--ink);padding:10px 11px;font:inherit;outline:none}input:focus{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 18%,transparent)}button{display:block;width:100%;margin-top:14px;border:0;border-radius:9px;background:var(--accent);color:#fff;padding:10px 12px;font:600 13px inherit;cursor:pointer}button:disabled{opacity:.6;cursor:wait}.error{min-height:18px;margin-top:12px;color:var(--bad);font-size:12px}
</style></head><body><main class="card"><div class="mark"><i></i>Vegapunk</div><h1>Sign in to Vegapunk</h1><p>This Linux Web Counterpart shares the desktop workspace and keeps the server behind a local access token.</p><form id="login"><label for="token">Access token</label><input id="token" name="token" type="password" autocomplete="current-password" autofocus><button id="submit" type="submit">Continue</button><div class="error" id="error" role="alert"></div></form></main><script>
const form=document.getElementById("login"),input=document.getElementById("token"),button=document.getElementById("submit"),error=document.getElementById("error");
form.addEventListener("submit",async(e)=>{e.preventDefault();error.textContent="";button.disabled=true;try{const r=await fetch("/web/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:input.value})});if(!r.ok)throw new Error("Invalid access token");location.replace("/")}catch(err){error.textContent=err instanceof Error?err.message:"Could not sign in";button.disabled=false;input.select()}});
</script></body></html>"""


# Brand colors for the connector badge riding the ✓ (UX-DECISIONS §30). The GUI owns the
# real logos; this page must render offline with zero assets, so a colored initial stands in.
_BRAND_COLORS = {
    "slack": "#4A154B",
    "github": "#24292f",
    "hubspot": "#ff7a59",
    "gmail": "#ea4335",
    "google_calendar": "#4285f4",
}


def _browser_page(
    title: str, detail: str, *, ok: bool = True, error: str = "", connector: str = ""
) -> str:
    """The page shown in the user's browser at the end of a loopback flow (sign-in or
    connector callback) — one branded card (UX-DECISIONS §30): OCW mark, ok/fail icon
    (the connector's initial rides the ✓), the friendly detail, and the raw error
    preserved on failures (it's the debugging breadcrumb). Inline CSS, light/dark via
    prefers-color-scheme, no external assets — it must render offline."""
    import html as _html

    badge = ""
    if ok and connector:
        color = _BRAND_COLORS.get(connector, "#3670b2")
        initial = _html.escape((connector[:1] or "?").upper())
        badge = f'<span class="mini" style="background:{color}">{initial}</span>'
    icon = (
        f'<div class="ico ok">✓{badge}</div>' if ok else '<div class="ico bad">✕</div>'
    )
    err = f'<div class="err">{_html.escape(error)}</div>' if error else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_html.escape(title)} — Vegapunk</title><style>"
        ":root{--paper:#f6f5f2;--panel:#fff;--line:#e4e2dc;--ink:#2c2c2a;--muted:#6f6e68;"
        "--faint:#a3a19a;--accent:#3670b2;--ok:#2e7d4f;--ok-soft:#e3f2e9;--bad:#b3423a;"
        "--bad-soft:#f8e7e5}"
        "@media(prefers-color-scheme:dark){:root{--paper:#191918;--panel:#232322;"
        "--line:#373633;--ink:#e8e6e1;--muted:#9d9b94;--faint:#6b6a64;--accent:#6ba3dd;"
        "--ok:#5cb884;--ok-soft:#20362a;--bad:#d97b74;--bad-soft:#3a2422}}"
        "body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;"
        "justify-content:center;gap:18px;background:var(--paper);color:var(--ink);"
        'font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px}'
        ".card{background:var(--panel);border:1px solid var(--line);border-radius:16px;"
        "padding:34px 32px 28px;max-width:320px;width:100%;text-align:center;"
        "box-shadow:0 10px 30px rgba(0,0,0,.06);box-sizing:border-box}"
        ".mark{display:flex;align-items:center;justify-content:center;gap:7px;margin-bottom:22px;"
        "font-size:13px;font-weight:650}"
        ".mark i{width:20px;height:20px;border-radius:6px;background:var(--accent);"
        "display:inline-block;position:relative}"
        ".mark i::after{content:'';position:absolute;inset:5px;border-radius:2px;"
        "background:conic-gradient(from 0deg,#fff 0 25%,transparent 0 50%,#fff 0 75%,transparent 0)}"
        ".ico{width:52px;height:52px;border-radius:50%;margin:0 auto 14px;display:flex;"
        "align-items:center;justify-content:center;font-size:24px;position:relative}"
        ".ico.ok{background:var(--ok-soft);color:var(--ok)}"
        ".ico.bad{background:var(--bad-soft);color:var(--bad)}"
        ".mini{position:absolute;right:-3px;bottom:-3px;width:22px;height:22px;border-radius:7px;"
        "display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;"
        "font-weight:700;border:2px solid var(--panel)}"
        "h1{font-size:17px;font-weight:650;margin:0 0 6px;letter-spacing:-.01em}"
        "p{font-size:12.5px;color:var(--muted);margin:0}"
        ".err{font-size:11.5px;color:var(--bad);background:var(--bad-soft);border-radius:8px;"
        "padding:7px 10px;margin-top:12px;text-align:left;word-break:break-word}"
        ".foot{font-size:10.5px;color:var(--faint)}"
        "</style></head><body>"
        '<div class="card"><div class="mark"><i></i>Vegapunk</div>'
        f"{icon}<h1>{_html.escape(title)}</h1><p>{_html.escape(detail)}</p>{err}</div>"
        '<div class="foot">Served locally by Vegapunk on your Mac</div>'
        "</body></html>"
    )


def _connector_title(name: str) -> str:
    """Display name for the loopback page — 'Slack connected', never 'slack connected'."""
    from ..connectors.descriptors import get_descriptor

    d = get_descriptor(name)
    return d.title if d else (name[:1].upper() + name[1:])


_CONNECT_FAILED_DETAIL = (
    "Something went wrong finishing this connection. "
    "Close this tab and try again from Vegapunk."
)

from ..attachments import (
    MAX_ATTACHMENTS as _MAX_ATTACHMENTS,
)
from ..attachments import (
    MAX_IMAGE_CHARS,
    MAX_PDF_CHARS,
    MAX_TEXT_CHARS,
    build_user_content,
)
from ..engine import ApprovalOutcome
from ..inbox import VIS_INBOX, VIS_INLINE, args_preview
from ..permissions import Mode
from ..providers import AssistantTurn
from ..youtube.client import YouTubeAuthError
from .discovery import (
    DiscoveryConfigurationError,
    DiscoveryConversionError,
    DiscoveryFacade,
    DiscoverySourceContentError,
    LaunchValidationError,
    PreparationValidationError,
)
from .discovery_artifacts import DiscoveryArtifactPathError
from .discovery_preferences import DiscoveryPreferencesValidationError
from .discovery_launch import (
    ActiveLaunchConflict,
    IdempotencyConflict,
    LaunchStateConflict,
)
from .manager import SessionManager
from .prompt_library import (
    DesktopPromptLibrary,
    InvalidPromptError,
    PromptLibrary,
    PromptLibraryUnavailableError,
    UnknownPromptError,
    default_prompt_roots,
    violation_for,
)
from .embodied import (
    ActiveRunConflict,
    CameraRelayError,
    EmbodiedFacade,
    EmbodiedValidationError,
    SimulatorUnavailableError,
    relay_camera_offer,
)
from .skills_manager import SkillsManagerError, SkillsManagerService
from .translation import (
    TranslationArtifactError,
    TranslationFacade,
    TranslationValidationError,
)


def create_app(
    manager: SessionManager,
    *,
    prompt_library_root: str | Path | None = None,
    prompt_baseline_root: str | Path | None = None,
    discovery_conversion_prompt_path: str | Path | None = None,
    discovery_runner_mode: str | None = None,
    discovery_repository_root: str | Path | None = None,
    web_dist: str | Path | None = None,
    web_enabled: bool | None = None,
) -> FastAPI:
    web_requested = bool(web_enabled or web_dist)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            live = (
                await manager.start_gateway()
            )  # start messaging listeners (if configured)
            if live:
                print(f"[coworker] messaging gateway live: {', '.join(live)}")
        except Exception:  # never let a bad connector stop the server
            import traceback

            traceback.print_exc()
        yield
        await manager.aclose()  # stop gateway + close MCP connections on shutdown

    app = FastAPI(title="coworker", version="0.0.0", lifespan=lifespan)
    # Skills Manager is a production Tauri surface.  The Web Counterpart keeps the same
    # command names and persists against the user's shared ~/.skills-manager directory.
    app.state.skills_manager = SkillsManagerService(
        workspace_root=getattr(manager, "default_workspace", None)
    )
    api_token = os.environ.get("COWORKER_API_TOKEN", "")
    web_token = os.environ.get("COWORKER_WEB_TOKEN", "")
    web_root = Path(web_dist).expanduser().resolve() if web_dist else None
    web_index = web_root / "index.html" if web_root else None
    web_enabled = bool(web_enabled if web_enabled is not None else web_root) and bool(
        web_index and web_index.is_file()
    )
    # A dedicated Web token is preferred. Falling back to the existing API token keeps
    # explicitly configured deployments compatible with the desktop launch contract.
    web_auth_token = web_token or api_token
    tokenless_paths = {
        "/v1/health",
        "/v1/youtube/oauth/callback",
        "/mcp/oauth/callback",
        "/web/auth",
        "/web/login",
        "/web/logout",
    }

    def _token_matches(candidate: str) -> bool:
        return bool(
            candidate
            and (
                (api_token and secrets.compare_digest(candidate, api_token))
                or (web_auth_token and secrets.compare_digest(candidate, web_auth_token))
            )
        )

    def _request_authenticated(request: Request) -> bool:
        provided = request.headers.get("x-openworker-token", "")
        cookie = request.cookies.get(_WEB_SESSION_COOKIE, "")
        return _token_matches(provided) or (web_enabled and _token_matches(cookie))

    def _websocket_authenticated(ws: WebSocket) -> bool:
        if not api_token and not web_auth_token:
            return True
        protocols = {
            part.strip()
            for part in ws.headers.get("sec-websocket-protocol", "").split(",")
            if part.strip()
        }
        return any(_token_matches(part) for part in protocols) or (
            web_enabled and _token_matches(ws.cookies.get(_WEB_SESSION_COOKIE, ""))
        )

    def _websocket_subprotocol(ws: WebSocket) -> str | None:
        # Browsers reject a server-selected subprotocol that was not offered by the client.
        # Desktop clients offer `openworker`; same-origin Web sessions authenticate by cookie
        # and intentionally offer no subprotocol.
        offered = {
            part.strip()
            for part in ws.headers.get("sec-websocket-protocol", "").split(",")
            if part.strip()
        }
        return "openworker" if api_token and "openworker" in offered else None

    def _is_public_web_path(path: str) -> bool:
        if not web_enabled:
            return False
        if path.startswith(("/v1", "/ws", "/auth", "/oauth", "/mcp")):
            return False
        # Every other path is a browser route or a static asset. It is safe to let the SPA
        # render its login gate before the API/WS session is authenticated.
        return True

    @app.middleware("http")
    async def require_sidecar_token(request: Request, call_next):
        # Preflights carry the requested header name, not its value. CORS checks the
        # Origin; the actual state-changing request still must authenticate.
        if (
            (not api_token and not web_auth_token)
            or request.method == "OPTIONS"
            or request.url.path in tokenless_paths
            or _is_public_web_path(request.url.path)
            or _request_authenticated(request)
        ):
            return await call_next(request)
        return JSONResponse(
            {"error": "missing or invalid Vegapunk sidecar token"},
            status_code=401,
        )

    app.add_middleware(
        CORSMiddleware,
        # Pinned to the desktop webview + localhost (see _ALLOWED_ORIGIN_RE): stops a random
        # website the user visits from reading local API responses cross-origin.
        allow_origin_regex=_ALLOWED_ORIGIN_RE.pattern,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.manager = manager
    youtube_oauth_states: dict[str, tuple[float, str]] = {}
    default_library_root, default_baseline_root = default_prompt_roots()
    app.state.prompt_library = DesktopPromptLibrary(
        PromptLibrary(
            Path(prompt_library_root) if prompt_library_root else default_library_root
        ),
        Path(prompt_baseline_root) if prompt_baseline_root else default_baseline_root,
    )
    app.state.discovery = DiscoveryFacade(
        manager._data_base,
        conversion_prompt_path=discovery_conversion_prompt_path,
        runner_mode=discovery_runner_mode or ("real" if web_requested else "fake"),
        repository_root=discovery_repository_root,
    )
    app.state.translation = TranslationFacade(manager._data_base)
    app.state.embodied = EmbodiedFacade(manager._data_base)

    if web_enabled and web_root is not None:
        assets_root = web_root / "assets"
        if assets_root.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_root), name="web-assets")

    def _web_index_response(request: Request) -> Response:
        """Serve the built desktop bundle with a tiny runtime marker for same-origin API use."""
        assert web_index is not None
        html = web_index.read_text(encoding="utf-8")
        marker = '<script>globalThis.__OPENWORKER_WEB__=true;</script>'
        if marker not in html:
            html = html.replace("<head>", f"<head>{marker}", 1)
        response = HTMLResponse(html)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/web/auth")
    def web_auth(request: Request) -> dict[str, Any]:
        return {
            "enabled": bool(web_enabled and web_auth_token),
            "authenticated": _request_authenticated(request),
        }

    @app.post("/web/login")
    async def web_login(request: Request) -> Response:
        if not web_enabled or not web_auth_token:
            return JSONResponse({"ok": True, "authenticated": True})
        body: Any = {}
        content_type = request.headers.get("content-type", "")
        try:
            if "application/json" in content_type:
                body = await request.json()
            else:
                raw = (await request.body()).decode("utf-8", errors="replace")
                body = {key: values[-1] for key, values in parse_qs(raw).items() if values}
        except Exception:
            body = {}
        candidate = body.get("token", "") if isinstance(body, dict) else ""
        if not isinstance(candidate, str) or not _token_matches(candidate):
            return JSONResponse({"ok": False, "error": "invalid access token"}, status_code=401)
        response = JSONResponse({"ok": True, "authenticated": True})
        response.set_cookie(
            _WEB_SESSION_COOKIE,
            web_auth_token,
            max_age=_WEB_SESSION_MAX_AGE,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            path="/",
        )
        return response

    @app.post("/web/logout")
    def web_logout() -> Response:
        response = JSONResponse({"ok": True})
        response.delete_cookie(_WEB_SESSION_COOKIE, path="/")
        return response

    @app.get("/v1/health")
    def health(request: Request) -> dict[str, Any]:
        if (api_token or web_auth_token) and not _request_authenticated(request):
            return {"status": "ok"}
        return {
            "status": "ok",
            "default_workspace": manager.default_workspace,
            "model": manager.model,
        }

    @app.get("/v1/discovery")
    def discovery() -> dict[str, Any]:
        """Return the Native Desktop Discovery shell from this sidecar."""
        return app.state.discovery.snapshot()

    @app.get("/v1/discovery/input-conversion-prompt")
    def discovery_input_conversion_prompt() -> dict[str, Any]:
        try:
            return app.state.discovery.get_conversion_prompt()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.put("/v1/discovery/input-conversion-prompt")
    def save_discovery_input_conversion_prompt(body: dict | None = None) -> dict[str, Any]:
        instruction = (body or {}).get("instruction") if isinstance(body, dict) else None
        if not isinstance(instruction, str):
            raise HTTPException(status_code=422, detail="instruction must be a string")
        try:
            return app.state.discovery.save_conversion_prompt(instruction)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery Input Conversion Prompt could not be saved.",
            ) from exc

    def _prompt_error(
        code: str,
        message: str,
        status_code: int,
        violations: list[dict] | None = None,
    ) -> JSONResponse:
        error: dict[str, Any] = {"code": code, "message": message}
        if violations:
            error["violations"] = violations
        return JSONResponse({"error": error}, status_code=status_code)

    @app.get("/v1/prompt-library/health")
    def prompt_library_health() -> dict[str, str]:
        return app.state.prompt_library.health()

    @app.get("/v1/prompt-library/prompts", response_model=None)
    def prompt_library_list() -> dict | JSONResponse:
        try:
            return {"prompts": app.state.prompt_library.list_catalogue()}
        except PromptLibraryUnavailableError as exc:
            return _prompt_error("library_unavailable", str(exc), 503)
        except Exception:
            return _prompt_error("internal_error", "Prompt Library request failed", 500)

    @app.get("/v1/prompt-library/prompts/{prompt_id:path}", response_model=None)
    def prompt_library_detail(prompt_id: str) -> dict | JSONResponse:
        try:
            return {"prompt": app.state.prompt_library.detail(prompt_id)}
        except UnknownPromptError:
            return _prompt_error("prompt_not_found", "unknown Prompt", 404)
        except PromptLibraryUnavailableError as exc:
            return _prompt_error("library_unavailable", str(exc), 503)
        except Exception:
            return _prompt_error("internal_error", "Prompt Library request failed", 500)

    @app.put("/v1/prompt-library/prompts/{prompt_id:path}", response_model=None)
    def prompt_library_save(prompt_id: str, body: dict | None = None) -> dict | JSONResponse:
        text = (body or {}).get("text") if isinstance(body, dict) else None
        if not isinstance(text, str):
            return _prompt_error("invalid_request", "text must be a string", 422)
        try:
            return {"prompt": app.state.prompt_library.save(prompt_id, text)}
        except UnknownPromptError:
            return _prompt_error("prompt_not_found", "unknown Prompt", 404)
        except InvalidPromptError as exc:
            violation = violation_for(exc).to_dict()
            return _prompt_error("invalid_prompt", str(exc), 422, [violation])
        except PromptLibraryUnavailableError as exc:
            return _prompt_error("library_unavailable", str(exc), 503)
        except Exception:
            return _prompt_error("internal_error", "Prompt Library request failed", 500)

    @app.post("/v1/discovery/preparation/intake")
    def discovery_preparation_intake(body: dict) -> dict[str, Any]:
        try:
            return app.state.discovery.intake(body or {})
        except PreparationValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/v1/discovery/preparation/sources/{source_id}")
    def discovery_preparation_delete_source(source_id: str) -> dict[str, Any]:
        try:
            return app.state.discovery.delete_source(source_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="source entry not found") from exc

    @app.post("/v1/discovery/preparation/save")
    def discovery_preparation_save(body: dict | None = None) -> dict[str, Any]:
        try:
            return app.state.discovery.save(body or {})
        except PreparationValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery Preparation could not be saved. Try again.",
            ) from exc

    @app.post("/v1/discovery/preparation/reset")
    def discovery_preparation_reset() -> dict[str, Any]:
        try:
            return app.state.discovery.reset()
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery Preparation could not be reset. Try again.",
            ) from exc

    @app.post("/v1/discovery/preparation/convert")
    def discovery_preparation_convert(body: dict | None = None) -> dict[str, Any]:
        del body
        try:
            return app.state.discovery.convert(
                manager.provider,
                manager.model,
                manager.discovery_model_settings(),
            )
        except PreparationValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DiscoverySourceContentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except DiscoveryConfigurationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DiscoveryConversionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/discovery/preparation/revisions")
    def discovery_preparation_save_revision(body: dict | None = None) -> dict[str, Any]:
        try:
            return app.state.discovery.save_revision(body or {})
        except PreparationValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery Execution Input revision could not be saved. Try again.",
            ) from exc

    @app.post("/v1/discovery/launches", status_code=201)
    def discovery_launch_start(
        request: Request, body: dict | None = None
    ) -> dict[str, Any]:
        try:
            return app.state.discovery.start_launch(
                body or {},
                idempotency_key=request.headers.get("idempotency-key", "").strip(),
                model_id=manager.model,
                settings=manager.discovery_model_settings(),
                discovery_preferences=manager.discovery_launch_preferences_snapshot(),
                external_data=manager.external_data_snapshot(),
            )
        except LaunchValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (ActiveLaunchConflict, IdempotencyConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery source content could not be prepared. Try again.",
            ) from exc

    @app.get("/v1/discovery/launches")
    def discovery_launch_list() -> dict[str, Any]:
        return app.state.discovery.list_launches()

    @app.get("/v1/discovery/launches/{launch_id}")
    def discovery_launch_get(launch_id: str) -> dict[str, Any]:
        try:
            return app.state.discovery.launch(launch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc

    @app.get("/v1/discovery/launches/{launch_id}/status")
    def discovery_launch_status(launch_id: str) -> dict[str, Any]:
        try:
            return app.state.discovery.status(launch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc

    @app.get("/v1/discovery/launches/{launch_id}/events")
    def discovery_launch_events(launch_id: str, after: int = 0) -> dict[str, Any]:
        try:
            return app.state.discovery.events(launch_id, after=max(after, 0))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc

    @app.get("/v1/discovery/launches/{launch_id}/logs/stream")
    def discovery_launch_log_stream(launch_id: str) -> StreamingResponse:
        try:
            app.state.discovery.launch(launch_id)
            stream = app.state.discovery.stream_log(launch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/discovery/launches/{launch_id}/artifacts")
    def discovery_launch_artifacts(launch_id: str) -> dict[str, Any]:
        try:
            return app.state.discovery.artifacts(launch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc

    @app.get("/v1/discovery/launches/{launch_id}/artifacts/read")
    def discovery_launch_artifact_read(launch_id: str, path: str) -> dict[str, Any]:
        try:
            return app.state.discovery.read_artifact(launch_id, path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc
        except DiscoveryArtifactPathError as exc:
            raise HTTPException(status_code=404, detail="Discovery artifact is not available") from exc

    @app.post("/v1/discovery/launches/{launch_id}/artifacts/reveal")
    def discovery_launch_artifact_reveal(
        launch_id: str, body: dict | None = None
    ) -> dict[str, Any]:
        body = body or {}
        path = body.get("path")
        mode = body.get("mode", "reveal")
        if not isinstance(path, str) or not isinstance(mode, str):
            raise HTTPException(status_code=422, detail="Discovery artifact path and mode are required")
        try:
            return app.state.discovery.reveal_artifact(launch_id, path, mode)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc
        except DiscoveryArtifactPathError as exc:
            raise HTTPException(status_code=404, detail="Discovery artifact is not available") from exc

    @app.post("/v1/discovery/launches/{launch_id}/stop")
    def discovery_launch_stop(launch_id: str) -> dict[str, Any]:
        try:
            return app.state.discovery.stop_launch(launch_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc
        except LaunchStateConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/discovery/launches/{launch_id}/resume", status_code=201)
    def discovery_launch_resume(
        request: Request, launch_id: str
    ) -> dict[str, Any]:
        try:
            return app.state.discovery.resume_launch(
                launch_id,
                idempotency_key=request.headers.get("idempotency-key", "").strip(),
            )
        except LaunchValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Discovery Launch not found") from exc
        except (ActiveLaunchConflict, IdempotencyConflict, LaunchStateConflict) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/translation/settings")
    def translation_settings() -> dict[str, Any]:
        return app.state.translation.settings_document()

    @app.put("/v1/translation/settings")
    @app.post("/v1/translation/settings")
    def save_translation_settings(body: dict | None = None) -> dict[str, Any]:
        try:
            return app.state.translation.save_settings(body or {})
        except TranslationValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Translation settings could not be saved. Try again.",
            ) from exc

    @app.post("/v1/translation/documents")
    def translation_register_documents(body: dict | None = None) -> dict[str, Any]:
        try:
            return app.state.translation.register_documents(body or {})
        except TranslationValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Translation document could not be stored. Try again.",
            ) from exc

    @app.get("/v1/translation/documents")
    def translation_documents() -> dict[str, Any]:
        return app.state.translation.list_documents()

    @app.delete("/v1/translation/documents/{document_id}")
    def translation_forget_document(document_id: str) -> dict[str, Any]:
        try:
            return app.state.translation.forget_document(document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation document not found") from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Translation document could not be removed. Try again.",
            ) from exc

    @app.post("/v1/translation/runs")
    def translation_start_runs(body: dict | None = None) -> dict[str, Any]:
        try:
            return app.state.translation.start_runs(body or {})
        except TranslationValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Translation run could not be started. Try again.",
            ) from exc

    @app.get("/v1/translation/runs")
    def translation_runs() -> dict[str, Any]:
        return app.state.translation.list_runs()

    @app.get("/v1/translation/runs/{run_id}")
    def translation_run(run_id: str) -> dict[str, Any]:
        try:
            return app.state.translation.run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc

    @app.get("/v1/translation/runs/{run_id}/events")
    def translation_run_events(run_id: str, after: int = 0) -> dict[str, Any]:
        try:
            return app.state.translation.events(run_id, after=max(after, 0))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc

    @app.post("/v1/translation/runs/{run_id}/cancel")
    def translation_cancel_run(run_id: str) -> dict[str, Any]:
        try:
            return app.state.translation.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc

    @app.get("/v1/translation/runs/{run_id}/logs/stream")
    def translation_run_log_stream(run_id: str) -> StreamingResponse:
        try:
            stream = app.state.translation.stream_log(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/v1/translation/runs/{run_id}/artifacts/{name}")
    def translation_run_artifact(run_id: str, name: str) -> FileResponse:
        try:
            path = app.state.translation.artifact_path(run_id, name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc
        except TranslationArtifactError as exc:
            raise HTTPException(
                status_code=404, detail="translation artifact is not available"
            ) from exc
        media_type = "application/pdf" if path.suffix.lower() == ".pdf" else None
        return FileResponse(path, media_type=media_type, filename=path.name)

    @app.post("/v1/translation/runs/{run_id}/reveal")
    def translation_run_reveal(run_id: str, body: dict | None = None) -> dict[str, Any]:
        """Show the run's own bundle folder. The path is never taken from the body."""
        try:
            return app.state.translation.reveal_bundle(
                run_id, str((body or {}).get("mode") or "reveal")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="translation run not found") from exc

    @app.get("/v1/embodied/environment")
    def embodied_environment() -> dict[str, Any]:
        """Describe the bench without building one.

        Constructing a ``SimulatedG1`` compiles the MJCF model and binds a GL
        context, so the declaration is answered from the plan's own constants and
        the joint list, and simulator availability is probed rather than proven by
        a run.
        """
        return app.state.embodied.environment()

    @app.post("/v1/embodied/runs", status_code=201)
    def embodied_start_run(body: dict | None = None) -> dict[str, Any]:
        try:
            return {"run": app.state.embodied.start_run(body or {})}
        except EmbodiedValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        except SimulatorUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ActiveRunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="The embodied run could not be started. Try again.",
            ) from exc

    @app.get("/v1/embodied/runs")
    def embodied_runs() -> dict[str, Any]:
        return app.state.embodied.list_runs()

    @app.get("/v1/embodied/runs/{run_id}")
    def embodied_run(run_id: str) -> dict[str, Any]:
        try:
            return app.state.embodied.run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="embodied run not found") from exc

    @app.get("/v1/embodied/runs/{run_id}/events")
    def embodied_run_events(run_id: str, after: int = 0) -> dict[str, Any]:
        try:
            return app.state.embodied.events(run_id, after=max(after, 0))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="embodied run not found") from exc

    @app.post("/v1/embodied/runs/{run_id}/cancel")
    def embodied_cancel_run(run_id: str) -> dict[str, Any]:
        try:
            return app.state.embodied.cancel(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="embodied run not found") from exc

    @app.post("/v1/embodied/cameras/{slot_id}/offer")
    async def embodied_camera_offer(slot_id: str, body: dict | None = None) -> dict[str, Any]:
        """Exchange one WebRTC offer with a robot camera on the browser's behalf.

        The robot's image service presents a self-signed certificate with no
        subjectAltName. No browser can be taught to trust such a certificate, so a
        page can never complete this exchange itself, however many warnings the
        operator clicks through. The sidecar performs it server-to-server and
        returns only the answer; the media still flows browser-to-robot over the
        DTLS connection whose fingerprint this signalling carries.
        """
        payload = body or {}
        try:
            return await asyncio.to_thread(
                relay_camera_offer, payload.get("host"), slot_id, payload.get("offer")
            )
        except CameraRelayError as exc:
            raise HTTPException(status_code=exc.status, detail=str(exc)) from exc

    @app.get("/v1/agents")
    def agents() -> dict[str, Any]:
        return {"agents": manager.list_agents()}

    @app.get("/v1/personas")
    def personas() -> dict[str, Any]:
        return {"personas": manager.personas.list_all()}

    @app.get("/v1/inbox")
    def inbox(session_id: str = "", state: str = "") -> dict[str, Any]:
        from dataclasses import asdict

        # The cross-session Inbox list shows only Unattended (inbox-visibility) items; a per-session
        # query returns inline ones too, so the answer-in-context card sees parked attended prompts.
        items = manager.inbox.list(
            session_id=session_id or None,
            state=state or None,
            visibility=None if session_id else VIS_INBOX,
        )
        # Enrich with the originating session's context so the Inbox is self-contained — the
        # "go to session" chip needs title/agent/workspace without depending on a (possibly stale)
        # client-side session list, and can link straight to it.
        out: list[dict[str, Any]] = []
        for i in items:
            d = asdict(i)
            rec = manager.session_store.load(i.session_id)
            if (
                rec is None
                and not session_id
                and i.state == "pending"
                and i.session_id not in manager._engines
            ):
                # Lazy cleanup for legacy orphans (sessions deleted before delete_session
                # started closing their items): an orphaned prompt can never be answered.
                # A LIVE engine without a record yet (brand-new session, first turn still
                # running) is NOT an orphan — hence the engine guard.
                manager.inbox.resolve_session(i.session_id)
                continue
            d["session_title"] = (rec.title if rec else None) or i.session_id
            d["session_agent"] = rec.agent if rec else None
            d["session_workspace"] = rec.workspace if rec else None
            d["session_exists"] = rec is not None
            out.append(d)
        return {"items": out}

    @app.post("/v1/inbox/{item_id}/resolve")
    async def resolve_inbox_item(item_id: str, body: dict) -> dict[str, Any]:
        # Idempotent + first-responder-wins: ok=False means it was already resolved elsewhere.
        # Routes through resolve_inbox so a restart-orphaned prompt durably resumes its turn.
        ok = await manager.resolve_inbox(item_id, str(body.get("resolution", "deny")))
        return {"ok": ok}

    @app.get("/v1/subscriptions")
    def subscriptions() -> dict[str, Any]:
        # Global view-only list: each (session → channel) subscription, enriched with the session's
        # title/agent and the channel its Inbox routes OUT to (so an inbound/outbound collision on
        # the same channel is visible).
        out: list[dict[str, Any]] = []
        for sub in manager.subscriptions.all():
            rec = manager.session_store.load(sub.session_id)
            agent = rec.agent if rec else ""
            routing = manager._routing_targets(sub.session_id, agent or "cowork")
            out.append(
                {
                    "session_id": sub.session_id,
                    "session_title": (rec.title if rec else None) or sub.session_id,
                    "agent": agent,
                    "channel": sub.channel,
                    # Display name from the channel buffer ("#ocw-test"), when any inbound
                    # message has carried one — the address stays the identifier.
                    "channel_name": manager.channel_buffer.name_for(sub.channel),
                    "routing_target": routing[0] if routing else None,
                    "collision": bool(routing and sub.channel in routing),
                }
            )
        return {"subscriptions": out}

    @app.get("/v1/channels/recent")
    def recent_channels() -> dict[str, Any]:
        # The picker's "recently-seen" source: channels the bot has received messages from.
        return {"channels": manager.channel_buffer.channels()}

    @app.get("/v1/unrouted")
    def unrouted() -> dict[str, Any]:
        # Dead-letter view: inbound messages with no destination + background-turn failures.
        return {"items": manager.unrouted.list()}

    @app.post("/v1/subscriptions")
    def subscribe(body: dict) -> dict[str, Any]:
        from ..subscriptions import resolve_channel

        session_id = str(body.get("session_id", "")).strip()
        raw = str(body.get("channel", ""))
        addr = resolve_channel(raw)
        if not session_id or not addr or ":" not in addr:
            if raw.strip().startswith("#"):
                # A bare #name can't be looked up locally — storing it literally would create a
                # subscription that never matches real traffic (resolve_channel returns "").
                return {
                    "ok": False,
                    "error": "Channel names can't be looked up — paste the channel ID "
                    "(channel name ▸ About) or the channel's Copy-link URL.",
                }
            return {"ok": False, "error": "need a session_id and a channel"}
        manager.subscriptions.subscribe(session_id, addr)
        return {"ok": True, "channel": addr}

    @app.post("/v1/subscriptions/remove")
    def unsubscribe(body: dict) -> dict[str, Any]:
        from ..subscriptions import resolve_channel

        session_id = str(body.get("session_id", "")).strip()
        addr = resolve_channel(str(body.get("channel", "")))
        removed = manager.subscriptions.unsubscribe(session_id, addr)
        return {"ok": True, "removed": removed}

    @app.get("/v1/inbox/reconcile")
    def reconcile_inbox(session_id: str) -> dict[str, Any]:
        # Called when a session resumes attended control (surface pending + recap inline).
        return manager.inbox.reconcile_on_resume(session_id)

    @app.get("/v1/inbox/routing")
    def inbox_routing() -> dict[str, Any]:
        return {"bindings": manager.inbox_routing.bindings()}

    @app.post("/v1/inbox/routing/binding")
    def set_inbox_binding(body: dict) -> dict[str, Any]:
        name = str(body.get("name", "")).strip()
        if not name:
            return {"ok": False, "error": "binding needs a `name`"}
        return manager.set_inbox_binding(
            name,
            channel=body.get("channel") or None,
            target=str(body.get("target", "")),
        )

    @app.get("/v1/sessions/{session_id}/unattended")
    def get_unattended(session_id: str) -> dict[str, Any]:
        return {"unattended": manager.unattended.is_unattended(session_id)}

    @app.post("/v1/sessions/{session_id}/unattended")
    def set_unattended(session_id: str, body: dict) -> dict[str, Any]:
        # The GUI gates the on-transition behind a one-tap confirm.
        on = bool(body.get("unattended"))
        manager.unattended.set(session_id, on)
        return {"ok": True, "session_id": session_id, "unattended": on}

    @app.get("/v1/sessions/{session_id}/connections")
    def session_connections(session_id: str, persona: str = "") -> dict[str, Any]:
        # `persona` is the GUI's hint for brand-new sessions (no record yet) — without it the
        # view resolves to the default persona and shows the wrong defaults/recommends.
        # §6: the Sources drawer payload — connected connectors w/ state + recommended + ⚠ count.
        return manager.session_connections_view(session_id, persona or None)

    @app.post("/v1/sessions/{session_id}/connections")
    def set_session_connection(session_id: str, body: dict) -> dict[str, Any]:
        # §6: a session override. `clear` drops the override (inherit the persona default again);
        # otherwise set an explicit on/off. Return the refreshed view so the drawer can re-render.
        body = body or {}
        connector = str(body.get("connector", "")).strip()
        if not connector:
            return {"ok": False, "error": "connector required"}
        if body.get("clear"):
            manager.session_connections.clear(session_id, connector)
        else:
            manager.session_connections.set(
                session_id, connector, bool(body.get("enabled", False))
            )
        persona = str(body.get("persona", "")) or None
        return {
            "ok": True,
            "connections": manager.session_connections_view(session_id, persona),
        }

    @app.post("/v1/personas/install")
    def install_persona(body: dict) -> dict[str, Any]:
        # Returns a consent summary per persona; they land disabled pending the user's approval
        # (then POST /v1/personas/{id} {enabled:true, surfaced:true}).
        reg = manager.personas
        try:
            if body.get("git_url"):
                summaries = reg.install_from_git(str(body["git_url"]))
            elif body.get("dir"):
                summaries = reg.install_from_dir(str(body["dir"]))
            else:
                return {"ok": False, "error": "provide a `dir` or `git_url`"}
        except Exception as e:  # surface manifest/clone errors to the caller
            return {"ok": False, "error": str(e)}
        return {"ok": True, "consent": summaries, "personas": reg.list_all()}

    @app.post("/v1/personas/{persona_id}")
    def update_persona(persona_id: str, body: dict) -> dict[str, Any]:
        reg = manager.personas
        archived = 0
        try:
            if "enabled" in body:
                # Disable archives the persona's sessions atomically (server-side, one
                # request) so any client gets the same semantic. See set_persona_enabled.
                archived = manager.set_persona_enabled(
                    persona_id, bool(body["enabled"])
                )["archived_sessions"]
            if "surfaced" in body:
                reg.set_surfaced(persona_id, bool(body["surfaced"]))
            if body.get("default"):
                reg.set_default(persona_id)
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return {"ok": True, "personas": reg.list_all(), "archived_sessions": archived}

    @app.delete("/v1/personas/{persona_id}")
    def persona_delete(persona_id: str) -> dict[str, Any]:
        # Uninstall a non-builtin persona (snapshot dir + lifecycle state). Local
        # operation — works signed out, regardless of where the persona came from.
        try:
            manager.personas.uninstall(persona_id)
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "personas": manager.personas.list_all()}

    @app.get("/v1/personas/{persona_id}")
    def persona_detail(persona_id: str) -> dict[str, Any]:
        # §5 detail page: identity + capabilities + recommends(+connected) + default connections.
        detail = manager.persona_detail(persona_id)
        if detail is None:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return detail

    @app.post("/v1/personas/{persona_id}/enable")
    def persona_enable(persona_id: str, body: dict) -> dict[str, Any]:
        # Dedicated §5/§8 route; delegates to the same manager toggle as POST /v1/personas/{id}
        # (so disable archives the persona's sessions here too).
        try:
            manager.set_persona_enabled(
                persona_id, bool((body or {}).get("enabled", True))
            )
        except KeyError:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        return {"ok": True, "personas": manager.personas.list_all()}

    @app.post("/v1/personas/{persona_id}/connections")
    def persona_set_connection(persona_id: str, body: dict) -> dict[str, Any]:
        # §5: flip a persona-default connector on/off; re-reads so the client can refresh.
        body = body or {}
        connector = str(body.get("connector", "")).strip()
        if not connector:
            return {"ok": False, "error": "connector required"}
        return manager.set_persona_connection(
            persona_id, connector, bool(body.get("enabled", False))
        )

    @app.get("/v1/skills")
    def skills() -> dict[str, Any]:
        return {"skills": manager.list_skills()}

    @app.post("/v1/skills-manager/invoke")
    def skills_manager_invoke(body: dict | None = None) -> Any:
        """Dispatch one production Skills Manager command for the browser counterpart.

        The request mirrors Tauri's IPC shape (``command`` + ``args``), allowing the
        existing Skills Manager components to remain unchanged in the desktop build.
        """
        payload = body if isinstance(body, dict) else {}
        command = payload.get("command")
        args = payload.get("args", {})
        if not isinstance(command, str) or not command.strip():
            raise HTTPException(status_code=422, detail="command must be a string")
        try:
            return app.state.skills_manager.invoke(
                command, args if isinstance(args, dict) else {}
            )
        except SkillsManagerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/skills-manager/file")
    def skills_manager_file(path: str) -> FileResponse:
        """Serve a local custom tool icon through the authenticated sidecar."""
        try:
            file_path = app.state.skills_manager.file_path(path)
        except SkillsManagerError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        headers = {"X-Content-Type-Options": "nosniff"}
        if app.state.skills_manager.is_web_staging_path(file_path):
            # Browser-selected uploads and generated exports are data artifacts, not
            # pages. Force download even for names such as `payload.html` so a LAN
            # browser cannot turn the staging endpoint into an inline XSS surface.
            return FileResponse(
                file_path,
                media_type="application/octet-stream",
                filename=file_path.name,
                headers=headers,
            )
        return FileResponse(file_path, headers=headers)

    @app.post("/v1/skills-manager/upload")
    def skills_manager_upload(body: dict | None = None) -> dict[str, str]:
        payload = body if isinstance(body, dict) else {}
        try:
            return {
                "path": app.state.skills_manager.upload_file(
                    str(payload.get("name", "upload.bin")),
                    str(payload.get("data", "")),
                )
            }
        except SkillsManagerError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/skills-manager/reserve-export")
    def skills_manager_reserve_export(body: dict | None = None) -> dict[str, str]:
        payload = body if isinstance(body, dict) else {}
        return {"path": app.state.skills_manager.reserve_export(str(payload.get("name", "skills-export.zip")))}

    @app.get("/v1/workspaces/recent")
    def recent_workspaces() -> dict[str, Any]:
        return {"workspaces": manager.recent_workspaces()}

    @app.post("/v1/workspaces/open")
    def open_workspace(body: dict) -> dict[str, Any]:
        return manager.open_workspace(
            body.get("path", ""), create=bool(body.get("create"))
        )

    @app.get("/v1/workspaces/trusted")
    def trusted_workspaces() -> dict[str, Any]:
        return {"workspaces": manager.trusted_workspaces()}

    @app.post("/v1/workspaces/trust")
    def set_workspace_trust(body: dict) -> dict[str, Any]:
        return manager.set_workspace_trust(
            str((body or {}).get("path", "")),
            trusted=bool((body or {}).get("trusted", False)),
        )

    @app.post("/v1/workspaces/pick")
    async def pick_workspace() -> dict[str, Any]:
        # Native folder picker opened by the LOCAL sidecar (browser GUIs can't get absolute
        # paths from web file dialogs). Off the event loop: blocks until pick/cancel.
        return await asyncio.to_thread(manager.pick_native_folder)

    @app.get("/v1/sessions")
    def sessions(workspace: str | None = None) -> dict[str, Any]:
        return {"sessions": manager.list_sessions(workspace)}

    @app.get("/v1/sessions/{session_id}/messages")
    def session_messages(session_id: str) -> dict[str, Any]:
        return {"messages": manager.session_messages(session_id)}

    @app.patch("/v1/sessions/{session_id}")
    def session_patch(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        if "pinned" in body or "archived" in body:
            return manager.set_session_flags(
                session_id,
                pinned=bool(body["pinned"]) if "pinned" in body else None,
                archived=bool(body["archived"]) if "archived" in body else None,
            )
        return manager.rename_session(session_id, str(body.get("title", "")))

    @app.delete("/v1/sessions/{session_id}")
    def session_delete(session_id: str) -> dict[str, Any]:
        return manager.delete_session(session_id)

    @app.get("/v1/sessions/{session_id}/roots")
    def session_roots(session_id: str) -> dict[str, Any]:
        return {"roots": manager.get_roots(session_id)}

    @app.post("/v1/sessions/{session_id}/roots")
    def session_add_root(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.add_root(
            session_id, str(body.get("path", "")), bool(body.get("writable", False))
        )

    @app.delete("/v1/sessions/{session_id}/roots")
    def session_remove_root(session_id: str, path: str) -> dict[str, Any]:
        return manager.remove_root(session_id, path)

    @app.get("/v1/sessions/{session_id}/artifacts")
    def session_artifacts(session_id: str) -> dict[str, Any]:
        return {"artifacts": manager.list_artifacts(session_id)}

    @app.get("/v1/sessions/{session_id}/artifacts/read")
    def session_artifact_read(session_id: str, path: str) -> dict[str, Any]:
        return manager.read_artifact(session_id, path)

    @app.post("/v1/sessions/{session_id}/artifacts/reveal")
    def session_artifact_reveal(session_id: str, body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.reveal_artifact(
            session_id, str(body.get("path", "")), str(body.get("mode", "reveal"))
        )

    @app.get("/v1/memory")
    def memory() -> dict[str, Any]:
        return {"memory": manager.list_memory()}

    @app.post("/v1/memory")
    def add_memory(body: dict) -> dict[str, Any]:
        return manager.add_memory(
            body.get("content", ""), body.get("scope", "workspace")
        )

    @app.post("/v1/chat/completions")
    def chat_completions(body: dict) -> dict[str, Any]:
        model = body.get("model", manager.model)
        turn = manager.provider_complete(
            model, body.get("messages", []), body.get("tools")
        )
        return _openai_response(model, turn)

    # -- MCP servers ------------------------------------------------------------
    @app.get("/v1/mcp")
    def mcp_list() -> dict[str, Any]:
        return {"servers": manager.list_mcp()}

    @app.post("/v1/mcp")
    def mcp_add(body: dict) -> dict[str, Any]:
        name = body.get("name")
        config = body.get("config")
        if not name or not isinstance(config, dict):
            return {"ok": False, "error": "name and config required"}
        return manager.add_mcp(name, config)

    @app.patch("/v1/mcp/{name}")
    def mcp_patch(name: str, body: dict) -> dict[str, Any]:
        return manager.patch_mcp(name, body or {})

    @app.delete("/v1/mcp/{name}")
    def mcp_delete(name: str) -> dict[str, Any]:
        return manager.delete_mcp(name)

    @app.get("/v1/mcp/{name}/tools")
    async def mcp_tools(name: str) -> dict[str, Any]:
        return await manager.mcp_tools(name)

    @app.post("/v1/mcp/{name}/connect")
    async def mcp_connect(name: str) -> dict[str, Any]:
        # Connect now. For `auth: oauth` servers the first connect opens the system
        # browser and waits on the loopback callback — that can take minutes, so it
        # runs as a background task; the GUI polls /v1/mcp for the status flip
        # (authorizing → connected | needs_auth + last_error).
        asyncio.create_task(manager.connect_mcp(name))
        return {"ok": True, "started": True}

    @app.post("/v1/mcp/{name}/signout")
    async def mcp_signout(name: str) -> dict[str, Any]:
        return await manager.signout_mcp(name)

    @app.get("/mcp/oauth/callback")
    async def mcp_oauth_callback(
        code: str = "", state: str = "", error: str = ""
    ) -> Any:
        # Loopback landing for the MCP OAuth browser flow (mcp/oauth.py). Browser-facing:
        # returns the same styled loopback page.
        from fastapi.responses import HTMLResponse

        from ..mcp import oauth as mcp_oauth

        if error:
            return HTMLResponse(
                _browser_page(
                    "Sign-in failed",
                    "The service reported an error. Return to Vegapunk and try again.",
                    ok=False,
                    error=error,
                ),
                status_code=400,
            )
        if not code or not mcp_oauth.deliver_callback(code, state or None):
            return HTMLResponse(
                _browser_page(
                    "Nothing waiting for this sign-in",
                    "The sign-in may have timed out. Return to Vegapunk and start it again.",
                    ok=False,
                ),
                status_code=400,
            )
        return HTMLResponse(
            _browser_page(
                "Connected",
                "Sign-in complete. You can close this tab and return to Vegapunk.",
                ok=True,
            )
        )

    @app.post("/v1/mcp/reload")
    async def mcp_reload() -> dict[str, Any]:
        return await manager.reload_mcp()

    # -- connectors (Slack / Telegram / …) --------------------------------------
    @app.get("/v1/connectors")
    def connectors_list() -> dict[str, Any]:
        return {"connectors": manager.list_connectors()}

    async def _refresh_listeners_if_two_way(name: str) -> None:
        # New/removed creds only take effect when the platform socket reconnects (Socket Mode
        # authenticates at connect time) — hot-reload the listeners in-process so pasting
        # tokens works immediately, no sidecar restart (§19).
        from ..connectors.config import PLATFORMS

        if name in PLATFORMS:
            try:
                await manager.refresh_gateway()
            except Exception:
                pass  # a listener that fails to come up must not fail the save

    @app.post("/v1/connectors/{name}/connect")
    async def connector_connect(name: str, body: dict) -> dict[str, Any]:
        fields = body.get("fields") if isinstance(body, dict) else None
        # experimental connectors require the caller to explicitly acknowledge the risk notice
        acknowledged = bool(isinstance(body, dict) and body.get("acknowledge_risk"))
        # token validation does a blocking HTTP call → keep it off the event loop
        result = await asyncio.to_thread(
            lambda: manager.connect_connector(
                name, fields or {}, acknowledged=acknowledged
            )
        )
        if result.get("ok"):
            await _refresh_listeners_if_two_way(name)
        return result

    @app.post("/v1/connectors/{name}/mcp-connect")
    async def connector_mcp_connect(name: str) -> dict[str, Any]:
        # One-click connect for an MCP-backed connector: the browser OAuth flow can
        # take minutes, so it runs in the background; the GUI polls /v1/connectors
        # until the card flips to connected (mode "mcp").
        from ..connectors.descriptors import get_descriptor

        d = get_descriptor(name)
        if d is None or not d.mcp_url:
            return {"ok": False, "error": f"{name} has no MCP connect path"}
        asyncio.create_task(manager.mcp_connect_connector(name))
        return {"ok": True, "started": True}

    @app.post("/v1/connectors/{name}/disconnect")
    async def connector_disconnect(name: str) -> dict[str, Any]:
        result = manager.disconnect_connector(name)
        await _refresh_listeners_if_two_way(name)
        return result

    @app.post("/v1/connectors/gmail/accounts/{email}/disconnect")
    def gmail_account_disconnect(email: str) -> dict[str, Any]:
        """Drop ONE mailbox; the default pointer moves to the next account."""
        from ..connectors import gmail_accounts

        return gmail_accounts.disconnect_account(manager.secrets, email)

    @app.post("/v1/connectors/gmail/accounts/{email}/default")
    def gmail_account_default(email: str) -> dict[str, Any]:
        from ..connectors import gmail_accounts

        return gmail_accounts.set_default(manager.secrets, email)

    @app.patch("/v1/connectors/gmail/filters")
    def gmail_filters(body: dict) -> dict[str, Any]:
        """Replace the "Never show agents" lists. Enforced in the local tool
        layer; agents see silent omissions, the user sees counts + audit."""
        from ..connectors import gmail_accounts

        senders = body.get("senders") if isinstance(body, dict) else None
        labels = body.get("labels") if isinstance(body, dict) else None
        if senders is not None and not isinstance(senders, list):
            return {"ok": False, "error": "senders must be a list"}
        if labels is not None and not isinstance(labels, list):
            return {"ok": False, "error": "labels must be a list"}
        return gmail_accounts.set_filters(manager.secrets, senders, labels)

    @app.post("/v1/connectors/google_calendar/accounts/{email}/disconnect")
    def gcal_account_disconnect(email: str) -> dict[str, Any]:
        """Drop ONE Google Calendar account; the default pointer moves to the
        next account."""
        from ..connectors import gcal_accounts

        return gcal_accounts.disconnect_account(manager.secrets, email)

    @app.post("/v1/connectors/google_calendar/accounts/{email}/default")
    def gcal_account_default(email: str) -> dict[str, Any]:
        from ..connectors import gcal_accounts

        return gcal_accounts.set_default(manager.secrets, email)

    @app.post("/v1/connectors/hubspot/portals/{hub_id}/disconnect")
    def hubspot_portal_disconnect(hub_id: str) -> dict[str, Any]:
        from ..connectors import hubspot_portals

        return hubspot_portals.disconnect_portal(manager.secrets, hub_id)

    @app.post("/v1/connectors/hubspot/portals/{hub_id}/default")
    def hubspot_portal_default(hub_id: str) -> dict[str, Any]:
        from ..connectors import hubspot_portals

        return hubspot_portals.set_default(manager.secrets, hub_id)

    @app.post("/v1/connectors/{name}/accounts/{account_id}/disconnect")
    def account_disconnect(name: str, account_id: str) -> dict[str, Any]:
        """Generic per-account disconnect for account-patterned connectors
        (batch 2+). Gmail/Calendar keep their specific email routes."""
        from ..connectors import accounts

        if not accounts.is_account_connector(name):
            return {"ok": False, "error": "not a multi-account connector"}
        return accounts.disconnect_account(manager.secrets, name, account_id)

    @app.post("/v1/connectors/{name}/accounts/{account_id}/default")
    def account_default(name: str, account_id: str) -> dict[str, Any]:
        from ..connectors import accounts

        if not accounts.is_account_connector(name):
            return {"ok": False, "error": "not a multi-account connector"}
        return accounts.set_default(manager.secrets, name, account_id)

    @app.patch("/v1/connectors/hubspot/hidden-fields")
    def hubspot_hidden_fields(body: dict) -> dict[str, Any]:
        """Replace the hidden-fields denylist (property names stripped from every
        record agents read — model-facing policy, not a human ACL)."""
        from ..connectors import hubspot_portals

        fields = body.get("hidden_fields") if isinstance(body, dict) else None
        if not isinstance(fields, list):
            return {"ok": False, "error": "hidden_fields must be a list"}
        return hubspot_portals.set_hidden_fields(manager.secrets, fields)

    @app.post("/v1/connectors/{name}/unauthorized/{item_id}")
    async def connector_unauthorized_resolve(
        name: str, item_id: str, body: dict
    ) -> dict[str, Any]:
        # Resolve a parked unauthorized message: dismiss / allow / allow_deliver (§19).
        action = str((body or {}).get("action", "")).strip()
        return await manager.resolve_unauthorized(name, item_id, action)

    @app.patch("/v1/connectors/{name}/tools")
    def connector_tools_patch(name: str, body: dict) -> dict[str, Any]:
        enabled = (body or {}).get("enabled")
        if not isinstance(enabled, dict):
            return {"ok": False, "error": "enabled map required"}
        return manager.update_connector_tools(name, enabled)

    @app.post("/v1/connectors/{name}/allow")
    def connector_allow(name: str, body: dict) -> dict[str, Any]:
        # `name` (optional) seeds the people directory so a directory-picked user's
        # chip shows their display name before they've ever sent a message.
        return manager.allow_user(
            name,
            str(body.get("user_id", "")),
            display_name=str(body.get("name", "")),
        )

    @app.get("/v1/connectors/slack/directory")
    async def slack_directory(q: str = "", limit: int = 25) -> dict[str, Any]:
        """Workspace member roster for the people picker. Cached locally; never
        leaves this machine."""
        from ..connectors import slack_directory as roster

        return await asyncio.to_thread(
            lambda: roster.list_members(manager.secrets, q, limit)
        )

    @app.get("/v1/connectors/slack/channels")
    async def slack_channels(q: str = "", limit: int = 25) -> dict[str, Any]:
        """Channel roster for the channel typeahead: all public channels, private
        ones only where the bot is a member (Slack API constraint)."""
        from ..connectors import slack_directory as roster

        return await asyncio.to_thread(
            lambda: roster.list_channels(manager.secrets, q, limit)
        )

    @app.post("/v1/connectors/{name}/disallow")
    def connector_disallow(name: str, body: dict) -> dict[str, Any]:
        return manager.disallow_user(name, str(body.get("user_id", "")))

    @app.post("/v1/connectors/slack/approval-owners/add")
    def slack_approval_owner_add(body: dict) -> dict[str, Any]:
        return manager.set_slack_approval_owner(
            str(body.get("user_id", "")),
            add=True,
            display_name=str(body.get("name", "")),
        )

    @app.post("/v1/connectors/slack/approval-owners/remove")
    def slack_approval_owner_remove(body: dict) -> dict[str, Any]:
        return manager.set_slack_approval_owner(
            str(body.get("user_id", "")), add=False
        )

    # -- audit / browser observability ------------------------------------------
    @app.get("/v1/audit")
    def audit_list(
        limit: int = 100,
        session_id: str | None = None,
        connector: str | None = None,
        tool: str | None = None,
    ) -> dict[str, Any]:
        return {
            "events": manager.list_audit(
                limit=limit, session_id=session_id, connector=connector, tool=tool
            )
        }

    @app.get("/v1/browser/state")
    def browser_state_get() -> dict[str, Any]:
        return manager.browser_state()

    @app.post("/v1/browser/screenshot")
    def browser_screenshot_post() -> dict[str, Any]:
        return manager.browser_screenshot()

    @app.post("/v1/browser/close")
    def browser_close_post() -> dict[str, Any]:
        return manager.browser_close()

    # -- web search -------------------------------------------------------------
    @app.get("/v1/web-search")
    def web_search_get() -> dict[str, Any]:
        return manager.get_web_search()

    @app.post("/v1/web-search")
    def web_search_set(body: dict) -> dict[str, Any]:
        provider = (body or {}).get("provider", "")
        if not provider:
            return {"ok": False, "error": "provider required"}
        return manager.set_web_search(provider, (body or {}).get("api_key"))

    # -- model providers (OpenAI, Ollama, …) ------------------------------------
    @app.get("/v1/providers")
    def providers_get() -> list[dict[str, Any]]:
        return manager.get_providers()

    @app.post("/v1/providers")
    def providers_set(body: dict) -> dict[str, Any]:
        name = (body or {}).get("name", "")
        if not name:
            return {"ok": False, "error": "name required"}
        return manager.set_provider(name, (body or {}).get("fields"))

    @app.delete("/v1/providers/{name}")
    def providers_remove(name: str) -> dict[str, Any]:
        return manager.remove_provider(name)

    @app.post("/v1/providers/verify")
    async def providers_verify(body: dict) -> dict[str, Any]:
        # Live read-only credential check (sync httpx) — run off the event loop.
        name = (body or {}).get("name", "") or "openai"
        return await asyncio.to_thread(
            manager.verify_provider, name, (body or {}).get("fields")
        )

    # -- settings (model API key) -----------------------------------------------
    @app.get("/v1/settings")
    def settings_get() -> dict[str, Any]:
        return manager.get_settings()

    @app.get("/v1/settings/discovery-launch")
    def settings_discovery_launch_get() -> dict[str, Any]:
        return manager.get_discovery_launch_preferences()

    @app.get("/v1/settings/api-services")
    def settings_api_services_get() -> dict[str, Any]:
        """Return the fixed External data catalog with redacted credentials."""
        return {"services": manager.get_api_services()}

    @app.post("/v1/settings/api-services/{name}")
    def settings_api_service_set(name: str, body: dict | None = None) -> dict[str, Any]:
        """Save exactly one API service profile; omitted credentials remain stored."""
        payload = body or {}
        current = next((item for item in manager.get_api_services() if item["name"] == name), None)
        if current is None:
            raise HTTPException(status_code=404, detail=f"unknown API service: {name}")
        enabled = bool(payload["enabled"]) if "enabled" in payload else bool(current["enabled"])
        return manager.set_api_service(
            name,
            enabled=enabled,
            credential=payload.get("credential"),
            credential_provided="credential" in payload,
            docs_url=payload.get("docs_url"),
            docs_url_provided="docs_url" in payload,
        )

    @app.post("/v1/settings/api-services/{name}/test")
    async def settings_api_service_test(name: str, body: dict | None = None) -> dict[str, Any]:
        """Run one read-only service check without blocking the event loop."""
        payload = body or {}
        current = next((item for item in manager.get_api_services() if item["name"] == name), None)
        if current is None:
            raise HTTPException(status_code=404, detail=f"unknown API service: {name}")
        return await asyncio.to_thread(
            manager.test_api_service,
            name,
            credential=payload.get("credential"),
            credential_provided="credential" in payload,
            docs_url=payload.get("docs_url"),
            docs_url_provided="docs_url" in payload,
        )

    @app.put("/v1/settings/discovery-launch")
    @app.post("/v1/settings/discovery-launch")
    def settings_discovery_launch_set(body: dict | None = None) -> dict[str, Any]:
        try:
            return {
                "ok": True,
                **manager.set_discovery_launch_preferences(body or {}),
            }
        except DiscoveryPreferencesValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.to_dict()) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Discovery Launch preferences could not be saved. Try again.",
            ) from exc

    @app.post("/v1/settings/model-key")
    def settings_set_model_key(body: dict) -> dict[str, Any]:
        return manager.set_model_key((body or {}).get("api_key", ""))

    @app.post("/v1/settings/default-model")
    def settings_set_default_model(body: dict) -> dict[str, Any]:
        return manager.set_default_model((body or {}).get("model", ""))

    @app.post("/v1/settings/models/add")
    def settings_models_add(body: dict) -> dict[str, Any]:
        return manager.add_model((body or {}).get("model", ""))

    @app.post("/v1/settings/models/remove")
    def settings_models_remove(body: dict) -> dict[str, Any]:
        return manager.remove_model((body or {}).get("model", ""))

    @app.post("/v1/settings/onboarded")
    def settings_set_onboarded(body: dict) -> dict[str, Any]:
        return manager.set_onboarded(bool((body or {}).get("value", True)))

    @app.post("/v1/settings/experimental-connectors")
    def settings_set_experimental(body: dict) -> dict[str, Any]:
        return manager.set_experimental_connectors(bool((body or {}).get("value")))

    @app.post("/v1/settings/surfaces")
    def settings_set_surfaces(body: dict) -> dict[str, Any]:
        b = body or {}
        return manager.set_surfaces(chat=b.get("chat"), code=b.get("code"))

    @app.post("/v1/settings/scratch-base")
    def settings_set_scratch_base(body: dict) -> dict[str, Any]:
        return manager.set_scratch_base(str((body or {}).get("path", "")))

    @app.post("/v1/settings/nav-layout")
    def settings_set_nav_layout(body: dict) -> dict[str, Any]:
        return manager.set_nav_layout(str((body or {}).get("nav_layout", "")))

    @app.post("/v1/settings/sessions-peek")
    def settings_set_sessions_peek(body: dict) -> dict[str, Any]:
        # Sidebar: sessions shown per group before "Show more" (owner ask, 2026-07-03).
        return manager.set_sessions_peek((body or {}).get("sessions_peek", 5))

    @app.post("/v1/settings/pdf")
    def settings_set_pdf(body: dict) -> dict[str, Any]:
        # Token savings (owner ask, 2026-07-17): fallback mode for models without native
        # PDF support + attach-time page/size thresholds.
        b = body or {}
        return manager.set_pdf_settings(
            fallback=b.get("pdf_fallback"),
            max_pages=b.get("pdf_max_pages"),
            max_mb=b.get("pdf_max_mb"),
        )

    @app.post("/v1/attachments/inspect-pdf")
    def attachments_inspect_pdf(body: dict) -> dict[str, Any]:
        # Attach-time page/size probe for the composer's threshold check. Local only.
        from ..pdf_support import inspect

        return inspect(str((body or {}).get("data_url", "")))

    # -- direct-message routing -------------------------------------------------
    @app.get("/v1/messaging/dm-route")
    def dm_route_get() -> dict[str, Any]:
        return {"dm_session": manager.dm_session()}

    @app.post("/v1/messaging/dm-route")
    def dm_route_set(body: dict) -> dict[str, Any]:
        # A falsy session_id clears the designation (DMs then park as unrouted).
        return manager.set_dm_session((body or {}).get("session_id", ""))

    if os.environ.get("COWORKER_DEBUG_INJECT") == "1":
        # Dev-only (env-gated, localhost): feed a message through the real inbound path so the
        # messaging stack can be exercised without a live bot connection. Not registered otherwise.
        @app.post("/v1/_debug/inject_inbound")
        async def debug_inject_inbound(body: dict) -> dict[str, Any]:
            from ..connectors.base import MessageEvent, SessionSource

            event = MessageEvent(
                text=str((body or {}).get("text", "")),
                source=SessionSource(
                    platform=str(body.get("platform", "slack")),
                    chat_id=str(body.get("chat_id", "C0BD7KZ1AH5")),
                    user_id=str(body.get("user_id", "U07JK68S4BH")),
                    user_name=str(body.get("user_name", "tester")),
                    chat_type=str(body.get("chat_type", "channel")),
                    chat_name=str(body.get("chat_name", "")) or None,
                    thread_id=str(body.get("thread_ts", "")) or None,
                    team_id=str(body.get("team_id", "")) or None,
                ),
                message_id=str(body.get("ts", "")) or None,
                # §31 mention router: the flag is normally computed from the raw Slack text
                # at mapping time; the injector sets it directly.
                mentions_me=bool(body.get("mentions_me")),
            )
            await manager._dispatch_inbound(event)
            return {"ok": True}

    # -- YouTube automation ------------------------------------------------------
    def _youtube_video_public(video: dict[str, Any], *, include_body: bool = False) -> dict[str, Any]:
        result = {
            "video_id": video.get("video_id"),
            "channel_id": video.get("channel_id"),
            "channel_title": video.get("channel_title"),
            "title": video.get("title"),
            "url": video.get("url"),
            "published_at": video.get("published_at"),
            "published_ts": video.get("published_ts"),
            "discovered_at": video.get("discovered_at"),
            "selected": bool(video.get("selected")),
            "caption_status": video.get("caption_status"),
            "caption_error": video.get("caption_error"),
            "caption": {
                "language_code": video.get("language_code"),
                "language_name": video.get("language_name"),
                "track_kind": video.get("track_kind"),
                "source": video.get("caption_source"),
            }
            if video.get("language_code")
            else None,
            "translation_status": video.get("translation_status") or "pending",
            "translation_error": video.get("translation_error"),
            "translation": {
                "language_code": video.get("translation_language_code"),
                "model": video.get("translation_model"),
                "translated_at": video.get("translated_at"),
            }
            if video.get("translation_status") == "ready"
            else None,
        }
        if include_body:
            result["caption_body"] = video.get("caption_body")
            result["translation_body"] = video.get("translation_body")
        return result

    @app.get("/v1/youtube/status")
    def youtube_status() -> dict[str, Any]:
        return {
            **manager.youtube_client.status(),
            "subscriptions_synced_at": manager.youtube_store.get_state("subscriptions_synced_at"),
            "last_scan_at": manager.youtube_store.get_state("last_scan_at"),
            "channel_count": len(manager.youtube_store.list_channels()),
            "video_count": len(manager.youtube_store.list_videos()),
        }

    def youtube_redirect_uri(request: Request) -> str:
        return manager.youtube_client.oauth_redirect_uri(
            str(request.url_for("youtube_oauth_callback"))
        )

    def youtube_authorization_redirect_uri(
        request: Request, requested_redirect_uri: str
    ) -> str:
        requested = requested_redirect_uri.strip()
        if requested:
            parsed = urlsplit(requested)
            callback_path = request.url_for("youtube_oauth_callback").path
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path != callback_path
                or parsed.query
                or parsed.fragment
            ):
                raise YouTubeAuthError(
                    "OAuth redirect URI must use the current YouTube callback path without a query or fragment."
                )
        return manager.youtube_client.authorization_redirect_uri(
            requested_redirect_uri=requested,
            default_redirect_uri=str(request.url_for("youtube_oauth_callback")),
        )

    @app.get("/v1/youtube/oauth/settings")
    def youtube_oauth_settings(request: Request) -> dict[str, Any]:
        return manager.youtube_client.oauth_settings(
            default_redirect_uri=str(request.url_for("youtube_oauth_callback"))
        )

    @app.put("/v1/youtube/oauth/settings")
    def youtube_oauth_settings_save(
        request: Request, body: dict | None = None
    ) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {}
        try:
            settings = manager.youtube_client.save_oauth_settings(
                client_id=str(payload.get("client_id") or ""),
                client_secret=str(payload.get("client_secret") or ""),
                redirect_uri=str(
                    payload.get("redirect_uri") or youtube_redirect_uri(request)
                ),
            )
        except YouTubeAuthError as exc:
            return {"ok": False, "error": str(exc)}
        manager.secrets.delete("youtube:default")
        return {"ok": True, **settings}

    @app.get("/v1/youtube/oauth/start")
    def youtube_oauth_start(
        request: Request, redirect_uri: str = ""
    ) -> dict[str, Any]:
        state = secrets.token_urlsafe(32)
        try:
            resolved_redirect_uri = youtube_authorization_redirect_uri(
                request, redirect_uri
            )
            url = manager.youtube_client.authorization_url(
                state=state, redirect_uri=resolved_redirect_uri
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        youtube_oauth_states[state] = (time.time() + 600, resolved_redirect_uri)
        return {"ok": True, "authorization_url": url}

    @app.get("/v1/youtube/oauth/callback", name="youtube_oauth_callback")
    async def youtube_oauth_callback(
        request: Request, code: str = "", state: str = "", error: str = ""
    ) -> HTMLResponse:
        if error:
            youtube_oauth_states.pop(state, None)
            return HTMLResponse(
                _browser_page(
                    "YouTube sign-in failed",
                    "Return to Vegapunk and start the connection again.",
                    ok=False,
                    error=error,
                    connector="youtube",
                ),
                status_code=400,
            )
        pending = youtube_oauth_states.pop(state, None)
        if not code or not state or pending is None or pending[0] < time.time():
            return HTMLResponse(
                _browser_page(
                    "Nothing waiting for this sign-in",
                    "The YouTube sign-in may have timed out. Start it again from Vegapunk.",
                    ok=False,
                    connector="youtube",
                ),
                status_code=400,
            )
        redirect_uri = pending[1]
        try:
            await manager.youtube_client.exchange_code(code=code, redirect_uri=redirect_uri)
            if manager.youtube_store.get_state("authorized_at") is None:
                manager.youtube_store.set_state("authorized_at", time.time())
            await manager.youtube.sync_subscriptions()
        except Exception as exc:
            return HTMLResponse(
                _browser_page(
                    "YouTube connection failed",
                    "The account was not connected. Return to Vegapunk and try again.",
                    ok=False,
                    error=str(exc),
                    connector="youtube",
                ),
                status_code=400,
            )
        return HTMLResponse(
            _browser_page(
                "YouTube connected",
                "Your subscriptions are synced. You can close this tab and return to Vegapunk.",
                ok=True,
                connector="youtube",
            )
        )

    @app.post("/v1/youtube/disconnect")
    def youtube_disconnect() -> dict[str, Any]:
        manager.secrets.delete("youtube:default")
        return {"ok": True}

    @app.post("/v1/youtube/subscriptions/refresh")
    async def youtube_subscriptions_refresh() -> dict[str, Any]:
        try:
            return await manager.youtube.sync_subscriptions()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @app.get("/v1/youtube/translation/settings")
    def youtube_translation_settings() -> dict[str, Any]:
        return manager.youtube_translation.settings()

    @app.put("/v1/youtube/translation/settings")
    def youtube_translation_settings_save(body: dict | None = None) -> dict[str, Any]:
        payload = body if isinstance(body, dict) else {}
        try:
            return {
                "ok": True,
                **manager.youtube_translation.save_settings(
                    base_url=str(payload.get("base_url") or ""),
                    model=str(payload.get("model") or ""),
                    api_key=payload.get("api_key"),
                    prompt=str(payload.get("prompt") or ""),
                    clear_api_key=bool(payload.get("clear_api_key")),
                ),
            }
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/v1/youtube/translation/test")
    async def youtube_translation_test() -> dict[str, Any]:
        return await manager.youtube_translation.test_connection()

    @app.post("/v1/youtube/updates")
    async def youtube_updates_fetch() -> dict[str, Any]:
        """Refresh the current subscriptions and discover their new videos."""
        try:
            result = await manager.youtube.scan()
            return {
                "ok": True,
                "discovered": result.discovered,
                "channel_failures": result.channel_failures,
                "scan_finished_at": result.scan_finished_at,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @app.post("/v1/youtube/automations")
    def youtube_automation_create(body: dict | None = None) -> dict[str, Any]:
        return manager.create_youtube_automation(body or {})

    @app.post("/v1/youtube/automations/{task_id}/run")
    async def youtube_automation_run(task_id: str) -> dict[str, Any]:
        return await manager.run_youtube_now(task_id)

    @app.get("/v1/youtube/videos")
    def youtube_videos() -> dict[str, Any]:
        return {"videos": [_youtube_video_public(v) for v in manager.youtube_store.list_videos()]}

    @app.get("/v1/youtube/videos/{video_id}")
    def youtube_video(video_id: str) -> dict[str, Any]:
        video = manager.youtube_store.get_video(video_id)
        if video is None:
            raise HTTPException(status_code=404, detail="video not found")
        return {"video": _youtube_video_public(video, include_body=True)}

    @app.post("/v1/youtube/videos/{video_id}/caption")
    async def youtube_video_caption(video_id: str) -> dict[str, Any]:
        if manager.youtube_store.get_video(video_id) is None:
            raise HTTPException(status_code=404, detail="video not found")
        try:
            result = await manager.youtube.fetch_caption(video_id)
        except YouTubeAuthError as exc:
            return {"ok": False, "error": str(exc)}
        video = result.get("video") or {}
        return {
            "ok": bool(result.get("ok")),
            "error": result.get("error"),
            "video": _youtube_video_public(video, include_body=True),
        }

    @app.post("/v1/youtube/videos/{video_id}/translate")
    async def youtube_video_translate(video_id: str) -> dict[str, Any]:
        if manager.youtube_store.get_video(video_id) is None:
            raise HTTPException(status_code=404, detail="video not found")
        result = await manager.youtube_translation.translate(video_id)
        video = result.get("video") or manager.youtube_store.get_video(video_id) or {}
        return {
            "ok": bool(result.get("ok")),
            "error": result.get("error"),
            "video": _youtube_video_public(video, include_body=True),
        }

    @app.patch("/v1/youtube/videos/{video_id}")
    def youtube_video_update(video_id: str, body: dict | None = None) -> dict[str, Any]:
        selected = (body or {}).get("selected")
        if not isinstance(selected, bool):
            return {"ok": False, "error": "selected must be a boolean"}
        if not manager.youtube_store.set_selected(video_id, selected):
            raise HTTPException(status_code=404, detail="video not found")
        return {"ok": True, "video": _youtube_video_public(manager.youtube_store.get_video(video_id) or {})}

    @app.delete("/v1/youtube/videos/{video_id}")
    def youtube_video_delete(video_id: str) -> dict[str, Any]:
        if not manager.youtube_store.delete_video(video_id):
            raise HTTPException(status_code=404, detail="video not found")
        return {"ok": True}

    # -- automations (scheduled tasks) ------------------------------------------
    @app.get("/v1/automations")
    def automations_list() -> dict[str, Any]:
        return manager.list_automations()

    @app.post("/v1/automations")
    def automations_create(body: dict) -> dict[str, Any]:
        return manager.create_automation(body or {})

    @app.get("/v1/automations/{task_id}")
    def automation_get(task_id: str) -> dict[str, Any]:
        return manager.get_automation(task_id)

    @app.patch("/v1/automations/{task_id}")
    def automation_update(task_id: str, body: dict) -> dict[str, Any]:
        return manager.update_automation(task_id, body or {})

    @app.delete("/v1/automations/{task_id}")
    def automation_delete(task_id: str) -> dict[str, Any]:
        return manager.delete_automation(task_id)

    @app.post("/v1/automations/{task_id}/seen")
    def automations_seen(task_id: str) -> dict[str, Any]:
        return manager.mark_automation_seen(task_id)

    @app.post("/v1/automations/{task_id}/run")
    def automation_run(task_id: str) -> dict[str, Any]:
        # Prepare a live manual run; the GUI opens the returned session and drives it.
        return manager.prepare_manual_run(task_id)

    @app.post("/v1/automations/{task_id}/runs/{run_id}/finalize")
    def automation_run_finalize(task_id: str, run_id: str) -> dict[str, Any]:
        return manager.finalize_manual_run(task_id, run_id)

    @app.websocket("/ws/session/{session_id}")
    async def ws_session(ws: WebSocket, session_id: str) -> None:
        if not _websocket_authenticated(ws):
            await ws.close(code=1008)
            return
        # CORS never gates WebSockets, so a cross-site page could otherwise open this socket
        # and drive the session into tool calls. Reject a disallowed browser Origin before
        # accepting the handshake (1008 = policy violation).
        if not _origin_allowed(
            ws.headers.get("origin"), host=ws.headers.get("host"), web_enabled=web_enabled
        ):
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol=_websocket_subprotocol(ws))
        agent = ws.query_params.get("agent") or "code"

        # All four interactive prompts (approval / question / directory / plan) are parked as Inbox
        # items and awaited via inbox.wait — so they survive a dropped socket (redelivered on
        # reconnect) and can be resolved from any surface. `visibility` decides where they SHOW:
        # Unattended → the cross-session Inbox; attended → inline in this session only. The agent
        # stays blocked until the item is resolved (live WS response, REST, or a bound channel).
        def _visibility() -> str:
            return (
                VIS_INBOX
                if manager.unattended.is_unattended(session_id)
                else VIS_INLINE
            )

        async def _mirror(item) -> None:
            # Unattended items mirror to a bound channel as buttons (see mirror_inbox_item).
            await manager.mirror_inbox_item(item)

        def _route() -> str:
            return manager.inbox_routing.route_for(session_id, agent)

        async def approver(_request) -> ApprovalOutcome:
            # The engine has already emitted PERMISSION_REQUIRED (the live inline card). Park the
            # item so the answer can also come from the Inbox / a reconnect / after a restart.
            item = manager.inbox.add_approval(
                session_id,
                f"Run `{_request.tool_name}`?",
                body="\n".join(
                    p
                    for p in (
                        (getattr(_request, "reason", "") or "").strip(),
                        args_preview(getattr(_request, "arguments", None)),
                    )
                    if p
                ),
                inbox=_route(),
                visibility=_visibility(),
                # Automation-run context (manual "Run now" rides this socket): lets the
                # card offer the task-persistent "Allow every time" (§25). {} elsewhere.
                data=manager.approval_prompt_data(session_id, _request),
                tool_call_id=getattr(_request, "tool_call_id", None),
            )
            if (
                item.state == "pending"
            ):  # freshly raised (not a durable-resume re-raise)
                manager.persist_session(
                    session_id
                )  # the pending tool call is now on disk
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resolution = await manager.inbox.wait(item.id)
            # Accept every vocabulary: the live card sends once/always_tool/always_command/
            # always_task/deny; the Inbox / a channel send allow/always/deny.
            return manager.approval_outcome(resolution, _request, session_id)

        async def question_asker(args: dict, tool_call_id=None) -> dict:
            # ask_user (engine does NOT emit the event — we do, only when attended).
            item = manager.inbox.add_question(
                session_id,
                str(args.get("question", "")),
                inbox=_route(),
                visibility=_visibility(),
                options=list(args.get("options") or []),
                allow_text=bool(args.get("allow_text", True)),
                multi=bool(args.get("multi", False)),
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
                else:
                    await ws.send_json(
                        {
                            "type": "question_requested",
                            "data": {
                                "question": item.title,
                                "options": item.options,
                                "allow_text": item.allow_text,
                                "multi": item.multi,
                                "header": str(args.get("header", "")),
                            },
                        }
                    )
            return {"answer": await manager.inbox.wait(item.id)}

        async def directory_requester(args: dict, tool_call_id=None) -> dict:
            # The engine has already emitted DIRECTORY_REQUESTED. Park, await, then apply the grant.
            item = manager.inbox.add_directory(
                session_id,
                "Grant access to a folder?",
                body=str(args.get("reason", "")),
                inbox=_route(),
                visibility=_visibility(),
                data={
                    "path": str(args.get("path", "")),
                    "writable": bool(args.get("writable", False)),
                },
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resp = _parse_json(
                await manager.inbox.wait(item.id)
            )  # {granted, path, writable}
            if not resp.get("granted"):
                return {"granted": False, "reason": "the user declined the request"}
            path = (resp.get("path") or args.get("path") or "").strip()
            if not path:
                return {"granted": False, "error": "no directory was provided"}
            writable = bool(resp.get("writable", args.get("writable", False)))
            res = manager.add_root(session_id, path, writable)
            if not res.get("ok"):
                return {
                    "granted": False,
                    "error": res.get("error", "could not grant access"),
                }
            primary = next(
                (
                    r
                    for r in res.get("roots", [])
                    if r.get("path")
                    and Path(r["path"]).expanduser().resolve()
                    == Path(path).expanduser().resolve()
                ),
                None,
            )
            return {
                "granted": True,
                "path": (primary or {}).get("path", path),
                "writable": writable,
            }

        async def plan_approver(_args: dict, tool_call_id=None) -> dict:
            # The engine has already emitted PLAN_PROPOSED. Park, await the verdict.
            item = manager.inbox.add_plan(
                session_id,
                "Approve the plan?",
                body=str(_args.get("plan", "")),
                inbox=_route(),
                visibility=_visibility(),
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                manager.persist_session(session_id)
                if item.visibility == VIS_INBOX:
                    await _mirror(item)
            resp = _parse_json(
                await manager.inbox.wait(item.id)
            )  # {approved, mode, feedback}
            if not resp.get("approved"):
                return {
                    "approved": False,
                    "feedback": resp.get("feedback") or "the user rejected the plan",
                }
            return {"approved": True, "mode": resp.get("mode") or "interactive"}

        async def _apply_model(model: Optional[str]) -> None:
            # Mid-session rebind is allowed (roadmap item 3, supersedes the 2026-07-04
            # lock): history is canonical and providers convert per call. A real switch
            # appends a persisted notice; broadcast it so live views render the marker
            # and update their header. Never rebind mid-turn — the running loop reads
            # `engine.model` per iteration and a mixed turn is exactly the breakage the
            # old lock existed to prevent.
            if not model or manager.is_running(session_id):
                return
            notice = engine.switch_model(model)
            if notice is None:  # same model, or first bind on a fresh session
                return
            manager.persist_session(session_id)
            await manager.broadcast_session(
                session_id,
                {"type": "model_changed", "data": {"model": model, "text": notice}},
            )

        def _resolve_pending(resolution: str) -> None:
            # Live WS responses resolve THE session's single pending prompt (one at a time, since the
            # agent blocks). Reconnect / Inbox resolve by id via REST instead.
            pend = manager.inbox.pending(session_id)
            if pend:
                manager.inbox.resolve(pend[0].id, resolution)

        workspace = ws.query_params.get("workspace")
        mcp_tools = await manager.prepare_mcp_tools(
            session_id, workspace=workspace, agent=agent
        )
        engine = manager.get_engine(
            session_id,
            workspace=workspace,
            agent=agent,
            approver=approver,
            extra_tools=mcp_tools,
            directory_requester=directory_requester,
            plan_approver=plan_approver,
            question_asker=question_asker,
        )
        if engine is None:
            await ws.send_json(
                {
                    "type": "error",
                    "data": {
                        "error": "no valid workspace — choose a project folder first"
                    },
                }
            )
            await ws.close()
            return
        await ws.send_json(
            {
                "type": "ready",
                "data": {
                    "session_id": session_id,
                    "agent": getattr(engine, "agent_name", "code"),
                    "model": engine.model,
                    "mode": engine.permissions.mode.value,
                    "workspace": (
                        str(getattr(engine, "executor").cwd)
                        if getattr(engine, "executor", None)
                        else None
                    ),
                    "command_trust": manager.workspace_command_trust(
                        str(getattr(engine, "audit_context", {}).get("workspace", ""))
                    ),
                },
            }
        )

        # Checkpoint events: persist mid-turn so a crash/quit can't eat the conversation.
        # turn_start = the user message just landed (a brand-new session gets its row here,
        # not at connect — empty never-used sessions shouldn't appear in Recents);
        # permission_required/directory_requested = parked indefinitely on the user;
        # iteration_end = a model response + its tool results completed.
        _CHECKPOINTS = {
            "turn_start",
            "permission_required",
            "directory_requested",
            "plan_proposed",
            "iteration_end",
        }

        async def run_turn(content, *, retry: bool = False) -> None:
            # The receive loop atomically claims this session before scheduling the task.
            # Keeping the claim outside prevents two back-to-back frames from both starting.
            try:
                events = engine.retry() if retry else engine.run(content)
                async for event in events:
                    # Broadcast to every socket viewing this session (this socket included — it's a
                    # registered client), so a second view of the same session stays in sync too.
                    await manager.broadcast_session(
                        session_id, {"type": event.type.value, "data": event.data}
                    )
                    if event.type.value in _CHECKPOINTS:
                        manager.save(session_id, engine)
            finally:
                manager.mark_idle(session_id)
                manager.save(session_id, engine)
                await manager.broadcast_session(
                    session_id, {"type": "turn_done", "data": {}}
                )

        # This socket is now a live view of the session; background turns (channel delivery,
        # self-wake, durable resume) broadcast here too, not just locally driven run_turns.
        manager.register_session_client(session_id, ws.send_json)
        inbound_times: deque[float] = deque()

        async def reject_input(reason: str) -> None:
            # Input validation failures are not provider failures and must not offer "Retry"
            # or flush an in-progress assistant stream in the GUI.
            await ws.send_json({"type": "input_rejected", "data": {"error": reason}})

        async def claim_turn(*, retry: bool = False, content=None) -> None:
            if not manager.try_mark_running(session_id):
                await reject_input(
                    "This session is already running a turn. Wait for it to finish or stop it."
                )
                return
            asyncio.create_task(run_turn(content, retry=retry))

        try:
            while True:
                try:
                    message = await ws.receive_json()
                except (json.JSONDecodeError, UnicodeDecodeError):
                    await reject_input("Invalid WebSocket message: expected JSON.")
                    continue

                now = asyncio.get_running_loop().time()
                while (
                    inbound_times
                    and now - inbound_times[0] > _WS_RATE_LIMIT_WINDOW_SECONDS
                ):
                    inbound_times.popleft()
                if len(inbound_times) >= _WS_RATE_LIMIT_COUNT:
                    await reject_input("Too many WebSocket messages; reconnect and try again.")
                    await ws.close(code=1008)
                    return
                inbound_times.append(now)

                if not isinstance(message, dict):
                    await reject_input("Invalid WebSocket message: expected an object.")
                    continue
                kind = message.get("type")
                if not isinstance(kind, str):
                    await reject_input("Invalid WebSocket message: missing string type.")
                    continue
                if kind == "approval":
                    _resolve_pending(message.get("decision", "deny"))
                elif kind == "directory_response":
                    _resolve_pending(
                        json.dumps(
                            {
                                "granted": bool(message.get("granted")),
                                "path": message.get("path", ""),
                                "writable": bool(message.get("writable", False)),
                            }
                        )
                    )
                elif kind == "plan_response":
                    _resolve_pending(
                        json.dumps(
                            {
                                "approved": bool(message.get("approved")),
                                "mode": message.get("mode", "interactive"),
                                "feedback": message.get("feedback", ""),
                            }
                        )
                    )
                elif kind == "question_response":
                    _resolve_pending(str(message.get("answer", "")))
                elif kind == "interrupt":
                    engine.request_interrupt()
                elif kind == "retry":
                    # Re-run after a provider error (engine guards on the error-notice
                    # tail, so a stray frame is a no-op that still ends with turn_done).
                    await claim_turn(retry=True)
                elif kind == "set_mode":
                    try:
                        engine.permissions.mode = Mode(message.get("mode"))
                    except (TypeError, ValueError):
                        pass
                elif kind == "set_model":
                    model = message.get("model")
                    if model is not None and not isinstance(model, str):
                        await reject_input("Invalid model: expected a string.")
                    else:
                        await _apply_model(model)
                elif kind == "user_message":
                    raw_text = message.get("text")
                    if raw_text is None:
                        raw_text = ""
                    if not isinstance(raw_text, str):
                        await reject_input("Invalid message text: expected a string.")
                        continue
                    text = raw_text.strip()
                    raw_attachments = message.get("attachments")
                    attachments = [] if raw_attachments is None else raw_attachments
                    # Reject an oversized frame instead of buffering it into a turn. Send a
                    # visible error so the surface can tell the user, and drop the message.
                    if not isinstance(attachments, list):
                        await reject_input("Invalid attachments: expected a list.")
                        continue
                    reject = None
                    if len(text) > _MAX_MESSAGE_TEXT_CHARS:
                        reject = (
                            f"Message too long ({len(text)} chars; "
                            f"limit {_MAX_MESSAGE_TEXT_CHARS})."
                        )
                    elif len(attachments) > _MAX_ATTACHMENTS:
                        reject = (
                            f"Too many attachments ({len(attachments)}; "
                            f"limit {_MAX_ATTACHMENTS})."
                        )
                    elif any(not isinstance(a, dict) for a in attachments):
                        reject = "Invalid attachment: expected an object."
                    elif _json_value_size(attachments) > _MAX_ATTACHMENTS_BYTES:
                        reject = "Attachments too large (limit 15 MB per message)."
                    else:
                        for attachment in attachments:
                            attachment_kind = attachment.get("kind")
                            name = attachment.get("name")
                            mime = attachment.get("mime")
                            if attachment_kind not in {"image", "pdf", "text"}:
                                reject = "Invalid attachment kind."
                            elif name is not None and (
                                not isinstance(name, str) or len(name) > 1024
                            ):
                                reject = "Invalid attachment name."
                            elif mime is not None and (
                                not isinstance(mime, str) or len(mime) > 255
                            ):
                                reject = "Invalid attachment MIME type."
                            elif attachment_kind == "image":
                                data = attachment.get("data_url")
                                if (
                                    not isinstance(data, str)
                                    or not data.startswith("data:image/")
                                    or ";base64," not in data
                                    or len(data) > MAX_IMAGE_CHARS
                                ):
                                    reject = "Invalid or oversized image attachment."
                            elif attachment_kind == "pdf":
                                data = attachment.get("data_url")
                                if (
                                    not isinstance(data, str)
                                    or not data.startswith(
                                        "data:application/pdf;base64,"
                                    )
                                    or len(data) > MAX_PDF_CHARS
                                ):
                                    reject = "Invalid or oversized PDF attachment."
                            else:
                                body = attachment.get("text")
                                if (
                                    not isinstance(body, str)
                                    or len(body) > MAX_TEXT_CHARS
                                ):
                                    reject = "Invalid or oversized text attachment."
                            if reject is not None:
                                break
                    if reject is not None:
                        await reject_input(reject)
                        continue
                    # The composer sends its visible model with every message — the FIRST
                    # one binds the session (race-proof across reconnects; see api.ts
                    # Session.userMessage), later ones may switch it (notice persisted).
                    model = message.get("model")
                    if model is not None and not isinstance(model, str):
                        await reject_input("Invalid model: expected a string.")
                        continue
                    await _apply_model(model)
                    if text or attachments:
                        content = build_user_content(text, attachments)
                        await claim_turn(content=content)
                else:
                    await reject_input(f"Unknown WebSocket message type: {kind}.")
        except WebSocketDisconnect:
            pass
        finally:
            manager.unregister_session_client(session_id, ws.send_json)

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        """App-wide event stream (session-independent): the GUI keeps one open for
        pushes like automation_run_started (the UX-026 toast). Read-only — inbound
        frames are ignored; the receive loop just detects disconnect."""
        if not _websocket_authenticated(ws):
            await ws.close(code=1008)
            return
        if not _origin_allowed(
            ws.headers.get("origin"), host=ws.headers.get("host"), web_enabled=web_enabled
        ):
            await ws.close(code=1008)
            return
        await ws.accept(subprotocol=_websocket_subprotocol(ws))
        manager.register_event_client(ws.send_json)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            manager.unregister_event_client(ws.send_json)

    if web_enabled and web_root is not None:

        @app.get("/{path:path}", include_in_schema=False)
        def web_spa(path: str, request: Request) -> Response:
            """Serve the exact desktop SPA and provide history-mode route fallback."""
            if web_auth_token and not _request_authenticated(request):
                response = HTMLResponse(_web_login_page(), status_code=200)
                response.headers["Cache-Control"] = "no-store"
                return response
            relative = Path(path)
            candidate = (web_root / relative).resolve()
            try:
                candidate.relative_to(web_root)
            except ValueError:
                return JSONResponse({"detail": "not found"}, status_code=404)
            if candidate.is_file() and candidate != web_index:
                return FileResponse(candidate)
            return _web_index_response(request)

    return app


def _parse_json(s: str) -> dict[str, Any]:
    """Parse a structured Inbox resolution (directory/plan carry their reply as a JSON string)."""
    try:
        v = json.loads(s) if s else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _openai_response(model: str, turn: AssistantTurn) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": turn.text or ""}
    if turn.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": turn.finish_reason or "stop",
            }
        ],
    }
