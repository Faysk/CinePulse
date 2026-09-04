# Overlay Composer — Preview

> Status: **Preview / experimental**. Esta feature vive na branch `preview-overlay-composer` e não altera a linha Stable 1.0 até passar pelos gates automatizados e pela aceitação visual/manual.

## Objetivo

O Overlay Composer permite montar elementos gráficos por cima do vídeo final sem transformar o CinePulse em um editor generalista. O foco é conteúdo musical e Lo-fi: personagem/arte em PNG ou GIF, waveform, barras e espectro, com posicionamento visual rápido e render final eficiente mesmo em projetos longos.

## Fluxo do criador

1. Selecione o vídeo e a música normalmente no CinePulse.
2. Abra o **Visual Lab** e use **Overlay Composer · Preview**.
3. Adicione um PNG/GIF e um ou mais visualizadores.
4. Arraste as layers no canvas e redimensione pelo handle inferior direito.
5. Ajuste opacidade, posição, tamanho, velocidade do GIF e parâmetros do visualizador.
6. Selecione personagem + visualizador e use **Agrupar** para mover/redimensionar o conjunto.
7. Opcionalmente aplique um **Layout rápido** e personalize a partir dele.
8. Gere um preview real antes do render longo.
9. O render final aplica a composição depois dos estágios pesados de IA/VFX.

## Layers e coordenadas

O modelo usa `cinepulse.overlay-scene/1` e coordenadas normalizadas (`0..1` como referência de canvas). Isso evita salvar posições dependentes de pixels. Uma composição montada em preview 640×360 pode ser projetada proporcionalmente para 1080p, 4K, 8K ou outra resolução de saída.

Cada layer possui:

- `id`, nome, tipo, `z_index`;
- visibilidade (`enabled`) e bloqueio (`locked`);
- retângulo normalizado X/Y/largura/altura;
- opacidade, rotação e preservação de aspecto;
- `AssetSpec` para PNG/GIF ou `VisualizerSpec` para áudio;
- serialização determinística e fingerprint.

## PNG e GIF

### PNG

O render final abre PNG como stream estático (`-loop 1`). Não existe expansão para milhares/milhões de PNGs intermediários.

### GIF

GIF é decodificado como stream. Quando `loop=True`, o loop ocorre no demuxer do FFmpeg (`-stream_loop -1`). Quando `loop=False`, o GIF termina naturalmente e o overlay usa `eof_action=pass`.

A velocidade do GIF usa ajuste de PTS, sem criar uma cópia frame-a-frame no scratch.

## Visualizadores musicais

São suportados:

- **Waveform** — linha temporal do áudio;
- **Barras** — frequência em bins configuráveis;
- **Espectro** — curva de frequência.

Controles atuais:

- foco: full, bass, mids, highs ou beats;
- sensibilidade;
- cor principal;
- cor secundária para barras/espectro;
- espessura;
- quantidade de barras;
- espelhamento no eixo central;
- opacidade e transformação da layer.

### Fidelidade Preview × render final

O preview interativo usa NumPy para permitir resposta imediata enquanto o usuário arrasta controles. O render real usa filtros FFmpeg.

Há equivalência de intenção, mas não identidade pixel-a-pixel entre os dois motores. Pontos importantes:

- waveform usa a cor principal;
- espessura de linha no FFmpeg é aproximada por dilation 3×3 repetida, porque `showwaves`/`showfreqs` não expõem espessura de linha nativa;
- barras usam `showfreqs` com largura igual à quantidade escolhida e upscale nearest-neighbor para preservar o número visual de bins;
- espelhamento final usa split + vflip + vstack;
- em fonte mono, a cor secundária do `showfreqs` pode não aparecer com a mesma distribuição horizontal do gradiente demonstrativo do preview.

Por isso, **Gerar preview real** continua sendo o gate perceptual antes de um render longo.

## Reação musical no editor

O canvas interativo usa um sinal demonstrativo para manter a interface leve e responsiva. Ele serve para visualizar estilo, ocupação, sensibilidade e movimento.

A sincronização real com a música acontece no preview renderizado/final, onde o visualizador recebe o áudio real no FFmpeg.

## Render order

A composição foi deliberadamente posicionada no final da cadeia visual:

1. leitura/loop da fonte;
2. cor/enquadramento;
3. Real-ESRGAN quando aplicável;
4. VFX do CinePulse;
5. RIFE/interpolação quando aplicável;
6. escala/finalização do vídeo base;
7. **Overlay Composer**;
8. codificação/mux final.

Consequências:

- PNG/GIF não são ampliados por Real-ESRGAN sem necessidade;
- overlays não são interpolados pelo RIFE;
- o layout trabalha diretamente na resolução final;
- o custo de IA do vídeo base não cresce por causa do overlay.

## Áudio e visualizer

O Studio mantém dois papéis separados:

- **áudio de saída**: segue a cadeia normal de preservação/masterização/LUFS;
- **áudio do visualizer**: leitura dedicada, usada somente para gerar vídeo do waveform/barras/espectro.

Quando existem vários visualizadores, o áudio dedicado é aberto uma única vez e dividido internamente com `asplit`.

Isso impede que filtros usados para desenhar o visualizer alterem acidentalmente a trilha de saída.

## Agrupamento

Grupos preservam a geometria relativa entre os membros.

A UI permite:

- mover o grupo pelo bounding box;
- redimensionar proporcionalmente pelo handle do grupo;
- undo/redo das alterações;
- impedir transformação parcial quando qualquer membro do grupo está bloqueado.

O handle do grupo possui hit-test prioritário, inclusive quando fica numa região vazia entre as layers.

## Layouts rápidos

A Preview inclui receitas iniciais:

- **Personagem + Waveform**;
- **Personagem + Barras**;
- **Waveform panorâmico**;
- **Espectro minimalista**.

Layouts mudam geometria/visualizer e podem criar grupo, mas não substituem o arquivo PNG/GIF escolhido pelo usuário.

## Persistência

A cena é armazenada em `RenderSettings.overlay_scene_json`.

Ela acompanha:

- configuração atual do Studio;
- presets personalizados;
- fila persistida;
- item recarregado da fila;
- worker/render final.

Compatibilidade com versões anteriores:

- configurações antigas sem `overlay_scene_json` recebem uma cena vazia;
- campos futuros desconhecidos continuam ignorados pelo restore legado;
- arquivo de overlay ausente bloqueia o render com mensagem da layer afetada, em vez de renderizar silenciosamente sem o elemento.

## Projetos longos

A arquitetura é streaming. O número de streams auxiliares depende da quantidade de layers, não de `duração × FPS`.

Para uma cena com 2 assets e múltiplos visualizadores:

- 2 streams de asset;
- 1 leitura compartilhada de áudio para todos os visualizadores;
- 0 sequência PNG temporária por frame;
- 0 cache de overlay dimensionado pela duração.

Isso não significa custo constante de CPU/GPU: resolução, FPS, tamanho das layers, quantidade de GIFs e filtros continuam influenciando o tempo de render.

Projetos longos com muitos GIFs recebem aviso porque o GIF precisa ser decodificado repetidamente durante toda a duração, mesmo sem crescimento de scratch.

## Safe areas

Existem guias de canvas e uma guia vertical social conservadora. A guia social **não é contrato exato** de Shorts/Reels/TikTok; interfaces e áreas ocupadas pelas plataformas mudam com o tempo. Use como margem visual e confira a plataforma de destino antes de publicar.

## Limites atuais da Preview

- somente PNG e GIF como assets externos nesta fase;
- sem texto vetorial/editor tipográfico próprio;
- sem keyframes/timeline de entrada e saída de layer;
- smoothing do `VisualizerSpec` ainda não tem paridade completa/exposição avançada;
- preview interativo usa reação demonstrativa;
- não há promessa de equivalência pixel-a-pixel NumPy × FFmpeg;
- 4K/8K e projetos reais de 1–2 h ainda precisam de aceitação manual/soak físico antes de promoção para Stable.

## Gates automatizados

O workflow `Overlay Composer Preview` cobre:

- unit tests Ubuntu + Windows;
- compilação do Studio integrado;
- persistência/backward compatibility;
- geometria de grupo e layouts;
- preview waveform/barras/espectro;
- FFmpeg real com PNG/GIF/waveform/barras espelhadas em Linux e Windows;
- contrato longform de 2 h;
- soak streaming Linux sem expansão de arquivos temporários.

Consulte `docs/OVERLAY_COMPOSER_ACCEPTANCE.md` para o estado exato dos gates e pendências manuais.
