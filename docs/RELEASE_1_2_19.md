# CinePulse 1.2.19

Esta release endurece a Restauração Preview para que um processo FFmpeg bem-sucedido nunca seja confundido com uma saída válida sem prova estrutural.

## Promoção somente após validação

Antes de substituir o destino, o CinePulse usa FFprobe com contagem real de frames e compara a saída temporária com o contrato da fonte. Geometria, contagem de quadros, presença e quantidade de streams de áudio e timeline precisam permanecer compatíveis; qualquer divergência falha fechado e a saída anterior continua intacta.

## Temporal sem corte por áudio

O encoder temporal não usa mais `-shortest`. A quantidade de vídeo é fixa pelo frame count da fonte, enquanto o input de áudio é limitado separadamente à duração frame-bound. Assim, uma faixa de áudio que termina antes do vídeo não remove quadros reconstruídos.

## Múltiplas faixas de áudio

O caminho temporal deixa de mapear apenas `1:a:0` e preserva todas as faixas da fonte com `1:a?`. O FFprobe conta os streams de áudio antes e depois; perder uma faixa impede a promoção do temporário. A integração real cobre uma fonte com duas faixas independentes.

## Bootstrap mais resiliente

O downloader hash-locked do instalador passa a repetir falhas transitórias de rede com backoff antes de desistir. O `uv` usa o mesmo caminho verificado e o smoke neural de release recebe retry equivalente. SHA-256 continua obrigatório antes de qualquer promoção/extração.

## Color-only e VFR

O caminho simples adiciona `-fps_mode passthrough`, preservando timestamps em fontes VFR em vez de inventar uma cadência implícita. A validação continua exigindo a mesma quantidade de quadros e duração compatível.

## Teste real

A suíte cria uma fonte de 1 segundo a 4 fps com áudio de apenas 0,5 segundo e executa a reconstrução temporal real. O resultado precisa conter os quatro quadros completos, demonstrando que o áudio curto não trunca mais o vídeo.

Cancelamento, scratch guard, isolamento da Restauração Preview e as proteções Stable anteriores permanecem inalterados.
