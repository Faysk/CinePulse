# CinePulse 1.2.22

A 1.2.22 é um patch de correção para seleção de GPU no caminho de separação de stems com Demucs.

## Seleção multi-GPU consistente

O CinePulse já escolhia um adaptador NVIDIA por `HardwareProfile.gpu_index` e usava esse índice em etapas como RIFE e NVENC. O Demucs, porém, recebia apenas `--device cuda`, o que podia direcionar o trabalho para a GPU 0 mesmo quando o restante do render estava pinado em outro adaptador.

Agora o comando Demucs recebe explicitamente `cuda:N` usando o índice selecionado pelo mesmo perfil de hardware. Jobs configurados para CPU continuam usando `--device cpu`.

## Bootstrap sem ocultar adaptadores

O bootstrap continua definindo `CUDA_DEVICE_ORDER=PCI_BUS_ID` para manter a ordem dos índices previsível, mas não define mais `CUDA_VISIBLE_DEVICES=0`. Assim, GPUs CUDA adicionais permanecem visíveis e cada estágio pode selecionar seu adaptador explicitamente.

## Cobertura

A regressão cobre seleção da GPU 1, preservação do caminho CPU e o contrato do bootstrap que impede pinning global em `CUDA_VISIBLE_DEVICES`.

A aceitação física de 8K/120 e demais capacidades extremas continua acompanhada separadamente pela issue #4. Esta release não transforma CI hospedado em prova física de hardware.
