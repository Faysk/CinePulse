# Core Integrity Phase 3 — VFX target-aware e envelope musical único

## Objetivo

Fechar a dependência arquitetural dos VFX em `320×180/60` (CP-003) e garantir que preview renderizado e render final usem a mesma normalização musical (CP-013), sem alterar ainda o color pipeline 8-bit/HDR reservado para a Phase 4.

## 1. Canvas VFX deixa de ser fixo

O render final não instancia mais `StudioFrameGenerator` obrigatoriamente em 320×180/60. O gerador agora recebe `width`, `height` e `fps` e toda a geometria dos efeitos é expressa em função do canvas solicitado.

Política atual, centralizada em `vfx_policy.py`:

- até 4K: VFX no tamanho nativo da base;
- até 120 fps: VFX na cadência nativa da base;
- acima de 4K: canvas adaptativo com orçamento de pixels equivalente a 3840×2160, mantendo aspecto e composição final Lanczos;
- acima de 120 fps: base preserva sua cadência, enquanto a reatividade VFX é amostrada em 120 fps.

Isto remove o defeito específico do canvas final fixo 320×180/60 sem fingir que 8K/240/480 já foi validado perceptivamente. Para 8K, o portão visual a 100% continua pendente antes do 1.0 estável.

## 2. Gerador de efeitos resolution-independent

`StudioFrameGenerator` passou a escalar:

- espessuras;
- amplitudes;
- raios;
- partículas;
- suavização de bordas;
- posição e velocidade espacial;
- máscaras/vinheta;

com base nas dimensões efetivas. O tempo do efeito usa `frame_number / fps` do próprio gerador, não mais `frame_number / 60`.

Isso mantém a identidade visual dos efeitos ao variar 720p, 1080p, 4K e cadências até 120 fps.

## 3. Preview visual usa o mesmo gerador dimensionável

Miniaturas e preview imediato continuam deliberadamente leves/demonstrativos, mas o overlay não precisa mais nascer em 320×180 para depois receber nearest-neighbor. O preview pede diretamente seu canvas ao mesmo gerador usado pelo render.

O preview imediato continua sendo uma demonstração sintética de reatividade. A correção CP-013 refere-se ao **preview renderizado**, que executa o pipeline real.

## 4. Envelope musical único de faixa completa

Novo módulo: `music_envelope.py`.

A análise base:

1. decodifica a faixa reativa completa em mono/48 kHz;
2. calcula graves, médios, agudos, RMS e ataques;
3. normaliza percentis usando a faixa completa;
4. armazena o envelope base em cache determinístico;
5. aplica foco/smoothing/expression e dinâmica de seções sobre a análise completa;
6. somente depois recorta/reamostra a janela solicitada.

Portanto um preview de 10 segundos e o render final não calculam percentis diferentes para os mesmos primeiros 10 segundos.

## 5. Cache

Chave do envelope inclui:

- caminho resolvido;
- tamanho;
- `mtime_ns`;
- duração analisada;
- FPS de análise;
- versão do analisador.

Há cache em RAM durante a sessão e cache `.npz` em:

`data/cache/music-envelope/`

Cache corrompido é descartado e reconstruído; falha ao gravar cache não bloqueia render.

## 6. Cadência de análise

A análise base ocorre a 120 fps. A janela é reamostrada por tempo para a cadência VFX planejada.

Consequências:

- 60 fps recebe amostras do mesmo envelope completo;
- 120 fps possui resposta realmente nativa de 120 amostras/s;
- preview 60 e final 120 permanecem temporalmente correlacionados porque vêm da mesma fonte normalizada.

## 7. RenderPlan

Arquitetura atual:

`core-integrity-phase3-vfx-envelope`

Quando VFX estão ativos, `internal_spec` passa a declarar a dimensão/FPS escolhida por `vfx_policy`.

Exemplos:

- 1920×1080/60 → internal 1920×1080/60;
- 3840×2160/120 → internal 3840×2160/120;
- 7680×4320/120 → internal 3840×2160/120 + warning `CI-P3-VFX-8K`.

`CP-003` deixa de aparecer como risco do plano porque o canvas fixo foi removido. `CP-013` entra nos códigos resolvidos pela arquitetura de envelope compartilhado.

## 8. Limites deliberados

Esta fase não corrige:

- CP-007 — intermediários 8-bit/HDR/SDR;
- compressões intermediárias H.264;
- pipeline GPU/shader para VFX;
- 8K nativo em NumPy por padrão;
- 240/480 fps nativos de VFX;
- chunking de Real-ESRGAN/RIFE;
- Storage Engine/preflight de pico;
- codecs/contêineres.

Esses limites permanecem visíveis para evitar trocar um número fixo por promessas não testadas.

## 9. Critérios de aceite desta Phase

- [x] render final deixa de depender de 320×180/60;
- [x] 1080p/60 gera VFX 1080p/60;
- [x] 4K/120 planeja VFX 4K/120;
- [x] 8K/120 usa política adaptativa explícita, não 320×180;
- [x] base 120 fps continua 120 fps;
- [x] gerador usa FPS configurado para tempo/animação;
- [x] preview renderizado analisa a faixa completa antes de recortar;
- [x] final usa a mesma chave/cache de envelope;
- [x] normalização e seções são calculadas antes do slice;
- [x] cache RAM/SSD possui invalidação por arquivo/versão;
- [x] testes automatizados e smoke FFmpeg real.

## 10. Portão que continua aberto para 1.0

A auditoria exige inspeção perceptiva a 100% em 4K/8K. A correção arquitetural CP-003 está implementada, mas o aceite final de **qualidade 8K real na máquina-alvo** continua pendente e não é substituído por testes sintéticos deste pacote.
