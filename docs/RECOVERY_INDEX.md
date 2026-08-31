# Recuperação de renders

**Status:** documentação operacional ativa

**Responsável:** mantenedores do CinePulse

**Última revisão:** 31 de agosto de 2026
**Escopo:** renders em chunks interrompidos durante a etapa RIFE

Este índice reúne as evidências, o procedimento operacional e o desenho futuro da recuperação de renders. Ele nasceu do primeiro render real 8K/120 fps recuperado até a entrega final.

## Leitura por objetivo

| Necessidade | Documento |
|---|---|
| Executar o aprimoramento completo em ordem segura | [Programa de robustez e recuperação](RECOVERY_HARDENING_PROGRAM.md) |
| Consultar requisitos, prioridade e estado | [Requisitos rastreáveis](RECOVERY_REQUIREMENTS.md) |
| Implementar schema, checkpoints, lease e estados | [Manifesto e máquina de estados](RECOVERY_MANIFEST_AND_STATE_MACHINE.md) |
| Implementar a experiência e operação na interface | [Interface e operação da recuperação](RECOVERY_UI_AND_OPERATIONS.md) |
| Provar quedas, corrupção, armazenamento e hardware | [Matriz de testes e falhas](RECOVERY_TEST_MATRIX.md) |
| Migrar filas/jobs e liberar sem risco | [Migração e rollout](RECOVERY_ROLLOUT_AND_MIGRATION.md) |
| Entender tudo o que aconteceu no caso `nova.mp4` | [Pós-mortem do incidente de 26–30/08/2026](INCIDENT_2026-08-26_RIFE_8K120.md) |
| Retomar com segurança outro job compatível | [Runbook de recuperação RIFE](RIFE_RECOVERY_RUNBOOK.md) |
| Entender a visão original da recuperação genérica | [Desenho de render reiniciável](RESUMABLE_RENDERING_DESIGN.md) |
| Conferir o contrato geral de verificação | [Verification & Render History](CORE_INTEGRITY_PHASE7_VERIFICATION_HISTORY.md) |
| Entender armazenamento e chunks do pipeline normal | [Storage Engine](CORE_INTEGRITY_PHASE6_STORAGE_ENGINE.md) |

## Estado real da capacidade

- **Comprovado:** o job `20260826-203826-da124c70` foi retomado por segmento, teve 990 segmentos defeituosos reparados, completou 43.533 quadros e gerou uma saída 8K/120 fps aprovada.
- **Implementado como ferramenta técnica:** validação, reparo de quadros pretos, retomada RIFE, concatenação com timeline exata, reutilização segura de master/parcial e promoção atômica.
- **Ainda não entregue:** descoberta automática e botão de retomada genérico na interface. Fechar e reabrir a interface ainda pode mostrar a fila vazia mesmo quando scratch, cache e histórico recuperáveis existem.
- **Específico do incidente:** os scripts `resume_nova_recovery.ps1`, `stage_nova_master_on_d.ps1` e `wait_nova_final_encode.ps1` contêm caminhos e números daquele job. Eles são evidência reproduzível, não uma interface genérica.

## Ordem recomendada para implementação

1. baseline e preservação do recuperador comprovado;
2. manifesto/máquina de estados;
3. worker durável, lease e heartbeat;
4. checkpoints idempotentes por fase;
5. gates de qualidade e armazenamento;
6. descoberta e interface;
7. fault injection e aceite físico;
8. migração/rollout;
9. operação e melhoria contínua.

Os gates, módulos previstos e critérios de avanço estão no [programa de robustez](RECOVERY_HARDENING_PROGRAM.md). Não pular diretamente para a interface: sem o contrato durável e os gates, um botão “Retomar” apenas automatizaria decisões inseguras.

## Regras que nunca devem ser quebradas

1. Não iniciar um segundo recuperador para o mesmo job.
2. Não apagar segmentos, cache, master ou parcial antes da validação e do aceite do resultado.
3. Não considerar um segmento pronto apenas porque um processo retornou código zero.
4. Não promover uma saída sem conferir resolução, FPS, contagem de quadros, codecs, áudio e sincronismo.
5. Não usar um volume externo lento para o fechamento de um MP4 grande quando houver SSD interno com espaço verificado.
6. Não anunciar “recuperação genérica pela interface” enquanto os critérios de aceite do desenho futuro permanecerem abertos.

## Evidências do caso concluído

As fontes locais autoritativas, deliberadamente não publicadas no repositório, são:

- checkpoint: `<scratch>/job_<token>/recovery-state.json`;
- resultado: `<data>/logs/renders/<job_id>/recovery-result.json`;
- log append-only: `<data>/logs/renders/<job_id>/recovery.log`;
- estado do job: `<data>/logs/renders/<job_id>/job.json`;
- saída aprovada: `<output>/nova_otimizado.mp4`.

Os caminhos exatos permanecem na máquina em que o caso ocorreu. Um bundle público de suporte deve redigi-los conforme a política de histórico técnico.
