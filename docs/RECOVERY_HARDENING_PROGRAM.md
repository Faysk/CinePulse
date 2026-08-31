# Programa de aprimoramento — recuperação e robustez

**Status:** plano executável aprovado para implementação incremental

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026

**Revisão:** ao concluir cada gate ou alterar o RenderPlan/worker
**Origem:** pós-mortem do job real 8K/120 `20260826-203826-da124c70`

## 1. Objetivo

Transformar as correções específicas do incidente em uma capacidade genérica do CinePulse: qualquer render compatível deve sobreviver a fechamento da interface, queda do processo, reinicialização e falha recuperável de armazenamento sem perder unidades confirmadas nem promover mídia corrompida.

Este programa trata todos os riscos conhecidos. Ele não promete impedir queda de energia, defeito físico, falha de driver ou artefato artístico de IA; promete detectar, conter, explicar e recuperar com segurança sempre que os dados necessários permanecerem disponíveis.

## 2. Fontes e documentos normativos

- [Requisitos rastreáveis](RECOVERY_REQUIREMENTS.md);
- [Manifesto e máquina de estados](RECOVERY_MANIFEST_AND_STATE_MACHINE.md);
- [Interface e operação](RECOVERY_UI_AND_OPERATIONS.md);
- [Matriz de testes e falhas](RECOVERY_TEST_MATRIX.md);
- [Migração e rollout](RECOVERY_ROLLOUT_AND_MIGRATION.md);
- [Runbook técnico atual](RIFE_RECOVERY_RUNBOOK.md);
- [Pós-mortem](INCIDENT_2026-08-26_RIFE_8K120.md).

## 3. Princípios de execução

1. Preservar antes de migrar.
2. Separar verdade durável de estado visual da interface.
3. Confirmar unidades pequenas e idempotentes.
4. Revalidar antes de reutilizar.
5. Tornar falhas explícitas e classificadas.
6. Não apagar evidência automaticamente.
7. Introduzir a nova rota em fatias reversíveis.
8. Exigir testes de queda, não apenas testes de sucesso.
9. Tratar qualidade técnica e qualidade perceptiva como gates diferentes.
10. Não declarar capacidade genérica com base em um único job recuperado.

## 4. Dependências entre etapas

```text
Etapa 0 — baseline preservado
  -> Etapa 1 — domínio e manifesto
      -> Etapa 2 — worker durável e ownership
          -> Etapa 3 — checkpoints por fase
              -> Etapa 4 — gates de qualidade
              -> Etapa 5 — armazenamento e staging
                  -> Etapa 6 — descoberta e UX
                      -> Etapa 7 — fault injection e aceite físico
                          -> Etapa 8 — migração e rollout
                              -> Etapa 9 — operação e melhoria contínua
```

Qualidade e armazenamento podem avançar em paralelo depois que o contrato da Etapa 3 estiver estável, mas nenhuma UX de “retomar” deve ser liberada antes de os dois gates existirem.

## 5. Resumo dos gates

| Etapa | Entrega principal | Gate para avançar |
|---|---|---|
| 0 | baseline e inventário | recuperação atual reproduzível e evidências preservadas |
| 1 | modelo `RenderJobManifest` | schema, migração e transições passam em testes |
| 2 | worker/lease/heartbeat | fechar UI não mata ou duplica job; pausa segura funciona |
| 3 | adapters/checkpoints | queda em cada fase perde no máximo uma unidade |
| 4 | gates de mídia | corrupção/preto/truncamento/timeline são barrados |
| 5 | storage orchestration | falta de espaço/USB/staging falham com preservação |
| 6 | recuperação na interface | job reaparece e ações conduzem ao fluxo correto |
| 7 | matriz de falhas | suites automatizadas + aceite Windows/NVIDIA passam |
| 8 | rollout/migração | jobs antigos preservados; rollback da feature funciona |
| 9 | operação | runbooks, retenção e revisão contínua ativos |

## 6. Etapa 0 — congelar e provar o baseline

### Objetivo

Evitar que a generalização destrua a única recuperação real já comprovada.

### Trabalho

- inventariar os arquivos ainda não versionados do recuperador e seus testes;
- separar artefatos temporários de revisão de código que pertence ao produto;
- registrar um ponto Git recuperável antes da refatoração, sem incluir mídias, cache ou paths de dados;
- executar os 8 testes específicos e a suíte fonte atual;
- conservar logs/JSON do job real fora do repositório;
- extrair do caso somente fixtures sintéticas e metadados redigidos;
- marcar scripts `resume_nova_*` como ferramentas incidentais, não APIs públicas.

### Áreas afetadas

`src/cinepulse/rife_recovery.py`, `rife_black_repair.py`, `matroska_quality.py`, scripts incidentais, testes e documentação de recuperação.

### Entregas

- baseline testado;
- inventário de arquivos versionáveis versus locais;
- registro das limitações atuais;
- fixture mínima reproduzindo segmentos 16/17/18 e PNG truncado.

### Gate G0

- testes específicos PASS;
- nenhum caminho para mídia pessoal entra em fixture;
- nenhuma evidência do job é apagada;
- `git diff --check`, compile e links documentais passam.

## 7. Etapa 1 — domínio, manifesto e máquina de estados

### Objetivo

Criar uma única fonte de verdade para job, tentativa, fase, unidade, artefato e verificação.

### Trabalho

- criar tipos imutáveis para identidade da fonte, volume, artefato, fase e expectativa;
- definir `RenderJobManifest` schema 1;
- separar `job_id`, `attempt_id`, `phase_id` e `unit_id`;
- modelar transições válidas e rejeitar saltos ilegais;
- criar repositório de manifesto com `.tmp`, flush, fsync de arquivo, backup e `os.replace`;
- registrar RenderPlan fingerprint e contratos de cor/entrega/storage/verificação;
- adicionar migração controlada e rejeição de schema futuro;
- fazer a fila guardar referência ao manifesto, não uma cópia divergente da verdade.

### Código previsto

- novo `src/cinepulse/render_job.py`;
- novo `src/cinepulse/job_store.py`;
- extensão de `state_store.py` e `render_history.py`;
- testes `test_render_job.py`, `test_job_store.py` e migração da fila.

### Entregas

- schema documentado com exemplo;
- validador e serializer determinísticos;
- tabela de transições;
- migração e backup testados.

### Gate G1

- round-trip não altera fingerprint;
- schema futuro é recusado sem escrita;
- arquivo truncado recupera backup ou bloqueia com evidência;
- transição inválida não muda o manifesto;
- concorrência de escritores não corrompe o estado.

## 8. Etapa 2 — worker durável, lease e heartbeat

### Objetivo

Desacoplar a vida do render da janela e impedir duplicidade.

### Trabalho

- extrair execução do `studio.py` para um `RenderWorker` sem dependência Tk;
- definir protocolo local de comandos: start, pause, resume, cancel, status e shutdown;
- criar lease por job com PID, start time, nonce e heartbeat;
- confirmar processo antes de recuperar lease stale;
- manter árvores FFmpeg/IA associadas à tentativa;
- permitir que a UI se desconecte/reconecte ao worker;
- definir comportamento de fechar janela;
- implementar watchdog por progresso interno, não somente por tempo de parede;
- distinguir processo lento, sem progresso, pausado e travado.

### Código previsto

- novo `render_worker.py`, `job_lease.py` e `worker_protocol.py`;
- redução gradual da orquestração em `studio.py`;
- integração com `process_control.py` e `runtime_distribution.py`.

### Entregas

- worker executável local;
- lease/heartbeat testável com relógio injetável;
- reconexão da UI;
- pausa cooperativa e cancelamento explícito.

### Gate G2

- fechar e reabrir UI mantém ou redescobre o job;
- segunda instância não inicia subprocessos;
- crash do owner libera lease somente após regra stale;
- pausa repetida três vezes conserva a mesma contagem final;
- cancelamento mata a árvore e preserva a última unidade confirmada.

## 9. Etapa 3 — checkpoints idempotentes por fase

### Objetivo

Levar o modelo comprovado do RIFE para todas as etapas longas.

### Trabalho por estágio

#### Entrada e preflight

- registrar identidade antes do processamento;
- persistir probe e decisão do RenderPlan;
- invalidar o job quando a fonte mudar, sem apagar artefatos.

#### Real-ESRGAN

- materializar lotes numerados;
- validar contagem, dimensões, decode e modelo;
- promover lote e atualizar checkpoint;
- reconstruir índice do cache a partir de lotes confirmados.

#### RIFE

- usar segmentos numerados contíguos;
- manter geração em diretório temporário;
- validar PNGs e segmento antes do commit;
- persistir contagem real, não percentual estimado.

#### VFX/transições/master

- escolher janelas temporais reprodutíveis;
- registrar seed/parâmetros quando houver aleatoriedade;
- preservar contrato de cor e cadence;
- tornar cada janela reexecutável.

#### Concatenação

- construir manifesto pela contagem exata;
- validar master antes de `master_ready`;
- preservar master parcial rejeitado.

#### Entrega e verificação

- codificar em parcial no volume final;
- registrar progresso em arquivo comum, não URL incompatível;
- reaproveitar parcial órfão somente se fechado e aprovado;
- promover depois do gate correspondente.

### Código previsto

- interface `StageAdapter`;
- adapters para upscale, RIFE, master, delivery e verification;
- integração progressiva com `studio.py`, `storage_engine.py` e `verification.py`.

### Gate G3

Para cada adapter: matar antes, durante e depois do commit deve produzir o mesmo resultado final e nunca contar parcial como concluído.

## 10. Etapa 4 — gates de qualidade e política RIFE

### Objetivo

Impedir que progresso estruturalmente existente, mas visualmente defeituoso, avance.

### Trabalho

- mover validação PNG para módulo genérico;
- selecionar RIFE UHD por resolução e versão;
- manter rota nativa 2× e retime seguro para resíduos;
- criar detector genérico de preto por luminância/variância;
- criar detector de congelamento com tolerância a cena estática;
- validar PTS, duplicações e fronteiras;
- manter o detector de tamanho FFV1 apenas como fast path calibrado;
- gerar amostra visual de fronteiras e pontos de maior risco;
- persistir resultado do gate por segmento/lote;
- invalidar somente dependentes quando modelo/política mudar.

### Código previsto

- `frame_quality.py`, evolução de `matroska_quality.py` e `rife_engine.py`;
- integração no worker normal;
- fixtures sintéticas de preto, freeze, truncamento e movimento.

### Gate G4

- defeitos conhecidos são detectados sem falso PASS;
- cenas estáticas controladas não viram falso freeze;
- 16/17/18 quadros permanecem exatos;
- zero regressão nas matrizes 720p/1080p/4K;
- teste físico 8K confirma a rota na GPU alvo.

## 11. Etapa 5 — armazenamento, staging e fechamento de arquivos grandes

### Objetivo

Tratar volume físico e fase de I/O como parte do contrato de render.

### Trabalho

- resolver serial/ID, tipo de barramento, capacidade e espaço do volume;
- estender StoragePlan para retenção, staging e duplicidade temporária;
- revalidar espaço antes de fases grandes;
- criar monitor de margem durante escrita;
- implementar cópia reiniciável com checksum opcional ou tamanho+probe conforme custo;
- selecionar SSD de staging com consentimento/configuração;
- definir política de `faststart` por destino/tamanho;
- classificar erros de trailer, desconexão e disco cheio;
- manter origem até a entrega aprovada;
- criar plano de cleanup separado do fluxo de sucesso.

### Código previsto

- extensão de `hardware.py`, `storage_engine.py` e `delivery.py`;
- novo `staging.py` e testes de volume simulados.

### Gate G5

- falta de espaço é detectada antes de corromper o estado;
- cópia interrompida retoma e valida;
- remoção do volume gera `recoverable/blocked` e preserva manifesto;
- entrega grande fecha em SSD interno;
- política de faststart não altera qualidade audiovisual.

## 12. Etapa 6 — descoberta e experiência na interface

### Objetivo

Fazer a capacidade técnica aparecer de forma compreensível e segura.

### Trabalho

- scanner limitado a manifests e scratch roots conhecidos;
- classificador `recoverable`, `needs_audit`, `blocked` e `active`;
- restauração do item na fila;
- inspector com fase, unidades, integridade, volumes, espaço e ação;
- progresso da fase separado do global;
- ETA por intervalo e amostra;
- ações de retomar, pausar, migrar, preservar e descartar;
- mensagens claras para encode, verificação e promoção;
- Central de atividade e detalhe técnico;
- acessibilidade, DPI e layout mínimo.

### Código previsto

- novo `recovery_service.py`;
- `ui/recovery_lab.py` e `ui/recovery_view.py`;
- integração com `queue_lab.py`, `queue_view.py` e `feedback_lab.py`.

### Gate G6

- job interrompido reaparece após restart;
- UI nunca oferece retomada enquanto outro owner está ativo;
- usuário não confunde parcial com final;
- ação destrutiva lista impacto e exige confirmação;
- aceite visual Windows em 1024×700 e DPI suportado passa.

## 13. Etapa 7 — fault injection e aceite

### Objetivo

Provar a história completa, inclusive falhas.

### Trabalho

- implementar harness de falhas determinísticas por etapa e ponto de commit;
- cobrir kill de worker/FFmpeg/IA, arquivo truncado, lacuna, disco cheio, volume removido e trailer inválido;
- testar migração, downgrade e concorrência;
- executar source/CPU/media gates;
- executar Windows/NVIDIA com RIFE e NVENC reais;
- executar render longo sintético e um aceite 8K/120 controlado;
- produzir relatório JSON por cenário e resumo humano.

### Gate G7

Todos os P0 da [matriz de testes](RECOVERY_TEST_MATRIX.md) passam no ambiente exigido. Skips de hardware permanecem pendências, não sucesso.

## 14. Etapa 8 — migração e rollout seguro

### Objetivo

Introduzir a nova arquitetura sem colocar jobs existentes em risco.

### Trabalho

- iniciar descoberta em dry-run;
- adicionar feature switch local;
- migrar fila por referência a manifesto com backup;
- classificar jobs antigos por confiança;
- manter recuperador legado acessível durante uma janela definida;
- liberar em anéis: desenvolvimento, opt-in, RC, default e estável;
- definir rollback da feature sem apagar manifests novos;
- atualizar MSI/portátil, SBOM e gates.

### Gate G8

- migração e rollback passam com fixtures de todos os schemas conhecidos;
- job legado permanece preservado;
- instalação/upgrade/repair reais passam;
- nenhum caminho de downgrade muta schema desconhecido.

## 15. Etapa 9 — operação, retenção e melhoria contínua

### Objetivo

Evitar que a robustez degrade depois da entrega.

### Trabalho

- manter runbooks e índice vivos;
- criar política de retenção por categoria;
- gerar bundle redigido de suporte;
- registrar métricas locais por fase;
- revisar falhas reais e adicionar fixtures;
- executar restore/fault drill periódico;
- revisar matriz de GPU/versão do RIFE;
- incluir recuperação no checklist de release.

### Gate G9

- documentação validada automaticamente;
- último drill possui evidência e data;
- owners/review dates estão atuais;
- nenhum incidente recorrente permanece apenas em conhecimento informal.

## 16. Backlog priorizado de implementação

### Primeira fatia — fundação sem UX nova

1. G0 baseline.
2. `RenderJobManifest` e store.
3. máquina de estados e migrations.
4. adapter RIFE usando o recuperador comprovado.
5. testes de kill nas fronteiras.

### Segunda fatia — worker e pipeline normal

1. RenderWorker separado da UI.
2. lease/heartbeat.
3. pausa e reconexão.
4. adapters de upscale/master/delivery.
5. gates genéricos de mídia.

### Terceira fatia — armazenamento e interface

1. identidade física de volume.
2. staging e política de arquivos grandes.
3. scanner de manifests.
4. inspector e ações.
5. ETA por fase.

### Quarta fatia — aceite e rollout

1. fault matrix completa.
2. Windows/NVIDIA.
3. migração/rollback.
4. MSI/portátil.
5. release candidate e documentação final.

## 17. Alternativas rejeitadas

- **Salvar apenas percentual:** não identifica unidade confirmada nem permite verificar integridade.
- **Retomar pelo maior arquivo encontrado:** pode promover parcial sem trailer ou segmento defeituoso.
- **Manter worker dentro da janela:** fechar UI continua sendo falha de processo.
- **Apagar scratch ao iniciar:** destrói a principal evidência recuperável.
- **Usar apenas hash de arquivo inteiro:** é caro demais para checkpoint frequente de centenas de GiB; usar identidade e validação proporcional por artefato.
- **Detectar preto somente por tamanho FFV1:** específico demais para outras resoluções/codecs.
- **Prometer ETA exata:** o limitador muda entre GPU, CPU e I/O.
- **Reescrever todo o `studio.py` de uma vez:** aumenta risco e impede comparar comportamento por fatia.

## 18. Definição de conclusão do programa

O programa só estará concluído quando:

- todos os requisitos P0 estiverem `implementado` e os físicos aplicáveis `aceito`;
- um job interrompido reaparecer e retomar pela interface;
- quedas forçadas em todas as fases preservarem o último commit;
- defeitos de mídia conhecidos bloquearem promoção;
- staging/USB/falta de espaço forem tratados;
- quick verify, count-frames e deep verify forem comunicados corretamente;
- migração e rollback estiverem comprovados;
- documentação, relatórios e runbooks estiverem indexados e validados.
