from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _locked_packages(path: Path) -> list[str]:
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.startswith("--") or text.startswith("\\"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)==", text)
        if match:
            names.append(match.group(1).lower())
    return sorted(set(names))


def _render_plan_codes(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    resolved_match = re.search(r'"resolved_audit_codes"\s*:\s*\[([^\]]*)\]', text)
    pending_match = re.search(r'"pending_audit_codes"\s*:\s*\[([^\]]*)\]', text)

    def parse(match: re.Match[str] | None) -> list[str]:
        if not match:
            return []
        return re.findall(r'"(CP-\d{3})"', match.group(1))

    return parse(resolved_match), parse(pending_match)


def _extract(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def _writer_workflows() -> list[str]:
    writers: list[str] = []
    workflow_root = ROOT / ".github" / "workflows"
    for path in sorted(workflow_root.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "contents: write" in text:
            writers.append(path.name)
    return writers


def _temporary_workflows() -> list[str]:
    root = ROOT / ".github" / "workflows"
    names: list[str] = []
    for path in sorted(root.glob("*.yml")):
        lowered = path.name.lower()
        if lowered.startswith("_tmp-") or lowered.startswith("tmp-") or "temporary" in lowered:
            names.append(path.name)
    return names


def _protected_update_roots(applier_text: str) -> set[str]:
    match = re.search(r"\$ProtectedTopLevel\s*=\s*@\(([^)]*)\)", applier_text, re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta e valida evidência estática para a auditoria final do CinePulse")
    parser.add_argument("--output", default="artifacts/ci/final-audit-static.json")
    args = parser.parse_args()

    pyproject_path = ROOT / "pyproject.toml"
    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    pyproject = tomllib.loads(pyproject_text)
    project_version = str(pyproject["project"]["version"])
    pytest_config = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))
    runtime_lock_path = ROOT / "requirements.lock"
    runtime_lock_text = runtime_lock_path.read_text(encoding="utf-8")
    runtime_locked = _locked_packages(runtime_lock_path)
    neural_lock_path = ROOT / "requirements-neural.lock"
    neural_lock_text = neural_lock_path.read_text(encoding="utf-8") if neural_lock_path.is_file() else ""
    neural_locked = _locked_packages(neural_lock_path) if neural_lock_path.is_file() else []
    resolved, pending = _render_plan_codes(ROOT / "src" / "cinepulse" / "render_plan.py")

    studio_path = ROOT / "src" / "cinepulse" / "studio.py"
    studio_text = studio_path.read_text(encoding="utf-8")
    ui_text = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (studio_path, ROOT / "src" / "cinepulse" / "ui")
        for path in ([base] if base.is_file() else sorted(base.rglob("*.py")))
    )
    render_plan_text = (ROOT / "src" / "cinepulse" / "render_plan.py").read_text(encoding="utf-8")
    color_text = (ROOT / "src" / "cinepulse" / "color_pipeline.py").read_text(encoding="utf-8")
    installer_text = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
    update_applier_path = ROOT / "installer" / "Apply-CinePulseUpdate.ps1"
    update_applier_text = update_applier_path.read_text(encoding="utf-8-sig") if update_applier_path.is_file() else ""
    portable_text = (ROOT / "scripts" / "Build-Portable.ps1").read_text(encoding="utf-8-sig")
    msi_text = (ROOT / "scripts" / "Build-Msi.ps1").read_text(encoding="utf-8-sig")
    rc_acceptance_text = (ROOT / "scripts" / "Invoke-RcAcceptance.ps1").read_text(encoding="utf-8-sig")
    init_text = (ROOT / "src" / "cinepulse" / "__init__.py").read_text(encoding="utf-8")
    rollout_text = (ROOT / "src" / "cinepulse" / "recovery_rollout.py").read_text(encoding="utf-8")
    gpu_workflow = (ROOT / ".github/workflows/gpu-acceptance.yml").read_text(encoding="utf-8")
    rc_workflow = (ROOT / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
    quality_workflow = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
    installer_acceptance = (ROOT / ".github/workflows/installer-v2-acceptance.yml").read_text(encoding="utf-8")
    publisher_workflow = (ROOT / ".github/workflows/publish-release.yml").read_text(encoding="utf-8")

    h8_paths = (
        ROOT / "src" / "cinepulse" / "overnight_runtime.py",
        ROOT / "src" / "cinepulse" / "adaptive_runtime.py",
        ROOT / "scripts" / "overnight_acceptance.py",
    )
    h8_text = "\n".join(path.read_text(encoding="utf-8") for path in h8_paths if path.is_file()).lower()
    tensorrt_path = ROOT / "src" / "cinepulse" / "tensorrt_preview.py"
    tensorrt_text = tensorrt_path.read_text(encoding="utf-8") if tensorrt_path.is_file() else ""
    h7_benchmark_path = ROOT / "scripts" / "tensorrt_preview_benchmark.py"
    h7_benchmark_text = h7_benchmark_path.read_text(encoding="utf-8") if h7_benchmark_path.is_file() else ""

    manifest_url = str(channel.get("manifest_url") or "").strip()
    signed_channel = bool(
        manifest_url
        and channel.get("require_signature")
        and str(channel.get("public_key") or "").strip()
        and str(channel.get("manifest_signature_url") or "").strip().startswith("https://")
    )
    update_policy_safe = not manifest_url or signed_channel
    neural_required = {"torch", "demucs", "soundfile"}
    neural_lock_complete = (
        neural_lock_path.is_file()
        and neural_required.issubset(set(neural_locked))
        and "--hash=sha256:" in neural_lock_text
    )
    lossless_intermediates = "return True" in color_text and "All active visual intermediates use FFV1" in color_text
    recovery_shadow_default = "ring: int = 1" in rollout_text and "recovery_worker: bool = False" in rollout_text and "recovery_discovery: bool = False" in rollout_text
    installer_uses_neural_lock = "requirements-neural.lock" in installer_text and "--require-hashes" in installer_text

    protected_update_roots = _protected_update_roots(update_applier_text)
    neural_lock_packaged = all(token in portable_text for token in ("'requirements-neural.in'", "'requirements-neural.lock'"))
    neural_lock_updatable = (
        update_applier_path.is_file()
        and neural_lock_packaged
        and "Get-ManagedTopLevelEntries -Root $Source" in update_applier_text
        and "Get-ManagedTopLevelEntries -Root $ProjectRoot" in update_applier_text
        and update_applier_text.count("Test-PackageManifest -PackageRoot") >= 2
        and "requirements-neural.in" not in protected_update_roots
        and "requirements-neural.lock" not in protected_update_roots
    )
    gpu_gate_guarded = all(token in gpu_workflow for token in ("self-hosted", "cinepulse-gpu", "pull_request:", "github.event.pull_request.head.repo.full_name == github.repository"))
    gpu_gate_release_aligned = all(token in gpu_workflow for token in ("python-version: '3.14.7'", "--require-hashes", "Start-CinePulse.ps1 -InstallOnly", "Test-NeuralInstaller.ps1"))
    windows_distribution_gate = all(token in rc_workflow for token in ("pull_request:", "Build-Portable.ps1", "Build-Msi.ps1", "Test-MsiLifecycle.ps1"))
    rc_version_bound_to_code = all(token in rc_workflow for token in ("tomllib", "Version mismatch: pyproject=", "does not match repository version", "GITHUB_REF_TYPE", "REQUESTED_VERSION"))
    quality_release_python = (
        "'3.14.7'" in quality_workflow
        and quality_workflow.count("python-version: '3.14.7'") >= 2
        and "--profile cpu" in quality_workflow
        and "--profile media" in quality_workflow
    )
    installer_acceptance_permanent = (
        "pull_request:" in installer_acceptance
        and installer_acceptance.count("branches: [main]") >= 2
        and "installer-v2-self-contained" not in installer_acceptance
        and "CINEPULSE_VERSION" in installer_acceptance
        and "-Version 1.1.0" not in installer_acceptance
    )

    declared_versions = {
        "pyproject": project_version,
        "package": _extract(r'__version__\s*=\s*["\']([^"\']+)', init_text),
        "portable_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", portable_text),
        "msi_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", msi_text),
        "rc_acceptance_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", rc_acceptance_text),
        "rc_workflow_default": _extract(r"^\s*default:\s*([^\s#]+)", rc_workflow),
    }
    version_metadata_synchronized = all(value == project_version for value in declared_versions.values())

    legacy_temporary_writer_workflows = (
        ROOT / ".github/workflows/neural-lock.yml",
        ROOT / ".github/workflows/release-metadata.yml",
        ROOT / ".github/workflows/overlay-studio-integrate.yml",
        ROOT / ".github/workflows/installer-v2-runtime-locks.yml",
    )
    temporary_workflows = _temporary_workflows()
    temporary_writer_workflows_absent = not any(path.exists() for path in legacy_temporary_writer_workflows) and not temporary_workflows
    writer_workflows = _writer_workflows()
    permanent_writer_allowlist_safe = writer_workflows == ["publish-release.yml"] and "github.ref == 'refs/heads/main'" in publisher_workflow

    stable_dependency_surface = "\n".join((
        pyproject_text,
        runtime_lock_text,
        neural_lock_text,
        installer_text,
    )).lower()
    tensorrt_not_stable_dependency = "tensorrt" not in stable_dependency_surface
    h7_preview_isolated = all(token in tensorrt_text for token in (
        "stable_distribution_allowed",
        "return False",
        "ncnn_baseline_fingerprint",
        "preview_only",
    )) and all(token in h7_benchmark_text for token in ("--ncnn-cache", "prove_ncnn_baseline", "stable_fallback"))
    h5_resident_runtime_safe = all(token in studio_text for token in (
        "ResidentEncodeStore",
        "select_resident_delivery_route",
        "baseline_command = list(command)",
        "resident_store.invalidate(resident_route.key)",
        "baseline CPU/zscale",
    ))
    h8_forbidden_mutations = (
        "realtime_priority_class", "setpriorityclass", "powercfg", "-pl ", "--power-limit",
        "nvidia-settings", "setprocesspriorityboost",
    )
    h8_no_global_or_realtime_mutations = not any(token in h8_text for token in h8_forbidden_mutations)
    h8_sustained_guard_present = all(token in h8_text for token in (
        "temperature_c", "power_w", "graphics_clock_mhz", "ram_percent", "disk_write_mbps",
        "cooldown_hint_seconds", "pressure_level",
    ))
    preview_composer_isolated_from_stable_plan = all(
        token not in render_plan_text
        for token in ("OverlayComposerState", "composer_export", "gpu_compositor", "TensorRt")
    )

    checks = {
        "pytest_src_path_configured": "src" in pytest_config.get("pythonpath", []),
        "no_misleading_gpu_automatic_label": "GPU automática" not in ui_text,
        "update_policy_signed_or_disabled": update_policy_safe,
        "runtime_lock_hashed": bool(runtime_locked) and "--hash=sha256:" in runtime_lock_text,
        "neural_lock_complete_and_hashed": neural_lock_complete,
        "installer_consumes_neural_hash_lock": installer_uses_neural_lock,
        "neural_lock_part_of_update_transaction": neural_lock_updatable,
        "neural_lock_packaged_in_portable": neural_lock_packaged,
        "visual_intermediates_lossless": lossless_intermediates,
        "recovery_stable_default_shadow_only": recovery_shadow_default,
        "windows_distribution_pr_gate_present": windows_distribution_gate,
        "release_candidate_version_bound_to_code": rc_version_bound_to_code,
        "quality_tests_actual_release_python": quality_release_python,
        "installer_acceptance_is_permanent_main_gate": installer_acceptance_permanent,
        "physical_gpu_pr_gate_guarded": gpu_gate_guarded,
        "physical_gpu_gate_uses_release_runtime": gpu_gate_release_aligned,
        "release_version_metadata_synchronized": version_metadata_synchronized,
        "temporary_branch_writer_workflows_absent": temporary_writer_workflows_absent,
        "permanent_write_workflow_allowlist_safe": permanent_writer_allowlist_safe,
        "h5_resident_runtime_has_exact_evidence_rollback": h5_resident_runtime_safe,
        "h7_tensorrt_not_stable_dependency": tensorrt_not_stable_dependency,
        "h7_preview_permission_bound_to_ncnn_baseline": h7_preview_isolated,
        "h8_no_realtime_or_silent_global_mutation": h8_no_global_or_realtime_mutations,
        "h8_sustained_resource_guard_present": h8_sustained_guard_present,
        "preview_composer_isolated_from_stable_render_plan": preview_composer_isolated_from_stable_plan,
    }

    payload = {
        "schema": 6,
        "project_version": project_version,
        "declared_versions": declared_versions,
        "studio_lines": _line_count(studio_path),
        "loop_engine_lines": _line_count(ROOT / "src" / "cinepulse" / "loop_engine.py"),
        "update_channel_mode": "signed" if manifest_url else "disabled",
        "update_protected_roots": sorted(protected_update_roots),
        "runtime_locked_packages": runtime_locked,
        "runtime_locked_package_count": len(runtime_locked),
        "neural_locked_packages": neural_locked,
        "neural_locked_package_count": len(neural_locked),
        "writer_workflows": writer_workflows,
        "temporary_workflows": temporary_workflows,
        "render_plan_resolved_audit_codes": resolved,
        "render_plan_pending_audit_codes": pending,
        "checks": checks,
        "passed": all(checks.values()),
    }

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not payload["passed"]:
        print("CINEPULSE_FINAL_AUDIT_STATIC_FAILED")
        for name, passed in checks.items():
            if not passed:
                print(f"- {name}")
        return 1
    print(f"CINEPULSE_FINAL_AUDIT_STATIC_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
