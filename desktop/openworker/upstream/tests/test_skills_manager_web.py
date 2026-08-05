from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app


def _invoke(client: TestClient, command: str, args: dict | None = None):
    response = client.post(
        "/v1/skills-manager/invoke",
        json={"command": command, "args": args or {}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_web_skills_manager_preserves_tauri_command_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    assert _invoke(client, "is_initialized") is False
    config = _invoke(client, "get_config")
    assert config["skills_dir"].endswith("skills")
    assert "codex" in config["tools"]

    skill = _invoke(
        client,
        "create_skill",
        {"name": "web-adapter", "description": "Web command adapter"},
    )
    assert skill["instance_id"] == "global:web-adapter"
    assert _invoke(client, "list_skills")[0]["name"] == "web-adapter"

    _invoke(client, "mark_initialized")
    assert _invoke(client, "is_initialized") is True


def test_web_skills_manager_file_commands_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    file_path = tmp_path / "skills-manager" / "skills" / "web-roundtrip" / "notes.md"

    _invoke(client, "create_directory", {"path": str(file_path.parent)})
    _invoke(client, "create_file", {"path": str(file_path)})
    _invoke(client, "write_file", {"path": str(file_path), "content": "hello"})
    assert _invoke(client, "read_file", {"path": str(file_path)}) == "hello"
    tree = _invoke(client, "read_directory_tree", {"path": str(file_path.parent)})
    assert tree["children"][0]["name"] == "notes.md"


def test_web_skills_manager_browser_upload_and_export_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    _invoke(client, "create_skill", {"name": "browser-roundtrip", "description": "export me"})
    reserved = client.post(
        "/v1/skills-manager/reserve-export", json={"name": "skills-export.zip"}
    )
    assert reserved.status_code == 200, reserved.text
    export_path = reserved.json()["path"]

    assert _invoke(client, "export_skills", {"outputPath": export_path}) == 1
    downloaded = client.get("/v1/skills-manager/file", params={"path": export_path})
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.startswith(b"PK")

    uploaded = client.post(
        "/v1/skills-manager/upload",
        json={
            "name": "skills-export.zip",
            "data": base64.b64encode(downloaded.content).decode("ascii"),
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    uploaded_path = uploaded.json()["path"]
    uploaded_download = client.get(
        "/v1/skills-manager/file", params={"path": uploaded_path}
    )
    assert uploaded_download.status_code == 200, uploaded_download.text
    assert uploaded_download.content == downloaded.content


def test_web_skills_manager_staging_files_are_downloads_not_inline_documents(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    uploaded = client.post(
        "/v1/skills-manager/upload",
        json={
            "name": "payload.html",
            "data": base64.b64encode(b"<script>window.pwned = true</script>").decode("ascii"),
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    response = client.get("/v1/skills-manager/file", params={"path": uploaded.json()["path"]})

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-type"] == "application/octet-stream"


def test_web_skills_manager_get_config_omits_provider_secret_and_preserves_it_on_save(
    tmp_path, monkeypatch
):
    manager_root = tmp_path / "skills-manager"
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    _invoke(
        client,
        "save_config",
        {
            "config": {
                "llm_provider": {
                    "base_url": "https://provider.invalid/v1",
                    "api_key": "SECRET123",
                    "model": "fixture-model",
                }
            }
        },
    )
    public_config = _invoke(client, "get_config")
    assert "llm_provider" not in public_config

    public_config["preferences"]["theme"] = "dark"
    _invoke(client, "save_config", {"config": public_config})
    persisted = json.loads((manager_root / "config.json").read_text(encoding="utf-8"))
    assert persisted["llm_provider"]["api_key"] == "SECRET123"


def test_web_skills_manager_import_to_hub_rejects_parent_alias_without_deleting_root(
    tmp_path, monkeypatch
):
    manager_root = tmp_path / "skills-manager"
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(client, "get_config")
    config_before = (manager_root / "config.json").read_text(encoding="utf-8")

    source_alias = manager_root / "skills" / "placeholder" / ".."
    response = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "import_skills_to_hub",
            "args": {"skillPaths": [str(source_alias)]},
        },
    )

    assert response.status_code == 400
    assert (manager_root / "config.json").read_text(encoding="utf-8") == config_before
    assert (manager_root / "skills").is_dir()


def test_web_skills_manager_import_rejects_absolute_archive_member(tmp_path, monkeypatch):
    manager_root = tmp_path / "skills-manager"
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    outside = tmp_path / "zip-slip.txt"
    archive_path = manager_root / ".web-imports" / "malicious.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "skills": [
                        {
                            "id": "malicious",
                            "name": "malicious",
                            "folder": "skills/malicious",
                        }
                    ]
                }
            ),
        )
        archive.writestr(f"skills/malicious/{outside.as_posix()}", "PWNED")

    result = _invoke(client, "import_skills", {"zipPath": str(archive_path)})

    assert not outside.exists()
    assert result["imported"] == [{"original_id": "malicious", "final_id": "malicious", "name": "malicious"}]
    assert not (manager_root / "skills" / "malicious" / outside.name).exists()


def test_web_skills_manager_file_endpoint_has_a_scoped_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    secret = tmp_path / "secret.txt"
    secret.write_text("not for the browser", encoding="utf-8")

    denied = client.get("/v1/skills-manager/file", params={"path": str(secret)})
    assert denied.status_code == 404

    tool_root = tmp_path / "tool"
    tool_skills = tool_root / "skills"
    tool_root.mkdir(parents=True)
    icon = tmp_path / "tool-icon.svg"
    icon.write_text("<svg />", encoding="utf-8")
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_root),
            "skillsPath": str(tool_skills),
            "iconPath": str(icon),
            "enabled": False,
        },
    )
    allowed = client.get("/v1/skills-manager/file", params={"path": str(icon)})
    assert allowed.status_code == 200
    assert allowed.content == b"<svg />"

    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "secret-icon-tool",
            "name": "Secret Icon Tool",
            "configPath": str(tool_root),
            "skillsPath": str(tool_skills),
            "iconPath": "/etc/passwd",
            "enabled": False,
        },
    )
    denied_icon = client.get(
        "/v1/skills-manager/file", params={"path": "/etc/passwd"}
    )
    assert denied_icon.status_code == 404


def test_web_skills_manager_file_endpoint_does_not_read_arbitrary_host_files(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    outside = tmp_path / "outside.txt"
    outside.write_text("must stay private", encoding="utf-8")
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    response = client.get("/v1/skills-manager/file", params={"path": str(outside)})

    assert response.status_code == 404
    assert response.content != b"must stay private"


def test_web_skills_manager_command_file_access_is_scoped(tmp_path, monkeypatch):
    manager_root = tmp_path / "skills-manager"
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    outside = tmp_path / "outside.txt"
    outside.write_text("must stay private", encoding="utf-8")

    for command, args in (
        ("read_file", {"path": str(outside)}),
        ("read_directory_tree", {"path": str(tmp_path)}),
        ("write_file", {"path": str(outside), "content": "mutate"}),
        ("create_file", {"path": str(tmp_path / "created.txt")}),
        ("create_directory", {"path": str(tmp_path / "created-dir")}),
        ("delete_path", {"path": str(outside)}),
    ):
        response = client.post(
            "/v1/skills-manager/invoke",
            json={"command": command, "args": args},
        )
        assert response.status_code == 400, (command, response.text)

    assert outside.read_text(encoding="utf-8") == "must stay private"
    assert not (tmp_path / "created.txt").exists()
    assert not (tmp_path / "created-dir").exists()


def test_web_skills_manager_allows_the_explicit_workspace_editor_scope(
    tmp_path, monkeypatch
):
    manager_root = tmp_path / "skills-manager"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(
        create_app(
            SessionManager(
                workspace=workspace,
                data_dir=tmp_path / "coworker",
            )
        )
    )
    file_path = workspace / "AGENTS.md"
    file_path.write_text("# workspace\n", encoding="utf-8")

    assert _invoke(client, "get_home_directory") == str(Path.home())
    assert _invoke(client, "read_file", {"path": str(file_path)}) == "# workspace\n"
    _invoke(client, "write_file", {"path": str(file_path), "content": "# edited\n"})
    assert file_path.read_text(encoding="utf-8") == "# edited\n"


def test_web_skills_manager_global_agents_scope_exposes_only_agents_md(
    tmp_path, monkeypatch
):
    manager_root = tmp_path / "skills-manager"
    home = tmp_path / "home"
    agents_root = home / ".codex"
    agents_root.mkdir(parents=True)
    agents_file = agents_root / "AGENTS.md"
    agents_file.write_text("# global\n", encoding="utf-8")
    secret = agents_root / "auth.json"
    secret.write_text('{"token":"private"}', encoding="utf-8")
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    monkeypatch.setenv("HOME", str(home))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    assert _invoke(client, "read_file", {"path": str(agents_file)}) == "# global\n"
    tree = _invoke(client, "read_directory_tree", {"path": str(agents_root)})
    assert [item["name"] for item in tree["children"]] == ["AGENTS.md"]
    denied = client.post(
        "/v1/skills-manager/invoke",
        json={"command": "read_file", "args": {"path": str(secret)}},
    )
    assert denied.status_code == 400


def test_web_skills_manager_file_endpoint_cannot_read_manager_config(tmp_path, monkeypatch):
    manager_root = tmp_path / "skills-manager"
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(manager_root))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    _invoke(client, "get_config")
    response = client.get(
        "/v1/skills-manager/file",
        params={"path": str(manager_root / "config.json")},
    )

    assert response.status_code == 404


def test_web_skills_manager_lists_skill_from_configured_tool_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tool_config_path = tmp_path / "tool" 
    tool_skills_path = tool_config_path / "skills"
    external_skill = tool_skills_path / "external-skill"
    external_skill.mkdir(parents=True)
    (external_skill / "SKILL.md").write_text(
        "---\nname: External Skill\ndescription: discovered outside the hub\n---\n",
        encoding="utf-8",
    )
    tool_config_path.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_config_path),
            "skillsPath": str(tool_skills_path),
            "enabled": True,
        },
    )

    skills = _invoke(client, "list_skills")

    assert [skill["id"] for skill in skills] == ["external-skill"]
    assert skills[0]["path"] == str(external_skill)


def test_web_skills_manager_external_skill_cannot_be_deleted_or_body_host_disabled(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tool_config_path = tmp_path / "tool"
    tool_skills_path = tool_config_path / "skills"
    external_skill = tool_skills_path / "external-skill"
    external_skill.mkdir(parents=True)
    (external_skill / "SKILL.md").write_text("# external\n", encoding="utf-8")
    tool_config_path.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_config_path),
            "skillsPath": str(tool_skills_path),
            "enabled": True,
        },
    )
    skill = _invoke(client, "list_skills")[0]

    delete_response = client.post(
        "/v1/skills-manager/invoke",
        json={"command": "delete_skill", "args": {"instanceId": skill["instance_id"]}},
    )
    assert delete_response.status_code == 400
    assert external_skill.is_dir()

    disable_response = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "disable_skill",
            "args": {"instanceId": skill["instance_id"], "toolId": "fixture-tool"},
        },
    )
    assert disable_response.status_code == 400
    assert external_skill.is_dir()

    batch = _invoke(
        client,
        "batch_set_skill_tools",
        {
            "request": {
                "targets": [{"kind": "skill", "id": skill["instance_id"]}],
                "tool_ids": ["fixture-tool"],
                "action": "disable",
            }
        },
    )
    assert batch["failed_count"] == 1
    assert external_skill.is_dir()


def test_web_skills_manager_deduplicates_same_external_skill_body(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    shared_config_path = tmp_path / "tool"
    shared_skills_path = shared_config_path / "skills"
    shared_skill = shared_skills_path / "shared-skill"
    shared_skill.mkdir(parents=True)
    (shared_skill / "SKILL.md").write_text("# shared\n", encoding="utf-8")
    shared_config_path.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    for tool_id in ("fixture-a", "fixture-b"):
        _invoke(
            client,
            "create_custom_tool",
            {
                "toolId": tool_id,
                "name": tool_id,
                "configPath": str(shared_config_path),
                "skillsPath": str(shared_skills_path),
                "enabled": True,
            },
        )

    skills = _invoke(client, "list_skills")

    assert [skill["id"] for skill in skills] == ["shared-skill"]


def test_web_skills_manager_keeps_same_id_different_external_bodies_distinct(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    roots = []
    for tool_id, label in (("fixture-a", "A"), ("fixture-b", "B")):
        config_path = tmp_path / tool_id
        skill_path = config_path / "skills" / "same-name"
        skill_path.mkdir(parents=True)
        (skill_path / "SKILL.md").write_text(f"# {label}\n", encoding="utf-8")
        config_path.mkdir(parents=True, exist_ok=True)
        roots.append((tool_id, config_path, config_path / "skills"))

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    for tool_id, config_path, skills_path in roots:
        _invoke(
            client,
            "create_custom_tool",
            {
                "toolId": tool_id,
                "name": tool_id,
                "configPath": str(config_path),
                "skillsPath": str(skills_path),
                "enabled": True,
            },
        )

    skills = _invoke(client, "list_skills")

    assert [skill["id"] for skill in skills] == ["same-name", "same-name"]
    assert len({skill["instance_id"] for skill in skills}) == 2
    assert len({skill["path"] for skill in skills}) == 2
    ambiguous = client.post(
        "/v1/skills-manager/invoke",
        json={"command": "delete_skill", "args": {"instanceId": "same-name"}},
    )
    assert ambiguous.status_code == 400
    for _, _, skills_path in roots:
        assert (skills_path / "same-name").is_dir()


def test_web_skills_manager_external_projection_never_deletes_body(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    body_root = tmp_path / "body-tool"
    body_skills = body_root / "skills"
    body = body_skills / "projected"
    body.mkdir(parents=True)
    (body / "SKILL.md").write_text("# body\n", encoding="utf-8")
    body_root.mkdir(parents=True, exist_ok=True)
    projection_root = tmp_path / "projection-tool"
    projection_skills = projection_root / "skills"
    projection_root.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    for tool_id, config_path, skills_path in (
        ("body-tool", body_root, body_skills),
        ("projection-tool", projection_root, projection_skills),
    ):
        _invoke(
            client,
            "create_custom_tool",
            {
                "toolId": tool_id,
                "name": tool_id,
                "configPath": str(config_path),
                "skillsPath": str(skills_path),
                "enabled": True,
            },
        )

    skill = _invoke(client, "list_skills")[0]
    assert skill["toggle_allowed"]["body-tool"] is False

    body_disable = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "disable_skill",
            "args": {"instanceId": skill["instance_id"], "toolId": "body-tool"},
        },
    )
    assert body_disable.status_code == 400
    assert body.is_dir()

    enable_projection = _invoke(
        client,
        "enable_skill",
        {"instanceId": skill["instance_id"], "toolId": "projection-tool"},
    )
    assert enable_projection is None
    projection = projection_skills / "projected"
    assert projection.is_symlink()
    assert projection.resolve() == body.resolve()

    _invoke(
        client,
        "disable_skill",
        {"instanceId": skill["instance_id"], "toolId": "projection-tool"},
    )
    assert not projection.exists()
    assert body.is_dir()


def test_web_skills_manager_hub_symlink_to_external_body_is_read_only(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    manager_root = tmp_path / "skills-manager"
    hub = manager_root / "skills"
    external = tmp_path / "external" / "linked"
    external.mkdir(parents=True)
    (external / "SKILL.md").write_text("# external body\n", encoding="utf-8")
    hub.mkdir(parents=True)
    (hub / "linked").symlink_to(external, target_is_directory=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    skill = _invoke(client, "list_skills")[0]

    assert skill["read_only"] is True
    assert skill["instance_id"].startswith("external:")
    write_response = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "write_file",
            "args": {"path": str(external / "SKILL.md"), "content": "mutate"},
        },
    )
    assert write_response.status_code == 400
    assert (external / "SKILL.md").read_text(encoding="utf-8") == "# external body\n"
    alias_body_write = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "write_file",
            "args": {"path": str(hub / "linked" / "SKILL.md"), "content": "mutate"},
        },
    )
    assert alias_body_write.status_code == 400

    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    (external / "alias.txt").symlink_to(outside)
    alias_write = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "write_file",
            "args": {"path": str(external / "alias.txt"), "content": "blocked"},
        },
    )
    assert alias_write.status_code == 400
    assert outside.read_text(encoding="utf-8") == "keep"


def test_web_skills_manager_nested_hub_symlink_keeps_external_body_read_only(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    manager_root = tmp_path / "skills-manager"
    hub = manager_root / "skills"
    external_tree = tmp_path / "external-tree"
    nested = external_tree / "nested" / "linked"
    nested.mkdir(parents=True)
    body_file = nested / "SKILL.md"
    body_file.write_text("# external nested body\n", encoding="utf-8")
    hub.mkdir(parents=True)
    (hub / "alias").symlink_to(external_tree, target_is_directory=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    skills = _invoke(client, "list_skills")
    assert len(skills) == 1
    assert skills[0]["read_only"] is True
    assert skills[0]["path"] == str(nested)

    response = client.post(
        "/v1/skills-manager/invoke",
        json={"command": "write_file", "args": {"path": str(body_file), "content": "blocked"}},
    )
    assert response.status_code == 400
    assert body_file.read_text(encoding="utf-8") == "# external nested body\n"


def test_web_skills_manager_empty_custom_skill_path_is_not_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    accidental = tmp_path / "accidental"
    accidental.mkdir()
    (accidental / "SKILL.md").write_text("# not a configured skill\n", encoding="utf-8")

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "empty-tool",
            "name": "Empty Tool",
            "configPath": str(tmp_path / "missing-config"),
            "skillsPath": "",
            "enabled": True,
        },
    )

    assert _invoke(client, "list_skills") == []


def test_web_skills_manager_empty_custom_config_path_is_not_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))

    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "empty-config-tool",
            "name": "Empty Config Tool",
            "configPath": "",
            "skillsPath": str(tmp_path / "skills"),
            "enabled": True,
        },
    )

    tool = next(item for item in _invoke(client, "detect_tools") if item["id"] == "empty-config-tool")
    assert tool["detected"] is False
    assert tool["config"]["config_path"] == ""
    assert _invoke(client, "list_skills") == []


def test_web_skills_manager_empty_active_project_path_is_not_current_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    config = _invoke(client, "get_config")
    config["active_project_id"] = "empty-project"
    config["projects"] = [{"id": "empty-project", "name": "Empty", "skills_dir": ""}]
    _invoke(client, "save_config", {"config": config})

    assert _invoke(client, "list_skills") == []


def test_web_skills_manager_external_skill_path_traversal_stays_read_only(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tool_root = tmp_path / "tool"
    skills_root = tool_root / "skills"
    external_skill = skills_root / "external-skill"
    external_skill.mkdir(parents=True)
    (external_skill / "SKILL.md").write_text("# external\n", encoding="utf-8")
    outside = skills_root / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    tool_root.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_root),
            "skillsPath": str(skills_root),
            "enabled": True,
        },
    )
    traversal = external_skill / ".." / "outside.txt"
    response = client.post(
        "/v1/skills-manager/invoke",
        json={"command": "write_file", "args": {"path": str(traversal), "content": "blocked"}},
    )
    assert response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "keep"


def test_web_skills_manager_indirect_skill_reads_skip_symlink_escape(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    tool_root = tmp_path / "tool"
    skills_root = tool_root / "skills"
    external_skill = skills_root / "external-skill"
    external_skill.mkdir(parents=True)
    (external_skill / "SKILL.md").write_text("# external\n", encoding="utf-8")
    secret = tmp_path / "secret.md"
    secret.write_text("EXFIL_SECRET", encoding="utf-8")
    (external_skill / "secret.md").symlink_to(secret)
    tool_root.mkdir(parents=True, exist_ok=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_root),
            "skillsPath": str(skills_root),
            "enabled": True,
        },
    )
    skill = _invoke(client, "list_skills")[0]

    translated = _invoke(
        client,
        "translate_skill_files",
        {"instanceId": skill["instance_id"]},
    )
    assert all(item["path"] != "secret.md" for item in translated["files"])
    assert "EXFIL_SECRET" not in str(translated)

    config = _invoke(client, "get_config")
    config["preferences"]["risk_scan_mode"] = "rules"
    _invoke(client, "save_config", {"config": config})
    report = _invoke(client, "get_risk_report", {"instanceId": skill["instance_id"]})
    assert all(item["location"]["file"] != "secret.md" for item in report["findings"])

    _invoke(client, "import_skills_to_hub", {"skillPaths": [str(external_skill)]})
    copied_secret = tmp_path / "skills-manager" / "skills" / "external-skill" / "secret.md"
    assert not copied_secret.exists()

    reserved = client.post(
        "/v1/skills-manager/reserve-export", json={"name": "safe.zip"}
    )
    assert reserved.status_code == 200
    output_path = reserved.json()["path"]
    assert _invoke(
        client,
        "export_skills",
        {"outputPath": output_path, "instanceIds": [skill["instance_id"]]},
    ) == 1
    with zipfile.ZipFile(output_path) as archive:
        assert "skills/external-skill/secret.md" not in archive.namelist()
        assert all(b"EXFIL_SECRET" not in archive.read(name) for name in archive.namelist())


def test_web_skills_manager_managed_skill_symlink_escape_is_rejected(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    manager_root = tmp_path / "skills-manager"
    skill_root = manager_root / "skills" / "managed"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# managed\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    (skill_root / "alias.txt").symlink_to(outside)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    for path in (skill_root / "alias.txt", skill_root / ".." / "outside.txt"):
        response = client.post(
            "/v1/skills-manager/invoke",
            json={"command": "write_file", "args": {"path": str(path), "content": "blocked"}},
        )
        assert response.status_code == 400
    assert outside.read_text(encoding="utf-8") == "keep"


def test_web_skills_manager_does_not_copy_when_projection_symlink_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SKILLS_MANAGER_HOME", str(tmp_path / "skills-manager"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    manager_root = tmp_path / "skills-manager"
    skill_root = manager_root / "skills" / "managed"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# managed\n", encoding="utf-8")
    tool_root = tmp_path / "tool"
    tool_skills = tool_root / "skills"
    tool_root.mkdir(parents=True)

    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "coworker")))
    _invoke(
        client,
        "create_custom_tool",
        {
            "toolId": "fixture-tool",
            "name": "Fixture Tool",
            "configPath": str(tool_root),
            "skillsPath": str(tool_skills),
            "enabled": True,
        },
    )

    def deny_symlink(self: Path, target: Path, *, target_is_directory: bool = False) -> None:
        raise OSError("symlinks unavailable")

    monkeypatch.setattr(Path, "symlink_to", deny_symlink)
    skill = next(item for item in _invoke(client, "list_skills") if item["id"] == "managed")
    response = client.post(
        "/v1/skills-manager/invoke",
        json={
            "command": "enable_skill",
            "args": {"instanceId": skill["instance_id"], "toolId": "fixture-tool"},
        },
    )
    assert response.status_code == 400
    assert not (tool_skills / "managed").exists()
