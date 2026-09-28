# CinePulse 1.2.22

A 1.2.22 corrige a seleção de GPU do Demucs em máquinas com múltiplas GPUs NVIDIA.

## Demucs respeita a GPU selecionada

O CinePulse já escolhia um adaptador NVIDIA por `HardwareProfile.gpu_index` para outras etapas do pipeline, mas o Demucs ainda recebia apenas `--device cuda`. Agora o índice selecionado é propagado explicitamente e o comando usa `--device cuda:N`, incluindo adaptadores como a GPU 1.

Jobs configurados para CPU continuam usando `--device cpu` sem mudança de comportamento.

## Bootstrap não esconde GPUs secundárias

O ambiente de inicialização mantém `CUDA_DEVICE_ORDER=PCI_BUS_ID` para uma enumeração previsível, mas deixa de fixar globalmente `CUDA_VISIBLE_DEVICES=0`. Isso evita ocultar adaptadores CUDA 1+ antes que cada engine possa usar o índice escolhido pelo CinePulse.

## Cobertura

Foram adicionadas regressões para comprovar `cuda:1`, preservar o caminho CPU e impedir que o bootstrap volte a fixar globalmente a GPU 0.

A correção foi validada pelos gates Quality, Release Candidate, Installer v2 Acceptance e Recovery Reliability antes da promoção para Stable.

As limitações físicas de GPU extrema continuam acompanhadas separadamente pela issue #4.
