"""Browser/sidecar adapter for the production Skills Manager surface.

The production Skills Manager was originally implemented as a Tauri application.  The
Linux Web Counterpart keeps its UI and command names intact and routes those commands
through this small, filesystem-backed adapter.  It deliberately uses the same on-disk
``~/.skills-manager`` layout as the desktop application so switching surfaces does not
create a second Skills store.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any


class SkillsManagerError(RuntimeError):
    """A user-visible Skills Manager command failure."""


_TOOL_DEFINITIONS: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    ("claude-code", "Claude Code", ".claude", (), "claude"),
    ("codex", "Codex", ".codex", (), "codex"),
    ("codebuddy", "CodeBuddy", ".codebuddy", (), "codebuddy"),
    ("opencode", "OpenCode", ".config/opencode", (".opencode",), "opencode"),
    ("cursor", "Cursor", ".cursor", (), "cursor"),
    ("gemini", "Gemini CLI", ".gemini", (), "gemini"),
    ("antigravity", "Antigravity", ".antigravity", (), "antigravity"),
    ("windsurf", "Windsurf", ".windsurf", (), "windsurf"),
    ("trae", "Trae", ".trae", (), "trae"),
    ("droid", "Droid", ".factory", (".droid",), "droid"),
    ("augment", "Augment", ".augment", (), "augment"),
    ("openclaw", "OpenClaw", ".openclaw", (), "openclaw"),
    ("cline", "Cline", ".cline", (), "cline"),
    ("vercel-skills", "Vercel Skills", ".agents", (".vercel", ".vercel-skills"), "vercel"),
    ("commandcode", "CommandCode", ".commandcode", (), "commandcode"),
    ("continue", "Continue", ".continue", (), "continue"),
    ("crush", "Crush", ".config/crush", (".crush",), "crush"),
    ("goose", "Goose", ".config/goose", (".goose",), "goose"),
    ("iflow", "iFlow", ".iflow", (), "iflow"),
    ("junie", "Junie", ".junie", (), "junie"),
    ("kilo-code", "Kilo Code", ".kilocode", (), "kilo"),
    ("kiro", "Kiro", ".kiro", (), "kiro"),
    ("qoder", "Qoder", ".qoder", (), "qoder"),
    ("qwen-code", "Qwen Code", ".qwen", (), "qwen"),
    ("roo-code", "Roo Code", ".roo", (), "roo"),
    ("zencoder", "Zencoder", ".zencoder", (), "zencoder"),
    ("pi", "Pi", ".pi/agent", (), "pi"),
    ("trae-cn", "Trae CN", ".trae-cn", (), "trae"),
    ("hermes", "Hermes", ".hermes", (), "hermes"),
    ("workbuddy", "WorkBuddy", ".workbuddy", (), "workbuddy"),
    ("qoderwork-cn", "QoderWork CN", ".qoderworkcn", (), "qoderworkcn"),
)

_TEXT_EXTENSIONS = {
    ".md",
    ".mdx",
    ".markdown",
    ".txt",
    ".text",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".sh",
}

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".ico", ".gif", ".webp", ".avif"}


def _arg(args: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in args:
            return args[name]
    return default


def _now() -> int:
    return int(time.time())


def _as_path(value: Any, *, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise SkillsManagerError(f"{field} is required")
    return Path(value).expanduser()


def _configured_path(value: Any) -> Path | None:
    """Interpret an optional filesystem setting without treating ``""`` as ``.``."""
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # FastAPI executes sync handlers in a thread pool. Multiple Skills Manager
    # reads can therefore migrate/save the same config concurrently; a PID-only
    # temporary name lets those requests clobber each other's replace target.
    temp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


class SkillsManagerService:
    """Translate Tauri command names into local sidecar operations."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        workspace_root: str | Path | None = None,
    ) -> None:
        configured_root = root or os.environ.get("SKILLS_MANAGER_HOME")
        self.root = Path(configured_root).expanduser() if configured_root else Path.home() / ".skills-manager"
        self.config_path = self.root / "config.json"
        self.skills_path = self.root / "skills"
        self.workspace_roots = []
        if workspace_root is not None and str(workspace_root).strip():
            self.workspace_roots.append(Path(workspace_root).expanduser())
        # The Agents.md surface has one explicit global location. Keep it
        # addressable without granting the browser the rest of $HOME. It is
        # handled separately below so only the AGENTS.md entry is exposed.
        self.agents_md_root = Path.home() / ".codex"

    # -- configuration -----------------------------------------------------

    def _default_config(self) -> dict[str, Any]:
        tools: dict[str, Any] = {}
        home = Path.home()
        for tool_id, _name, config_dir, _alts, _cli in _TOOL_DEFINITIONS:
            config_path = home / config_dir
            tools[tool_id] = {
                "enabled": config_path.exists(),
                "detected": config_path.exists(),
                "skills_path": str(config_path / "skills"),
                "config_path": str(config_path),
            }
        return {
            "version": "2.1.7",
            "skills_dir": str(self.skills_path),
            "tools": tools,
            "custom_tools": {},
            "skill_metadata": {},
            "preferences": {
                "theme": "system",
                "font_family": "system",
                "language": "en",
                "auto_sync": True,
                "sync_on_save": True,
                "default_editor": "builtin",
                "tab_size": 2,
                "show_sync_notifications": True,
                "remove_links_when_disabling_tool": False,
                "skill_usage_monitor": True,
                "risk_scan_mode": "off",
            },
            "marketplace_favorites": {},
            "marketplace_sources": [
                {
                    "id": "src_clawhub",
                    "name": "ClawHub",
                    "url": "https://clawhub.ai",
                    "source_type": "clawhub_api",
                    "enabled": True,
                    "builtin": True,
                }
            ],
            "projects": [],
            "active_project_id": None,
            "llm_provider": None,
            "initialized": False,
        }

    def _load_config(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        self.skills_path.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            config = self._default_config()
            _atomic_json(self.config_path, config)
            return config
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillsManagerError(f"Failed to parse config: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SkillsManagerError("config must be an object")
        defaults = self._default_config()
        config = {**defaults, **loaded}
        config["skills_dir"] = str(self.skills_path)
        config["tools"] = {**defaults["tools"], **(loaded.get("tools") or {})}
        config["custom_tools"] = loaded.get("custom_tools") or {}
        config["skill_metadata"] = loaded.get("skill_metadata") or {}
        config["preferences"] = {**defaults["preferences"], **(loaded.get("preferences") or {})}
        # The desktop loader persists migrations on read.  Do the same for the web adapter.
        if config != loaded:
            _atomic_json(self.config_path, config)
        return config

    def _public_config(self) -> dict[str, Any]:
        """Return the browser-safe config without provider credentials."""
        config = dict(self._load_config())
        # The Skills Manager UI never edits the shared provider credentials. Omitting
        # this field (rather than returning a mask) prevents a later save round-trip
        # from replacing a real key with the mask.
        config.pop("llm_provider", None)
        return config

    def _save_config(self, config: dict[str, Any]) -> None:
        config = dict(config)
        config["skills_dir"] = str(self.skills_path)
        self.skills_path.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.config_path, config)

    # -- tools --------------------------------------------------------------

    def _tool_config(self, config: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
        item = (config.get("tools") or {}).get(tool_id)
        if isinstance(item, dict):
            return item
        custom = (config.get("custom_tools") or {}).get(tool_id)
        if isinstance(custom, dict):
            config_path = _configured_path(custom.get("config_path"))
            return {
                "enabled": bool(custom.get("enabled", False)),
                "detected": config_path.exists() if config_path is not None else False,
                "skills_path": custom.get("skills_path") if isinstance(custom.get("skills_path"), str) else "",
                "config_path": custom.get("config_path") if isinstance(custom.get("config_path"), str) else "",
            }
        return None

    def _detect_builtin(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        home = Path.home()
        result: list[dict[str, Any]] = []
        for tool_id, name, config_dir, alternatives, cli in _TOOL_DEFINITIONS:
            saved = (config.get("tools") or {}).get(tool_id)
            saved_config_path = _configured_path(saved.get("config_path")) if isinstance(saved, dict) else None
            if saved_config_path is not None:
                config_path = saved_config_path
                skills_path = _configured_path(saved.get("skills_path")) or (config_path / "skills")
            else:
                config_path = home / config_dir
                for alternative in alternatives:
                    candidate = home / alternative
                    if not config_path.exists() and candidate.exists():
                        config_path = candidate
                        break
                skills_path = config_path / "skills"
            detected = config_path.exists()
            item = {
                "id": tool_id,
                "name": name,
                "detected": detected,
                "cli_available": shutil.which(cli) is not None,
                "config": {
                    "enabled": bool(saved.get("enabled", detected)) if isinstance(saved, dict) else detected,
                    "detected": detected,
                    "skills_path": str(skills_path),
                    "config_path": str(config_path),
                },
                "source": "builtin",
                "icon_path": None,
            }
            result.append(item)
            config.setdefault("tools", {})[tool_id] = item["config"]
        return result

    def detect_tools(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        del refresh  # detection is cheap and intentionally reflects current filesystem state
        config = self._load_config()
        result = self._detect_builtin(config)
        for tool_id, custom in sorted((config.get("custom_tools") or {}).items()):
            if not isinstance(custom, dict):
                continue
            config_path = _configured_path(custom.get("config_path"))
            skills_path = _configured_path(custom.get("skills_path"))
            result.append(
                {
                    "id": tool_id,
                    "name": str(custom.get("name") or tool_id),
                    "detected": config_path.exists() if config_path is not None else False,
                    "cli_available": False,
                    "config": {
                        "enabled": bool(custom.get("enabled", False)),
                        "detected": config_path.exists() if config_path is not None else False,
                        "skills_path": str(skills_path) if skills_path is not None else "",
                        "config_path": str(config_path) if config_path is not None else "",
                    },
                    "source": "custom",
                    "icon_path": custom.get("icon_path"),
                }
            )
        self._save_config(config)
        return result

    # -- skill scanning -----------------------------------------------------

    @staticmethod
    def _parse_scalar(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    def _metadata_for(self, directory: Path) -> tuple[str, str | None, str, str]:
        name = directory.name
        description: str | None = None
        version = "1.0"
        source = "local"
        meta_json = directory / "meta.json"
        if meta_json.is_file() and self._path_confined_to(meta_json, directory):
            try:
                meta = json.loads(meta_json.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    name = str(meta.get("name") or name)
                    description = meta.get("description")
                    version = str(meta.get("version") or version)
                    source = str(meta.get("source") or source)
            except (OSError, json.JSONDecodeError):
                pass
        skill_file = directory / "SKILL.md"
        if not skill_file.exists():
            skill_file = directory / "skill.md"
        if skill_file.is_file() and self._path_confined_to(skill_file, directory):
            try:
                content = skill_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            if content.startswith("---"):
                marker = content.find("\n---", 3)
                if marker >= 0:
                    for line in content[4:marker].splitlines():
                        key, separator, raw = line.partition(":")
                        if not separator:
                            continue
                        if key.strip() == "name":
                            name = self._parse_scalar(raw) or name
                        elif key.strip() == "description":
                            description = self._parse_scalar(raw) or description
                        elif key.strip() == "version":
                            version = self._parse_scalar(raw) or version
                        elif key.strip() == "source":
                            source = self._parse_scalar(raw) or source
        return name, description, version, source

    @staticmethod
    def _is_skill_dir(path: Path) -> bool:
        return (path / "SKILL.md").is_file() or (path / "skill.md").is_file() or (path / "meta.json").is_file()

    def _skill_enabled(self, skill_path: Path, skill_id: str, config: dict[str, Any]) -> dict[str, bool]:
        return self._skill_state(skill_path, skill_id, config)[0]

    @staticmethod
    def _resolved_path(path: Path) -> Path:
        try:
            return path.expanduser().resolve(strict=False)
        except OSError:
            return Path(os.path.abspath(os.path.normpath(str(path.expanduser()))))

    @classmethod
    def _same_path(cls, left: Path, right: Path) -> bool:
        return cls._resolved_path(left) == cls._resolved_path(right)

    @classmethod
    def _path_is_within(cls, path: Path, root: Path) -> bool:
        try:
            cls._resolved_path(path).relative_to(cls._resolved_path(root))
            return True
        except ValueError:
            return False

    @staticmethod
    def _lexical_path(path: Path) -> Path:
        return Path(os.path.abspath(os.path.normpath(str(path.expanduser()))))

    @classmethod
    def _lexical_path_is_within(cls, path: Path, root: Path) -> bool:
        try:
            cls._lexical_path(path).relative_to(cls._lexical_path(root))
            return True
        except ValueError:
            return False

    @staticmethod
    def _raw_path_is_within(path: Path, root: Path) -> bool:
        """Keep the user-provided prefix so ``root/../outside`` cannot evade a guard."""
        candidate = str(path.expanduser())
        root_text = str(root.expanduser())
        if not Path(candidate).is_absolute():
            candidate = str(Path.cwd() / candidate)
        if not Path(root_text).is_absolute():
            root_text = str(Path.cwd() / root_text)
        candidate = os.path.normcase(candidate)
        root_text = os.path.normcase(root_text).rstrip(os.sep)
        return candidate == root_text or candidate.startswith(root_text + os.sep)

    @classmethod
    def _external_instance_id(cls, path: Path, skill_id: str) -> str:
        body_key = str(cls._resolved_path(path)).encode("utf-8", errors="surrogateescape")
        digest = hashlib.sha256(body_key).hexdigest()[:16]
        return f"external:{digest}:{skill_id}"

    def _skill_state(
        self, skill_path: Path, skill_id: str, config: dict[str, Any]
    ) -> tuple[dict[str, bool], dict[str, bool], dict[str, str]]:
        """Return observed tool state and the operations that are safe to expose.

        A real directory under a tool root is that tool's Skill Body, not a projection
        that the manager may remove. Only a symlink projection (or an absent target)
        can be changed by the enable/disable command.
        """
        enabled: dict[str, bool] = {}
        toggle_allowed: dict[str, bool] = {}
        link_status: dict[str, str] = {}
        for tool in self.detect_tools():
            tool_id = str(tool["id"])
            tool_config = tool.get("config") or {}
            raw_skills_path = tool_config.get("skills_path")
            if not isinstance(raw_skills_path, str) or not raw_skills_path.strip():
                enabled[tool_id] = False
                toggle_allowed[tool_id] = False
                link_status[tool_id] = "missing"
                continue
            skills_root = Path(raw_skills_path).expanduser()
            target = skills_root / skill_id
            value = False
            allowed = True
            status = "missing"
            try:
                if target.is_symlink():
                    try:
                        resolved_target = target.resolve(strict=True)
                    except OSError:
                        status = "broken"
                    else:
                        value = self._same_path(resolved_target, skill_path)
                        status = "linked" if value else "wrong_target"
                elif target.exists():
                    value = True
                    if self._same_path(target, skill_path):
                        status = "linked"
                        allowed = False
                    else:
                        status = "unmanaged"
                        allowed = False
            except OSError:
                value = target.exists()
                status = "unmanaged" if value else "missing"
                allowed = not value
            enabled[tool_id] = value
            toggle_allowed[tool_id] = allowed
            link_status[tool_id] = status
        return enabled, toggle_allowed, link_status

    def _scan_root(
        self,
        root: Path,
        config: dict[str, Any],
        *,
        scope: str = "global",
        project_id: str | None = None,
        project_name: str | None = None,
        read_only: bool = False,
        source_tool_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not root.is_dir():
            return []
        found: list[dict[str, Any]] = []
        # Carry symlink provenance through the traversal. A Skill can be nested
        # below a hub entry that is itself a symlink; checking only the final
        # directory would incorrectly classify that external body as editable.
        stack: list[tuple[Path, int, bool]] = [(root, 0, False)]
        seen_paths: set[str] = set()
        while stack:
            directory, depth, escaped = stack.pop()
            if depth >= 5:
                continue
            try:
                children = sorted((p for p in directory.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
            except OSError:
                continue
            for child in children:
                if child.name.startswith("."):
                    continue
                if self._is_skill_dir(child):
                    skill_id = child.name
                    body_key = str(self._resolved_path(child))
                    if body_key in seen_paths:
                        continue
                    seen_paths.add(body_key)
                    name, description, version, source = self._metadata_for(child)
                    normalized_source = "imported" if source in {"imported", "marketplace", "vault"} else "local"
                    candidate_read_only = read_only or escaped
                    if not candidate_read_only and child.is_symlink():
                        # A hub entry that points outside the hub is an external
                        # body, even though the link itself lives under skills/.
                        candidate_read_only = not self._path_is_within(child, root)
                    if scope == "project":
                        instance_id = f"project:{project_id}:{skill_id}"
                    elif candidate_read_only:
                        instance_id = self._external_instance_id(child, skill_id)
                    else:
                        instance_id = f"global:{skill_id}"
                    enabled, toggle_allowed, link_status = self._skill_state(child, skill_id, config)
                    found.append(
                        {
                            "id": skill_id,
                            "instance_id": instance_id,
                            "scope": scope,
                            "project_id": project_id,
                            "project_name": project_name,
                            "name": name,
                            "description": description,
                            "version": version,
                            "source": normalized_source,
                            "enabled": enabled,
                            "toggle_allowed": toggle_allowed,
                            "link_status": link_status,
                            "package_meta": None,
                            # External inventory records point at the resolved body,
                            # never at a tool-root symlink that could be mistaken for
                            # the body itself by a later mutation command.
                            "path": str(self._resolved_path(child) if candidate_read_only else child),
                            "read_only": candidate_read_only,
                            "source_tool_id": source_tool_id,
                            "source_root": str(root),
                            "source_is_projection": child.is_symlink() or escaped,
                            "can_edit": not candidate_read_only,
                            "can_delete": not candidate_read_only,
                        }
                    )
                else:
                    child_escaped = escaped or not self._path_is_within(child, root)
                    stack.append((child, depth + 1, child_escaped))
        found.sort(key=lambda item: (str(item.get("instance_id")), str(item.get("path"))))
        return found

    def _inventory_roots(
        self,
        config: dict[str, Any],
        *,
        include_hub: bool,
        include_project: bool,
        include_tools: bool,
    ) -> list[dict[str, Any]]:
        roots: list[dict[str, Any]] = []
        if include_hub:
            roots.append(
                {
                    "path": Path(str(config["skills_dir"])),
                    "scope": "global",
                    "project_id": None,
                    "project_name": None,
                    "read_only": False,
                    "source_tool_id": None,
                }
            )
        if include_project:
            active_id = config.get("active_project_id")
            for project in config.get("projects") or []:
                if not isinstance(project, dict) or project.get("id") != active_id:
                    continue
                raw_project_skills_path = project.get("skills_dir")
                if (
                    not isinstance(raw_project_skills_path, str)
                    or not raw_project_skills_path.strip()
                ):
                    break
                roots.append(
                    {
                        "path": Path(raw_project_skills_path).expanduser(),
                        "scope": "project",
                        "project_id": str(project.get("id")),
                        "project_name": str(project.get("name") or project.get("id")),
                        "read_only": False,
                        "source_tool_id": None,
                    }
                )
                break
        if include_tools:
            for tool in self.detect_tools():
                tool_id = str(tool.get("id") or "").strip()
                raw_path = (tool.get("config") or {}).get("skills_path")
                if not tool_id or not isinstance(raw_path, str) or not raw_path.strip():
                    continue
                path = Path(raw_path).expanduser()
                roots.append(
                    {
                        "path": path,
                        "scope": "global",
                        "project_id": None,
                        "project_name": None,
                        "read_only": True,
                        "source_tool_id": tool_id,
                    }
                )
        return roots

    def _list_skill_inventory(
        self,
        config: dict[str, Any],
        *,
        include_hub: bool,
        include_project: bool,
        include_tools: bool,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen_bodies: dict[str, int] = {}
        for root in self._inventory_roots(
            config,
            include_hub=include_hub,
            include_project=include_project,
            include_tools=include_tools,
        ):
            skills = self._scan_root(
                root["path"],
                config,
                scope=root["scope"],
                project_id=root["project_id"],
                project_name=root["project_name"],
                read_only=root["read_only"],
                source_tool_id=root["source_tool_id"],
            )
            for skill in skills:
                body_key = str(self._resolved_path(Path(str(skill["path"]))))
                existing_index = seen_bodies.get(body_key)
                if existing_index is not None:
                    existing = result[existing_index]
                    # Prefer a real body-hosting root over a symlink alias as the
                    # provenance shown for an external body. Preserve the first
                    # manager-owned hub/project record for compatibility.
                    if (
                        bool(existing.get("read_only"))
                        and not bool(skill.get("source_is_projection"))
                        and bool(existing.get("source_is_projection"))
                    ):
                        result[existing_index] = skill
                    continue
                seen_bodies[body_key] = len(result)
                result.append(skill)
        result.sort(
            key=lambda item: (
                bool(item.get("read_only")),
                str(item.get("scope")),
                str(item.get("instance_id")),
                str(item.get("path")),
            )
        )
        return result

    def list_skills(self, *, scan_all_tools: bool = False) -> list[dict[str, Any]]:
        config = self._load_config()
        if scan_all_tools:
            return self._list_skill_inventory(
                config,
                include_hub=False,
                include_project=False,
                include_tools=True,
            )
        return self._list_skill_inventory(
            config,
            include_hub=True,
            include_project=True,
            include_tools=True,
        )

    def _find_skill(self, instance_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        del config
        skills = self.list_skills()
        exact = [skill for skill in skills if skill.get("instance_id") == instance_id]
        if len(exact) == 1:
            return exact[0]
        matches = [skill for skill in skills if skill.get("id") == instance_id]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SkillsManagerError(
                f"Skill id is ambiguous; use instance_id: {instance_id}"
            )
        raise SkillsManagerError(f"Skill not found: {instance_id}")

    # -- filesystem/link operations ----------------------------------------

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)

    def _sync_skill(self, skill: dict[str, Any], tool_id: str, enabled: bool, config: dict[str, Any]) -> None:
        tool = next((item for item in self.detect_tools() if item["id"] == tool_id), None)
        if tool is None:
            raise SkillsManagerError(f"Tool not found: {tool_id}")
        tool_config = tool.get("config") or {}
        raw_skills_path = tool_config.get("skills_path")
        if not isinstance(raw_skills_path, str) or not raw_skills_path.strip():
            raise SkillsManagerError(f"Tool has no configured skills path: {tool_id}")
        skills_root = Path(raw_skills_path).expanduser()
        destination = skills_root / str(skill["id"])
        source = Path(str(skill["path"])).expanduser()
        if enabled:
            if not source.exists():
                raise SkillsManagerError("Skill source does not exist")
            skills_root.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                if self._same_path(destination, source):
                    return
                if not destination.is_symlink():
                    raise SkillsManagerError(
                        f"Skill target already contains a different body: {destination}"
                    )
                self._remove_path(destination)
            try:
                destination.symlink_to(source, target_is_directory=True)
            except OSError as exc:
                # A copied directory is a new Skill Body, not a Tool projection;
                # silently creating one would make later disable operations unable
                # to distinguish manager-owned content from an installer-owned body.
                raise SkillsManagerError(
                    f"Cannot create Skill projection for tool: {tool_id}"
                ) from exc
        elif destination.is_symlink():
            try:
                resolved_target = destination.resolve(strict=True)
            except OSError as exc:
                raise SkillsManagerError("Cannot disable a broken skill projection") from exc
            if not self._same_path(resolved_target, source):
                raise SkillsManagerError("Refusing to remove an unrelated skill projection")
            destination.unlink(missing_ok=True)
        elif destination.exists():
            if self._same_path(destination, source):
                raise SkillsManagerError("Cannot disable a Skill Body hosted by the tool")
            raise SkillsManagerError("Refusing to remove an unmanaged Skill Body")

    # -- command implementations ------------------------------------------

    def invoke(self, command: str, args: dict[str, Any] | None = None) -> Any:
        args = args if isinstance(args, dict) else {}
        handlers = {
            "get_config": lambda: self._public_config(),
            "get_home_directory": lambda: str(Path.home()),
            "save_config": lambda: self._command_save_config(args),
            "is_initialized": lambda: bool(self._load_config().get("initialized", False)),
            "mark_initialized": lambda: self._command_mark_initialized(),
            "detect_tools": lambda: self.detect_tools(),
            "refresh_tools": lambda: self.detect_tools(refresh=True),
            "set_tool_enabled": lambda: self._command_set_tool_enabled(args),
            "update_tool_paths": lambda: self._command_update_tool_paths(args),
            "create_custom_tool": lambda: self._command_create_custom_tool(args),
            "update_custom_tool": lambda: self._command_update_custom_tool(args),
            "delete_custom_tool": lambda: self._command_delete_custom_tool(args),
            "list_skills": lambda: self.list_skills(),
            "refresh_skills": lambda: self.list_skills(),
            "scan_existing_skills": lambda: self.list_skills(scan_all_tools=True),
            "import_skills_to_hub": lambda: self._command_import_to_hub(args),
            "create_skill": lambda: self._command_create_skill(args),
            "delete_skill": lambda: self._command_delete_skill(args),
            "enable_skill": lambda: self._command_toggle_skill(args, True),
            "disable_skill": lambda: self._command_toggle_skill(args, False),
            "batch_set_skill_tools": lambda: self._command_batch_set(args),
            "toggle_skill_favorite": lambda: self._command_toggle_favorite(args),
            "read_directory_tree": lambda: self._command_read_directory_tree(args),
            "read_file": lambda: self._command_read_file(args),
            "write_file": lambda: self._write_file(args),
            "create_file": lambda: self._create_file(args),
            "create_directory": lambda: self._create_directory(args),
            "delete_path": lambda: self._delete_path(args),
            "rename_path": lambda: self._rename_path(args),
            "get_available_editors": lambda: self._available_editors(),
            "open_in_editor": lambda: self._open_in_editor(args),
            "check_sync_status": lambda: {"issues_count": 0},
            "fix_sync_issues": lambda: {"success": [], "failed": []},
            "get_skill_usage_stats": lambda: {},
            "clear_usage_stats": lambda: None,
            "get_usage_hook_status": lambda: False,
            "install_usage_hook": lambda: None,
            "uninstall_usage_hook": lambda: None,
            "scan_all_risks": lambda: self._scan_all_risks(),
            "get_risk_report": lambda: self._risk_report(args),
            "get_risk_reports_batch": lambda: self._risk_reports_batch(args),
            "clear_risk_cache_command": lambda: None,
            "clear_translation_cache": lambda: None,
            "get_cached_text_translation": lambda: None,
            "get_cached_skill_translations": lambda: [],
            "get_cached_marketplace_translations": lambda: [],
            "is_llm_provider_configured": lambda: self._llm_configured(),
            "translate_skill": lambda: self._translate_skill(args),
            "translate_skill_files": lambda: self._translate_skill_files(args),
            "translate_skills_batch": lambda: self._translate_skills_batch(args),
            "translate_text_content": lambda: self._translate_text(args),
            "list_skill_packages": lambda: [],
            "remove_skill_package": lambda: None,
            "export_skills": lambda: self._export_skills(args),
            "preview_import_skills": lambda: self._preview_import(args),
            "import_skills": lambda: self._import_zip(args),
        }
        handler = handlers.get(command)
        if handler is None:
            raise SkillsManagerError(f"Unsupported Skills Manager command: {command}")
        return handler()

    def _command_save_config(self, args: dict[str, Any]) -> None:
        value = args.get("config", args)
        if not isinstance(value, dict):
            raise SkillsManagerError("config must be an object")
        current = self._load_config()
        merged = {**current, **value}
        merged["tools"] = {**current.get("tools", {}), **(value.get("tools") or {})}
        merged["custom_tools"] = value.get("custom_tools", current.get("custom_tools", {}))
        merged["skill_metadata"] = value.get("skill_metadata", current.get("skill_metadata", {}))
        self._save_config(merged)

    def _command_mark_initialized(self) -> None:
        config = self._load_config()
        config["initialized"] = True
        self._save_config(config)

    def _command_set_tool_enabled(self, args: dict[str, Any]) -> None:
        tool_id = str(_arg(args, "toolId", "tool_id", default=""))
        config = self._load_config()
        enabled = bool(_arg(args, "enabled", default=False))
        if tool_id in (config.get("tools") or {}):
            config["tools"][tool_id]["enabled"] = enabled
        elif tool_id in (config.get("custom_tools") or {}):
            config["custom_tools"][tool_id]["enabled"] = enabled
        else:
            raise SkillsManagerError(f"Tool not found: {tool_id}")
        self._save_config(config)

    def _command_update_tool_paths(self, args: dict[str, Any]) -> None:
        tool_id = str(_arg(args, "toolId", "tool_id", default=""))
        config = self._load_config()
        item = self._tool_config(config, tool_id)
        if item is None:
            raise SkillsManagerError(f"Tool not found: {tool_id}")
        config_path = _arg(args, "configPath", "config_path")
        skills_path = _arg(args, "skillsPath", "skills_path")
        if config_path is not None:
            item["config_path"] = str(config_path)
            configured = _configured_path(config_path)
            item["detected"] = configured is not None and configured.exists()
        if skills_path is not None:
            item["skills_path"] = str(skills_path)
        if tool_id in (config.get("tools") or {}):
            config["tools"][tool_id] = item
        else:
            config["custom_tools"][tool_id].update(item)
        self._save_config(config)

    def _command_create_custom_tool(self, args: dict[str, Any]) -> None:
        tool_id = str(_arg(args, "toolId", "tool_id", default="")).strip()
        if not tool_id:
            raise SkillsManagerError("tool_id is required")
        config = self._load_config()
        config.setdefault("custom_tools", {})[tool_id] = {
            "name": str(_arg(args, "name", default=tool_id)),
            "config_path": str(_arg(args, "configPath", "config_path", default="")),
            "skills_path": str(_arg(args, "skillsPath", "skills_path", default="")),
            "enabled": bool(_arg(args, "enabled", default=False)),
            "icon_path": _arg(args, "iconPath", "icon_path"),
        }
        self._save_config(config)

    def _command_update_custom_tool(self, args: dict[str, Any]) -> None:
        tool_id = str(_arg(args, "toolId", "tool_id", default=""))
        config = self._load_config()
        if tool_id not in (config.get("custom_tools") or {}):
            raise SkillsManagerError(f"Custom tool not found: {tool_id}")
        current = config["custom_tools"][tool_id]
        for key, names in {
            "name": ("name",),
            "config_path": ("configPath", "config_path"),
            "skills_path": ("skillsPath", "skills_path"),
            "icon_path": ("iconPath", "icon_path"),
            "enabled": ("enabled",),
        }.items():
            value = _arg(args, *names)
            if value is not None:
                current[key] = value
        self._save_config(config)

    def _command_delete_custom_tool(self, args: dict[str, Any]) -> None:
        config = self._load_config()
        tool_id = str(_arg(args, "toolId", "tool_id", default=""))
        if (config.get("custom_tools") or {}).pop(tool_id, None) is None:
            raise SkillsManagerError(f"Custom tool not found: {tool_id}")
        self._save_config(config)

    def _command_import_to_hub(self, args: dict[str, Any]) -> None:
        paths = _arg(args, "skillPaths", "skill_paths", default=[])
        if not isinstance(paths, list):
            raise SkillsManagerError("skill_paths must be an array")
        self.skills_path.mkdir(parents=True, exist_ok=True)
        for raw in paths:
            source = _as_path(raw, field="skill_path")
            self._assert_path_readable(source)
            if not source.is_dir() or not self._is_skill_dir(source):
                raise SkillsManagerError("skill_path must be a Skill directory")
            skill_id = source.name
            # Path.name preserves `.`/`..` instead of normalising them. Reject those
            # aliases before joining with the hub, otherwise `skills/good/..` would
            # resolve to the manager root and the replacement below could delete it.
            if not skill_id or skill_id in {".", ".."} or "/" in skill_id or "\\" in skill_id:
                raise SkillsManagerError("invalid skill path")
            destination = self.skills_path / skill_id
            if not self._lexical_path_is_within(destination, self.skills_path):
                raise SkillsManagerError("skill destination is outside the Skills Manager hub")
            if destination.exists() or destination.is_symlink():
                self._remove_path(destination)
            self._copy_skill_body(source, destination)

    def _command_create_skill(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(_arg(args, "name", default="")).strip()
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise SkillsManagerError("invalid skill name")
        config = self._load_config()
        destination = self.skills_path / name
        if destination.exists():
            raise SkillsManagerError(f"Skill already exists: {name}")
        destination.mkdir(parents=True)
        description = str(_arg(args, "description", default="") or "")
        (destination / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\nversion: 1.0\n---\n\n# {name}\n",
            encoding="utf-8",
        )
        return next(item for item in self._scan_root(self.skills_path, config) if item["id"] == name)

    def _command_delete_skill(self, args: dict[str, Any]) -> None:
        skill = self._find_skill(str(_arg(args, "instanceId", "instance_id", default="")))
        if bool(skill.get("read_only")) or skill.get("can_delete") is False:
            raise SkillsManagerError("External Skill Bodies cannot be deleted by Skills Manager")
        path = Path(str(skill["path"])).expanduser()
        self._remove_path(path)

    def _command_toggle_skill(self, args: dict[str, Any], enabled: bool) -> None:
        instance_id = str(_arg(args, "instanceId", "instance_id", default=""))
        tool_id = str(_arg(args, "toolId", "tool_id", default=""))
        config = self._load_config()
        skill = self._find_skill(instance_id, config)
        toggle_allowed = (skill.get("toggle_allowed") or {}).get(tool_id, True)
        if not toggle_allowed:
            raise SkillsManagerError(
                "This Tool hosts the Skill Body directly; Skills Manager will not remove it"
            )
        self._sync_skill(skill, tool_id, enabled, config)

    def _command_batch_set(self, args: dict[str, Any]) -> dict[str, Any]:
        request = args.get("request") if isinstance(args.get("request"), dict) else args
        targets = request.get("targets") or []
        tool_ids = request.get("tool_ids", request.get("toolIds")) or []
        action = request.get("action", "enable")
        attempted = applied = failed = 0
        failures: list[dict[str, Any]] = []
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_id = str(target.get("id", ""))
            if target.get("kind") == "group":
                continue
            for tool_id in tool_ids:
                attempted += 1
                try:
                    self._command_toggle_skill(
                        {"instanceId": target_id, "toolId": str(tool_id)}, action == "enable"
                    )
                    applied += 1
                except Exception as exc:  # report per-item failures like the desktop command
                    failed += 1
                    failures.append({"target_kind": target.get("kind", "skill"), "target_id": target_id, "tool_id": str(tool_id), "message": str(exc)})
        return {
            "requested_target_count": len(targets),
            "requested_tool_count": len(tool_ids),
            "resolved_skill_count": len(targets),
            "attempted_operation_count": attempted,
            "applied_count": applied,
            "skipped_count": max(0, len(targets) * len(tool_ids) - attempted),
            "failed_count": failed,
            "failures": failures,
        }

    def _command_toggle_favorite(self, args: dict[str, Any]) -> None:
        config = self._load_config()
        instance_id = str(_arg(args, "instanceId", "instance_id", default=""))
        favorited = bool(_arg(args, "favorited", default=False))
        metadata = config.setdefault("skill_metadata", {})
        item = metadata.setdefault(instance_id, {"tags": []})
        if favorited:
            item["favorited_at"] = _now()
        else:
            item.pop("favorited_at", None)
            if not item.get("tags"):
                metadata.pop(instance_id, None)
        self._save_config(config)

    # -- files/editors ------------------------------------------------------

    def _safe_skill_files(self, root: Path):
        """Yield only regular files physically contained by a Skill body."""
        if not root.is_dir():
            return
        try:
            paths = root.rglob("*")
            for path in paths:
                if path.is_symlink() or not path.is_file():
                    continue
                if self._path_confined_to(path, root):
                    yield path
        except OSError:
            return

    def _copy_skill_body(self, source: Path, destination: Path) -> None:
        """Copy a Skill body without dereferencing nested symlinks."""
        destination.mkdir(parents=True, exist_ok=True)
        try:
            for entry in source.rglob("*"):
                if entry.is_symlink() or not self._path_confined_to(entry, source):
                    continue
                target = destination / entry.relative_to(source)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif entry.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(entry, target)
        except OSError as exc:
            raise SkillsManagerError(f"Failed to copy Skill body: {exc}") from exc

    @classmethod
    def _path_confined_to(cls, path: Path, root: Path) -> bool:
        """Require both lexical and resolved containment for a web path."""
        return cls._lexical_path_is_within(path, root) and cls._path_is_within(path, root)

    def _is_agents_md_file(self, path: Path) -> bool:
        return (
            path.name == "AGENTS.md"
            and self._lexical_path(path).parent == self._lexical_path(self.agents_md_root)
            and self._path_confined_to(path, self.agents_md_root)
        )

    def _is_agents_md_root(self, path: Path) -> bool:
        return self._same_path(path, self.agents_md_root)

    def _read_scope_for(self, path: Path) -> Path | None:
        """Return the most specific Skill Manager-owned read scope for ``path``."""
        candidates: list[Path] = [self.skills_path, *self.workspace_roots]
        candidates.extend(
            Path(str(skill["path"])).expanduser()
            for skill in self.list_skills()
            if isinstance(skill.get("path"), str)
        )
        matches = [root for root in candidates if self._path_confined_to(path, root)]
        if self._is_agents_md_file(path) or self._is_agents_md_root(path):
            matches.append(self.agents_md_root)
        if not matches:
            return None
        return max(matches, key=lambda root: len(str(self._resolved_path(root))))

    def _assert_path_readable(self, path: Path) -> Path:
        scope = self._read_scope_for(path)
        if scope is None:
            raise SkillsManagerError("Path is outside the Skills Manager web read scope")
        return scope

    def _assert_web_staging_path(self, path: Path) -> None:
        if not any(
            self._path_confined_to(path, self.root / directory)
            for directory in (".web-imports", ".web-exports")
        ):
            raise SkillsManagerError("Path is outside the Skills Manager web staging scope")

    def is_web_staging_path(self, path: Path) -> bool:
        """Whether a file is a browser upload/export staging artifact."""
        return any(
            self._path_confined_to(path, self.root / directory)
            for directory in (".web-imports", ".web-exports")
        )

    def _command_read_directory_tree(self, args: dict[str, Any]) -> dict[str, Any]:
        path = _as_path(_arg(args, "path"), field="path")
        scope = self._assert_path_readable(path)
        return self._directory_tree(path, scope=scope)

    def _command_read_file(self, args: dict[str, Any]) -> str:
        path = _as_path(_arg(args, "path"), field="path")
        self._assert_path_readable(path)
        return self._read_file(path)

    def _assert_path_writable(self, path: Path) -> None:
        """Keep browser file mutations inside manager-owned Skill roots."""
        if self._is_agents_md_file(path):
            return
        config = self._load_config()
        writable_roots = [self.skills_path, *self.workspace_roots]
        writable_roots.extend(
            Path(str(item["path"])).expanduser()
            for item in self._inventory_roots(
                config,
                include_hub=False,
                include_project=True,
                include_tools=False,
            )
            if isinstance(item.get("path"), Path)
        )
        for skill in self.list_skills():
            skill_root = Path(str(skill["path"]))
            raw_inside = self._raw_path_is_within(path, skill_root)
            lexical_inside = self._lexical_path_is_within(path, skill_root)
            resolved_inside = self._path_is_within(path, skill_root)
            if skill.get("read_only") and (raw_inside or lexical_inside or resolved_inside):
                raise SkillsManagerError(
                    "External Skill Bodies are read-only in Skills Manager"
                )
            if not skill.get("read_only") and raw_inside and not resolved_inside:
                raise SkillsManagerError(
                    "Managed Skill paths cannot resolve outside the Skill Body"
                )
            if not skill.get("read_only"):
                writable_roots.append(skill_root)
        if not any(self._path_confined_to(path, root) for root in writable_roots):
            raise SkillsManagerError(
                "Path is outside the Skills Manager web write scope"
            )

    def _directory_tree(self, root: Path, *, scope: Path | None = None) -> dict[str, Any]:
        if not root.exists():
            raise SkillsManagerError(f"Path not found: {root}")
        scope = scope or self._assert_path_readable(root)

        def build(path: Path, depth: int = 0) -> dict[str, Any]:
            item: dict[str, Any] = {"name": path.name or str(path), "path": str(path), "is_dir": path.is_dir()}
            if path.is_dir() and depth < 20:
                try:
                    children = []
                    for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                        # A Skill may contain a symlink to an unrelated host path. It
                        # remains visible to the filesystem, but never to a browser tree.
                        if not self._path_confined_to(child, scope):
                            continue
                        if self._is_agents_md_root(scope) and child.name != "AGENTS.md":
                            continue
                        children.append(build(child, depth + 1))
                    item["children"] = children
                except OSError as exc:
                    raise SkillsManagerError(str(exc)) from exc
            return item
        return build(root)

    @staticmethod
    def _read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise SkillsManagerError(str(exc)) from exc

    def _write_file(self, args: dict[str, Any]) -> None:
        path = _as_path(_arg(args, "path"), field="path")
        self._assert_path_writable(path)
        content = _arg(args, "content", default="")
        if not isinstance(content, str):
            raise SkillsManagerError("content must be a string")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _create_file(self, args: dict[str, Any]) -> None:
        path = _as_path(_arg(args, "path"), field="path")
        self._assert_path_writable(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=False)

    def _create_directory(self, args: dict[str, Any]) -> None:
        path = _as_path(_arg(args, "path"), field="path")
        self._assert_path_writable(path)
        path.mkdir(parents=True, exist_ok=True)

    def _delete_path(self, args: dict[str, Any]) -> None:
        path = _as_path(_arg(args, "path"), field="path")
        self._assert_path_writable(path)
        if not path.exists() and not path.is_symlink():
            raise SkillsManagerError(f"Path not found: {path}")
        self._remove_path(path)

    def _rename_path(self, args: dict[str, Any]) -> None:
        old = _as_path(_arg(args, "oldPath", "old_path"), field="old_path")
        new = _as_path(_arg(args, "newPath", "new_path"), field="new_path")
        self._assert_path_writable(old)
        self._assert_path_writable(new)
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)

    @staticmethod
    def _available_editors() -> list[dict[str, Any]]:
        editors = (
            ("vscode", "Visual Studio Code", "code"),
            ("cursor", "Cursor", "cursor"),
            ("windsurf", "Windsurf", "windsurf"),
            ("zed", "Zed", "zed"),
            ("sublime", "Sublime Text", "subl"),
            ("pycharm", "PyCharm", "pycharm"),
            ("webstorm", "WebStorm", "webstorm"),
        )
        return [{"id": editor_id, "name": name, "command": command, "available": shutil.which(command) is not None, "icon": editor_id} for editor_id, name, command in editors]

    def _open_in_editor(self, args: dict[str, Any]) -> None:
        editor_id = str(_arg(args, "editorId", "editor_id", default=""))
        path = str(_arg(args, "path", default=""))
        self._assert_path_writable(Path(path))
        editor = next((item for item in self._available_editors() if item["id"] == editor_id), None)
        if editor is None or not editor["available"]:
            raise SkillsManagerError(f"Editor not available: {editor_id}")
        subprocess.Popen([str(editor["command"]), path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- risk/translation ---------------------------------------------------

    def _risk_report(self, args: dict[str, Any]) -> dict[str, Any]:
        skill = self._find_skill(str(_arg(args, "instanceId", "instance_id", default="")))
        mode = str((self._load_config().get("preferences") or {}).get("risk_scan_mode", "off"))
        findings: list[dict[str, Any]] = []
        if mode != "off":
            root = Path(str(skill["path"]))
            for file in self._safe_skill_files(root):
                try:
                    text = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                patterns = ((r"rm\s+-rf\s+[/~]", "destructive", "high", "Recursive deletion command"), (r"\bcurl\b[^\n|]*\|\s*(?:ba)?sh", "network", "high", "Piped remote script"), (r"\bsudo\b", "privilege", "medium", "Privilege escalation command"))
                for pattern, category, level, message in patterns:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        findings.append({"rule_id": f"web.{category}", "category": category, "level": level, "confidence": 0.85, "message": message, "evidence": match.group(0), "location": {"file": str(file.relative_to(root)), "line": text[:match.start()].count("\n") + 1}, "source": "rule"})
        level = "safe"
        for candidate in ("critical", "high", "medium", "low"):
            if any(item["level"] == candidate for item in findings):
                level = candidate
                break
        return {"instance_id": skill["instance_id"], "level": level, "findings": findings, "scanned_at": _now(), "scanner_version": "web-1", "mode": mode, "llm_reviewed": False}

    def _scan_all_risks(self) -> list[dict[str, Any]]:
        return [self._risk_report({"instanceId": skill["instance_id"]}) for skill in self.list_skills()]

    def _risk_reports_batch(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = _arg(args, "instanceIds", "instance_ids")
        reports = self._scan_all_risks() if not isinstance(ids, list) else [self._risk_report({"instanceId": item}) for item in ids]
        return {str(report["instance_id"]): report for report in reports}

    def _llm_configured(self) -> bool:
        provider = self._load_config().get("llm_provider")
        return isinstance(provider, dict) and bool(provider.get("base_url") and provider.get("api_key") and provider.get("model"))

    def _skill_content(self, skill: dict[str, Any]) -> str:
        root = Path(str(skill["path"]))
        for name in ("SKILL.md", "skill.md"):
            candidate = root / name
            if candidate.is_file() and self._path_confined_to(candidate, root):
                return self._read_file(candidate)
        return ""

    def _translation_output(self, *, name: str, description: str | None, content: str) -> dict[str, Any]:
        # The desktop command delegates to the configured provider.  Returning the original
        # content is a safe offline fallback and keeps the Web surface usable when no provider
        # is configured; a later provider adapter can replace this without changing the UI.
        return {"name": name, "description": description or "", "content_md": content, "cached": False}

    def _translate_skill(self, args: dict[str, Any]) -> dict[str, Any]:
        skill = self._find_skill(str(_arg(args, "instanceId", "instance_id", default="")))
        return self._translation_output(name=str(skill["name"]), description=skill.get("description"), content=self._skill_content(skill))

    def _translate_skill_files(self, args: dict[str, Any]) -> dict[str, Any]:
        skill = self._find_skill(str(_arg(args, "instanceId", "instance_id", default="")))
        root = Path(str(skill["path"]))
        files: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for path in self._safe_skill_files(root):
            if path.suffix.lower() not in _TEXT_EXTENSIONS:
                continue
            relative = str(path.relative_to(root))
            try:
                files.append({"path": relative, "translation": self._translation_output(name=str(skill["name"]), description=skill.get("description"), content=self._read_file(path))})
            except Exception as exc:
                failed.append({"path": relative, "reason": str(exc)})
        return {"files": files, "failed": failed}

    def _translate_skills_batch(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = _arg(args, "instanceIds", "instance_ids", default=[])
        succeeded: list[str] = []
        failed: list[dict[str, Any]] = []
        for instance_id in ids if isinstance(ids, list) else []:
            try:
                self._translate_skill({"instanceId": instance_id})
                succeeded.append(str(instance_id))
            except Exception as exc:
                failed.append({"instance_id": str(instance_id), "reason": str(exc)})
        return {"succeeded": succeeded, "failed": failed}

    def _translate_text(self, args: dict[str, Any]) -> dict[str, Any]:
        content = str(_arg(args, "content", default=""))
        return self._translation_output(name=str(_arg(args, "label", default="")), description="", content=content)

    # -- import/export ------------------------------------------------------

    def _export_skills(self, args: dict[str, Any]) -> int:
        output_path = _as_path(_arg(args, "outputPath", "output_path"), field="output_path")
        self._assert_web_staging_path(output_path)
        ids = _arg(args, "instanceIds", "instance_ids")
        # External tool roots are inventory sources, not manager-owned export
        # bodies. Keep the historical "export all" action scoped to the hub;
        # explicit instance IDs may still copy a read-only body out deliberately.
        selected = [skill for skill in self.list_skills() if not skill.get("read_only")]
        if isinstance(ids, list):
            selected = [
                skill
                for skill in self.list_skills()
                if skill["instance_id"] in ids or skill["id"] in ids
            ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        config = self._load_config()
        manifest = {
            "format_version": 1,
            "exported_at": _now(),
            "app_version": str(config.get("version", "2.1.7")),
            "skills": [],
        }
        for skill in selected:
            metadata = (config.get("skill_metadata") or {}).get(skill["instance_id"], {})
            manifest["skills"].append(
                {
                    "id": skill["id"],
                    "name": skill["name"],
                    "description": skill.get("description"),
                    "version": skill.get("version", "1.0"),
                    "folder": f"skills/{skill['id']}",
                    "enabled_tools": [tool_id for tool_id, is_enabled in (skill.get("enabled") or {}).items() if is_enabled],
                    "tags": metadata.get("tags", []) if isinstance(metadata, dict) else [],
                    "favorited_at": metadata.get("favorited_at") if isinstance(metadata, dict) else None,
                }
            )
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for skill in selected:
                root = Path(str(skill["path"]))
                for path in self._safe_skill_files(root):
                    archive.write(path, Path("skills") / skill["id"] / path.relative_to(root))
        return len(selected)

    def _preview_import(self, args: dict[str, Any]) -> dict[str, Any]:
        zip_path = _as_path(_arg(args, "zipPath", "zip_path"), field="zip_path")
        self._assert_web_staging_path(zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise SkillsManagerError("not a valid skills archive")
        with zipfile.ZipFile(zip_path) as archive:
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
                names = sorted({Path(name).parts[1] for name in archive.namelist() if len(Path(name).parts) > 1 and Path(name).parts[0] == "skills"})
                manifest = {
                    "format_version": 1,
                    "exported_at": _now(),
                    "app_version": "unknown",
                    "skills": [{"id": name, "name": name, "description": None, "version": "1.0", "folder": f"skills/{name}", "enabled_tools": [], "tags": [], "favorited_at": None} for name in names],
                }
        conflicts = []
        for item in manifest.get("skills", []):
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id", ""))
            local_path = self.skills_path / skill_id
            if skill_id and local_path.exists():
                conflicts.append({"skill_id": skill_id, "skill_name": str(item.get("name") or skill_id), "local_path": str(local_path)})
        return {"manifest": manifest, "conflicts": conflicts}

    def _import_zip(self, args: dict[str, Any]) -> dict[str, Any]:
        zip_path = _as_path(_arg(args, "zipPath", "zip_path"), field="zip_path")
        self._assert_web_staging_path(zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise SkillsManagerError("not a valid skills archive")
        preview = self._preview_import({"zipPath": str(zip_path)})
        resolutions = _arg(args, "resolutions", default=[])
        resolution_map = {
            str(item.get("skill_id")): str(item.get("strategy", "skip"))
            for item in resolutions
            if isinstance(item, dict)
        }
        conflicts = {item["skill_id"] for item in preview["conflicts"]}
        imported: list[dict[str, str]] = []
        skipped: list[str] = []
        overwritten: list[str] = []
        renamed: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        config = self._load_config()
        self.skills_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            for item in preview["manifest"].get("skills", []):
                if not isinstance(item, dict):
                    continue
                skill_id = str(item.get("id", ""))
                if not skill_id or "/" in skill_id or "\\" in skill_id or skill_id in {".", ".."}:
                    failed.append({"skill_id": skill_id, "message": "invalid skill id"})
                    continue
                strategy = resolution_map.get(skill_id, "skip") if skill_id in conflicts else "import"
                destination_id = skill_id
                destination = self.skills_path / destination_id
                if strategy == "skip" and skill_id in conflicts:
                    skipped.append(skill_id)
                    continue
                destination_exists = destination.exists() or destination.is_symlink()
                if destination.is_symlink() and strategy == "import":
                    failed.append(
                        {
                            "skill_id": skill_id,
                            "message": "skill destination is a symlink",
                        }
                    )
                    continue
                if strategy == "overwrite" and destination_exists:
                    self._remove_path(destination)
                    overwritten.append(skill_id)
                elif strategy == "rename" and destination_exists:
                    suffix = 1
                    while (self.skills_path / f"{skill_id}-{suffix}").exists():
                        suffix += 1
                    destination_id = f"{skill_id}-{suffix}"
                    destination = self.skills_path / destination_id
                    renamed.append({"original_id": skill_id, "new_id": destination_id, "name": str(item.get("name") or skill_id)})
                try:
                    prefix = f"skills/{skill_id}/"
                    for member in archive.namelist():
                        if not member.startswith(prefix):
                            continue
                        relative = Path(member[len(prefix):])
                        if (
                            relative.is_absolute()
                            or not relative.parts
                            or any(part in {"", ".", ".."} for part in relative.parts)
                        ):
                            continue
                        target = destination.joinpath(*relative.parts)
                        if not self._path_confined_to(target, destination):
                            raise SkillsManagerError("archive member escapes Skill destination")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if member.endswith("/"):
                            target.mkdir(parents=True, exist_ok=True)
                        else:
                            with archive.open(member) as source, target.open("wb") as output:
                                shutil.copyfileobj(source, output)
                    imported.append({"original_id": skill_id, "final_id": destination_id, "name": str(item.get("name") or skill_id)})
                    if item.get("tags") or item.get("favorited_at") is not None:
                        config.setdefault("skill_metadata", {})[f"global:{destination_id}"] = {"tags": item.get("tags", []), "favorited_at": item.get("favorited_at")}
                except (OSError, KeyError, ValueError) as exc:
                    failed.append({"skill_id": skill_id, "message": str(exc)})
        self._save_config(config)
        return {"imported": imported, "skipped": skipped, "overwritten": overwritten, "renamed": renamed, "failed": failed}

    # -- web file serving ---------------------------------------------------

    def file_path(self, raw_path: str) -> Path:
        path = _as_path(raw_path, field="path")
        if not path.is_file():
            raise SkillsManagerError("file not found")
        resolved = self._resolved_path(path)
        if any(
            self._path_confined_to(resolved, self.root / directory)
            for directory in (".web-imports", ".web-exports")
        ):
            return resolved

        # The only externally rooted files the browser surface needs are custom
        # tool icons.  Do not turn this endpoint into an arbitrary host-file
        # reader for paths supplied by a LAN browser.
        config = self._load_config()
        for custom in (config.get("custom_tools") or {}).values():
            if not isinstance(custom, dict):
                continue
            icon_path = custom.get("icon_path")
            if (
                isinstance(icon_path, str)
                and icon_path.strip()
                and self._same_path(resolved, Path(icon_path))
                and not self._path_is_within(resolved, self.root)
                and resolved.suffix.lower() in _IMAGE_EXTENSIONS
            ):
                return resolved
        raise SkillsManagerError("file is outside the Skills Manager web file scope")

    def upload_file(self, name: str, encoded: str) -> str:
        """Persist a browser-selected file so Tauri's path-based commands can consume it."""
        if not isinstance(encoded, str) or not encoded:
            raise SkillsManagerError("file data is required")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SkillsManagerError("invalid file data") from exc
        if len(content) > 64 * 1024 * 1024:
            raise SkillsManagerError("file is too large")
        safe_name = Path(str(name or "upload.bin")).name or "upload.bin"
        staging_root = self.root / ".web-imports"
        self._assert_web_staging_path(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)
        destination = staging_root / f"{time.time_ns()}-{safe_name}"
        self._assert_web_staging_path(destination)
        destination.write_bytes(content)
        return str(destination)

    def reserve_export(self, name: str) -> str:
        safe_name = Path(str(name or "skills-export.zip")).name or "skills-export.zip"
        if not safe_name.lower().endswith(".zip"):
            safe_name += ".zip"
        staging_root = self.root / ".web-exports"
        self._assert_web_staging_path(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)
        destination = staging_root / safe_name
        self._assert_web_staging_path(destination)
        if destination.exists():
            destination = destination.with_name(f"{destination.stem}-{time.time_ns()}{destination.suffix}")
            self._assert_web_staging_path(destination)
        return str(destination)
