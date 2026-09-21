# CinePulse 1.2.18

Esta release fecha no Overlay Composer o mesmo tipo de lacuna temporal que já havia sido corrigida no pipeline principal.

## Composer frame-bound de ponta a ponta

O Composer já renderizava um número inteiro exato de quadros, porém o mux final ainda aplicava `-t profile.duration`. Em cadências fracionárias, como 30000/1001 fps, `round(duration*fps)` pode representar uma timeline ligeiramente maior que o decimal original. Cortar o mux pelo decimal podia remover o último quadro.

A 1.2.18 passa a:

- calcular uma vez a contagem exata de quadros;
- derivar a duração CFR por `frames/fps`;
- limitar somente o input de áudio por essa duração;
- limitar o vídeo por `-frames:v`;
- contar os quadros do mux com FFprobe antes da promoção atômica.

## Áudio e visualizadores

A análise de envelopes do Composer usa a mesma duração CFR realmente entregue. O áudio continua em stream-copy no mux de referência; a mudança não reencoda nem reduz qualidade.

## Verificação

Um teste de integração com FFmpeg cobre uma base estática em 30000/1001 fps, áudio separado e duração nominal de 1,0 s. O contrato exige 30 quadros completos, equivalentes a uma timeline CFR de 1,001 s.

AtomicOutput, cancelamento, Preview parity, full-utilization e os contratos de recovery da 1.2.17 permanecem inalterados.
