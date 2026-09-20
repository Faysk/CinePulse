# CinePulse 1.2.6

Esta release continua o full-utilization da 1.2.5, mas evita reaprender a mesma falha em cada lote e corrige a consistência multi-GPU do pipeline.

## Memória de fallback do RIFE por render

Quando um chunk precisa recuar de `3:3:3` para `2:2:2` ou `1:1:1` após OOM real, o safe runner publica a política aplicada e o Studio reaproveita esse nível nos chunks seguintes. O override nunca pode ser mais agressivo que a política full-utilization e não consulta VRAM livre.

## Contagem exata em RIFE chunked

Taxas fracionárias como 60000/1001→120 podiam acumular erro ao arredondar cada chunk isoladamente. Em um caso de 21.745 frames fonte, isso representava 43 frames de saída a menos. A 1.2.6 distribui o alvo pela posição cumulativa dos chunks e bloqueia a montagem se a contagem final não coincidir exatamente com o contrato.

## GPU fixa por render

O Studio passa ao RIFE o índice de GPU já selecionado para o render. Isso evita executar `nvidia-smi` novamente em cada chunk apenas para redescobrir o mesmo adaptador. O encode final HEVC/NVENC baseline, o fast-path resident e o recovery passam a usar a mesma identidade de GPU.

## Recovery

- jobs antigos usam todos os threads lógicos detectados atualmente, mesmo que tenham sido salvos com um `cpu_threads` menor;
- RIFE recovery usa o índice de GPU detectado em vez de `-g 0` fixo;
- o sinalizador `-u` é aplicado apenas para geometria UHD, mantendo 1080p/1440p fora do modo UHD desnecessário;
- diagnósticos de recovery deixam de rotular todo erro de quadro preto como 'modo UHD'.

## Segurança mantida

A versão não reintroduz throttling preventivo por telemetria. Fallback continua sendo acionado por falha concreta, validação de PNG/mídia segue fail-closed, e AtomicOutput/cancelamento/verificação final permanecem inalterados.
