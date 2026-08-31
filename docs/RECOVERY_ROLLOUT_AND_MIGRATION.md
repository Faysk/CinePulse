# Plano — migração, compatibilidade e rollout da recuperação

**Status:** planejado

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026
**Objetivo:** introduzir a arquitetura reiniciável sem arriscar filas, jobs ou artefatos existentes

## 1. Escopo de migração

Existem quatro fontes legadas:

1. itens da fila schema 2;
2. históricos por job da Phase 7;
3. scratch/chunks da Phase 6 sem manifesto genérico;
4. estado e scripts específicos da recuperação `nova.mp4`.

Nenhuma dessas fontes deve ser apagada pela migração. O novo sistema cria referências e manifests ao lado das evidências existentes.

## 2. Estratégia de compatibilidade

### Fila

Adicionar campos opcionais:

```json
{
  "job_id": "...",
  "manifest": "<relative-or-managed-reference>",
  "recovery_origin": "history|scratch|manual|null"
}
```

Itens antigos continuam carregando. A fila não replica fase/artefatos; consulta o manifesto quando presente.

### Histórico

`job.json`, `plan.json`, `contracts.json` e `verification.json` continuam válidos. O migrador usa esses arquivos como evidência, sem sobrescrevê-los.

### Scratch legado

Primeiro é somente leitura. O classificador atribui:

- `high`: job/history/fingerprint e sequência conferem;
- `medium`: parâmetros reconstruíveis, mas falta uma identidade forte;
- `low`: somente arquivos temporários sem contrato suficiente.

Somente `high` pode oferecer retomada direta. `medium` exige inspeção/confirmar; `low` permanece preservado e bloqueado.

### Recuperador do incidente

Funções genéricas são movidas para módulos de produto. Scripts com paths fixos continuam fora do fluxo normal e recebem aviso de legado. Não são executados automaticamente.

## 3. Migração do schema

Regras:

1. ler e validar origem;
2. criar backup da fila/configuração mutada;
3. produzir manifesto em caminho temporário;
4. validar round-trip e referências;
5. promover manifesto;
6. atualizar fila em operação atômica separada;
7. registrar evento de migração;
8. nunca remover origem.

Se o passo 6 falhar, o manifesto órfão pode ser redescoberto; a fila anterior permanece válida.

## 4. Feature switches locais

Propostos:

- `recovery_manifest_write`: grava manifestos para jobs novos;
- `recovery_worker`: usa worker durável;
- `recovery_discovery`: mostra jobs descobertos;
- `recovery_stage_adapters`: ativa checkpoints por fase;
- `recovery_cleanup_ui`: habilita inventário/limpeza explícita.

São flags locais de rollout, não opções permanentes para o usuário comum. Desligar uma flag nunca apaga manifesto ou converte estado.

## 5. Anéis de liberação

### Anel 0 — testes

- manifests somente em fixtures;
- fault injection completo;
- nenhuma descoberta de dados reais.

### Anel 1 — desenvolvimento opt-in

- manifest para jobs novos;
- UI atual ainda controla execução;
- comparar estado legado versus novo;
- divergência bloqueia promoção do novo caminho.

### Anel 2 — worker opt-in

- worker durável para previews e renders pequenos;
- close/reopen e pause/resume;
- rollback por flag.

### Anel 3 — RC

- descoberta dry-run e depois visível;
- RIFE/Real-ESRGAN reais em Windows/NVIDIA;
- staging e entrega grande;
- MSI/portátil.

### Anel 4 — padrão

- worker e manifesto ativos por padrão;
- caminho legado disponível somente para diagnóstico durante uma versão;
- métricas locais e suporte monitorados.

### Anel 5 — estável

- requisitos P0 aceitos;
- caminho legado removível somente após inventário de dependências;
- documentação e migration matrix fechadas.

## 6. Rollback

Rollback de feature:

- desabilita criação/descoberta nova;
- preserva manifests;
- não tenta converter schema novo para antigo;
- mantém saída e histórico acessíveis;
- impede versão antiga de mutar job desconhecido;
- orienta reabrir na versão compatível.

Rollback de tentativa:

- encerra owner de forma segura;
- restaura fila/config apenas se backup validar;
- não remove artefatos produzidos;
- registra causa e revisão.

## 7. Matriz mínima de compatibilidade

| Origem | Versão nova | Versão antiga após rollback |
|---|---|---|
| fila schema 2 sem manifesto | carrega e pode migrar | continua carregando backup/original |
| job Phase 7 completo | indexa como histórico | continua abrindo relatório |
| scratch Phase 6 recuperável | classifica em read-only | permanece intacto |
| manifest schema 1 | executa se suportado | preserva e informa incompatibilidade |
| schema futuro | recusa sem mutar | recusa sem mutar |
| script `nova` | somente manual/legado | comportamento atual preservado |

## 8. Release gates

Antes de cada anel:

- unit tests e migrations;
- `git diff --check` e compileall;
- source/CPU/media gates;
- fault matrix proporcional ao anel;
- Windows parser e MSI quando aplicável;
- GPU acceptance quando RIFE/NVENC entram no anel;
- links, IDs de requisitos e docs indexadas;
- bundle/SBOM sem mídia ou paths pessoais.

## 9. Critérios de parada do rollout

Parar promoção quando:

- manifesto divergir do estado legado;
- houver duplicidade de worker;
- uma queda perder unidade já confirmada;
- job antigo for mutado sem backup;
- detector de qualidade produzir falso PASS conhecido;
- saída parcial for apresentada como final;
- cleanup atingir arquivo fora do inventário;
- um gate físico necessário estiver skipped.

## 10. Evidência por anel

Cada execução produz:

- versão/commit;
- flags habilitadas;
- schemas testados;
- cenários e ambientes;
- resultados e skips;
- rollback executado;
- artefatos/checksums do teste sintético;
- decisão de promover, repetir ou interromper.

## 11. Conclusão da migração

A migração termina quando:

- todos os jobs novos usam manifesto;
- fila referencia manifests sem duplicar estado;
- legado conhecido foi classificado;
- rollback de feature e schema foi exercitado;
- nenhuma versão suportada apaga job desconhecido;
- scripts específicos não são necessários no fluxo normal;
- um ciclo RC → rollback → RC foi comprovado.
