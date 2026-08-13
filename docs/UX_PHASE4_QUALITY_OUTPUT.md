# UX Phase 4 — Qualidade e saída

Status: **implementado no MegaPack de desenvolvimento**

## Objetivo

Transformar a aba `Qualidade e saída` de uma lista plana de parâmetros em um workspace de decisão técnica. O usuário continua tendo acesso aos mesmos controles, mas passa a ver **a consequência da configuração atual** no contexto da fonte e do hardware detectado.

A fase não promete tempo exato de render. Sem uma matriz de benchmarks por GPU/modelo/codec, qualquer ETA apresentado antes do processamento seria enganoso. Em vez disso, o CinePulse mostra **carga relativa heurística**, escala, multiplicação de FPS, referência de VRAM, tamanho aproximado e avisos reais do preflight.

## Estrutura entregue

### Imagem de saída

Agrupa:

- resolução;
- FPS;
- formato da tela.

O formato continua sincronizado com a aba Projeto e usa a mesma `StringVar` consumida por `RenderSettings`.

### Melhoria de imagem

As opções viraram cards explicativos:

- `Preservar`;
- `Lanczos`;
- `Real-ESRGAN IA`.

O card do Real-ESRGAN mostra se o componente local está presente. Se o usuário selecionar IA sem o componente, a interface não mente: mostra `Ação necessária`, e o render final continua protegido pela validação já existente.

### Movimento e interpolação

As opções viraram cards:

- `RIFE IA`;
- `FFmpeg suave`;
- `Repetir quadros`.

RIFE ausente **não é tratado como bloqueio**, porque o pipeline real já possui fallback automático para FFmpeg. A UI explicita esse comportamento.

### Áudio e verificação final

Agrupa:

- tratamento de loudness;
- preservação do áudio original no modo compatível;
- verificação VMAF quando aplicável.

### Uso da máquina

Agrupa:

- GPU automática / somente CPU;
- threads de CPU;
- reserva mínima de disco.

O contrato anterior foi preservado: ao escolher somente CPU com Real-ESRGAN ativo, o CinePulse troca a melhoria para Lanczos, pois o módulo local de IA depende da GPU.

## Painel de impacto

`ui/quality_lab.py` calcula dados consultivos e testáveis.

### Fonte → destino

Quando o vídeo foi analisado:

- resolução da fonte;
- FPS da fonte;
- perfil SDR/HDR;
- resolução final;
- FPS final;
- formato;
- duração usada para estimativa.

No modo Loop musical, o tamanho estimado só usa a duração da música após o áudio ser realmente analisado. Antes disso, a UI deixa a duração pendente em vez de inventar um valor.

### Escala

Mostra a maior razão dimensional entre destino e fonte.

Exemplo: um vídeo 1280×720 enviado para um destino vertical 4320×7680 representa ampliação dimensional de aproximadamente `10,7×` na dimensão limitante. A UI classifica isso como ampliação extrema e não afirma que IA possa recuperar informação inexistente.

### Movimento

Mostra:

- FPS fonte → FPS destino;
- multiplicação aproximada do número de quadros;
- estratégia selecionada.

Se o FPS final não excede o FPS da fonte, a interface informa que não é necessário criar quadros extras.

### VRAM

Quando Real-ESRGAN está ativo, a referência segue a mesma heurística usada pelos avisos de preflight:

`2048 MB + megapixels_destino × 420 MB`

É apresentada como **referência**, não como requisito absoluto. Tiles, modelo, driver e outras etapas podem mudar o consumo real.

### Arquivo estimado

Usa a mesma fórmula de bitrate de referência existente no Studio:

- escala com resolução;
- escala com FPS;
- limite conservador entre 8 e 600 Mb/s;
- aplica duração quando conhecida.

O texto usa `~` e `bitrate de referência` para deixar claro que encode real e conteúdo podem produzir tamanho diferente.

## Carga relativa

A carga relativa é uma **heurística comparativa**:

1. parte do throughput de pixels em relação a 1080p/60;
2. aplica peso adicional para upscale neural quando há ampliação;
3. aplica peso adicional quando é necessário criar quadros, diferenciando RIFE/FFmpeg/repetição.

Classes:

- Leve;
- Moderada;
- Alta;
- Muito alta;
- Extrema.

Ela serve para comparar configurações dentro do CinePulse. Não é convertida em minutos/horas.

## Compatibilidade e avisos

O painel reaproveita `preflight.quality_warnings` e acrescenta contexto de componentes/hardware:

- ampliação acima de 4×;
- FPS acima de 4× da fonte;
- 240/480 fps;
- pressão estimada de VRAM;
- RIFE acima de 120 fps;
- fonte HDR e VFX SDR;
- Real-ESRGAN ausente;
- RIFE ausente com fallback;
- NVENC não detectado.

Estados semânticos usam verde, amarelo, vermelho ou azul sem depender somente do texto.

## Honestidade visual

Não foi criada uma imagem falsa de “antes/depois Real-ESRGAN”. Uma miniatura simulada seria visualmente atraente, mas prometeria um detalhe que depende do conteúdo e do modelo real. A aba leva o usuário ao `Gerar preview`, que é o lugar correto para avaliar textura, movimento e encode.

## Arquivos

- `src/cinepulse/ui/quality_lab.py`;
- `src/cinepulse/ui/quality_view.py`;
- `src/cinepulse/studio.py` para sincronização/controller;
- `tests/test_quality_lab.py`.

## Quality gates

- 44 testes automatizados passando;
- `compileall` sem erro;
- smoke de GUI com mídia real;
- troca 8K/120/9:16 + RIFE + Real-ESRGAN atualiza impacto sem bloquear Tk;
- modo CPU mantém o comportamento anterior e retira Real-ESRGAN;
- light/dark passam no smoke;
- sem dependência nova;
- `RenderSettings` permanece inalterado;
- nenhuma ETA falsa foi introduzida.

## Correção encontrada durante a fase

Ao revisar a relação entre UX e pipeline, foi identificado que o primeiro rascunho da Fase 3 tratava RIFE ausente como requisito bloqueante no card inline. Isso não correspondia ao render real, que possui fallback FFmpeg. A regra foi corrigida: **Real-ESRGAN ausente pode bloquear quando selecionado; RIFE ausente gera aviso e fallback.**

## Próxima fase

**Fase 5 — Fila:** transformar a tabela vazia/operacional em uma fila legível, recuperável e orientada a estado, mantendo persistência e recuperação já existentes.
