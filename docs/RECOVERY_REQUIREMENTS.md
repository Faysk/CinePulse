# Requisitos — robustez e recuperação de renders

**Status:** baseline de implementação

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026

**Revisar após:** qualquer alteração no worker, fila, scratch, RIFE, entrega ou verificação
**Escopo:** renders finais e previews materializados; prioridade para pipelines longos com IA

## 1. Como usar este documento

Cada requisito possui um identificador estável. Planos, código, testes e relatórios devem referenciar esses IDs, evitando que uma correção exista somente como comentário ou conhecimento da equipe.

Estados permitidos:

- `aberto`: ainda não implementado;
- `parcial`: existe em uma rota específica ou sem todos os gates;
- `implementado`: código e testes automatizados passaram;
- `aceito`: também passou no ambiente físico exigido;
- `bloqueado`: há impedimento registrado e evidência preservada.

`Implementado` não equivale automaticamente a `aceito`. Um requisito dependente de Windows, NVIDIA, disco USB ou render longo só recebe `aceito` depois do teste correspondente.

## 2. Resultado de produto

Um render é considerado robusto quando:

1. cada fase possui estado durável fora da janela;
2. uma interrupção perde no máximo a unidade ainda não confirmada;
3. o CinePulse redescobre o job sem varrer discos arbitrariamente;
4. a retomada revalida identidades e artefatos antes de escrever;
5. defeitos conhecidos impedem a promoção;
6. a interface distingue processamento, verificação e conclusão;
7. limpeza é explícita, inventariada e posterior ao aceite;
8. falhas físicas não provocam perda silenciosa nem arquivo final falsamente válido.

## 3. Requisitos funcionais e de durabilidade

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-FUN-001 | P0 | parcial | Todo render recebe `job_id`, manifesto versionado e fingerprint do RenderPlan antes da primeira mutação. Hoje o histórico possui job/fingerprint, mas não o manifesto reiniciável completo. |
| RH-FUN-002 | P0 | parcial | Cada fase declara sua unidade de commit; após queda, somente a unidade corrente pode precisar ser refeita. Comprovado na recuperação RIFE, pendente nas demais fases. |
| RH-FUN-003 | P0 | aberto | O worker deve continuar ou pausar com segurança sem depender da vida da janela Tk ou de uma conversa Codex. |
| RH-FUN-004 | P0 | aberto | Fechar a interface durante trabalho ativo oferece: continuar em segundo plano, pausar com segurança ou cancelar. |
| RH-FUN-005 | P0 | parcial | Pausa cooperativa termina na próxima fronteira segura e grava `paused`; a sentinela existe na ferramenta RIFE, mas não no worker genérico. |
| RH-FUN-006 | P0 | parcial | Retomada valida fonte, configurações, cache e sequência antes de qualquer mutação. Implementado para o recuperador RIFE. |
| RH-FUN-007 | P0 | aberto | Jobs interrompidos reaparecem automaticamente na fila ao iniciar a aplicação. |
| RH-FUN-008 | P0 | aberto | Apenas um worker pode possuir a lease de um job; segunda instância deve sair sem iniciar FFmpeg/IA. |
| RH-FUN-009 | P0 | aberto | Lease stale só pode ser tomada depois de confirmar ausência do processo e expirar heartbeat. |
| RH-FUN-010 | P0 | parcial | A saída final só é promovida depois da verificação. `AtomicOutput` já cobre a entrega normal; o contrato deve abranger todas as rotas recuperadas. |
| RH-FUN-011 | P1 | aberto | Retry registra nova tentativa sem apagar histórico da tentativa anterior. |
| RH-FUN-012 | P1 | aberto | Mudança autorizada de scratch/destino entre fases preserva o mesmo job e registra a migração. |
| RH-FUN-013 | P1 | aberto | Cancelamento é distinto de pausa e de descarte; cancelar processo não apaga automaticamente artefatos recuperáveis. |
| RH-FUN-014 | P1 | aberto | Jobs incompatíveis são classificados como `blocked`, com divergência exata e ação segura. |

## 4. Requisitos de qualidade audiovisual

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-QUA-001 | P0 | parcial | Quadros intermediários devem ser estruturalmente íntegros; PNG exige assinatura, parse e término válidos. Implementado na recuperação RIFE. |
| RH-QUA-002 | P0 | parcial | Cada segmento confirma codec, dimensões, pixel format, FPS e número de pacotes antes do commit. Implementado na recuperação RIFE. |
| RH-QUA-003 | P0 | parcial | RIFE 8K seleciona rota UHD segura; paralelismo só é habilitado se a matriz daquela versão/hardware estiver aprovada. |
| RH-QUA-004 | P0 | aberto | O pipeline normal detecta quadros pretos por análise genérica de sinal; o tamanho de pacote específico pode ser apenas uma otimização. |
| RH-QUA-005 | P0 | aberto | O pipeline detecta quadros congelados inesperados e lacunas temporais, distinguindo cenas realmente estáticas. |
| RH-QUA-006 | P0 | parcial | Contagens residuais 16/17/18 mantêm o número exato sem pedir razão insegura ao RIFE. Comprovado no recuperador. |
| RH-QUA-007 | P0 | parcial | A timeline concatenada deriva de contagem exata de quadros/pacotes, sem arredondamento acumulado. Implementado no recuperador. |
| RH-QUA-008 | P0 | aberto | Fronteiras entre segmentos são amostradas para duplicação, salto, preto e descontinuidade de PTS. |
| RH-QUA-009 | P0 | implementado | Verificação final confere dimensões, FPS, CFR, contagem, duração, codecs, streams e sincronismo A/V. |
| RH-QUA-010 | P1 | implementado | Deep verify opcional decodifica até EOF; a interface deve diferenciar claramente quando ele não foi executado. |
| RH-QUA-011 | P1 | aberto | Amostra perceptiva automática gera contatos/frames de fronteira para inspeção humana sem declarar qualidade artística automaticamente. |
| RH-QUA-012 | P1 | aberto | Mudança de versão/modelo da IA invalida somente os artefatos cujo contrato depende dessa versão. |

## 5. Requisitos de armazenamento

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-STO-001 | P0 | aberto | Fonte, scratch, cache, master e saída registram identidade do volume físico além da letra Windows. |
| RH-STO-002 | P0 | parcial | Preflight calcula pico por fase, reserva e crescimento de cache; deve ser estendido para staging e retenção de recuperáveis. |
| RH-STO-003 | P0 | aberto | Espaço livre é rechecado antes de cada fase grande e durante escrita longa com limiar de parada segura. |
| RH-STO-004 | P0 | parcial | Master pode ser staged para SSD interno com cópia reiniciável, validação e origem preservada. Comprovado no job real. |
| RH-STO-005 | P0 | aberto | A aplicação identifica tipo de barramento/volume e alerta sobre fechamento de MP4 grande em USB lento/instável. |
| RH-STO-006 | P0 | parcial | `faststart` é condicionado a destino, tamanho e finalidade; removido no recuperador local grande. |
| RH-STO-007 | P0 | parcial | Escrita usa parcial e promoção atômica no mesmo volume. Já existente para saída e segmentos recuperados. |
| RH-STO-008 | P1 | aberto | Cópia entre volumes grava progresso, tamanho, identidade de origem e validação da cópia. |
| RH-STO-009 | P1 | aberto | Limpeza apresenta inventário de arquivos/bytes por categoria e exige confirmação explícita. |
| RH-STO-010 | P1 | aberto | Cache continua classificado como descartável; sua ausência nunca autoriza apagar fonte ou declarar backup. |
| RH-STO-011 | P1 | aberto | Falha de disco/cabo deixa o job `recoverable` ou `blocked`, nunca `complete`. |

## 6. Requisitos de interface e comunicação

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-UX-001 | P0 | aberto | A fila exibe jobs redescobertos com origem `Recuperado do disco`. |
| RH-UX-002 | P0 | aberto | O inspector mostra fase, última unidade confirmada, integridade, volumes, espaço, erro e próxima ação. |
| RH-UX-003 | P0 | aberto | Percentual da fase e progresso global ponderado são separados. |
| RH-UX-004 | P0 | aberto | `Encode concluído`, `verificando` e `arquivo final aprovado` são estados visualmente distintos. |
| RH-UX-005 | P0 | aberto | Retomar, pausar, migrar SSD, preservar e descartar são ações diferentes; descarte é a única destrutiva. |
| RH-UX-006 | P1 | aberto | ETA é faixa baseada em amostras da fase e inclui confiança/condição, nunca uma promessa única. |
| RH-UX-007 | P1 | aberto | Baixa utilização de GPU é explicada conforme a fase e os possíveis limitadores de I/O/CPU. |
| RH-UX-008 | P1 | aberto | Erro apresenta linguagem simples e detalhe técnico copiável separadamente. |
| RH-UX-009 | P1 | aberto | Recuperação funciona em 1024×700, DPI Windows suportado e navegação por teclado. |
| RH-UX-010 | P1 | aberto | Nenhum modal repetitivo é usado para progresso; modais ficam restritos a decisões destrutivas ou de risco. |

## 7. Observabilidade, privacidade e suporte

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-OBS-001 | P0 | parcial | Cada transição de fase e commit produz evento append-only com timestamp e tentativa. O recuperador registra isso; falta unificação. |
| RH-OBS-002 | P0 | aberto | Heartbeat contém progresso interno monotônico e última atividade, sem depender apenas de uso da GPU. |
| RH-OBS-003 | P0 | aberto | Erros possuem código estável, fase, artefato, comando redigido e indicação `retryable/blocked`. |
| RH-OBS-004 | P1 | parcial | Bundle de suporte redige paths absolutos e não faz upload automático; estender para manifesto/checkpoints. |
| RH-OBS-005 | P1 | aberto | Métricas de tempo, throughput e falhas ficam locais e vinculadas ao job; nenhuma telemetria é adicionada. |
| RH-OBS-006 | P1 | aberto | Relatório final lista o que foi reaproveitado, refeito, rejeitado e promovido. |
| RH-OBS-007 | P1 | aberto | Documentação e schema possuem `owner`, data, revisão e validação automática de links/IDs. |

## 8. Migração e compatibilidade

| ID | Pri. | Estado | Requisito e critério objetivo |
|---|---|---|---|
| RH-MIG-001 | P0 | aberto | O novo manifesto aceita somente schemas conhecidos e rejeita schema futuro sem mutação. |
| RH-MIG-002 | P0 | aberto | Migração cria backup e usa escrita atômica, como o state store atual. |
| RH-MIG-003 | P0 | aberto | Jobs legados são descobertos primeiro em modo somente leitura e classificados por confiança. |
| RH-MIG-004 | P0 | aberto | Scripts específicos de `nova.mp4` não viram API pública; seus aprendizados são migrados para módulos genéricos. |
| RH-MIG-005 | P1 | aberto | Feature rollout permite desligar descoberta/worker novo sem tornar manifestos existentes ilegíveis. |
| RH-MIG-006 | P1 | aberto | Downgrade não executa job com schema desconhecido; preserva e orienta abrir em versão compatível. |
| RH-MIG-007 | P1 | aberto | A fila schema 2 mantém itens existentes e recebe referência ao manifesto, sem duplicar toda a verdade do job. |

## 9. Matriz de responsabilidade por mudança

| Mudança | Documentos/testes obrigatórios para revisão |
|---|---|
| schema ou estado do job | este documento, especificação do manifesto, testes de migração e fault matrix |
| worker/processos | programa, lease/heartbeat, cancelamento e testes de queda |
| RIFE/Real-ESRGAN | requisitos de qualidade, fixtures, GPU acceptance e teste perceptivo |
| scratch/cache/staging | requisitos de armazenamento, preflight e testes de disco |
| fila/UX | especificação de UX, testes de queue lab e aceite Windows |
| verificação/promoção | Phase 7, matriz de testes e relatório de evidência |
| cleanup | runbook, inventário, confirmação destrutiva e restore drill |

## 10. Definição de pronto de um requisito

Um item só muda para `implementado` quando:

- código e documentação concordam;
- existe teste automatizado proporcional ao risco;
- falha deixa evidência legível;
- caminhos de rollback/preservação foram testados;
- nenhuma reivindicação física não executada aparece como aprovada.

Quando o requisito depende de hardware real, `aceito` também exige a evidência definida em [Matriz de testes de recuperação](RECOVERY_TEST_MATRIX.md).
