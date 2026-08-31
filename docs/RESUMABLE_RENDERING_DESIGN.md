# Desenho — render reiniciável e recuperação pela interface

**Status:** proposta baseada em incidente real; ainda não entregue na interface

**Última revisão:** 31 de agosto de 2026
**Objetivo:** permitir que qualquer job compatível seja descoberto, explicado, pausado e retomado sem operação manual

> Este documento preserva a visão de produto. O plano executável, os requisitos, o schema e os testes foram detalhados posteriormente no [Programa de robustez e recuperação](RECOVERY_HARDENING_PROGRAM.md) e estão reunidos no [índice de recuperação](RECOVERY_INDEX.md).

## 1. Problema

O pipeline já preserva histórico, cache e chunks, mas esses elementos não formam ainda uma experiência única de recuperação. Depois de uma queda, a interface pode mostrar fila vazia embora exista um job recuperável. O usuário não sabe se perdeu tudo, quanto foi concluído, qual fase estava ativa, se há corrupção ou qual disco limita o processo.

O caso 8K/120 demonstrou que “continuar do último arquivo” também não é suficiente: segmentos existentes podem estar estruturalmente legíveis e visualmente defeituosos, o master pode acumular erro de timeline e uma saída completa pode não ter contêiner fechado.

## 2. Resultado esperado para o usuário

Ao iniciar, o CinePulse deve mostrar um card não modal:

> Render interrompido encontrado — 93,99% da interpolação preservada. Fonte e cache disponíveis. Auditoria de integridade necessária antes de retomar.

Ações:

- **Inspecionar**;
- **Retomar com segurança**;
- **Pausar**;
- **Escolher outro SSD para a etapa final**;
- **Preservar sem retomar**;
- **Descartar**, somente com confirmação e inventário exato do que será removido.

## 3. Fonte de verdade

Cada job precisa de um manifesto durável e versionado, separado do estado efêmero da janela:

```text
job_id
schema/version
source identity
settings + RenderPlan fingerprint
cache identities
scratch roots e volume identities
fase atual
unidades planejadas/concluídas
artefatos e estado de validação
process owner/heartbeat
tentativas e último erro
expectativa de entrega
resultado de verificação
```

A letra do volume não deve ser a única identidade. O manifesto deve combinar volume ID/serial e caminho relativo, mantendo o caminho absoluto apenas como pista local.

## 4. Máquina de estados

```text
queued
  -> preflight
  -> running:upscale
  -> running:interpolation
  -> auditing
  -> repairing
  -> master_building
  -> master_ready
  -> final_encoding
  -> verifying
  -> complete

qualquer fase mutável
  -> pause_requested -> paused
  -> interrupted -> recoverable | blocked
  -> error -> recoverable | blocked
```

`complete` exige saída promovida e verificação aprovada. `recoverable` exige contrato reconstruível. `blocked` preserva dados e explica exatamente a divergência.

## 5. Unidade de commit por estágio

| Estágio | Unidade confirmada | Validação antes do commit |
|---|---|---|
| Real-ESRGAN | lote/cache segmentado | quantidade, dimensões, decode e identidade |
| RIFE | segmento | PNG íntegro, pacotes, codec, dimensões, FPS e gate visual |
| VFX/master | segmento ou janela temporal | timeline, duração, cor e streams |
| concatenação | master | quadros, FPS, duração, codec e timeline exata |
| entrega | parcial fechado | contrato completo e contêiner legível |
| promoção | arquivo final | verificação aprovada e escrita atômica |

O percentual exibido deve ser derivado dessas unidades e da fase, nunca apenas do tamanho de um arquivo parcial.

## 6. Descoberta ao iniciar

1. Ler jobs persistidos com estado diferente de `complete/cancelled`.
2. Procurar scratch roots configurados sem varrer discos inteiros.
3. Correlacionar `job_id`, fingerprint, fonte, cache e chunk root.
4. Detectar processo/heartbeat ainda ativo antes de oferecer retomada.
5. Fazer inspeção somente leitura e barata.
6. Classificar como `recoverable`, `needs_audit` ou `blocked`.
7. Restaurar um item na fila com origem “Recuperado do disco”.

O scanner não deve apagar temporários órfãos durante a descoberta.

## 7. UX do inspector de recuperação

O inspector deve mostrar, em linguagem direta:

- fase atual e o que essa fase faz;
- progresso dentro da fase e progresso global ponderado;
- última unidade confirmada;
- fonte/cache presentes ou ausentes;
- integridade auditada e quantidade de defeitos;
- espaço necessário por volume;
- volume interno/USB e risco de gargalo;
- tempo observado por unidade e ETA como faixa, não promessa;
- próximo passo exato;
- caminhos técnicos apenas na área avançada.

Durante a verificação, diferenciar:

- codificação terminada, arquivo ainda parcial;
- quick verify de contrato/metadados;
- contagem real de quadros;
- deep verify até EOF;
- promoção final.

## 8. Política de armazenamento

- scratch, cache, master e entrega possuem papéis separados;
- cache é descartável e nunca fonte de verdade;
- artefatos confirmados recebem identidade/hash ou tamanho+mtime+probe conforme custo;
- saída grande deve receber preflight do volume físico;
- master pode ser staged para SSD interno com cópia reiniciável;
- o sistema não remove o original ao concluir o staging;
- cleanup só ocorre após aceite e inventário explícito.

## 9. Política RIFE de qualidade

Para 8K, a rota segura deve ser selecionada automaticamente:

- modo UHD;
- paralelismo conservador quando a implementação demonstrar truncamento;
- interpolação em razão nativa suportada;
- retime temporal validado para contagens residuais;
- validação estrutural dos quadros intermediários;
- amostragem visual/estatística genérica, sem depender somente de um tamanho de pacote específico;
- gate final antes da concatenação.

O detector determinístico do incidente pode continuar como otimização, mas não como único detector genérico.

## 10. Concorrência e fechamento da aplicação

- cada job recebe lock/lease com PID, início e heartbeat;
- lease stale pode ser recuperado somente depois de confirmar que a árvore de processos terminou;
- fechar a janela durante um render deve oferecer “continuar em segundo plano”, “pausar com segurança” ou “cancelar”;
- um worker durável não pode depender da vida da conversa Codex;
- o launcher não deve criar worker duplicado;
- sentinelas e checkpoints devem sobreviver à reinicialização.

## 11. Critérios de aceite

### Recuperação funcional

- queda forçada em cada estágio retorna ao último commit confirmado;
- nenhuma retomada reprocessa unidades válidas sem motivo registrado;
- lacunas/corrupção bloqueiam a mutação e apontam o artefato exato;
- duas instâncias não processam o mesmo job;
- pausar e reiniciar pelo menos três vezes produz a mesma contagem final.

### Qualidade

- fixture 8K sintética com padrão conhecido não produz quadros pretos;
- PNG truncado com retorno zero é rejeitado;
- segmentos 16/17/18 mantêm a contagem exata;
- concatenação de milhares de segmentos mantém duração e quadros;
- saída final passa quick verify, count-frames e deep verify configurável;
- comparação perceptiva amostrada não mostra lacunas temporais nas fronteiras.

### Armazenamento

- desligamento durante escrita deixa somente parcial não promovido;
- staging interrompido retoma sem apagar origem;
- USB lento gera aviso e alternativa de SSD interno;
- falta de espaço é detectada antes da fase que o exige;
- cleanup lista bytes/arquivos e exige confirmação explícita.

### Interface

- job interrompido reaparece ao abrir a aplicação;
- progresso informa a fase atual;
- `codificação concluída` não é confundida com `verificação concluída`;
- erros mostram ação segura e preservação existente;
- caminhos técnicos ficam disponíveis sem dominar a experiência comum.

## 12. Plano de implementação

1. Extrair o manifesto/checkpoint genérico do recuperador específico.
2. Integrar locks, heartbeat e pausa cooperativa ao worker principal.
3. Incorporar os gates de PNG/preto/timeline ao caminho RIFE normal.
4. Criar scanner limitado aos scratch roots conhecidos.
5. Restaurar jobs encontrados no state store da fila.
6. Criar inspector e ações de recuperação.
7. Adicionar staging de master e seleção de volume por fase.
8. Executar testes de queda em cada estágio e um novo render físico 8K/120.
9. Somente depois marcar “retomada pela interface” como concluída no roadmap.

## 13. Não objetivos imediatos

- retomar qualquer arquivo temporário arbitrário sem manifesto;
- reconstruir configurações por adivinhação;
- esconder falhas de qualidade para maximizar percentual reaproveitado;
- limpar automaticamente centenas de gigabytes após o primeiro sucesso;
- prometer ETA exata em pipelines limitados alternadamente por GPU, CPU e disco.
