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


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta evidência estática para a auditoria final do CinePulse")
    parser.add_argument("--output", default="artifacts/ci/final-audit-static.json")
    args = parser.parse_args()

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {})
    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))
    locked = _locked_packages(ROOT / "requirements.lock")
    resolved, pending = _render_plan_codes(ROOT / "src" / "cinepulse" / "render_plan.py")

    ui_text = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (ROOT / "src" / "cinepulse" / "studio.py", ROOT / "src" / "cinepulse" / "ui")
        for path in ([base] if base.is_file() else sorted(base.rglob("*.py")))
    )

    payload = {
        "schema": 1,
        "project_version": pyproject["project"]["version"],
        "studio_lines": _line_count(ROOT / "src" / "cinepulse" / "studio.py"),
        "loop_engine_lines": _line_count(ROOT / "src" / "cinepulse" / "loop_engine.py"),
        "pytest_src_path_configured": "src" in pytest_config.get("pythonpath", []),
        "misleading_gpu_automatic_label_present": "GPU automática" in ui_text,
        "update_channel_manifest_url_configured": bool(str(channel.get("manifest_url", "")).strip()),
        "runtime_locked_packages": locked,
        "runtime_locked_package_count": len(locked),
        "render_plan_resolved_audit_codes": resolved,
        "render_plan_pending_audit_codes": pending,
        "windows_release_workflow_present": (ROOT / ".github/workflows/release-candidate.yml").is_file(),
        "gpu_acceptance_workflow_present": (ROOT / ".github/workflows/gpu-acceptance.yml").is_file(),
    }

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"CINEPULSE_FINAL_AUDIT_STATIC_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
