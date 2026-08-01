"""Native Desktop Discovery Preparation intake and persistence contracts."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.providers.base import AssistantTurn
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
    def __init__(self, text: str = "# Converted input"):
        self.text = text
        self.calls: list[dict] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append({"model": model, "messages": messages, "settings": settings})
        return AssistantTurn(text=self.text)

    def capabilities(self, model):
        del model
        return None


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


def test_conversion_is_explicit_and_saved_revisions_are_immutable(tmp_path, monkeypatch):
    provider = FakeConversionProvider("# Converted once")
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
    assert conversion["draft"] == "# Converted once"
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
        json={"formatted_input": "# Reviewed once"},
    )
    assert first.status_code == 200
    first_revision = first.json()["preparation"]["revisions"][0]
    assert first_revision["formatted_input"] == "# Reviewed once"
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
        json={"formatted_input": "# Reviewed twice"},
    )
    revisions = second.json()["preparation"]["revisions"]
    assert [revision["formatted_input"] for revision in revisions] == [
        "# Reviewed once",
        "# Reviewed twice",
    ]
    assert revisions[0]["revision_id"] != revisions[1]["revision_id"]

    restored = _client(state_root).get("/v1/discovery", headers=_headers()).json()
    assert [revision["formatted_input"] for revision in restored["preparation"]["revisions"]] == [
        "# Reviewed once",
        "# Reviewed twice",
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
    provider = FakeConversionProvider("# First conversion")
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
        json={"formatted_input": "# Reviewed input"},
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
