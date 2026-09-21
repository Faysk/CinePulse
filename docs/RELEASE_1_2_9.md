# CinePulse 1.2.9

A 1.2.8 eliminou cortes globais por timestamp e tornou vídeo/intermediários frame-bound. A 1.2.9 fecha a outra metade do contrato: o áudio passa a terminar exatamente na mesma linha do tempo dos quadros entregues.

## Duração real do CFR

A duração de entrega agora é derivada de `frame_count / fps`. Isso importa quando `round(project_duration*fps)` arredonda para cima ou para baixo: o vídeo real pode diferir do decimal de origem por até meio frame.

## Áudio trim/pad exato

Studio, VFX fused e recovery usam a duração frame-bound para limitar o input de áudio. Depois, a cadeia de entrega aplica `atrim`, `asetpts` e `apad=whole_dur`, preservando qualquer filtro de mastering/loudness no meio da cadeia.

Assim:

- áudio longo não cria cauda depois do último frame;
- áudio ligeiramente curto não termina antes do vídeo por causa do arredondamento CFR;
- preview e self-test continuam curtos sem reintroduzir `-t` global no mux;
- mastering continua dentro do mesmo contrato temporal.

## Proteções mantidas

Continuam ativos frame count exato, full-utilization, multi-GPU pinning, fallback pós-falha real, AtomicOutput, recovery crash-safe e verificação final com tolerância zero de frames.
