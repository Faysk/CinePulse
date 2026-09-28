# CinePulse 1.2.21

Esta release promove para Stable o hardening acumulado depois da 1.2.19. O foco é confiabilidade: identidade de conteúdo, concorrência, recuperação crash-safe e encerramento determinístico de subprocessos.

## Identidade de conteúdo e caches

Caches e evidências deixam de confiar apenas em caminho, tamanho e mtime quando isso pode aceitar conteúdo trocado no mesmo arquivo. Real-ESRGAN, Demucs, envelopes musicais, visualizer, restauração Preview, Composer, TensorRT e histórico passam a vincular decisões ao conteúdo relevante.

## Concorrência e durabilidade

Publicação de caches usa temporários únicos por execução. Checkpoints e evidências com read-modify-write são serializados por caminho e publicados com flush/fsync apropriado, evitando perda de atualização e arquivos parcialmente promovidos.

## Lifecycle de processos

Rotas Stable, Preview, Aurora, Real-ESRGAN, RIFE e recovery encerram árvores de processos e fecham pipes mesmo quando polling, progresso ou leitura de stdout falha inesperadamente. Isso reduz risco de FFmpeg/IA órfãos após exceções.

## Recovery e worker

A recuperação RIFE faz promoção crash-safe e compartilha a mesma identidade de cache usada pelo render normal. Ownership de render é exclusivo entre instâncias, comandos de worker presos em `processing` podem ser reconciliados após crash e payloads/replies inválidos falham fechado.

## Componentes experimentais

Downloads passam a respeitar contratos explícitos de tamanho, reavaliar espaço quando servidores ignoram Range e rejeitar estruturas ZIP inseguras. Marcadores de instalação também ficam vinculados à integridade da árvore instalada.

## Aceitação

A matriz hospedada da `main` já passou em Windows/Linux, Python 3.11–3.14.7, CPU e mídia antes deste PR. O PR de release executa novamente Quality, Release Candidate e o publisher completo de Windows, incluindo Portable, updater, MSI e ciclo install/repair/uninstall antes de publicar.

A aceitação física NVIDIA/8K continua separada na issue #4. Nenhum gate hospedado é tratado como prova de hardware físico.
