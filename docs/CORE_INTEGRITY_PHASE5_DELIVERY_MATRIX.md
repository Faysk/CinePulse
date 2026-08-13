# Phase 5 — Delivery Matrix

## Contrato

A extensão não é mais apenas um nome de arquivo. Ela participa do planejamento e define uma combinação legal de contêiner, vídeo e áudio.

### Automático pelo arquivo

- `.mp4` → YouTube / Streaming;
- `.mov` → Master de arquivo;
- `.mkv` → Arquivo eficiente;
- `.webm` → Web.

### Perfis explícitos

Se o usuário escolher um perfil específico, a extensão precisa corresponder. Isso evita renders de várias horas terminarem em erro de muxer.

## Matriz

| Saída | Encoder de vídeo | Pixel format | Áudio | Observação |
|---|---|---|---|---|
| MP4 | HEVC NVENC ou libx265 | yuv420p / p010le | AAC 384k | `hvc1`, faststart |
| MOV master | prores_ks, profile HQ | yuv422p10le | PCM 24-bit | master/mezzanine |
| MKV arquivo | HEVC NVENC ou libx265 | yuv420p / 10-bit | FLAC | áudio lossless |
| WebM | libvpx-vp9 | yuv420p / 10-bit | Opus | sem HEVC/AAC |

## Limite estável

O CinePulse 1.0 ainda não declara 10K/12K ou 144/240/480 fps como entrega estável. Essas opções ficam bloqueadas até testes de hardware/codec provarem um perfil concreto. A decisão é intencionalmente conservadora e atende ao CP-009.

## Color pipeline

A Delivery Matrix recebe o `ColorPipeline` já resolvido. Portanto HEVC/VP9 recebem 8/10-bit conforme a informação que realmente sobreviveu ao pipeline; ProRes master é armazenado em 10-bit sem afirmar que uma fonte 8-bit ganhou detalhe.

## Áudio

- AAC: 384 kb/s, 48 kHz;
- PCM 24-bit: sem downmix/sample-rate forçado;
- FLAC: lossless, sem downmix/sample-rate forçado;
- Opus: 256 kb/s VBR, 48 kHz.

A normalização LUFS continua independente do codec e é aplicada antes da codificação final.
