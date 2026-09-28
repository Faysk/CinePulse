# CinePulse 1.2.22

Esta release corrige a seleção de GPU no caminho de separação de stems do Demucs em máquinas com múltiplos adaptadores NVIDIA.

## GPUs CUDA permanecem visíveis

O bootstrap não define mais `CUDA_VISIBLE_DEVICES=0`. O CinePulse mantém `CUDA_DEVICE_ORDER=PCI_BUS_ID` para uma enumeração previsível, mas deixa todos os adaptadores disponíveis para a seleção feita pelo próprio `HardwareProfile`.

## Demucs segue a GPU escolhida

O índice físico escolhido pelo CinePulse agora é propagado até `build_demucs_command()`. Em processamento GPU, o Demucs recebe `--device cuda:<índice>`; em processamento CPU, continua recebendo `--device cpu`.

Isso alinha o Demucs com as demais etapas que já respeitam a GPU selecionada e elimina o caso em que RIFE/NVENC podiam usar uma GPU enquanto os stems eram enviados silenciosamente para a GPU 0.

## Regressões

A suíte cobre explicitamente uma GPU secundária (`cuda:1`), preservação do caminho CPU e o contrato de bootstrap que proíbe mascarar adaptadores com `CUDA_VISIBLE_DEVICES`.

A aceitação física NVIDIA/8K permanece no fluxo dedicado de hardware e não é substituída por estes testes de contrato.
