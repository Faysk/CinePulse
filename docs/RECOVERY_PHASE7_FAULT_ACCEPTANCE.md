# Recovery & Reliability Mega Pack — Phase 7: Fault Injection & Acceptance

**Status:** automated gate implementation complete; physical acceptance pending execution
**Base:** Phase 6 (`d860a1f50b87ac6d8fe6f4254e6e76de8f569382`)
**Gate alvo:** G7

## Entrega

### Recovery fault gate

Novo `scripts/recovery_fault_gate.py` produz evidência JSON e roda explicitamente os testes de:

- RIFE safety;
- manifesto/CAS/backup;
- lease/heartbeat/PID reuse;
- protocolo do worker;
- pause/resume/cancel;
- commit protocol/fault points;
- quality gates;
- storage/staging;
- recovery discovery/UX model.

### Workflow de PR

Novo workflow `Recovery Reliability` roda:

- source/fault gate em Ubuntu;
- source/fault gate em Windows;
- media commit integration em Linux com FFmpeg real.

A integração de mídia cria FFV1 sintético, injeta crash **depois da promoção e antes do checkpoint**, reinicia o adapter e exige reconciliação sem uma segunda execução do producer.

### GPU acceptance físico

O workflow self-hosted existente `GPU Acceptance` ganha `recovery_gpu_acceptance.py`:

1. exige RIFE/modelo reais no runner;
2. gera fixture 8K autorizada/sintética;
3. executa a rota segura GPU;
4. exige política UHD `-u`, jobs `1:1:1` e geração nativa 2×;
5. pede alvo residual para também exercitar o retime seguro;
6. valida a sequência PNG final.

Esse teste **não é executado em runner GitHub genérico** e não pode ser marcado como PASS até o workflow self-hosted ser disparado e ficar verde.

## Regra de evidência

- cenário não executado = pendente;
- skip em requisito físico obrigatório != sucesso;
- artefatos JSON de CI ficam vinculados ao commit;
- mídia de teste é sintética;
- nenhum volume pessoal deve ser removido para teste.

## Ainda pendente fisicamente

- Windows/NVIDIA 8K real no self-hosted;
- soak longo;
- SSD/USB descartável com indisponibilidade controlada;
- DPI/layout visual Windows;
- fechamento/reabertura da UI com o launcher novo habilitado.

Esses pontos são bloqueadores para declarar **recuperação genérica estável**, mas não bloqueiam continuar para a Phase 8 de rollout/migração, porque a própria Phase 8 mantém tudo atrás de flags até os gates físicos existirem.
