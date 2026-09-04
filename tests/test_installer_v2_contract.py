from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def test_paths_default_to_project_root_not_localappdata() -> None:
    text = _text("src/cinepulse/paths.py")
    # Documentation may mention LocalAppData when explaining that it is not
    # used; reject actual environment lookups instead of matching comments.
    assert 'os.environ.get("LOCALAPPDATA")' not in text
    assert "os.environ['LOCALAPPDATA']" not in text
    assert "os.environ[\"LOCALAPPDATA\"]" not in text
    assert 'os.getenv("LOCALAPPDATA")' not in text
    assert 'root / "data"' in text
    assert 'root / "cache"' in text
    assert 'root / "temp"' in text
    assert 'root / "components"' in text


def test_launchers_load_central_isolated_environment() -> None:
    for path in (
        "CinePulse.cmd",
        "Install-CinePulse.cmd",
        "CinePulse-Installed.cmd",
        "Install-CinePulse-Installed.cmd",
    ):
        text = _text(path)
        assert "installer\\CinePulse-Environment.cmd" in text, path


def test_environment_routes_temp_and_dependency_caches_below_root() -> None:
    text = _text("installer/CinePulse-Environment.cmd")
    for token in (
        "CINEPULSE_DATA_DIR",
        "CINEPULSE_COMPONENTS_DIR",
        "CINEPULSE_CACHE_DIR",
        "CINEPULSE_TEMP_DIR",
        "TEMP=%CINEPULSE_TEMP_DIR%",
        "TMP=%CINEPULSE_TEMP_DIR%",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "PIP_CACHE_DIR",
        "TORCH_HOME",
        "HF_HOME",
        "NUMBA_CACHE_DIR",
        "MPLCONFIGDIR",
        "PYTHONPYCACHEPREFIX",
        "PYTHONNOUSERSITE=1",
    ):
        assert token in text


def test_bootstrap_does_not_redirect_installed_runtime_to_user_profile() -> None:
    text = _text("installer/Start-CinePulse.ps1")
    assert "$UserDataRoot" not in text
    assert "UserGpuPreferences" not in text
    assert "$RuntimeRoot = Join-Path $ProjectRoot '.runtime'" in text
    assert "$ComponentsRoot = Join-Path $ProjectRoot 'components'" in text
    assert "$TempRoot = Join-Path $ProjectRoot 'temp'" in text


def test_msi_exposes_user_selectable_install_directory() -> None:
    wxs = _text("installer/wix/Product.wxs")
    build = _text("scripts/Build-Msi.ps1")
    assert 'WixUI_InstallDir' in wxs
    assert 'InstallDirectory="INSTALLFOLDER"' in wxs
    assert "WixToolset.UI.wixext" in build


def test_msi_lifecycle_uses_non_default_install_root() -> None:
    text = _text("scripts/Test-MsiLifecycle.ps1")
    assert "msi-install-root" in text
    assert 'INSTALLFOLDER=$InstallRoot' in text


def test_temporary_installer_patch_scaffolds_are_absent() -> None:
    for relative in (
        ".github/workflows/installer-v2-apply.yml",
        ".github/workflows/installer-v2-msi-apply.yml",
        ".github/workflows/hotfix-neural-installer.yml",
        "scripts/_installer_v2_patch.py",
        "scripts/_installer_v2_msi_patch.py",
        "scripts/_hotfix_apply_neural_index.py",
    ):
        assert not (ROOT / relative).exists(), relative
