# Auditoria técnica completa do CinePulse

**Data:** 13 de agosto de 2026
**Versão auditada:** `1.0.0-rc.5`
**Commit auditado:** `0042891`
**Branch:** `main`, sincronizada com `origin/main` no momento da auditoria
**Escopo:** código-fonte, pipeline audiovisual, IA local, GPU/CPU, armazenamento, UX, fila, presets, instalação, atualização, segurança, testes, documentação e preparação para release.

## 1. Resumo executivo

O CinePulse já possui uma base funcional relevante: render atômico, recuperação de saída, cancelamento da árvore de processos, fila persistente, presets, preview, VFX reativos, integração com Real-ESRGAN, RIFE, Demucs e VMAF, instalação portátil, MSI, downloads verificados e documentação inicial.

Entretanto, a versão auditada ainda não deve ser tratada como `1.0 estável` nem como garantia de qualidade excepcional em toda a matriz anunciada de 720p a 12K e 24 a 480 fps.

O principal problema não é a ausência de mais recursos ou modelos de IA. O problema central é que o pipeline pode reduzir silenciosamente resolução, profundidade de cor e cadência temporal antes de criar uma saída rotulada como 4K/8K/120 fps. Também existem divergências entre as opções apresentadas na interface e o processamento realmente executado.

Os principais bloqueadores são:

1. o modo musical cria um master intermediário de 720p ou 1440p e 60 fps;
2. uma fonte 120 fps pode ser reduzida a 60 fps e posteriormente interpolada de volta a 120 fps;
3. os VFX são gerados internamente em 320×180 e 60 fps;
4. o Real-ESRGAN sempre aplica x2 à fonte completa, mesmo quando o destino é menor;
5. a pré-verificação não representa o plano real de processamento;
6. “Sem melhoria” e “Lanczos” não possuem comportamentos efetivamente distintos;
7. intermediários de 8 bits podem destruir informação de fontes 10-bit/HDR;
8. formatos e combinações de resolução/FPS são aceitos sem compatibilidade real do codec;
9. MSI e modo portátil estão misturados pelo launcher;
10. os testes de integração não fazem parte do portão automático de release.

### Conclusão executiva

O projeto é promissor e possui bons fundamentos de segurança operacional, mas precisa de uma etapa de consolidação técnica antes de receber novas IAs ou ser promovido para `1.0 estável`.

A prioridade recomendada é construir um planejador de renderização explícito, preservar a qualidade da fonte, tornar IA e interpolação dependentes do destino real e derivar a pré-verificação desse mesmo plano.

## 2. Metodologia e limites da auditoria

Foram revisados:

- estado do Git, versão, branch e publicação;
- estrutura e responsabilidades dos módulos;
- construção dos comandos FFmpeg;
- fluxo de Real-ESRGAN, RIFE, Demucs e VFX;
- estimativas de saída e temporários;
- processamento de cor, HDR, profundidade de bits e áudio;
- contêineres e codecs aceitos;
- fila, presets, preview, logs e recuperação;
- MSI, pacote portátil, bootstrap e atualização;
- hashes, extração de arquivos, higiene do repositório e privacidade;
- testes unitários, scripts de integração, CI e documentação.

Foram executadas apenas validações automatizadas leves:

- `scripts/Test-Release.ps1`;
- compilação dos módulos Python;
- parsing dos scripts PowerShell;
- 27 testes unitários;
- verificação de higiene do repositório.

Não foram executados nesta auditoria:

- render musical longo;
- render real 8K/120 fps;
- processamento completo com dezenas de milhares de quadros de IA;
- instalação/desinstalação real do MSI;
- comparação artística de VFX;
- benchmark de tempo, VRAM ou qualidade perceptiva em mídia real do usuário.

Assim, sucesso de código e testes leves não deve ser interpretado como comprovação de qualidade visual em render real.

## 3. Pontos fortes confirmados

### 3.1 Segurança da saída

- A saída final é criada como arquivo parcial e promovida de forma atômica.
- Um arquivo existente só é substituído depois que a nova saída existe.
- Existe backup temporário e rollback em caso de falha.
- O cancelamento preserva o arquivo anterior.

Referências:

- `src/cinepulse/safe_output.py`
- `src/cinepulse/process_control.py`

### 3.2 Segurança de componentes

- Downloads principais possuem versões e SHA-256 fixados.
- Componentes são preparados em staging antes da promoção.
- Arquivos ZIP gerenciados pelo Python possuem proteção contra travessia de diretórios.
- Modelos e binários grandes não são rastreados pelo Git.
- Componentes experimentais permanecem separados do pipeline principal.

Referências:

- `src/cinepulse/component_manager.py`
- `src/cinepulse/experimental_components.py`
- `installer/bootstrap-manifest.json`
- `installer/experimental-components.json`

### 3.3 Privacidade

- O funcionamento principal é local.
- Não há telemetria padrão.
- Diagnósticos evitam enumerar mídias do usuário.
- O repositório não contém credenciais detectáveis ou mídias pessoais rastreadas.

### 3.4 Funcionalidades já estruturadas

- loop musical;
- remoção do áudio original do vídeo no modo musical;
- formatos horizontal, vertical, IMAX e Cinema Wide;
- preview e comparação lado a lado;
- fila e presets persistentes;
- normalização de loudness em duas passagens;
- VFX guiados por frequências e opcionalmente por stems;
- Real-ESRGAN, RIFE, Demucs e VMAF integrados;
- diagnóstico e relatório final;
- cancelamento e recuperação após interrupção.

## 4. Escala de prioridade

| Prioridade | Significado |
|---|---|
| P0 | Bloqueia a promessa central de qualidade, confiabilidade ou release estável. |
| P1 | Deve ser corrigido logo após os bloqueadores; afeta desempenho, segurança ou consistência. |
| P2 | Melhoria importante de UX, manutenção e operação. |
| P3 | Evolução futura, após a base principal estar estabilizada. |

## 5. Achados P0 — bloqueadores

### CP-001 — Redução silenciosa de resolução e FPS no master musical

**Evidência:** `src/cinepulse/studio.py`, aproximadamente linhas 1920–2008.

No modo musical, `needs_master` é sempre verdadeiro. O pipeline cria um intermediário com uma das seguintes dimensões:

- 1280×720 ou 720×1280 sem Real-ESRGAN;
- 2560×1440 ou 1440×2560 com Real-ESRGAN;
- sempre em 60 fps.

Depois esse master é ampliado para a resolução escolhida. Se a saída for 8K/120, o resultado pode conter apenas detalhe espacial equivalente ao master 720p/1440p e movimento baseado em 60 fps.

**Impacto:** crítico. A configuração exibida ao usuário não representa a qualidade interna efetiva.

**Correção recomendada:**

- calcular a resolução de trabalho a partir da fonte, destino, VFX e hardware;
- não reduzir uma fonte que já atende ao destino;
- preservar os FPS originais sempre que eles forem iguais ou superiores ao destino;
- utilizar resolução reduzida apenas no preview rápido;
- registrar explicitamente no plano qualquer redução intencional.

**Critério de aceite:** uma fonte 7680×4320/120 destinada a 1920×1080/120 não deve passar por um master 60 fps, nem chamar RIFE, nem aplicar upscale.

### CP-002 — Fonte 120 fps é reduzida a 60 e interpolada de volta

**Evidência:** `src/cinepulse/studio.py`, aproximadamente linhas 1945, 2001 e 2003–2012.

O master musical é convertido para 60 fps. Quando RIFE está selecionado e o destino é 120 fps, o pipeline interpola o master de 60 para 120, mesmo que a fonte original já fosse 120 fps.

**Impacto:** perda de metade dos quadros temporais originais, criação artificial de quadros e custo adicional de processamento e armazenamento.

**Correção recomendada:** preservar a cadência original durante todas as etapas e somente interpolar quando `target_fps > effective_source_fps`.

**Critério de aceite:** fonte e destino 120 fps devem produzir zero chamadas ao RIFE e zero chamadas ao `minterpolate`.

### CP-003 — VFX gerados em 320×180/60 fps

**Evidência:** `src/cinepulse/vfx.py`, constantes `EFFECT_WIDTH`, `EFFECT_HEIGHT` e `EFFECT_FPS`.

Todos os VFX são desenhados em 320×180/60 e ampliados para a resolução intermediária.

**Impacto:** serrilhado, partículas borradas, gradientes com banding, espectros pouco definidos e ausência de resposta visual verdadeiramente nativa em 120 fps.

**Correção recomendada:**

- renderização vetorial ou por shader;
- resolução de VFX dependente do destino;
- supersampling para formas finas;
- geração real na cadência de saída ou composição temporal analítica.

**Critério de aceite:** comparação em zoom de 100% deve demonstrar bordas e partículas sem pixelização em 4K e 8K.

### CP-004 — Real-ESRGAN sempre aplica x2 à fonte inteira

**Evidência:** `src/cinepulse/studio.py`, função `_enhance_clip_ai`.

O CinePulse extrai todos os quadros da fonte em PNG, executa `realesr-animevideov3` com escala x2 e só depois redimensiona para o master.

Uma fonte 8K pode gerar quadros temporários 16K mesmo quando o destino final é 1080×1920.

**Impacto:** uso potencial de terabytes, tempo extremamente alto, risco de falta de espaço e processamento sem benefício visual.

**Correção recomendada:**

- criar uma decisão target-aware;
- ignorar upscale quando o destino for menor;
- separar restauração de ampliação;
- selecionar escala e modelo pelo conteúdo;
- processar quadros em lotes com limite de armazenamento;
- excluir cada lote após sua codificação;
- evitar o modelo de anime para conteúdo fotográfico.

**Critério de aceite:** fonte 8K destinada a 1080p não deve criar nenhum quadro 16K.

### CP-005 — Pré-verificação não representa o pipeline real

**Evidência:** `src/cinepulse/studio.py`, função `_preflight_report`.

A estimativa de IA utiliza:

```text
largura_da_fonte × altura_da_fonte × quantidade_de_quadros × 10 bytes
```

Ela não deriva o consumo das etapas efetivamente planejadas e não considera corretamente:

- cache de IA já válido;
- masters H.264;
- transições;
- VFX;
- entrada e saída do RIFE;
- arquivos mantidos simultaneamente;
- saída CRF em CPU;
- resolução intermediária real;
- arquivos de stems;
- diferenças por conteúdo na compressão PNG.

**Impacto:** pode bloquear trabalhos viáveis e, em outras combinações, subestimar o pico real.

**Correção recomendada:** introduzir um objeto `RenderPlan` puro, contendo cada etapa, duração, resolução, FPS, codec, cache, temporários, espaço persistente e pico simultâneo.

**Critério de aceite:** erro máximo recomendado de ±20% no pico temporário e ±15% no tamanho final em uma matriz controlada de testes.

### CP-006 — “Sem melhoria” e “Lanczos” não são opções distintas

**Evidência:** somente `ENHANCE_AI` cria uma ramificação própria em `src/cinepulse/studio.py`.

“Sem melhoria — preservar a fonte” e “Upscale simples — Lanczos” terminam no mesmo redimensionamento Lanczos final.

**Impacto:** comportamento enganoso e ausência de controle real sobre preservação da fonte.

**Correção recomendada:**

- **Preservar:** impedir upscale e interpolação desnecessários; usar stream copy quando tecnicamente possível;
- **Lanczos:** executar redimensionamento espacial explícito;
- **IA:** executar apenas quando o plano demonstrar ganho ou quando o usuário solicitar restauração.

**Critério de aceite:** testes devem demonstrar comandos e resultados diferentes para as três opções.

### CP-007 — Perda de 10-bit e conversão HDR incorreta

**Evidência:** intermediários em `yuv420p` em `src/cinepulse/studio.py` e `src/cinepulse/vfx.py`.

O master H.264, transições e VFX trabalham em 8 bits. A saída final pode ser codificada em `p010le`, mas isso apenas coloca dados já reduzidos em um contêiner de 10 bits.

Além disso, `setparams` apenas declara metadados; não realiza transformação real de HDR/BT.2020 para SDR/BT.709.

**Impacto:** banding, alteração de cores, luzes estouradas, pretos incorretos e falsa preservação de HDR.

**Correção recomendada:**

- intermediários 10-bit;
- `zscale`, tone mapping e conversão de gamut explícitos;
- dithering ao reduzir profundidade;
- bloquear IA atual sobre HDR ou implementar fluxo HDR consciente;
- validar faixa completa versus limitada;
- não rotular como HDR um resultado que passou por IA/VFX SDR.

**Critério de aceite:** padrões HDR e gradientes 10-bit devem manter metadados, luminância e ausência de banding dentro de limites definidos.

### CP-008 — Formatos aceitos não correspondem ao encoder

**Evidência:** `src/cinepulse/preflight.py` aceita MP4, MKV, MOV e WebM; `src/cinepulse/studio.py` sempre usa HEVC + AAC no final.

WebM não suporta essa combinação. A função `audio_codec_for_container` existe, mas não é usada pelo pipeline final.

**Impacto:** projetos aceitos pela validação podem falhar somente no final do processamento.

**Correção recomendada:** criar uma matriz contêiner/codec:

| Contêiner | Vídeo recomendado | Áudio recomendado |
|---|---|---|
| MP4 | HEVC, H.264 ou AV1 compatível | AAC |
| MOV | HEVC/H.264/ProRes | AAC ou PCM |
| MKV | HEVC, AV1, H.264 ou FFV1 | AAC, FLAC ou PCM |
| WebM | AV1 ou VP9 | Opus |

**Critério de aceite:** toda extensão aceita deve produzir um arquivo reproduzível e válido.

### CP-009 — 12K e 240/480 fps não possuem validação real de codec

O CinePulse oferece essas opções, mas não bloqueia combinações incompatíveis com HEVC, NVENC, nível do codec, sample rate do perfil ou plataforma de destino.

**Impacto:** promessa que pode ser tecnicamente impossível, falha tardia e consumo excessivo de recursos.

**Correção recomendada:**

- consultar capacidades reais do encoder;
- bloquear combinações impossíveis;
- apresentar 12K/240/480 como experimental;
- permitir somente perfis comprovados por hardware e codec;
- registrar compatibilidade esperada com YouTube e players.

### CP-010 — MSI e portátil utilizam o mesmo comportamento

**Evidência:**

- `installer/wix/Product.wxs` exclui `.cinepulse-portable`;
- `installer/Start-CinePulse.ps1` recria o marcador quando `-NonPortable` não é passado;
- os atalhos do MSI chamam `CinePulse.cmd` sem distinguir o modo instalado.

**Impacto:**

- instalação MSI passa a se comportar como portátil;
- atualizador pode sobrescrever arquivos gerenciados pelo MSI;
- reparo e desinstalação ficam inconsistentes;
- componentes baixados podem permanecer órfãos;
- dados e cache podem ficar no local errado.

A versão do pacote MSI também está fixa em `1.0.0`, independentemente do RC.

**Correção recomendada:**

- launcher MSI próprio com `-NonPortable`;
- versão MSI derivada automaticamente da release;
- política de upgrade testada entre RCs e versão estável;
- atualização MSI por novo pacote MSI, sem sobrescrita portátil;
- opção de preservar ou remover componentes e dados na desinstalação.

**Critério de aceite:** instalar RC anterior, atualizar para RC seguinte, reparar e desinstalar sem sobras inesperadas nem perda de dados escolhidos para preservação.

## 6. Achados P1 — alta prioridade

### CP-011 — Muitas gerações de compressão com perdas

Um trabalho pode atravessar IA, master, transição, VFX, RIFE e saída final. Cada intermediário H.264 representa nova compressão.

**Recomendação:** reduzir etapas, usar pipes/filter graphs e adotar intermediários lossless ou visualmente lossless em 10-bit.

### CP-012 — RIFE também utiliza diretórios completos de PNG

O RIFE extrai todos os quadros do trecho e mantém entrada e saída simultaneamente até a montagem final.

**Recomendação:** processamento em blocos, frame server ou integração que não dependa de materializar o vídeo inteiro em PNG.

### CP-013 — Preview pode reagir diferente do render final

A análise de frequência e percentis é calculada somente sobre a duração do preview. A mesma posição pode ter intensidade diferente no vídeo final, que é normalizado usando a música inteira.

**Recomendação:** analisar e armazenar o envelope completo uma vez; preview e final devem consumir a mesma análise temporal.

### CP-014 — Verificação final é insuficiente

A função `_verify_output` confere resolução, FPS médio e duração. Ela não confirma:

- presença e codec do áudio esperado;
- canais e sample rate;
- sincronização A/V;
- número exato de quadros;
- cadência constante;
- decodificação até o fim;
- ausência de corrupção no final do arquivo.

**Recomendação:** adicionar verificação rápida e opção de verificação profunda com decodificação completa.

### CP-015 — WAV de entrada não significa áudio final lossless

O áudio final é sempre AAC 384 kb/s e 48 kHz. Isso é adequado para YouTube, mas não para um master de arquivo.

**Recomendação:** oferecer perfis separados:

- YouTube AAC;
- master PCM 24-bit;
- FLAC em MKV;
- preservar canais e sample rate quando compatível.

### CP-016 — “GPU automática” não significa processamento inteiro na GPU

Real-ESRGAN, RIFE, Demucs e NVENC podem utilizar a GPU dedicada, mas geração de VFX em NumPy, análise musical e vários filtros FFmpeg continuam na CPU.

**Recomendação:** mostrar por etapa o dispositivo usado e migrar somente os gargalos comprovados para CUDA/shaders.

### CP-017 — Instalador interno força Windows PowerShell antigo

O botão da interface chama `powershell.exe`, enquanto os launchers externos procuram PowerShell 7.

**Recomendação:** centralizar a descoberta do PowerShell e reutilizar o mesmo launcher em todos os caminhos.

### CP-018 — Pacote portátil pode depender do Python do sistema

O bootstrap prefere `py` ou `python` quando disponíveis. Um ambiente virtual criado dessa forma pode parar de funcionar se o Python base for removido ou atualizado.

**Recomendação:** o pacote portátil deve sempre usar o Python gerenciado e fixado. O Python do sistema pode ser uma opção de desenvolvimento, não o padrão de distribuição.

### CP-019 — Canal de atualização possui hash, mas não assinatura

HTTPS e SHA-256 protegem contra corrupção. Não protegem contra comprometimento da conta ou release que hospeda simultaneamente manifesto e arquivo.

**Recomendação:** assinatura Ed25519/Minisign do manifesto e Authenticode nos executáveis/MSI quando houver certificado.

### CP-020 — Dependências não são totalmente reproduzíveis

O lock principal contém apenas NumPy. PyTorch, Demucs, SoundFile e dependências transitivas não possuem lock completo com hashes de wheels.

**Recomendação:** gerar locks por Python/plataforma, incluir hashes, produzir SBOM e registrar licenças efetivamente instaladas.

### CP-021 — Cache sem política automática de limite

O cache de IA pode crescer indefinidamente até o usuário limpá-lo manualmente.

**Recomendação:** quota configurável, política LRU, previsão de crescimento e proteção da reserva mínima do disco.

### CP-022 — Pasta de temporários não é configurável pela interface

**Recomendação:** permitir escolher SSD de scratch e exibir velocidade, espaço, volume e uso estimado. Um trabalho deve poder separar saída e temporários.

### CP-023 — Não há log persistente por render

O botão “Ver log” usa apenas dados em memória. Após fechar o aplicativo, o histórico técnico do render é perdido.

**Recomendação:** criar log por `job_id`, com comandos, decisões, tempos, dispositivos, versões e erros, redigindo caminhos quando exportado para suporte.

## 7. Achados P2 — UX, operação e manutenção

### CP-024 — Contraste incorreto no modo escuro

O resumo e o tempo usam cores fixas escuras, ficando quase invisíveis no tema escuro.

**Recomendação:** estilos sem cores inline e teste automático de contraste.

### CP-025 — Preferências visuais não persistem

Modo escuro, geometria da janela e últimas pastas são perdidos ao reiniciar.

### CP-026 — Pré-verificação precisa de apresentação por etapas

Em vez de um bloco de texto, mostrar:

| Etapa | Entrada | Saída | Dispositivo | Temporário | Motivo |
|---|---|---|---|---:|---|
| Upscale IA | ignorado | — | — | 0 GB | destino menor que a fonte |
| VFX | 8K/120 | 8K/120 | CPU/GPU | estimativa | efeitos selecionados |
| RIFE | ignorado | — | — | 0 GB | FPS já atendido |

### CP-027 — Preview precisa de seleção temporal

Adicionar:

- início;
- posição manual;
- pico/refrão detectado;
- ponto de emenda;
- trecho aleatório reproduzível.

### CP-028 — Fila precisa de mais controles

- editar;
- duplicar;
- reordenar;
- tentar novamente;
- limpar concluídos;
- abrir saída/relatório;
- pausar somente quando houver checkpoints reais.

### CP-029 — Presets e fila não possuem schema de migração

Arquivos JSON devem incluir versão, validação, backup e migração entre releases.

### CP-030 — Segunda instância não é efetivamente bloqueada

O diário detecta outro PID, mas a interface da segunda instância continua capaz de iniciar novo trabalho.

**Recomendação:** mutex por usuário ou bloqueio de render com tomada atômica e opção somente leitura.

### CP-031 — Branding do Windows está incompleto

Adicionar `.ico` à janela, atalhos, MSI, Apps e Recursos e diálogos.

### CP-032 — `studio.py` concentra responsabilidades demais

O arquivo possui aproximadamente 3.000 linhas e mistura UI, render, fila, presets, instalação, atualização, cache e relatórios.

**Recomendação de módulos:**

- `render_plan.py`;
- `pipeline.py`;
- `encoders.py`;
- `storage_estimator.py`;
- `ui/`;
- `queue_store.py`;
- `preset_store.py`;
- `quality_validation.py`;
- `audio_pipeline.py`;
- `color_pipeline.py`.

### CP-033 — Pipeline clássico duplicado

`loop_engine.py` mantém uma interface antiga extensa, enquanto `studio.py` é a entrada principal e importa apenas utilitários de mídia.

**Recomendação:** extrair os utilitários comuns e aposentar ou isolar claramente o fluxo legado.

## 8. Achados P3 — evolução futura

Estas melhorias são relevantes, mas não devem anteceder a correção do pipeline principal:

- waveform e timeline musical;
- marcação de seções, batidas, refrões e emendas;
- comparação A/B com zoom de 100%, alternância e diferença;
- VFX por shaders e composição GPU;
- arquitetura de plugins para VFX e modelos;
- perfis de entrega para YouTube, Shorts, arquivo e master;
- benchmark comunitário por GPU;
- relatório de consumo energético, tempo e pico de VRAM;
- suporte a AV1 e intermediários profissionais;
- restauração temporal com BasicVSR++;
- profundidade, segmentação e tracking somente após integração real;
- CLAP para direção musical somente com ganho artístico comprovado;
- acessibilidade, atalhos de teclado e futura internacionalização;
- crash report local exportável e opt-in para suporte.

## 9. Auditoria de testes e CI

### Resultado atual

- 27 testes unitários aprovados;
- release gate aprovado;
- compilação Python aprovada;
- PowerShell aprovado;
- higiene do repositório aprovada.

### Lacunas

Os arquivos abaixo não correspondem ao padrão padrão `test*.py` e não são executados pelo comando atual:

- `tests/integration_smoke.py`;
- `tests/integration_hdr.py`;
- `tests/integration_cancel.py`.

O GitHub Actions também não executa:

- Ruff;
- análise de tipos;
- cobertura;
- integração CPU básica;
- build portátil;
- build/validação MSI;
- teste do atualizador;
- matriz de Python suportada;
- auditoria de dependências;
- SBOM.

### Testes obrigatórios recomendados

1. fonte 8K/120 → 1080p/120 sem IA e sem RIFE;
2. fonte 720p/24 → 4K/60 com IA e interpolação;
3. preview e render final usando o mesmo envelope musical;
4. HDR sem VFX preservado;
5. HDR com VFX convertido corretamente para SDR;
6. saída MP4, MKV, MOV e WebM com codecs compatíveis;
7. áudio AAC, PCM e FLAC;
8. cancelamento em cada etapa;
9. falta de espaço durante lote de IA;
10. cache hit e cache miss;
11. duas instâncias simultâneas;
12. upgrade MSI entre versões;
13. atualização portátil e rollback;
14. fila restaurada após encerramento;
15. decodificação completa da saída final.

## 10. Arquitetura recomendada: RenderPlan

O `RenderPlan` deve ser a fonte única de verdade usada por:

- pré-verificação;
- interface;
- render;
- barra de progresso;
- log;
- relatório final;
- testes.

Exemplo conceitual:

```text
Projeto
  Fonte: 7680×4320, 120 fps, SDR 10-bit
  Destino: 1080×1920, 120 fps, HEVC 10-bit

Plano
  1. Análise do loop             CPU       cacheável
  2. Real-ESRGAN                 IGNORADO  destino menor que a fonte
  3. RIFE                        IGNORADO  fonte já possui 120 fps
  4. Enquadramento 9:16          GPU/CPU   1080×1920/120
  5. VFX                         GPU       1080×1920/120
  6. Áudio                       CPU       AAC 384k ou PCM selecionado
  7. Codificação final           NVENC     HEVC Main10
  8. Verificação                 CPU       decode + A/V sync
```

Cada etapa deve declarar:

- motivo;
- dependências;
- resolução e FPS de entrada/saída;
- formato de pixel;
- dispositivo;
- duração;
- possibilidade de cache;
- tamanho persistente;
- temporário de pico;
- peso no progresso;
- estratégia de cancelamento;
- artefatos produzidos.

## 11. Roadmap recomendado

### Fase 1 — Correção da promessa central

- implementar `RenderPlan`;
- corrigir preservação de resolução e FPS;
- distinguir preservar, Lanczos e IA;
- impedir IA/RIFE desnecessários;
- bloquear combinações impossíveis.

**Saída da fase:** o comando executado corresponde ao que a interface informa.

### Fase 2 — Qualidade e armazenamento

- processamento em blocos para IA e RIFE;
- intermediários 10-bit/lossless;
- VFX escaláveis;
- estimativa por etapa;
- scratch disk e cache LRU.

**Saída da fase:** nenhum trabalho exige materializar o projeto inteiro em PNG.

### Fase 3 — Cor, áudio e formatos

- color management real;
- HDR/SDR explícito;
- codecs por contêiner;
- áudio AAC/PCM/FLAC;
- validação profunda.

**Saída da fase:** cada perfil de entrega possui especificação e teste próprios.

### Fase 4 — Distribuição confiável

- separar MSI e portátil;
- corrigir versão e upgrade MSI;
- Python gerenciado obrigatório no portátil;
- atualização assinada;
- lock completo e SBOM;
- desinstalação previsível.

**Saída da fase:** instalar, atualizar, reparar e remover funcionam de forma reproduzível.

### Fase 5 — UX e operação

- pré-verificação em tabela;
- timeline de preview;
- logs persistentes;
- fila aprimorada;
- tema acessível;
- persistência de preferências.

### Fase 6 — Novas IAs e VFX avançados

Somente depois das fases anteriores:

- BasicVSR++;
- CLAP;
- Depth Anything;
- SAM 2;
- CoTracker;
- CodeFormer;
- geração opcional por LTX;
- shaders e plugins.

## 12. Portões de aceite para 1.0 estável

A versão deve ser promovida para estável somente quando todos os itens abaixo forem comprovados:

- [ ] fonte 120 fps não perde quadros antes da saída 120 fps;
- [ ] fonte maior que o destino não recebe upscale desnecessário;
- [ ] “Preservar”, “Lanczos” e “IA” produzem planos diferentes;
- [ ] VFX não dependem de um canvas fixo 320×180 para saída final;
- [ ] estimativa de temporários fica dentro da tolerância definida;
- [ ] falta de espaço interrompe antes do render, não no meio;
- [ ] HDR, SDR, 8-bit, 10-bit, faixa completa e limitada são tratados explicitamente;
- [ ] cada contêiner aceito possui codec válido;
- [ ] áudio final corresponde ao perfil escolhido;
- [ ] verificação confirma vídeo, áudio, duração, frames, sync e decodificação;
- [ ] preview representa o mesmo comportamento temporal do final;
- [ ] fila real com múltiplos projetos foi aprovada;
- [ ] cancelamento foi validado em todas as etapas;
- [ ] MSI atualiza e desinstala corretamente;
- [ ] portátil funciona sem Python/FFmpeg instalados no sistema;
- [ ] atualização e rollback foram testados;
- [ ] integrações leves fazem parte do CI;
- [ ] render musical real longo foi aprovado pelo usuário;
- [ ] render real 8K/120 foi aprovado na máquina-alvo;
- [ ] documentação corresponde ao comportamento observado.

## 13. Priorização final resumida

| Ordem | Trabalho | Prioridade |
|---:|---|---|
| 1 | `RenderPlan` como fonte única de verdade | P0 |
| 2 | Preservar resolução, FPS e 10-bit | P0 |
| 3 | Tornar Real-ESRGAN e RIFE target-aware | P0 |
| 4 | Refazer pré-verificação por etapas | P0 |
| 5 | Corrigir VFX 320×180/60 | P0 |
| 6 | Corrigir contêineres, codecs e limites | P0 |
| 7 | Separar MSI e portátil | P0 |
| 8 | Processar IA/RIFE em blocos | P1 |
| 9 | Corrigir color management e áudio master | P1 |
| 10 | Fortalecer verificação e logs | P1 |
| 11 | Integrar testes de render ao CI | P1 |
| 12 | Modularizar e polir UX | P2 |
| 13 | Adicionar novas IAs e plugins | P3 |

## 14. Parecer final

O CinePulse não precisa de mais modelos neste momento para se tornar melhor. Ele precisa garantir que os recursos já existentes trabalhem sobre um pipeline tecnicamente coerente.

O objetivo de curto prazo deve ser simples e verificável:

> Uma saída anunciada como 8K/120 deve manter ou produzir qualidade espacial e temporal compatível com 8K/120, sem passar silenciosamente por 720p/1440p/60, sem recodificações desnecessárias e sem estimativas fictícias de armazenamento.

Depois que esse contrato estiver garantido por arquitetura e testes, o projeto terá uma base adequada para novas IAs, VFX avançados e publicação como versão estável.
