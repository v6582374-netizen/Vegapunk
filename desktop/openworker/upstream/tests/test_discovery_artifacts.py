"""Native Discovery Launch-owned artifact and access-boundary contracts."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
from coworker.server import SessionManager, create_app

TOKEN = "a" * 64


class FakeConversionProvider:
    def complete(self, *, model, messages, tools=None, **settings):
        del model, messages, tools, settings
        return AssistantTurn(
            text='{"task_description":"Reviewed research input","domain":"Scientific ML","background":"","constraints":[]}'
        )


def _headers(**extra: str) -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN, **extra}


def _client(state_root: Path, monkeypatch) -> TestClient:
    state_root.mkdir(parents=True, exist_ok=True)
    manager = SessionManager(
        data_dir=state_root,
        model="relay/test-model",
        provider=FakeConversionProvider(),
        model_settings={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "reasoning_effort": "none",
        },
    )
    monkeypatch.setattr(
        "coworker.server.discovery.DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        state_root / "conversion-prompt.yaml",
    )
    (state_root / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    return TestClient(create_app(manager))


def _start_launch(client: TestClient, key: str) -> str:
    assert client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question."},
    ).status_code == 200
    assert client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    ).status_code == 200
    assert client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    ).status_code == 200
    revision = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={
            "execution_input": {
                "task_description": "Reviewed research input",
                "domain": "Scientific ML",
                "background": "",
                "constraints": [],
            }
        },
    ).json()["preparation"]["revisions"][-1]["revision_id"]
    response = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": key}),
        json={"revision_id": revision},
    )
    assert response.status_code == 201
    return response.json()["launch_id"]


def _wait_for_history(client: TestClient, launch_id: str) -> dict:
    for _ in range(100):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        for launch in snapshot["history"]:
            if launch["launch_id"] == launch_id:
                return launch
        time.sleep(0.01)
    raise AssertionError("Launch did not reach history")


def test_launch_artifacts_are_previewed_without_exposing_runner_log_or_absolute_paths(
    tmp_path, monkeypatch
):
    client = _client(tmp_path / "state", monkeypatch)
    launch_id = _start_launch(client, "artifact-start")
    _wait_for_history(client, launch_id)

    launch_dir = tmp_path / "state" / "discovery" / "launches" / launch_id
    artifacts_root = launch_dir / "artifacts"
    (artifacts_root / "notes.md").write_text("# Notes\n\nReadable", encoding="utf-8")
    (artifacts_root / "data.json").write_text('{"ok": true}\n', encoding="utf-8")
    (artifacts_root / "figure.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    (artifacts_root / "paper.pdf").write_bytes(b"%PDF-fake")
    (artifacts_root / "paper.docx").write_bytes(b"PK-fake")
    (launch_dir / "runner.log").write_text("diagnostic only\n", encoding="utf-8")

    listing = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts", headers=_headers()
    )
    assert listing.status_code == 200
    artifacts = {item["path"]: item for item in listing.json()["artifacts"]}
    assert "runner.log" not in artifacts
    assert artifacts["notes.md"]["kind"] == "markdown"
    assert artifacts["data.json"]["kind"] == "structured"
    assert artifacts["figure.png"]["kind"] == "image"
    assert artifacts["paper.pdf"]["previewable"] is False
    assert artifacts["paper.docx"]["previewable"] is False
    assert all("abs_path" not in item for item in artifacts.values())

    markdown = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "notes.md"},
    )
    assert markdown.status_code == 200
    assert markdown.json()["content"].startswith("# Notes")

    image = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "figure.png"},
    )
    assert image.status_code == 200
    assert image.json()["data_url"].startswith("data:image/png;base64,")

    pdf = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "paper.pdf"},
    )
    assert pdf.status_code == 200
    assert pdf.json()["previewable"] is False
    assert pdf.json()["data_url"] is None

    opened: list[list[str]] = []

    class FakeProcess:
        pass

    def fake_popen(args, **kwargs):
        del kwargs
        opened.append(args)
        return FakeProcess()

    monkeypatch.setattr("coworker.server.discovery_artifacts.subprocess.Popen", fake_popen)
    reveal = client.post(
        f"/v1/discovery/launches/{launch_id}/artifacts/reveal",
        headers=_headers(),
        json={"path": "paper.pdf", "mode": "open"},
    )
    assert reveal.status_code == 200
    assert reveal.json()["ok"] is True
    assert opened


def test_artifact_access_rejects_unknown_launch_traversal_absolute_and_symlink_escape(
    tmp_path, monkeypatch
):
    client = _client(tmp_path / "state", monkeypatch)
    launch_id = _start_launch(client, "artifact-boundary")
    _wait_for_history(client, launch_id)
    launch_dir = tmp_path / "state" / "discovery" / "launches" / launch_id
    artifacts_root = launch_dir / "artifacts"
    artifacts_root.mkdir(exist_ok=True)
    (artifacts_root / "safe.txt").write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        os.symlink(outside, artifacts_root / "escape.txt")
    except OSError:
        pass

    for path in ("../record.json", "/etc/passwd", "C:/Windows/win.ini", "escape.txt"):
        response = client.get(
            f"/v1/discovery/launches/{launch_id}/artifacts/read",
            headers=_headers(),
            params={"path": path},
        )
        assert response.status_code == 404, path

    unknown = client.get(
        "/v1/discovery/launches/launch-missing/artifacts", headers=_headers()
    )
    assert unknown.status_code == 404

    unknown_read = client.get(
        "/v1/discovery/launches/launch-missing/artifacts/read",
        headers=_headers(),
        params={"path": "safe.txt"},
    )
    assert unknown_read.status_code == 404


def test_artifacts_are_bound_to_the_selected_launch(tmp_path, monkeypatch):
    client = _client(tmp_path / "state", monkeypatch)
    first = _start_launch(client, "artifact-first")
    _wait_for_history(client, first)
    second = _start_launch(client, "artifact-second")
    _wait_for_history(client, second)

    first_root = tmp_path / "state" / "discovery" / "launches" / first / "artifacts"
    second_root = tmp_path / "state" / "discovery" / "launches" / second / "artifacts"
    (first_root / "first.txt").write_text("first", encoding="utf-8")
    (second_root / "second.txt").write_text("second", encoding="utf-8")

    first_listing = client.get(
        f"/v1/discovery/launches/{first}/artifacts", headers=_headers()
    ).json()["artifacts"]
    second_listing = client.get(
        f"/v1/discovery/launches/{second}/artifacts", headers=_headers()
    ).json()["artifacts"]
    assert {item["path"] for item in first_listing} >= {"first.txt"}
    assert "second.txt" not in {item["path"] for item in first_listing}
    assert {item["path"] for item in second_listing} >= {"second.txt"}

    cross_launch = client.get(
        f"/v1/discovery/launches/{first}/artifacts/read",
        headers=_headers(),
        params={"path": f"../{second}/artifacts/second.txt"},
    )
    assert cross_launch.status_code == 404


def test_symlinked_artifact_root_is_not_exposed(tmp_path, monkeypatch):
    client = _client(tmp_path / "state", monkeypatch)
    launch_id = _start_launch(client, "artifact-root-symlink")
    _wait_for_history(client, launch_id)

    launch_dir = tmp_path / "state" / "discovery" / "launches" / launch_id
    artifacts_root = launch_dir / "artifacts"
    real_root = launch_dir / "real-artifacts"
    artifacts_root.rename(real_root)
    try:
        os.symlink(real_root, artifacts_root)
    except OSError:
        return

    listing = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts", headers=_headers()
    )
    assert listing.status_code == 200
    assert listing.json()["artifacts"] == []
    read = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "report.md"},
    )
    assert read.status_code == 404
