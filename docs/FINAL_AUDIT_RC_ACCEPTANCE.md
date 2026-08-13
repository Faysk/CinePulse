# CinePulse — Final Audit & Release Candidate Acceptance

**Base revisada:** UX MegaPack Phase 1–8 + Core Integrity Phase 1–9
**Auditoria-base:** `AUDITORIA_COMPLETA_2026-08-13.md`
**Versão do código:** `1.0.0-rc.5` / `1.0.0rc5`
**Objetivo desta passagem:** reconciliar CP-001…CP-033 com o código acumulado, executar os gates disponíveis, registrar pendências reais e preparar o aceite em Windows/NVIDIA sem promover prematuramente para `1.0 estável`.

## Veredito

### Release Candidate

**CONDIÇÃO: APROVADO EM CÓDIGO / ACEITE DE DISTRIBUIÇÃO PENDENTE.**

Não foi encontrado nenhum P0 original ainda aberto no caminho ativo do Studio. O pacote está apto a seguir para o gate de Release Candidate em Windows real. Isso **não** significa que MSI, GPU, 8K/120 ou HDR perceptivo tenham sido aprovados neste ambiente Linux.

### 1.0 estável

**NÃO APROVADO AINDA.**

Antes de promover para estável faltam, no mínimo:

1. executar o aceite Windows completo, incluindo MSI install/repair/uninstall;
2. executar o gate NVIDIA real para RIFE, Real-ESRGAN e Demucs;
3. render musical longo com mídia real;
4. render 8K/120 na máquina-alvo;
5. inspeção perceptiva de HDR/tone mapping e VFX em conteúdo real;
6. decidir/fechar CP-011;
7. configurar uma política de assinatura de release real (CP-019);
8. fechar o lock transitivo das dependências neurais distribuídas (CP-020).

CP-027, CP-032 e CP-033 continuam como dívida conhecida; não são P0, mas devem permanecer visíveis no roadmap.

## Achados novos desta auditoria final

### FA-001 — execução direta do pytest não conhecia `src/`

O pacote Phase 9 passava pelo `ci_gate.py`, porque o gate injeta `PYTHONPATH`. Porém `python -m pytest` a partir de uma extração limpa falhava na coleta com `ModuleNotFoundError: cinepulse`.

**Correção:** `pyproject.toml` agora declara `pythonpath = ["src"]` na configuração do pytest.

**Resultado:** `python -m pytest -q` passa diretamente com **187 testes** nesta passagem final.

### FA-002 — “GPU automática” ainda era uma promessa ampla demais

A auditoria original CP-016 estava correta: VFX NumPy, análise musical e diversos filtros permanecem CPU mesmo quando componentes neurais/encoder usam GPU.

**Correção:** a UI passa a usar **Aceleração automática** e explica que a GPU é priorizada somente nas etapas compatíveis. O texto do `RenderPlan` agora inclui o dispositivo declarado por etapa.

**Resultado:** CP-016 sai da lista de pendências arquiteturais.

### FA-003 — divergência documental sobre pendências

O relatório da Phase 9 citava apenas CP-019/020/032/033 como abertos, enquanto o `RenderPlan` ainda carregava CP-011/016/019/020/027/032/033.

**Correção:** esta auditoria final reconcilia a matriz. CP-016 foi corrigido nesta passagem; permanecem explicitamente CP-011/019/020/027/032/033.

### FA-004 — modularização ainda é dívida real

`studio.py` possui **6.149 linhas** e `loop_engine.py` **1.067 linhas**. O Studio ainda importa utilitários de `loop_engine.py`, enquanto o aplicativo clássico permanece no mesmo módulo.

Isso confirma que CP-032 e CP-033 **não devem ser marcados como resolvidos** somente porque novos módulos técnicos foram extraídos.

## Matriz final CP-001…CP-033

| Código | Estado final | Evidência / decisão |
|---|---|---|
| CP-001 | ✅ Resolvido | master target-aware; matriz 8K/120 → 1080p/120 coberta por testes |
| CP-002 | ✅ Resolvido | fonte que já atende FPS não é reduzida e reinterpolada |
| CP-003 | ✅ Resolvido em arquitetura | VFX target-aware; 8K usa política adaptativa explícita; inspeção 100% permanece manual |
| CP-004 | ✅ Resolvido | Real-ESRGAN é target-aware e SKIP em downscale/no-upscale |
| CP-005 | ✅ Resolvido em arquitetura | Storage Engine deriva etapas do RenderPlan; calibração em render gigante continua gate de campo |
| CP-006 | ✅ Resolvido | Preservar, Lanczos e IA geram políticas distintas |
| CP-007 | ✅ Resolvido em arquitetura | 10-bit/HDR explícito, tone-map real, dithering e limites neurais honestos |
| CP-008 | ✅ Resolvido | matriz MP4/MOV/MKV/WebM com codecs válidos |
| CP-009 | ✅ Resolvido para perfil estável | >8K e >120 fps são bloqueados até validação específica |
| CP-010 | 🟡 Código resolvido | MSI/portátil separados; lifecycle Windows real ainda precisa ficar verde |
| CP-011 | 🟠 Aberto P1 | SDR8 ainda pode atravessar mais de um intermediário H.264 CRF/CQ antes da saída final |
| CP-012 | ✅ Resolvido | RIFE em chunks com liberação dos PNGs |
| CP-013 | ✅ Resolvido | preview/final compartilham envelope musical completo normalizado |
| CP-014 | ✅ Resolvido | quick verify + deep verify, frame count, CFR, streams, codecs e EOF |
| CP-015 | ✅ Resolvido | AAC/PCM24/FLAC/Opus por perfil de entrega |
| CP-016 | ✅ Resolvido nesta passagem | “Aceleração automática” + dispositivo por etapa no RenderPlan |
| CP-017 | 🟡 Código resolvido | descoberta única de PowerShell; execução real Windows pendente |
| CP-018 | 🟡 Código resolvido | runtime gerenciado obrigatório; Windows limpo sem Python/FFmpeg externo ainda é gate |
| CP-019 | 🟠 Parcial | suporte de assinatura pronto; canal atual sem manifesto publicado/chave de produção |
| CP-020 | 🟠 Parcial | NumPy está hash-locked e existe SBOM; stack neural transitiva ainda não está completamente locked por wheel/hash |
| CP-021 | ✅ Resolvido | quota + LRU + proteção de item ativo |
| CP-022 | ✅ Resolvido | scratch configurável na interface |
| CP-023 | ✅ Resolvido | histórico persistente por `job_id` |
| CP-024 | ✅ Resolvido | tokens de tema e contraste centralizados; dark/light testados |
| CP-025 | 🟡 Substancialmente resolvido | tema, geometria e última aba persistem; últimas pastas ainda não são persistidas |
| CP-026 | ✅ Resolvido | RenderPlan e armazenamento são apresentados por etapas |
| CP-027 | 🟠 Aberto P2 | timeline demonstrativa existe, mas o preview renderizado ainda não oferece seleção explícita início/meio/pico/refrão/emenda/aleatório |
| CP-028 | 🟡 Substancialmente resolvido | reordenar, retry, limpar concluídos, abrir saída/relatório/histórico e carregar no editor existem; duplicar não existe; pausa não é anunciada sem checkpoints |
| CP-029 | ✅ Resolvido | schemas versionados, backup, migração e rejeição de schema futuro |
| CP-030 | 🟡 Código resolvido | mutex/PID lock implementado; named mutex Win32 precisa de evidência no gate Windows |
| CP-031 | 🟡 Código resolvido | `.ico`, WiX e atalhos implementados; shell Windows real precisa de inspeção |
| CP-032 | 🟠 Aberto P2 | `studio.py` ainda possui 6.149 linhas e concentra orquestração/estado/UI |
| CP-033 | 🟠 Aberto P2 | fluxo clássico permanece em `loop_engine.py` e ainda fornece utilitários ao Studio |

## P0 original

**10 de 10 achados P0 possuem correção arquitetural/código no pacote acumulado.**

Alguns deles ainda têm aceite físico pendente — especialmente HDR e distribuição — mas não foi identificado um P0 original sem uma política corretiva implementada.

## P1/P2 que impedem promoção imediata para estável

### CP-011 — gerações intermediárias com perdas

Em SDR 8-bit, `_intermediate_encoder()` ainda pode escolher H.264 de alta qualidade. Master → transição → VFX → final pode, portanto, envolver múltiplas gerações com perdas.

Isso é uma dívida de qualidade real. Para `1.0 estável`, há duas opções aceitáveis:

- migrar intermediários ativos para FFV1/um mezzanine visualmente lossless e recalibrar o Storage Engine; ou
- comprovar por VMAF/SSIM + inspeção 100% que a política atual fica abaixo do limiar de degradação definido e documentá-la como compromisso deliberado.

A primeira opção é preferível para o objetivo de qualidade do CinePulse.

### CP-019 — assinatura real

A infraestrutura existe, mas `installer/update-channel.json` ainda não aponta para um manifesto publicado e não há evidência de chave pública/assinatura de produção nesta cópia.

### CP-020 — reprodutibilidade neural

`requirements.lock` fixa NumPy com hash. PyTorch, torchaudio, Demucs, SoundFile e respectivas dependências transitivas continuam fora de um lock completo por wheel/hash/plataforma.

## Evidência automatizada executada nesta passagem

Ambiente disponível: Linux/Xvfb, Python 3.13 e FFmpeg local.

- `python -m pytest -q`: **187 PASS**;
- `PYTHONPATH=src:. python -m unittest discover -s tests`: **187 PASS**;
- `scripts/release_gate.py`: PASS;
- `compileall src tests scripts`: PASS;
- `scripts/final_audit.py`: PASS;
- source/CPU/media gates da Phase 9 permanecem os gates canônicos;
- smoke básico, áudio, cancelamento, delivery matrix, storage, deep verification, chunks neurais, VFX, HDR e SDR10 já possuem integração automatizada.

> Observação: a execução agregada de `release-light` pode ultrapassar limites de tempo de alguns ambientes de automação; os perfis `cpu` e `media` são independentes justamente para permitir paralelização. Isso não altera os resultados individuais dos testes.

## Aceite Windows/NVIDIA

Foi adicionado `scripts/Invoke-RcAcceptance.ps1` para executar, numa máquina Windows adequada:

```powershell
pwsh -File .\scripts\Invoke-RcAcceptance.ps1 -Version 1.0.0-rc.5
```

Para incluir GPU real:

```powershell
pwsh -File .\scripts\Invoke-RcAcceptance.ps1 -Version 1.0.0-rc.5 -RunGpu
```

Para também instalar, reparar e desinstalar o MSI na máquina/runner de teste:

```powershell
pwsh -File .\scripts\Invoke-RcAcceptance.ps1 -Version 1.0.0-rc.5 -RunGpu -RunMsiLifecycle
```

`-RunMsiLifecycle` é deliberadamente explícito porque modifica a instalação local. O ideal é executá-lo em VM/runner descartável.

## Decisão de release

### Pode virar um novo RC?

**Sim, após o gate Windows ficar verde.** O código acumulado está em condição de Release Candidate e não possui P0 original conhecido aberto no caminho principal.

### Pode virar `1.0.0` agora?

**Não.** O pacote ainda precisa da evidência externa definida acima e do fechamento/decisão consciente sobre CP-011, CP-019 e CP-020.

### Dívidas que podem sobreviver ao primeiro RC

- CP-027 — seleção temporal avançada do preview;
- CP-032 — modularização do `studio.py`;
- CP-033 — isolamento/aposentadoria do fluxo clássico;
- partes restantes de CP-025/028.

Elas devem permanecer rastreadas e não podem ser silenciosamente tratadas como concluídas.
