# UX Phase 6 — IA local

## Objetivo

Transformar a aba **IA local** de um inventário técnico em um gerenciador de capacidades compreensível, sem alterar o contrato do render nem prometer que um checkpoint baixado já é uma função pronta.

A regra central da fase é simples:

> **arquivo detectado não significa recurso integrado.**

O CinePulse 1.0 possui quatro capacidades integradas ao pipeline atual: **Real-ESRGAN, RIFE, Demucs e VMAF**. Os demais itens do catálogo experimental podem existir no disco, mas continuam fora do render até receberem integração, fallback, testes e validação próprios.

## Problemas da tela anterior

A rc.5 já fazia o trabalho importante de detectar, selecionar e instalar componentes, mas a UX ainda tinha ambiguidades:

- todos os módulos apareciam na mesma tabela com peso visual semelhante;
- `Instalado` podia ser lido como “pronto para usar”, inclusive nos experimentais;
- o benefício real, fallback e impacto de ausência não estavam próximos do estado;
- `Selecionar faltantes` podia incluir experimentais quando o modo avançado estava ligado;
- tamanho e licença só apareciam tarde, na confirmação do download;
- faltava uma forma explícita de reverificar o inventário depois de alterações externas;
- o usuário não conseguia distinguir rapidamente recurso integrado, arquivo experimental e capability faltante;
- o progresso de download ficava concentrado no log/rodapé global.

## Estrutura nova

### 1. Resumo de capacidades

O topo da aba mostra quatro indicadores:

- **No render:** quantidade de módulos integrados realmente detectados;
- **Faltando:** quantos módulos integrados ainda não estão disponíveis;
- **Experimentais:** quantos conjuntos experimentais foram detectados no disco;
- **Seleção:** tamanho aproximado do download atualmente selecionado.

Esses números são derivados do mesmo `ai_suite.inventory()` usado pela aplicação e não de uma lista paralela escondida na interface.

### 2. Aviso de honestidade

A tela mantém permanentemente visível o contrato:

**Instalado ≠ integrado**.

O texto cita explicitamente os quatro motores integrados e os sete experimentais atuais. Assim, a presença de LTX, SAM 2 ou CodeFormer no disco nunca é apresentada como uma função ativa do CinePulse.

### 3. Filtros

A lista pode ser reduzida para:

- **Todos**;
- **No render** — somente capacidades integradas;
- **Experimentais** — somente itens fora do pipeline atual;
- **Faltando** — tudo que ainda não foi detectado.

O filtro não modifica arquivos nem seleção; é somente apresentação.

### 4. Estados reais

Os estados foram reescritos para explicar consequência, não só presença de arquivo.

Exemplos integrados:

- `Pronto no render`;
- `Faltando • necessário para upscale por IA`;
- `Faltando • fallback FFmpeg disponível`;
- `Faltando • stems ficam desativados`;
- `Faltando • medição VMAF indisponível`.

Exemplos experimentais:

- `Experimental • aceite necessário`;
- `Disponível para baixar • não integrado`;
- `Arquivos instalados • fora do render`.

### 5. Inspector por componente

Selecionar um módulo abre um inspector que mostra:

- categoria;
- estado real;
- benefício;
- onde ele é usado no CinePulse;
- o que acontece se estiver ausente;
- tamanho detectado ou download aproximado;
- licença;
- aviso de restrição;
- recomendação de instalação.

O inspector diferencia explicitamente os fallbacks do pipeline:

- **Real-ESRGAN:** obrigatório apenas quando o usuário seleciona o upscale por IA;
- **RIFE:** pode cair para interpolação FFmpeg;
- **Demucs:** VFX continuam funcionando sem stems;
- **VMAF:** render continua sem a medição perceptiva.

## Segurança dos experimentais

O modo experimental agora libera **somente seleção e download**.

Mesmo quando esse modo está ligado:

- `Selecionar necessários` escolhe apenas componentes integrados faltantes;
- `Instalar necessários` instala apenas componentes integrados faltantes;
- experimentais precisam ser escolhidos conscientemente;
- desativar o modo remove experimentais da seleção pendente;
- itens experimentais instalados continuam marcados como `fora do render`;
- licenças não comerciais/restritivas continuam visíveis no inspector.

Isso reduz a chance de um clique em massa iniciar dezenas de gigabytes de checkpoints que não mudam o produto atual.

## Instalação e feedback

A instalação continua usando os mecanismos anteriores e preserva:

- PowerShell/instalador gerenciado para os componentes integrados;
- URLs fixadas e SHA-256 para experimentais;
- staging e troca segura;
- log persistente;
- bloqueio de render enquanto a instalação está ativa.

A Phase 6 adiciona feedback local dentro da aba:

- descrição da atividade atual;
- barra de atividade;
- percentual quando uma linha do instalador informa um percentual explícito.

O percentual é tratado como **progresso da atividade/arquivo atual**, não como porcentagem global ou ETA. Linhas sem percentual mantêm estado indeterminado. Não foi inventada uma estimativa global para múltiplos pacotes.

## Reverificação

O botão **Reverificar** força um novo `ai_suite.inventory()`.

Entre reverificações, a UI reutiliza um snapshot do inventário para evitar executar a detecção do VMAF/FFmpeg toda vez que o usuário apenas troca filtro ou seleção. A instalação concluída força uma reverificação automática.

## Correção de consistência do Demucs

A detecção de instalação do Demucs passou a exigir também `htdemucs_ft.yaml`, exatamente o manifesto que `stem_engine.py` exige para executar o modelo local.

Antes, a tela podia considerar o conjunto encontrado apenas pelos pesos e Python, enquanto o motor de stems ainda recusaria execução sem o YAML. A Phase 6 alinha os dois contratos.

## Arquitetura

Novos arquivos:

- `ui/ai_lab.py` — estados, descrições, filtros, tamanho, seleção e parsing conservador de progresso;
- `ui/ai_view.py` — construção Tk da aba e inspector.

`studio.py` continua dono de:

- seleção em memória;
- worker de instalação;
- eventos da thread;
- mensagens de confirmação;
- integração com o rodapé global.

A instalação e o pipeline de render não foram movidos nem reescritos nesta fase.

## Quality gates executados

- 58 testes automatizados: PASS;
- `compileall`: PASS;
- smoke GUI em 1024×700: PASS;
- filtros Todos / No render / Experimentais: PASS;
- opt-in experimental e remoção da seleção ao desligar: PASS;
- `Selecionar necessários` exclui experimentais mesmo com modo avançado ligado: PASS;
- feedback de percentual local: PASS;
- light/dark: PASS;
- smoke de render básico com vídeo e WAV sintéticos: PASS;
- áudio final permaneceu na música de 880 Hz do fixture: PASS.

## Limites deliberados

Não foram adicionados:

- cancelamento falso de download quando o instalador subjacente não oferece rollback/cancelamento estruturado;
- ETA global de instalação;
- promessa de compatibilidade de hardware para componentes ainda não integrados;
- botão “ativar” para experimental;
- execução de LTX, CodeFormer, SAM, Depth, CoTracker, CLAP ou BasicVSR++ no render.

Esses recursos só devem aparecer quando houver implementação real e validada.
