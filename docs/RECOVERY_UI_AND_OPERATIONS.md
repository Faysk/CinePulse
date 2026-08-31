# Especificação — interface e operação da recuperação

**Status:** desenho de produto e operação

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026
**Público:** usuário final, suporte local e mantenedores

## 1. Objetivo de experiência

O usuário deve entender em poucos segundos:

- se existe trabalho preservado;
- em qual fase o job está;
- o que já foi confirmado;
- por que parou;
- qual ação é segura;
- quando o arquivo pode ser usado.

Detalhes técnicos continuam disponíveis, mas não são necessários para uma retomada normal.

## 2. Princípios de UX

1. Resultado antes de mecanismo.
2. Fase sempre visível ao lado do percentual.
3. Parcial nunca recebe linguagem de arquivo final.
4. Pausar, cancelar e descartar não são sinônimos.
5. Erro recuperável termina com uma próxima ação.
6. Nenhuma exclusão acontece como efeito colateral de retomar.
7. Estimativa é intervalo condicionado, não promessa.
8. A interface não oferece ação que viole lease ou integridade.

## 3. Descoberta ao abrir o CinePulse

### Caso recuperável

Card na Central de atividade e item na fila:

> Render interrompido encontrado<br>
> 2.555 de 2.718 segmentos confirmados. Fonte e cache disponíveis. É necessário conferir a integridade antes de continuar.

Ações primárias:

- `Inspecionar`;
- `Retomar com segurança`.

Ações secundárias:

- `Preservar por enquanto`;
- `Abrir histórico técnico`.

### Caso ativo em segundo plano

> Render em andamento<br>
> O worker continua processando. Última confirmação há 18 segundos.

Ações: `Acompanhar`, `Pausar com segurança`.

Não oferecer `Retomar`.

### Caso bloqueado

> Não é seguro continuar<br>
> O volume que contém o cache não está disponível. Nenhum arquivo foi apagado.

Ações: `Reconectar volume`, `Escolher alternativa`, `Ver detalhes`.

## 4. Item da fila

Campos mínimos:

- nome do projeto;
- badge de estado;
- fase atual;
- progresso da fase;
- progresso global;
- última atualização;
- aviso de integridade/armazenamento;
- origem `Recuperado do disco` quando aplicável.

Estados visuais:

| Estado | Cor semântica | Texto curto |
|---|---|---|
| ativo | primária | `Processando` |
| auditoria | informativa | `Conferindo trabalho preservado` |
| reparo | atenção | `Corrigindo segmentos` |
| pausa solicitada | atenção | `Finalizando unidade atual` |
| pausado | neutra | `Pausado com segurança` |
| recuperável | informativa | `Pronto para retomar` |
| bloqueado | perigo | `Ação necessária` |
| verificando | informativa | `Verificando arquivo` |
| completo | sucesso | `Arquivo aprovado` |

Cor nunca é o único indicador.

## 5. Inspector de recuperação

### Resumo

- estado e explicação;
- última unidade confirmada;
- quantidade preservada;
- quantidade que pode ser refeita;
- próxima ação recomendada.

### Etapas

Timeline:

```text
Entrada ✓
Real-ESRGAN ✓
Interpolação 93,99%
Auditoria pendente
Master não iniciado
Entrega não iniciada
Verificação não iniciada
```

### Integridade

- fonte: presente/alterada/ausente;
- cache: presente/descartado/incompatível;
- segmentos: confirmados, rejeitados e em quarentena;
- último gate executado;
- limitações do detector.

### Armazenamento

- volume e tipo físico;
- espaço atual e necessário por próxima fase;
- risco USB/velocidade medida;
- opção de staging em SSD;
- arquivos grandes retidos.

### Tempo

- tempo da fase;
- throughput recente;
- ETA em faixa;
- motivo de não haver ETA quando faltam amostras.

### Detalhe técnico

- job/attempt IDs;
- paths;
- códigos de erro;
- logs e resultados;
- botão para copiar resumo redigido.

## 6. Ações e consequências

### Retomar com segurança

Executa auditoria de identidade/integridade, adquire lease e continua do commit. Não apaga quarentena ou parciais.

### Pausar com segurança

Solicita pausa. Texto durante espera:

> Concluindo a unidade atual para não perder trabalho.

Depois:

> Pausado após o segmento 1.622. Pode fechar o CinePulse.

### Cancelar execução

Encerra subprocessos e marca a tentativa como cancelada. Explica que artefatos recuperáveis permanecem até decisão de limpeza.

### Preservar por enquanto

Remove destaque/alerta da sessão, mas mantém item e dados. Não muda para concluído.

### Migrar para SSD

Mostra origem, destino, bytes, espaço/margem e estimativa. Cópia pode pausar/retomar; origem permanece.

### Descartar dados recuperáveis

Única ação destrutiva. Antes de confirmar, mostrar inventário:

```text
Segmentos: 301,7 GiB
Cache: 139,6 GiB
Parciais rejeitados: 61,6 GiB
Logs/manifesto: 18 MiB (recomendado preservar)
```

Permitir preservar logs/manifests por padrão. Não apagar entrada nem saída final aprovada.

## 7. Fechamento da aplicação

Com worker ativo:

- `Continuar em segundo plano` — fecha UI, mantém worker;
- `Pausar e fechar` — aguarda checkpoint seguro e fecha;
- `Voltar` — não fecha;
- `Cancelar render` fica em ação separada com confirmação.

Se o worker durável não estiver disponível, não oferecer continuar em segundo plano. A UI deve ser honesta e permitir apenas pausar/cancelar.

## 8. Progresso

Exemplo correto:

```text
Interpolação — 93,99%
2.555/2.718 segmentos confirmados
Progresso total do projeto — 71–74%
```

Não mostrar apenas `94%`, pois master, entrega e verificação ainda podem levar horas.

Durante encode:

```text
Codificando entrega — 100%
Fechando contêiner — não desconecte o volume
```

Durante verificação:

```text
Codificação concluída
Contando quadros — 21.766/43.533
O arquivo ainda não recebeu aprovação final
```

## 9. ETA

Mostrar somente quando houver amostras suficientes:

> Estimativa desta fase: 2 h 40 min a 3 h 20 min, baseada nos últimos 30 segmentos. Pode variar com temperatura e disco.

Regras:

- reiniciar amostragem ao mudar de fase/hardware;
- ignorar outliers explicados por pausa;
- ampliar faixa quando throughput oscilar;
- não somar estimativas inexistentes como se fossem zero;
- registrar cálculo no detalhe técnico.

## 10. Mensagens para problemas conhecidos

| Situação | Mensagem simples | Ação |
|---|---|---|
| PNG truncado | `A IA produziu um quadro incompleto. O segmento não foi aceito.` | retry seguro/rota conservadora |
| quadro preto | `Foram encontrados quadros inválidos em segmentos já processados.` | auditar e reparar |
| master curto | `A duração do master não corresponde à contagem de quadros.` | reconstruir timeline |
| MP4 sem trailer | `A codificação percorreu os quadros, mas o arquivo não foi fechado corretamente.` | preservar/reencodar |
| USB lento | `Este volume pode tornar o fechamento do arquivo instável ou muito demorado.` | sugerir SSD |
| falta de espaço | `Faltam X GiB de margem para a próxima etapa.` | migrar/liberar espaço |
| fonte mudou | `O arquivo de entrada não é o mesmo usado neste job.` | reconectar/novo job |
| processo duplicado | `Este render já está sendo processado por outro worker.` | acompanhar |

## 11. Verificação e conclusão

Mostrar checklist:

- contrato de resolução/FPS;
- contagem real de quadros;
- codecs e áudio;
- sincronismo;
- quick verify;
- deep verify, com estado `executado`, `não solicitado` ou `pendente`;
- inspeção perceptiva, quando requerida.

`Arquivo aprovado` só aparece depois da promoção. Se o usuário copiar o parcial antes disso, a interface deve avisar que a verificação ainda não terminou.

## 12. Operação e suporte

### Bundle local

Inclui:

- manifesto redigido;
- últimos eventos/erros;
- RenderPlan/contracts;
- verificação;
- inventário de artefatos sem conteúdo de mídia;
- versões de FFmpeg, GPU driver e modelos.

Não inclui mídia, nomes pessoais, paths completos ou upload automático.

### Rotina de suporte

1. verificar owner ativo;
2. ler manifesto e último evento;
3. conferir identidade/volumes;
4. classificar retryable/blocked;
5. executar auditoria somente leitura;
6. retomar pela aplicação quando disponível;
7. usar runbook técnico apenas se a UI não suportar o caso;
8. preservar evidência de qualquer nova falha.

## 13. Acessibilidade e layout

- navegação por teclado em todas as ações;
- foco inicial na ação recomendada não destrutiva;
- confirmação destrutiva não preselecionada;
- labels além de cor/ícone;
- textos não cortados em 1024×700;
- DPI 100/125/150/200%;
- leitor de tela recebe estado/fase/progresso;
- logs não roubam foco durante atualização.

## 14. Critérios de aceite UX

- usuário identifica corretamente se pode fechar a UI;
- job redescoberto aparece sem configuração manual;
- teste de compreensão diferencia encode 100% de arquivo aprovado;
- pausa informa a última unidade confirmada;
- bloqueio sempre apresenta causa e próxima ação;
- descarte lista bytes e nunca inclui entrada/saída final;
- layout e teclado passam no checklist Windows;
- todas as mensagens P0 possuem teste de apresentação/estado.
