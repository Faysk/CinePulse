# CinePulse Core Integrity MegaPack

Base técnica: auditoria de 13/08/2026 + UX MegaPack Phase 8.

## Missão

Consolidar o pipeline antes do `1.0 estável` para garantir que resolução, FPS, cor, áudio, contêiner, armazenamento e recursos de IA executados correspondam ao que a interface informa.

A ordem é deliberada: nenhuma nova IA entra no caminho crítico antes de o pipeline existente ser coerente e testável.

## Phase 1 — RenderPlan

**Status: concluída neste pacote.**

- fonte única de verdade;
- etapas e specs explícitas;
- fingerprint determinístico;
- integração com preflight, Qualidade, worker, log e relatório;
- riscos CP-001/002/003/004/006/007 expostos sem fingir que já foram corrigidos.

## Phase 2 — Preservação espacial e temporal

**Status: concluída neste pacote.**

- master final target-aware, sem resolução fixa 720p/1440p;
- FPS do master derivado de fonte/destino e política de interpolação;
- fonte 120 fps → destino 120 fps preserva 120 fps;
- caminho RIFE base removido e RIFE limitado a uma passagem realmente necessária;
- Real-ESRGAN x2 ignorado quando o framing não requer upscale;
- `Preservar` impede ampliação de pixels, `Lanczos` redimensiona explicitamente e `IA` só entra quando há ganho espacial necessário;
- composição VFX deixa de retimar o vídeo-base para 60 fps, embora o layer interno 320×180/60 continue pendente para a Phase 3;
- CP-001, CP-002, CP-004 e CP-006 tratados pela nova política; CP-003 e CP-007 continuam visíveis no RenderPlan.

## Phase 3 — VFX e envelope musical

**Status: concluída neste pacote.**

- removida dependência final do canvas fixo 320×180/60;
- gerador dimensionável e temporalmente target-aware;
- VFX nativos até 4K/120, com política adaptativa explícita acima disso;
- envelope musical completo a 120 fps, normalizado antes do recorte;
- cache RAM/SSD compartilhado por preview renderizado e final;
- CP-003 e CP-013 tratados; gate perceptivo 8K a 100% continua pendente.

## Phase 4 — Color pipeline

**Status: concluída neste pacote.**

- novo `color_pipeline.py` como contrato explícito de cor;
- intermediários color-critical em FFV1, preservando 10-bit quando o estágio suporta;
- HDR limpo permanece HDR/10-bit;
- HDR diante de VFX/transição é tone-mapped explicitamente para SDR BT.709;
- Real-ESRGAN/RIFE atuais são tratados honestamente como fronteiras SDR 8-bit;
- gamut/range conversion real via `zscale`, tone mapping e dithering controlado;
- full/limited preservado em caminho limpo;
- saída nunca volta a ser rotulada HDR/10-bit depois de uma fronteira que perdeu essa informação;
- CP-007 tratado no caminho ativo do Studio.

## Phase 5 — Codecs, contêineres e áudio

**Status: concluída neste pacote.**

- novo `delivery.py` resolve perfil, extensão, contêiner, vídeo, áudio, bit depth e compatibilidade antes do render;
- MP4 → HEVC + AAC; MOV master → ProRes 422 HQ + PCM 24-bit; MKV arquivo → HEVC + FLAC; WebM → VP9 + Opus;
- FFmpeg ativo é consultado para confirmar encoders obrigatórios;
- 10K/12K e 144/240/480 fps são bloqueados no perfil estável até validação específica de hardware/codec;
- HFR até 120 fps permanece permitido com aviso de compatibilidade;
- master/arquivo preservam canais/sample rate quando o codec permite;
- RenderPlan/preflight/UI/worker/verificação final compartilham o mesmo contrato de entrega;
- CP-008, CP-009 e CP-015 tratados no caminho ativo do Studio.

## Phase 6 — Storage Engine

**Status: concluída neste pacote.**

- novo `storage_engine.py` deriva pico scratch e crescimento de cache das etapas reais do RenderPlan;
- preflight mostra armazenamento por etapa, volume, espaço e uma amostra rápida de escrita do scratch;
- scratch disk configurável na aba Qualidade e saída, separado da pasta de destino quando desejado;
- Real-ESRGAN e RIFE processam lotes limitados de PNG em vez de materializar o projeto inteiro;
- lotes neurais são convertidos em segmentos FFV1 lossless e os PNGs são removidos antes do lote seguinte;
- intermediários já consumidos são removidos durante o job, reduzindo o pico simultâneo;
- cache global passa a ter quota configurável, recência atualizada nos hits e limpeza LRU automática;
- espaço de saída, scratch e crescimento do cache são somados corretamente quando compartilham o mesmo volume;
- CP-005, CP-012, CP-021 e CP-022 tratados no caminho ativo do Studio.

## Phase 7 — Verification & Render History

**Status: concluída neste pacote.**

- quick verify obrigatório confirma geometria, FPS, CFR, frame count, duração, streams, codecs, canais, sample rate e sync temporal;
- deep verify opcional decodifica vídeo/áudio até EOF com erro fatal em corrupção;
- cada job ganha `job.json`, `render.log`, `plan.json`, `contracts.json` e `verification.json`;
- relatório humano inclui a evidência técnica e aponta para o histórico local;
- fila e presets passam a usar JSON versionado com backup, migração de formato legado e bloqueio de schema futuro;
- fila persiste/abre o histórico técnico do job;
- CP-014, CP-023 e CP-029 tratados no caminho ativo do Studio.

## Phase 8 — Runtime e distribuição

**Status: concluída em código neste pacote; aceite Windows fica para o gate da Phase 9.**

- MSI e portátil usam launchers/roots distintos e o MSI não ativa o self-updater in-place;
- Python gerenciado e versão fixada tornam-se obrigatórios no runtime distribuído;
- descoberta de PowerShell é centralizada e prioriza PowerShell 7;
- named mutex por usuário bloqueia segunda instância no Windows, com PID lock testável em CI;
- versão MSI passa a derivar da release e o branding usa `cinepulse.ico`;
- runtime lock exige hash e o build portátil gera SBOM CycloneDX;
- canal de update pode exigir assinatura destacada antes do parse do manifesto;
- build MSI possui hook Authenticode real, mas nenhuma assinatura é reivindicada sem certificado;
- CP-010/017/018/030/031 tratados em código; CP-019/020 continuam explicitamente parciais até chave/release real e lock transitivo completo.

## Phase 9 — CI e release gate

**Status: concluída em código neste pacote; execuções Windows/GPU reais permanecem evidência externa obrigatória.**

- novo `ci_gate.py` centraliza perfis source, CPU, release-light e GPU e grava evidência JSON;
- matriz source roda Windows/Linux em Python 3.11/3.13;
- smokes CPU históricos passam a fazer parte de um gate obrigatório em CI;
- Release Candidate Windows executa integração, build portátil, updater, MSI e validação do payload;
- build scripts aceitam Python de build explícito sem enfraquecer o runtime gerenciado distribuído;
- GPU gate é manual/self-hosted e executa RIFE, Real-ESRGAN e Demucs reais somente em máquina NVIDIA preparada;
- artifacts de gate/distribuição são preservados para auditoria;
- aceite de MSI/PowerShell/assinaturas continua condicionado a uma execução verde no Windows real.

## Regra de avanço

Cada fase deve fechar:

1. implementação pequena e auditável;
2. testes unitários/integração correspondentes;
3. smoke real quando tecnicamente possível;
4. documentação do que foi corrigido e do que continua pendente;
5. pacote extraído e revalidado antes de iniciar a fase seguinte.

## Final Audit & Release Candidate Acceptance

**Status: código auditado; aceite externo Windows/NVIDIA pendente.**

- matriz CP-001…CP-033 reconciliada com o código acumulado;
- nenhum P0 original permanece sem correção arquitetural no caminho ativo do Studio;
- CP-016 foi fechado no polish final: a UI usa `Aceleração automática` e o RenderPlan exibe dispositivo por etapa;
- execução direta do pytest foi corrigida com `pythonpath = ["src"]`;
- permanecem explicitamente CP-011, CP-019, CP-020, CP-027, CP-032 e CP-033;
- `scripts/final_audit.py` registra evidência estática reproduzível;
- `scripts/Invoke-RcAcceptance.ps1` reúne gates Windows, builds e GPU opcional;
- `docs/RC_ACCEPTANCE_CHECKLIST.md` define os gates perceptivos e de hardware que não podem ser simulados no container.

A promoção para `1.0.0` continua proibida até o aceite Windows/NVIDIA, os renders reais obrigatórios e a decisão sobre CP-011/019/020.
