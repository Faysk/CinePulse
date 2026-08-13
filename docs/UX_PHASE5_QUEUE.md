# UX Phase 5 — Fila de render

Status: **implementado no MegaPack de desenvolvimento**

## Objetivo

Transformar a aba `Fila` de uma tabela operacional em um workspace de execução legível e recuperável, **sem mudar a ordem real de processamento, a persistência do `queue.json`, o preflight por item ou o pipeline de render**.

A fila precisa responder rapidamente a cinco perguntas:

1. quantos projetos ainda faltam;
2. qual item está sendo processado;
3. quanto desse item já avançou;
4. quais itens precisam de atenção;
5. onde estão a saída e o relatório de um item concluído.

## Contrato preservado

O comportamento anterior continua valendo:

- cada item armazena um `RenderSettings` completo e independente;
- a fila é salva em `data/config/queue.json` por escrita temporária + `os.replace`;
- um item que estava `Renderizando` quando o aplicativo encerrou volta como `Aguardando` na próxima abertura;
- cada item passa novamente por validação e preflight imediatamente antes de iniciar;
- saída atômica, journal de render, cancelamento e relatórios continuam pertencendo ao pipeline existente;
- a execução permanece sequencial;
- erros de um item não apagam os demais itens da fila.

A Phase 5 acrescenta metadados de apresentação (`progress` e `stage`) ao JSON. Leitores anteriores ignoram essas chaves; filas antigas sem essas chaves continuam válidas.

## Nova estrutura visual

### Resumo global

A parte superior apresenta quatro indicadores:

- `Na fila`;
- `Em processamento`;
- `Concluídos`;
- `Atenção`.

`Atenção` reúne `Erro`, `Interrompido` e `Cancelado`. Cor é apenas um reforço: o texto do estado continua explícito para não depender de percepção cromática.

### Lista de projetos

A tabela principal mostra apenas informações que ajudam a decidir ordem e estado:

- posição;
- projeto;
- perfil de qualidade;
- progresso;
- estado.

O caminho de saída saiu da tabela principal e foi movido para o inspector do item selecionado. Isso reduz largura desperdiçada e evita truncar justamente o nome do projeto e o estado.

### Inspector do item selecionado

Mostra:

- estado textual;
- nome do projeto;
- resolução, FPS e aspecto;
- estágio atual;
- barra de progresso;
- entrada;
- saída;
- estratégia de processamento;
- VFX;
- último erro ou relatório conhecido.

O progresso usa os mesmos eventos `progress` do render global. Nenhum segundo medidor foi inventado.

## Progresso por item

Enquanto a fila está em execução, os eventos já emitidos pelo worker atualizam:

- barra global do CinePulse;
- `progress` do item ativo em memória;
- coluna `Progresso`;
- barra do inspector quando o item ativo está selecionado.

O progresso não é gravado no disco a cada evento para evitar I/O desnecessário. Ele é persistido nos momentos em que a fila já salva estado. Em caso de encerramento durante render, o item volta para `Aguardando` e o progresso é zerado, porque o render será reiniciado com segurança em vez de fingir continuação parcial.

## Recuperação

Quando `queue.json` contém um item `Renderizando`:

- estado restaurado: `Aguardando`;
- progresso: `0%`;
- estágio: `Recuperado após encerramento`;
- observação: `Recuperado após encerramento; o item será reiniciado com segurança.`

Isso torna a recuperação visível sem alterar a política já existente.

## Reordenar

Setas `↑` e `↓` alteram a posição do item selecionado.

Regras:

- permitido somente com fila parada e nenhum processamento ativo;
- a nova ordem é persistida imediatamente;
- nenhuma mídia é movida ou renomeada;
- itens já concluídos podem permanecer na lista, mas somente `Aguardando` é considerado para a próxima execução.

## Retry controlado

`Tentar novamente` só atua sobre:

- `Erro`;
- `Interrompido`;
- `Cancelado`.

O item volta para:

- `Aguardando`;
- progresso `0%`;
- erro limpo;
- estágio `Reenfileirado manualmente`.

Isso não altera o `RenderSettings` capturado originalmente.

O comportamento histórico de `Iniciar fila` também foi preservado: itens de atenção são reenfileirados automaticamente quando a execução global é iniciada.

## Carregar no editor

O inspector ganhou `Carregar no editor`.

A ação copia para as `StringVar`/`BooleanVar` atuais os parâmetros salvos daquele item:

- arquivos;
- resolução/FPS/aspecto;
- melhoria/interpolação;
- VFX e cor;
- reação musical;
- transição;
- áudio;
- CPU/disco;
- opções de preview.

O item original da fila não é modificado. Isso permite partir de um render antigo para criar uma variação sem destruir a referência enfileirada.

## Saída e relatório

Ações explícitas:

- `Abrir saída`;
- `Abrir relatório`.

Se a saída ainda não existe, o CinePulse tenta abrir a pasta pai quando ela existe. Se não houver relatório, a interface informa isso em vez de falhar silenciosamente.

Duplo clique em um item também tenta abrir sua saída/pasta.

## Limpeza segura

### Limpar concluídos

Remove apenas os itens `Concluído` da lista. Os vídeos finais e relatórios permanecem no disco.

### Limpar fila

Agora pede confirmação e deixa explícito que:

- entradas não serão apagadas;
- renders já concluídos não serão apagados;
- relatórios não serão apagados.

A ação continua bloqueada durante a execução da fila.

## Estado vazio

Fila sem itens mostra uma instrução curta apontando para `Adicionar à fila` no rodapé e informa que a fila é persistida automaticamente.

Não são exibidos números ou caminhos fictícios.

## Arquitetura

Novos arquivos:

- `src/cinepulse/ui/queue_lab.py` — transformação pura de estado em informação de apresentação;
- `src/cinepulse/ui/queue_view.py` — construção Tk da aba;
- `tests/test_queue_lab.py` — estados, progresso, resumo, apresentação e limites de reordenação.

`studio.py` continua dono de execução/persistência, mas deixa de conter o layout detalhado da aba.

## Decisões de UX deliberadas

### Sem pausa falsa

Não foi criada uma ação `Pausar`. O pipeline atual suporta cancelamento seguro, não suspensão/resume real de FFmpeg/IA. Um botão de pausa seria uma promessa técnica falsa.

### Sem ETA global inventada

O inspector usa o ETA global existente somente durante render no rodapé. A fila não soma durações futuras sem benchmark válido por item/hardware.

### Sem paralelismo

A Phase 5 não executa dois renders simultâneos. A fila permanece sequencial para preservar o comportamento, evitar disputa de VRAM/disco e não introduzir uma mudança de produto escondida em um redesign.

## Quality gates

- 50 testes automatizados passando;
- `compileall` sem erro;
- smoke GUI da fila em light/dark;
- smoke com quatro estados representativos: renderizando, aguardando, concluído e erro;
- progresso do item ativo aparece na lista e no inspector;
- retry e reordenação exercitados no smoke;
- `Carregar no editor` exercitado sem alterar o item original;
- rodapé global permanece visível porque a fila passou a usar o mesmo contêiner rolável das telas densas;
- nenhuma dependência nova;
- `RenderSettings` permanece inalterado;
- nenhum arquivo de mídia é apagado pelas ações de limpeza da fila.

## Próxima fase

**Fase 6 — IA local:** separar claramente capacidade integrada, componente instalado, download disponível e módulo experimental, mostrando benefício, licença, validação e estado sem anunciar arquivo presente como recurso funcional quando ele ainda não está integrado ao pipeline.
