"""BabelDOC document translation: settings, documents, runs, bundling, and routes.

Every run here is driven by a fake translation engine passed into the real
``run_translation`` seam, so no model is ever called while the bundling,
cancellation, and state-projection code under test is the production code.

The behaviour this module guards above all is the integration's one deviation from
upstream BabelDOC: a finished run leaves the original document and every artifact in
one folder created next to the original.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server.translation import (
    DEFAULT_TRANSLATION_SETTINGS,
    STAGE_NAMES,
    TRANSLATE_STAGE_TABLE,
    TranslationArtifactError,
    TranslationFacade,
    TranslationSettings,
    TranslationValidationError,
    bundle_dir_for,
    unique_path,
)
from coworker.server.translation_worker import run_translation

TOKEN = "a" * 64
TERMINAL = {"done", "error", "cancelled"}


# -- fixtures and fakes ----------------------------------------------------------


def _pdf_bytes(pages: int = 2) -> bytes:
    """A real, small PDF so page counting and PDF probing exercise real code."""
    import pymupdf

    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"Fixture page {index + 1}")
    payload = document.tobytes()
    document.close()
    return payload


class FakeTranslateResult:
    """The attribute surface ``_serialize_result`` reads off a BabelDOC result."""

    def __init__(self, mono: Path, dual: Path, glossary: Path | None = None):
        self.original_pdf_path = None
        self.mono_pdf_path = mono
        self.dual_pdf_path = dual
        self.no_watermark_mono_pdf_path = None
        self.no_watermark_dual_pdf_path = None
        self.auto_extracted_glossary_path = glossary
        self.total_seconds = 1.25
        self.peak_memory_usage = 4096
        self.total_valid_character_count = 128
        self.total_valid_text_token_count = 64


def _stage_events(stage: str, total: int, base_progress: float):
    """The exact event shapes babeldoc's progress monitor emits for one stage."""
    yield {
        "type": "progress_start",
        "stage": stage,
        "stage_progress": 0.0,
        "stage_current": 0,
        "stage_total": total,
        "overall_progress": base_progress,
    }
    yield {
        "type": "progress_update",
        "stage": stage,
        "stage_progress": 50.0,
        "stage_current": total // 2,
        "stage_total": total,
        "overall_progress": base_progress + 2.0,
    }
    yield {
        "type": "progress_end",
        "stage": stage,
        "stage_progress": 100.0,
        "stage_current": total,
        "stage_total": total,
        "overall_progress": base_progress + 5.0,
    }


async def fake_engine(values, source_path: Path, bundle_dir: Path, log):
    """Write plausible outputs into ``bundle_dir`` and report BabelDOC's events."""
    log(f"[fake] translating {source_path.name}")
    stem = source_path.stem
    lang_out = values.get("lang_out") or "zh"
    mono = bundle_dir / f"{stem}.{lang_out}.mono.pdf"
    dual = bundle_dir / f"{stem}.{lang_out}.dual.pdf"
    glossary = bundle_dir / f"{stem}.glossary.csv"
    mono.write_bytes(_pdf_bytes(1))
    dual.write_bytes(_pdf_bytes(2))
    glossary.write_text("term,translation\nmodel,模型\n", encoding="utf-8")

    for index, stage in enumerate(STAGE_NAMES[:3]):
        for event in _stage_events(stage, 4, base_progress=index * 10.0):
            yield event
    log("[fake] outputs written")
    yield {
        "type": "finish",
        "translate_result": FakeTranslateResult(mono, dual, glossary),
    }


async def failing_engine(values, source_path, bundle_dir, log):
    del values, source_path, bundle_dir
    log("[fake] failing on purpose")
    for event in _stage_events(STAGE_NAMES[0], 2, base_progress=0.0):
        yield event
    yield {"type": "error", "error": "fake engine could not reach the model"}


async def resultless_engine(values, source_path, bundle_dir, log):
    del values, source_path, bundle_dir, log
    for event in _stage_events(STAGE_NAMES[0], 1, base_progress=0.0):
        yield event


async def streaming_engine(values, source_path, bundle_dir, log):
    """Keep emitting progress so a cancel can land while the run is running."""
    del values, source_path, bundle_dir
    log("[fake] streaming until cancelled")
    for _ in range(4000):
        yield {
            "type": "progress_update",
            "stage": STAGE_NAMES[0],
            "stage_progress": 1.0,
            "stage_current": 1,
            "stage_total": 100,
            "overall_progress": 1.0,
        }
        await asyncio.sleep(0.005)
    yield {"type": "error", "error": "fake engine was never cancelled"}


def _facade(tmp_path: Path, engine=fake_engine, *, gate: threading.Event | None = None):
    def runner(run_dir: Path) -> None:
        if gate is not None:
            assert gate.wait(timeout=20), "gate was never released"
        run_translation(run_dir, engine)

    return TranslationFacade(tmp_path / "data", runner=runner)


def _await_state(facade: TranslationFacade, run_id: str, states, timeout: float = 30.0):
    deadline = time.monotonic() + timeout
    snapshot = facade.run(run_id)
    while snapshot["state"] not in states:
        assert time.monotonic() < deadline, f"run stuck in {snapshot['state']}"
        time.sleep(0.005)
        snapshot = facade.run(run_id)
    return snapshot


def _register_upload(facade: TranslationFacade, filename: str = "paper.pdf", pages: int = 2):
    content = _pdf_bytes(pages)
    response = facade.register_documents(
        {
            "files": [
                {
                    "filename": filename,
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "size": len(content),
                }
            ]
        }
    )
    return response["documents"][0], content


def _run_to_completion(facade: TranslationFacade, document_id: str, **body):
    created = facade.start_runs({"document_ids": [document_id], **body})
    run_id = created["runs"][0]["run_id"]
    return _await_state(facade, run_id, TERMINAL)


# -- settings --------------------------------------------------------------------


def test_settings_document_describes_every_parameter_it_offers(tmp_path):
    facade = _facade(tmp_path)
    document = facade.settings_document()

    assert document["schema_version"] == TranslationSettings.schema_version
    assert document["values"] == DEFAULT_TRANSLATION_SETTINGS
    assert document["defaults"] == DEFAULT_TRANSLATION_SETTINGS
    # Every editable value is described, and nothing is described that is not editable.
    assert set(document["parameters"]) == set(DEFAULT_TRANSLATION_SETTINGS)
    for key, definition in document["parameters"].items():
        assert definition["type"] in {"string", "integer", "number", "boolean", "enum"}
        assert definition["description"].strip()
        if definition["type"] in {"integer", "number"}:
            assert definition["minimum"] <= definition["maximum"]
            assert definition["minimum"] <= DEFAULT_TRANSLATION_SETTINGS[key] <= definition["maximum"]
        if definition["type"] == "enum":
            assert DEFAULT_TRANSLATION_SETTINGS[key] in definition["values"]


def test_saving_part_of_the_document_merges_and_survives_a_reload(tmp_path):
    facade = _facade(tmp_path)

    saved = facade.save_settings({"values": {"lang_out": "ja", "qps": 9}})

    assert saved["values"]["lang_out"] == "ja"
    assert saved["values"]["qps"] == 9
    untouched = {k: v for k, v in DEFAULT_TRANSLATION_SETTINGS.items() if k not in {"lang_out", "qps"}}
    assert {k: saved["values"][k] for k in untouched} == untouched
    assert saved["defaults"]["lang_out"] == DEFAULT_TRANSLATION_SETTINGS["lang_out"]

    reloaded = TranslationSettings(tmp_path / "data" / "translation" / "settings.json")
    assert reloaded.get() == saved["values"]


def test_settings_reject_wrong_types_out_of_range_and_bad_enums(tmp_path):
    facade = _facade(tmp_path)

    with pytest.raises(TranslationValidationError) as wrong_type:
        facade.save_settings({"values": {"ignore_cache": "yes", "qps": "fast"}})
    assert {v["path"] for v in wrong_type.value.violations} == {"ignore_cache", "qps"}

    with pytest.raises(TranslationValidationError) as out_of_range:
        facade.save_settings({"values": {"qps": 0, "short_line_split_factor": 5.0}})
    assert {v["path"] for v in out_of_range.value.violations} == {"qps", "short_line_split_factor"}
    assert all("between" in v["message"] for v in out_of_range.value.violations)

    with pytest.raises(TranslationValidationError) as bad_enum:
        facade.save_settings({"values": {"watermark_output_mode": "sometimes"}})
    assert [v["path"] for v in bad_enum.value.violations] == ["watermark_output_mode"]

    with pytest.raises(TranslationValidationError) as bad_pages:
        facade.save_settings({"values": {"pages": "one to five"}})
    assert [v["path"] for v in bad_pages.value.violations] == ["pages"]

    with pytest.raises(TranslationValidationError) as empty_required:
        facade.save_settings({"values": {"lang_in": "   "}})
    assert [v["path"] for v in empty_required.value.violations] == ["lang_in"]

    # A rejected save leaves the stored document untouched.
    assert facade.settings_document()["values"] == DEFAULT_TRANSLATION_SETTINGS


def test_settings_reject_unknown_fields_and_foreign_schema_versions(tmp_path):
    facade = _facade(tmp_path)

    with pytest.raises(TranslationValidationError) as unknown_value:
        facade.save_settings({"values": {"turbo_mode": True}})
    assert [v["path"] for v in unknown_value.value.violations] == ["turbo_mode"]

    with pytest.raises(TranslationValidationError) as unknown_field:
        facade.save_settings({"values": {"lang_out": "ja"}, "sneaky": 1})
    assert [v["path"] for v in unknown_field.value.violations] == ["sneaky"]

    with pytest.raises(TranslationValidationError) as version:
        facade.save_settings({"schema_version": 99, "values": {"lang_out": "ja"}})
    assert [v["path"] for v in version.value.violations] == ["schema_version"]

    assert facade.settings_document()["values"] == DEFAULT_TRANSLATION_SETTINGS


def test_run_overrides_are_validated_without_touching_stored_settings(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)

    with pytest.raises(TranslationValidationError):
        facade.start_runs({"document_ids": [document["document_id"]], "overrides": {"qps": 999}})

    snapshot = _run_to_completion(facade, document["document_id"], overrides={"lang_out": "de"})
    assert snapshot["lang_out"] == "de"
    assert facade.settings_document()["values"]["lang_out"] == DEFAULT_TRANSLATION_SETTINGS["lang_out"]


def test_stage_table_matches_the_installed_babeldoc_table():
    high_level = pytest.importorskip("babeldoc.format.pdf.high_level")

    assert tuple(tuple(entry) for entry in high_level.TRANSLATE_STAGES) == TRANSLATE_STAGE_TABLE


# -- documents -------------------------------------------------------------------


def test_uploaded_bytes_are_staged_with_digest_size_pages_and_bundle_dir(tmp_path):
    facade = _facade(tmp_path)
    document, content = _register_upload(facade, pages=3)

    source_path = Path(document["source_path"])
    assert source_path.is_file()
    assert source_path.read_bytes() == content
    assert document["filename"] == "paper.pdf"
    assert document["size"] == len(content)
    assert document["sha256"] == hashlib.sha256(content).hexdigest()
    assert document["pages"] == 3
    assert document["bundle_dir"] == str(source_path.parent / "paper")
    assert facade.list_documents()["documents"] == [document]


def test_absolute_local_paths_are_registered_where_the_user_keeps_them(tmp_path):
    facade = _facade(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "thesis.pdf"
    original.write_bytes(_pdf_bytes(2))

    document = facade.register_documents({"paths": [str(original)]})["documents"][0]

    assert document["source_path"] == str(original)
    assert document["sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert document["size"] == original.stat().st_size
    assert document["pages"] == 2
    # The bundle folder is derived from where the document already lives.
    assert document["bundle_dir"] == str(library / "thesis")
    assert bundle_dir_for(original, "thesis.pdf") == library / "thesis"


def test_documents_reject_non_pdf_missing_relative_and_escaping_names(tmp_path):
    facade = _facade(tmp_path)
    notes = tmp_path / "notes.txt"
    notes.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(TranslationValidationError, match="unsupported document type"):
        facade.register_documents({"paths": [str(notes)]})
    with pytest.raises(TranslationValidationError, match="unsupported document type"):
        facade.register_documents(
            {"files": [{"filename": "notes.txt", "content_base64": "aGk=", "size": 2}]}
        )
    with pytest.raises(TranslationValidationError, match="not found"):
        facade.register_documents({"paths": [str(tmp_path / "ghost.pdf")]})
    with pytest.raises(TranslationValidationError, match="absolute"):
        facade.register_documents({"paths": ["library/thesis.pdf"]})
    with pytest.raises(TranslationValidationError, match="bare file name"):
        facade.register_documents(
            {"files": [{"filename": "../../escape.pdf", "content_base64": "aGk=", "size": 2}]}
        )
    with pytest.raises(TranslationValidationError, match="at least one"):
        facade.register_documents({})

    assert facade.list_documents()["documents"] == []


def test_uploads_reject_a_size_that_disagrees_with_the_bytes(tmp_path):
    facade = _facade(tmp_path)
    content = _pdf_bytes(1)

    with pytest.raises(TranslationValidationError, match="do not match"):
        facade.register_documents(
            {
                "files": [
                    {
                        "filename": "paper.pdf",
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "size": len(content) + 1,
                    }
                ]
            }
        )
    with pytest.raises(TranslationValidationError, match="valid base64"):
        facade.register_documents(
            {"files": [{"filename": "paper.pdf", "content_base64": "not base64!", "size": 4}]}
        )


def test_starting_a_run_for_an_unknown_document_is_refused(tmp_path):
    facade = _facade(tmp_path)

    with pytest.raises(TranslationValidationError) as error:
        facade.start_runs({"document_ids": ["deadbeef"]})
    assert [v["path"] for v in error.value.violations] == ["document_ids"]

    with pytest.raises(TranslationValidationError):
        facade.start_runs({"document_ids": []})


# -- run lifecycle ---------------------------------------------------------------


def test_a_run_walks_queued_to_running_to_done_with_monotonic_progress(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)

    created = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]
    assert created["state"] == "queued"
    assert created["stage_index"] == -1
    assert created["overall_progress"] == 0.0
    assert created["stage_total_count"] == len(TRANSLATE_STAGE_TABLE)
    assert [stage["name"] for stage in created["stages"]] == list(STAGE_NAMES)

    snapshot = _await_state(facade, created["run_id"], TERMINAL)

    assert snapshot["state"] == "done"
    assert snapshot["error"] is None
    assert snapshot["overall_progress"] == 100.0
    assert snapshot["started_at"] is not None and snapshot["finished_at"] is not None
    assert snapshot["finished_at"] >= snapshot["started_at"]
    assert snapshot["elapsed_seconds"] >= 0.0
    assert snapshot["result"]["bundle_dir"] == snapshot["bundle_dir"]
    assert facade.list_runs()["runs"][0]["run_id"] == created["run_id"]

    page = facade.events(created["run_id"])
    kinds = [event["type"] for event in page["events"]]
    assert kinds[0] == "run.queued"
    assert kinds[1] == "run.started"
    assert kinds[-1] == "finish"
    assert "progress_start" in kinds and "progress_end" in kinds

    sequences = [event["sequence"] for event in page["events"]]
    assert sequences == sorted(sequences) == list(range(1, len(sequences) + 1))
    assert page["latest_sequence"] == sequences[-1]
    assert page["oldest_sequence"] == 1

    progress = [event for event in page["events"] if event["type"].startswith("progress_")]
    overall = [event["overall_progress"] for event in progress]
    assert overall == sorted(overall)
    for event in progress:
        assert event["stage"] in STAGE_NAMES
        assert event["stage_index"] == STAGE_NAMES.index(event["stage"])
    assert [event["stage"] for event in progress if event["type"] == "progress_start"] == list(
        STAGE_NAMES[:3]
    )


def test_the_event_cursor_only_replays_what_the_caller_has_not_seen(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)
    snapshot = _run_to_completion(facade, document["document_id"])
    run_id = snapshot["run_id"]

    everything = facade.events(run_id)
    latest = everything["latest_sequence"]
    assert latest > 2

    tail = facade.events(run_id, after=2)
    assert [event["sequence"] for event in tail["events"]] == list(range(3, latest + 1))
    assert tail["latest_sequence"] == latest
    assert tail["truncated_before_sequence"] == 2

    drained = facade.events(run_id, after=latest)
    assert drained["events"] == []
    assert drained["latest_sequence"] == latest
    assert drained["oldest_sequence"] is None


def test_unknown_run_ids_are_not_addressable(tmp_path):
    facade = _facade(tmp_path)

    for candidate in ["0" * 32, "not-a-run", "../../etc", ""]:
        with pytest.raises(KeyError):
            facade.run(candidate)
        with pytest.raises(KeyError):
            facade.events(candidate)
        with pytest.raises(KeyError):
            facade.cancel(candidate)


# -- bundling: the integration's own invariant -----------------------------------


def test_a_finished_run_bundles_the_original_and_every_artifact_in_one_folder(tmp_path):
    facade = _facade(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "thesis.pdf"
    original.write_bytes(_pdf_bytes(2))
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    document = facade.register_documents({"paths": [str(original)]})["documents"][0]

    snapshot = _run_to_completion(facade, document["document_id"])
    assert snapshot["state"] == "done"

    bundle = Path(snapshot["bundle_dir"])
    # The bundle is an absolute sibling of where the user kept the document.
    assert bundle.is_absolute()
    assert bundle == library / "thesis"
    assert bundle.parent == original.parent
    assert not original.exists()  # the original moved into the bundle

    names = sorted(entry.name for entry in bundle.iterdir())
    assert names == [
        "thesis.glossary.csv",
        "thesis.pdf",
        "thesis.zh.dual.pdf",
        "thesis.zh.mono.pdf",
    ]
    assert hashlib.sha256((bundle / "thesis.pdf").read_bytes()).hexdigest() == digest

    assert snapshot["source_path"] == str(bundle / "thesis.pdf")
    assert snapshot["result"]["original_pdf_path"] == str(bundle / "thesis.pdf")
    assert Path(snapshot["result"]["mono_pdf_path"]).parent == bundle
    assert Path(snapshot["result"]["dual_pdf_path"]).parent == bundle

    roles = {artifact["name"]: artifact["role"] for artifact in snapshot["artifacts"]}
    assert roles["thesis.pdf"] == "source"
    assert roles["thesis.zh.mono.pdf"] == "mono"
    assert roles["thesis.zh.dual.pdf"] == "dual"
    assert roles["thesis.glossary.csv"] == "glossary"
    assert roles["runner.log"] == "log"
    assert all(artifact["size"] > 0 for artifact in snapshot["artifacts"])

    # The document list follows the original into the bundle.
    listed = facade.list_documents()["documents"][0]
    assert listed["source_path"] == str(bundle / "thesis.pdf")
    assert listed["bundle_dir"] == str(bundle)


def test_bundling_never_overwrites_a_file_the_user_already_had(tmp_path):
    facade = _facade(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "thesis.pdf"
    original.write_bytes(_pdf_bytes(2))
    # A bundle folder from an earlier session, already holding a same-named document.
    bundle = library / "thesis"
    bundle.mkdir()
    (bundle / "thesis.pdf").write_text("precious earlier copy", encoding="utf-8")
    document = facade.register_documents({"paths": [str(original)]})["documents"][0]

    snapshot = _run_to_completion(facade, document["document_id"])

    assert snapshot["state"] == "done"
    assert Path(snapshot["bundle_dir"]) == bundle
    assert (bundle / "thesis.pdf").read_text(encoding="utf-8") == "precious earlier copy"
    assert snapshot["source_path"] == str(bundle / "thesis (2).pdf")
    assert (bundle / "thesis (2).pdf").is_file()
    assert unique_path(bundle / "thesis.pdf") == bundle / "thesis (3).pdf"


def test_a_file_squatting_on_the_bundle_name_forces_a_numbered_bundle(tmp_path):
    facade = _facade(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "thesis.pdf"
    original.write_bytes(_pdf_bytes(1))
    squatter = library / "thesis"  # a plain file where the bundle folder wants to be
    squatter.write_text("unrelated user file", encoding="utf-8")
    document = facade.register_documents({"paths": [str(original)]})["documents"][0]

    snapshot = _run_to_completion(facade, document["document_id"])

    assert snapshot["state"] == "done"
    assert squatter.is_file()
    assert squatter.read_text(encoding="utf-8") == "unrelated user file"
    bundle = Path(snapshot["bundle_dir"])
    assert bundle == library / "thesis (2)"
    assert bundle.is_dir()
    # The run still reports the artifacts it actually produced.
    names = {artifact["name"] for artifact in snapshot["artifacts"]}
    assert {"thesis.pdf", "thesis.zh.mono.pdf", "thesis.zh.dual.pdf"} <= names
    assert facade.artifact_path(snapshot["run_id"], "thesis.zh.mono.pdf").parent == bundle


def test_two_runs_of_one_document_share_the_bundle_without_losing_the_original(tmp_path):
    facade = _facade(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    original = library / "thesis.pdf"
    original.write_bytes(_pdf_bytes(1))
    document = facade.register_documents({"paths": [str(original)]})["documents"][0]

    first = _run_to_completion(facade, document["document_id"])
    second = _run_to_completion(facade, document["document_id"])

    assert first["state"] == second["state"] == "done"
    bundle = Path(first["bundle_dir"])
    assert Path(second["bundle_dir"]) == bundle
    # The original is in the bundle exactly once; the second run found it already there.
    originals = sorted(p.name for p in bundle.glob("thesis*.pdf") if ".zh." not in p.name)
    assert originals == ["thesis.pdf"]
    assert second["source_path"] == str(bundle / "thesis.pdf")


# -- failure and cancellation ----------------------------------------------------


def test_an_engine_error_ends_the_run_in_error_with_the_reason(tmp_path):
    facade = _facade(tmp_path, failing_engine)
    document, _ = _register_upload(facade)
    library_source = Path(document["source_path"])

    snapshot = _run_to_completion(facade, document["document_id"])

    assert snapshot["state"] == "error"
    assert snapshot["error"] == "fake engine could not reach the model"
    assert snapshot["result"] is None
    assert snapshot["finished_at"] is not None
    # A failed run must not bundle: the original stays where it was.
    assert library_source.is_file()
    assert snapshot["source_path"] == str(library_source)

    events = facade.events(snapshot["run_id"])["events"]
    assert events[-1]["type"] == "error"
    assert events[-1]["error"] == "fake engine could not reach the model"


def test_an_engine_that_finishes_without_a_result_is_an_error_not_a_success(tmp_path):
    facade = _facade(tmp_path, resultless_engine)
    document, _ = _register_upload(facade)

    snapshot = _run_to_completion(facade, document["document_id"])

    assert snapshot["state"] == "error"
    assert snapshot["error"] == "translation finished without a result"


def test_cancelling_a_running_run_stops_it_and_stops_its_events(tmp_path):
    facade = _facade(tmp_path, streaming_engine)
    document, _ = _register_upload(facade)
    source_path = Path(document["source_path"])
    run_id = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]["run_id"]
    _await_state(facade, run_id, {"running"} | TERMINAL)

    facade.cancel(run_id)
    snapshot = _await_state(facade, run_id, TERMINAL)

    assert snapshot["state"] == "cancelled"
    assert snapshot["stage"] is None
    assert snapshot["error"] is None
    assert snapshot["result"] is None
    assert source_path.is_file()  # a cancelled run does not bundle

    events = facade.events(run_id)["events"]
    assert events[-1]["type"] == "run.cancelled"
    settled = facade.events(run_id)["latest_sequence"]
    time.sleep(0.2)
    assert facade.events(run_id)["latest_sequence"] == settled
    assert facade.cancel(run_id)["state"] == "cancelled"  # cancelling twice is harmless


def test_cancelling_a_queued_run_never_starts_it(tmp_path):
    gate = threading.Event()
    facade = _facade(tmp_path, gate=gate)
    first, _ = _register_upload(facade, filename="first.pdf")
    second, _ = _register_upload(facade, filename="second.pdf")

    blocking = facade.start_runs({"document_ids": [first["document_id"]]})["runs"][0]["run_id"]
    queued = facade.start_runs({"document_ids": [second["document_id"]]})["runs"][0]["run_id"]

    cancelled = facade.cancel(queued)
    assert cancelled["state"] == "cancelled"
    assert cancelled["started_at"] is None
    events = facade.events(queued)["events"]
    assert [event["type"] for event in events] == ["run.queued", "run.cancelled"]
    assert Path(second["source_path"]).is_file()
    assert not Path(second["bundle_dir"]).exists()

    gate.set()
    assert _await_state(facade, blocking, TERMINAL)["state"] == "done"
    assert facade.run(queued)["state"] == "cancelled"


def _dead_pid() -> int:
    """A pid that is certainly not running: spawn a process, then reap it."""
    import subprocess

    process = subprocess.Popen(["true"])
    process.wait()
    return process.pid


def _abandoning_runner(cancel: bool):
    """A runner that dies the way SIGKILL does: `running` on disk, no terminal state."""

    def runner(run_dir: Path) -> None:
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        state.update(state="running", pid=_dead_pid(), started_at=time.time())
        (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        if cancel:
            (run_dir / "cancel").write_text(str(time.time()), encoding="utf-8")

    return runner


def test_a_run_whose_worker_died_is_reported_as_failed_not_running(tmp_path):
    """Only the worker writes state, so a worker killed mid-run would otherwise leave the run
    reading `running` forever — unfinishable, uncancellable, and never reporting a result."""
    facade = TranslationFacade(tmp_path / "data", runner=_abandoning_runner(cancel=False))
    document, _ = _register_upload(facade)

    run_id = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]["run_id"]
    snapshot = _await_state(facade, run_id, TERMINAL)

    assert snapshot["state"] == "error"
    assert snapshot["error"] == "the translation worker stopped without finishing"
    assert snapshot["finished_at"] is not None
    assert snapshot["stage"] is None
    # Settled once and for all — the projection must not keep rewriting it.
    assert facade.events(run_id)["events"][-1]["type"] == "error"
    settled = facade.events(run_id)["latest_sequence"]
    assert facade.run(run_id)["state"] == "error"
    assert facade.events(run_id)["latest_sequence"] == settled


def test_a_cancelled_run_whose_worker_died_is_reported_as_cancelled(tmp_path):
    facade = TranslationFacade(tmp_path / "data", runner=_abandoning_runner(cancel=True))
    document, _ = _register_upload(facade)

    run_id = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]["run_id"]
    snapshot = _await_state(facade, run_id, TERMINAL)

    assert snapshot["state"] == "cancelled"
    assert snapshot["error"] is None
    assert facade.events(run_id)["events"][-1]["type"] == "run.cancelled"


def test_an_abandoned_run_can_still_be_deleted_with_its_document(tmp_path):
    facade = TranslationFacade(tmp_path / "data", runner=_abandoning_runner(cancel=False))
    document, _ = _register_upload(facade)
    run_id = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]["run_id"]
    _await_state(facade, run_id, TERMINAL)

    removed = facade.forget_document(document["document_id"])

    assert removed["removed_runs"] == 1
    assert removed["source_deleted"] is True
    assert facade.list_documents()["documents"] == []


# -- artifacts -------------------------------------------------------------------


def test_artifact_names_cannot_escape_the_runs_own_bundle(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)
    snapshot = _run_to_completion(facade, document["document_id"])
    run_id = snapshot["run_id"]
    outsider = tmp_path / "secret.pdf"
    outsider.write_bytes(_pdf_bytes(1))

    wanted = facade.artifact_path(run_id, "paper.zh.mono.pdf")
    assert wanted.is_file()
    assert wanted.parent == Path(snapshot["bundle_dir"])
    assert facade.artifact_path(run_id, "runner.log").is_file()

    for name in [
        "../paper.pdf",
        "../../etc/passwd",
        "..",
        ".",
        str(outsider),
        "/etc/passwd",
        "sub/paper.pdf",
        "paper.zh.mono.pdf\x00",
        "",
        "never-produced.pdf",
    ]:
        with pytest.raises(TranslationArtifactError):
            facade.artifact_path(run_id, name)


def test_an_artifact_of_another_run_is_not_reachable_through_this_one(tmp_path):
    facade = _facade(tmp_path)
    mine, _ = _register_upload(facade, filename="mine.pdf")
    theirs, _ = _register_upload(facade, filename="theirs.pdf")
    my_run = _run_to_completion(facade, mine["document_id"])
    their_run = _run_to_completion(facade, theirs["document_id"])

    assert facade.artifact_path(their_run["run_id"], "theirs.zh.mono.pdf").is_file()
    with pytest.raises(TranslationArtifactError):
        facade.artifact_path(my_run["run_id"], "theirs.zh.mono.pdf")


# -- HTTP surface ----------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_API_TOKEN", TOKEN)
    manager = SessionManager(data_dir=tmp_path / "state")
    app = create_app(manager)
    # Same facade, same worker core: only the runner seam is injected.
    app.state.translation = _facade(tmp_path)
    with TestClient(app) as running:
        yield running


def _headers() -> dict[str, str]:
    return {"X-OpenWorker-Token": TOKEN}


def test_translation_routes_carry_a_document_from_upload_to_download(client, tmp_path):
    assert client.get("/v1/translation/settings").status_code == 401

    settings = client.get("/v1/translation/settings", headers=_headers())
    assert settings.status_code == 200
    assert settings.json()["values"] == DEFAULT_TRANSLATION_SETTINGS

    saved = client.put(
        "/v1/translation/settings", headers=_headers(), json={"values": {"lang_out": "fr"}}
    )
    assert saved.status_code == 200
    assert saved.json()["values"]["lang_out"] == "fr"

    rejected = client.put(
        "/v1/translation/settings", headers=_headers(), json={"values": {"qps": 0}}
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["violations"][0]["path"] == "qps"

    content = _pdf_bytes(2)
    registered = client.post(
        "/v1/translation/documents",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "report.pdf",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "size": len(content),
                }
            ]
        },
    )
    assert registered.status_code == 200
    document = registered.json()["documents"][0]
    assert document["pages"] == 2
    assert client.get("/v1/translation/documents", headers=_headers()).json()["documents"] == [
        document
    ]

    started = client.post(
        "/v1/translation/runs",
        headers=_headers(),
        json={"document_ids": [document["document_id"]]},
    )
    assert started.status_code == 200
    run_id = started.json()["runs"][0]["run_id"]

    facade = client.app.state.translation
    snapshot = _await_state(facade, run_id, TERMINAL)
    assert snapshot["state"] == "done"

    fetched = client.get(f"/v1/translation/runs/{run_id}", headers=_headers())
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "done"
    assert fetched.json()["lang_out"] == "fr"
    assert run_id in {run["run_id"] for run in client.get("/v1/translation/runs", headers=_headers()).json()["runs"]}

    events = client.get(f"/v1/translation/runs/{run_id}/events", headers=_headers()).json()
    assert events["run_id"] == run_id
    assert events["events"][0]["type"] == "run.queued"
    latest = events["latest_sequence"]
    tail = client.get(
        f"/v1/translation/runs/{run_id}/events", headers=_headers(), params={"after": latest}
    ).json()
    assert tail["events"] == []

    bundle = Path(fetched.json()["bundle_dir"])
    assert bundle.is_dir()
    assert (bundle / "report.pdf").is_file()

    download = client.get(
        f"/v1/translation/runs/{run_id}/artifacts/report.fr.mono.pdf", headers=_headers()
    )
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == (bundle / "report.fr.mono.pdf").read_bytes()

    logs = client.get(f"/v1/translation/runs/{run_id}/logs/stream", headers=_headers())
    assert logs.status_code == 200
    assert "[fake] translating report.pdf" in logs.text


def test_missing_runs_and_artifacts_answer_404(client):
    unknown = "0" * 32
    assert client.get(f"/v1/translation/runs/{unknown}", headers=_headers()).status_code == 404
    assert client.get(f"/v1/translation/runs/{unknown}/events", headers=_headers()).status_code == 404
    assert client.post(f"/v1/translation/runs/{unknown}/cancel", headers=_headers()).status_code == 404
    assert (
        client.get(f"/v1/translation/runs/{unknown}/artifacts/x.pdf", headers=_headers()).status_code
        == 404
    )

    content = _pdf_bytes(1)
    document = client.post(
        "/v1/translation/documents",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "brief.pdf",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "size": len(content),
                }
            ]
        },
    ).json()["documents"][0]
    run_id = client.post(
        "/v1/translation/runs",
        headers=_headers(),
        json={"document_ids": [document["document_id"]]},
    ).json()["runs"][0]["run_id"]
    _await_state(client.app.state.translation, run_id, TERMINAL)

    assert (
        client.get(
            f"/v1/translation/runs/{run_id}/artifacts/never-made.pdf", headers=_headers()
        ).status_code
        == 404
    )
    # A traversal attempt never even resolves to the artifact route.
    assert (
        client.get(
            f"/v1/translation/runs/{run_id}/artifacts/..%2F..%2Fsettings.json",
            headers=_headers(),
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/v1/translation/runs", headers=_headers(), json={"document_ids": ["missing"]}
        ).status_code
        == 422
    )


def test_provider_setting_accepts_openai_compatible_names_and_rejects_the_rest(tmp_path):
    facade = _facade(tmp_path)

    # Empty is the default: keep reading the OpenAI slot, exactly as before this field existed.
    assert facade.settings_document()["values"]["provider"] == ""

    for name in ("openai", "deepseek", "ollama"):
        assert facade.save_settings({"values": {"provider": name}})["values"]["provider"] == name

    # A native-SDK provider cannot drive BabelDOC's OpenAI-only translator, so it is refused at
    # save time rather than failing halfway into a run.
    for name in ("anthropic", "gemini", "bedrock", "relay", "not-a-provider"):
        with pytest.raises(TranslationValidationError) as caught:
            facade.save_settings({"values": {"provider": name}})
        assert [v["path"] for v in caught.value.violations] == ["provider"]

    # The last valid save is what survives a rejected one.
    assert facade.settings_document()["values"]["provider"] == "ollama"


# -- removing a queue entry ------------------------------------------------------


def test_forgetting_an_upload_drops_its_runs_and_its_staged_copy(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)
    finished = _run_to_completion(facade, document["document_id"])
    assert finished["state"] == "done"
    staged_dir = Path(document["source_path"]).parent

    removal = facade.forget_document(document["document_id"])

    assert removal["filename"] == "paper.pdf"
    assert removal["removed_runs"] == 1
    # A finished run bundled artifacts beside the copy, so the folder holding the user's
    # translations survives even though the bookkeeping is gone.
    assert removal["source_deleted"] is False
    assert staged_dir.exists()
    assert facade.list_documents()["documents"] == []
    assert facade.list_runs()["runs"] == []
    with pytest.raises(KeyError):
        facade.run(finished["run_id"])


def test_forgetting_an_unrun_upload_deletes_the_copy_this_module_made(tmp_path):
    facade = _facade(tmp_path)
    document, _ = _register_upload(facade)
    staged_dir = Path(document["source_path"]).parent
    assert staged_dir.is_dir()

    removal = facade.forget_document(document["document_id"])

    # Nothing was ever produced beside it, so the staged copy is this module's alone to drop.
    assert removal["source_deleted"] is True
    assert removal["removed_runs"] == 0
    assert not staged_dir.exists()
    assert facade.list_documents()["documents"] == []


def test_forgetting_a_path_registered_document_never_touches_the_users_file(tmp_path):
    facade = _facade(tmp_path)
    original = tmp_path / "library" / "thesis.pdf"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(_pdf_bytes(3))
    registered = facade.register_documents({"paths": [str(original)]})["documents"][0]

    removal = facade.forget_document(registered["document_id"])

    assert removal["source_deleted"] is False
    assert original.is_file(), "a document the user keeps elsewhere is never deleted"
    assert facade.list_documents()["documents"] == []


def test_forgetting_a_document_cancels_a_run_still_working_on_it(tmp_path):
    facade = _facade(tmp_path, streaming_engine)
    document, _ = _register_upload(facade)
    run_id = facade.start_runs({"document_ids": [document["document_id"]]})["runs"][0]["run_id"]
    _await_state(facade, run_id, {"running"})

    removal = facade.forget_document(document["document_id"])

    assert removal["cancelled_runs"] == [run_id]
    assert removal["removed_runs"] == 1
    assert facade.list_documents()["documents"] == []
    assert not (tmp_path / "data" / "translation" / "runs" / run_id).exists()


def test_forgetting_leaves_other_documents_and_their_runs_alone(tmp_path):
    facade = _facade(tmp_path)
    keep, _ = _register_upload(facade, filename="keep.pdf")
    drop, _ = _register_upload(facade, filename="drop.pdf")
    kept_run = _run_to_completion(facade, keep["document_id"])
    _run_to_completion(facade, drop["document_id"])

    facade.forget_document(drop["document_id"])

    remaining = facade.list_documents()["documents"]
    assert [item["document_id"] for item in remaining] == [keep["document_id"]]
    assert facade.run(kept_run["run_id"])["state"] == "done"


def test_forgetting_an_unknown_document_is_a_lookup_failure(tmp_path):
    facade = _facade(tmp_path)
    with pytest.raises(KeyError):
        facade.forget_document("2" * 32)


def test_the_delete_route_removes_one_queue_entry_and_404s_on_the_rest(client, tmp_path):
    content = _pdf_bytes(1)
    registered = client.post(
        "/v1/translation/documents",
        headers=_headers(),
        json={
            "files": [
                {
                    "filename": "route.pdf",
                    "content_base64": base64.b64encode(content).decode("ascii"),
                    "size": len(content),
                }
            ]
        },
    ).json()["documents"][0]
    document_id = registered["document_id"]

    removed = client.delete(f"/v1/translation/documents/{document_id}", headers=_headers())
    assert removed.status_code == 200
    assert removed.json()["document_id"] == document_id
    assert client.get("/v1/translation/documents", headers=_headers()).json()["documents"] == []

    # Gone means gone: a second delete, and any unknown id, are both 404.
    assert client.delete(f"/v1/translation/documents/{document_id}", headers=_headers()).status_code == 404
    assert client.delete(f"/v1/translation/documents/{'3' * 32}", headers=_headers()).status_code == 404
