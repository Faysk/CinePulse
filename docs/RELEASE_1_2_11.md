# CinePulse 1.2.11

Esta release estende ao Real-ESRGAN as garantias de timeline exata que já existiam no RIFE e na entrega final.

## Chunks Real-ESRGAN com timeline exata

Os chunks lossless FFV1 não são mais concatenados por uma lista simples de arquivos. Antes da montagem, o CinePulse lê estruturalmente cada Matroska, registra sua quantidade real de packets e exige que a soma seja exatamente o número de frames esperado. O manifest de concat declara a duração de cada segmento como `frames / source_fps`, evitando acúmulo de arredondamento do timebase do Matroska.

## Master validado antes do cache

Depois do concat, o master Real-ESRGAN também é inspecionado. Se a quantidade de packets não coincidir exatamente com o contrato, o render falha antes de promover um master incompleto para o cache.

## Cache de IA mais estrito

Um arquivo existente só é reutilizado quando todas estas condições são verdadeiras:

- resolução exatamente 2x a fonte;
- codec de vídeo FFV1;
- packet count exatamente igual ao total esperado;
- duração compatível com a timeline CFR derivada da contagem de frames.

Um cache truncado, estrangeiro ou produzido por um contrato antigo incompatível é descartado e reconstruído.

## Segurança e desempenho

A mudança não reduz concorrência, não reintroduz medição de headroom e não altera modelo, escala, FPS, cor/HDR ou qualidade. Ela apenas impede que uma sequência de chunks correta seja montada com timestamps acumulativamente imprecisos ou que um cache incompleto seja tratado como válido.
