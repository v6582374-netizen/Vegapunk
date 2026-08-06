"""Native Discovery P0 vertical-slice and process-boundary acceptance tests."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
from coworker.server import SessionManager, create_app
from coworker.server import discovery_launch as discovery_launch_module
from coworker.server import discovery_worker as discovery_worker_module
from coworker.server.discovery_launch import DiscoveryLaunchStore

TOKEN = "a" * 64


class FakeConversionProvider:
    def complete(self, *, model, messages, tools=None, **settings):
        del model, messages, tools, settings
        return AssistantTurn(
            text='{"task_description":"Reviewed acceptance input","domain":"Scientific ML","background":"","constraints":[]}'
        )


def _headers(**extra: str) -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN, **extra}


def _client(state_root: Path, monkeypatch, *, runner_mode: str = "fake") -> TestClient:
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
    return TestClient(create_app(manager, discovery_runner_mode=runner_mode))


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def test_materialized_config_snapshots_selected_qwen_catalog(tmp_path):
    repository_root = Path(__file__).resolve().parents[4]
    launch_dir = tmp_path / "launch"

    config_path = discovery_worker_module._materialize_config(
        repository_root,
        launch_dir,
        {"model_id": "qwen:qwen3-max", "settings": {}},
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    # The Codex experiment keeps the UI model spelling, while the MAS runtime gets
    # an immutable, launch-owned catalog with the selected canonical identity.
    assert config["experiment"]["model"] == "qwen:qwen3-max"
    catalog_path = Path(config["model_catalog_path"])
    if not catalog_path.is_absolute():
        catalog_path = repository_root / catalog_path
    assert catalog_path != repository_root / "config/model_catalog.yaml"
    assert catalog_path.is_file()
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    assert catalog["active_text_model"] == "qwen/qwen3-max"
    assert catalog["capability_models"]["image_generation"] == (
        "qwen/qwen-image-2.0-pro"
    )

    bare_model_config = discovery_worker_module._materialize_config(
        repository_root,
        tmp_path / "bare-model-launch",
        {"model_id": "gpt-5.6-sol", "settings": {}},
    )
    assert yaml.safe_load(bare_model_config.read_text(encoding="utf-8"))["experiment"][
        "model"
    ] == "gpt-5.6-sol"


def test_materialized_config_reuses_frozen_catalog_on_resume(tmp_path):
    repository_root = tmp_path / "repo"
    (repository_root / "config").mkdir(parents=True)
    (repository_root / "config" / "default_config.yaml").write_text(
        "model_catalog_path: config/model_catalog.yaml\n", encoding="utf-8"
    )
    catalog = {
        "models": {
            "test/model": {
                "provider": "test",
                "model": "model",
                "capabilities": ["text", "image_generation"],
            }
        },
        "capability_models": {"image_generation": "test/model"},
    }
    global_catalog = repository_root / "config" / "model_catalog.yaml"
    global_catalog.write_text(yaml.safe_dump(catalog), encoding="utf-8")
    launch_dir = tmp_path / "launch"

    discovery_worker_module._materialize_config(
        repository_root, launch_dir, {"model_id": "test:model", "settings": {}}
    )
    frozen_path = launch_dir / ".execution" / "model_catalog.yaml"
    frozen_before = frozen_path.read_text(encoding="utf-8")
    global_catalog.write_text(
        yaml.safe_dump({"models": {}, "capability_models": {}}), encoding="utf-8"
    )

    discovery_worker_module._materialize_config(
        repository_root, launch_dir, {"model_id": "test:model", "settings": {}}
    )
    assert frozen_path.read_text(encoding="utf-8") == frozen_before


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


def test_web_launch_admission_starts_the_real_discovery_entrypoint(tmp_path, monkeypatch):
    """The Web Start Entry must hand execution to launch_discovery.py."""

    client = _client(tmp_path / "state", monkeypatch, runner_mode="real")
    assert client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Start the real web discovery workflow."},
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
                "task_description": "Run the saved discovery input",
                "domain": "Scientific ML",
                "background": "",
                "constraints": [],
            }
        },
    ).json()["preparation"]["revisions"][0]["revision_id"]

    calls: list[list[str]] = []

    class Process:
        pid = os.getpid()

    def fake_popen(command, **_kwargs):
        calls.append(list(command))
        return Process()

    monkeypatch.setattr(discovery_launch_module.subprocess, "Popen", fake_popen)
    started = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "real-entrypoint"}),
        json={"revision_id": revision},
    )

    assert started.status_code == 201
    assert calls
    command = calls[0]
    assert command[command.index("--mode") + 1] == "experiment"
    assert command[command.index("--exp_backend") + 1] == "codex"
    assert any("launch_discovery.py" in part for part in command)
    assert "--launch_dir" in command


def test_real_worker_uses_backend_from_launch_snapshot(tmp_path, monkeypatch):
    root = tmp_path / "state" / "discovery"
    store = DiscoveryLaunchStore(
        root,
        runner_mode="real",
        repository_root=Path(__file__).resolve().parents[4],
    )
    calls: list[list[str]] = []

    class Process:
        pid = os.getpid()

    def fake_popen(command, **_kwargs):
        calls.append(list(command))
        return Process()

    monkeypatch.setattr(discovery_launch_module.subprocess, "Popen", fake_popen)
    store.admit(
        request_fingerprint="qwen-backend",
        idempotency_key="qwen-backend",
        input_snapshot={"preparation_id": "preparation", "revision_id": "revision"},
        configuration_snapshot={
            "model_id": "qwen/qwen3.6-plus",
            "settings": {},
            "discovery_launch_preferences": {"backend": "qwen_code"},
        },
        response_builder=lambda: {},
    )

    assert calls
    command = calls[0]
    assert command[command.index("--exp_backend") + 1] == "qwen_code"


def test_real_worker_setup_failure_is_recorded_as_failed(tmp_path, monkeypatch):
    root = tmp_path / "state" / "discovery"
    store = DiscoveryLaunchStore(
        root,
        runner_mode="real",
        repository_root=Path(__file__).resolve().parents[4],
    )

    class Process:
        pid = os.getpid()

    monkeypatch.setattr(
        discovery_launch_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    admitted = store.admit(
        request_fingerprint="worker-setup-failure",
        idempotency_key="worker-setup-failure",
        input_snapshot={"preparation_id": "preparation", "revision_id": "revision"},
        configuration_snapshot={"model_id": "relay/test-model", "settings": {}},
        response_builder=lambda: {},
    )
    launch_id = admitted["launch_id"]
    launch_dir = root / "launches" / launch_id
    (launch_dir / "input_snapshot.json").write_text("{broken", encoding="utf-8")

    monkeypatch.undo()
    result = discovery_worker_module.run(
        launcher_entry=Path(__file__).resolve().parents[4] / "launch_discovery.py",
        launch_dir=launch_dir,
        discovery_root=root,
        attempt_id=json.loads(
            (launch_dir / "record.json").read_text(encoding="utf-8")
        )["current_attempt_id"],
        repository_root=Path(__file__).resolve().parents[4],
        mode="experiment",
        exp_backend="codex",
        resume=False,
    )

    assert result == 1
    assert store.status(launch_id)["launch"]["state"] == "failed"


def test_real_worker_projects_discovery_success_and_paper_failure_separately(
    tmp_path, monkeypatch
):
    """The production launcher owns both stages; the Web sidecar keeps their outcomes distinct."""

    root = tmp_path / "state" / "discovery"
    repository_root = Path(__file__).resolve().parents[4]
    store = DiscoveryLaunchStore(
        root,
        runner_mode="real",
        repository_root=repository_root,
    )

    class Process:
        pid = os.getpid()

    monkeypatch.setattr(
        discovery_launch_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: Process(),
    )
    admitted = store.admit(
        request_fingerprint="worker-paper-failure",
        idempotency_key="worker-paper-failure",
        input_snapshot={
            "preparation_id": "preparation",
            "revision_id": "revision",
            "execution_input": {
                "task_description": "Run the saved task",
                "domain": "Scientific ML",
                "background": "",
                "constraints": [],
            },
            "sources": [],
        },
        configuration_snapshot={"model_id": "relay/gpt-5.6-sol", "settings": {}},
        response_builder=lambda: {},
    )
    launch_id = admitted["launch_id"]
    launch_dir = root / "launches" / launch_id

    launcher = tmp_path / "fake_production_launcher.py"
    launcher.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--launch_dir', '--launch-dir', dest='launch_dir', required=True)
args, _ = parser.parse_known_args()
launch_dir = Path(args.launch_dir)
(launch_dir / 'discovery_summary.json').write_text(
    json.dumps({'rounds': [{'round': 1, 'results': []}]}), encoding='utf-8'
)
print('ALL DISCOVERY ROUNDS COMPLETED', flush=True)
print('PaperOrchestra failed at vendored_paper_orchestra: expected test failure', flush=True)
""",
        encoding="utf-8",
    )

    monkeypatch.undo()
    result = discovery_worker_module.run(
        launcher_entry=launcher,
        launch_dir=launch_dir,
        discovery_root=root,
        attempt_id=json.loads(
            (launch_dir / "record.json").read_text(encoding="utf-8")
        )["current_attempt_id"],
        repository_root=repository_root,
        mode="experiment",
        exp_backend="codex",
        resume=False,
    )

    assert result == 0
    observed = store.status(launch_id)
    assert observed["launch"]["state"] == "completed"
    assert observed["launch"]["paper_orchestra"] == {
        "state": "failed",
        "run_dir": "paper_orchestra_runs/paper",
        "error": (
            "PaperOrchestra reported a terminal failure; Discovery artifacts were "
            "preserved"
        ),
    }
    artifacts = {item["path"] for item in observed["produced_outputs"]}
    assert "discovery_summary.json" in artifacts
    assert "runner.log" not in artifacts


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
