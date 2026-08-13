# Core Integrity MegaPack — Phase 4: Color Pipeline

Data: 2026-08-13
Base: Core Integrity Phase 3 acumulada sobre UX MegaPack Phase 8
Escopo principal: CP-007 — profundidade de bits, HDR/SDR, gamut, transfer, range e intermediários color-critical.

## Objetivo

A Phase 4 elimina o comportamento em que uma fonte HDR/10-bit podia atravessar masters/transições/VFX 8-bit e terminar novamente dentro de uma saída `p010le` rotulada como 10-bit/HDR.

A nova regra é:

> Metadados nunca substituem transformação de cor. Se HDR for preservado, a informação permanece HDR/10-bit no caminho ativo. Se um estágio ainda for SDR-only, a conversão HDR→SDR acontece explicitamente antes dele e a saída deixa de ser rotulada como HDR.

## Novo módulo `color_pipeline.py`

O módulo define um contrato puro para cada render:

- `preserve_hdr`: caminho limpo preserva primárias, transferência, matriz, range e >=10-bit;
- `tone_map_sdr`: HDR entra em estágio SDR-only e é convertido uma única vez para BT.709;
- `preserve_sdr`: SDR preserva profundidade e range quando o caminho suporta;
- redução 10→8 é explícita quando Real-ESRGAN/RIFE atuais impõem uma fronteira neural 8-bit.

O plano expõe:

- perfil da fonte;
- perfil de trabalho;
- perfil final;
- intenção de cor;
- pixel format de trabalho/final;
- se HDR foi preservado ou tone-mapped;
- estágios SDR-only responsáveis pela decisão;
- suposições por metadados incompletos.

## HDR limpo

Para HDR10/HLG sem estágios SDR-only:

- `yuv420p10le` é mantido;
- primárias/transfer/matriz/range são preservados;
- masters color-critical usam FFV1 em Matroska;
- final HEVC usa Main10/p010le ou `yuv420p10le` em CPU;
- não há `setparams` fingindo conversão para BT.709.

Exemplo conceitual:

```text
HDR10 BT.2020/PQ 10-bit
→ master FFV1 10-bit HDR
→ final HEVC Main10 HDR
```

## HDR com VFX ou transição

VFX NumPy e o caminho de transição ainda não são considerados HDR-aware.

A política conservadora é:

```text
HDR
→ zscale (linearização)
→ float RGB
→ tonemap Mobius
→ gamut BT.2020 → BT.709
→ range limitado
→ error-diffusion dithering
→ SDR BT.709 10-bit
→ VFX/transição
→ final SDR 10-bit
```

Assim o arquivo final não recebe metadados HDR depois de a faixa dinâmica ter sido convertida.

## HDR/SDR 10-bit com Real-ESRGAN ou RIFE

Os caminhos neurais atuais são tratados como fronteiras SDR 8-bit até haver validação explícita de processamento high-bit-depth/HDR.

Por isso:

- HDR é tone-mapped antes do modelo;
- SDR 10-bit é reduzido explicitamente para 8-bit com `zscale` + `error_diffusion`;
- o resultado final permanece SDR 8-bit;
- o RenderPlan mostra `CI-P4-AI-8BIT` quando essa redução acontece;
- o CinePulse não volta a colocar o resultado num contêiner 10-bit para sugerir precisão que já não existe.

Isso é deliberadamente conservador e será revisitado somente quando os modelos/pipelines forem comprovados em high-bit-depth.

## Intermediários

Quando a fonte é HDR ou >8-bit, masters e intermediários pós-composição passam a usar:

```text
Matroska + FFV1 level 3
```

na profundidade de trabalho planejada.

Para SDR 8-bit comum, o CinePulse mantém H.264 de alta qualidade para não explodir uso de scratch antes da Phase 6 (Storage Engine).

## Range full/limited

O caminho limpo preserva `pc/full` versus `tv/limited`.

Quando HDR é tone-mapped para SDR, a política atual padroniza a saída em BT.709 limited de forma explícita. Isso evita apenas trocar metadata sem converter níveis.

## Detecção HDR

BT.2020 sozinho não é mais suficiente para classificar uma fonte como HDR. A detecção explícita usa transferência PQ (`smpte2084`) ou HLG (`arib-std-b67`). BT.2020 + BT.709 pode ser wide-gamut SDR e não é tone-mapped automaticamente.

## VFX 10-bit

O filter graph de VFX recebe pixel format e metadados de trabalho do ColorPipeline.

Em SDR 10-bit/tone-mapped 10-bit:

- base entra como `yuv420p10le`;
- composição termina como `yuv420p10le`;
- intermediário color-critical usa FFV1;
- metadados BT.709/range são preservados.

A layer gerada em RGBA continua 8-bit; isso não reduz a base inteira para 8-bit. A migração do próprio gerador para float/high-bit-depth/shader permanece uma evolução posterior.

## RenderPlan

Versão da arquitetura:

```text
core-integrity-phase4-color-pipeline
```

CP-007 passa para `resolved_audit_codes`.

Novos avisos informativos:

- `CI-P4-HDR-SDR`: HDR será tone-mapped porque existe estágio SDR-only;
- `CI-P4-AI-8BIT`: estágio neural requer redução explícita para 8-bit;
- `CI-P4-COLOR-UNKNOWN`: metadados SDR incompletos exigem suposição BT.709 nos campos ausentes.

Nenhum desses avisos é usado para fingir que HDR permanece HDR depois de processamento SDR.

## Limites deliberados

Esta Phase não resolve:

- container/codec matrix (Phase 5);
- perfis de áudio master (Phase 5);
- chunking/Storage Engine (Phase 6);
- validação perceptiva HDR em monitor de referência;
- mastering metadata HDR10 (MaxCLL/MaxFALL/master-display) completa;
- Dolby Vision;
- VFX/shaders HDR nativos;
- RIFE/Real-ESRGAN high-bit-depth comprovados;
- fluxo clássico de `aurora.py`/`loop_engine.py` (CP-033).

## Critérios de aceite fechados nesta Phase

- [x] master HDR/10-bit não colapsa para H.264/yuv420p 8-bit;
- [x] SDR 10-bit atravessa master mantendo 10-bit;
- [x] HDR limpo mantém BT.2020/PQ/10-bit no arquivo final;
- [x] HDR + VFX vira SDR BT.709 por tone mapping real, sem falsa flag HDR;
- [x] VFX conseguem manter base SDR 10-bit;
- [x] full range é preservado em caminho SDR limpo;
- [x] redução 10→8 antes de estágio neural usa dithering explícito;
- [x] SDR 8-bit final não é automaticamente promovido a Main10;
- [x] BT.2020 SDR não é confundido com HDR apenas pelas primárias;
- [x] RenderPlan descreve a mesma intenção executada pelo worker.

## Portões ainda manuais para 1.0

- inspeção em monitor HDR real;
- padrões HDR/gradientes 10-bit de referência;
- luminância/tone-map perceptivo em cenas reais;
- validação Windows/NVENC Main10 na máquina-alvo;
- render longo e 8K/120 reais.
