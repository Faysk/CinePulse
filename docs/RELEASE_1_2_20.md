# CinePulse 1.2.20

Esta release publica o hardening acumulado desde o v1.2.19 e corrige a última divergência confirmada no caminho multi-GPU do Demucs.

## Multi-GPU consistente

O bootstrap não força mais `CUDA_VISIBLE_DEVICES=0`. Todas as GPUs CUDA permanecem visíveis, enquanto `CUDA_DEVICE_ORDER=PCI_BUS_ID` mantém a enumeração previsível. O adaptador escolhido pelo `HardwareProfile` continua sendo o índice autoritativo do render.

O Demucs agora recebe esse mesmo índice explicitamente e usa `--device cuda:<índice>`. Jobs CPU continuam emitindo `--device cpu`. Isso elimina o caso em que RIFE/NVENC estavam na GPU selecionada enquanto a separação de stems caía silenciosamente na GPU 0.

## Crash safety, recovery e estado

Desde 1.2.19, a main recebeu hardening adicional para tornar checkpoints, estado de controle, publicação de componentes, promoção de saídas finais e recovery mais resistentes a interrupções e concorrência. Discovery de recovery permanece estritamente read-only e promoções críticas usam contratos de integridade antes de substituir evidência válida.

## Identidade de conteúdo e cache

Caches e evidências passam a depender da identidade real do conteúdo em mais rotas, incluindo mídia, música, visualizer, compositor, Real-ESRGAN, TensorRT e Restauração Preview. Substituir um arquivo preservando tamanho/mtime não deve mais reutilizar resultado incompatível.

## Lifecycle de processos

FFmpeg, subprocessos neurais e prefetch/background são coletados de forma determinística em fluxos normais, cancelamentos e saídas excepcionais, reduzindo risco de processos órfãos e recursos presos após falhas.

## Updater e installer

A release também inclui reforços no estado do updater, integridade de arquivos instalados, validação de archives experimentais e limites de download antes de promoção/extração.

## Validação desta release

A PR de 1.2.20 adiciona regressões específicas para o Demucs em GPU secundária e para impedir que o bootstrap volte a mascarar adaptadores CUDA. Os gates Quality, Release Candidate e Publish Release permanecem obrigatórios antes da publicação Stable.
