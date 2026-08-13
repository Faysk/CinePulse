# Core Integrity Phase 7 — Verification & Render History

## Objetivo

Transformar “o FFmpeg terminou” em um resultado tecnicamente comprovado e reproduzível. A Phase 7 usa o mesmo RenderPlan/DeliveryPlan das fases anteriores para validar o arquivo final e preservar evidências locais de cada execução.

## Quick verify

A verificação rápida é obrigatória para previews e renders finais.

Contrato mínimo:

1. `width × height` exatamente iguais ao alvo;
2. FPS dentro da tolerância de 0,02;
3. duração dentro da tolerância de 0,35 s;
4. `r_frame_rate` e `avg_frame_rate` compatíveis com CFR esperado;
5. `nb_read_frames`/`nb_frames` próximo de `round(duration × fps)`;
6. codec de vídeo igual ao DeliveryPlan;
7. presença/ausência de áudio igual ao projeto;
8. codec de áudio igual ao DeliveryPlan quando aplicável;
9. canais e sample rate iguais ao contrato resolvido;
10. diferença de término entre áudio e vídeo dentro de 0,35 s quando os metadados permitem medir.

Erros impedem `AtomicOutput.commit()`.

## Deep verify

Quando habilitado pelo usuário, após o quick verify:

```text
ffmpeg -v error -xerror -i <partial> -map 0:v:0 [-map 0:a:0] -f null -
```

O comando precisa chegar ao EOF com retorno zero. Assim, corrupção no fim do arquivo ou erro de decodificação não é mascarado por metadados aparentemente válidos.

## Histórico por job

Root:

`PATHS.logs / renders / <job_id>`

O `job_id` combina timestamp legível com sufixo aleatório curto para evitar colisão entre renders iniciados no mesmo segundo.

### job.json

Estado mutável do job:

- schema;
- job_id;
- status `running/success/error/cancelled`;
- preview;
- queue_id;
- versão do CinePulse;
- timestamps;
- output/report/error;
- RenderSettings serializado.

### render.log

Append-only UTF-8 durante o job. `_log()` continua alimentando a UI e simultaneamente grava o histórico ativo.

### plan.json

Serialização completa do RenderPlan e fingerprint.

### contracts.json

Snapshot de:

- ColorPipeline;
- DeliveryPlan;
- StorageEstimate;
- expectativa de verificação.

### verification.json

Resultado estruturado da verificação final com o probe que sustentou a decisão.

## Fila e presets

`state_store.py` centraliza a persistência versionada.

Política:

1. ler formato atual;
2. aceitar formato legado conhecido;
3. rejeitar schema futuro;
4. ao migrar/salvar, copiar versão anterior para `.bak`;
5. escrever `.tmp`;
6. promover com `os.replace`.

Isso evita que upgrades silenciosamente corrompam arquivos de estado antigos.

## Privacidade e suporte

O histórico local pode manter paths completos para tornar um render reproduzível na própria máquina.

Ao exportar para suporte, `export_redacted_history()` substitui prefixos absolutos por `<PATH>` antes de criar o ZIP. Nenhum upload é realizado pelo CinePulse.

## Critérios de aceite implementados

- quick verify confirma resolução/FPS/duração/codecs/streams;
- contagem real de frames é registrada;
- CFR é validado;
- áudio esperado/inesperado é validado;
- canais/sample rate são conferidos;
- A/V delta é medido quando disponível;
- deep verify decodifica até EOF;
- falha técnica impede promoção do parcial;
- todo job possui histórico persistente;
- fila/presets possuem schema, backup e migração;
- formato legado continua carregável;
- schema futuro é recusado.
