# CinePulse 1.2.21

Esta release consolida o hardening pós-1.2.19 e fecha os bugs corrigíveis por código identificados na auditoria final. O aceite físico de GPU/8K permanece separado em #4 e não é promovido por esta release sem execução no runner NVIDIA dedicado.

## Lifecycle de processos mais determinístico

Os caminhos de FFmpeg, Real-ESRGAN, RIFE, Demucs, Aurora, VFX e Composer agora fecham pipes e encerram árvores de subprocessos também em saídas excepcionais. Falhas entre o `Popen` e o início da thread de leitura deixam de permitir children órfãos ou handles presos.

O Composer também trata corretamente falha ao iniciar o encoder ou o pool de decoders depois que o decoder base já foi criado.

## Persistência e recuperação

Mutações duráveis por caminho passam a ser serializadas entre threads e processos. No Windows o CinePulse usa mutex nomeado por caminho; em POSIX usa `flock` sobre lockfile derivado do caminho. Isso fecha a janela de lost update em stores de estado e no `JobStore`, mantendo CAS/revision checks como defesa adicional.

Checkpoints, promoção de outputs e metadados críticos usam publicação atômica e fsync onde aplicável. Discovery de recovery permanece somente leitura até uma ação explícita.

## Cache e identidade de conteúdo

Caches de mídia, Real-ESRGAN, Demucs, visualizer, restoration, TensorRT e evidência de compositor deixam de depender apenas de path/size/mtime. Identidades content-aware evitam reuso de resultados quando um arquivo é substituído preservando metadados.

Publicação de caches temporários passa a usar nomes únicos, reduzindo colisões entre writers concorrentes.

## Componentes, downloads e instalador

Readiness de componentes neurais exige os arquivos reais e não vazios necessários para cada runtime. Downloads experimentais respeitam tamanho fixado, SHA-256, limites de extração e estruturas ZIP seguras. Markers de instalação são vinculados à integridade da árvore instalada.

O updater e os estados de controle falham fechado para payloads malformados e persistem markers críticos de forma durável.

## Cobertura

A matriz de regressão cobre concorrência real entre processos, falhas de spawn/thread, cancelamento, promoção atômica, cache identity e recovery. Os workflows Quality, Recovery Reliability e Release Candidate continuam sendo os gates de software para publicação Stable.

## Limitação física conhecida

A issue #4 continua sendo a fonte de verdade para graduação física de GPU/8K/120 e recovery no hardware NVIDIA alvo. Esta release não transforma fila/skipped/unavailable desse workflow em PASS.
