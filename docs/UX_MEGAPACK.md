# CinePulse — MegaPack Visual & UX

Status: **em implementação**
Base protegida: **1.0.0-rc.5**

## Objetivo

Transformar a interface do CinePulse de uma GUI predominantemente funcional em um estúdio visual claro, previsível e agradável, **sem reescrever o pipeline de renderização e sem reduzir as garantias técnicas já validadas**.

A regra central é simples:

> Primeiro preservar o motor. Depois melhorar como o usuário entende, prevê e controla esse motor.

## Princípios obrigatórios

1. **Sem regressão silenciosa.** Render, fila, preflight, recuperação, saída atômica, Real-ESRGAN, RIFE, Demucs, VMAF, atualização e instalação continuam separados da camada visual.
2. **Preview honesto.** Miniaturas de VFX devem usar o mesmo `StudioFrameGenerator` do render real. Arte promocional não pode se passar por preview técnico.
3. **Feedback antes do custo.** Sempre que possível, mostrar o efeito da configuração antes de executar FFmpeg/IA pesada.
4. **Progressive disclosure.** O iniciante vê o essencial; o usuário avançado continua tendo acesso a todos os parâmetros.
5. **Estado inequívoco.** Preset selecionado, preset aplicado, qualidade ativa, modo de preview e estágio do render não podem parecer a mesma coisa quando não são.
6. **Ações destrutivas distinguíveis.** Excluir, cancelar, limpar e sobrescrever precisam de hierarquia e confirmação adequadas.
7. **Uma linguagem visual.** Cores, espaçamentos, títulos, cards, estados e botões passam a usar tokens compartilhados.
8. **Windows primeiro, sem aprisionar o núcleo.** A experiência principal continua voltada ao Windows, mas lógica visual testável deve permanecer independente do SO quando possível.

## Diagnóstico da base rc.5

### Pontos fortes preservados

- pipeline funcional já separado em módulos especializados fora da UI;
- Real-ESRGAN, RIFE, Demucs e VMAF integrados;
- preflight e avisos de qualidade extrema;
- render atômico e journal de recuperação;
- fila persistente;
- previews reais e comparação A/B já existentes como produto renderizado;
- gerenciamento de componentes e atualização;
- documentação de arquitetura reconhece que `studio.py` precisa ser extraído gradualmente.

### Dívida de UX prioritária

- `studio.py` concentra interface, estado, fila e orquestração; a classe principal possui mais de 100 métodos;
- a tela inicial usa grande área vazia e quase nenhum feedback visual;
- VFX são apresentados principalmente como checkboxes e nomes;
- transições são nomes em `Combobox`, exigindo que o usuário conheça o resultado antes de escolher;
- preview existente é útil para validação, mas caro demais para descoberta rápida;
- resumo no rodapé é tecnicamente rico, porém pouco hierárquico;
- seleção de preset e aplicação do preset são estados diferentes, mas visualmente muito próximos;
- ações de sistema, projeto e render competem pelo mesmo nível de atenção;
- componentes experimentais e integrados precisam de hierarquia visual mais forte.

## Arquitetura do MegaPack

### Camada de design

`src/cinepulse/ui/tokens.py`

Centraliza:

- cores oficiais da marca;
- superfícies light/dark;
- cores semânticas;
- espaçamento;
- raio e tipografia de referência.

A identidade usa os valores já documentados em `docs/BRAND.md`:

- Pulse Blue `#42D8FF`;
- AI Violet `#8B5CF6`;
- Audio Green `#37F5B0`;
- Cinema `#080B12`.

### Camada de preview imediato

`src/cinepulse/ui/preview.py`

Responsabilidades:

- gerar fundo de demonstração local quando não há vídeo;
- extrair um frame real do vídeo com FFmpeg quando possível;
- produzir miniaturas com o `StudioFrameGenerator` real;
- compor VFX sobre a imagem sem disparar o render completo;
- suportar Original / A-B / Resultado;
- gerar PPM para `PhotoImage` sem adicionar Pillow como dependência obrigatória.

Essa camada **não substitui** o preview de qualidade. Existem dois conceitos distintos:

- **preview imediato:** descoberta e ajuste visual;
- **preview renderizado:** validação real do pipeline, codec, interpolação, áudio e saída.

## Plano de telas

### Fase 1 — Shell + Início

Objetivo: tornar a primeira impressão autoexplicativa.

- shell visual consistente;
- preset com hierarquia clara;
- cards Rápido / Recomendado / Máximo;
- arquivos do projeto acessíveis na Home;
- resumo de hardware compacto;
- preview imediato;
- Original / A-B / Resultado;
- cards de VFX com miniaturas reais;
- atalhos de transição;
- resumo de configuração e ações finais agrupadas.

### Fase 2 — Visual e transições

Objetivo: tornar o ajuste artístico o coração do produto.

- painel de controles à esquerda;
- preview grande à direita;
- cards selecionáveis de VFX;
- direção musical como escolha visual;
- sliders com valor, explicação e reset;
- comparação rápida de variações;
- cards animados/representativos de transição;
- seção Demucs explicando benefício e custo;
- atualização debounced do preview.

### Fase 3 — Projeto

- tipo de projeto explicado visualmente;
- drag-and-drop quando tecnicamente seguro;
- metadados de vídeo e áudio após seleção;
- validação inline;
- saída sugerida sem esconder a decisão;
- preview de enquadramento/aspect ratio;
- comparação lado a lado como opção contextual.

### Fase 4 — Qualidade e saída

- agrupar Resolução/FPS/Formato;
- separar Melhoria, Interpolação, Codec/HDR e Áudio;
- mostrar impacto estimado: tempo, VRAM, espaço e compatibilidade;
- avisos de 8K/120+ no contexto da escolha;
- presets de plataforma sem mascarar parâmetros reais.

### Fase 5 — Fila

- cards/linhas com origem, saída, perfil, progresso e estado;
- reordenar antes de iniciar;
- retry controlado;
- abrir saída/relatório;
- resumo global da fila;
- estado vazio útil.

### Fase 6 — IA local

- separar claramente `Integrado`, `Instalado`, `Disponível` e `Experimental`;
- explicar o benefício real de cada componente;
- mostrar tamanho/licença/estado de validação;
- ações por componente;
- download com progresso e feedback de falha;
- nunca anunciar um componente detectado como função pronta sem integração real.

### Fase 7 — Estados transversais

- processamento;
- cancelamento;
- erro recuperável;
- erro bloqueante;
- sucesso;
- atualização;
- falta de espaço;
- hardware incompatível;
- componente faltante;
- render recuperado após interrupção.

## Quality gates

Uma fase só é considerada pronta quando:

- suíte automatizada anterior continua verde;
- novos componentes possuem teste quando a lógica for testável sem GUI;
- app abre sem exceções em smoke test;
- controles existentes continuam chamando os mesmos fluxos de render;
- nenhum recurso integrado some da interface sem substituição explícita;
- estados light/dark permanecem legíveis;
- janela mínima continua utilizável;
- interface não bloqueia durante FFmpeg, download ou geração pesada;
- preview imediato falha de forma graciosa e nunca impede render;
- nenhum path de mídia aparece em diagnóstico público por causa da nova UI;
- documentação é atualizada junto com mudanças de comportamento.

## Estado implementado

- design tokens criados;
- base visual modernizada sem trocar Tk/ttk;
- Home reorganizada em duas colunas;
- preview visual imediato adicionado;
- uso do mesmo motor VFX para miniaturas e overlay;
- tentativa assíncrona de usar frame real do vídeo;
- fallback de demonstração local;
- modos Original / A-B / Resultado;
- cards clicáveis para os oito VFX atuais;
- atalhos de transição;
- seleção de qualidade deixa de expulsar o usuário automaticamente da Home;
- novos testes de preview adicionados.

### Fase 2 — Visual Lab v1 concluída

- layout da aba `Visual e transições` movido para `ui/visual_view.py`;
- lógica visual determinística e metadados movidos para `ui/visual_lab.py`;
- VFX exibidos como cards com miniaturas produzidas pelo motor real;
- nomes longos recebem rótulos curtos sem alterar os identificadores usados pelo render;
- preview grande passa a reagir a foco, suavização e expressividade usando `shape_reactivity`;
- sinal musical demonstrativo é explicitamente identificado como demonstração e não como análise do áudio real;
- frame real do vídeo é reutilizado quando disponível;
- Original / A-B / Resultado também existem no Visual Lab;
- timeline demonstrativa e animação leve foram adicionadas sem acionar o pipeline pesado;
- quatro direções musicais ganharam atalhos visuais;
- transições principais ganharam miniaturas semânticas e continuam disponíveis integralmente no `Combobox`;
- variações `Mais suave`, `Mais energia`, `Menos partículas` e `Modo épico` podem ser comparadas e aplicadas;
- troca de cor atualiza as miniaturas de descoberta;
- cache visual deixa de ser descartado ao terminar uma instalação de componentes;
- preview interativo continua separado do preview renderizado e deixa essa diferença explícita na UI;
- suíte aumentada para 35 testes automatizados;
- smoke tests cobrem abertura e interação da aba em light e dark.

### Contrato de honestidade do Visual Lab

O Visual Lab deve explicar claramente o que é real e o que é aproximação:

- **real:** geometria e composição dos VFX, cor, intensidade, ocupação e função de reatividade;
- **representativo:** sinal musical sintético usado para experimentar foco/suavização/expressão e as miniaturas estáticas de transição;
- **somente no preview renderizado/final:** áudio real, stems Demucs, emenda temporal verdadeira, codec, RIFE, Real-ESRGAN, HDR e demais etapas pesadas.

Esse contrato evita que uma miniatura bonita prometa um comportamento que o render não executa.

### Fase 3 — Projeto concluída

- aba Projeto extraída para `ui/project_view.py`;
- helpers puros de UX em `ui/project_lab.py`;
- os dois modos de projeto viraram cards explicativos sem alterar os valores internos;
- vídeo e música ganham análise FFprobe assíncrona com metadados inline;
- destino recebe validação imediata de extensão e colisão com as entradas;
- enquadramento ganhou preview com frame real quando disponível e fallback demonstrativo;
- `Preencher` usa semântica de crop central e informa a área aproximada descartada;
- `Encaixar` preserva o quadro e representa barras;
- formato e enquadramento editados na aba Projeto usam as mesmas `StringVar` do render;
- preflight detalhado pode rodar em segundo plano e aparecer inline;
- modal detalhado anterior foi preservado;
- drag-and-drop ficou deliberadamente adiado para não adicionar dependência frágil antes de fechar o fluxo principal;
- suíte aumentada para 40 testes;
- smoke adicional usa vídeo e áudio sintéticos reais para validar FFprobe, frame, enquadramento e preflight.

### Fase 4 — Qualidade e saída concluída

- aba extraída para `ui/quality_view.py`;
- cálculos consultivos isolados em `ui/quality_lab.py`;
- resolução/FPS/formato agrupados como geometria da saída;
- melhoria e interpolação viraram cards com consequência e disponibilidade de componentes;
- painel Fonte → Destino mostra escala e multiplicação de FPS;
- carga relativa substitui ETA inventada por uma heurística explicitamente comparativa;
- referência de VRAM reutiliza a mesma lógica dos avisos de preflight;
- tamanho de saída usa duração real quando disponível e fica pendente quando não há dado suficiente;
- compatibilidade reúne HDR, escala extrema, FPS extremo, VRAM, componentes e NVENC;
- RIFE ausente é aviso/fallback, não bloqueio;
- Real-ESRGAN ausente permanece bloqueio quando explicitamente selecionado;
- seleção CPU preserva a regra anterior de retirar Real-ESRGAN;
- suíte aumentada para 44 testes;
- smoke com mídia real valida 8K/120/9:16 e atualização dinâmica do painel.

### Fase 5 — Fila concluída

- layout extraído para `ui/queue_view.py`;
- apresentação/agrupamento de estado isolados em `ui/queue_lab.py`;
- resumo global mostra aguardando, ativo, concluídos e itens que precisam de atenção;
- tabela prioriza projeto, perfil, progresso e estado;
- inspector detalha entrada, saída, processamento, VFX, erro/relatório e progresso;
- eventos reais de progresso do worker alimentam o item ativo sem criar um segundo medidor artificial;
- recuperação de item que estava renderizando fica explicitamente visível e reinicia em 0%;
- reordenação é permitida somente com fila parada e é persistida imediatamente;
- retry é restrito a erro/interrompido/cancelado;
- `Carregar no editor` restaura uma cópia das configurações sem modificar o item salvo;
- abrir saída/relatório ganhou ações explícitas;
- limpeza de concluídos preserva arquivos; limpeza total agora exige confirmação;
- não foi introduzida pausa falsa, ETA global inventada ou paralelismo de render;
- a fila usa contêiner rolável para não expulsar o rodapé global em janelas menores;
- suíte aumentada para 50 testes;
- smoke cobre light/dark, seleção, retry, reordenação e carregar no editor.

### Fase 6 — IA local concluída

- aba extraída para `ui/ai_view.py`;
- lógica de apresentação e estados isolada em `ui/ai_lab.py`;
- topo resume capacidades integradas prontas, faltantes, experimentais detectados e tamanho da seleção;
- contrato `Instalado ≠ integrado` fica visível permanentemente;
- filtros separam Todos / No render / Experimentais / Faltando;
- estados explicam consequência real, incluindo fallback do RIFE, ausência de stems do Demucs e VMAF opcional;
- inspector detalha benefício, integração, impacto de ausência, espaço, licença e recomendação;
- `Selecionar necessários` e `Instalar necessários` nunca incluem experimentais automaticamente;
- opt-in experimental libera somente seleção/download e é revogável sem ativar recurso no render;
- progresso local mostra atividade e percentual somente quando o instalador fornece percentual explícito;
- botão `Reverificar` força novo inventário e interações comuns reutilizam snapshot para não reprovar VMAF/FFmpeg a cada clique;
- detecção do Demucs foi alinhada ao `stem_engine`, incluindo `htdemucs_ft.yaml`;
- suíte aumentada para 58 testes;
- smoke cobre 1024×700, filtros, opt-in, seleção segura, light/dark e render básico real.

### Fase 7 — Estados transversais concluída

- semântica global `info / busy / success / warning / error` isolada em `ui/feedback_lab.py`;
- strip persistente substitui o antigo status solto sem remover `self.status` dos fluxos legados;
- feedback combina badge, título, detalhe e próxima ação segura — cor nunca é o único indicador;
- Central de atividade mantém até 40 eventos da sessão e preserva detalhe técnico sem poluir as telas principais;
- estágios intermediários atualizam o estado corrente sem gerar dezenas de notificações;
- render/preview passam a distinguir preparação, sucesso verificado, cancelamento e falha;
- erros conhecidos apontam para Projeto, Qualidade ou IA local conforme a causa;
- preflight bloqueante/avisos/sucesso também aparecem no estado global;
- fila recuperada após encerramento registra explicitamente o reinício seguro em 0%;
- fila concluída com falhas usa warning, não falso sucesso;
- instalação de IA e atualização deixam de depender de modais informativos para conclusão normal;
- recuperação de saída parcial deixa claro quando o arquivo foi promovido, preservado ou recusado;
- confirmações destrutivas e decisões de risco continuam modais;
- suíte aumentada para 62 testes automatizados;
- smoke mínimo valida os cinco estados, central de atividade, light/dark e preflight bloqueado.

### Fase 8 — Polish final e Release UX implementada

- primeiro uso ganhou onboarding não modal e reaproveitável via `F1`;
- preferências de interface persistem light/dark, aba, geometria e conclusão do guia;
- geometria restaurada é sanitizada para o monitor atual;
- os seis workspaces principais passam a empilhar painéis automaticamente em 1024×700;
- wheel funciona sobre cards/labels sem roubar scroll de Treeview/Text/Listbox;
- navegação por teclado cobre abas, arquivos, preview, log e Central de atividade;
- foco de botões recebe destaque explícito;
- DPI awareness do Windows é solicitado antes da criação do Tk, com fallback seguro;
- preset selecionado, preset aplicado e ajustes manuais passam a ser estados visivelmente diferentes;
- Central de atividade ganha cópia de detalhe e fechamento por `Esc`;
- suíte sobe para 69 testes e o worker básico é revalidado após o polish.

## Próximo marco

**Aceite Windows da 1.0:** executar `docs/WINDOWS_UX_ACCEPTANCE.md` na máquina de destino, incluindo 100/125/150/200% DPI, fila real com dois itens e render longo. Xvfb não substitui esse aceite.
