from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Restore the AI installation progress event accidentally removed by the
# updater event-loop refactor.
studio_path = "src/cinepulse/studio.py"
studio = read(studio_path)
if 'elif kind == "ai_install_status":' not in studio:
    needle = '                elif kind == "ai_install_done":\n'
    block = '''                elif kind == "ai_install_status":\n                    line = str(event[1])\n                    self.ai_install_status_text.set(line[-180:])\n                    percent = progress_from_log(line)\n                    if percent is not None:\n                        if hasattr(self, "ai_install_progressbar"):\n                            self.ai_install_progressbar.stop()\n                            self.ai_install_progressbar.configure(mode="determinate")\n                        self.ai_install_progress.set(float(percent))\n                        self.ai_install_progress_text.set(f"Atividade atual: {percent}%")\n                    else:\n                        self.ai_install_progress_text.set("Atividade em andamento")\n'''
    studio = replace_once(studio, needle, block + needle, "restore ai_install_status")
write(studio_path, studio)


# ---------------------------------------------------------------------------
# 2) Harden GitHub Stable discovery and deferred MSI handoff.
manager_path = "src/cinepulse/update_manager.py"
manager = read(manager_path)

anchor = '''    return digest.hexdigest().lower()\n\n\ndef _validated_update_info(info: UpdateInfo) -> tuple[str, str]:\n'''
insert = '''    return digest.hexdigest().lower()\n\n\ndef _sha256_file(path: Path) -> str:\n    digest = hashlib.sha256()\n    with Path(path).open("rb") as stream:\n        while True:\n            block = stream.read(_DOWNLOAD_BLOCK_BYTES)\n            if not block:\n                break\n            digest.update(block)\n    return digest.hexdigest().lower()\n\n\ndef _validated_update_info(info: UpdateInfo) -> tuple[str, str]:\n'''
if "def _sha256_file(" not in manager:
    manager = replace_once(manager, anchor, insert, "insert staged file hashing")

old = '''    if info.package_kind not in {"portable", "msi"}:\n        raise ValueError(f"Tipo de pacote de atualização inválido: {info.package_kind}")\n    return version, digest\n'''
new = '''    if info.package_kind not in {"portable", "msi"}:\n        raise ValueError(f"Tipo de pacote de atualização inválido: {info.package_kind}")\n    if info.source == "github-release":\n        expected_asset = (\n            f"CinePulse-{version}-Setup.msi"\n            if info.package_kind == "msi"\n            else f"CinePulse-{version}-windows-portable.zip"\n        )\n        if info.asset_name != expected_asset:\n            raise ValueError("O asset da atualização GitHub não corresponde à versão e ao modo de instalação.")\n        _validate_release_asset_url(info.download_url, version, expected_asset)\n    return version, digest\n'''
if "O asset da atualização GitHub não corresponde" not in manager:
    manager = replace_once(manager, old, new, "bind github UpdateInfo to exact asset")

old = '''def _checksum_from_release_asset(\n    assets: list[dict],\n    asset_name: str,\n    *,\n    current_version: str,\n    timeout: int,\n) -> str:\n'''
new = '''def _checksum_from_release_asset(\n    assets: list[dict],\n    asset_name: str,\n    *,\n    version: str,\n    current_version: str,\n    timeout: int,\n) -> str:\n'''
if "    version: str,\n    current_version: str," not in manager:
    manager = replace_once(manager, old, new, "checksum version binding")

old = '''    url = str(checksum_asset.get("browser_download_url") or "")\n    request = _github_request(url, current_version)\n'''
new = '''    url = str(checksum_asset.get("browser_download_url") or "")\n    _validate_release_asset_url(url, version, "SHA256SUMS.txt")\n    request = _github_request(url, current_version)\n'''
if '_validate_release_asset_url(url, version, "SHA256SUMS.txt")' not in manager:
    manager = replace_once(manager, old, new, "checksum URL same-release binding")

old = '''        digest = _checksum_from_release_asset(\n            [item for item in assets if isinstance(item, dict)],\n            asset_name,\n            current_version=current_version,\n            timeout=timeout,\n        )\n'''
new = '''        digest = _checksum_from_release_asset(\n            [item for item in assets if isinstance(item, dict)],\n            asset_name,\n            version=version,\n            current_version=current_version,\n            timeout=timeout,\n        )\n'''
if "            version=version,\n            current_version=current_version," not in manager:
    manager = replace_once(manager, old, new, "checksum call version binding")

old = '''    api_url = _release_api_url()\n    request = _github_request(api_url, current_version)\n'''
new = '''    if installation not in {"portable", "installed"}:\n        raise ValueError(f"Modo de instalação inválido para atualização: {installation}")\n    api_url = _release_api_url()\n    request = _github_request(api_url, current_version)\n'''
if "Modo de instalação inválido para atualização" not in manager:
    manager = replace_once(manager, old, new, "installation mode validation")

old = '''    version = tag[1:]\n    _version_key(version)\n    if not is_newer(version, current_version):\n'''
new = '''    version = tag[1:]\n    if not re.fullmatch(r"\\d+\\.\\d+\\.\\d+", version):\n        raise ValueError("A release Stable precisa usar versão final x.y.z; prerelease não é aceita.")\n    _version_key(version)\n    if not is_newer(version, current_version):\n'''
if "A release Stable precisa usar versão final x.y.z" not in manager:
    manager = replace_once(manager, old, new, "final stable tag validation")

old = '''    if info.package_kind == "msi" and staged.suffix.lower() != ".msi":\n        raise ValueError("A atualização instalada exige um pacote .msi preparado.")\n    if info.package_kind == "portable" and staged.name != "pending-update.json":\n        raise ValueError("A atualização portátil exige o descritor pending-update.json.")\n\n    helper_root = Path(tempfile.gettempdir()) / "CinePulseUpdater" / "handoff"\n'''
new = '''    app_root = Path(app_root).expanduser().resolve()\n    if info.package_kind == "msi":\n        expected_name = info.asset_name or f"CinePulse-{info.version.strip()}-Setup.msi"\n        if staged.suffix.lower() != ".msi" or staged.name != expected_name:\n            raise ValueError("A atualização instalada exige o pacote MSI exato preparado para esta versão.")\n        update_root = _installed_update_root().expanduser().resolve()\n        if update_root != staged and update_root not in staged.parents:\n            raise ValueError("O pacote MSI preparado está fora da área privada do updater.")\n        if _sha256_file(staged) != info.sha256.strip().lower():\n            raise RuntimeError("O pacote MSI preparado mudou após a verificação; a instalação foi bloqueada.")\n    else:\n        if staged.name != "pending-update.json":\n            raise ValueError("A atualização portátil exige o descritor pending-update.json.")\n        runtime_root = (app_root / ".runtime").resolve()\n        if runtime_root != staged and runtime_root not in staged.parents:\n            raise ValueError("O descritor da atualização portátil está fora do runtime do CinePulse.")\n\n    helper_root = Path(tempfile.gettempdir()) / "CinePulseUpdater" / "handoff"\n'''
if "O pacote MSI preparado mudou após a verificação" not in manager:
    manager = replace_once(manager, old, new, "deferred MSI revalidation")

old = '''        cwd=str(Path(app_root).resolve()),\n'''
new = '''        cwd=str(app_root),\n'''
if old in manager:
    manager = replace_once(manager, old, new, "reuse resolved app root")

write(manager_path, manager)


# ---------------------------------------------------------------------------
# 3) Repair the brittle Phase 8 contract. The removed third installed-mode
# occurrence belonged to the old updater UI, not component repair.
dist_test_path = "tests/test_distribution_phase8.py"
dist = read(dist_test_path)
old = '''        self.assertGreaterEqual(studio.count('installation_mode(APP_DIR) == "installed"'), 3)\n        self.assertGreaterEqual(studio.count('command.append("-NonPortable")'), 2)\n'''
new = '''        # Two component launch/repair paths must preserve installed mode.\n        # The legacy updater used to contribute a third unrelated text match;\n        # the one-click updater now snapshots installation mode once.\n        self.assertGreaterEqual(studio.count('installation_mode(APP_DIR) == "installed"'), 2)\n        self.assertGreaterEqual(studio.count('command.append("-NonPortable")'), 2)\n        self.assertIn("install_mode = installation_mode(APP_DIR)", studio)\n        self.assertIn("installation=install_mode", studio)\n'''
if "legacy updater used to contribute" not in dist:
    dist = replace_once(dist, old, new, "phase8 installed-mode contract")
write(dist_test_path, dist)


# ---------------------------------------------------------------------------
# 4) Expand updater behavioral/security regression tests.
manager_test_path = "tests/test_update_manager.py"
tests = read(manager_test_path)
if "import hashlib\n" not in tests:
    tests = replace_once(tests, "import io\n", "import hashlib\nimport io\n", "test hashlib import")
if "    launch_staged,\n" not in tests:
    tests = replace_once(tests, "    is_newer,\n", "    is_newer,\n    launch_staged,\n", "launch_staged test import")

marker = '''    def test_stage_rejects_invalid_version_before_filesystem_or_network(self) -> None:\n'''
if "test_release_discovery_rejects_misflagged_prerelease_tag" not in tests:
    extra = '''    def test_release_discovery_rejects_misflagged_prerelease_tag(self) -> None:\n        response = _Response(_release_payload("1.2.0-rc1"))\n        with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response):\n            with self.assertRaises(ValueError):\n                check_github_release("1.1.3", installation="portable", timeout=3)\n\n    def test_checksum_fallback_must_stay_on_same_release(self) -> None:\n        payload = json.loads(_release_payload(digest=False).decode("utf-8"))\n        checksum = next(item for item in payload["assets"] if item["name"] == "SHA256SUMS.txt")\n        checksum["browser_download_url"] = (\n            "https://github.com/Faysk/CinePulse/releases/download/v9.9.9/SHA256SUMS.txt"\n        )\n        response = _Response(json.dumps(payload).encode("utf-8"))\n        with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response) as open_url:\n            with self.assertRaises(ValueError):\n                check_github_release("1.1.3", installation="portable", timeout=3)\n        self.assertEqual(1, open_url.call_count)\n\n    def test_github_update_info_is_bound_to_exact_asset_name(self) -> None:\n        with self.assertRaises(ValueError):\n            _validated_update_info(\n                UpdateInfo(\n                    "1.2.0",\n                    "https://github.com/Faysk/CinePulse/releases/download/v1.2.0/CinePulse-1.2.0-Setup.msi",\n                    "b" * 64,\n                    package_kind="msi",\n                    asset_name="different.msi",\n                    source="github-release",\n                )\n            )\n\n    def test_deferred_msi_handoff_rechecks_hash_before_launch(self) -> None:\n        with tempfile.TemporaryDirectory() as temporary:\n            root = Path(temporary)\n            updates = root / "updates"\n            staged = updates / "1.2.0" / "CinePulse-1.2.0-Setup.msi"\n            staged.parent.mkdir(parents=True)\n            staged.write_bytes(b"changed-after-staging")\n            info = UpdateInfo(\n                "1.2.0",\n                "https://github.com/Faysk/CinePulse/releases/download/v1.2.0/CinePulse-1.2.0-Setup.msi",\n                hashlib.sha256(b"original-package").hexdigest(),\n                package_kind="msi",\n                asset_name="CinePulse-1.2.0-Setup.msi",\n            )\n            with patch("cinepulse.update_manager._installed_update_root", return_value=updates):\n                with self.assertRaises(RuntimeError):\n                    launch_staged(info, staged, root / "app", 4321)\n\n'''
    tests = replace_once(tests, marker, extra + marker, "updater hardening tests")
write(manager_test_path, tests)

ux_test_path = "tests/test_update_ux.py"
ux = read(ux_test_path)
marker = '''    def test_installed_mode_uses_msi_major_upgrade_without_bootstrap_race(self) -> None:\n'''
if "test_updater_refactor_preserves_ai_install_progress_events" not in ux:
    extra = '''    def test_updater_refactor_preserves_ai_install_progress_events(self) -> None:\n        studio = self.text("src/cinepulse/studio.py")\n        self.assertIn('elif kind == "ai_install_status":', studio)\n        self.assertIn("progress_from_log(line)", studio)\n        self.assertIn('self.ai_install_progress_text.set(f"Atividade atual: {percent}%")', studio)\n\n'''
    ux = replace_once(ux, marker, extra + marker, "AI progress regression test")
write(ux_test_path, ux)


# ---------------------------------------------------------------------------
# 5) Make privacy and updater docs match the new automatic network behavior.
privacy = '''# Privacidade\n\nCinePulse é local-first:\n\n- mídia, projetos, frames, áudio e resultados de IA permanecem no computador;\n- o CinePulse não envia telemetria de uso, inventário de mídia ou dados de projeto para um servidor do projeto;\n- diagnósticos locais podem registrar versões, hardware, espaço e estado dos componentes sem enumerar vídeos ou músicas;\n- logo após abrir, o aplicativo faz uma verificação HTTPS curta da release Stable mais recente no GitHub para descobrir atualizações;\n- essa verificação envia apenas metadados normais da conexão HTTP, incluindo o endereço IP visto pelo GitHub e o `User-Agent` `CinePulse/<versão>`; nenhum caminho local, mídia, projeto, hardware detalhado ou identificador criado pelo CinePulse é anexado ao pedido;\n- falha ou bloqueio de rede nessa verificação não impede o uso local do programa;\n- downloads de atualização ou componentes só ocorrem quando necessários e usam as origens documentadas;\n- relatórios e bundles de suporte só são compartilhados quando o usuário decide fazê-lo.\n\nA checagem automática de versão existe para o botão de atualização solicitado no aplicativo e não é usada como analytics. Recursos remotos futuros devem declarar claramente quais dados saem da máquina e permanecer separados do processamento local de mídia.\n'''
write("docs/PRIVACY.md", privacy)

acceptance_path = "docs/ONE_CLICK_UPDATER_ACCEPTANCE.md"
acceptance = read(acceptance_path)
needle = "- GitHub asset URL, SemVer and SHA-256 are validated before promotion;\n"
replacement = '''- GitHub asset URL, final `x.y.z` Stable SemVer and SHA-256 are validated before promotion;\n- `SHA256SUMS.txt` fallback must come from the exact same GitHub release as the selected package;\n- a deferred MSI is SHA-256 checked again immediately before handoff, so a changed staged file is blocked;\n'''
if "a deferred MSI is SHA-256 checked again" not in acceptance:
    acceptance = replace_once(acceptance, needle, replacement, "acceptance security hardening")
needle = "- failed discovery is silent at startup; failed staging/application keeps the current installation usable;\n"
replacement = '''- failed discovery is silent at startup; failed staging/application keeps the current installation usable;\n- privacy documentation discloses the automatic GitHub version request and confirms that media/project data is not attached;\n'''
if "privacy documentation discloses" not in acceptance:
    acceptance = replace_once(acceptance, needle, replacement, "acceptance privacy disclosure")
write(acceptance_path, acceptance)

security_path = "docs/ONE_CLICK_UPDATER_SECURITY.md"
security = read(security_path)
if "Only final `x.y.z` tags" not in security:
    security += '''\n## Audit hardening\n\nOnly final `x.y.z` tags are accepted by the automatic Stable path even if a GitHub release were accidentally marked non-prerelease. The checksum fallback is accepted only from `SHA256SUMS.txt` on the exact same release URL. For MSI installs, the staged file is hashed again immediately before handoff; if it changed while CinePulse was busy, installation is blocked.\n\nThe startup discovery request is documented in `docs/PRIVACY.md`. It does not include media, project paths or a CinePulse-generated machine identifier.\n'''
write(security_path, security)


# ---------------------------------------------------------------------------
# 6) Teach permanent release/final-audit gates about the default GitHub updater.
release_gate_path = "scripts/release_gate.py"
gate = read(release_gate_path)
old = '''    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))\n    bootstrap = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8-sig"))\n'''
new = '''    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))\n    update_manager_text = (ROOT / "src" / "cinepulse" / "update_manager.py").read_text(encoding="utf-8")\n    publisher_text = (ROOT / ".github" / "workflows" / "publish-release.yml").read_text(encoding="utf-8")\n    bootstrap = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8-sig"))\n'''
if "update_manager_text =" not in gate:
    gate = replace_once(gate, old, new, "release gate updater sources")

needle = '''    for name in ("uv", "ffmpeg", "real_esrgan", "rife"):\n'''
if "github_release_contract" not in gate:
    block = '''    github_release_contract = all(\n        token in update_manager_text\n        for token in (\n            'https://api.github.com/repos/Faysk/CinePulse/releases/latest',\n            '_validate_release_asset_url',\n            'SHA256SUMS.txt',\n            'A release Stable precisa usar versão final x.y.z',\n            '_sha256_file(staged)',\n        )\n    )\n    publisher_contract = all(\n        token in publisher_text\n        for token in (\n            'Stable publisher requires x.y.z SemVer',\n            'dist/SHA256SUMS.txt',\n            'gh release',\n        )\n    )\n    require(github_release_contract, "Updater GitHub Stable sem contrato de origem/hash completo", failures)\n    require(publisher_contract, "Publisher não garante assets/hash da release consumida pelo updater", failures)\n\n'''
    gate = replace_once(gate, needle, block + needle, "release gate github updater contract")
old = '''    update_policy = "disabled" if not manifest_url else "signed"\n    print(f"CINEPULSE_RELEASE_GATE_OK version={package_version} update_channel={update_policy}")\n'''
new = '''    update_source = "signed-manifest+github-installed" if manifest_url else "github-release"\n    print(f"CINEPULSE_RELEASE_GATE_OK version={package_version} update_source={update_source}")\n'''
if "update_source={update_source}" not in gate:
    gate = replace_once(gate, old, new, "release gate output truthfulness")
write(release_gate_path, gate)

final_path = "scripts/final_audit.py"
final = read(final_path)
old = '''    publisher_workflow = (ROOT / ".github/workflows/publish-release.yml").read_text(encoding="utf-8")\n\n    manifest_url = str(channel.get("manifest_url") or "").strip()\n'''
new = '''    publisher_workflow = (ROOT / ".github/workflows/publish-release.yml").read_text(encoding="utf-8")\n    update_manager_text = (ROOT / "src" / "cinepulse" / "update_manager.py").read_text(encoding="utf-8")\n\n    manifest_url = str(channel.get("manifest_url") or "").strip()\n'''
if "update_manager_text = (ROOT / \"src\" / \"cinepulse\" / \"update_manager.py\")" not in final:
    final = replace_once(final, old, new, "final audit updater source")
old = '''    update_policy_safe = not manifest_url or signed_channel\n    neural_required = {"torch", "demucs", "soundfile"}\n'''
new = '''    github_release_update_contract_safe = (\n        all(\n            token in update_manager_text\n            for token in (\n                'https://api.github.com/repos/Faysk/CinePulse/releases/latest',\n                '_validate_release_asset_url',\n                'SHA256SUMS.txt',\n                'A release Stable precisa usar versão final x.y.z',\n                '_sha256_file(staged)',\n            )\n        )\n        and all(\n            token in publisher_workflow\n            for token in (\n                'Stable publisher requires x.y.z SemVer',\n                'dist/SHA256SUMS.txt',\n                'gh release',\n            )\n        )\n    )\n    # Portable may opt into the legacy manifest channel, but when it does that\n    # channel must be signed. Installed mode and the default portable path use\n    # the pinned GitHub release contract above.\n    update_policy_safe = github_release_update_contract_safe and (not manifest_url or signed_channel)\n    neural_required = {"torch", "demucs", "soundfile"}\n'''
if "github_release_update_contract_safe" not in final:
    final = replace_once(final, old, new, "final audit github updater safety")
old = '''        "update_policy_signed_or_disabled": update_policy_safe,\n'''
new = '''        "update_policy_trusted_source": update_policy_safe,\n        "github_release_update_contract_safe": github_release_update_contract_safe,\n'''
if '"update_policy_trusted_source"' not in final:
    final = replace_once(final, old, new, "final audit updater checks")
old = '''        "schema": 5,\n'''
new = '''        "schema": 6,\n'''
if '"schema": 6' not in final:
    final = replace_once(final, old, new, "final audit schema")
old = '''        "update_channel_mode": "signed" if manifest_url else "disabled",\n'''
new = '''        "update_channel_mode": "signed-manifest+github-installed" if manifest_url else "github-release",\n'''
if '"github-release"' not in final.split('"update_channel_mode"', 1)[1][:160]:
    final = replace_once(final, old, new, "final audit update source payload")
write(final_path, final)


# ---------------------------------------------------------------------------
# 7) Lock the audit/reporting changes themselves.
release_contract_path = "tests/test_update_release_contract.py"
release_tests = read(release_contract_path)
marker = '''    def test_updater_documentation_records_bootstrap_boundary(self) -> None:\n'''
if "test_automatic_check_is_disclosed_in_privacy_contract" not in release_tests:
    extra = '''    def test_automatic_check_is_disclosed_in_privacy_contract(self) -> None:\n        privacy = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")\n        self.assertIn("verificação HTTPS curta", privacy)\n        self.assertIn("User-Agent", privacy)\n        self.assertIn("nenhum caminho local, mídia, projeto", privacy)\n\n    def test_release_gates_model_default_github_updater(self) -> None:\n        gate = (ROOT / "scripts" / "release_gate.py").read_text(encoding="utf-8")\n        audit = (ROOT / "scripts" / "final_audit.py").read_text(encoding="utf-8")\n        self.assertIn('update_source = "signed-manifest+github-installed" if manifest_url else "github-release"', gate)\n        self.assertIn('"github_release_update_contract_safe"', audit)\n        self.assertIn('"update_policy_trusted_source"', audit)\n        self.assertNotIn('update_channel={update_policy}', gate)\n\n'''
    release_tests = replace_once(release_tests, marker, extra + marker, "release/privacy contract tests")
write(release_contract_path, release_tests)

print("CINEPULSE_UPDATER_FULL_AUDIT_PATCHED")
