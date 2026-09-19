from __future__ import annotations

import json
from pathlib import Path

from cinepulse.component_identity import bootstrap_component_fingerprint


def _write_manifest(root: Path, payload: dict) -> None:
    installer = root / "installer"
    installer.mkdir(parents=True, exist_ok=True)
    (installer / "bootstrap-manifest.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_component_fingerprint_uses_version_and_sha256(tmp_path: Path) -> None:
    digest = "a" * 64
    _write_manifest(
        tmp_path,
        {"rife": {"version": "ncnn-test", "sha256": digest}},
    )
    assert bootstrap_component_fingerprint("rife", root=tmp_path) == f"rife:ncnn-test:{digest}"


def test_component_fingerprint_fails_closed_on_invalid_manifest(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        {"rife": {"version": "ncnn-test", "sha256": "not-a-sha"}},
    )
    assert bootstrap_component_fingerprint("rife", root=tmp_path) == ""
    assert bootstrap_component_fingerprint("missing", root=tmp_path) == ""


def test_repository_bootstrap_manifest_has_neural_component_fingerprints() -> None:
    real = bootstrap_component_fingerprint("real_esrgan")
    rife = bootstrap_component_fingerprint("rife")
    assert real.startswith("real_esrgan:")
    assert rife.startswith("rife:")
    assert len(real.rsplit(":", 1)[-1]) == 64
    assert len(rife.rsplit(":", 1)[-1]) == 64
