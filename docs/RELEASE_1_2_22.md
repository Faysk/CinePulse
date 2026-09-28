# CinePulse 1.2.22

A 1.2.22 corrige a seleção de GPU do Demucs em máquinas com múltiplos adaptadores NVIDIA.

## Demucs respeita a GPU selecionada

O CinePulse já escolhia um adaptador por `HardwareProfile.gpu_index` para etapas como RIFE/NVENC, mas o Demucs usava `--device cuda` sem índice. Agora a separação de stems recebe o mesmo índice e executa com `--device cuda:<índice>`.

Jobs configurados para CPU continuam usando `--device cpu`.

## Bootstrap multi-GPU

O bootstrap deixa de definir `CUDA_VISIBLE_DEVICES=0`, portanto adaptadores CUDA secundários não são ocultados globalmente. `CUDA_DEVICE_ORDER=PCI_BUS_ID` permanece ativo para manter a enumeração previsível.

## Cobertura

A suíte inclui regressões que provam `cuda:1` quando a GPU 1 é selecionada, `cpu` no modo CPU e ausência de pinning global de `CUDA_VISIBLE_DEVICES` nos bootstraps.

A aceitação física de GPU/8K continua separada na issue #4 e não é promovida por esta release.
