# Relatório — Core Integrity MegaPack Phase 2

**Base:** Core Integrity Phase 1 acumulada sobre UX MegaPack Phase 8
**Escopo:** CP-001, CP-002, CP-004, CP-006 + preservação da cadência base durante VFX

## Implementado

- `RenderPlan` atualizado para `core-integrity-phase2-preservation`;
- master de estúdio passa a usar resolução do destino;
- master FPS deixa de ser fixo em 60;
- RIFE base removido do worker;
- RIFE final é planejado apenas quando o FPS efetivo é menor que o destino;
- Real-ESRGAN usa escala necessária do framing (`contain`/`cover`) e pode ser SKIP mesmo quando selecionado;
- validação de componente/GPU para Real-ESRGAN torna-se target-aware;
- preflight só estima temporários de IA quando a etapa realmente será tentada;
- estimativa visual de carga/VRAM passa a obedecer ao plano real;
- Preservar impede upscale de pixels e usa canvas/padding quando necessário;
- Lanczos mantém resize explícito;
- VFX não força mais a base para `N/(60*TB)` e recebe FPS de saída do master.

## Achados da auditoria

| Código | Phase 2 |
|---|---|
| CP-001 | corrigido pela política do master target-aware |
| CP-002 | corrigido: sem 120→60→120 e sem RIFE base |
| CP-004 | corrigido: IA ignorada quando upscale não é necessário |
| CP-006 | corrigido: Preservar e Lanczos têm comportamento diferente |
| CP-003 | parcial: base preserva FPS; layer 320×180/60 ainda pendente |
| CP-007 | pendente para Color Pipeline |

## Validação automatizada

- `unittest discover`: **93/93 PASS**;
- `compileall`: PASS;
- release gate: PASS;
- `git diff --check`: PASS.

## Smoke FFmpeg real

### Preservar em canvas maior

Entrada sintética: 320×180 / 120 fps / 1 s.
Saída: 640×360 / 120 fps.

Resultado FFprobe:

```text
width=640
height=360
r_frame_rate=120/1
nb_frames=120
```

O filtro utilizado manteve `scale=320:180` e apenas adicionou `pad=640:360`, comprovando que Preservar não ampliou os pixels.

### Composição VFX sobre base 120 fps

Base sintética: 320×180 / 120 fps.
Layer de efeito: 60 fps.
Saída: 320×180 / 120 fps.

Resultado FFprobe:

```text
width=320
height=180
r_frame_rate=120/1
nb_frames=120
```

Isso comprova que a composição não rebaixa mais a cadência do vídeo-base para 60 fps.

## Próxima fronteira

Phase 3 deve atacar CP-003 por completo: resolução e cadência do próprio layer VFX, envelope musical único/cacheado e consistência entre preview e final.
