from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "packaging" / "make_update_manifest.py"


def run_manifest(dist: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--version",
            "0.1.0",
            "--tag",
            "v0.1.0",
            "--repo",
            "v6582374-netizen/Vegapunk",
            "--dist",
            str(dist),
            "--out",
            str(output),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_manifest_contains_only_signed_vegapunk_macos_artifact(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    artifact = dist / "Vegapunk-macos-arm64.app.tar.gz"
    artifact.write_bytes(b"signed bundle bytes")
    (dist / "Vegapunk-macos-arm64.app.tar.gz.sig").write_text("signature\n")
    (dist / "OpenWorker-macos-arm64.app.tar.gz").write_bytes(b"legacy bundle")

    output = tmp_path / "latest.json"
    result = run_manifest(dist, output, "--notes", "Vegapunk 0.1.0")

    assert result.returncode == 0, result.stderr
    manifest = json.loads(output.read_text())
    assert manifest["version"] == "0.1.0"
    assert manifest["notes"] == "Vegapunk 0.1.0"
    assert manifest["platforms"] == {
        "darwin-aarch64": {
            "signature": "signature",
            "url": "https://github.com/v6582374-netizen/Vegapunk/releases/download/v0.1.0/Vegapunk-macos-arm64.app.tar.gz",
        }
    }


def test_manifest_refuses_unsigned_or_legacy_only_artifacts(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "OpenWorker-macos-arm64.app.tar.gz").write_bytes(b"legacy bundle")

    output = tmp_path / "latest.json"
    result = run_manifest(dist, output)

    assert result.returncode == 1
    assert "no signed updater artifacts" in result.stderr
    assert not output.exists()
