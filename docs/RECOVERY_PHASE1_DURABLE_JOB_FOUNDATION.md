# Recovery & Reliability Mega Pack — Phase 1: Durable Job Foundation

**Status:** implementation candidate
**Base:** Phase 0 (`7b3d3d30ce44efe49afcf902a23b7255992b15a7`)
**Gate alvo:** G1

## Entrega

Esta phase introduz a fonte de verdade durável descrita em `RECOVERY_MANIFEST_AND_STATE_MACHINE.md` sem remover a compatibilidade rc.6.

### Domínio

- novo `RenderJobManifest` schema `cinepulse.render-job/1`;
- `job_id` estável e `revision` monotônica;
- máquina de estados explícita e transições ilegais recusadas;
- RenderPlan fingerprint, expectativa de entrega, progresso de fase e erro estruturado;
- schema futuro é recusado sem mutação.

### Store

- novo `JobStore` com compare-and-swap por `revision`;
- temporário exclusivo, flush/fsync do arquivo, `os.replace` e fsync de diretório onde suportado;
- `.bak` preserva a revisão anterior;
- manifesto truncado pode ser recuperado do backup, preservando o primário corrompido como evidência;
- manifesto + backup inválidos bloqueiam em vez de criar estado fictício;
- lock intra-processo evita escritores concorrentes dentro do mesmo runtime; ownership cross-processo permanece responsabilidade da Phase 2.

### Integração compatível

`RenderHistory` continua gravando `job.json`, `plan.json`, `contracts.json` e `verification.json`, mas passa a manter `manifest.json` em shadow mode:

1. `start()` cria manifesto e entra em `preflight`;
2. RenderPlan com fingerprint promove para `running`;
3. contratos persistem a expectativa técnica;
4. verificação entra em `verifying`;
5. sucesso aprovado chega a `complete`;
6. erro registra código estruturado e chega a `blocked`;
7. cancelamento chega a `cancelled` quando a transição é válida.

Falha de shadow manifest é registrada em `render.log` e não destrói o caminho legado. Isso mantém rollback real durante o rollout.

## Testes

- round-trip determinístico;
- schema futuro recusado;
- transição inválida sem incremento de revisão;
- lifecycle até `complete`;
- progresso inválido bloqueado;
- CAS rejeita writer stale;
- recuperação de primário truncado via `.bak`;
- primary + backup inválidos bloqueiam;
- histórico cria manifesto, grava fingerprint/expectation e fecha estado;
- bundle de suporte redige paths também no manifesto.

## Limites deliberados

- cross-process lease/heartbeat entra na Phase 2;
- fila ainda não usa manifesto como referência primária;
- stage checkpoints idempotentes entram na Phase 3;
- discovery/UX entra na Phase 6;
- o shadow mode só deixa de ser opcional após rollout/migration da Phase 8.

## Gate G1

Considerado implementado em código quando source tests e migration/state tests passam. Aceite físico não é exigido para este gate puramente transacional, mas concorrência cross-processo só será considerada resolvida depois do G2.
