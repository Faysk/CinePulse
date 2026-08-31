# Recovery & Reliability Mega Pack — Phase 0: RIFE Safety

**Status:** implementation candidate
**Baseline:** `04a3ae829412177e78249523b0f57ed4f300fbcd`
**Gate:** G0 + immediate RIFE safety hotfix

## Objetivo

Eliminar do pipeline normal a invocação RIFE que reproduziu o defeito observado no incidente 8K/120, sem aguardar a arquitetura completa de recuperação genérica.

## Mudanças

- `rife_engine.build_command()` deixa de expor diretamente `rife-ncnn-vulkan` e passa a chamar `cinepulse.rife_safe_runner`;
- o runner valida assinatura PNG, dimensões IHDR e `IEND` antes de aceitar entrada ou saída;
- a interpolação neural sempre gera primeiro a contagem nativa `2×`;
- 8K/UHD usa `-u` e `-j 1:1:1` no caminho GPU;
- resoluções menores mantêm o paralelismo GPU `2:2:2` já usado pelo produto;
- CPU mantém política conservadora `1:2:2`;
- alvos residuais (por exemplo 17/18) são obtidos por retime uniforme somente depois de validar a sequência nativa;
- o wrapper devolve exatamente o número de PNGs solicitado ao chamador existente, evitando a tolerância histórica `desired - 1` na prática sem reescrever `studio.py` nesta fase.

## Limites deliberados

- esta fase não implementa manifesto genérico, lease, heartbeat ou discovery;
- segmentos FFV1 do pipeline normal ainda serão transacionalizados na Phase 3, quando `StageAdapter` e unidades de commit existirem;
- o detector universal de preto/freeze permanece Phase 4; o gate específico do incidente continua no recuperador legado;
- progresso interno do runner seguro ainda é observado principalmente por logs enquanto a geração nativa ocorre; progresso por unidade durável entra com o worker/adapters.

## Critérios de aceite

1. unit tests existentes continuam verdes;
2. testes novos provam política 8K/UHD serial e 2× nativo;
3. PNG sem `IEND` é recusado;
4. dimensões inconsistentes são recusadas;
5. `build_command()` de CPU/GPU sempre passa pelo runner seguro;
6. source/CPU/media gates atuais permanecem verdes;
7. um teste físico Windows/NVIDIA 8K continua obrigatório antes de marcar RH-QUA-003 como `aceito`.

## Decisão

Depois desta phase, o pipeline normal deixa de chamar diretamente a combinação insegura que originou os quadros pretos do incidente. A arquitetura de recuperação genérica continua sendo implementada nas phases seguintes, sem confundir este hotfix com conclusão do programa.
