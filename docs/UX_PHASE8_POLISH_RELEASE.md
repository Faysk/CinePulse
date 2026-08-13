# UX MegaPack — Phase 8: Polish final e Release UX

Status: **implementada no código; aceite visual final no Windows ainda é obrigatório**.

## Objetivo

Fechar as diferenças que fazem uma interface funcional ainda parecer “ferramenta interna”: primeiro uso, navegação por teclado, foco, comportamento em janela mínima, DPI, persistência de preferências, clareza de preset e consistência de ajuda.

A Phase 8 não altera `RenderSettings`, FFmpeg, Real-ESRGAN, RIFE, Demucs, VMAF, fila ou o formato dos projetos. O trabalho é deliberadamente de shell/UX.

## Mudanças implementadas

### 1. Primeiro uso sem modal bloqueante

A Home mostra um card `Primeiros passos` enquanto o usuário ainda não concluiu o onboarding. Ele explica o fluxo em três ações e permite ir diretamente para Projeto ou Visual Lab.

- não bloqueia a aplicação;
- pode ser dispensado com `Entendi`;
- a escolha é persistida em `config/ui_state.json`;
- o guia completo continua acessível por `Ajuda` / `F1`.

### 2. Guia rápido reaproveitável

`F1` abre um guia local com:

- Projeto;
- Visual Lab;
- Qualidade;
- preview renderizado;
- Fila;
- IA local;
- contrato `Instalado ≠ integrado`;
- atalhos de teclado.

O guia acompanha light/dark em tempo real e fecha com `Esc`.

### 3. Atalhos de teclado

- `F1`: primeiros passos;
- `Ctrl+1 … Ctrl+6`: abas;
- `Ctrl+Tab` / `Ctrl+Shift+Tab`: próxima/anterior;
- `Ctrl+O`: vídeo;
- `Ctrl+Shift+O`: música;
- `Ctrl+Shift+S`: saída;
- `Ctrl+P`: preview renderizado;
- `Ctrl+L`: log;
- `Ctrl+Shift+A`: Central de atividade.

Não existe atalho de um toque para apagar, limpar fila ou iniciar um render final caro. Ações de risco continuam exigindo intenção explícita.

### 4. Preset selecionado ≠ preset aplicado

A área de preset agora expõe três estados sem ambiguidade:

- `Ativo: <nome>`;
- `Selecionado: <nome> • ainda não aplicado | Ativo: <nome>`;
- `Ativo: <nome> • ajustes manuais`.

Selecionar um nome no combo não muda o projeto até `Aplicar`. Ajustes manuais depois da aplicação também ficam explícitos. O objetivo é impedir que o cabeçalho prometa 8K/120 enquanto o estado real já foi alterado para outra configuração.

### 5. Layout responsivo real em 1024×700

Os workspaces de duas colunas foram registrados como splits responsivos:

- Home;
- Projeto;
- Qualidade e saída;
- Visual e transições;
- Fila;
- IA local.

Em janelas compactas eles empilham os painéis verticalmente e removem `minsize` horizontais que antes podiam criar conteúdo inacessível. Em janelas amplas retornam às proporções originais.

O rodapé também muda por contexto em 1024×700: o `Cancelar` não reserva espaço quando não há processamento, o progresso ocioso some, `Adicionar à fila` ganha uma ação compacta ao lado do render e utilidades secundárias saem do shell mínimo. Durante um processamento, o resumo longo cede espaço para barra, estágio, feedback e cancelamento.

O threshold atual é consultivo e centralizado em `ui/polish_lab.py`, não espalhado pelas views.

### 6. Scroll consistente

`ScrollableTab` passa a aceitar wheel sobre cards e labels, inclusive `Button-4/5` em plataformas que usam esses eventos. Treeview/Text/Listbox preservam seu próprio scroll.

### 7. DPI do Windows

Antes de criar o primeiro `Tk`, o CinePulse tenta:

1. `PROCESS_PER_MONITOR_DPI_AWARE`;
2. fallback `SetProcessDPIAware`.

A chamada é best-effort e nunca impede a abertura. O código evita forçar `tk scaling` manualmente para não aplicar escala duas vezes em instalações nas quais Tk/Windows já negociaram DPI corretamente.

### 8. Geometria e preferências persistentes

`config/ui_state.json` armazena somente estado de interface:

- light/dark;
- onboarding concluído;
- última aba;
- geometria da janela.

Geometrias restauradas são sanitizadas para o monitor atual. Mudança de monitor/DPI não deve deixar a janela fora da área visível.

Esse arquivo é conveniência: erro de escrita nunca bloqueia render.

### 9. Foco e atividade

- botões recebem foco visual reforçado no tema compartilhado;
- Central de atividade fecha com `Esc`;
- detalhe pode ser copiado sem selecionar manualmente o Text;
- `Enter` atualiza o evento selecionado;
- `Ctrl+C` copia o detalhe corrente;
- atalhos do guia navegam para a área escolhida e fecham o guia, devolvendo o foco ao editor.

### 10. Encerramento limpo do shell Tk

Os callbacks periódicos do Studio (`poll`, relógio, responsive layout, previews e sequência da fila) passam por um scheduler rastreado. Ao fechar:

- novos callbacks deixam de ser aceitos;
- animação demonstrativa é encerrada;
- timers pendentes são cancelados antes de destruir o `Tk`;
- reabrir o Studio no mesmo processo não deixa comandos Tcl órfãos.

O ajuste também impede que iniciar/parar/iniciar rapidamente a animação do Visual Lab crie duas cadeias de playback concorrentes.

## Novos módulos

- `ui/polish_lab.py`: estado, geometria, compactação e catálogo de atalhos testáveis sem Tk;
- `ui/polish_view.py`: onboarding, guia rápido e registry de splits responsivos;
- `ui/platform_support.py`: DPI awareness do Windows.

## Validação automatizada

A suíte passou de 62 para **69 testes**. Novos testes cobrem:

- sanitização de estado de UI;
- geometria inválida/off-screen;
- compactação em 1024×700;
- mapeamento de abas;
- unicidade dos atalhos documentados;
- hook DPI best-effort.

## Smoke de GUI

Em Xvfb/Tk 8.6 foram exercitados:

- 1440×900 wide;
- 1024×700 compact;
- seis splits responsivos;
- rodapé compacto ocioso e ativo sem cortar feedback/ações principais;
- seleção de preset sem aplicação;
- aplicação de preset;
- detecção de ajuste manual;
- F1/guia;
- light → dark → light;
- navegação por atalho;
- Central de atividade;
- dismiss do onboarding;
- encerramento limpo;
- duas instâncias Tk sequenciais no mesmo processo sem callback Tcl órfão;
- stop/restart rápido da animação do Visual Lab sem duplicar a cadeia de timers.

## Smoke de render

O worker básico foi executado depois do polish com mídia sintética:

- fonte sintética;
- saída 1280×720 / 30 fps;
- duração final 2,4 s;
- áudio presente;
- frequência dominante final 880 Hz.

Resultado: **PASS**.

## O que não declaramos validado aqui

- aparência final em Windows 100/125/150/200% DPI;
- Narrator/NVDA completo;
- MSI real nesta máquina;
- multi-monitor Windows com hot-plug;
- render longo 8K/120;
- RIFE/Real-ESRGAN/Demucs no hardware de destino durante esta fase.

Esses pontos ficam no checklist `WINDOWS_UX_ACCEPTANCE.md` e não são substituídos por Xvfb.
