# CinePulse 1.2.10

Esta release fecha uma inconsistência residual do recovery após a adoção da timeline frame-bound.

## Uma única duração real

O vídeo final já é definido por uma quantidade inteira de quadros. A duração real da entrega é, portanto, `frame_count / fps`. O recovery ainda usava `contract.duration` em alguns pontos, valor que vem da duração decimal original da fonte e pode diferir por uma fração de frame em cadências como 23.976, 29.97 e 59.94 fps.

A 1.2.10 usa a duração frame-bound em todo o caminho de entrega do recovery.

## Loudness

A primeira passagem de loudness agora mede exatamente a janela que será entregue. Isso evita calcular medições com alguns milissegundos fora da timeline CFR real e depois aplicar essas medições a uma janela ligeiramente diferente.

## Self-test

O self-test continua pedindo aproximadamente 0,10 s, mas primeiro converte essa janela em uma quantidade inteira de frames. A expectativa de verificação passa a usar a duração que esses frames realmente representam.

## Verificação final

`VerifyExpectation` usa a mesma duração frame-bound do encode. A contagem de quadros continua com tolerância zero, e os contratos de áudio/canais/sample-rate permanecem inalterados.

## Segurança

Não há mudança de modelo, escala, FPS alvo, cor/HDR, codec, qualidade de encoder, full-utilization ou política de fallback. A alteração apenas elimina duas fontes de verdade para a duração do mesmo arquivo.
