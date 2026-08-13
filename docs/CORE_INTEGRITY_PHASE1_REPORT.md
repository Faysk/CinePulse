# CinePulse Core Integrity MegaPack — Phase 1 Report

Data: 2026-08-13

## Escopo fechado

Esta fase implementa o `RenderPlan` como fonte única de verdade para as decisões estruturais do pipeline **sem alterar ainda a política de qualidade auditada**.

Base de trabalho:

- UX MegaPack Phase 8;
- CinePulse `1.0.0-rc.5`;
- auditoria técnica de 13/08/2026.

## Entregas implementadas

### 1. Novo domínio `render_plan.py`

- `FrameSpec`;
- `PlanRisk`;
- `RenderStep`;
- `PlanInput`;
- `RenderPlan`;
- fingerprint determinístico;
- serialização para dicionário/JSON;
- mensagens resumidas de etapa;
- riscos com código da auditoria.

### 2. Worker conectado ao plano

O worker agora consulta o RenderPlan para:

- execução da etapa Real-ESRGAN selecionada;
- existência do master de estúdio;
- geometria e FPS do master atual;
- tentativa de RIFE base;
- tentativa de RIFE final.

A análise automática do loop continua antes do plano definitivo porque pode alterar a transição real. O plano do job é construído depois dessa decisão.

### 3. Pré-verificação conectada ao plano

O retorno de `_preflight_report()` agora inclui:

- `render_plan`;
- `render_plan_fingerprint`;
- etapas reais do pipeline;
- riscos estruturais convertidos em avisos explícitos.

### 4. Qualidade e saída

Novo card `Plano real de processamento` mostra:

- fingerprint;
- etapas que rodam/ignoram;
- resolução/FPS de cada saída intermediária;
- quantidade de riscos críticos;
- códigos CP correspondentes.

### 5. Log e relatório final

Cada render registra:

```text
RenderPlan <fingerprint> • <architecture_version>
PLAN <etapa>
PLAN RISK <risco>
```

O relatório final também recebe o fingerprint, a sequência de etapas e os riscos declarados.

## Achados da auditoria modelados nesta fase

| Código | Detecção no RenderPlan | Corrigido nesta fase? |
|---|---|---|
| CP-001 | master menor que destino | Não; explicitado para Phase 2 |
| CP-002 | fonte >60 fps passando por master 60 | Não; explicitado para Phase 2 |
| CP-003 | VFX interno 320×180/60 | Não; explicitado para Phase 3 |
| CP-004 | Real-ESRGAN x2 mesmo com destino menor | Não; explicitado para Phase 2 |
| CP-006 | Preservar e Lanczos ainda convergem | Não; explicitado para Phase 2 |
| CP-007 | HDR/10-bit passando por master 8-bit | Não; explicitado para Phase 4 |

A escolha de **não corrigir esses P0 ao mesmo tempo que introduzimos o planejador é intencional**. Esta fase separa arquitetura de política para reduzir risco de regressão e permitir que as próximas correções sejam testadas contra uma fonte única de decisão.

## Testes automatizados

Baseline UX Phase 8: 69 testes.

Após Phase 1:

**82/82 PASS**

Novos testes cobrem:

- master fixo atual e riscos espaciais/temporais;
- fonte 120 fps;
- original sem master;
- Real-ESRGAN x2 target-unaware;
- RIFE base/final;
- RIFE desnecessário quando fonte já atende FPS;
- canvas VFX 320×180/60;
- HDR e SDR 10-bit passando por master 8-bit;
- ambiguidade Preservar/Lanczos;
- transição condicional do auto-loop;
- fingerprint/serialização determinísticos;
- códigos de risco preservados nas mensagens;
- validação de dimensões/FPS inválidos.

## Validações técnicas adicionais

- `compileall src tests`: PASS;
- `scripts/release_gate.py`: `CINEPULSE_RELEASE_GATE_OK version=1.0.0rc5`;
- `git diff --check`: sem erro de whitespace nas mudanças;
- GUI headless/Xvfb: aba Qualidade abre com o novo card: PASS;
- cenário visual 1280×720/120 → 8K/120 com VFX exibe quatro riscos críticos no RenderPlan: PASS.

## Render sintético real após a integração

Entrada:

- vídeo: 640×360/30 fps;
- música WAV: 2 s;
- modo Loop musical;
- Lanczos;
- 720p/60;
- repetição de quadros;
- CPU;
- sem VFX.

Saída verificada:

- 1280×720;
- 60 fps;
- HEVC;
- `yuv420p10le`;
- AAC 48 kHz estéreo;
- arquivo final criado atomicamente.

O log registrou:

```text
RenderPlan c923a1d6f9969ee7
PLAN ✓ Master de estúdio ... → 1280×720 • 60 fps • yuv420p 8-bit
```

O relatório final registrou o mesmo fingerprint e todas as etapas.

## Limites conscientes da Phase 1

Ainda não são considerados resolvidos:

- master musical fixo;
- perda 120→60→120;
- Real-ESRGAN target-aware;
- RIFE target-aware na nova política;
- Preservar realmente diferente de Lanczos;
- VFX nativos/escaláveis;
- intermediários 10-bit/lossless;
- estimativa de storage derivada por etapa;
- color management real;
- container/codec matrix;
- chunking IA/RIFE.

## Próximo boundary

**Core Integrity Phase 2 — Spatial & Temporal Preservation**

Objetivos:

1. remover redução espacial/temporal desnecessária do render final;
2. preservar FPS original quando já atende ao destino;
3. impedir Real-ESRGAN quando destino é menor, salvo futuro modo explícito de restauração;
4. executar RIFE apenas quando `target_fps > effective_source_fps`;
5. tornar Preservar, Lanczos e IA realmente distintos;
6. fazer o worker obedecer a nova política apenas alterando o RenderPlan, mantendo UI/preflight/log/relatório sincronizados.

## Package verification

O ZIP provisório foi validado antes do fechamento final:

- CRC do ZIP: PASS;
- extração em pasta limpa: PASS;
- `compileall`: PASS;
- suíte extraída: **82/82 PASS**;
- `scripts/release_gate.py`: PASS;
- GUI extraída abriu a aba Qualidade: PASS;
- render musical sintético executado **a partir do pacote extraído**: PASS;
- saída do pacote extraído: 1280×720/60, HEVC `yuv420p10le`, áudio AAC;
- log do pacote extraído contém o fingerprint do RenderPlan: PASS.

Após esta atualização documental, o pacote final deve ser reconstruído e seu SHA-256 publicado junto com a entrega.
