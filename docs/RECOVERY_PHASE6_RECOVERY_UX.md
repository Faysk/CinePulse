# Recovery & Reliability Mega Pack — Phase 6: Recovery UX

**Status:** implementation candidate
**Base:** Phase 5 (`5e854a7e3e328d0199fc0a264e4c8a95b0f5f573`)
**Gate alvo:** G6

## Entrega

A recuperação passa a ter um modelo de descoberta e apresentação independente da memória da UI.

### RecoveryService

- varre somente o root de histórico conhecido e apenas `*/manifest.json`;
- nunca varre discos arbitrários;
- ignora jobs `complete`/`discarded`;
- lê manifesto e lease em modo somente leitura durante discovery;
- classifica `active`, `needs_audit`, `recoverable` e `blocked`;
- owner ativo nunca recebe ação `Retomar`;
- fonte ausente bloqueia e oferece reconexão sem mutar manifesto;
- stale/estado interrompido vira `needs_audit`, não resume cegamente;
- gera payload compatível para injeção futura na fila e snapshot local de diagnóstico.

### UI model

`ui/recovery_lab.py` separa:

- badge de estado;
- fase atual;
- unidades confirmadas e percentual **da fase**;
- motivo;
- origem `Recuperado do disco`;
- ações seguras permitidas pelo classificador.

`ui/recovery_view.py` materializa os cards sem embutir regra de negócio. O botão chama `on_action(job_id, action)`; discovery e execução continuam no service/worker.

### Regras de comunicação

- `94% da fase` nunca vira `Arquivo aprovado`;
- ativo: `Acompanhar`/`Pausar`, sem retomar;
- recuperável: `Inspecionar`/`Retomar com segurança`;
- precisa auditoria: `Conferir integridade` antes de retomar;
- bloqueado: causa + próxima ação;
- nenhum discovery executa cleanup.

## Testes

- job pausado reaparece como recuperável;
- lease viva aparece como ativo e não oferece resume;
- fonte ausente aparece como blocked sem alterar manifest;
- job completo não reaparece;
- card diferencia progresso de fase de conclusão.

## Integração

A view/service já são consumíveis pelo launcher novo. A UI legacy não é reescrita nesta phase; a injeção automática no startup/fila fica protegida pelo feature switch `recovery_discovery` e entra na Phase 8, quando rollback e migração já existirem. Isso segue o rollout normativo: discovery real começa em dry-run e só depois fica visível.

## Gate G6

Modelo, classificador, ações e view estão implementados. O aceite visual Windows 1024×700/DPI e a ativação automática no startup pertencem ao anel RC/Phase 8 e ao aceite físico da Phase 7.
