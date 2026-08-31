from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .job_store import JobStore
from .render_job import RenderJobManifest


@dataclass(frozen=True)
class LegacyClassification:
    confidence: str
    reason: str
    job_id: str | None


@dataclass(frozen=True)
class MigrationResult:
    job_id: str
    confidence: str
    manifest: str | None
    migrated: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} não contém objeto JSON")
    return payload


def classify_legacy_job(job_dir: Path) -> LegacyClassification:
    job_path = job_dir / "job.json"
    plan_path = job_dir / "plan.json"
    contracts_path = job_dir / "contracts.json"
    if not job_path.is_file():
        return LegacyClassification("low", "job.json ausente", None)
    try:
        job = _json(job_path)
    except Exception as exc:
        return LegacyClassification("low", f"job.json inválido: {exc}", None)
    job_id = str(job.get("job_id") or "") or None
    if not job_id or job_id != job_dir.name:
        return LegacyClassification("low", "job_id ausente ou divergente do diretório", job_id)
    if plan_path.is_file() and contracts_path.is_file():
        try:
            plan = _json(plan_path)
            contracts = _json(contracts_path)
        except Exception as exc:
            return LegacyClassification("medium", f"contratos não validam: {exc}", job_id)
        fingerprint = str(plan.get("fingerprint") or "")
        contract_job = str(contracts.get("job_id") or job_id)
        if fingerprint and contract_job == job_id:
            return LegacyClassification("high", "job/history/fingerprint/contracts conferem", job_id)
        return LegacyClassification("medium", "histórico existe, mas falta fingerprint/identidade forte", job_id)
    if plan_path.is_file():
        return LegacyClassification("medium", "job e RenderPlan existem sem contracts completos", job_id)
    return LegacyClassification("low", "somente histórico básico; contrato insuficiente", job_id)


def _legacy_manifest(job_dir: Path) -> RenderJobManifest:
    job = _json(job_dir / "job.json")
    plan = _json(job_dir / "plan.json") if (job_dir / "plan.json").is_file() else {}
    contracts = _json(job_dir / "contracts.json") if (job_dir / "contracts.json").is_file() else {}
    job_id = str(job["job_id"])
    settings = job.get("settings") if isinstance(job.get("settings"), dict) else {}
    source = {"path_hint": str(settings.get("video") or "")}
    manifest = RenderJobManifest.new(job_id, source=source, now=float(job.get("started_at") or 0.0) or None)
    fingerprint = str(plan.get("fingerprint") or "")
    if fingerprint:
        manifest = manifest.with_render_plan(fingerprint, path="plan.json")
    expected = contracts.get("verification_expected")
    if isinstance(expected, dict):
        manifest = manifest.with_expectation(expected)
    status = str(job.get("status") or "running").casefold()
    if status in {"success", "complete", "concluído"}:
        for target in ("preflight", "running", "verifying", "complete"):
            manifest = manifest.transition(target, reason="legacy_migration")
    elif status in {"cancelled", "canceled", "cancelado"}:
        manifest = manifest.transition("preflight", reason="legacy_migration")
        manifest = manifest.transition("cancelled", reason="legacy_migration")
    elif status in {"error", "failed", "erro"}:
        manifest = manifest.transition("preflight", reason="legacy_migration")
        manifest = manifest.transition("blocked", reason="legacy_error")
    else:
        manifest = manifest.transition("preflight", reason="legacy_migration")
        manifest = manifest.transition("running", reason="legacy_migration")
        manifest = manifest.transition("interrupted", reason="legacy_owner_unknown")
    return manifest


def migrate_legacy_job(job_dir: Path, *, dry_run: bool = True, allow_medium: bool = False) -> MigrationResult:
    classification = classify_legacy_job(job_dir)
    job_id = classification.job_id or job_dir.name
    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        return MigrationResult(job_id, classification.confidence, str(manifest_path), False, "manifest já existe")
    allowed = classification.confidence == "high" or (classification.confidence == "medium" and allow_medium)
    if not allowed:
        return MigrationResult(job_id, classification.confidence, None, False, classification.reason)
    if dry_run:
        return MigrationResult(job_id, classification.confidence, str(manifest_path), False, "dry-run: elegível")
    manifest = _legacy_manifest(job_dir)
    JobStore(manifest_path).create(manifest)
    return MigrationResult(job_id, classification.confidence, str(manifest_path), True, "manifest criado ao lado do legado")


def attach_manifest_reference(items: list[dict], *, job_id: str, manifest_reference: str, recovery_origin: str = "history") -> list[dict]:
    migrated: list[dict] = []
    for item in items:
        copy = dict(item)
        if str(copy.get("job_id") or "") == job_id:
            copy["manifest"] = manifest_reference
            copy["recovery_origin"] = recovery_origin
        migrated.append(copy)
    return migrated
