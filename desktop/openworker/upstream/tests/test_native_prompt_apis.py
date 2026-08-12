from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _client(tmp_path: Path) -> TestClient:
    prompt_root = tmp_path / "prompts"
    baseline_root = tmp_path / "prompt_baseline"
    shutil.copytree(REPOSITORY_ROOT / "config" / "prompts", prompt_root)
    shutil.copytree(REPOSITORY_ROOT / "config" / "prompt_baseline", baseline_root)
    conversion_prompt = tmp_path / "discovery_input_conversion_prompt.yaml"
    conversion_prompt.write_text(
        "instruction: Format the saved Discovery preparation.\n",
        encoding="utf-8",
    )
    manager = SessionManager(data_dir=tmp_path / "state")
    return TestClient(
        create_app(
            manager,
            prompt_library_root=prompt_root,
            prompt_baseline_root=baseline_root,
            discovery_conversion_prompt_path=conversion_prompt,
        )
    )


def test_prompt_library_is_served_by_the_native_sidecar(tmp_path: Path) -> None:
    client = _client(tmp_path)

    health = client.get("/v1/prompt-library/health")
    assert health.status_code == 200
    assert health.json() == {"api_version": "v1", "status": "ready"}

    catalogue = client.get("/v1/prompt-library/prompts")
    assert catalogue.status_code == 200
    prompts = catalogue.json()["prompts"]
    assert any(prompt["id"] == "discovery.generation.system" for prompt in prompts)
    assert {
        "external_data.connector",
        "external_data.web_evidence",
    }.issubset({prompt["id"] for prompt in prompts})

    detail = client.get("/v1/prompt-library/prompts/discovery.generation.system")
    assert detail.status_code == 200
    assert detail.json()["prompt"]["text"] == detail.json()["prompt"]["system_original_text"]

    original = client.get("/v1/prompt-library/prompts/experiment.coder_openhands").json()
    updated = original["prompt"]["text"] + "\nNATIVE_SIDECAR_TEST_MARKER\n"
    saved = client.put(
        "/v1/prompt-library/prompts/experiment.coder_openhands",
        json={"text": updated},
    )
    assert saved.status_code == 200
    assert saved.json()["prompt"]["text"] == updated


def test_discovery_conversion_prompt_is_served_by_the_native_sidecar(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    current = client.get("/v1/discovery/input-conversion-prompt")
    assert current.status_code == 200
    assert current.json() == {
        "instruction": "Format the saved Discovery preparation.",
        "configured": True,
    }

    saved = client.put(
        "/v1/discovery/input-conversion-prompt",
        json={"instruction": "Convert the preparation into reviewable inputs."},
    )
    assert saved.status_code == 200
    assert saved.json()["instruction"] == "Convert the preparation into reviewable inputs."


def test_retired_prompt_routes_are_not_part_of_the_sidecar_contract(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    assert client.get("/api/prompt-library/v1/prompts").status_code == 404
    assert client.get("/api/admin/discovery-input-conversion-prompt").status_code == 404
