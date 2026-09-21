# CinePulse 1.2.10

Esta release não muda o algoritmo de render da 1.2.9. Ela transforma o contrato frame-bound de áudio em uma prova de integração com FFmpeg real dentro do gate de mídia.

## Gate de áudio real

O novo `integration_audio_timeline.py` cria uma timeline de 31 frames a 30 fps (31/30 s) e executa dois casos:

- áudio de 0,75 s precisa ser preenchido até a timeline final;
- áudio de 1,50 s precisa ser aparado até a mesma timeline.

A saída usa FFV1 + PCM 24-bit em Matroska. Depois, o áudio é decodificado novamente e o teste exige exatamente 49.600 samples a 48 kHz, além de 31 frames de vídeo.

## Por que contar samples

Matroska pode não publicar `stream.duration` em todos os streams PCM. Em vez de depender dessa metadata opcional, o gate mede o payload de áudio decodificado. Isso prova diretamente trim/pad e evita falso negativo por ausência de metadata.

## CI

O teste entra no profile `media`, portanto é executado pelo job Media Integrity e pelos gates Release light. Full-utilization, qualidade, codecs e comportamento de produção permanecem iguais à 1.2.9.
