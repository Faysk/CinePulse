# Relatório — Core Integrity MegaPack Phase 4

**Data:** 2026-08-13
**Base:** Core Integrity Phase 3
**Escopo:** CP-007 e color management do caminho ativo do Studio.

## Implementado

- novo `src/cinepulse/color_pipeline.py`;
- RenderPlan atualizado para `core-integrity-phase4-color-pipeline`;
- HDR limpo preservado como HDR/10-bit;
- HDR com VFX/transição convertido explicitamente para SDR BT.709;
- `zscale` + linearização + `tonemap=mobius` + gamut/range conversion;
- `error_diffusion` na redução de profundidade;
- SDR 10-bit preservado em intermediários color-critical;
- FFV1/Matroska para masters/intermediários de fontes HDR/>8-bit;
- VFX passa a aceitar saída `yuv420p10le` e metadados de trabalho;
- Real-ESRGAN/RIFE atuais tratados como fronteiras SDR 8-bit;
- saída após fronteira neural permanece SDR 8-bit, sem falsa promoção Main10;
- range full/limited propagado em caminho limpo;
- classificação HDR deixa de usar BT.2020 sozinho;
- preflight/Qualidade deixam de usar warnings do antigo pipeline globalmente SDR e passam a refletir o RenderPlan.

## Resultado dos achados

| Código | Phase 4 |
|---|---|
| CP-007 | corrigido no caminho ativo do Studio; preservação ou conversão ficam explícitas |
| CI-P4-HDR-SDR | aviso informativo novo quando HDR precisa virar SDR |
| CI-P4-AI-8BIT | aviso novo quando Real-ESRGAN/RIFE exigem redução 10→8 |
| CI-P4-COLOR-UNKNOWN | aviso novo quando metadados SDR estão incompletos |

## Validação automatizada

Suíte `test*.py`:

**115/115 PASS**

Novos testes cobrem:

- HDR limpo 10-bit;
- HDR + VFX tone-map;
- SDR10 + RIFE com boundary 8-bit explícita;
- SDR10 limpo preservado;
- full range;
- `zscale`/tonemap/dither no filter chain;
- FFV1 para intermediário color-critical;
- final SDR8 sem falsa promoção Main10;
- VFX graph 10-bit;
- BT.2020 SDR sem falso HDR;
- RenderPlan sem CP-007 pendente.

## Integrações reais

### HDR limpo

Fonte sintética HDR10:

- 320×180/24;
- `yuv420p10le`;
- BT.2020;
- PQ (`smpte2084`);
- `bt2020nc`;
- range limited.

Saída original limpa:

```text
HDR10 • bt2020/smpte2084 • 10-bit
```

**PASS**

### HDR passando por master musical

O mesmo HDR10 foi processado em modo musical, obrigando a criação do master de estúdio.

Saída:

```text
HDR10 • bt2020/smpte2084 • 10-bit
```

**PASS**

Isso cobre diretamente a regressão CP-007 do antigo master H.264/yuv420p 8-bit.

### HDR + VFX

O mesmo HDR10 foi renderizado com `Pulso cinematográfico`.

Saída:

```text
SDR • bt709/bt709 • 10-bit
```

**PASS**

A saída não foi marcada como HDR. O caminho executou tone mapping antes da composição.

### SDR10 através de master

Fonte SDR BT.709 10-bit em modo musical:

```text
SDR • bt709/bt709 • 10-bit
```

**PASS**

### Full range

Fonte SDR10 `color_range=pc` em caminho limpo:

```text
range=pc
```

**PASS**

### Regressões do worker

- integration smoke básico: PASS;
- áudio/loudness: PASS;
- VFX: PASS;
- áudio dominante esperado preservado.

## Limites

Não foi reivindicada validação perceptiva de HDR em monitor de referência. Os testes desta fase comprovam contrato técnico, metadata, bit depth, filtros reais e execução end-to-end sintética. Luminância percebida, highlight roll-off e qualidade de tone mapping em mídia real continuam no checklist de aceite.

CP-008/009/015 e matriz de codecs/contêiner/áudio permanecem para a Phase 5.
