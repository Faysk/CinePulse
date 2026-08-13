# UX Phase 7 — Estados transversais

Status: **concluída no MegaPack**
Base funcional protegida: **CinePulse 1.0.0-rc.5**

## Objetivo

Fazer com que o CinePulse use a mesma linguagem para eventos que atravessam todas as telas: processamento, bloqueio, aviso, sucesso, recuperação, atualização e falha.

Antes desta fase, a informação existia, mas podia aparecer como `status.set`, modal, texto de fila, log ou badge específico de uma aba. Isso obrigava o usuário a reaprender o significado do estado dependendo de onde estava.

A Phase 7 não altera o contrato do pipeline. Ela organiza **como o estado é explicado e qual próxima ação segura é oferecida**.

## Modelo semântico

Foram padronizados cinco níveis:

- `info` — mudança de estado que não exige ação;
- `busy` — trabalho em andamento, sem prometer conclusão;
- `success` — operação concluída e verificada no nível que o fluxo realmente conhece;
- `warning` — fluxo preservado, porém existe algo que merece revisão;
- `error` — bloqueio/falha que impede aquela operação de continuar.

Cor nunca é o único sinal. O strip persistente sempre combina:

- badge textual;
- título;
- explicação;
- ação primária quando existe uma próxima ação segura;
- ação secundária quando detalhe/log é útil.

## Novos módulos

### `ui/feedback_lab.py`

Camada testável sem Tk:

- normalização de severidade;
- metadados semânticos;
- compactação de mensagens técnicas;
- classificação de falhas conhecidas;
- histórico limitado da sessão;
- supressão de duplicatas consecutivas.

A classificação **não apaga o erro bruto**. Mensagens técnicas continuam armazenadas no histórico/log, enquanto a superfície principal mostra uma explicação humana.

### `ui/feedback_view.py`

Camada visual:

- strip global no rodapé;
- estilos light/dark por estado;
- ações contextuais;
- contador de atividade;
- central de atividade com resumo e detalhe técnico.

## Strip global persistente

O antigo texto de status isolado foi substituído por uma superfície contextual sem remover `self.status` do código legado.

Essa decisão é deliberada: dezenas de fluxos já escreviam em `self.status`, então uma reescrita total seria risco desnecessário. Um `trace` converte atualizações legadas em estado informativo e os fluxos críticos usam `_set_feedback` explicitamente.

Resultado:

- o motor não precisou ser reescrito;
- mensagens antigas continuam visíveis;
- estados importantes passam a ter severidade e ação consistente.

## Estados cobertos

### Render / preview

- início → `PROCESSANDO`;
- troca de estágio → atualiza o mesmo estado sem inundar o histórico;
- conclusão → `CONCLUÍDO`, com ação para abrir arquivo e relatório quando existe;
- cancelamento → `ATENÇÃO`, deixando explícito que temporários do job foram removidos;
- falha → `BLOQUEADO`, com explicação humana e causa técnica preservada.

### Falhas conhecidas

A UI reconhece categorias frequentes e aponta uma ação coerente:

- espaço em disco → rever projeto/armazenamento;
- permissão de escrita → rever destino;
- Real-ESRGAN → abrir IA local;
- Demucs → abrir IA local;
- RIFE → rever qualidade/interpolação;
- áudio → rever projeto;
- FFmpeg/etapa de vídeo → rever qualidade.

O texto bruto continua disponível na Central de atividade e no log.

### Pré-verificação

- requisitos básicos ausentes → bloqueio global + destaque na aba Projeto;
- verificando → estado ocupado, sem disparar render;
- armazenamento bloqueante → erro com próxima ação;
- avisos → warning com acesso à Qualidade e saída;
- sem bloqueios → sucesso com atalho para gerar preview.

### Fila

- início da fila → estado ocupado;
- item concluído → registrado sem perder o contexto da fila;
- fila inteira concluída → sucesso;
- fila terminada com erros → warning, não falso sucesso;
- item que estava `Renderizando` após encerramento → volta para `Aguardando` em 0% e gera aviso de recuperação;
- queue JSON ilegível → editor continua disponível e a falha é apresentada como recuperável.

### IA local

- instalação em andamento → busy;
- instalação concluída → success e reverificação do inventário;
- instalação interrompida → error com acesso direto à IA local/log;
- nenhum experimental passa a ser descrito como integrado por causa do novo estado global.

### Atualização

- consulta → busy;
- versão atual → success;
- usuário adia → info;
- pacote baixado/verificado → success;
- falha → error, explicitando que a instalação atual não foi substituída;
- canal sem feed → info em vez de modal de erro.

### Recuperação

- outro processo ativo → warning e nenhuma tentativa concorrente de recuperação;
- parcial válido promovido → success;
- falha ao promover → error e parcial preservado;
- parcial não promovido → warning, sem anunciá-lo como render final.

## Central de atividade

O botão `Atividade (N)` abre um histórico **somente da sessão atual**.

Cada entrada contém:

- horário;
- severidade;
- área;
- título humano;
- explicação;
- detalhe técnico quando diferente da explicação.

O histórico é limitado a 40 itens e evita duplicatas consecutivas. Estágios intermediários de um render não viram dezenas de entradas; eles atualizam o estado corrente. A Central permanece sincronizada enquanto está aberta, possui rolagem independente para lista/detalhe e acompanha a troca entre tema claro e escuro.

## Modais: regra da Phase 7

A fase reduz modais informativos rotineiros, mas **não remove confirmações necessárias**.

Continuam adequados para:

- sobrescrever saída;
- excluir preset;
- limpar fila;
- aceitar download/licença;
- continuar apesar de avisos de preflight;
- cancelar e sair durante processamento;
- decisão de recuperar um parcial válido.

Resultados normais, atualização pronta e instalação concluída passam a preferir feedback persistente em vez de interromper o usuário com `showinfo`.

## Compatibilidade

- `self.status` e `self.stage` continuam existindo;
- `RenderSettings` não foi alterado;
- fila persistida continua compatível;
- testes que constroem `VideoOptimizerStudio` sem Tk via `__new__` continuam suportados;
- nenhuma mudança foi feita em codec, VFX, áudio, RIFE, Real-ESRGAN, Demucs ou AtomicOutput para viabilizar a nova UI.

## Validação específica

Cobertura nova inclui:

- normalização de severidade;
- metadados de estado;
- compactação de detalhe;
- classificação de falhas;
- histórico limitado;
- supressão de duplicatas.

Smoke GUI em 1024×700 cobre:

- info/busy/success/warning/error;
- ações do strip;
- central de atividade e atualização enquanto aberta;
- rolagem independente de lista/detalhe;
- light/dark/light com a Central aberta;
- preflight bloqueado refletido globalmente;
- encerramento limpo.

## Próximo boundary

**Phase 8 — Polish final e Release UX.**

Foco sugerido:

- microcopy e consistência de nomenclatura;
- acessibilidade/teclado/foco;
- densidade em 1024×700 e escalas DPI do Windows;
- estados vazios finais;
- tooltips apenas onde reduzem ambiguidade;
- instalação/primeiro uso;
- revisão visual tela a tela;
- smoke Windows com componentes reais;
- checklist 1.0 estável.
