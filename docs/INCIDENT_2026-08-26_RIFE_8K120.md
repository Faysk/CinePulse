# Pós-mortem — recuperação do render RIFE 8K/120 fps

**Incidente:** interrupção e recuperação do job `20260826-203826-da124c70`

**Período:** 26 a 30 de agosto de 2026

**Documento fechado em:** 31 de agosto de 2026

**Status:** recuperado e verificado

**Severidade operacional:** alta — render longo, centenas de gigabytes de intermediários e ausência de retomada visível na interface
**Escopo deste documento:** fatos observados, causas, correções, resultado e ações futuras

## 1. Resumo executivo

O computador reiniciou durante um render de `nova.mp4` para 8K UHD e 120 fps. Ao reabrir o CinePulse, a fila apareceu vazia, mas o trabalho não estava todo perdido: o cache Real-ESRGAN, os segmentos FFV1 já materializados e o histórico do job continuavam nos discos.

A primeira validação da recuperação encontrou 754 de 2.718 segmentos contíguos. A retomada avançou até 2.555 segmentos, quando uma auditoria de qualidade revelou um defeito mais grave que a interrupção: 6.197 quadros solidamente pretos distribuídos por 990 segmentos. Todos os segmentos afetados foram reconstruídos com RIFE em modo UHD e execução serial, validados e substituídos atomicamente, mantendo os originais em quarentena.

Depois de completar os 2.718 segmentos e 43.533 quadros, a concatenação inicial perdeu aproximadamente 0,918 s por arredondamento acumulado do timebase Matroska de milhares de clipes curtos. A timeline passou a ser derivada da contagem exata de pacotes. Duas tentativas de fechar o MP4 em `G:` falharam no trailer/contêiner. O master de 301,72 GiB foi então copiado de forma reiniciável para o SSD interno `D:`, e a saída final foi codificada e verificada ali.

Resultado aprovado: `nova_otimizado.mp4`, 33.096.031.715 bytes, 7680×4320, 120 fps CFR, 43.533 quadros, HEVC, AAC estéreo/48 kHz, duração de 362,775 s e delta A/V de aproximadamente 0,002 s.

## 2. Impacto percebido

- A interface não mostrou o projeto após a reinicialização e deu a impressão de perda total.
- O processamento original e as retomadas consumiram vários dias.
- Uma parte relevante do trabalho já concluído continha quadros pretos e não poderia ser usada sem reparo.
- A concatenação e a codificação final movimentaram mais de 300 GiB.
- O volume externo `G:` falhou justamente no fechamento do MP4, depois de a codificação percorrer os 43.533 quadros.
- O usuário precisou acompanhar percentuais por arquivos de estado e logs, fora da interface.

Não houve perda confirmada da mídia-fonte, do cache Real-ESRGAN, dos segmentos válidos ou da saída final aprovada.

## 3. Configuração do job

| Campo | Valor observado |
|---|---|
| Entrada | `<source>/nova.mp4` |
| Tamanho da entrada | 1.373.182.226 bytes |
| Modo | melhorar vídeo original, mantendo duração e conteúdo |
| Destino pedido inicialmente | `<external-output>/nova_otimizado.mp4` |
| Destino final aprovado | `<internal-ssd>/nova_otimizado.mp4` |
| Resolução/FPS | 7680×4320 a 120 fps |
| Melhoria | Real-ESRGAN x2 |
| Interpolação | RIFE |
| Scratch | `<scratch>` em HDD USB de alta capacidade |
| Cache preservado | `<data>/cache/ai/<cache-key>.mkv` |
| Diretório dos segmentos | `<scratch>/job_<token>/rife_<token>` |
| Segmentos planejados | 2.718 |
| Quadros-fonte do estágio RIFE | 21.745 |
| Quadros-alvo | 43.533 |
| Versão registrada | 1.0.0-rc.6 |

## 4. Linha do tempo por etapa

### Etapa A — interrupção e descoberta do trabalho preservado

Em 26/08, o PC reiniciou durante o render. A fila reaberta não continha o item porque o estado recuperável do scratch não era redescoberto nem apresentado pela interface.

Em 27/08 às 21:43, a primeira validação técnica confirmou:

- fonte e cache ainda existentes;
- 754 segmentos contíguos e legíveis;
- 6.032/21.745 quadros-fonte já consumidos;
- 12.064/43.533 quadros-alvo materializados, aproximadamente 27,71%;
- possibilidade de continuar a partir do segmento 755.

Decisão: preservar tudo e criar um recuperador reiniciável em vez de executar novamente o render comum pela interface.

### Etapa B — retomadas, pausas e checkpoint

O recuperador passou a tratar cada segmento promovido como unidade de commit:

1. extrair apenas o próximo bloco do cache;
2. gerar os quadros RIFE em diretório temporário;
3. validar os PNGs;
4. codificar um `segment_NNNNN.partial.mkv` em FFV1;
5. validar resolução, FPS, codec e contagem;
6. promover para `segment_NNNNN.mkv`;
7. atualizar `recovery-state.json` atomicamente.

Fechar o Codex ou interromper o processo parava a execução em andamento, mas não invalidava segmentos já confirmados. Uma nova chamada recalculava a sequência contígua e retomava do próximo segmento.

Foi adicionado um arquivo sentinela `STOP_RECOVERY` para pausa cooperativa. A regra operacional permaneceu: nunca iniciar dois recuperadores simultâneos.

### Etapa C — descoberta dos quadros pretos

Quando o job chegou a 2.555 segmentos, ou 40.920 quadros, uma auditoria estrutural encontrou:

| Medida | Resultado |
|---|---:|
| Segmentos auditados | 2.555 |
| Segmentos afetados | 990 |
| Proporção de segmentos afetados | 38,75% |
| Quadros auditados | 40.920 |
| Quadros pretos | 6.197 |
| Proporção de quadros pretos | 15,14% |

O defeito era determinístico: nos segmentos FFV1 8K/yuv420p, o quadro totalmente preto produzia um pacote de tamanho conhecido, posteriormente cruzado com decodificação e `signalstats`. Isso permitiu examinar centenas de gigabytes sem decodificar cada pixel de todos os quadros.

### Etapa D — causa do defeito e o caso crítico do segmento 810

A causa foi a combinação do RIFE NCNN/Vulkan em 8K sem o modo UHD, contagens-alvo não nativas e paralelismo que podia produzir saída incompleta mesmo com retorno zero.

O segmento 810 tornou o problema reproduzível:

- entrada: 8 quadros válidos;
- pedido direto de 17 quadros: 12 quadros pretos;
- tentativa com 32 quadros: quadros pretos e pressão de memória;
- tentativa de 16 quadros em paralelo: PNG truncado apesar do código de saída zero;
- tentativa de 16 quadros com `-u -j 1:1:1`: 16 PNGs íntegros;
- retime temporal uniforme de 16 para 17: 17 quadros válidos e zero quadro preto.

A validação de PNG passou a conferir assinatura e marcador terminal `IEND`; contar nomes de arquivos deixou de ser aceito como prova de sucesso.

### Etapa E — reparo seguro dos 990 segmentos

O reparo adotou a seguinte política:

1. auditar todos os segmentos e listar somente os afetados;
2. reextrair do cache os quadros-fonte correspondentes;
3. executar a interpolação nativa 2× em modo UHD e serial;
4. quando o alvo fosse 17 ou 18, ajustar temporalmente os quadros válidos sem pedir ao RIFE uma razão insegura;
5. gerar um segmento de reparo parcial;
6. conferir pacotes, dimensões, FPS, codec e ausência de preto determinístico;
7. criar hardlink do segmento defeituoso em `black-frame-quarantine`;
8. substituir o segmento ativo por operação atômica;
9. limpar somente temporários filhos conhecidos depois do commit.

Resultado registrado em 29/08 às 10:48: `BLACK_REPAIR_COMPLETE repaired_segments=990`. Os 990 originais permaneceram preservados na quarentena.

### Etapa F — conclusão da interpolação e gate de preto

Após o reparo, o RIFE continuou do último segmento confirmado até:

- 2.718/2.718 segmentos;
- 21.745/21.745 quadros-fonte;
- 43.533/43.533 quadros-alvo;
- progresso de interpolação 100%.

O gate final reexaminou todos os 2.718 segmentos e registrou `BLACK_GATE_OK black_frames=0`. A conclusão do RIFE não foi inferida apenas pelo número de arquivos.

### Etapa G — concatenação e erro acumulado de timeline

A primeira concatenação terminou depois de aproximadamente 9.389 s, mas o master parcial tinha 361,855 s em vez de aproximadamente 362,773 s. O contêiner Matroska representa o tempo desses segmentos curtos com granularidade de milissegundos; arredondar cada um separadamente acumulou quase um segundo ao longo de 2.718 arquivos.

Correção: o manifesto de concatenação passou a declarar a duração de cada segmento como `número_exato_de_pacotes / 120`, preservando a timeline matemática. O master incorreto foi mantido como `recovered_rife_master.partial.mkv`, e uma nova concatenação produziu:

- `<scratch>/job_<token>/recovered_rife_master.mkv`;
- 323.969.923.451 bytes, aproximadamente 301,72 GiB;
- 362,774 s;
- 43.533 quadros.

### Etapa H — falhas ao fechar o MP4 em `G:`

A primeira tentativa longa em `G:` deixou um arquivo de aproximadamente 30,82 GiB sem `moov`; o controlador/processo não concluiu o contêiner. O recuperador aprendeu a inspecionar um parcial órfão antes de decidir entre reutilizar ou preservar como rejeitado.

Também foi corrigido um erro no caminho de progresso: `file:///E:/...` não era aceito pelo FFmpeg Windows para `-progress`; o processo passou a receber um caminho Windows comum.

Uma tentativa posterior alcançou todos os quadros, mas falhou ao escrever o trailer e fechar o arquivo com `Invalid argument`. O arquivo permaneceu preservado para diagnóstico, não foi promovido.

Arquivos rejeitados preservados:

- `<external-output>/.nova_otimizado.recovery-partial.mp4`;
- `<external-output>/.nova_otimizado.recovery-partial.rejected-<timestamp>.mp4`.

Ambos têm 33.094.834.121 bytes e não devem ser tratados como entrega final.

### Etapa I — mudança para SSD interno e remoção de `faststart`

O inventário físico mostrou:

- `B:`: Seagate Expansion Desk USB, usado como scratch de alta capacidade;
- `G:`: SPCC Solid State Disk ligado por USB, destino que falhou no fechamento;
- `D:`: Fanxiang S790 2 TB NVMe interno, com espaço suficiente.

O master foi copiado do HDD USB de scratch para o SSD NVMe interno com cópia reiniciável e não bufferizada. O original permaneceu intacto. A cópia local foi validada por tamanho e duração antes de ser reutilizada como `<internal-ssd>/.nova_otimizado.recovery-master.mkv`.

Para a saída local de mais de 30 GiB, `+faststart` foi removido. Essa opção apenas reposiciona os metadados do MP4 para início mais rápido em streaming progressivo; removê-la não muda os quadros, o áudio ou a qualidade, e evita uma segunda movimentação integral do arquivo no fechamento.

### Etapa J — codificação e verificação final

A codificação final em `D:` levou 11.932 s, aproximadamente 3 h 18 min. A utilização da GPU variou porque o pipeline alternava leitura do master FFV1, escala/crop, alimentação do NVENC, áudio, mux e escrita. GPU abaixo de 100% não significou que o processo estivesse parado; em vários momentos o limitador era I/O ou alimentação do encoder.

Depois da codificação, a verificação levou aproximadamente 2 h 21 min porque contou os quadros reais do fluxo 8K. O estado registra `mode=quick` e `decoded_to_eof=false`: portanto, foi uma verificação de contrato com `ffprobe -count_frames`, não o deep verify separado que decodifica vídeo e áudio com FFmpeg até EOF.

Às 16:23:23 de 30/08, o parcial aprovado foi promovido atomicamente para `<internal-ssd>/nova_otimizado.mp4`.

## 5. Resultado técnico comprovado

| Verificação | Resultado |
|---|---|
| Arquivo final | `<internal-ssd>/nova_otimizado.mp4` |
| Tamanho | 33.096.031.715 bytes, aproximadamente 30,82 GiB |
| Contêiner | MP4 |
| Vídeo | HEVC Main, `hvc1`, `yuv420p`, BT.709 limited |
| Resolução | 7680×4320 |
| Cadência | 120/1 fps, CFR |
| Quadros contados | 43.533/43.533 |
| Duração do vídeo | 362,775 s |
| Áudio | AAC LC, estéreo, 48 kHz |
| Duração do áudio | 362,773 s |
| Delta A/V | aproximadamente 0,002 s |
| Gate de preto dos segmentos | 0 quadros pretos determinísticos |
| Problemas da verificação | nenhum |
| Job | `status=success`, `recovered=true` |

### Limite da conclusão de qualidade

Os gates comprovam integridade estrutural, ausência do defeito preto conhecido, cadência, dimensões, codecs, contagem e sincronismo. Eles não substituem uma inspeção perceptiva humana completa de cada quadro nem provam que toda interpolação é artisticamente perfeita em oclusões e movimentos extremos.

## 6. O parcial publicado durante a verificação

Durante a verificação, o arquivo em `D:` já estava totalmente codificado; a etapa era somente leitura. O probe registrado aponta para `.nova_otimizado.recovery-partial.mp4`, com o mesmo tamanho do arquivo final, e a promoção usa `os.replace`, sem recodificação.

Assim, a cópia feita enquanto a verificação estava em cerca de 50% veio do mesmo conteúdo que depois recebeu o nome final. Não foi registrado um hash da cópia publicada naquele instante, então a identidade com essa cópia externa não pode ser provada retroativamente por dois hashes; o fluxo e o tamanho demonstram que não houve uma segunda codificação entre a cópia e a promoção.

## 7. Causas-raiz

### Causa primária da sensação de perda

O estado recuperável existia em scratch/histórico, mas a fila da interface não o redescobria. Persistência de artefatos e persistência de UX eram capacidades diferentes.

### Causa dos quadros pretos

Invocação RIFE inadequada para 8K e contagens não nativas, sem validação de conteúdo e integridade de PNG antes do commit.

### Causa da duração incorreta do master

Arredondamento do timebase de milhares de segmentos curtos durante a concatenação sem durações explícitas derivadas dos pacotes.

### Causa das falhas finais em `G:`

O fechamento de um MP4 de aproximadamente 31 GiB, especialmente com `faststart`, exigiu operações pesadas no volume USB. O sistema chegou ao fim dos quadros, mas não conseguiu fechar o trailer de forma válida. O log sustenta o gargalo/falha de I/O e contêiner; ele não prova um defeito físico permanente do dispositivo.

## 8. O que funcionou

- cache e segmentos permaneceram após reinicializações e pausas;
- commits por segmento permitiram retomada real;
- validação antes da mutação evitou recomeçar cegamente;
- quarentena por hardlink preservou os defeitos para auditoria sem duplicar imediatamente centenas de gigabytes;
- substituição atômica evitou expor segmento reparado pela metade;
- gate de quadros pretos impediu a concatenação silenciosa de material defeituoso;
- timeline por pacote corrigiu a duração sem reinterpolar;
- master e parciais suspeitos foram preservados;
- staging para SSD interno resolveu o fechamento final;
- a promoção final só ocorreu depois do contrato técnico passar.

## 9. O que precisa melhorar

| Prioridade | Ação | Estado |
|---|---|---|
| P0 | Redescobrir jobs interrompidos ao iniciar a interface | aberto |
| P0 | Exibir “Retomar do checkpoint” com segmento, fase, integridade e espaço | aberto |
| P0 | Aplicar validação de PNG e gate de preto no pipeline RIFE normal | ferramenta de recuperação pronta; integração normal aberta |
| P0 | Usar modo UHD/serial seguro automaticamente para 8K | ferramenta de recuperação pronta; política normal aberta |
| P1 | Persistir progresso de cada fase fora do processo da UI | parcial |
| P1 | Fazer preflight físico do volume de destino para arquivos grandes | aberto |
| P1 | Evitar `faststart` local em saídas muito grandes ou torná-lo opção de entrega | implementado no recuperador; integração normal aberta |
| P1 | Mostrar separadamente interpolação, concatenação, encode e verificação | aberto |
| P1 | Oferecer pausa cooperativa pela interface | sentinela técnica pronta; UI aberta |
| P2 | Estimar ETA por fase a partir de amostras recentes, com intervalo de confiança | aberto |
| P2 | Gerar bundle de incidente redigido e indexado | aberto |

Os critérios completos estão em [Desenho de render reiniciável](RESUMABLE_RENDERING_DESIGN.md).

## 10. Retenção e limpeza

Nenhum artefato de recuperação deve ser apagado automaticamente por esta documentação. Depois de o usuário aceitar visualmente o resultado e manter pelo menos uma cópia verificada da saída final, a limpeza pode ser planejada nesta ordem:

1. registrar hash da saída final e da cópia de backup;
2. confirmar reprodução e duração fora do CinePulse;
3. preservar `job.json`, `recovery-state.json`, `recovery-result.json` e logs;
4. decidir explicitamente sobre os dois parciais inválidos de `G:`;
5. decidir sobre o master duplicado de `D:` e `B:`;
6. remover quarentena, segmentos e cache somente com autorização explícita.

O cache de 139,65 GiB, os masters de 301,72 GiB e os segmentos não são backup da entrada. A entrada original continua sendo a fonte de verdade.
