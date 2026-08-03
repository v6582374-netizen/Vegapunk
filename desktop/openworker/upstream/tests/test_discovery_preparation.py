"""Native Desktop Discovery Preparation intake and persistence contracts."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
from coworker.server import SessionManager, create_app
from coworker.server import discovery as discovery_module
from coworker.server import discovery_launch as discovery_launch_module
from coworker.server.discovery_launch import DiscoveryLaunchStore

TOKEN = "a" * 64


def _encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _client(state_root, *, provider=None, model_settings=None):
    manager = SessionManager(
        data_dir=state_root, provider=provider, model_settings=model_settings
    )
    return TestClient(create_app(manager))


def _headers() -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN}


def _docx_bytes(text: str) -> bytes:
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as document:
        document.writestr("word/document.xml", document_xml)
    return stream.getvalue()


def test_conversion_prompt_path_uses_the_packaged_sidecar_root(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery_module.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert discovery_module._conversion_prompt_path() == (
        tmp_path / "config" / "discovery_input_conversion_prompt.yaml"
    )


def test_conversion_prompt_path_uses_the_repository_config_in_source_checkouts():
    prompt_path = discovery_module._conversion_prompt_path()
    assert prompt_path == (
        Path(discovery_module.__file__).resolve().parents[5]
        / "config"
        / "discovery_input_conversion_prompt.yaml"
    )
    assert prompt_path.is_file()


class FakeConversionProvider:
    def __init__(self, text: str | None = None):
        self.text = (
            json.dumps(
                {
                    "task_description": "Converted Discovery task",
                    "domain": "Scientific ML",
                    "background": "Converted background",
                    "constraints": ["Use the committed sources."],
                }
            )
            if text is None
            else text
        )
        self.calls: list[dict] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append({"model": model, "messages": messages, "settings": settings})
        return AssistantTurn(text=self.text)

    def capabilities(self, model):
        del model
        return None


def _execution_input(
    task_description: str = "Converted Discovery task",
    *,
    domain: str = "Scientific ML",
    background: str = "Converted background",
    constraints: list[str] | None = None,
) -> dict[str, object]:
    return {
        "task_description": task_description,
        "domain": domain,
        "background": background,
        "constraints": constraints or ["Use the committed sources."],
    }


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


def test_reset_atomically_clears_preparation_and_revision_history(tmp_path, monkeypatch):
    state_root = tmp_path / "state"
    provider = FakeConversionProvider(json.dumps(_execution_input("Converted reset input")))
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=state_root, provider=provider))
    )

    intake = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "text": "Reset this Preparation.",
            "files": [
                {
                    "filename": "brief.md",
                    "content_base64": _encoded(b"source bytes"),
                    "size": 12,
                }
            ],
        },
    )
    assert intake.status_code == 200
    assert client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    ).status_code == 200
    assert client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    ).status_code == 200
    revision = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Reviewed reset input")},
    )
    assert revision.status_code == 200
    assert revision.json()["preparation"]["revisions"]

    reset = client.post("/v1/discovery/preparation/reset", headers=_headers())

    assert reset.status_code == 200
    preparation = reset.json()["preparation"]
    assert preparation["status"] == "empty"
    assert preparation["dirty"] is False
    assert preparation["draft"] == {"text": "", "sources": []}
    assert preparation["saved"] == {"text": "", "sources": []}
    assert preparation["revisions"] == []
    assert preparation["conversion"]["status"] == "pending"

    restarted = _client(state_root).get("/v1/discovery", headers=_headers()).json()
    assert restarted["preparation"]["revisions"] == []
    assert restarted["preparation"]["saved"] == {"text": "", "sources": []}

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Keep this state if reset fails."},
    )
    original_replace = discovery_module.os.replace

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path):
        if Path(destination) == state_root / "discovery" / "preparation.json":
            raise OSError("simulated reset storage failure")
        return original_replace(source, destination)

    monkeypatch.setattr(discovery_module.os, "replace", fail_replace)
    failed = client.post("/v1/discovery/preparation/reset", headers=_headers())
    assert failed.status_code == 500
    assert failed.json()["detail"] == "Discovery Preparation could not be reset. Try again."
    unchanged = client.get("/v1/discovery", headers=_headers()).json()["preparation"]
    assert unchanged["draft"]["text"] == "Keep this state if reset fails."
    assert unchanged["saved"] == {"text": "", "sources": []}


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


def test_conversion_is_explicit_and_saved_revisions_are_immutable(tmp_path, monkeypatch):
    provider = FakeConversionProvider(json.dumps(_execution_input("Converted once")))
    state_root = tmp_path / "state"
    manager = SessionManager(
        data_dir=state_root,
        model="relay/test-model",
        provider=provider,
        model_settings={
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "reasoning_effort": "none",
        },
    )
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(create_app(manager))

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question.", "files": []},
    )
    client.post(
        "/v1/discovery/preparation/save",
        headers=_headers(),
        json={},
    )

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert converted.status_code == 200
    conversion = converted.json()["preparation"]["conversion"]
    assert conversion["status"] == "editing"
    assert conversion["execution_input"]["task_description"] == "Converted once"
    assert converted.json()["preparation"]["revisions"] == []
    assert provider.calls[0]["model"] == "relay/test-model"
    assert provider.calls[0]["settings"] == {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 4096,
        "reasoning_effort": "none",
    }
    assert provider.calls[0]["messages"][0] == {
        "role": "system",
        "content": "Convert the evidence.",
    }

    first = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Reviewed once")},
    )
    assert first.status_code == 200
    first_revision = first.json()["preparation"]["revisions"][0]
    assert first_revision["execution_input"]["task_description"] == "Reviewed once"
    assert first.json()["preparation"]["conversion"]["status"] == "saved"

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Changed research question."},
    )
    dirty = client.get("/v1/discovery", headers=_headers()).json()["preparation"]
    assert dirty["conversion"]["status"] == "dirty"
    assert dirty["revisions"][0]["eligible"] is False

    client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    )
    client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    second = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Reviewed twice")},
    )
    revisions = second.json()["preparation"]["revisions"]
    assert [revision["execution_input"]["task_description"] for revision in revisions] == [
        "Reviewed once",
        "Reviewed twice",
    ]
    assert revisions[0]["revision_id"] != revisions[1]["revision_id"]

    restored = _client(state_root).get("/v1/discovery", headers=_headers()).json()
    assert [revision["execution_input"]["task_description"] for revision in restored["preparation"]["revisions"]] == [
        "Reviewed once",
        "Reviewed twice",
    ]


def test_conversion_rejects_empty_or_unsaved_preparation_without_revision(tmp_path, monkeypatch):
    provider = FakeConversionProvider()
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )

    empty = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert empty.status_code == 422
    assert "non-empty" in empty.json()["detail"].lower()
    assert provider.calls == []

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Unsaved question."},
    )
    unsaved = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert unsaved.status_code == 422
    assert "save" in unsaved.json()["detail"].lower()
    assert provider.calls == []


def test_structured_conversion_returns_one_backend_execution_input_and_runs_it(
    tmp_path, monkeypatch
):
    provider = FakeConversionProvider(
        json.dumps(
            {
                "task_description": "Explain the observed transition.",
                "domain": "Space plasma physics",
                "background": "satellite pass",
                "constraints": ["Do not infer causality from one pass."],
            }
        )
    )
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert directly to structured inputs.\n", encoding="utf-8"
    )
    client = _client(tmp_path / "state", provider=provider)
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Compare two transitions."},
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert converted.status_code == 200
    conversion = converted.json()["preparation"]["conversion"]
    assert conversion["execution_input"] == {
        "task_description": "Explain the observed transition.",
        "domain": "Space plasma physics",
        "background": "satellite pass",
        "constraints": ["Do not infer causality from one pass."],
    }
    assert "draft" not in conversion

    saved = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": conversion["execution_input"]},
    )
    assert saved.status_code == 200
    revision = saved.json()["preparation"]["revisions"][0]
    assert revision["execution_input"] == conversion["execution_input"]
    assert "formatted_input" not in revision

    started = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "structured-input-start"},
        json={"revision_id": revision["revision_id"]},
    )
    assert started.status_code == 201
    snapshot = started.json()["snapshot"]["current_launch"]["input_snapshot"]
    assert snapshot["execution_input"] == conversion["execution_input"]
    assert "execution_inputs" not in snapshot
    assert "input_id" not in snapshot
    assert "formatted_input" not in snapshot


@pytest.mark.parametrize(
    "model_output",
    [
        json.dumps({"execution_inputs": [_execution_input()]}),
        "# This must not become a Markdown intermediate",
    ],
)
def test_conversion_rejects_non_backend_execution_input_shapes(
    model_output, tmp_path, monkeypatch
):
    provider = FakeConversionProvider(model_output)
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = _client(tmp_path / "state", provider=provider)
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question."},
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )

    assert converted.status_code == 502
    conversion = client.get("/v1/discovery", headers=_headers()).json()["preparation"]["conversion"]
    assert conversion["status"] == "failed"
    assert "execution_input" not in conversion


def test_restart_discards_incompatible_legacy_revisions_without_losing_preparation(
    tmp_path,
):
    state_root = tmp_path / "state"
    preparation = {"text": "Committed legacy research.", "sources": []}
    fingerprint = discovery_module._preparation_fingerprint(preparation)
    state_path = state_root / "discovery" / "preparation.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "text": preparation["text"],
                "sources": [],
                "revisions": [
                    {
                        "revision_id": "legacy-many",
                        "created_at": "2026-08-01T00:00:00+00:00",
                        "model_id": "legacy-model",
                        "preparation_fingerprint": fingerprint,
                        "execution_inputs": [
                            {"title": "first legacy input"},
                            {"title": "second legacy input"},
                        ],
                    },
                    {
                        "revision_id": "legacy-invalid-single",
                        "created_at": "2026-08-01T00:00:00+00:00",
                        "model_id": "legacy-model",
                        "preparation_fingerprint": fingerprint,
                        "execution_inputs": [{"title": "not a backend input"}],
                    },
                    {
                        "revision_id": "legacy-single-valid",
                        "created_at": "2026-08-01T00:00:00+00:00",
                        "model_id": "legacy-model",
                        "preparation_fingerprint": fingerprint,
                        "execution_inputs": [_execution_input("Migrate this revision")],
                    },
                    {
                        "revision_id": "current-valid",
                        "created_at": "2026-08-01T00:00:00+00:00",
                        "model_id": "current-model",
                        "preparation_fingerprint": fingerprint,
                        "execution_input": _execution_input("Keep this revision"),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = _client(state_root).get("/v1/discovery", headers=_headers())

    assert snapshot.status_code == 200
    preparation_snapshot = snapshot.json()["preparation"]
    assert preparation_snapshot["status"] == "saved"
    assert preparation_snapshot["saved"]["text"] == preparation["text"]
    assert [
        revision["execution_input"]["task_description"]
        for revision in preparation_snapshot["revisions"]
    ] == ["Migrate this revision", "Keep this revision"]


def test_conversion_public_shape_contains_only_backend_task_fields(tmp_path, monkeypatch):
    model_output = _execution_input("Exact task") | {
        "title": "Discard this review metadata",
        "objective": "Discard this duplicate field",
    }
    provider = FakeConversionProvider(json.dumps(model_output))
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = _client(tmp_path / "state", provider=provider)
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question."},
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )

    assert converted.status_code == 200
    assert set(converted.json()["preparation"]["conversion"]["execution_input"]) == {
        "task_description",
        "domain",
        "background",
        "constraints",
    }


def test_conversion_reads_docx_without_an_optional_python_docx_dependency(tmp_path, monkeypatch):
    provider = FakeConversionProvider()
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    document = _docx_bytes("DOCX evidence")
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "evidence.docx",
                    "content_base64": _encoded(document),
                    "size": len(document),
                }
            ]
        },
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert converted.status_code == 200
    request = json.loads(provider.calls[0]["messages"][1]["content"])
    assert request["sources"][0]["content"] == "DOCX evidence"


def test_unreadable_source_fails_conversion_without_deleting_the_source(tmp_path, monkeypatch):
    provider = FakeConversionProvider()
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    intake = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "broken.pdf",
                    "content_base64": _encoded(b"not a PDF"),
                    "size": 9,
                }
            ]
        },
    )
    source_id = intake.json()["preparation"]["draft"]["sources"][0]["source_id"]
    client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    )

    failed = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert failed.status_code == 422
    assert "broken.pdf" in failed.json()["detail"]
    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["conversion"]["status"] == "failed"
    assert snapshot["preparation"]["revisions"] == []
    assert snapshot["preparation"]["draft"]["sources"][0]["source_id"] == source_id


@pytest.mark.parametrize(
    ("filename", "content"),
    [("broken.docx", b"not a DOCX archive"), ("broken.zip", b"not a ZIP archive")],
)
def test_unreadable_docx_and_zip_fail_conversion_without_deleting_the_source(
    filename, content, tmp_path, monkeypatch
):
    provider = FakeConversionProvider()
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    intake = client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": filename,
                    "content_base64": _encoded(content),
                    "size": len(content),
                }
            ]
        },
    )
    assert intake.status_code == 200
    source_id = intake.json()["preparation"]["draft"]["sources"][0]["source_id"]
    assert client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    ).status_code == 200

    failed = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert failed.status_code == 422
    assert filename in failed.json()["detail"]
    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["conversion"]["status"] == "failed"
    assert snapshot["preparation"]["draft"]["sources"][0]["source_id"] == source_id


def test_conversion_reads_zip_manifest(tmp_path, monkeypatch):
    provider = FakeConversionProvider()
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("src/experiment.py", "print('ok')")
    content = archive.getvalue()
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "baseline.zip",
                    "content_base64": _encoded(content),
                    "size": len(content),
                }
            ]
        },
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    converted = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert converted.status_code == 200
    request = json.loads(provider.calls[0]["messages"][1]["content"])
    assert request["sources"][0]["kind"] == "baseline_code"
    assert "src/experiment.py" in request["sources"][0]["content"]


def test_empty_conversion_output_creates_no_revision(tmp_path, monkeypatch):
    provider = FakeConversionProvider("")
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question."},
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})

    failed = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert failed.status_code == 502
    assert "empty" in failed.json()["detail"].lower()
    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["conversion"]["status"] == "failed"
    assert snapshot["preparation"]["revisions"] == []


def test_failed_reconversion_preserves_earlier_revisions(tmp_path, monkeypatch):
    provider = FakeConversionProvider(json.dumps(_execution_input("First conversion")))
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Research question."},
    )
    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})
    assert client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    ).status_code == 200
    saved = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Reviewed input")},
    )
    assert saved.status_code == 200
    previous_revisions = saved.json()["preparation"]["revisions"]

    provider.text = ""
    failed = client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    )
    assert failed.status_code == 502
    snapshot = client.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["revisions"] == previous_revisions
    assert snapshot["preparation"]["conversion"]["status"] == "failed"


def _prepare_saved_revision(client, *, text: str = "Research question.") -> str:
    assert client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": text},
    ).status_code == 200
    assert client.post(
        "/v1/discovery/preparation/save", headers=_headers(), json={}
    ).status_code == 200
    assert client.post(
        "/v1/discovery/preparation/convert", headers=_headers(), json={}
    ).status_code == 200
    saved = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Reviewed research input")},
    )
    assert saved.status_code == 200
    return saved.json()["preparation"]["revisions"][0]["revision_id"]


def test_run_admits_one_immutable_launch_and_keeps_preparation_editable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    provider = FakeConversionProvider(json.dumps(_execution_input("Converted input")))
    state_root = tmp_path / "state"
    manager = SessionManager(
        data_dir=state_root,
        model="relay/test-model",
        provider=provider,
        model_settings={"temperature": 0.0, "max_tokens": 512},
    )
    client = TestClient(create_app(manager))
    revision_id = _prepare_saved_revision(client)

    admitted = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "start-1"},
        json={"preparation_id": "preparation", "revision_id": revision_id},
    )
    assert admitted.status_code == 201
    result = admitted.json()
    assert result["state"] == "starting"
    launch_id = result["launch_id"]
    assert result["snapshot"]["current_launch"]["launch_id"] == launch_id
    assert result["snapshot"]["current_launch"]["revision_id"] == revision_id

    launch_dir = state_root / "discovery" / "launches" / launch_id
    input_snapshot = json.loads(
        (launch_dir / "input_snapshot.json").read_text(encoding="utf-8")
    )
    configuration_snapshot = json.loads(
        (launch_dir / "launch_configuration.json").read_text(encoding="utf-8")
    )
    assert input_snapshot["revision_id"] == revision_id
    assert input_snapshot["execution_input"] == _execution_input("Reviewed research input")
    assert "formatted_input" not in input_snapshot
    assert configuration_snapshot["model_id"] == "relay/test-model"
    assert configuration_snapshot["settings"] == {
        "temperature": 0.0,
        "max_tokens": 512,
    }
    assert configuration_snapshot["discovery_launch_preferences"]["workflow"] == {
        "loop_rounds": 10,
        "loop_mode": "incremental",
        "max_iterations": 4,
        "top_ideas_count": 5,
        "top_ideas_evo": True,
        "max_concurrent_tasks": 5,
    }

    # The Preparation remains an independent editable draft after admission.
    assert client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Edited after launch."},
    ).status_code == 200
    assert client.get("/v1/discovery", headers=_headers()).json()["preparation"]["dirty"] is True
    assert json.loads(
        (launch_dir / "input_snapshot.json").read_text(encoding="utf-8")
    ) == input_snapshot

    reset = client.post("/v1/discovery/preparation/reset", headers=_headers())
    assert reset.status_code == 200
    reset_snapshot = reset.json()
    assert reset_snapshot["preparation"]["status"] == "empty"
    assert reset_snapshot["current_launch"]["launch_id"] == launch_id
    assert json.loads(
        (launch_dir / "input_snapshot.json").read_text(encoding="utf-8")
    ) == input_snapshot

    import time

    for _ in range(40):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        if snapshot["current_launch"] is None:
            break
        time.sleep(0.025)
    assert snapshot["current_launch"] is None
    assert snapshot["history"][0]["launch_id"] == launch_id
    assert snapshot["history"][0]["state"] == "completed"


def test_run_rejects_ineligible_revision_and_enforces_idempotent_single_active_slot(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    provider = FakeConversionProvider(json.dumps(_execution_input("Converted input")))
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state", provider=provider))
    )
    revision_id = _prepare_saved_revision(client)

    client.post(
        "/v1/discovery/preparation/intake",
        headers=_headers(),
        json={"text": "Make this revision stale."},
    )
    stale = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "stale"},
        json={"revision_id": revision_id},
    )
    assert stale.status_code == 422
    assert "Preparation" in stale.json()["detail"]

    client.post("/v1/discovery/preparation/save", headers=_headers(), json={})
    client.post("/v1/discovery/preparation/convert", headers=_headers(), json={})
    current = client.post(
        "/v1/discovery/preparation/revisions",
        headers=_headers(),
        json={"execution_input": _execution_input("Current input")},
    )
    current_revision_id = current.json()["preparation"]["revisions"][-1]["revision_id"]

    first = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "start-1"},
        json={"revision_id": current_revision_id},
    )
    assert first.status_code == 201
    retry = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "start-1"},
        json={"revision_id": current_revision_id},
    )
    assert retry.status_code == 201
    assert retry.json()["launch_id"] == first.json()["launch_id"]

    conflicting_retry = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "start-1"},
        json={"revision_id": revision_id},
    )
    assert conflicting_retry.status_code == 409
    active_conflict = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "start-2"},
        json={"revision_id": current_revision_id},
    )
    assert active_conflict.status_code == 409


def test_run_requires_a_successful_current_conversion_after_sidecar_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    state_root = tmp_path / "state"
    client = _client(state_root, provider=FakeConversionProvider())
    revision_id = _prepare_saved_revision(client)

    restarted = _client(state_root)
    snapshot = restarted.get("/v1/discovery", headers=_headers()).json()
    assert snapshot["preparation"]["conversion"]["status"] == "pending"
    rejected = restarted.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "restart-gate"},
        json={"revision_id": revision_id},
    )
    assert rejected.status_code == 422
    assert "successful current Conversion" in rejected.json()["detail"]


def test_stop_is_graceful_and_resume_appends_one_idempotent_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    client = _client(tmp_path / "state", provider=FakeConversionProvider())
    revision_id = _prepare_saved_revision(client)
    started = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "stop-start"},
        json={"revision_id": revision_id},
    )
    launch_id = started.json()["launch_id"]

    stopped = client.post(
        f"/v1/discovery/launches/{launch_id}/stop", headers=_headers()
    )
    assert stopped.status_code == 200
    for _ in range(60):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        if snapshot["history"] and snapshot["history"][0]["launch_id"] == launch_id:
            break
        time.sleep(0.01)
    history = snapshot["history"][0]
    assert history["state"] == "stopped"
    assert history["resumable"] is True
    assert history["checkpoint"]["round"] >= 0

    repeated_stop = client.post(
        f"/v1/discovery/launches/{launch_id}/stop", headers=_headers()
    )
    assert repeated_stop.status_code == 200
    assert repeated_stop.json()["history"][0]["state"] == "stopped"

    resumed = client.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers={**_headers(), "Idempotency-Key": "resume-1"},
    )
    assert resumed.status_code == 201
    assert resumed.json()["launch_id"] == launch_id
    assert len(resumed.json()["snapshot"]["current_launch"]["attempts"]) == 2
    retry = client.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers={**_headers(), "Idempotency-Key": "resume-1"},
    )
    assert retry.status_code == 201
    assert len(retry.json()["snapshot"]["current_launch"]["attempts"]) == 2

    for _ in range(80):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        if snapshot["history"] and snapshot["history"][0]["state"] == "completed":
            break
        time.sleep(0.01)
    assert snapshot["history"][0]["launch_id"] == launch_id
    assert len(snapshot["history"][0]["attempts"]) == 2
    terminal_resume = client.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers={**_headers(), "Idempotency-Key": "resume-terminal"},
    )
    assert terminal_resume.status_code == 409


def test_restart_adopts_matching_live_runner_without_auto_resume(tmp_path, monkeypatch):
    # Keep this lifecycle probe active while the second sidecar instance starts.
    # The normal deterministic runner is intentionally short for the rest of the suite.
    monkeypatch.setattr(discovery_launch_module, "FAKE_RUNNER_DELAY_SECONDS", 2.0)
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    state_root = tmp_path / "state"
    client = _client(state_root, provider=FakeConversionProvider())
    revision_id = _prepare_saved_revision(client)
    started = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "adopt-start"},
        json={"revision_id": revision_id},
    )
    launch_id = started.json()["launch_id"]

    restarted = _client(state_root)
    adopted = restarted.get("/v1/discovery", headers=_headers()).json()
    assert adopted["current_launch"]["launch_id"] == launch_id
    assert adopted["current_launch"]["state"] in {"starting", "running"}
    assert len(adopted["current_launch"]["attempts"]) == 1

    for _ in range(800):
        adopted = restarted.get("/v1/discovery", headers=_headers()).json()
        if adopted["history"] and adopted["history"][0]["state"] == "completed":
            break
        time.sleep(0.01)
    assert adopted["history"][0]["launch_id"] == launch_id


def test_missing_runner_reconciles_to_interrupted_and_preserves_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    state_root = tmp_path / "state"
    client = _client(state_root, provider=FakeConversionProvider())
    revision_id = _prepare_saved_revision(client)
    started = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "interrupt-start"},
        json={"revision_id": revision_id},
    )
    launch_id = started.json()["launch_id"]
    launch_dir = state_root / "discovery" / "launches" / launch_id
    for _ in range(60):
        current = client.get("/v1/discovery", headers=_headers()).json()["current_launch"]
        if current and current["checkpoint"]:
            break
        time.sleep(0.01)
    record = json.loads((launch_dir / "record.json").read_text(encoding="utf-8"))
    index = json.loads(
        (state_root / "discovery" / "launches" / "index.json").read_text(encoding="utf-8")
    )
    record["state"] = "running"
    record["runner_pid"] = 999999
    index["active_launch_id"] = launch_id
    (launch_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")
    (state_root / "discovery" / "launches" / "index.json").write_text(
        json.dumps(index), encoding="utf-8"
    )
    (launch_dir / "runner.json").unlink(missing_ok=True)

    restarted = _client(state_root)
    reconciled = restarted.get("/v1/discovery", headers=_headers()).json()
    assert reconciled["current_launch"] is None
    assert reconciled["history"][0]["state"] == "interrupted"
    assert reconciled["history"][0]["resumable"] is True
    assert reconciled["history"][0]["checkpoint"] is not None
    resumed = restarted.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers={**_headers(), "Idempotency-Key": "interrupt-resume"},
    )
    assert resumed.status_code == 201
    assert resumed.json()["launch_id"] == launch_id


def test_failed_launch_is_read_only_history(tmp_path, monkeypatch):
    monkeypatch.setattr(
        discovery_module,
        "DISCOVERY_INPUT_CONVERSION_PROMPT_PATH",
        tmp_path / "conversion-prompt.yaml",
    )
    (tmp_path / "conversion-prompt.yaml").write_text(
        "instruction: Convert the evidence.\n", encoding="utf-8"
    )
    state_root = tmp_path / "state"
    manager = SessionManager(
        data_dir=state_root,
        provider=FakeConversionProvider(),
        model_settings={"__discovery_fake_failure_stage": "research"},
    )
    client = TestClient(create_app(manager))
    revision_id = _prepare_saved_revision(client)
    started = client.post(
        "/v1/discovery/launches",
        headers={**_headers(), "Idempotency-Key": "failed-start"},
        json={"revision_id": revision_id},
    )
    launch_id = started.json()["launch_id"]
    for _ in range(80):
        snapshot = client.get("/v1/discovery", headers=_headers()).json()
        if snapshot["history"] and snapshot["history"][0]["state"] == "failed":
            break
        time.sleep(0.01)
    assert snapshot["history"][0]["launch_id"] == launch_id
    assert snapshot["history"][0]["state"] == "failed"
    assert snapshot["history"][0]["resumable"] is False
    rejected = client.post(
        f"/v1/discovery/launches/{launch_id}/resume",
        headers={**_headers(), "Idempotency-Key": "failed-resume"},
    )
    assert rejected.status_code == 409


def test_launch_admission_is_serialized_by_the_durable_lock(tmp_path):
    root = tmp_path / "discovery"
    stores = [DiscoveryLaunchStore(root), DiscoveryLaunchStore(root)]
    outcomes: list[str] = []

    def admit(store: DiscoveryLaunchStore, key: str):
        try:
            store.admit(
                request_fingerprint=key,
                idempotency_key=key,
                input_snapshot={"preparation_id": "preparation", "revision_id": key},
                configuration_snapshot={"model_id": "test", "settings": {}},
                response_builder=dict,
            )
        except RuntimeError as error:
            outcomes.append(type(error).__name__)
        else:
            outcomes.append("admitted")

    threads = [
        threading.Thread(target=admit, args=(stores[index], f"race-{index}"))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ActiveLaunchConflict", "admitted"]
