# CinePulse 1.2.12

Esta release corrige os últimos caminhos auxiliares que ainda podiam divergir do adaptador GPU selecionado e fecha a timeline de áudio da comparação A/B.

## NVENC auxiliar no mesmo adaptador do render

O pipeline principal já fixava RIFE, Real-ESRGAN, delivery final, recovery e resident encode no `gpu_index` selecionado. Alguns encoders auxiliares ainda usavam o default do FFmpeg, que normalmente é GPU 0.

A 1.2.12 adiciona seleção explícita de GPU em:

- H.264/NVENC usado por intermediários SDR e comparação;
- helper HEVC/NVENC legado do Studio;
- fallback H.264/NVENC direto do VFX.

Isso evita que uma máquina multi-GPU processe IA em um adaptador e codifique intermediários em outro sem intenção.

## Comparação A/B com timeline de áudio exata

A comparação A/B já limitava o vídeo por quantidade exata de frames, mas fazia stream-copy do áudio do arquivo processado. Padding do codec ou um EOF de áudio ligeiramente posterior podia deixar o MP4 de comparação durar além do último frame.

Agora a comparação calcula a duração real como `comparison_frames / comparison_fps`, aplica trim/pad de áudio nessa janela e codifica a faixa de comparação em AAC 320 kbps. O vídeo continua limitado por `-frames:v` e nenhum `-t` global é reintroduzido.

## Comparação A/B não invalida o render principal

A comparação é pós-processamento opcional. Se o H.264/NVENC auxiliar falhar, o CinePulse remove a saída parcial e repete uma vez com libx264. Se até a comparação CPU falhar, ou se o usuário cancelar enquanto ela é montada, o preview principal já validado permanece como resultado de sucesso em vez de o job ser reclassificado como falha/cancelamento.

## O que não muda

Não há alteração de modelo, escala, FPS, cor/HDR, política full-utilization ou qualidade do arquivo final. A mudança é de consistência de dispositivo e de duração na saída auxiliar de comparação.
