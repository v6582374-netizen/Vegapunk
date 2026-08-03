"""Native Discovery P0 vertical-slice and process-boundary acceptance tests."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
from coworker.server import SessionManager, create_app

TOKEN = "a" * 64


class FakeConversionProvider:
    def complete(self, *, model, messages, tools=None, **settings):
        del model, messages, tools, settings
        return AssistantTurn(
            text='{"task_description":"Reviewed acceptance input","domain":"Scientific ML","background":"","constraints":[]}'
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
    prompt_path = state_root / "conversion-prompt.yaml"
    prompt_path.write_text("instruction: Convert the evidence.\n", encoding="utf-8")
    monkeypatch.setattr(
        "coworker.server.discovery.DISCOVERY_INPUT_CONVERSION_PROMPT_PATH", prompt_path
    )
    return TestClient(create_app(manager))


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _wait_for_history(client: TestClient, launch_id: str) -> dict:
    for _ in range(120):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        for launch in snapshot["history"]:
            if launch["launch_id"] == launch_id:
                return launch
        time.sleep(0.01)
    raise AssertionError("Discovery Launch did not reach history")


def test_native_vertical_slice_covers_launch_and_owned_artifacts(tmp_path, monkeypatch):
    client = _client(tmp_path / "state", monkeypatch)
    intake = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Compare two constrained baselines.",
            "files": [
                {
                    "filename": "brief.md",
                    "content_base64": _encoded(b"baseline notes"),
                    "size": 14,
                },
                {
                    "filename": "measurements.csv",
                    "content_base64": _encoded(b"salinity,flux\n10,42\n"),
                    "size": 20,
                },
            ],
        },
    )
    assert intake.status_code == 200
    assert intake.json()["preparation"]["status"] == "draft"
    assert client.get("/v1/discovery", headers=_headers()).json()["preparation"]["dirty"] is True

    saved = client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    )
    assert saved.status_code == 200
    assert saved.json()["preparation"]["dirty"] is False

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert converted.status_code == 200
    revision_response = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={
            "execution_input": {
                "task_description": "Reviewed acceptance input",
                "domain": "Scientific ML",
                "background": "",
                "constraints": [],
            }
        },
    )
    assert revision_response.status_code == 200
    revision_id = revision_response.json()["preparation"]["revisions"][-1]["revision_id"]

    started = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "acceptance-start"}),
        json={"revision_id": revision_id},
    )
    assert started.status_code == 201
    launch_id = started.json()["launch_id"]

    conflict = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "acceptance-conflict"}),
        json={"revision_id": revision_id},
    )
    assert conflict.status_code == 409

    history = _wait_for_history(client, launch_id)
    assert history["state"] == "completed"
    status = client.get(
        f"/v1/discovery/launches/{launch_id}/status", headers=_headers()
    )
    assert status.status_code == 200
    assert status.json()["allowed_actions"] == []

    listing = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts", headers=_headers()
    )
    assert listing.status_code == 200
    artifacts = {item["path"]: item for item in listing.json()["artifacts"]}
    assert {"report.md", "summary.json"} <= artifacts.keys()
    assert "runner.log" not in artifacts
    assert all("abs_path" not in item for item in artifacts.values())

    report = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "report.md"},
    )
    assert report.status_code == 200
    assert "completed" in report.json()["content"]

    traversal = client.get(
        f"/v1/discovery/launches/{launch_id}/artifacts/read",
        headers=_headers(),
        params={"path": "../record.json"},
    )
    assert traversal.status_code == 404

    stop_terminal = client.post(
        f"/v1/discovery/launches/{launch_id}/stop", headers=_headers()
    )
    assert stop_terminal.status_code == 409
    resume_terminal = client.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers=_headers(**{"Idempotency-Key": "acceptance-terminal-resume"}),
    )
    assert resume_terminal.status_code == 409


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_sidecar(port: int, token: str) -> None:
    url = f"http://127.0.0.1:{port}/v1/discovery"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        request = urllib.request.Request(url, headers={"X-OpenWorker-Token": token})
        try:
            with urllib.request.urlopen(request, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.HTTPError):
            time.sleep(0.05)
    raise AssertionError("sidecar did not expose /v1/discovery on its injected port")


def test_sidecar_process_smoke_proves_dynamic_port_auth_and_parent_cleanup(tmp_path):
    """Exercise the same subprocess contract the Tauri shell owns."""
    port = _free_port()
    state_root = tmp_path / "state"
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    sidecar_env = os.environ.copy()
    project_root = str(Path(__file__).resolve().parents[1])
    sidecar_env["PYTHONPATH"] = os.pathsep.join(
        [project_root, sidecar_env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    sidecar_env.update(
        {
            "COWORKER_STATE_DIR": str(state_root),
            "COWORKER_API_TOKEN": TOKEN,
            "COWORKER_EXIT_WITH_PARENT": "1",
            "COWORKER_PARENT_PID": str(parent.pid),
        }
    )
    sidecar = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "coworker.server.run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=project_root,
        env=sidecar_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_sidecar(port, TOKEN)
        with urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}/v1/discovery"), timeout=1
        ) as unauthorized:
            raise AssertionError(
                f"unauthorized request unexpectedly succeeded: {unauthorized.status}"
            )
    except urllib.error.HTTPError as error:
        assert error.code == 401
    finally:
        parent.terminate()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 6
        while sidecar.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        survived_parent = sidecar.poll() is None
        if survived_parent:
            sidecar.terminate()
        sidecar.wait(timeout=5)
        assert not survived_parent, "sidecar survived its owning parent"
