# UX Phase 3 — Projeto

Status: **implementado no MegaPack de desenvolvimento**

## Objetivo

Transformar a aba Projeto em um workspace de preparação e validação, para que o usuário entenda **o que entrou, o que sairá e o que será cortado ou preservado** antes de pagar o custo de um preview renderizado.

A fase não altera `RenderSettings`, FFmpeg, Real-ESRGAN, RIFE, Demucs, fila ou o pipeline final. Ela reorganiza a apresentação e adiciona leitura/feedback em segundo plano.

## Fluxo entregue

1. Escolher explicitamente entre `Loop musical` e `Melhorar vídeo original` por cards explicativos.
2. Selecionar vídeo, música e destino.
3. Receber metadados inline do FFprobe sem bloquear a interface.
4. Ver um frame real do vídeo no guia de enquadramento quando a extração é possível.
5. Experimentar formato e `Preencher / cortar` ou `Encaixar / barras` usando as mesmas variáveis do render.
6. Ver uma explicação aproximada de quanto da área da fonte será cortada no modo `Preencher`.
7. Executar a pré-verificação detalhada dentro da própria aba, sem abrir modal para o fluxo normal.
8. Usar o preview renderizado para validar temporalmente vídeo, áudio, VFX e transição antes do vídeo final.

## Metadados inline

### Vídeo

A interface resume:

- resolução;
- FPS;
- duração;
- codec/perfil;
- SDR/HDR e profundidade de bits;
- áudio embutido quando existe.

### Música

A interface resume:

- duração;
- codec;
- sample rate;
- canais;
- bitrate quando informado pelo FFprobe.

Falhas de leitura aparecem no próprio card e não impedem o usuário de trocar o arquivo.

## Enquadramento

`ui/project_lab.py` implementa uma prévia geométrica independente de Tk.

O comportamento é equivalente às decisões do filtro final:

- **Preencher:** escalar até cobrir e cortar pelo centro;
- **Encaixar:** escalar até caber e completar com barras.

O contorno azul é somente um guia da UI e não aparece na exportação.

Para `9:16`, `16:9`, `IMAX 1.90:1`, `Cinema Wide 2.39:1` e `Original`, a razão é calculada explicitamente. Quando há frame real, a prévia usa o tamanho lógico da fonte obtido pelo FFprobe.

## Saúde do projeto

A validação foi dividida em dois níveis.

### Inline imediata

Sem modal:

- existência do vídeo;
- existência da música quando obrigatória;
- destino informado;
- extensão/container da saída;
- proteção contra sobrescrever uma entrada;
- aviso quando a pasta direta de saída ainda não existe.

### Pré-verificação detalhada

Executada em thread para não bloquear Tk e reutilizando `_preflight_report` já existente:

- tamanho estimado da saída;
- temporários estimados;
- espaço disponível;
- reserva mínima;
- HDR/faixa de cor;
- resolução/FPS extremos;
- pressão estimada de VRAM;
- Real-ESRGAN selecionado/ausente como bloqueio quando necessário;
- RIFE selecionado/ausente como aviso, preservando fallback FFmpeg;
- aceleração disponível;
- recomendações sobre fonte de áudio.

O resultado fica no card `Saúde do projeto`. O diálogo detalhado antigo continua disponível como ação secundária para não remover comportamento existente.

## Honestidade do preview

A aba distingue três níveis:

- **guia de enquadramento:** geometria instantânea de corte/barras;
- **preview visual:** descoberta rápida de VFX em outras áreas do app;
- **preview renderizado:** validação real de mídia, áudio, transição, interpolação e encode.

O guia de enquadramento não promete upscale, RIFE, VFX, codec ou qualidade final.

## Decisão sobre drag-and-drop

Drag-and-drop foi **adiado deliberadamente** nesta fase. Tk/ttk puro não oferece um caminho robusto e portátil sem dependência adicional/integração específica de plataforma. A prioridade foi entregar seleção, análise e validação confiáveis antes de adicionar uma conveniência que pudesse fragilizar instalação ou empacotamento.

## Arquivos

- `src/cinepulse/ui/project_lab.py`: helpers puros de metadados, validação leve e enquadramento;
- `src/cinepulse/ui/project_view.py`: construção Tk da aba;
- `src/cinepulse/studio.py`: controller assíncrono e sincronização com estado já existente;
- `tests/test_project_lab.py`: testes determinísticos da nova lógica.

## Quality gates

- 40 testes automatizados passando;
- `compileall` sem erro;
- smoke GUI de navegação/interação da aba Projeto em light/dark;
- smoke com mídia sintética real: FFprobe + extração de frame + enquadramento + pré-verificação inline;
- nenhuma alteração no contrato de `RenderSettings`;
- nenhum caminho pesado de render substituído;
- falha de metadados ou frame nunca bloqueia a troca de arquivo;
- nenhuma nova dependência obrigatória.

## Próxima fase

**Fase 4 — Qualidade e saída:** reorganizar resolução/FPS/formato, melhoria/interpolação, áudio e uso de máquina; apresentar custo/compatibilidade no contexto da escolha e reduzir a sensação de “painel técnico sem consequência visível”.
