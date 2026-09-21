# CinePulse 1.2.14

Esta release estende ao recovery crash-safe a filosofia da 1.2.13: aceleração primeiro, mas sem perder um trabalho recuperável por uma falha real do NVENC.

## Recovery final GPU→CPU

O self-test e o encode final do recovery continuam tentando o encoder configurado originalmente. Quando o caminho usa NVENC e as linhas reais do FFmpeg indicam uma falha GPU/NVENC, o CinePulse remove o partial da tentativa falha e repete uma única vez com a variante CPU equivalente da mesma `DeliveryPlan`.

## Fail-fast preservado

Não existe retry genérico. Erros de disco, filtro, input, timeout ou outras falhas não classificadas como GPU continuam interrompendo a operação imediatamente e preservam o diagnóstico original.

## Contrato de saída preservado

O fallback troca apenas o backend do encoder. Resolução, FPS, quantidade exata de frames, cor/HDR, áudio frame-bound, muxer, bitrate contratual e verificação final continuam os mesmos.

## Verificação coerente

O helper de recovery devolve a `DeliveryPlan` realmente usada na tentativa vencedora. Assim, self-test e verificação final continuam conferindo o codec e o áudio contra a rota que efetivamente produziu o arquivo.
