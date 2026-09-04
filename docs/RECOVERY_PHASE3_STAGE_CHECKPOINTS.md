# Recovery & Reliability Mega Pack — Phase 3: Stage Checkpoints

**Status:** implementation candidate
**Base:** Phase 2 (`6c75f7992d839e4350983c3e1766709ec6c56b25`)
**Gate alvo:** G3

## Entrega

Esta phase transforma progresso em unidades idempotentes. Arquivo existente deixa de ser sinônimo de trabalho confirmado.

### StageCheckpointStore

Cada stage recebe checkpoint com:

- job/attempt/stage;
- fingerprint da política;
- revision;
- unidades identificadas por `unit_id` e `ordinal`;
- estados `planned`, `producing`, `validating`, `committed`, `rejected`, `quarantined`, `interrupted`;
- artefato, contrato e resultado de validação.

Checkpoint com job/attempt/policy divergente é recusado; não é reaproveitado silenciosamente.

### AtomicStageAdapter

Protocolo por unidade:

1. reconciliar final já existente somente após validar;
2. registrar `producing`;
3. produzir em parcial exclusivo no mesmo diretório/volume;
4. registrar `validating`;
5. validar contrato;
6. `os.replace(partial, final)`;
7. registrar `committed`;
8. só então executar cleanup conhecido.

Se houver queda entre promoção e checkpoint, o final é preservado e a retomada revalida/reconcilia. Se houver queda antes da promoção, somente a unidade corrente é refeita; parciais continuam como evidência.

### MediaStageAdapter

Adapter de mídia comum para RIFE/upscale/master/delivery:

- resolução;
- FPS;
- codec;
- pixel format;
- contagem mínima ou exata de frames via FFprobe.

Isso também fecha a lacuna encontrada na auditoria: `pix_fmt` passa a fazer parte explicitamente do contrato de unidade, em vez de ser apenas afirmado na documentação.

## Fault matrix automatizada

Há injeção determinística nos pontos:

- antes do producer;
- depois do producer;
- depois da validação;
- depois da promoção;
- depois do checkpoint.

Todos os caminhos devem convergir para o mesmo resultado final `committed`. Depois de uma promoção já concluída, a retomada não pode executar novamente o producer caro.

## Integração incremental

Os adapters são independentes de Tk e encaixam diretamente no `RenderWorker`. O recuperador RIFE específico continua preservado como referência comprovada. O pipeline legacy de `studio.py` ainda não é removido nesta phase; a troca por adapters ocorre no rollout opt-in, evitando uma reescrita monolítica do arquivo legado.

## Gate G3

- parcial nunca conta como concluído;
- final sem checkpoint só é reconciliado após validação;
- checkpoint committed com artefato ausente bloqueia;
- falhas antes/durante/depois do commit convergem;
- contrato de mídia inclui `pix_fmt` e frame count;
- nenhuma limpeza acontece antes de commit.
