from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-release.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_publisher_has_write_permission_but_only_publishes_from_main() -> None:
    text = _workflow()
    assert "permissions:\n  contents: write" in text
    assert "github.event_name != 'pull_request'" in text
    assert "github.ref == 'refs/heads/main'" in text


def test_publisher_uses_exact_release_runtime_and_hash_lock() -> None:
    text = _workflow()
    assert "python-version: '3.14.7'" in text
    assert "--require-hashes --only-binary=:all: -r requirements.lock" in text
    assert "tests/test_installer_v2_contract.py" in text
    assert "Test-IsolatedEnvironment.ps1" in text
    assert "Test-NeuralInstaller.ps1" in text


def test_publisher_runs_full_acceptance_before_release_creation() -> None:
    text = _workflow()
    acceptance = text.index("Invoke-RcAcceptance.ps1")
    checksums = text.index("SHA256SUMS.txt")
    publish = text.index("gh @Args")
    assert acceptance < checksums < publish
    assert "-RunMsiLifecycle" in text


def test_publisher_outputs_required_release_assets() -> None:
    text = _workflow()
    for token in (
        "windows-portable.zip",
        "Setup.msi",
        "Setup-manifest.json",
        "SBOM.cdx.json",
        "SHA256SUMS.txt",
    ):
        assert token in text


def test_publisher_is_idempotent_and_refuses_tag_retargeting() -> None:
    text = _workflow()
    assert "CINEPULSE_RELEASE_ALREADY_PUBLISHED" in text
    assert "does not resolve to this main commit" in text
    assert "Existing tag $Tag points to" in text
    assert "--verify-tag" in text
    assert "--target" in text


def test_publisher_release_is_gated_by_repository_version() -> None:
    text = _workflow()
    assert "Version mismatch: pyproject=" in text
    assert "Requested version" in text
    assert "Stable publisher requires x.y.z SemVer" in text


def test_publisher_binds_release_notes_and_push_trigger_to_version_metadata() -> None:
    text = _workflow()
    assert "'pyproject.toml'" in text
    assert "'src/cinepulse/__init__.py'" in text
    assert "RELEASE_$($ProjectVersion.Replace('.', '_')).md" in text
    assert "RELEASE_NOTES_FILE=$NotesFile" in text
    assert "'--notes-file', $env:RELEASE_NOTES_FILE" in text
