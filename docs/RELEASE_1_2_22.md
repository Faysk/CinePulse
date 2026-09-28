# CinePulse 1.2.22

A 1.2.22 é o patch final da auditoria #7 após a Stable 1.2.21. Ela corrige quatro deltas de lifecycle/persistência que continuavam presentes na `main` publicada.

## Lifecycle de FFmpeg

VFX, Aurora e o runner FFmpeg principal do Studio agora colocam o início da thread leitora dentro da mesma fronteira de cleanup do subprocesso. Se `Thread.start()` falhar, o processo agrupado é encerrado, pipes são fechados e a exceção original permanece visível.

O finalizador compartilhado do Studio tolera explicitamente uma thread que nunca chegou a iniciar, evitando que `join()` gere uma segunda exceção e esconda a causa real.

## Overlay Composer

O decoder base, encoder e decoder pool são criados dentro de uma única fronteira de lifecycle. Se o segundo spawn ou a preparação dos decoders falhar, qualquer processo já iniciado é reaped e seus streams são fechados.

## Persistência entre processos

`path_mutation_transaction` passa a serializar read-modify-write por path entre processos e threads:

- Windows: named mutex derivado do path normalizado;
- POSIX: `flock` em lock file hashado no diretório temporário;
- chamadas aninhadas na mesma thread permanecem reentrantes.

O JobStore usa a transação cross-process e preserva CAS/revision como segunda defesa. O store Preview do TensorRT usa a mesma serialização em `record` e `invalidate`.

## Demucs multi-GPU

A release também inclui a correção #78, já presente na `main`: o bootstrap não fixa mais `CUDA_VISIBLE_DEVICES=0`, preserva `CUDA_DEVICE_ORDER=PCI_BUS_ID` e o Demucs recebe explicitamente o `HardwareProfile.gpu_index` como `--device cuda:N`. Jobs CPU continuam em `--device cpu`.

## Cobertura

A suíte adiciona regressões para falha em `Thread.start()` em VFX/Aurora/Studio, spawn parcial do Overlay Composer e concorrência real de quatro subprocessos escrevendo no mesmo path sem lost update.

A primeira tentativa desta rodada já demonstrou o valor do gate Windows: ele bloqueou um `join()` inválido em thread não iniciada; o finalizador foi corrigido antes desta release.

## Escopo físico

A issue #4 continua sendo a única fonte de verdade para aceite físico NVIDIA/8K/120 e graduation de caminhos Preview. A 1.2.22 não converte CI hospedado em evidência de hardware.
