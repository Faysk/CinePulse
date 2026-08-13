# Core Integrity MegaPack — Phase 6

## Escopo

Phase 6 implementa o Storage Engine planejado após a auditoria: CP-005 (preflight não representava o pipeline), CP-012 (RIFE materializava diretórios completos de PNG), CP-021 (cache sem limite) e CP-022 (scratch não configurável).

## Implementação concluída

### 1. Estimativa derivada do RenderPlan

`storage_engine.estimate_storage()` percorre as etapas reais do RenderPlan e calcula pico scratch por estágio. Real-ESRGAN e RIFE só entram na conta se o planner realmente pedir essas etapas.

O preflight exibe uma seção **ARMAZENAMENTO POR ETAPA** e inclui o contrato serializado no relatório retornado à UI.

### 2. Scratch configurável

A aba Qualidade e saída ganhou seleção de disco/pasta scratch. O worker cria `job_*` no caminho escolhido, limpa jobs abandonados com mais de 24 horas e remove o job atual no `finally`.

O preflight informa volume, espaço livre/total, reserva mínima e amostra rápida de escrita.

### 3. Real-ESRGAN bounded

O Real-ESRGAN agora processa lotes limitados. Depois de cada lote:

- o resultado é transformado em segmento FFV1;
- PNGs de entrada/saída são excluídos;
- só então o próximo lote é extraído.

Os segmentos são concatenados no cache final `.mkv`.

### 4. RIFE bounded

RIFE segue o mesmo modelo de lotes, com tamanho adaptado também à razão temporal de interpolação. O diretório PNG do lote é apagado assim que o segmento FFV1 correspondente está seguro.

### 5. Intermediários liberados cedo

O worker não mantém mais toda a cadeia visual até o `finally`. Arquivos já consumidos são removidos depois que o sucessor foi criado com sucesso.

### 6. Cache quota/LRU

Nova política global de cache:

- quota configurável (50 GB padrão);
- inventário recursivo;
- hits atualizam recência;
- evicção das entradas mais antigas;
- proteção da entrada ativa;
- limpeza de diretórios vazios.

### 7. Planejamento por volume

`StoragePlan` agora contabiliza crescimento de cache no mesmo volume da saída/scratch quando aplicável. Cache em terceiro volume recebe sua própria verificação de espaço.

## Testes

Suíte automatizada: **141/141 PASS**.

Novos testes cobrem:

- chunk menor para frames maiores;
- razão RIFE influenciando o lote;
- estimator seguindo as etapas do RenderPlan;
- AI/RIFE ausentes da estimativa quando o planner os ignora;
- scratch default/override;
- cache LRU e arquivo protegido;
- recência em cache hit;
- uso recursivo do cache;
- probe de volume/espaço/velocidade;
- crescimento de cache somado ao scratch quando compartilham volume.

Integrações executadas:

- smoke Studio básico: PASS;
- matriz MP4/MOV/MKV/WebM: PASS;
- scratch customizado + preflight + cleanup do job: PASS;
- Real-ESRGAN fake end-to-end em 13 frames com lotes de 5: PASS;
- RIFE fake end-to-end 13→26 frames com lotes de 5: PASS;
- `compileall`: PASS;
- release gate: PASS.

## Estado dos achados

- CP-005: tratado no Studio ativo por estimativa por etapa derivada do RenderPlan e verificação por volume;
- CP-012: tratado por chunking Real-ESRGAN/RIFE e descarte imediato do PNG working set;
- CP-021: tratado por quota/LRU configurável;
- CP-022: tratado por scratch configurável + espaço/volume/uso previsto + amostra rápida de escrita.

## Próxima fronteira

Phase 7 — Verification & Render History:

- log persistente por `job_id`;
- `plan.json` e storage/delivery/color contracts por render;
- quick verify e deep verify;
- frame count, streams, A/V sync e decode até EOF;
- schema e migração para fila/presets.
