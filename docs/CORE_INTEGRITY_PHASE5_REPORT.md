# Core Integrity MegaPack — Phase 5

## Objetivo

Fechar CP-008, CP-009 e CP-015 da auditoria de 13/08/2026 sem adicionar novos modelos de IA. A fase transforma formato de entrega em decisão explícita e falha cedo quando a combinação não é suportada.

## Implementação

### Delivery Matrix

Novo módulo `src/cinepulse/delivery.py`:

| Perfil / extensão | Vídeo | Áudio | Intenção |
|---|---|---|---|
| MP4 / YouTube-Streaming | HEVC | AAC 384 kb/s / 48 kHz | compatibilidade e distribuição |
| MOV / Master de arquivo | ProRes 422 HQ | PCM 24-bit | master/mezzanine |
| MKV / Arquivo eficiente | HEVC | FLAC | arquivo de alta qualidade com áudio lossless |
| WebM / Web | VP9 | Opus | entrega web legal no contêiner |

O perfil `Automático pelo arquivo` deriva a intenção da extensão; perfis explícitos exigem a extensão correspondente e bloqueiam divergências no preflight.

### Capability gate

`detect_ffmpeg_encoders()` consulta o binário FFmpeg realmente usado pelo CinePulse. Se `libvpx-vp9`, `prores_ks`, `libx265/hevc_nvenc`, AAC, FLAC, PCM ou `libopus` necessários não existirem, o trabalho é bloqueado antes do render.

### Limites estáveis

Nesta fase a matriz estável é deliberadamente conservadora:

- até 7680×4320 (8K);
- até 120 fps;
- 60 < FPS <= 120 recebe aviso HFR;
- 10K/12K e 144/240/480 ficam visíveis na UI, mas são bloqueados antes do processamento até existir validação específica.

### Áudio

O worker não força mais AAC estéreo para todo destino. Streaming usa AAC/48 kHz; PCM e FLAC não recebem `-ac 2` nem `-ar 48000`, preservando canais e sample rate quando o contêiner/codec permite. WebM usa Opus.

### RenderPlan / UI / worker

`RenderPlan` passa para `core-integrity-phase5-delivery-matrix` e inclui `Codec e contêiner` como etapa real. A aba Qualidade e saída mostra o contrato resolvido, a fila preserva o perfil e o diálogo de saída aceita MP4, MOV, MKV e WebM.

### Verificação

A verificação final continua checando geometria/FPS/duração e agora também confirma codec de vídeo e codec de áudio quando a saída possui áudio. Verificação profunda de decode/A-V sync continua reservada para a Phase 7.

## Validação executada

- `compileall`: PASS;
- 130/130 testes unitários: PASS;
- `scripts/release_gate.py`: PASS;
- smoke Studio básico MP4: PASS;
- preflight bloqueia perfil/extensão divergente: PASS;
- preflight bloqueia 12K/240 antes do worker: PASS;
- matriz real end-to-end:
  - MP4 → `hevc` + `aac`: PASS;
  - MOV → `prores` + `pcm_s24le`: PASS;
  - MKV → `hevc` + `flac`: PASS;
  - WebM → `vp9` + `opus`: PASS.

## Estado da auditoria

- CP-008: fechado no Studio ativo;
- CP-009: fechado para o perfil estável por capability gate + bloqueio explícito de combinações ainda não comprovadas;
- CP-015: fechado por perfis de áudio reais, sem AAC universal;
- CP-014 permanece para Phase 7 (verificação profunda);
- CP-005/012/021/022 seguem para Phase 6 (Storage Engine).
