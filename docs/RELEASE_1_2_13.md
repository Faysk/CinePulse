# CinePulse 1.2.13

Esta release continua a filosofia full-utilization: o CinePulse não reduz carga preventivamente por telemetria. Em vez disso, os encoders auxiliares acelerados recebem fallback CPU somente depois de uma falha real do processo.

## Master SDR

O master intermediário SDR continua começando com H.264/NVENC no adaptador selecionado. Se essa codificação falhar, o parcial é descartado e o mesmo comando é repetido uma vez com libx264. Geometria, filtros, quantidade de frames e contrato de cor permanecem iguais.

## Transições

As transições usam a mesma estratégia. FFV1/lossless não é afetado; apenas o caminho H.264/NVENC ganha retry CPU após falha.

## VFX

O renderer VFX agora trabalha com no máximo duas tentativas de encoder:

- intermediário acelerado: `h264_nvenc` → `libx264` após falha;
- entrega fused: os argumentos NVENC da `DeliveryPlan` → argumentos CPU equivalentes fornecidos pelo Studio.

O envelope musical, efeitos, frame count, áudio frame-bound, muxer e metadados de cor são preservados entre as tentativas. Cancelamento nunca é convertido em retry.

## Classificação do retry

O fallback CPU é acionado somente quando as linhas reais do FFmpeg indicam falha de GPU/NVENC. Erros de disco, filtro, input e outras falhas não-GPU continuam fail-fast e preservam o diagnóstico original.

## Finalização comum

O caminho final sem VFX também prepara um comando equivalente totalmente CPU (`libx265`). Se o fast-path resident ou o NVENC baseline falhar por erro classificado como GPU, o partial é descartado e a entrega é repetida sem depender novamente de NVENC.

## Proteções mantidas

Continuam ativos AtomicOutput, verificação final, integridade de frames/pacotes, timeline CFR exata, pinning multi-GPU, cancelamento de processos e fallbacks neurais pós-falha.
