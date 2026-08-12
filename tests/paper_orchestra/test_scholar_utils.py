from __future__ import annotations

import importlib.util
import io
import os
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path


def _load_scholar_utils(monkeypatch, *, semantic_key: str | None, s2_key: str | None):
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *_args, **_kwargs: None
    fake_requests = types.ModuleType("requests")
    fake_requests.get = lambda *_args, **_kwargs: None
    fake_thefuzz = types.ModuleType("thefuzz")
    fake_thefuzz.fuzz = types.SimpleNamespace(ratio=lambda *_args: 100)

    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "thefuzz", fake_thefuzz)
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", semantic_key or "")
    monkeypatch.setenv("S2_API_KEY", s2_key or "")

    module_path = (
        Path(__file__).resolve().parents[2]
        / "third_party/paper_orchestra/utils/scholar_utils.py"
    )
    spec = importlib.util.spec_from_file_location(
        "paper_orchestra_test_scholar_utils", module_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    captured = io.StringIO()
    with redirect_stdout(captured):
        spec.loader.exec_module(module)
    return module, captured.getvalue()


def test_scholar_utils_uses_alias_and_never_prints_the_credential(monkeypatch):
    module, output = _load_scholar_utils(
        monkeypatch,
        semantic_key=None,
        s2_key="secret-from-store",
    )

    assert module.S2_API_KEY == "secret-from-store"
    assert "configured" in output
    assert "secret-from-store" not in output
