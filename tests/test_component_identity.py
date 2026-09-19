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


def test_critical_file_change_invalidates_installed_component_fingerprint(tmp_path: Path) -> None:
    component = tmp_path / "components" / "real-esrgan"
    component.mkdir(parents=True)
    (component / ".cinepulse-component.json").write_text(
        json.dumps({
            "schema": 1,
            "key": "real-esrgan",
            "version": "installed-version",
            "sha256": "a" * 64,
        }),
        encoding="utf-8",
    )
    exe = component / "realesrgan-ncnn-vulkan.exe"
    model = component / "model.bin"
    exe.write_bytes(b"exe-v1")
    model.write_bytes(b"model-v1")
    first = bootstrap_component_fingerprint(
        "real_esrgan",
        component_root=component,
        critical_files=(exe, model),
    )
    model.write_bytes(b"model-v2-longer")
    second = bootstrap_component_fingerprint(
        "real_esrgan",
        component_root=component,
        critical_files=(exe, model),
    )
    assert first
    assert second
    assert first != second


def test_missing_critical_file_fails_closed(tmp_path: Path) -> None:
    component = tmp_path / "components" / "rife"
    component.mkdir(parents=True)
    (component / ".cinepulse-component.json").write_text(
        json.dumps({
            "schema": 1,
            "key": "rife",
            "version": "installed-version",
            "sha256": "a" * 64,
        }),
        encoding="utf-8",
    )
    missing = component / "rife-ncnn-vulkan.exe"
    assert bootstrap_component_fingerprint(
        "rife",
        component_root=component,
        critical_files=(missing,),
    ) == ""


def test_installed_component_marker_is_preferred_over_release_manifest(tmp_path: Path) -> None:
    manifest_digest = "a" * 64
    installed_digest = "b" * 64
    _write_manifest(
        tmp_path,
        {"real_esrgan": {"version": "manifest-version", "sha256": manifest_digest}},
    )
    component = tmp_path / "components" / "real-esrgan"
    component.mkdir(parents=True)
    (component / ".cinepulse-component.json").write_text(
        json.dumps({
            "schema": 1,
            "key": "real-esrgan",
            "version": "installed-version",
            "sha256": installed_digest,
        }),
        encoding="utf-8",
    )
    assert bootstrap_component_fingerprint(
        "real_esrgan",
        root=tmp_path,
        component_root=component,
    ) == f"real_esrgan:installed-version:{installed_digest}"


def test_wrong_component_marker_key_fails_closed_even_if_manifest_exists(tmp_path: Path) -> None:
    manifest_digest = "a" * 64
    _write_manifest(
        tmp_path,
        {"rife": {"version": "manifest-version", "sha256": manifest_digest}},
    )
    component = tmp_path / "components" / "rife"
    component.mkdir(parents=True)
    (component / ".cinepulse-component.json").write_text(
        json.dumps({
            "schema": 1,
            "key": "real-esrgan",
            "version": "wrong",
            "sha256": "b" * 64,
        }),
        encoding="utf-8",
    )
    assert bootstrap_component_fingerprint(
        "rife",
        root=tmp_path,
        component_root=component,
    ) == ""


def test_missing_installed_marker_fails_closed_in_runtime_mode(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        {"rife": {"version": "manifest-version", "sha256": "a" * 64}},
    )
    component = tmp_path / "components" / "rife"
    component.mkdir(parents=True)
    assert bootstrap_component_fingerprint(
        "rife",
        root=tmp_path,
        component_root=component,
    ) == ""


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
