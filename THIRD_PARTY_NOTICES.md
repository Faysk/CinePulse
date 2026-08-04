# Componentes de terceiros

O repositório do CinePulse contém integração, mas não deve conter binários ou pesos dos projetos abaixo. A licença do CinePulse não altera as licenças desses componentes.

| Componente | Finalidade | Distribuído no Git | Verificação necessária |
|---|---|---:|---|
| FFmpeg/FFprobe | codificação e análise | não | a licença muda conforme os recursos habilitados na build |
| Real-ESRGAN | upscale | não | código, binário NCNN e modelos |
| RIFE | interpolação | não | implementação e checkpoint escolhidos |
| BasicVSR++/MMagic | restauração temporal | não | código, dependências e checkpoints |
| Demucs | separação de áudio | não | código e pesos |
| CLAP | análise musical | não | código, dataset e checkpoint |
| Video Depth Anything | profundidade | não | há variantes/checkpoints com termos diferentes |
| SAM 2 | segmentação | não | código e checkpoints |
| CoTracker | rastreamento | não | código e checkpoints |
| CodeFormer | restauração facial | não | código, detectores e modelos |
| VMAF | avaliação perceptiva | não | biblioteca, modelos e build do FFmpeg |
| LTX | geração experimental | não | código e checkpoint são avaliados separadamente |

Antes de uma release, fixe a versão, URL oficial, SHA-256, licença e permissão de redistribuição de cada artefato em `src/cinepulse/resources/components.catalog.json`. Se a redistribuição não estiver claramente permitida, o instalador deve direcionar o usuário à fonte oficial ou fazer download sob solicitação, sem espelhar o arquivo.

Este documento organiza o projeto; não substitui aconselhamento jurídico.

