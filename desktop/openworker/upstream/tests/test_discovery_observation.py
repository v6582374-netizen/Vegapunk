"""Native Discovery Runtime Desk and Raw Discovery Console contracts."""

from __future__ import annotations

import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
from coworker.server import SessionManager, create_app
from coworker.server.discovery_launch import DiscoveryLaunchStore

TOKEN = "a" * 64


class FakeConversionProvider:
    def complete(self, *, model, messages, tools=None, **settings):
        del model, messages, tools, settings
        return AssistantTurn(
            text='{"task_description":"Reviewed research input","domain":"Scientific ML","background":"","constraints":[]}'
        )


def _client(state_root, monkeypatch):
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


def _headers(**extra):
    return {"X-OpenWorker-Token": TOKEN, **extra}


def _start_launch(client: TestClient) -> str:
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
    ).json()["preparation"]["revisions"][0]["revision_id"]
    response = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "observation-start"}),
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


def _assert_no_private_launch_input(value):
    """Public Discovery observations must never recursively expose source bytes."""
    if isinstance(value, dict):
        assert "content_base64" not in value
        assert "input_snapshot" not in value
        assert "launch_configuration_snapshot" not in value
        for child in value.values():
            _assert_no_private_launch_input(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_private_launch_input(child)


def test_discovery_observations_project_launches_without_private_source_payloads(
    tmp_path, monkeypatch
):
    client = _client(tmp_path / "state", monkeypatch)
    source = b"%PDF-1.7\n" + (b"private source bytes\n" * 2048)
    assert client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Research question.",
            "files": [
                {
                    "filename": "evidence.txt",
                    "size": len(source),
                    "content_base64": base64.b64encode(source).decode("ascii"),
                }
            ],
        },
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
    ).json()["preparation"]["revisions"][0]["revision_id"]
    started = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "summary-only-start"}),
        json={"revision_id": revision},
    )
    assert started.status_code == 201
    launch_id = started.json()["launch_id"]

    private_input = (
        tmp_path / "state" / "discovery" / "launches" / launch_id / "input_snapshot.json"
    )
    private_payload = json.loads(private_input.read_text(encoding="utf-8"))
    private_source = private_payload["sources"][0]
    assert "content_base64" not in private_source
    assert private_source["content_ref"] == private_source["sha256"]
    source_blob = (
        tmp_path / "state" / "discovery" / "sources" / private_source["content_ref"]
    )
    assert source_blob.read_bytes() == source

    _assert_no_private_launch_input(started.json())
    history = _wait_for_history(client, launch_id)
    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    _assert_no_private_launch_input(snapshot)
    assert history["launch_id"] == launch_id
    assert len(json.dumps(snapshot)) < len(source)

    second = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "summary-only-second-start"}),
        json={"revision_id": revision},
    )
    assert second.status_code == 201
    _wait_for_history(client, second.json()["launch_id"])
    source_store = tmp_path / "state" / "discovery" / "sources"
    assert [path.name for path in source_store.iterdir() if path.is_file()] == [
        private_source["content_ref"]
    ]
    replayed = client.post(
        "/v1/discovery/launches",
        headers=_headers(**{"Idempotency-Key": "summary-only-second-start"}),
        json={"revision_id": revision},
    )
    assert replayed.status_code == 201
    replay_snapshot = replayed.json()["snapshot"]
    assert replay_snapshot["current_launch"]["launch_id"] == second.json()["launch_id"]
    assert "content_base64" not in replayed.text
    persisted_index = json.loads(
        (tmp_path / "state" / "discovery" / "launches" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    assert "snapshot" not in persisted_index["idempotency"][
        "summary-only-second-start"
    ]["result"]

    status = client.get(
        f"/v1/discovery/launches/{launch_id}/status", headers=_headers()
    )
    assert status.status_code == 200
    _assert_no_private_launch_input(status.json())
    assert len(status.text) < len(source)


def test_legacy_launch_records_and_idempotency_replays_are_projected_safely(tmp_path):
    root = tmp_path / "discovery"
    launch_id = "launch-legacy"
    launch_dir = root / "launches" / launch_id
    launch_dir.mkdir(parents=True)
    raw_input = {
        "preparation_id": "preparation",
        "revision_id": "revision",
        "research_text": "private research text",
        "sources": [
            {
                "source_id": "source-1",
                "filename": "evidence.pdf",
                "extension": ".pdf",
                "size": 213420,
                "sha256": "a" * 64,
                "content_base64": "A" * 284560,
            }
        ],
        "execution_input": {"task_description": "Legacy task"},
    }
    record = {
        "launch_id": launch_id,
        "preparation_id": "preparation",
        "revision_id": "revision",
        "state": "completed",
        "stage": "completed",
        "round": 3,
        "created_at": "2026-08-04T00:00:00+00:00",
        "completed_at": "2026-08-04T00:01:00+00:00",
        "input_snapshot": raw_input,
        "launch_configuration_snapshot": {"model_id": "relay/test-model", "settings": {}},
        "attempts": [{"adoption_nonce": "SECRET", "attempt_id": "attempt-1"}],
        "timeline": {"milestones": [{"attempts": [{"content_base64": "SECRET"}]}]},
        "activity": [{"content_base64": "SECRET"}],
        "checkpoint": {"content_base64": "SECRET"},
        "paper_orchestra": {"content_base64": "SECRET"},
    }
    (launch_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")
    (root / "launches" / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "active_launch_id": None,
                "history_ids": [launch_id],
                "launch_ids": [launch_id],
                "idempotency": {
                    "legacy-key": {
                        "request_fingerprint": "fingerprint",
                        "result": {
                            "launch_id": launch_id,
                            "state": "completed",
                            "snapshot": {"history": [record]},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store = DiscoveryLaunchStore(root)
    public = store.get(launch_id)
    assert "input_snapshot" not in public
    assert public["input_summary"]["source_bytes"] == 213420
    assert "content_base64" not in json.dumps(public)
    status = store.status(launch_id)
    assert "content_base64" not in json.dumps(status)
    (launch_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "sequence": 1,
                "occurred_at": "2026-08-04T00:00:00+00:00",
                "type": "work.state.updated",
                "data": {"content_base64": "SECRET", "state": "completed"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert "content_base64" not in json.dumps(store.events(launch_id))
    assert "input_snapshot" not in json.loads(
        (launch_dir / "record.json").read_text(encoding="utf-8")
    )

    replay = store.replay_idempotent("legacy-key", "fingerprint")
    assert replay["launch_id"] == launch_id
    assert replay["state"] == "completed"
    assert "content_base64" not in json.dumps(replay)


def test_stale_idempotency_replay_never_points_to_an_unrelated_launch(tmp_path):
    root = tmp_path / "discovery"
    launch_id = "launch-current"
    launch_dir = root / "launches" / launch_id
    launch_dir.mkdir(parents=True)
    (launch_dir / "record.json").write_text(
        json.dumps(
            {
                "launch_id": launch_id,
                "preparation_id": "preparation",
                "revision_id": "revision",
                "state": "completed",
                "stage": "completed",
                "round": 1,
            }
        ),
        encoding="utf-8",
    )
    (root / "launches" / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "active_launch_id": None,
                "history_ids": [launch_id],
                "launch_ids": [launch_id],
                "idempotency": {
                    "stale-key": {
                        "request_fingerprint": "fingerprint",
                        "result": {
                            "launch_id": "launch-deleted",
                            "state": "completed",
                            "launch": {"launch_id": launch_id, "state": "completed"},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store = DiscoveryLaunchStore(root)
    replay = store.replay_idempotent(
        "stale-key",
        "fingerprint",
        response_builder=lambda: {
            "current_launch": {"launch_id": launch_id},
            "history": [{"launch_id": launch_id}],
        },
    )

    assert replay is not None
    assert replay["launch_id"] == "launch-deleted"
    assert replay["launch"] is None
    assert replay["snapshot"]["current_launch"] is None


def test_admission_factory_failure_cleans_partial_source_materialization(tmp_path):
    root = tmp_path / "discovery"
    store = DiscoveryLaunchStore(root)
    digest = "a" * 64
    source_path = root / "sources" / digest

    def materialize() -> dict:
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"partial")
        raise OSError("source materialization failed")

    def cleanup() -> None:
        source_path.unlink(missing_ok=True)

    with pytest.raises(OSError, match="source materialization failed"):
        store.admit(
            request_fingerprint="fingerprint",
            idempotency_key="factory-failure",
            input_snapshot={"preparation_id": "preparation", "revision_id": "revision"},
            configuration_snapshot={"model_id": "relay/test-model", "settings": {}},
            response_builder=lambda: {},
            input_snapshot_factory=materialize,
            input_snapshot_cleanup=cleanup,
        )

    assert not source_path.exists()


def test_public_observation_rejects_unbounded_or_non_finite_numbers(tmp_path):
    root = tmp_path / "discovery"
    launch_id = "launch-numeric"
    launch_dir = root / "launches" / launch_id
    launch_dir.mkdir(parents=True)
    huge = 10**100
    (launch_dir / "record.json").write_text(
        json.dumps(
            {
                "launch_id": launch_id,
                "preparation_id": "preparation",
                "revision_id": "revision",
                "state": "completed",
                "stage": "completed",
                "round": huge,
                "runner_pid": huge,
                "event_sequence": huge,
                "timeline": {
                    "revision": float("inf"),
                    "percent": float("nan"),
                    "milestones": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "launches" / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "active_launch_id": None,
                "history_ids": [launch_id],
                "launch_ids": [launch_id],
                "idempotency": {},
            }
        ),
        encoding="utf-8",
    )

    store = DiscoveryLaunchStore(root)
    public = store.get(launch_id)
    status = store.status(launch_id)
    encoded = json.dumps({"public": public, "status": status}, allow_nan=False)

    assert str(huge) not in encoded
    assert "round" not in public
    assert status["round"] == 0


def test_untrusted_stored_input_summary_is_reprojected_safely(tmp_path):
    root = tmp_path / "discovery"
    launch_id = "launch-summary-corrupt"
    launch_dir = root / "launches" / launch_id
    launch_dir.mkdir(parents=True)
    record = {
        "launch_id": launch_id,
        "preparation_id": "preparation",
        "revision_id": "revision",
        "state": "completed",
        "stage": "completed",
        "round": 1,
        "input_summary": {
            "preparation_id": "preparation",
            "revision_id": "revision",
            "title": "safe title",
            "research_text": "PRIVATE",
            "sources": [
                {
                    "source_id": "source-1",
                    "filename": "evidence.pdf",
                    "size": 10,
                    "sha256": "a" * 64,
                    "content_base64": "SECRET",
                }
            ],
        },
    }
    (launch_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")
    (root / "launches" / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "active_launch_id": None,
                "history_ids": [launch_id],
                "launch_ids": [launch_id],
                "idempotency": {},
            }
        ),
        encoding="utf-8",
    )

    public = DiscoveryLaunchStore(root).get(launch_id)
    _assert_no_private_launch_input(public)
    assert public["input_summary"] == {
        "preparation_id": "preparation",
        "revision_id": "revision",
        "preparation_fingerprint": None,
        "source_count": 1,
        "source_bytes": 10,
        "sources": [
            {
                "source_id": "source-1",
                "filename": "evidence.pdf",
                "size": 10,
                "sha256": "a" * 64,
            }
        ],
        "title": "safe title",
    }


def test_runtime_desk_status_and_cursor_events_survive_reconnect(tmp_path, monkeypatch):
    client = _client(tmp_path / "state", monkeypatch)
    launch_id = _start_launch(client)
    history = _wait_for_history(client, launch_id)

    status = client.get(
        f"/v1/discovery/launches/{launch_id}/status", headers=_headers()
    )
    assert status.status_code == 200
    body = status.json()
    assert body["launch"]["state"] == history["state"] == "completed"
    assert body["timeline"]["current_milestone_id"] is None
    assert [item["state"] for item in body["timeline"]["milestones"]] == [
        "completed",
        "completed",
        "completed",
    ]
    assert body["activity"]["items"]
    assert body["allowed_actions"] == []

    events = client.get(
        f"/v1/discovery/launches/{launch_id}/events?after=0", headers=_headers()
    )
    assert events.status_code == 200
    event_body = events.json()
    assert event_body["events"]
    sequences = [event["sequence"] for event in event_body["events"]]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
    assert event_body["latest_sequence"] == sequences[-1]

    resumed_events = client.get(
        f"/v1/discovery/launches/{launch_id}/events?after={sequences[-2]}",
        headers=_headers(),
    )
    assert resumed_events.status_code == 200
    assert [event["sequence"] for event in resumed_events.json()["events"]] == [
        sequences[-1]
    ]

    restarted = _client(tmp_path / "state", monkeypatch)
    reconnected = restarted.get(
        f"/v1/discovery/launches/{launch_id}/status", headers=_headers()
    )
    assert reconnected.status_code == 200
    assert reconnected.json()["timeline"] == body["timeline"]
    assert reconnected.json()["activity"] == body["activity"]


def test_raw_discovery_console_replays_only_the_selected_launch_log(tmp_path, monkeypatch):
    client = _client(tmp_path / "state", monkeypatch)
    launch_id = _start_launch(client)
    _wait_for_history(client, launch_id)

    replay = client.get(
        f"/v1/discovery/launches/{launch_id}/logs/stream", headers=_headers()
    )
    assert replay.status_code == 200
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert "fake-runner: preparing round=1" in replay.text
    assert "fake-runner: finalizing round=3" in replay.text
    assert "file=" not in str(replay.request.url)

    arbitrary_file = client.get(
        f"/v1/discovery/launches/{launch_id}/logs/stream?file=../record.json",
        headers=_headers(),
    )
    assert arbitrary_file.status_code == 200
    assert "launch_id" not in arbitrary_file.text

    unknown = client.get(
        "/v1/discovery/launches/launch-missing/logs/stream", headers=_headers()
    )
    assert unknown.status_code == 404
