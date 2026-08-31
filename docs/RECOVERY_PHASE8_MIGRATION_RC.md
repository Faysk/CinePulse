# Recovery & Reliability Mega Pack — Phase 8: Migration & RC Rollout

**Status:** implementation candidate; rollout capped at shadow/dry-run until physical gates pass
**Base:** Phase 7 (`a6662f441816737a63f4c9ef6562346fac47a2a5`)
**Gate alvo:** G8

## Entrega

### Feature rings

`recovery_rollout.py` implementa os anéis normativos:

- Ring 0 — recovery nova desligada;
- Ring 1 — manifesto shadow para jobs novos;
- Ring 2 — worker/adapters opt-in, discovery desligada;
- Ring 3 — discovery **dry-run**;
- Ring 4 — candidato a RC depois dos gates físicos;
- Ring 5 — cleanup UI somente após aceite estável.

Flags podem vir de `recovery-flags.json` ou override local por ambiente. Rollback volta ao Ring 1: desliga execução/discovery nova e preserva manifests/artefatos.

### Migração legada

`recovery_migration.py` classifica histórico antigo:

- `high`: job + plan fingerprint + contracts coerentes;
- `medium`: evidência parcial, exige opt-in explícito;
- `low`: contrato insuficiente, somente preservação.

Migração high-confidence cria `manifest.json` **ao lado** do legado; não apaga ou reescreve `job.json`, `plan.json` ou `contracts.json`. Job que estava `running` sem owner conhecido migra para `interrupted`, nunca para `complete`.

Fila pode receber referência ao manifesto sem duplicar fase/artefatos. Itens não relacionados permanecem byte-semantically intactos no modelo de migração.

### Bootstrap

`app.py` executa `run_recovery_bootstrap()` antes do Studio:

- Ring 1: nada além do shadow manifest já existente;
- Ring 3+: discovery somente leitura em `<logs>/renders`;
- snapshot local `recovery-discovery.json`;
- falha do bootstrap gera log e **não impede o CinePulse legado de abrir**;
- nenhuma descoberta é injetada silenciosamente na fila legacy nesta etapa.

Isso evita ativar UI/worker novos antes de fechar Windows/NVIDIA/storage físico.

## Testes

- progressão conservadora de rings;
- override local de flag;
- rollback preserva manifesto;
- high-confidence dry-run não escreve;
- high-confidence real cria manifesto `interrupted` preservando legado;
- medium/low permanecem read-only por padrão;
- queue reference não modifica item não relacionado;
- Ring 1 não faz discovery;
- Ring 3 gera snapshot sem mutar manifesto.

## Decisão de rollout

A branch/PR pode avançar como **Preview / Recovery Reliability opt-in** quando os workflows automatizados estiverem verdes.

Não promover para `1.0.0` estável enquanto estiver pendente qualquer um de:

- self-hosted Windows/NVIDIA RIFE 8K UHD;
- close/reopen UI com worker externo;
- storage físico SSD/USB controlado;
- soak longo;
- aceite visual/DPI;
- integração visível da recovery view no launcher novo.

## Gate G8

Migração, flags, rollback e bootstrap dry-run estão implementados. A promoção de Ring 3 para Ring 4/5 permanece bloqueada por evidência física, não por falta de código de rollout.
