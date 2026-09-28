# CinePulse 1.2.21

Esta release conclui a parte corrigível por código da auditoria final #7 e consolida o hardening pós-1.2.19 já integrado na main.

## Lifecycle de processos

- VFX e Aurora mantêm o processo FFmpeg dentro da fronteira de cleanup mesmo se a thread de leitura falhar ao iniciar.
- O runner FFmpeg do Studio sempre reap o subprocesso, fecha stdout e limpa a referência foreground em falhas de startup/progresso/cancelamento.
- O Overlay Composer também limpa o decoder já iniciado quando o spawn do encoder ou a preparação dos decoders falha.

## Persistência e concorrência

- A serialização de read-modify-write por path passa a funcionar entre processos, não apenas entre threads da mesma instância.
- Windows usa named mutex reentrante por path; POSIX usa flock em arquivo de lock hashado.
- JobStore usa a mesma transação cross-process e continua exigindo CAS/revision.
- A evidência Preview do TensorRT serializa record/invalidate para impedir lost updates concorrentes.

## Hardening consolidado da #76

- identidade compartilhada/content-aware de caches e evidências;
- publicação concorrente segura de caches de música/visualizer;
- cleanup determinístico de subprocessos neurais e recovery RIFE;
- checkpoint transactions com fsync e identidade de conteúdo no histórico;
- fingerprint de conteúdo para Restoration/TensorRT e evidência do compositor.

## Validação

A PR desta release executa os gates de Quality/Recovery/Installer/Release Candidate/Publish Release no head exato. A publicação Stable só ocorre após merge na main e reexecução do publisher.

## Escopo físico

A issue #4 continua sendo a fonte de verdade para aceite físico NVIDIA, incluindo 8K/120 e graduation de caminhos Preview. Esta release não converte CI hospedado em evidência de hardware físico.
