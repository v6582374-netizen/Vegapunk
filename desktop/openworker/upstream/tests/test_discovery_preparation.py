"""Native Desktop Discovery Preparation intake and persistence contracts."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server import discovery as discovery_module


TOKEN = "a" * 64


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _client(state_root):
    manager = SessionManager(data_dir=state_root)
    return TestClient(create_app(manager))


def _headers() -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN}


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("COWORKER_API_TOKEN", TOKEN)


def test_intake_accepts_text_and_multiple_files_with_stable_source_ids(tmp_path):
    client = _client(tmp_path / "state")

    response = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Study the effect of salinity on desalination membranes.",
            "files": [
                {
                    "filename": "notes.md",
                    "content_base64": _encoded(b"first notes"),
                    "size": 11,
                },
                {
                    "filename": "notes.md",
                    "content_base64": _encoded(b"second notes"),
                    "size": 12,
                },
            ],
        },
    )

    assert response.status_code == 200
    preparation = response.json()["preparation"]
    assert preparation["status"] == "draft"
    assert preparation["dirty"] is True
    assert preparation["draft"]["text"].startswith("Study the effect")
    sources = preparation["draft"]["sources"]
    assert [source["filename"] for source in sources] == ["notes.md", "notes.md"]
    assert all(source["size"] > 0 for source in sources)
    assert len({source["source_id"] for source in sources}) == 2

    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["draft"]["sources"] == sources


def test_invalid_batch_is_rejected_without_partial_mutation_and_delete_is_draft_only(tmp_path):
    client = _client(tmp_path / "state")
    accepted = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Keep this draft.",
            "files": [
                {
                    "filename": "source.txt",
                    "content_base64": _encoded(b"accepted"),
                    "size": 8,
                }
            ],
        },
    )
    source_id = accepted.json()["preparation"]["draft"]["sources"][0]["source_id"]
    before = client.get("/v1/discovery", headers=_headers()).json()["preparation"]

    rejected = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "This text must not land.",
            "files": [
                {
                    "filename": "valid.csv",
                    "content_base64": _encoded(b"a,b\n1,2"),
                    "size": 7,
                },
                {
                    "filename": "unsupported.exe",
                    "content_base64": _encoded(b"nope"),
                    "size": 4,
                },
            ],
        },
    )
    assert rejected.status_code == 422
    assert client.get("/v1/discovery", headers=_headers()).json()["preparation"] == before

    deleted = client.delete(
        f"/v1/discovery/preparation/sources/{source_id}", headers=_headers()
    )
    assert deleted.status_code == 200
    preparation = deleted.json()["preparation"]
    assert preparation["draft"]["sources"] == []
    assert preparation["saved"]["sources"] == []
    assert preparation["draft"]["text"] == "Keep this draft."


def test_save_is_explicit_and_restart_restores_only_latest_committed_state(tmp_path):
    state_root = tmp_path / "state"
    client = _client(state_root)
    intake = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Committed research question.",
            "files": [
                {
                    "filename": "brief.txt",
                    "content_base64": _encoded(b"committed bytes"),
                    "size": 15,
                }
            ],
        },
    )
    source_id = intake.json()["preparation"]["draft"]["sources"][0]["source_id"]

    saved = client.post(
        "/v1/discovery/preparation/save",
        headers=_headers(),
        json={"text": "Committed research question."},
    )
    assert saved.status_code == 200
    assert saved.json()["preparation"]["status"] == "saved"
    assert saved.json()["preparation"]["dirty"] is False

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Unsaved draft text.",
            "files": [
                {
                    "filename": "draft.csv",
                    "content_base64": _encoded(b"draft"),
                    "size": 5,
                }
            ],
        },
    )

    restarted = _client(state_root)
    restored = restarted.get("/v1/discovery", headers=_headers()).json()["preparation"]
    assert restored["status"] == "saved"
    assert restored["dirty"] is False
    assert restored["draft"]["text"] == "Committed research question."
    assert [source["source_id"] for source in restored["draft"]["sources"]] == [source_id]

    reset = restarted.delete(
        f"/v1/discovery/preparation/sources/{source_id}", headers=_headers()
    )
    assert reset.status_code == 200
    reset = restarted.post(
        "/v1/discovery/preparation/save",
        headers=_headers(),
        json={"text": ""},
    )
    assert reset.status_code == 200
    assert reset.json()["preparation"]["status"] == "empty"
    assert reset.json()["preparation"]["saved"]["sources"] == []

    reset_restarted = _client(state_root)
    empty = reset_restarted.get("/v1/discovery", headers=_headers()).json()["preparation"]
    assert empty["status"] == "empty"
    assert empty["draft"] == {"text": "", "sources": []}


def test_failed_save_preserves_previous_committed_state(tmp_path, monkeypatch):
    state_root = tmp_path / "state"
    client = _client(state_root)
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Known-good state."},
    )
    assert client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    ).status_code == 200

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "This save will fail."},
    )
    original_replace = discovery_module.os.replace

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path):
        if Path(destination) == state_root / "discovery" / "preparation.json":
            raise OSError("simulated storage failure")
        return original_replace(source, destination)

    monkeypatch.setattr(discovery_module.os, "replace", fail_replace)
    failed = client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    )
    assert failed.status_code == 500
    assert failed.json()["detail"] == "Discovery Preparation could not be saved. Try again."

    restored = _client(state_root).get("/v1/discovery", headers=_headers()).json()
    assert restored["preparation"]["saved"]["text"] == "Known-good state."


@pytest.mark.parametrize(
    ("filename", "payload", "expected_error"),
    [
        ("folder/notes.md", {"content_base64": _encoded(b"x"), "size": 1}, "folder"),
        ("notes.exe", {"content_base64": _encoded(b"x"), "size": 1}, "supported"),
        ("notes.md", {"content_base64": _encoded(b""), "size": 0}, "empty"),
        ("notes.md", {"content_base64": _encoded(b"x"), "size": 2}, "size"),
    ],
)
def test_source_identity_whitelist_and_content_validation(filename, payload, expected_error, tmp_path):
    client = _client(tmp_path / "state")
    body = {
        "files": [{"filename": filename, **payload}],
    }

    response = client.post(
        "/v1/discovery/preparation/intake", headers=_headers(), json=body
    )

    assert response.status_code == 422
    assert expected_error in response.json()["detail"].lower()
    assert client.get("/v1/discovery", headers=_headers()).json()["preparation"]["draft"] == {
        "text": "",
        "sources": [],
    }
