# Core Integrity MegaPack — Phase 1: RenderPlan

Data: 2026-08-13
Base: UX MegaPack Phase 8 sobre CinePulse `1.0.0-rc.5`

## Objetivo

A Phase 1 cria uma fonte única e testável para as decisões estruturais do render. Antes desta fase, pré-verificação, UI e worker reproduziam parte das mesmas regras de forma independente. Isso permitia divergência entre o que a interface explicava e o que o worker realmente executava.

O novo `RenderPlan` **não tenta esconder nem corrigir silenciosamente o pipeline atual**. Ele modela o comportamento vigente, inclusive os problemas apontados pela auditoria, para que as fases seguintes possam mudar a política em um único lugar.

A regra arquitetural passa a ser:

> nenhuma decisão de upscale, master, interpolação, VFX ou finalização deve ser explicada por uma camada e tomada de forma diferente por outra.

## Novo módulo

`src/cinepulse/render_plan.py`

Estruturas principais:

- `FrameSpec`: resolução, FPS e formato de pixel de uma etapa;
- `PlanRisk`: risco estrutural com código da auditoria, severidade e explicação;
- `RenderStep`: etapa declarativa com entrada, saída, dispositivo, cache/materialização e motivo;
- `PlanInput`: dados normalizados que entram no planejador;
- `RenderPlan`: sequência completa, riscos, fingerprint e serialização;
- `build_render_plan()`: função pura e determinística;
- `risks_as_warnings()`: tradução conservadora dos riscos para preflight.

## Fingerprint determinístico

Cada plano recebe um fingerprint SHA-256 truncado, calculado a partir do conteúdo serializado do próprio plano.

Exemplo:

```text
RenderPlan c923a1d6f9969ee7
```

O mesmo conjunto de decisões produz o mesmo fingerprint. Isso permite correlacionar:

- UI;
- pré-verificação;
- log;
- relatório final;
- testes;
- futuros logs persistentes por `job_id`.

## Etapas modeladas

O plano atual declara, quando aplicável:

1. melhoria espacial / Real-ESRGAN;
2. RIFE base;
3. master de estúdio;
4. transição do loop;
5. VFX reativos;
6. RIFE final;
7. enquadramento e codificação final.

Cada etapa possui um estado:

- `run`: será executada;
- `skip`: é explicitamente ignorada;
- `conditional`: pode ser tentada ou alterada por fallback/análise dinâmica.

## Integração com o worker

O worker deixa de recalcular parte das condições centrais de forma independente.

A Phase 1 já usa o plano para decidir:

- se existe master de estúdio;
- resolução e FPS do master atual;
- tentativa de RIFE base;
- tentativa de RIFE final;
- execução da etapa Real-ESRGAN selecionada.

A análise automática do loop continua ocorrendo antes do plano definitivo do job porque ela pode trocar um corte seco por uma dissolução curta. Depois dessa análise, o worker constrói o `RenderPlan` definitivo usando a transição realmente escolhida.

## Integração com a pré-verificação

A pré-verificação agora devolve:

- `render_plan` serializado;
- `render_plan_fingerprint`;
- lista explícita das etapas;
- riscos estruturais atuais com o código da auditoria.

Assim, uma configuração problemática não recebe apenas um alerta genérico. Exemplo conceitual:

```text
PLANO REAL DO PIPELINE • 3a2f...
✓ Master de estúdio: ... → 1280×720 • 60 fps • yuv420p 8-bit
✓ VFX reativos: ... → 1280×720 • 60 fps
✓ Enquadramento e codificação final: ... → 7680×4320 • 120 fps

Avisos:
• [CRÍTICO CP-001] Master interno menor que o destino ...
• [CRÍTICO CP-002] Cadência temporal é reduzida antes da saída ...
```

O objetivo desta fase é tornar a degradação **visível e rastreável**, antes de eliminá-la na Phase 2.

## Integração com Qualidade e saída

A aba `Qualidade e saída` recebe um novo card **Plano real de processamento**.

Ele apresenta:

- fingerprint;
- etapas que rodam ou são ignoradas;
- geometria/FPS de saída de cada etapa;
- contagem de riscos críticos;
- códigos dos achados relacionados.

O texto deixa claro que a Phase 1 descreve o pipeline atual e que os riscos mostrados são precisamente o trabalho das fases seguintes. Isso evita transformar o planejador em uma promessa falsa de que CP-001/CP-002 já foram corrigidos.

## Integração com relatório final

O relatório final passa a registrar:

- fingerprint do RenderPlan;
- versão da arquitetura do planejador;
- etapas executadas/ignoradas;
- riscos estruturais declarados para aquele job.

Isso cria uma trilha de auditoria mínima mesmo antes da futura Phase de logs persistentes por job.

## Riscos da auditoria já identificados pelo RenderPlan

### CP-001 — master menor que o destino

Se o master atual for menor que a saída, o plano sinaliza que a saída será reconstruída a partir daquele intermediário.

### CP-002 — redução para 60 fps

Fonte acima de 60 fps que passa pelo master atual gera risco crítico explícito.

### CP-003 — VFX 320×180/60

Quando VFX estão ativos, o plano declara o `internal_spec` real de 320×180/60 e sinaliza o risco, com severidade maior em 4K/8K ou acima de 60 fps.

### CP-004 — Real-ESRGAN x2 target-unaware

Se a fonte já atende ou excede o destino e Real-ESRGAN está selecionado, o plano mostra que o pipeline atual ainda executa x2.

### CP-006 — Preservar versus Lanczos

Quando `Preservar` precisa redimensionar, o plano avisa que nesta arquitetura os dois caminhos ainda convergem para Lanczos no master/final.

### CP-007 — 10-bit/HDR passando por master 8-bit

Fontes HDR **ou qualquer fonte acima de 8 bits** que entram no master atual recebem risco crítico.

## O que esta fase deliberadamente NÃO corrige

A Phase 1 não altera a política de qualidade para mascarar o problema.

Ainda permanecem para as próximas fases:

- master musical adaptativo/nativo;
- preservação real de FPS >60;
- Real-ESRGAN target-aware;
- distinção efetiva `Preservar` / `Lanczos` / `IA`;
- VFX escaláveis;
- intermediários 10-bit/lossless;
- estimativa de storage derivada por etapa;
- codecs por contêiner;
- color management real;
- chunking de Real-ESRGAN/RIFE.

Isto é intencional. Fazer a Phase 1 também reescrever o pipeline produziria uma mudança grande demais para saber se um eventual erro veio da arquitetura ou da nova política.

## Critérios de aceite da Phase 1

- [x] planner puro e determinístico;
- [x] fingerprint estável;
- [x] serialização completa;
- [x] preflight usa o mesmo planner;
- [x] aba Qualidade mostra o plano;
- [x] worker consome decisões do plano;
- [x] relatório final registra o plano;
- [x] CP-001/002/003/004/006/007 aparecem quando as condições correspondentes existem;
- [x] comportamento atual do render é preservado nesta fase;
- [x] suíte automatizada ampliada;
- [x] render sintético real após a integração do planner.

## Saída para a Phase 2

A próxima fase pode modificar **a política do `build_render_plan()`** para eliminar degradações espaciais/temporais e tornar Real-ESRGAN/RIFE dependentes do destino.

O worker, a pré-verificação, a UI e o relatório já estão conectados ao mesmo contrato; portanto a Phase 2 não deve precisar reimplementar essas decisões em quatro lugares diferentes.
