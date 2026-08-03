"""Native Discovery Runtime Desk and Raw Discovery Console contracts."""

from __future__ import annotations

import time

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
