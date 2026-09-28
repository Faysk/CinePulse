# CinePulse 1.2.21

A 1.2.21 publica o conjunto de hardening acumulado depois da 1.2.19. A 1.2.20 não foi publicada como Stable separada; esta release reúne as correções de lifecycle, persistência, recovery, identidade de cache e integridade que já estavam na `main`.

## Lifecycle e cancelamento mais determinísticos

Caminhos clássicos e neurais passam a fechar/reap processos e pipes também quando ocorre exceção durante polling, prefetch, Preview, Aurora, Studio ou recovery. Isso reduz processos filhos órfãos, handles presos e temporários que permaneciam bloqueados depois de falhas.

## Persistência e promoção crash-safe

Pending update, promoção final de render, checkpoints e evidências de policy usam publicação durável e serialização onde existe read-modify-write concorrente. Recovery discovery permanece somente leitura; RIFE/recovery evita deixar uma saída válida em estado ambíguo durante promoção.

O delivery verificado continua sendo a fonte autoritativa depois do commit final, evitando que cleanup ou telemetria posterior reclassifiquem um artefato já validado.

## Ownership e recuperação de worker

Somente uma instância pode possuir um render ativo por vez. Comandos de worker que ficaram presos por crash anterior podem ser recuperados pelo protocolo persistente sem assumir trabalho pertencente a outro job.

## Caches ligados ao conteúdo real

Caches e evidências deixam de confiar apenas em caminho, tamanho ou `mtime` quando isso poderia aceitar um arquivo diferente com metadados iguais. A identidade passa a incorporar conteúdo nos caminhos de mídia, Real-ESRGAN, Composer, envelopes de música, visualizer, restauração, histórico e TensorRT.

Publicação concorrente de caches de música/visualizer usa temporários únicos e promoção atômica, impedindo colisões entre produtores simultâneos.

## Componentes e arquivos experimentais

Bootstrap/component readiness é vinculado ao conteúdo realmente instalado. Archives experimentais rejeitam estruturas inseguras, a prontidão depende da integridade da árvore extraída e downloads respeitam limites explícitos de bytes.

## Cobertura

A suíte ganhou regressões para cleanup excepcional de subprocessos, concorrência de checkpoint/cache, invalidação de identidade quando o conteúdo muda sem alterar metadados e integridade das promoções crash-safe.

As limitações físicas continuam separadas: 8K/120 e demais claims de GPU extrema ainda dependem do gate de hardware real acompanhado pela issue #4.
