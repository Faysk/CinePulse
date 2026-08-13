# Core Integrity Phase 2 — Preservação espacial e temporal

## Objetivo

Eliminar os caminhos em que o CinePulse reduzia qualidade espacial/temporal e depois tentava reconstruí-la. Esta fase cobre diretamente os achados CP-001, CP-002, CP-004 e CP-006 da auditoria de 13/08/2026.

## Contratos introduzidos

### 1. Master target-aware

O master usado por modo musical, transições e VFX passa a usar o canvas real do destino. Não existe mais política final fixa de 1280×720/2560×1440.

Exemplo de aceite:

```text
Fonte:   7680×4320 / 120 fps
Destino: 1920×1080 / 120 fps
Master:  1920×1080 / 120 fps
```

Não há passagem por 720p/60.

### 2. Preservação temporal

Quando a fonte já possui FPS igual ou superior ao destino, nenhum interpolador é usado para recriar quadros existentes.

- 120 → 120: preserva 120; RIFE = SKIP;
- 120 → 60: downsample intencional para 60; RIFE = SKIP;
- 24 → 60 com RIFE: master permanece 24 e ocorre uma única passagem 24 → 60;
- 24 → 60 com FFmpeg: o master alcança 60 usando o modo escolhido, sem RIFE adicional.

O antigo caminho `RIFE base` foi removido da execução do worker.

### 3. Real-ESRGAN target-aware

A decisão usa a escala geométrica necessária para `contain` ou `cover`, não apenas uma comparação ingênua de largura/altura.

- fonte maior/suficiente para o destino: IA = SKIP;
- fonte menor e framing exige upscale: IA x2 = RUN;
- portrait `contain` pode dispensar IA mesmo quando o canvas possui uma dimensão maior;
- portrait `cover` pode exigir IA se preencher o canvas requer ampliação real.

A pré-verificação deixa de reservar temporários de Real-ESRGAN quando o plano decidiu ignorá-lo.

### 4. Três políticas espaciais reais

**Preservar**

- nunca amplia pixels da fonte;
- downscale continua permitido;
- quando preencher/cobrir exigiria upscale, a imagem permanece nativa/downscaled e é centralizada no canvas.

**Lanczos**

- redimensiona explicitamente para cumprir o framing solicitado;
- pode ampliar ou reduzir.

**Real-ESRGAN**

- roda somente quando o framing realmente exige ampliação;
- continua x2 nesta fase;
- enquadramento final continua usando Lanczos após a saída neural.

### 5. VFX sem rebaixar a base para 60 fps

O gerador interno de efeitos continua 320×180/60 nesta fase, portanto CP-003 não está encerrado. Porém o filter graph não usa mais `setpts=N/(60*TB)` no vídeo-base.

Um master 120 fps permanece 120 fps durante a composição; o layer de efeito 60 fps é sincronizado sobre essa base. Tornar o próprio layer VFX target-aware é responsabilidade da Phase 3.

## Fonte única de verdade

A Phase 1 já conectava UI, preflight, worker, log e relatório ao `RenderPlan`. A Phase 2 altera a política dentro desse contrato, evitando correções duplicadas em cada consumidor.

Metadados novos do plano:

- `required_spatial_scale`;
- `spatial_upscale_required`;
- `rife_calls_planned`;
- `resolved_audit_codes`;
- `pending_audit_codes`.

## Limites deliberados

Esta fase não tenta resolver:

- CP-003: canvas/amostragem interna VFX 320×180/60;
- CP-007: masters H.264/yuv420p 8-bit e color management HDR;
- PNGs completos de IA/RIFE;
- codec/container matrix;
- scratch disk/cache LRU;
- verificação profunda.

Esses itens permanecem no roadmap para evitar misturar mudanças de qualidade espacial/temporal com outras cirurgias grandes.
