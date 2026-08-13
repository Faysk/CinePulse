# Relatório — Core Integrity MegaPack Phase 3

**Base:** Core Integrity Phase 2 acumulada sobre UX MegaPack Phase 8
**Escopo:** CP-003 + CP-013, com preservação explícita dos limites de CP-007

## Implementado

- novo `vfx_policy.py` com canvas/cadência determinísticos e target-aware;
- `StudioFrameGenerator` aceita dimensão e FPS reais;
- geometria dos oito VFX escala com o canvas;
- tempo de animação usa FPS do próprio layer;
- VFX até 4K e 120 fps são planejados nativamente;
- saídas acima de 4K usam canvas adaptativo 4K explícito em vez de 320×180;
- base nunca é retimada para acompanhar o layer;
- novo `music_envelope.py` analisa a faixa completa a 120 fps;
- percentis/estrutura musical são calculados sobre a faixa completa antes do recorte;
- preview renderizado e final compartilham envelope/cache;
- cache RAM + SSD determinístico, invalidado por arquivo/duração/versão;
- preview visual imediato pede seu tamanho diretamente ao gerador, sem depender de resize nearest do antigo 320×180;
- `RenderPlan` atualizado para `core-integrity-phase3-vfx-envelope`.

## Auditoria

| Código | Phase 3 |
|---|---|
| CP-003 | corrigido arquiteturalmente: removido canvas final fixo 320×180/60 |
| CP-013 | corrigido: preview renderizado/final usam normalização da faixa completa |
| CP-007 | pendente para Phase 4 |
| Gate 8K visual 100% | pendente de aceite perceptivo em hardware-alvo |

## Validação automatizada

- suíte `test*.py`: **103/103 PASS**;
- `compileall`: PASS;
- release gate: PASS;
- `git diff --check`: PASS.

Novos testes cobrem:

- VFX 1080p/60 target-aware;
- VFX 4K/120 nativo;
- VFX 8K/120 com canvas adaptativo 4K e warning explícito;
- gerador em 640×360/120;
- filter graph sem retime da base;
- escala Lanczos somente quando canvas interno é menor;
- preview slice e final slice com valores idênticos nos mesmos timestamps;
- reamostragem 120 fps;
- estrutura musical respeitando FPS de análise;
- normalização de faixa completa;
- cache SSD sem nova decodificação.

## Smoke FFmpeg real

Entrada base sintética:

- 640×360;
- 120 fps;
- 1 segundo.

Áudio reativo:

- WAV 48 kHz;
- 3 segundos completos;
- preview VFX de 1 segundo analisando a duração completa de 3 segundos.

Saída VFX:

```text
width=640
height=360
r_frame_rate=120/1
nb_frames=120
```

Log:

```text
VFX Phase 3: layer 640×360 • 120 fps; base 640×360/120 fps.
Envelope musical: analisando faixa completa a 120 fps (3.00s).
```

Isso comprova no smoke que o layer não está limitado a 320×180/60 e que a base de 120 fps permanece com 120 frames.

### Smoke do worker: preview → final

No mesmo processo/Tk, foi executado um preview renderizado de 1 s e depois o render final de 2,4 s usando a mesma música.

Log do preview:

```text
Envelope musical: analisando faixa completa a 120 fps (2.40s).
```

Log do final:

```text
Envelope musical: cache RAM <fingerprint>.
```

Os dois arquivos foram criados com sucesso. Isso valida o caminho real do worker: o preview curto não recalcula a normalização em 1 s e o final reutiliza a análise completa.

## Limites mantidos

- VFX continuam CPU/NumPy; shaders/GPU ficam para evolução posterior;
- >4K usa canvas adaptativo 4K por segurança operacional;
- >120 fps usa reatividade de 120 fps;
- intermediário VFX continua yuv420p 8-bit nesta Phase;
- CP-007 será tratado separadamente para evitar misturar color management com geometria/reatividade.

## Próxima fronteira

Phase 4: Color Pipeline — 10-bit/HDR/SDR explícito, tone mapping/gamut/range reais e remoção de falsa preservação HDR.
