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


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta e valida evidência estática para a auditoria final do CinePulse")
    parser.add_argument("--output", default="artifacts/ci/final-audit-static.json")
    args = parser.parse_args()

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    pytest_config = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))
    runtime_locked = _locked_packages(ROOT / "requirements.lock")
    neural_lock_path = ROOT / "requirements-neural.lock"
    neural_locked = _locked_packages(neural_lock_path) if neural_lock_path.is_file() else []
    resolved, pending = _render_plan_codes(ROOT / "src" / "cinepulse" / "render_plan.py")

    ui_text = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (ROOT / "src" / "cinepulse" / "studio.py", ROOT / "src" / "cinepulse" / "ui")
        for path in ([base] if base.is_file() else sorted(base.rglob("*.py")))
    )
    color_text = (ROOT / "src" / "cinepulse" / "color_pipeline.py").read_text(encoding="utf-8")
    installer_text = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
    portable_text = (ROOT / "scripts" / "Build-Portable.ps1").read_text(encoding="utf-8-sig")
    msi_text = (ROOT / "scripts" / "Build-Msi.ps1").read_text(encoding="utf-8-sig")
    rc_acceptance_text = (ROOT / "scripts" / "Invoke-RcAcceptance.ps1").read_text(encoding="utf-8-sig")
    init_text = (ROOT / "src" / "cinepulse" / "__init__.py").read_text(encoding="utf-8")
    rollout_text = (ROOT / "src" / "cinepulse" / "recovery_rollout.py").read_text(encoding="utf-8")
    gpu_workflow = (ROOT / ".github/workflows/gpu-acceptance.yml").read_text(encoding="utf-8")
    rc_workflow = (ROOT / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")

    manifest_url = str(channel.get("manifest_url") or "").strip()
    signed_channel = bool(
        manifest_url
        and channel.get("require_signature")
        and str(channel.get("public_key") or "").strip()
        and str(channel.get("manifest_signature_url") or "").strip().startswith("https://")
    )
    update_policy_safe = not manifest_url or signed_channel
    # CinePulse installs only the packages required for Demucs separation.
    # torchaudio belongs to Demucs' training surface and is intentionally not
    # part of the production runtime lock.
    neural_required = {"torch", "demucs", "soundfile"}
    neural_lock_complete = (
        neural_lock_path.is_file()
        and neural_required.issubset(set(neural_locked))
        and "--hash=sha256:" in neural_lock_path.read_text(encoding="utf-8")
    )
    lossless_intermediates = "return True" in color_text and "All active visual intermediates use FFV1" in color_text
    recovery_shadow_default = "ring: int = 1" in rollout_text and "recovery_worker: bool = False" in rollout_text and "recovery_discovery: bool = False" in rollout_text
    installer_uses_neural_lock = "requirements-neural.lock" in installer_text and "--require-hashes" in installer_text
    neural_lock_updatable = all(token in installer_text for token in ("'requirements-neural.in'", "'requirements-neural.lock'"))
    neural_lock_packaged = all(token in portable_text for token in ("'requirements-neural.in'", "'requirements-neural.lock'"))
    gpu_gate_guarded = all(token in gpu_workflow for token in ("self-hosted", "cinepulse-gpu", "pull_request:", "github.event.pull_request.head.repo.full_name == github.repository"))
    windows_distribution_gate = all(token in rc_workflow for token in ("pull_request:", "Build-Portable.ps1", "Build-Msi.ps1", "Test-MsiLifecycle.ps1"))

    declared_versions = {
        "pyproject": project_version,
        "package": _extract(r'__version__\s*=\s*["\']([^"\']+)', init_text),
        "portable_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", portable_text),
        "msi_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", msi_text),
        "rc_acceptance_default": _extract(r"\[string\]\$Version\s*=\s*'([^']+)'", rc_acceptance_text),
        "rc_workflow_default": _extract(r"^\s*default:\s*([^\s#]+)", rc_workflow),
    }
    version_metadata_synchronized = all(value == project_version for value in declared_versions.values())

    temporary_writer_workflows = (
        ROOT / ".github/workflows/neural-lock.yml",
        ROOT / ".github/workflows/release-metadata.yml",
        ROOT / ".github/workflows/overlay-studio-integrate.yml",
    )
    temporary_writer_workflows_absent = not any(path.exists() for path in temporary_writer_workflows)

    checks = {
        "pytest_src_path_configured": "src" in pytest_config.get("pythonpath", []),
        "no_misleading_gpu_automatic_label": "GPU automática" not in ui_text,
        "update_policy_signed_or_disabled": update_policy_safe,
        "runtime_lock_hashed": bool(runtime_locked) and "--hash=sha256:" in (ROOT / "requirements.lock").read_text(encoding="utf-8"),
        "neural_lock_complete_and_hashed": neural_lock_complete,
        "installer_consumes_neural_hash_lock": installer_uses_neural_lock,
        "neural_lock_part_of_update_transaction": neural_lock_updatable,
        "neural_lock_packaged_in_portable": neural_lock_packaged,
        "visual_intermediates_lossless": lossless_intermediates,
        "recovery_stable_default_shadow_only": recovery_shadow_default,
        "windows_distribution_pr_gate_present": windows_distribution_gate,
        "physical_gpu_pr_gate_guarded": gpu_gate_guarded,
        "release_version_metadata_synchronized": version_metadata_synchronized,
        "temporary_branch_writer_workflows_absent": temporary_writer_workflows_absent,
    }

    payload = {
        "schema": 3,
        "project_version": project_version,
        "declared_versions": declared_versions,
        "studio_lines": _line_count(ROOT / "src" / "cinepulse" / "studio.py"),
        "loop_engine_lines": _line_count(ROOT / "src" / "cinepulse" / "loop_engine.py"),
        "update_channel_mode": "signed" if manifest_url else "disabled",
        "runtime_locked_packages": runtime_locked,
        "runtime_locked_package_count": len(runtime_locked),
        "neural_locked_packages": neural_locked,
        "neural_locked_package_count": len(neural_locked),
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
