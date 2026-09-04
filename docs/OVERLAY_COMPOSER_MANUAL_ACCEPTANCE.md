# Overlay Composer Preview — Manual Acceptance Workflow

Este documento transforma os gates físicos/perceptuais do Overlay Composer em uma sessão reproduzível com evidências locais.

> Escopo: **Preview**. Automated green e este harness não promovem a feature para Stable por conta própria.

## 1. Preparar a branch

No Windows usado para o teste:

```powershell
git switch preview-overlay-composer-clean
git pull
```

Confirme que o working tree está limpo antes de começar:

```powershell
git status --short
git rev-parse HEAD
```

O PR de referência é o **#3 — Overlay Composer Preview**.

## 2. Criar uma sessão de acceptance

Na raiz do CinePulse:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-OverlayAcceptance.ps1 -OpenFolder
```

O helper cria automaticamente:

```text
artifacts/overlay-acceptance/YYYYMMDD-HHMMSS/
├── environment.json
└── ACCEPTANCE.md
```

`environment.json` registra, quando disponível:

- branch e commit testados;
- working tree dirty/clean;
- Windows/build;
- PowerShell;
- Python;
- FFmpeg/FFprobe;
- CPU;
- RAM;
- adaptadores de vídeo e resolução atual;
- valores de DPI disponíveis no registro do Windows;
- NVIDIA/driver/VRAM/temperatura via `nvidia-smi`;
- discos e espaço livre.

`ACCEPTANCE.md` é o checklist da sessão. Marque nele PASS/FAIL/PARTIAL e anote findings com severidade S1–S4.

A pasta `artifacts/` já é ignorada pelo Git e pode guardar screenshots, outputs pequenos, logs e relatórios sem sujar o repositório.

## 3. Ordem recomendada do teste físico

### Gate A — regressão zero sem Overlay

Antes de testar a feature:

1. abra um projeto conhecido;
2. deixe a cena Overlay vazia;
3. faça um render curto;
4. confirme vídeo, áudio, duração e comportamento normal do CinePulse.

Se o caminho sem Overlay regredir, classifique como **S1** e pare a promoção.

### Gate B — interação básica

Monte a composição alvo desta feature:

```text
PNG ou GIF do personagem
+
waveform / barras / spectrum
```

Valide:

- drag X/Y;
- resize pelo handle;
- opacidade;
- z-order;
- lock;
- undo/redo;
- clipping fora do canvas;
- agrupamento;
- mover grupo;
- escalar grupo;
- handle de grupo em área vazia do bounding box;
- presets rápidos.

### Gate C — música real

Use uma faixa que você conhece bem e compare:

- waveform;
- bars;
- spectrum;
- sensibilidade baixa/média/alta;
- espessura;
- quantidade de barras;
- mirror;
- cores principal/secundária.

O julgamento aqui é perceptual: o gráfico deve parecer ligado à música, sem flicker desagradável ou resposta errática.

Também confirme que a trilha final não foi alterada por existir uma entrada separada usada apenas pelo visualizer.

### Gate D — persistência

Execute pelo menos:

1. salvar preset;
2. restaurar preset;
3. adicionar à fila;
4. reabrir item da fila;
5. fechar/reabrir CinePulse;
6. confirmar posições, tamanhos, estilos e agrupamento.

Depois mova temporariamente um PNG/GIF usado pela cena e confirme que o render bloqueia com erro claro de asset ausente em vez de simplesmente omitir a layer.

### Gate E — DPI

Teste no mínimo:

- Windows 100%;
- Windows 125% **ou** 150%.

Em ambos:

- ponteiro deve coincidir com a seleção no canvas;
- handle deve coincidir com a borda visível;
- resize do grupo deve continuar correto;
- painel de propriedades deve continuar utilizável;
- não deve existir overflow grave do layout.

## 4. Matriz de render

Mínimo recomendado para considerar o Preview fisicamente aceito:

| Teste | Resolução | FPS | Conteúdo |
|---|---:|---:|---|
| Baseline | 1920×1080 | 30/60 | sem Overlay |
| Composição 1 | 1920×1080 | 60 | PNG + waveform |
| Composição 2 | 1920×1080 | 60 | GIF + bars |
| Composição 3 | 3840×2160 | 60 | PNG/GIF + spectrum/bars |
| Extreme smoke | 7680×4320 | alvo viável | composição representativa |

8K é smoke/acceptance de extremo; não é necessário transformar todo teste manual em 8K.

Para cada output registre no `ACCEPTANCE.md`:

- resolução;
- FPS;
- encoder;
- duração;
- PASS/FAIL;
- observação visual;
- nome do arquivo de evidência.

## 5. Monitorar soak real

Abra **um segundo PowerShell** enquanto o CinePulse estiver renderizando.

Exemplo de 30 minutos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-OverlayAcceptance.ps1 `
  -SessionRoot .\artifacts\overlay-acceptance\SOAK-30M `
  -MonitorMinutes 30 `
  -SampleSeconds 15
```

Exemplo de 2 horas com output e scratch conhecidos:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Invoke-OverlayAcceptance.ps1 `
  -SessionRoot .\artifacts\overlay-acceptance\SOAK-2H `
  -MonitorMinutes 120 `
  -SampleSeconds 30 `
  -OutputPath 'D:\renders\lofi-final.mp4' `
  -ScratchPath 'D:\CinePulseScratch'
```

Se você souber o PID exato do processo de render, pode restringir a coleta:

```powershell
... -ProcessId 12345
```

Sem `-ProcessId`, o helper soma processos locais chamados `cinepulse`, `python` e `pythonw` como aproximação de uso do app.

Durante o monitor são gravados:

```text
soak-samples.csv
soak-summary.json
```

As amostras podem incluir:

- RAM livre;
- working set/private memory do app;
- CPU acumulada do processo;
- utilização GPU;
- VRAM usada/total;
- temperatura da GPU;
- tamanho do output;
- tamanho do scratch, quando informado;
- espaço livre do volume alvo.

### Observação sobre ScratchPath

Calcular tamanho recursivo de um diretório muito grande tem custo. Use `-ScratchPath` somente quando ele apontar para o scratch específico da sessão/projeto, não para uma unidade inteira.

## 6. Critérios para interromper o soak

Pare e registre como S1/S2 se observar:

- crash;
- output corrompido;
- áudio ausente/incorreto;
- crescimento de scratch compatível com expansão massiva de frames de Overlay;
- RAM/VRAM crescendo continuamente sem estabilização aparente;
- temperatura fora do que é normal/seguro para a máquina;
- queda crítica de espaço livre;
- desalinhamento severo do Overlay no output.

O script **não decide automaticamente temperatura segura**, porque isso depende do hardware e configuração física. Ele registra o valor; a avaliação continua humana.

## 7. Evidências recomendadas

Dentro da pasta da sessão, guarde quando possível:

```text
screenshots/
  dpi-100.png
  dpi-150.png
  editor-group.png
  final-1080p.png
  final-4k.png
logs/
outputs-notes.md
```

Não é necessário versionar mídia pesada no GitHub.

## 8. Resultado da sessão

No topo de `ACCEPTANCE.md`, marque exatamente um:

- `PASS — suitable for continued Preview rollout`;
- `FAIL — blocker found`;
- `PARTIAL — more evidence required`.

No final, escolha uma recomendação:

- `Keep Draft / fix blockers`;
- `Preview candidate — manual acceptance adequate`;
- `Stable discussion allowed — all required physical gates passed`.

## 9. Promoção

A ordem continua sendo:

```text
Automated CI
→ Manual Windows/DPI
→ Real music/perceptual review
→ 1080p/4K renders
→ long soak
→ extreme smoke when viable
→ only then Stable discussion
```

Não faça merge do PR #3 apenas porque o checklist foi gerado. O conteúdo precisa ser efetivamente executado e preenchido.
