from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDER_PLAN = ROOT / "src" / "cinepulse" / "render_plan.py"

OLD_RESOLVED = '"resolved_audit_codes": ["CP-001", "CP-002", "CP-003", "CP-004", "CP-005", "CP-006", "CP-007", "CP-008", "CP-009", "CP-010", "CP-012", "CP-013", "CP-014", "CP-015", "CP-016", "CP-017", "CP-018", "CP-021", "CP-022", "CP-023", "CP-029", "CP-030", "CP-031"],'
NEW_RESOLVED = '"resolved_audit_codes": ["CP-001", "CP-002", "CP-003", "CP-004", "CP-005", "CP-006", "CP-007", "CP-008", "CP-009", "CP-010", "CP-011", "CP-012", "CP-013", "CP-014", "CP-015", "CP-016", "CP-017", "CP-018", "CP-019", "CP-020", "CP-021", "CP-022", "CP-023", "CP-029", "CP-030", "CP-031"],'
OLD_PENDING = '"pending_audit_codes": ["CP-011", "CP-019", "CP-020", "CP-027", "CP-032", "CP-033"],'
NEW_PENDING = '"pending_audit_codes": ["CP-027", "CP-032", "CP-033"],'
OLD_NOTE = '"policy_note": "Phase 8 separates installed/portable runtime behavior, centralizes PowerShell discovery, requires a managed Python runtime, adds single-instance protection and Windows branding. Signature and full transitive dependency locking remain release-gate work.",'
NEW_NOTE = '"policy_note": "Stable 1.0 uses lossless visual intermediates, signed-or-disabled update trust, hash-locked neural dependencies, managed Python, single-instance protection and Windows distribution gates. Generic recovery remains shadow/Preview by default until physical acceptance.",'


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        return text, False
    if old not in text:
        raise RuntimeError(f"metadata esperado não encontrado: {label}")
    return text.replace(old, new, 1), True


def main() -> int:
    text = RENDER_PLAN.read_text(encoding="utf-8")
    changed = False
    for old, new, label in (
        (OLD_RESOLVED, NEW_RESOLVED, "resolved_audit_codes"),
        (OLD_PENDING, NEW_PENDING, "pending_audit_codes"),
        (OLD_NOTE, NEW_NOTE, "policy_note"),
    ):
        text, item_changed = replace_once(text, old, new, label)
        changed = changed or item_changed
    if changed:
        RENDER_PLAN.write_text(text, encoding="utf-8", newline="\n")
        print("CINEPULSE_RELEASE_METADATA_UPDATED")
    else:
        print("CINEPULSE_RELEASE_METADATA_ALREADY_CURRENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
