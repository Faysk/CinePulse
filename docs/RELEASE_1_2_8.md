# CinePulse 1.2.8

Esta release continua a limpeza temporal da 1.2.7. O foco é impedir que um limite de duração necessário para áudio volte a cortar vídeo CFR e eliminar os últimos intermediários do Studio que ainda usavam `-t` global.

## Áudio com janela própria

Studio, VFX fused e recovery usam `bounded_audio_input_args()`, que emite `-t <duração> -i <áudio>`. Assim o limite pertence somente à entrada de áudio. O vídeo continua limitado exclusivamente por quantidade de quadros.

Isso é especialmente importante em preview e self-test: a faixa original pode ter vários minutos, enquanto o vídeo de teste tem poucos segundos. Sem a janela no input, o mux podia continuar por causa do áudio mesmo depois que `-frames:v` encerrava o vídeo.

## Intermediários sem corte por timestamp

- master do Studio: `-frames:v round(video_duration*work_fps)`;
- materialização de cor: `-frames:v round(duration*source_fps)` + validação estrutural de pacotes FFV1;
- comparação A/B: FPS derivado do resultado processado, hstack em cadência explícita e limite por frames.

## Resultado

O caminho principal do Studio deixa de usar `-t` como limite global de vídeo. Duração continua sendo usada para progresso, análise de loudness e janela de input de áudio, mas não para decidir quantos quadros CFR devem existir.

## Proteções mantidas

Continuam ativos full-utilization, pinning multi-GPU, fallback pós-falha real, AtomicOutput, verificação final com tolerância zero de frames e recovery crash-safe.
