# Especificação — manifesto e máquina de estados de render

**Status:** desenho normativo para implementação

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026
**Schema inicial proposto:** `cinepulse.render-job/1`

## 1. Objetivo

Definir o estado durável que permite observar, pausar, retomar, migrar e verificar um render sem depender da memória da interface. O manifesto não substitui logs, RenderPlan ou resultados de verificação; ele os referencia e mantém a visão transacional do job.

## 2. Identificadores

| Identificador | Vida útil | Função |
|---|---|---|
| `job_id` | todo o projeto de render | identidade estável mostrada na fila e histórico |
| `attempt_id` | uma execução/reexecução | separa retries e mantém erros anteriores |
| `phase_id` | uma fase da tentativa | identifica etapa e implementação usada |
| `unit_id` | lote/segmento/janela | menor trabalho promovido atomicamente |
| `artifact_id` | vida do artefato | liga caminho, identidade, contrato e dependentes |
| `owner_nonce` | uma lease | evita confundir PID reciclado com worker original |

IDs são opacos. Números sequenciais podem existir como `ordinal`, mas não substituem identidade.

## 3. Localização

Estrutura proposta:

```text
<data>/logs/renders/<job_id>/
  job.json
  manifest.json
  manifest.json.bak
  events.jsonl
  plan.json
  contracts.json
  verification.json
  attempts/<attempt_id>/
    attempt.json
    commands.jsonl
    errors.jsonl
```

O scratch contém material pesado e um ponteiro mínimo:

```text
<scratch>/job_<token>/
  cinepulse-job-ref.json
  checkpoints/
  stages/
  partials/
  quarantine/
```

O histórico em dados do aplicativo é a âncora. Scratch pode desaparecer; nesse caso o job continua visível, porém possivelmente `blocked` ou reiniciável de fase anterior.

## 4. Estrutura do manifesto

Exemplo ilustrativo; campos e enums só se tornam API depois de testes/migração:

```json
{
  "schema": 1,
  "kind": "cinepulse.render-job",
  "job_id": "20260826-203826-da124c70",
  "revision": 42,
  "created_at": "2026-08-26T20:38:26+01:00",
  "updated_at": "2026-08-30T16:23:23+01:00",
  "state": "verifying",
  "reason": "count_frames",
  "render_plan": {
    "fingerprint": "...",
    "path": "plan.json"
  },
  "source": {
    "path_hint": "<source>\\nova.mp4",
    "size": 1373182226,
    "mtime_ns": 1787771897826697100,
    "volume": {
      "id": "windows-volume-guid-or-serial",
      "bus": "usb",
      "filesystem": "ntfs"
    },
    "probe_fingerprint": "..."
  },
  "attempt": {
    "attempt_id": "attempt-0004",
    "started_at": "...",
    "owner": {
      "pid": 1234,
      "process_start": "...",
      "nonce": "...",
      "heartbeat_at": "..."
    }
  },
  "phase": {
    "name": "verification",
    "phase_id": "verification-v1",
    "status": "running",
    "units_total": 43533,
    "units_committed": 21766,
    "unit_kind": "frames_counted",
    "last_commit": "frame-00021766",
    "started_at": "..."
  },
  "artifacts": [],
  "expectation": {
    "width": 7680,
    "height": 4320,
    "fps_num": 120,
    "fps_den": 1,
    "frames": 43533,
    "video_codec": "hevc",
    "audio_codec": "aac"
  },
  "last_error": null,
  "cleanup": {
    "eligible": false,
    "accepted_at": null
  }
}
```

## 5. Identidade da fonte e dos artefatos

### Fonte

A comparação mínima usa:

- volume ID/serial;
- caminho relativo ou file ID quando disponível;
- tamanho;
- mtime em nanossegundos;
- fingerprint do probe;
- hash parcial ou integral apenas quando o custo e o risco justificarem.

Letra de unidade e caminho absoluto são pistas, não identidade suficiente. Se a fonte reaparecer com outra letra e a identidade forte coincidir, o usuário pode confirmar a reconexão.

### Artefato

Cada artefato declara:

- `role`: cache, segment, master, partial, final, quarantine ou evidence;
- caminho e volume;
- tamanho/mtime;
- produtor: fase, versão, modelo e argumentos normalizados;
- dependências;
- contrato de mídia;
- validações executadas e versão do validador;
- estado: `partial`, `committed`, `rejected`, `superseded`, `missing` ou `accepted`.

Um artefato não pode ser `committed` enquanto o arquivo estiver aberto pelo produtor.

## 6. Estados do job

| Estado | Significado |
|---|---|
| `queued` | aceito para execução, sem owner |
| `preflight` | identidade, contratos, espaço e componentes em validação |
| `running` | fase produtiva ativa |
| `pause_requested` | pedido recebido; aguardando fronteira segura |
| `paused` | nenhum subprocesso mutável; checkpoint consistente |
| `interrupted` | owner desapareceu sem fechamento normal |
| `auditing` | artefatos existentes em inspeção somente leitura |
| `repairing` | unidades rejeitadas sendo substituídas com preservação |
| `recoverable` | retomada segura disponível |
| `blocked` | divergência exige decisão ou recurso externo |
| `verifying` | entrega fechada em validação, ainda parcial |
| `complete` | verificação aprovada e saída promovida |
| `cancelled` | execução cancelada; política de retenção ainda se aplica |
| `discarded` | usuário autorizou limpeza e ela terminou com inventário |

## 7. Transições permitidas

```text
queued -> preflight
preflight -> running | blocked | cancelled
running -> pause_requested | verifying | interrupted | recoverable | blocked | cancelled
pause_requested -> paused | interrupted | blocked
paused -> recoverable | cancelled
interrupted -> auditing
auditing -> recoverable | repairing | blocked
repairing -> auditing | recoverable | blocked
recoverable -> preflight | cancelled
verifying -> complete | recoverable | blocked
cancelled -> recoverable | discarded
complete -> discarded
blocked -> auditing | recoverable | cancelled
```

Regras:

- `complete` nunca retorna para `running`; uma nova entrega cria nova tentativa ou novo job conforme a mudança;
- `discarded` é terminal;
- `blocked` exige `reason_code` e ação sugerida;
- transição inválida falha sem incrementar `revision`.

## 8. Estados da unidade

```text
planned -> producing -> validating -> committed
                      -> rejected -> quarantined
producing -> interrupted
interrupted -> planned | quarantined
```

Somente `committed` avança `units_committed`. O diretório e o nome do arquivo não determinam o estado sem o contrato correspondente.

## 9. Protocolo de commit

Para cada unidade:

1. conferir owner/lease;
2. registrar evento `unit_started`;
3. produzir em diretório/arquivo parcial exclusivo da tentativa;
4. flush e fechamento do produtor;
5. validar estrutura e mídia;
6. registrar resultado de validação;
7. promover com operação atômica no mesmo volume;
8. atualizar manifesto em revisão seguinte;
9. registrar `unit_committed` append-only;
10. somente então liberar temporários filhos conhecidos.

Se o processo morrer entre 7 e 8, a auditoria de retomada pode reconhecer o arquivo promovido, revalidá-lo e reconciliar o manifesto. Nunca deve confiar apenas no nome.

## 10. Escrita do manifesto

Protocolo:

1. adquirir lock do store;
2. ler revisão atual;
3. validar transição e compare-and-swap da revisão;
4. serializar JSON determinístico em `manifest.json.tmp-<nonce>`;
5. flush e `fsync` do arquivo quando suportado;
6. preservar versão anterior como `.bak` por substituição controlada;
7. `os.replace` do temporário;
8. reabrir e validar schema/revision em operações críticas;
9. liberar lock.

Diretório fsync não deve ser anunciado como garantido em plataformas onde não é suportado. O teste de recuperação deve simular truncamento e interrupção nos pontos relevantes.

## 11. Lease e heartbeat

Campos mínimos:

- PID;
- início real do processo;
- nonce aleatório;
- host ID local;
- heartbeat timestamp;
- phase/unit atual;
- contador monotônico de progresso;
- subprocessos conhecidos.

Uma lease só é stale se:

1. heartbeat excedeu o limite da fase;
2. PID não existe ou o início do processo não coincide;
3. nenhum subprocesso registrado continua escrevendo o artefato;
4. auditoria somente leitura não encontrou atividade recente.

GPU baixa ou tamanho de arquivo parado por poucos minutos não bastam para declarar stale.

## 12. Progresso e ETA

Cada fase declara:

- unidade total e confirmada;
- progresso observado ainda não confirmado;
- custo estimado e amostras recentes;
- condição limitante observada;
- peso global derivado do plano/storage, nunca constante universal.

O global é calculado por fases confirmadas + fração da fase atual. O UI sempre mostra a fase para impedir que “100% da interpolação” seja confundido com “arquivo final pronto”.

## 13. Classificação de erros

| Classe | Exemplo | Ação padrão |
|---|---|---|
| `retryable_unit` | processo morreu antes do commit | refazer somente unidade |
| `retryable_phase` | master parcial inválido | preservar parcial e refazer fase |
| `needs_storage` | falta de espaço/volume ausente | pausar e oferecer migração |
| `needs_source` | fonte desconectada | bloquear até reconectar/confirmar |
| `quality_repairable` | segmento preto | auditar e reparar unidades |
| `contract_mismatch` | fonte/modelo/config mudou | bloquear e pedir decisão |
| `unsupported_schema` | job de versão futura | preservar e abrir com versão compatível |
| `fatal_integrity` | manifesto e backup ilegíveis | bloquear, exportar evidência, não mutar |

Cada erro possui código estável, mensagem simples, detalhe técnico redigível, retryability e artefatos afetados.

## 14. Descoberta e reconciliação

Ao iniciar:

1. ler índices de jobs conhecidos;
2. verificar manifests não terminais;
3. correlacionar referências nos scratch roots configurados;
4. conferir lease;
5. executar auditoria barata e somente leitura;
6. reconciliar arquivos promovidos sem revisão somente após validação;
7. classificar estado;
8. publicar item para a fila.

Não varrer todo o computador nem apagar órfãos durante discovery.

## 15. Compatibilidade e privacidade

- schema futuro é rejeitado sem mutação;
- migração é incremental e mantém backup;
- paths completos ficam locais;
- export de suporte substitui paths/volume IDs por tokens consistentes;
- nenhum manifesto ou heartbeat é enviado pela rede;
- comandos exportados removem dados que identifiquem mídia pessoal;
- manifests nunca incluem conteúdo de vídeo/áudio.

## 16. Critérios de aceite da especificação

- round-trip determinístico;
- revisão monotônica e compare-and-swap;
- transições ilegais recusadas;
- recuperação de `.bak` testada;
- disputa de dois writers testada;
- lease stale e PID reciclado testados;
- reconciliação pós-commit/pré-manifest testada;
- source reconnection por volume identity testada;
- redaction testada;
- todos os requisitos RH-FUN-001–014 e RH-MIG-001–007 possuem teste ou pendência explícita.
