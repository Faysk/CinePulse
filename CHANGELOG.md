# Changelog

## 1.1.3 — 2026-09-05

- corrige a estimativa/materialização de armazenamento de loops longos distinguindo duração do clipe reutilizável da duração total do projeto;
- em Loop musical, RIFE interpola o clipe reutilizável antes da expansão temporal e evita uma segunda passagem full-length;
- VFX terminal de Loop musical pode ser fundido à entrega final, eliminando o intermediário FFV1 full-length sem remover AtomicOutput/verificação;
- mantém 8K/120 como carga extrema sujeita a aceitação física separada, sem converter CI hospedado em PASS de hardware.

## Não lançado — Restauração Preview + Hardware H1–H5

- adiciona laboratório Preview isolado para detectar/revisar textos, QR codes e overlays persistentes, reconstruir regiões temporalmente e aplicar restauração de cor limitada;
- exportação Preview usa arquivo temporário + promoção atômica, invalida análise quando a fonte muda no mesmo caminho e mantém o render Stable separado;
- envelope experimental permite planejar até 12K/120 com guardas de memória/scratch e aviso explícito de aceitação física pendente para 8K+/alta cadência;
- H1–H4 adicionam telemetria local, topologia/orçamentos de CPU, tuning físico opt-in, headroom RAM/VRAM/scratch e overlap neural estritamente limitado;
- H5 consome a telemetria já coletada para downshift monotônico de chunks/overlap sob pressão térmica ou de memória, sem reduzir modelo, resolução, FPS, cor ou qualidade de entrega;
- auditoria pesada reforça cancelamento Windows e Preview temporal por árvore de processos, contabiliza buffers rawvideo no working set e preserva fail-closed para VFR/FFprobe/baixa confiança;
- aceitação física RTX/8K/12K/120 continua PENDING até execução em runner/hardware real; nenhuma evidência sintética é promovida a PASS físico.

## 1.1.2 — 2026-09-05

- fecha a auditoria pós-1.1.1 com correções de preflight, saída atômica, locks/leases, cancelamento, persistência e updater;
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

## 1.0.0-rc.6 — 2026-08-13

- consolida o Core Integrity MegaPack, com `RenderPlan` único e decisões explícitas de resolução, FPS, cor, armazenamento e entrega;
- adiciona preservação real, upscale Lanczos/Real-ESRGAN, interpolação FFmpeg/RIFE e VFX guiado pelo envelope musical;
- acrescenta verificação profunda, histórico de render, saída atômica, fila persistente e UX modular;
- separa corretamente as distribuições MSI e portátil, inclui updater validado, SBOM, hooks de assinatura e gates de release;
- valida 187 testes, matriz Windows/Linux em Python 3.11/3.13, integração CPU e integridade de mídia;
- corrige compatibilidade do Tk no Windows, simulação neural em chunks, geração de SBOM no Python 3.11 e aliases de caminhos temporários.

## Core Integrity MegaPack — Phase 9

- novo `scripts/ci_gate.py` transforma source checks e integrações CPU/GPU em perfis reproduzíveis com evidência JSON;
- matriz de source passa a cobrir Windows/Linux e Python 3.11/3.13;
- smokes de áudio, VFX, cancelamento, delivery, HDR, SDR10, storage, verificação e chunks neurais passam a ser gate explícito de CI;
- workflow Release Candidate Windows executa release-light, PowerShell, build portátil, updater, build/validação MSI e publica evidências;
- workflow GPU Acceptance fica manual/self-hosted para RIFE, Real-ESRGAN e Demucs reais;
- `Build-Portable.ps1`/`Build-Msi.ps1` aceitam `-BuildPython`, eliminando dependência de `.runtime` já inicializado na máquina de build;
- `Test-Updater.ps1` deixa de fixar a versão RC e passa a testar a versão fornecida pelo gate;
- release gate passa a exigir workflows e documentação da Phase 9;
- suíte unitária sobe para 185 testes; execuções Windows/GPU reais permanecem portões externos honestamente pendentes.

## Core Integrity MegaPack — Phase 8

- MSI e portátil passam a usar contratos separados, com `CinePulse-Installed.cmd`/`Install-CinePulse-Installed.cmd` forçando `-NonPortable`;
- dados/runtime/componentes do MSI passam para `%LOCALAPPDATA%\CinePulse`, enquanto o portátil permanece autocontido;
- bootstrap elimina dependência do Python do sistema e cria runtime com versão fixada, `uv --python-preference only-managed` e lock com hashes;
- novo `runtime_distribution.py` centraliza descoberta de PowerShell e bloqueia segunda instância com named mutex por usuário no Windows;
- WiX recebe versão dinâmica, ícone real e atalhos exclusivos para o launcher instalado;
- self-updater in-place fica restrito ao portátil; instalação MSI orienta atualização por pacote MSI novo;
- novo `signatures.py` permite exigir assinatura destacada do manifesto antes do parse; build portátil consegue gerar canal assinado quando chaves reais são fornecidas;
- `Build-Msi.ps1` ganha hook Authenticode verificável sem fingir assinatura quando não há certificado;
- novo `generate_sbom.py` gera CycloneDX e o build portátil inclui o SBOM no manifesto de integridade;
- CP-010/017/018/030/031 passam a tratados; CP-019/020 permanecem parciais até release assinada e lock transitivo completo;
- suíte automatizada sobe para 176 testes; validação Windows real de MSI/PowerShell/SignTool fica como gate da Phase 9.

## Core Integrity MegaPack — Phase 7

- novo `verification.py` separa quick verify obrigatório de deep verify opcional com decode completo até EOF;
- verificação passa a confirmar frame count, CFR, presença de áudio, codecs, canais, sample rate e delta A/V antes da promoção atômica;
- aba Qualidade e saída ganha opção explícita de verificação profunda sem impor o custo a todo render;
- novo `render_history.py` cria `job.json`, `render.log`, `plan.json`, `contracts.json` e `verification.json` por job_id;
- log da UI passa a ser persistido durante o render, mantendo comandos, decisões, fallbacks e erros após fechar o app;
- export técnico redigido remove paths absolutos de bundles de suporte sem enviar dados automaticamente;
- novo `state_store.py` versiona fila/presets, migra formatos legados, cria backup `.bak` e rejeita schemas futuros;
- fila persiste o histórico técnico e ganha ação para abrir a pasta do job;
- RenderPlan passa para `core-integrity-phase7-verification-history` e marca CP-014/CP-023/CP-029 como tratados;
- suíte automatizada sobe para 159 testes; smoke básico, quatro contêineres e deep verify real passam.

## Core Integrity MegaPack — Phase 6

- novo `storage_engine.py` transforma armazenamento em contrato derivado das etapas reais do RenderPlan;
- preflight passa a mostrar pico scratch por etapa, volume, espaço, cache e uma amostra rápida de escrita;
- scratch disk torna-se configurável na aba Qualidade e saída e o worker usa esse caminho para `job_*`;
- Real-ESRGAN passa a processar lotes limitados, converter cada lote em FFV1 e apagar PNGs antes do próximo;
- RIFE adota o mesmo modelo bounded, com lote reduzido conforme aumenta a razão de interpolação;
- intermediários visuais já consumidos são liberados durante o job em vez de sobreviverem até o `finally`;
- cache global ganha quota configurável, atualização de recência em cache hit e evicção LRU automática;
- StoragePlan soma saída, scratch e crescimento de cache corretamente quando compartilham volumes;
- RenderPlan passa para `core-integrity-phase6-storage-engine` e marca CP-005/CP-012/CP-021/CP-022 como tratados;
- suíte automatizada sobe para 141 testes; smoke básico, matriz de quatro contêineres, scratch customizado e integrações neurais em chunks passam.

## Core Integrity MegaPack — Phase 5

- novo `delivery.py` transforma extensão, contêiner, codec de vídeo, codec de áudio, bit depth e perfil de entrega em um contrato único;
- MP4 passa a usar HEVC + AAC, MOV master usa ProRes 422 HQ + PCM 24-bit, MKV de arquivo usa HEVC + FLAC e WebM usa VP9 + Opus;
- WebM deixa de cair no caminho HEVC + AAC, fechando a incompatibilidade tardia apontada pelo CP-008;
- perfil estável passa a bloquear 10K/12K e 144/240/480 fps antes do render até existir matriz comprovada por encoder/hardware;
- capacidades do FFmpeg ativo são consultadas e a ausência de encoder obrigatório vira erro de preflight, não falha no fim do trabalho;
- áudio de master/arquivo deixa de ser sempre AAC: PCM/FLAC preservam canais e sample rate quando compatível;
- perfil de entrega aparece em Qualidade e saída, presets/fila persistem a escolha e o diálogo final oferece MP4/MOV/MKV/WebM;
- RenderPlan passa para `core-integrity-phase5-delivery-matrix` e incorpora uma etapa explícita de codec/contêiner;
- verificação final confirma também o codec de vídeo e, quando há áudio, o codec de áudio esperado;
- suíte automatizada sobe para 130 testes e integração end-to-end valida quatro entregas reais: HEVC/AAC, ProRes/PCM, HEVC/FLAC e VP9/Opus.

## Core Integrity MegaPack — Phase 4

- novo `color_pipeline.py` torna HDR/SDR, bit depth, gamut, transfer e range decisões explícitas e testáveis;
- HDR limpo passa a permanecer HDR/10-bit por masters color-critical em FFV1 em vez de H.264/yuv420p 8-bit;
- HDR que entra em VFX/transição recebe conversão real via `zscale` + linearização + `tonemap` + BT.709/range conversion;
- Real-ESRGAN e RIFE atuais são tratados como fronteiras SDR 8-bit, com redução 10→8 por error-diffusion dithering e sem falsa promoção posterior para HDR/Main10;
- VFX passam a aceitar base/saída `yuv420p10le` e metadata de cor do plano;
- caminhos SDR 10-bit e full-range são preservados quando os estágios suportam;
- SDR 8-bit final deixa de ser automaticamente codificado como Main10;
- BT.2020 SDR deixa de ser classificado como HDR apenas pelas primárias;
- RenderPlan passa para `core-integrity-phase4-color-pipeline` e CP-007 entra em `resolved_audit_codes`;
- suíte automatizada sobe para 115 testes, com integrações reais para HDR limpo, master HDR, HDR→SDR com VFX, SDR10 e full range.

## Core Integrity MegaPack — Phase 3

- VFX deixam de depender de canvas final fixo 320×180/60 e passam a usar política target-aware;
- `StudioFrameGenerator` torna-se dimensionável e usa FPS configurado para o tempo dos efeitos;
- 1080p/60 e 4K/120 podem gerar layers nativos; acima de 4K há canvas adaptativo 4K explicitamente reportado;
- novo `music_envelope.py` analisa a faixa completa a 120 fps e normaliza antes de recortar qualquer preview;
- preview renderizado e render final passam a compartilhar a mesma análise/cache, fechando a divergência CP-013;
- cache do envelope usa RAM + SSD e chave por arquivo, duração, FPS e versão do analisador;
- preview visual imediato também pede o canvas diretamente ao gerador em vez de depender do antigo resize 320×180;
- RenderPlan passa para `core-integrity-phase3-vfx-envelope`, com CP-003/CP-013 como tratados e warnings honestos para >4K/>120 fps;
- suíte automatizada ampliada para 103 testes e smoke FFmpeg confirma 640×360/120 com 120 frames.

## Core Integrity MegaPack — Phase 2

- master de estúdio passa a usar a resolução real do destino em vez de 720p/1440p fixos;
- cadência do master deixa de ser fixa em 60 fps e preserva fontes 120 fps quando o destino também pede 120 fps;
- caminho `RIFE base` é removido da execução: RIFE agora é no máximo uma passagem e somente quando `target_fps > effective_source_fps`;
- Real-ESRGAN torna-se target-aware e é ignorado quando o enquadramento já pode atingir o destino sem upscale;
- preflight, validação, VRAM/carga e worker respeitam a decisão real de executar ou ignorar Real-ESRGAN/RIFE;
- `Preservar` passa a impedir ampliação de pixels da fonte e deixa de ser equivalente ao modo Lanczos;
- VFX ainda são gerados internamente em 320×180/60, mas a composição não força mais o vídeo-base a 60 fps;
- riscos CP-001, CP-002, CP-004 e CP-006 passam a ser tratados pela política Phase 2; CP-003 e CP-007 permanecem explicitamente pendentes;
- suíte automatizada ampliada para 93 testes, com smoke FFmpeg real confirmando 120 quadros/120 fps tanto no caminho Preservar quanto na composição VFX.

## Core Integrity MegaPack — Phase 1

- novo `render_plan.py` cria uma fonte única e determinística para etapas, entrada/saída, dispositivo, cache/materialização e riscos;
- preflight, aba Qualidade, worker e relatório final passam a consumir o mesmo RenderPlan;
- cada plano recebe fingerprint estável para correlação entre UI, log, relatório e testes;
- worker deixa de duplicar as decisões centrais de master/RIFE e passa a consultar o plano;
- riscos CP-001/002/003/004/006/007 da auditoria ficam explícitos em vez de silenciosos;
- o planejador modela deliberadamente o pipeline atual nesta fase; a política de preservação/target-awareness será alterada na Phase 2;
- suíte automatizada ampliada para 82 testes e render sintético real revalidado após a integração.

## UX MegaPack — desenvolvimento

- Home reorganizada com preview imediato, descoberta visual de VFX e hierarquia de ações;
- Visual Lab com VFX reais, A/B, timeline demonstrativa, variações e guias de transição;
- Projeto redesenhado com modos explicados, FFprobe assíncrono, metadados inline, validação de saída, preview de enquadramento e preflight inline;
- novas views extraídas gradualmente do `studio.py`, sem alterar o pipeline de render;
- Qualidade e saída reorganizada com impacto Fonte → Destino, carga relativa, VRAM/tamanho estimados e avisos contextuais sem ETA fictícia;
- Fila redesenhada com resumo operacional, progresso por item, inspector, retry, reordenação e recuperação explícita;
- IA local redesenhada como gerenciador de capacidades, separando integrado, faltante, experimental e apenas instalado;
- seleção automática de IA passa a incluir somente componentes integrados necessários; experimentais exigem escolha explícita;
- inspector de IA mostra impacto, fallback, tamanho, licença e restrições;
- feedback local de instalação usa percentual somente quando o instalador o informa, sem ETA global inventada.
- estados transversais unificados em info/processando/concluído/atenção/bloqueado, com próxima ação contextual;
- Central de atividade preserva eventos da sessão e detalhe técnico sem sobrecarregar as telas principais;
- conclusão normal de render, IA e atualização passa a usar feedback persistente, mantendo modais para confirmações e decisões de risco;
- recuperação de fila/render deixa explícito quando o trabalho foi reiniciado, promovido ou apenas preservado.
- Phase 8 adiciona onboarding não modal, guia F1, persistência de tema/aba/geometria e restauração segura de janela;
- seis workspaces passam a empilhar automaticamente em 1024×700 e o scroll é normalizado sobre cards/labels;
- rodapé ganha densidade contextual em janela mínima: `Cancelar` só aparece quando útil, progresso ocioso sai e `Fila +` permanece acessível;
- atalhos de teclado cobrem navegação, arquivos, preview, log e atividade sem criar atalhos destrutivos;
- preset selecionado, aplicado e manualmente ajustado passam a ser estados distintos na interface;
- inicialização solicita DPI awareness no Windows antes de criar o Tk;
- callbacks periódicos do shell passam a ser rastreados e cancelados no encerramento, evitando comandos Tcl órfãos em relaunch/testes;
- animação do Visual Lab passa a cancelar a cadeia anterior ao pausar/reiniciar, evitando timers duplicados;
- suíte do MegaPack chega a 69 testes e o render básico é revalidado após o polish.

## 1.0.0-rc.5 — 2026-08-09

- preferência de GPU de alto desempenho registrada no Windows para Python, FFmpeg, Real-ESRGAN e RIFE;
- ambiente CUDA fixado na primeira GPU NVIDIA dedicada durante todo o processo;
- removido o `-g 0` que podia selecionar a GPU integrada em notebooks híbridos;
- Real-ESRGAN e RIFE agora usam a seleção automática de alto desempenho do NCNN, mantendo CPU apenas quando solicitada;
- diagnóstico e tela inicial informam a política gráfica ativa.

## 1.0.0-rc.4 — 2026-08-08

- tela IA local transformada em gerenciador com seleção individual, instalação dos selecionados e instalação de tudo que falta;
- componentes integrados são instalados em segundo plano com PowerShell 7, log em tempo real e atualização automática do inventário;
- modo avançado permite baixar componentes experimentais após aceite explícito de licenças, espaço e compatibilidade;
- downloads experimentais usam fontes oficiais, arquivos temporários e verificação SHA-256 antes da instalação;
- BasicVSR++, CLAP, Video Depth Anything, SAM 2.1, CoTracker 3, CodeFormer e código-base LTX-2.3 permanecem claramente marcados como não integrados ao render.

## 1.0.0-rc.3 — 2026-08-04

- instalação completa agora abre uma janela visível, mantém o resultado na tela e grava `data/logs/installer.log`;
- PowerShell 7 é selecionado automaticamente quando instalado, com fallback seguro para Windows PowerShell;
- MSI e pacote portátil criam um atalho do CinePulse na Área de Trabalho;
- MSI inicia o provisionamento completo por um instalador dedicado, com etapas e indicação clara de sucesso ou erro.

## 1.0.0-rc.2 — 2026-08-04

- instalação completa antes da primeira abertura, incluindo Real-ESRGAN, RIFE, Demucs e seus modelos;
- downloads oficiais fixados e conferidos por SHA-256, com troca atômica dos componentes;
- ambiente privado CUDA/PyTorch para Demucs, sem depender do Python do usuário;
- preset adaptado automaticamente quando uma instalação antiga estiver incompleta;
- comando de reparo/instalação acessível pela interface e preparação de pacote MSI.

## 1.0.0-rc.1 — 2026-08-04

- pré-verificação separada para disco de saída e temporários, teste de escrita e proteção das mídias de entrada;
- avisos proporcionais de VRAM, escala e interpolação extrema;
- atualizador portátil preparado para releases do GitHub, com HTTPS, SHA-256, aplicação no reinício e rollback;
- manifesto de integridade no pacote portátil e diagnóstico de arquivos ausentes ou alterados;
- portão automatizado de release para versões, scripts, compilação, testes e higiene do repositório;
- separação explícita entre motores integrados e extensões futuras, sem prometer recursos experimentais.

## 0.1.0-alpha.2 — 2026-08-04

- render atômico com verificação antes de substituir o arquivo final;
- recuperação de render válido interrompido e cancelamento da árvore de processos;
- RIFE NCNN integrado com cache temporário, progresso e fallback para FFmpeg;
- Real-ESRGAN, RIFE, Demucs e VMAF validados em renders sintéticos reais;
- Demucs opcional para VFX guiado por baixo, bateria, voz ou instrumentos, com cache;
- normalização LUFS em duas passagens e medição de true peak;
- detecção de HDR/faixa de cor e preservação HDR para vídeo original sem VFX;
- VMAF perceptivo amostral no relatório de vídeos originais;
- onboarding com hardware, VRAM e níveis Rápido, Recomendado e Máximo;
- Python portátil automático via uv fixado e validado por SHA-256;
- suíte ampliada para testes unitários e integrações reais de áudio, VFX, IA e cancelamento.

## 0.1.0-alpha.1 — 2026-08-04

- migração isolada do núcleo funcional para CinePulse;
- armazenamento portátil ou em LocalAppData;
- descoberta compatível dos componentes da instalação anterior;
- catálogo de componentes com validação SHA-256 e instalação atômica;
- diagnóstico local sem enumeração de mídias;
- documentação, política de segurança, licença e templates do GitHub;
- testes leves e verificação contra pesos, arquivos gigantes e Git aninhado;
- marcador de render para impedir atualização concorrente em pacotes futuros.
