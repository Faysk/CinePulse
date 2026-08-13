# Core Integrity Phase 6 — Storage Engine

## Objetivo

Corrigir os achados CP-005, CP-012, CP-021 e CP-022 da auditoria de 13/08/2026 sem alterar a intenção artística do render. A fase torna armazenamento uma parte explícita do contrato de execução, reduz o working set neural e permite que temporários sejam movidos para um SSD dedicado.

## Arquitetura

Novo módulo `src/cinepulse/storage_engine.py`.

O Storage Engine recebe o `RenderPlan` já resolvido pelas fases anteriores e calcula, por etapa:

- artefato persistente esperado;
- working set temporário;
- pico simultâneo no scratch;
- crescimento potencial de cache;
- tamanho de lote Real-ESRGAN;
- tamanho de lote RIFE.

A pré-verificação deixa de somar uma heurística genérica a partir de resolução/fonte. Ela passa a usar as etapas que o mesmo RenderPlan entregará ao worker.

## Scratch disk

`RenderSettings` passa a carregar:

- `scratch_dir`;
- `cache_quota_gb`.

A aba **Qualidade e saída → Uso da máquina** permite escolher a pasta/disco de scratch. O preflight mostra:

- caminho real;
- identidade do volume;
- espaço livre/total;
- pico scratch estimado;
- reserva mínima;
- pequena amostra sequencial de escrita, cacheada por volume por 15 minutos.

A medição de escrita é apenas indicativa; não é apresentada como benchmark formal.

## Real-ESRGAN em chunks

O fluxo anterior extraía todos os quadros do trecho para PNG, executava o Real-ESRGAN sobre o diretório completo e só depois montava o vídeo.

A Phase 6 usa lotes target-aware:

1. escolhe um número máximo de frames a partir de um orçamento de working set;
2. extrai apenas o lote atual;
3. executa Real-ESRGAN;
4. codifica o resultado do lote em FFV1 lossless;
5. remove PNGs de entrada e saída;
6. avança para o lote seguinte;
7. concatena os segmentos lossless no master de cache.

Assim, o projeto completo deixa de coexistir como PNG de entrada + PNG aprimorado.

## RIFE em chunks

RIFE adota a mesma política:

1. extrai um lote limitado da fonte;
2. gera somente os frames interpolados daquele lote;
3. compacta o lote em FFV1;
4. remove os diretórios PNG;
5. concatena os segmentos ao final.

O tamanho do lote considera a razão `target_fps/source_fps`, portanto uma interpolação 24→120 usa lotes menores que 24→48 sob o mesmo orçamento de scratch.

## Liberação antecipada de intermediários

O worker agora remove intermediários temporários assim que a etapa seguinte foi promovida com sucesso:

- color prepass após IA/master;
- master após transição;
- transição/master após VFX;
- VFX/master após RIFE;
- último intermediário visual após codificação final.

Isso faz a estimativa de **pico simultâneo** representar o comportamento real, em vez de assumir que todos os arquivos temporários permanecem até o fim.

## Cache LRU

O cache global possui quota configurável.

A política:

- soma arquivos recursivamente;
- ordena por recência `max(atime, mtime)`;
- atualiza a recência de entradas reutilizadas;
- remove entradas mais antigas até voltar à quota;
- permite proteger a entrada criada/usada pelo job atual;
- remove diretórios vazios em best effort.

A quota é uma política de retenção. O preflight ainda contabiliza o espaço necessário para escrever a nova entrada de cache antes da evicção posterior.

## StoragePlan por volume

A validação diferencia:

- volume de saída;
- volume de scratch;
- volume de cache.

Quando dois ou três caminhos compartilham o mesmo volume, seus consumos são somados e a reserva mínima é aplicada uma única vez naquele volume. Isso evita tanto dupla contagem quanto subestimação.

## Limites conhecidos

- FFV1 dos lotes neurais reduz o risco de perdas acumuladas, mas pode produzir segmentos grandes;
- a estimativa continua sendo uma previsão e deverá ser calibrada com renders reais grandes no gate final;
- chunks RIFE são independentes; validação perceptiva de fronteiras de lote permanece parte do aceite Windows/GPU;
- a amostra de velocidade do scratch é pequena e serve apenas como alerta operacional;
- cache de componentes/instaladores não é tratado como cache de render e continua fora da limpeza LRU.

## Critérios de aceite implementados

- fonte/destino e etapas reais alimentam a estimativa;
- scratch pode estar em volume diferente da saída;
- Real-ESRGAN não mantém PNGs do projeto inteiro;
- RIFE não mantém PNGs do projeto inteiro;
- entradas antigas do cache são removidas automaticamente ao exceder a quota;
- cache hit atualiza recência;
- preflight bloqueia falta de espaço considerando saída + scratch + cache por volume;
- job temporário usa o scratch escolhido e é removido ao concluir/cancelar/falhar.
