# Core Integrity MegaPack — Phase 9 Report

## Resultado

Phase 9 implementa a camada de CI e release gates sobre a base acumulada UX Phase 1–8 + Core Integrity Phase 1–8.

### Implementado

- `scripts/ci_gate.py` com perfis `source`, `cpu`, `media`, `release-light` e `gpu`;
- evidência JSON por gate e timeout individual por etapa;
- descoberta automática de Xvfb em Linux headless;
- matriz source Windows/Linux e Python 3.11/3.13;
- gate CPU obrigatório com cancelamento, delivery, storage, verification e neural chunks;
- gate media separado com VFX/HDR/SDR10 para paralelização;
- workflow Release Candidate Windows com build portátil, updater, MSI e lifecycle install/repair/uninstall;
- workflow GPU manual/self-hosted para RIFE, Real-ESRGAN e Demucs reais;
- `Build-Portable.ps1` e `Build-Msi.ps1` aceitam `-BuildPython`;
- `Test-Updater.ps1` parametrizado por versão;
- MSI lifecycle protegido contra execução acidental fora de CI;
- custom action do MSI pode ser suprimida somente pelo gate com `CINEPULSE_SKIP_BOOTSTRAP=1`;
- release gate exige os novos workflows/scripts/documentos.

### Correção encontrada pela própria Phase 9

Ao colocar `integration_cancel.py` num gate real, Linux encerrava também o processo do runner. A causa era `terminate_process_tree()` usar `killpg()` enquanto alguns `Popen` canceláveis não criavam sessão/grupo próprio. Os processos FFmpeg, RIFE, Real-ESRGAN e Demucs controlados pelo Studio agora usam `popen_group_kwargs()`.

O teste de cancelamento passou após a correção e continua preservando a saída anterior e removendo arquivos parciais/lock.

## Validação local

- unit tests: **185/185 PASS**;
- release gate: PASS;
- compileall: PASS;
- YAML parse dos três workflows: PASS;
- source gate: PASS;
- CPU gate: PASS;
- media gate: PASS;
- MP4/MOV/MKV/WebM: PASS dentro do CPU gate;
- deep verify 72/72 frames, CFR, EOF e A/V delta 0.0: PASS;
- HDR10 preserve/master e HDR→SDR VFX: PASS;
- SDR10/full range: PASS;
- cancellation/recovery: PASS;
- bounded neural chunks contract: PASS.

## Evidência externa ainda necessária

A Phase 9 não declara como executados localmente os gates que exigem Windows/GPU:

- PowerShell real;
- build WiX/MSI;
- instalação/reparo/desinstalação MSI;
- bootstrap/atualizador Windows;
- mutex Win32;
- Authenticode/Minisign real;
- GPU NVIDIA com RIFE/Real-ESRGAN/Demucs.

Esses itens agora são automatizáveis pelos workflows `release-candidate.yml` e `gpu-acceptance.yml`.

## Auditoria

A Phase 9 fecha a lacuna de os scripts `integration_*.py` ficarem fora do portão automático. Eles permanecem scripts end-to-end explícitos, mas agora são chamados por perfis de CI obrigatórios.

Continuam deliberadamente abertos para etapas posteriores/finais: CP-019, CP-020, CP-032, CP-033 e gates perceptivos/8K120 em hardware real.
