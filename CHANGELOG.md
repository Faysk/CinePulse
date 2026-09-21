# Changelog

## 1.2.19 — 2026-09-21

- Restauração Preview passa a exigir FFprobe para validar a saída antes da promoção atômica;
- o probe de Preview lê contagem exata de quadros, geometria, FPS, duração e presença de áudio da fonte e do candidato;
- color-only preserva timestamps com `-fps_mode passthrough` e só substitui a saída se frame count/geometria/áudio/timeline permanecerem compatíveis;
- reconstrução temporal deixa de usar `-shortest`, impedindo que uma faixa de áudio curta corte os últimos quadros do vídeo;
- encoder temporal declara CFR explicitamente (`-r` + `-fps_mode cfr`); a fonte VFR continua bloqueada, enquanto o candidato gerado é validado por frame count/FPS/duração exatos sem falso positivo de `avg_frame_rate` em clipes curtos;
- temporal limita somente a entrada de áudio à duração `frames/fps`, usa `-frames:v` e exige `frames_written == source.frame_count`;
- candidato temporal é validado novamente por FFprobe antes do `os.replace()`; mismatch preserva qualquer saída anterior e remove o temporário;
- adiciona integração real com vídeo de 1 s/4 frames e áudio de 0,5 s, exigindo os 4 quadros completos na saída.
- temporal preserva todas as faixas de áudio (`-map 1:a?`) e a validação passa a rejeitar promoção quando a quantidade de streams de áudio muda;
- adiciona integração real com fonte temporal de duas faixas de áudio, exigindo as duas na saída;
- downloads hash-locked do bootstrap passam a repetir falhas transitórias com backoff; smoke neural e download hash-locked do FFmpeg no publisher recebem o mesmo hardening para evitar derrubar RC/Publish por 5xx temporário, sem relaxar SHA-256;

## 1.2.18 — 2026-09-21

- Overlay Composer deixa de usar `-t profile.duration` como corte global no mux final;
- o número de quadros do Composer passa a ser uma função explícita do contrato `round(duration*fps)` e a duração real da timeline deriva de `frames/fps`;
- o áudio do mux é limitado apenas na própria entrada com `bounded_audio_input_args`, preservando o vídeo frame-bound;
- o vídeo final do Composer usa `-frames:v <frames>` mesmo em stream-copy, impedindo corte do último quadro em cadências fracionárias;
- antes do `AtomicOutput.commit()`, o FFprobe conta os quadros do resultado e o export falha fechado se a contagem não coincidir exatamente;
- a análise dos envelopes musicais usa a mesma duração CFR real da saída;
- adiciona teste real de FFmpeg com base estática + áudio separado em 30000/1001 fps para provar 30 quadros completos em uma timeline de 1.001 s.

## 1.2.17 — 2026-09-21

- recuperação de `.partial` no startup deixa de aceitar apenas `duration > 0` e resolução não-zero; passa a usar o mesmo contrato de verificação da saída final;
- `render.json` grava resolução, FPS, duração frame-bound, presença de áudio, codecs, canais, sample rate e nível Deep Verify necessários para validar a saída interrompida;
- `quick_verify` é exigido com `frame_tolerance=0`; partials com menos/mais quadros, FPS/geometria/codec/áudio incorretos ou sync inválido ficam preservados e nunca são oferecidos para promoção;
- renders originalmente configurados com Deep Verify repetem `deep_verify` antes da promoção do partial recuperado;
- journals legados/incompletos falham fechado: o arquivo parcial permanece disponível para inspeção/manual recovery, sem virar saída final automaticamente;
- adiciona testes para contrato de journal, partial truncado e preservação do nível Deep Verify.

## 1.2.16 — 2026-09-21

- recovery discovery deixa de depender exclusivamente da existência de `manifest.json`: diretórios com apenas `manifest.json.bak` também são encontrados e passam pelo recovery normal do `JobStore`;
- quando o manifesto principal sumiu mas o backup é válido, o backup é revalidado/restaurado e o job volta a aparecer com sua classificação real;
- quando manifesto principal e backup estão ambos ilegíveis, o job não desaparece mais silenciosamente: aparece como `blocked/unreadable` com ações de inspeção e preservação;
- a descoberta de manifesto irrecuperável não altera nem apaga as evidências corrompidas, mantendo o diretório intacto para diagnóstico/manual recovery;
- adiciona testes para backup-only, corrupção dupla, preservação das evidências e apresentação segura do card de recovery.

## 1.2.15 — 2026-09-21

- comparação A/B só troca H.264/NVENC por libx264 quando a exceção contém evidência real de falha GPU/NVENC; erro de disco, input ou filtro não dispara retry enganoso;
- extração CUDA foreground do pipeline neural deixa de repetir pela CPU para qualquer `RuntimeError`: fallback passa a exigir classificação GPU explícita;
- prefetch CUDA recebe o mesmo contrato, evitando descartar/reextrair chunks por falhas que não pertencem à GPU;
- mismatch explícito de contagem de frames CUDA continua acionando CPU, porque a própria saída prova uma falha de integridade da rota acelerada mesmo com exit code zero;
- Quality Linux desabilita apenas sources em `/etc/apt/sources.list.d/` que apontem para `packages.microsoft.com` antes de instalar FFmpeg/Xvfb/Tk dos repositórios Ubuntu, evitando que um 403 externo derrube Media/CPU integration;
- adiciona contratos de regressão para classificação GPU e isolamento de APT de terceiro.

## 1.2.14 — 2026-09-21

- recovery crash-safe passa a usar o mesmo contrato GPU-first/CPU-fallback da renderização normal na codificação final;
- o self-test do encoder recuperado também pode repetir `hevc_nvenc` com `libx265`, evitando bloquear uma recuperação válida apenas porque o NVENC falhou naquele momento;
- retry CPU só ocorre quando a exceção contém evidência real de falha GPU/NVENC; disco cheio, filtro inválido, input quebrado, timeout e outros erros não-GPU continuam fail-fast;
- o partial produzido pela tentativa GPU é removido antes do retry CPU para impedir reaproveitamento de container/trailer incompleto;
- a `DeliveryPlan` devolvida pelo helper corresponde ao encoder que realmente venceu, mantendo a verificação final coerente após fallback;
- adiciona testes para NVENC→CPU, falha não-GPU sem retry e jobs originalmente CPU sem tentativa redundante.

## 1.2.13 — 2026-09-21

- master SDR passa a tentar H.264/NVENC no adaptador selecionado e, após falha real, remove a saída parcial e repete uma vez com libx264;
- transição de loop recebe o mesmo fallback NVENC→libx264, preservando filtro, geometria, pixel format, metadata de cor e timeline;
- VFX intermediário H.264/NVENC passa a repetir uma vez com libx264 após `return_code != 0`, sem reavaliar RAM/VRAM nem reduzir carga antes da falha;
- VFX fused recebe do Studio os argumentos CPU equivalentes da própria `DeliveryPlan`; se a entrega NVENC falhar, o segundo attempt troca apenas o encoder e preserva áudio, muxer, frame count e filtros;
- cancelamento continua fail-fast e nunca aciona retry de encoder;
- adiciona testes funcionais para transição, VFX intermediário e VFX fused, além dos contratos de regressão do pipeline.
- retry CPU só ocorre quando o erro é classificado como GPU/NVENC; falhas não-GPU continuam fail-fast.
- a finalização HEVC/NVENC normal também ganha rollback completo para `libx265` em falha GPU real; o fallback não reutiliza NVENC escondido no baseline.


## 1.2.12 — 2026-09-21

- fixa explicitamente `-gpu <selected>` nos encoders H.264/HEVC NVENC auxiliares do Studio, evitando que intermediários, transições ou comparação caiam silenciosamente no adaptador 0 em máquinas multi-GPU;
- o fallback H.264/NVENC direto do VFX recebe `gpu_index` do Studio e usa o mesmo adaptador selecionado para o render;
- a comparação A/B calcula `comparison_duration = frames/fps` e deixa de fazer `-c:a copy` sem limite de timeline;
- quando existe áudio no arquivo processado, a comparação usa `atrim + asetpts + apad` até a duração CFR exata e reencoda AAC 320 kbps; sem áudio, mantém saída silenciosa explícita;
- preserva `-frames:v` como limite do vídeo da comparação e não reintroduz `-t` global;
- comparação A/B passa a ser best-effort: falha H.264/NVENC auxiliar repete com libx264, e falha/cancelamento do A/B depois do preview principal validado não reclassifica o render principal como erro/cancelado;
- adiciona contratos para pinning de GPU em caminhos auxiliares e para impedir retorno de stream-copy de áudio na comparação.

## 1.2.11 — 2026-09-21

- aplica ao Real-ESRGAN o mesmo contrato temporal exato já usado pelo RIFE: cada chunk FFV1 é contado estruturalmente e o concat recebe `duration = frames/fps`;
- recusa a montagem quando a soma dos packets dos chunks não coincide exatamente com o número de frames esperado para o trecho;
- valida o master Real-ESRGAN depois do concat e exige `packet_count == total_frames` antes de promover/cachear;
- endurece o cache de IA: reutilização agora exige resolução x2 correta, codec FFV1, packet count exato e duração compatível com a timeline CFR derivada dos frames;
- a barra/progresso da concat usa a duração frame-bound real em vez do decimal original do trecho;
- integração neural passa a verificar estruturalmente que o master Real-ESRGAN final contém exatamente todos os quadros esperados;
- adiciona contratos de regressão para impedir retorno do concat simples sem durations ou cache aceito só por resolução/duração aproximada.

## 1.2.10 — 2026-09-21

- recovery passa a derivar a duração de entrega diretamente de `total_target_frames / target_fps`;
- Studio passa a nomear e reutilizar `final_timeline_duration = final_target_frames / target_fps` como fonte única da duração realmente entregue;
- RenderJournal, RenderHistory, verificação final, relatório de qualidade e comparison preview deixam de registrar/verificar `project_duration` decimal e usam a timeline CFR exata;
- análise de loudness do recovery usa a mesma janela frame-bound realmente codificada, evitando medir alguns milissegundos a mais ou a menos em cadências fracionárias;
- `VerifyExpectation` final do recovery passa a usar a duração CFR exata em vez de `contract.duration` decimal;
- self-test do encoder converte a janela de 0,10 s para um número inteiro de frames e verifica a duração efetivamente representada por esses frames;
- mensagens de partial reuse deixam de amarrar o contrato de áudio a uma versão antiga específica;
- adiciona contratos de regressão para impedir nova divergência entre duração declarada e duração representada pelos quadros.

## 1.2.9 — 2026-09-21

- introduz `frame_bound_duration(frame_count, fps)` como fonte única da duração real de uma linha do tempo CFR;
- Studio calcula a janela de áudio final a partir de `final_target_frames / target_fps`, em vez de reutilizar o decimal original de `project_duration`;
- VFX fused limita o input de áudio pela duração exata dos frames realmente entregues;
- recovery calcula a janela de áudio a partir do `frame_limit` real do self-test/final e não do duration original;
- adiciona `atrim + asetpts + apad` ao áudio de entrega para garantir que a faixa termine exatamente junto do vídeo mesmo quando o arredondamento de frames sobe e a fonte termina alguns milissegundos antes;
- mastering/loudness continua preservado dentro da cadeia de áudio exata;
- adiciona testes para duração frame-bound, trim/pad e contratos Studio/VFX/recovery.

## 1.2.8 — 2026-09-21

- adiciona `bounded_audio_input_args()` para aplicar a janela de duração como opção do input de áudio (`-t ... -i audio`), nunca como corte global do mux;
- preview/final normal, VFX fused e recovery passam a usar a mesma regra, evitando que a faixa inteira continue depois do último frame de vídeo em previews/autotestes;
- o self-test do recovery deixa de adicionar `-t` global depois de `-frames:v`, preservando a contagem exata de vídeo enquanto limita apenas o áudio;
- master intermediário do Studio substitui `-t video_duration` por `-frames:v round(video_duration*work_fps)`;
- materialização de cor FFV1 usa contagem exata de frames e valida `packet_count` depois da escrita;
- comparação A/B passa a usar o FPS real do resultado processado, `hstack` com cadência explícita e `-frames:v`, removendo o último `-t` global do Studio;
- loudness analysis usa o mesmo helper de input de áudio limitado;
- adiciona testes de regressão para janelas de áudio, intermediários frame-bound e comparação A/B.

## 1.2.7 — 2026-09-21

- remove `-t duration` do concat do master RIFE para impedir corte do último frame quando `round(duration*fps)` exige um frame além do timestamp decimal;
- valida estruturalmente o master FFV1 após concat e exige `packet_count == total_target_count` antes de continuar;
- recovery deixa de reutilizar masters antigos apenas por tolerância de duração e passa a exigir a contagem exata de pacotes;
- concat de recovery também deixa de usar `-t`, e valida a contagem exata depois da montagem antes da promoção atômica;
- encode final CFR substitui o corte global por duração por `-frames:v` calculado a partir de `round(project_duration*target_fps)`;
- VFX final/intermediário usa contagem exata de frames e torna explícito `overlay` com `eof_action=repeat`, `shortest=0` e `repeatlast=1`, evitando encurtar a base quando o layer reativo termina primeiro;
- verificação final do Studio passa a exigir contagem de quadros conhecida e tolerância zero; uma saída com frame faltando/sobrando ou contagem indeterminada não é promovida;
- recovery passa a restaurar o contrato real de áudio do job: suporta saída silenciosa quando esperado, preserva canais reais, ajusta sample rate conforme o codec de entrega e reaplica o `audio_mode`/loudness do render original;
- recovery também preserva o backend original do job: `use_cpu=True` mantém RIFE/encode em CPU; jobs GPU continuam no adaptador selecionado, sem troca silenciosa de backend;
- autoteste do recovery deixa de assumir MP4/HEVC: usa a extensão, o perfil e o codec reais do job, com contagem exata de frames;
- partials antigos de recovery com masterização de áudio não são reutilizados sem prova do filtro aplicado; a 1.2.7 força um encode novo nesses casos.
- adiciona contratos de regressão para master RIFE, recovery e entrega final frame-bound.

## 1.2.6 — 2026-09-20

- memoriza a política RIFE realmente aplicada em um chunk e a reutiliza nos chunks seguintes do mesmo render, evitando repetir OOM já conhecido;
- corrige drift de contagem em RIFE chunked para taxas fracionárias como 59.94→120 fps: o alvo passa a ser distribuído cumulativamente, a montagem exige contagem final exata e o concat FFV1 usa durações derivadas de frames para não acumular o timebase de 1 ms do Matroska;
- o safe runner aceita apenas overrides de sessão iguais ou menos agressivos que a política full-utilization e mantém esse nível como piso de rollback, sem upshift oculto;
- o Studio passa o `gpu_index` já selecionado ao RIFE, evitando redescoberta via `nvidia-smi` em cada chunk e mantendo o mesmo adaptador por todo o render;
- corrige encode final HEVC/NVENC baseline e recovery para usar o mesmo índice de GPU selecionado, em vez de cair silenciosamente no default GPU 0;
- o recovery de jobs antigos deixa de respeitar limites históricos de `cpu_threads` e usa todos os threads lógicos detectados na máquina atual;
- o recovery RIFE usa o adaptador detectado e só envia `-u` quando a geometria realmente é UHD;
- recovery reconhece tanto o scheduling legado por chunk quanto o novo scheduling cumulativo da 1.2.6, evitando rejeitar segmentos válidos após interrupção;
- amplia testes de sessão RIFE, CLI `APPLIED`, multi-GPU, recovery e contratos do modo full-utilization.

## 1.2.5 — 2026-09-20

- corrige o caminho Real-ESRGAN da 1.2.4 que ainda referenciava `neural_headroom` depois da remoção do probe de headroom, evitando `NameError` antes do upscale;
- remove da aba Qualidade o Spinbox de threads e os perfis de utilização que já não controlavam o runtime full-utilization;
- canonicaliza `cpu_threads` legado em presets e fila para o total lógico da máquina atual, preservando compatibilidade de arquivos antigos sem manter um limite fictício;
- RIFE passa a usar fallback pós-OOM em escada (`3:3:3 -> 2:2:2 -> 1:1:1` quando aplicável), sem consultar VRAM livre;
- o staging temporário do RIFE ganha nonce por execução para evitar colisão entre invocações concorrentes no mesmo processo;
- Real-ESRGAN ganha uma segunda marcha de fallback `1:1:1` quando o fallback conservador também sofre OOM; falhas de integridade continuam fail-closed;
- adiciona contratos de regressão específicos para o modo full-utilization e para a ausência das variáveis de headroom removidas.

## 1.2.4 — 2026-09-19

- muda a prioridade do runtime para utilização total antes de limitação preventiva;
- todos os perfis de CPU passam a disponibilizar 100% dos threads lógicos ao render;
- Real-ESRGAN deixa de reduzir concorrência por VRAM livre/geometria e usa envelope estático agressivo pelo porte total do adaptador;
- budgets de Real-ESRGAN/RIFE deixam de depender de RAM disponível, VRAM livre e benchmark de scratch: Real-ESRGAN usa 16 GiB/3 worksets com extract+pack overlap; RIFE usa 12 GiB/2 worksets com extract overlap;
- o controlador adaptativo deixa de reduzir chunks, overlap ou CPU por RAM%, VRAM livre, temperatura, throughput ou instabilidade medida;
- RIFE inicia em 3:3:3 abaixo de UHD e 2:2:2 em UHD sem gating por VRAM livre; somente uma falha/OOM real aciona o fallback conservador;
- permanecem ativos os contratos de integridade de PNG/mídia, AtomicOutput, cancelamento e validação final;
- telemetria pode continuar registrada para diagnóstico/histórico, mas não governa mais throttling preventivo nesta versão.

## 1.2.3 — 2026-09-19

- amplia a utilização segura de GPU/VRAM/RAM sem alterar modelo, escala, FPS, cor/HDR ou qualidade do encoder;
- separa corretamente o host-feed de CPU da concorrência Vulkan do Real-ESRGAN e admite políticas maiores somente com headroom atual e/ou evidência física exata;
- torna budgets de chunks Real-ESRGAN/RIFE dinâmicos por RAM, scratch e VRAM, com limites rígidos de worksets concorrentes e preflight alinhado ao runtime;
- adiciona telemetria NVIDIA de NVENC/NVDEC e seleção multi-GPU mais fiel à atividade real;
- endurece cache/tuning com identidade exata de componente, CPU, GPU, driver e geometria, preservando evidência válida quando a falha decorre apenas de pressão transitória de VRAM;
- corrige staging do mix reativo do Demucs para manter extensão WAV válida no FFmpeg, rejeita caches WAV inválidos e impede reutilização de árvores `.demucs-partial-*` nunca promovidas;
- corrige rollback do RIFE para permitir downshift do baseline `2:2:2` para `1:1:1` quando a VRAM livre despenca durante a execução;
- mantém GPU Acceptance físico separado dos gates hospedados; nenhuma alegação de desempenho físico é promovida sem runner NVIDIA real.

## 1.2.2 — 2026-09-19

- corrige o export CPU do Overlay Composer para carregar a mesma análise musical da prévia; Spectrum/Wave/Circular e pulse/beat reaction deixam de cair silenciosamente para envelopes zerados no vídeo final;
- torna o mux final do Composer cancelável e encerra árvores FFmpeg pelo mesmo controle seguro usado no restante do CinePulse;
- integra o worker de export do Composer ao ciclo de vida da aplicação: fechar a janela ou o CinePulse sinaliza cancelamento e aguarda encerramento antes de destruir a UI;
- adiciona preflight de RAM e scratch para o master FFV1 + mux atômico, falhando cedo quando 8K/10K/12K não cabem com segurança;
- mantém fundos estáticos fora do fast-path H6 até existir evidência física específica para essa base, evitando reutilizar aprovação de vídeo;
- amplia o GPU Acceptance para alterações do Composer/compositor e adiciona Python 3.12 à matriz declarada de compatibilidade;
- atualiza o runtime neural para `certifi 2026.7.22` com hash lock;
- fixa GitHub Actions por commit SHA e usa no publisher o FFmpeg exato/hash-locked do bootstrap manifest.

## 1.2.1 — 2026-09-18

- redesenha o Overlay Composer como editor visual de manipulação direta: o usuário arrasta camadas no quadro e redimensiona pelos cantos preservando a proporção;
- adiciona fundo de imagem/vídeo como elemento de primeira classe; PNG/JPG/WebP e outros formatos de imagem não exigem criar um vídeo artificial antes;
- quando o fundo é uma imagem estática, a duração vem automaticamente da música do projeto e FPS/resolução vêm das configurações atuais do CinePulse;
- GIFs, imagens e visualizadores entram com posição/tamanho inicial úteis e podem ser movidos diretamente no preview;
- remove da experiência padrão a matriz técnica de master/stems e os campos X/Y normalizados; a música já escolhida no projeto passa a dirigir automaticamente os visualizadores;
- mantém ajustes técnicos menos comuns em “Mais opções”, sem expor detalhes de implementação no fluxo principal;
- preserva export atômico, cancelamento, referência CPU determinística e aceleração GPU somente quando houver evidência compatível;
- atualiza o schema do projeto Composer para 3, mantendo leitura dos schemas 1 e 2.

## 1.1.3 — 2026-09-05

- corrige a estimativa/materialização de armazenamento de loops longos distinguindo duração do clipe reutilizável da duração total do projeto;
- em Loop musical, RIFE interpola o clipe reutilizável antes da expansão temporal e evita uma segunda passagem full-length;
- VFX terminal de Loop musical pode ser fundido à entrega final, eliminando o intermediário FFV1 full-length sem remover AtomicOutput/verificação;
- mantém 8K/120 como carga extrema sujeita a aceitação física separada, sem converter CI hospedado em PASS de hardware.

## 1.2.0 — 2026-09-06

- adiciona verificação assíncrona da release Stable ao abrir e botão `Atualizar vX.Y.Z`; o fluxo seleciona o pacote MSI/Portable exato, valida origem e SHA-256, espera trabalhos ativos e reinicia o CinePulse após a atualização;
- adiciona laboratório Preview isolado para detectar/revisar textos, QR codes e overlays persistentes, reconstruir regiões temporalmente e aplicar restauração de cor limitada;
- exportação Preview usa arquivo temporário + promoção atômica, invalida análise quando a fonte muda no mesmo caminho e mantém o render Stable separado;
- envelope experimental permite planejar até 12K/120 com guardas de memória/scratch e aviso explícito de aceitação física pendente para 8K+/alta cadência;
- H0–H4 adicionam telemetria local, topologia/orçamentos de CPU, perfis Equilibrado/Máquina dedicada/Overnight, tuning físico opt-in, headroom RAM/VRAM/scratch e overlap neural estritamente limitado;
- H2/H3 mantêm Real-ESRGAN e RIFE sob políticas exatas/evidence-gated, com fallback conservador e nenhuma promoção de desempenho sem benchmark físico;
- H5 adiciona caminhos NVDEC/CUDA/NVENC somente quando a combinação exata de GPU/driver/FFmpeg/formato passou evidência física, mantendo o caminho CPU/zscale como fallback autoritativo;
- H6 adiciona a base do compositor GPU com rota CPU/NumPy como referência de correção; overlays/visualizers não comprovados fisicamente continuam no CPU;
- H7 mantém TensorRT opcional e Preview-only, subordinado a uma baseline NCNN já aprovada na mesma máquina;
- H8 mede quadros neurais realmente concluídos por segundo em Real-ESRGAN/RIFE e só reduz CPU/chunk/overlap por temperatura/potência/clock quando existe queda sustentada de throughput ou risco real de instabilidade; temperatura alta sozinha não reduz carga;
- Overlay Composer persiste PNG/GIF/APNG/WebP/vídeo-alpha, transformações, blend, loop e bindings `master/vocals/drums/bass/other`; stems configurados dirigem reatividade visual e não substituem silenciosamente a trilha final;
- auditoria pesada reforça cancelamento Windows e Preview temporal por árvore de processos, contabiliza buffers rawvideo no working set e preserva fail-closed para VFR/FFprobe/baixa confiança;
- aceitação física RTX/8K/12K/120 continua PENDING até execução no hardware real; nenhuma evidência sintética é promovida a PASS físico.

## 1.1.2 — 2026-09-05

- fecha a auditoria pós-1.1.1 com correções de preflight, saída atômica, locks/leases, cancelamento, updater e publicação versionada;
- fila e presets recuperam estado corrompido a partir de backup validado sem fazer downgrade silencioso de schema futuro;
- JobLease e single-instance lock ganham identidade de processo/nonce e proteção contra races, PID reuse e ownership stale;
- cancelamento POSIX espera encerramento e escala para SIGKILL; worker persiste somente transições válidas da máquina de estados;
- updater aplica limites de recursos e rejeita ZIP traversal, symlinks, entradas criptografadas, duplicatas case-insensitive e payload expandido excessivo;
- remove workflow temporário com permissão de escrita e restaura `publish-release.yml` como único writer permanente;
- sincroniza metadados de versão em pacote, portátil, MSI e RC;
- publisher passa a derivar release notes da versão, validar o documento correspondente e publicar a partir da alteração de metadados de release na `main`;
- mantém GPU física/8K e aceitação perceptiva extrema como gates separados, sem PASS sintético.

## Não lançado — recuperação RIFE pós-interrupção

- adiciona recuperador reiniciável por segmento para o layout RIFE em chunks, com checkpoint atômico e preservação de cache, segmentos, masters e parciais;
- adiciona auditoria estrutural de segmentos FFV1 e reparo seguro do defeito determinístico de quadros pretos observado em 8K;
- usa RIFE em modo UHD/serial, valida integridade dos PNGs e aplica retime temporal seguro para contagens residuais de 17/18 quadros;
- corrige a concatenação de milhares de segmentos com durações derivadas da contagem exata de pacotes;
- permite reutilizar master/parcial somente após validação, preserva rejeitados e remove `faststart` da entrega local muito grande;
- documenta o caso real 8K/120, o runbook operacional, requisitos rastreáveis, manifesto/máquina de estados, UX, fault matrix, migração e o programa completo para recuperação genérica pela interface;
- valida o recuperador no job real `20260826-203826-da124c70`: 2.718 segmentos, 43.533 quadros, zero preto no gate conhecido e MP4 final 7680×4320/120 HEVC + AAC aprovado.
