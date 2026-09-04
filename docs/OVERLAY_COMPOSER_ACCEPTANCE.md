# Overlay Composer Preview — Acceptance Status

> Branch: `preview-overlay-composer-clean`
>
> Escopo: Overlay Composer Preview. Este documento **não promove** a feature para Stable e não autoriza merge automático em `main`.

## Estado atual

**Automated Preview gates: GREEN** na branch isolada baseada diretamente em `main`.

Evidência autoritativa atual:

- head: `961a3764010b0a46ee1bed29b285e2491482242e`;
- `Overlay Composer Preview` run **33900543902** — **PASS**;
- `Quality` run **33900544449** — **PASS**;
- base: `main` em `04a3ae829412177e78249523b0f57ed4f300fbcd`.

O run Overlay atual também executa no Windows o helper `scripts/Invoke-OverlayAcceptance.ps1 -GenerateOnly` e exige que ele produza `environment.json` e `ACCEPTANCE.md`. Esse passo passou no job Windows.

A branch limpa foi criada para eliminar histórico e arquivos não relacionados que existiam na branch experimental anterior. O gate de isolamento compara `origin/main...HEAD` e rejeita qualquer arquivo fora do allowlist do Overlay Composer.

## Evidência automatizada

### Overlay Composer Preview

Run `33900543902` concluiu com sucesso:

- `Overlay branch isolation` — PASS;
- `Overlay unit · ubuntu-latest` — PASS;
- `Overlay unit · windows-latest` — PASS;
- `Overlay media integration · Linux` — PASS;
- `Overlay media integration · Windows` — PASS;
- `Overlay streaming soak · Linux` — PASS;
- `Generate manual acceptance evidence pack` no Windows — PASS.

No job unit Ubuntu, **52 testes** passam no snapshot isolado da `main`; o mesmo conjunto passa no job Windows.

### Quality geral do CinePulse no PR

Run `33900544449` passou integralmente:

- Source · Ubuntu · Python 3.11 — PASS;
- Source · Ubuntu · Python 3.13 — PASS;
- Source · Windows · Python 3.11 — PASS;
- Source · Windows · Python 3.13 — PASS;
- CPU integration · Linux — PASS;
- Media integrity · Linux — PASS.

### O que esses gates provam

#### Isolamento da feature

- a branch Preview é baseada diretamente em `main`;
- o diff contém somente arquivos explicitamente permitidos do Overlay Composer;
- Recovery Mega Pack, release tooling e outros subsistemas não fazem parte deste PR;
- scaffolding temporário de integração foi removido;
- o CI falha se esse scaffolding reaparecer;
- o CI falha se arquivos não relacionados forem introduzidos na branch Preview.

#### Modelo e persistência

- schema `cinepulse.overlay-scene/1` válido e serialização determinística;
- backward compatibility para settings legados sem `overlay_scene_json`;
- cena acompanha preset, fila, restore e `RenderSettings`;
- fonte de asset ausente bloqueia o render em vez de omitir a layer silenciosamente.

#### Editor

- add/remove de PNG, GIF e visualizer;
- z-order;
- undo/redo;
- agrupamento;
- movimento e escala proporcional do grupo;
- preservação da geometria relativa durante escala;
- grupo não sofre transformação parcial quando contém layer bloqueada;
- handle de resize do grupo possui hit-test direto mesmo quando cai em área vazia do canvas;
- layouts rápidos possuem geometria determinística.

#### Preview

- composição alpha e clipping fora do canvas;
- waveform reage a estado de áudio;
- barras preservam transparência;
- spectrum usa representação em linha no preview;
- spectrum espelhado ocupa os dois lados esperados;
- ordem de composição asset/visualizer é respeitada.

#### FFmpeg real

Os testes de mídia executam FFmpeg real em Linux e Windows e validam:

- PNG estático via streaming;
- GIF animado/loopado;
- waveform;
- barras espelhadas;
- quantidade configurável de barras;
- espessura aproximada;
- cores principal/secundária;
- stream de áudio presente;
- duração e resolução esperadas;
- saída visual não permanece plana.

#### Longform

O contrato longform usa um projeto lógico de **7.200 segundos (2 h)** e verifica que a arquitetura do overlay não materializa uma sequência `duração × FPS` de frames temporários.

O número de inputs auxiliares depende da quantidade de assets/visualizers, não da quantidade total de frames do projeto.

Também existe um soak FFmpeg real de **30 segundos** em Linux com PNG + GIF loopado + múltiplos visualizers, escrevendo em sink `null` e verificando ausência de expansão de sequência temporária de overlay.

#### Harness físico Windows

`scripts/Invoke-OverlayAcceptance.ps1` gera uma sessão local em `artifacts/overlay-acceptance/` contendo:

- `environment.json` com inventário de máquina/runtime;
- `ACCEPTANCE.md` com checklist físico/perceptual;
- opcionalmente `soak-samples.csv` e `soak-summary.json` quando usado com `-MonitorMinutes`.

O helper coleta, quando disponível, branch/head, working tree, Windows, PowerShell, Python, FFmpeg, CPU, RAM, displays, DPI do registro, NVIDIA/VRAM/temperatura, discos e espaço livre.

O helper **não decide automaticamente** se uma temperatura é segura nem promove a feature por conta própria.

## Garantias que NÃO estamos declarando

Os gates acima **não** significam que qualquer projeto 4K/8K/12K ou qualquer composição de 2 h terá tempo de render, VRAM ou consumo de CPU constantes.

Eles também não provam equivalência pixel-a-pixel entre o preview NumPy e o render FFmpeg.

A arquitetura evita crescimento de scratch proporcional ao número de frames do overlay, mas o custo computacional ainda cresce com resolução, FPS, área ocupada, quantidade de GIFs e complexidade dos filtros.

## Gates manuais ainda pendentes antes de considerar Stable

- abrir e operar o Composer no Windows real do CinePulse;
- validar drag/resize/group/preset visualmente com mouse em DPI 100% e pelo menos um cenário de scaling do Windows;
- gerar preview real com música do usuário e confirmar sensação de waveform/barras/espectro;
- render 1080p e 4K reais;
- executar pelo menos um teste 8K quando a máquina/tempo permitirem;
- soak físico de projeto longo (ideal 1–2 h) acompanhando RAM/VRAM, disco, temperatura e tamanho de scratch;
- confirmar qualidade/performance com o encoder usado normalmente pelo CinePulse;
- revisar visualmente safe areas para o destino real antes de publicar.

O procedimento operacional está em `docs/OVERLAY_COMPOSER_MANUAL_ACCEPTANCE.md`.

## Rollout

1. Manter o PR #3 como **draft**.
2. Executar `scripts/Invoke-OverlayAcceptance.ps1` na máquina física antes da sessão.
3. Executar gates manuais/perceptuais e preencher o `ACCEPTANCE.md` gerado.
4. Registrar problemas encontrados sem promover a feature silenciosamente.
5. Somente depois decidir se a feature entra em Stable, permanece Preview ou recebe nova rodada de polimento.

## Regra de promoção

**Automated green ≠ Stable accepted.**

A promoção depende de automated green **e** aceitação manual/perceptual nos cenários físicos acima.
