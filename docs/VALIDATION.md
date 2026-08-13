# Validação da versão 1.0.0-rc.6

Data: 2026-08-04  
Ambiente: Windows 11, Python portátil 3.13.7, FFmpeg 8.1.2/9.0, RTX 4070 Laptop 8 GB, 28 threads de CPU.

## Verificações automatizadas

- 24 testes unitários aprovados;
- compilação de todos os módulos Python;
- análise sintática de todos os scripts PowerShell;
- proteção contra pesos, arquivos acima de 90 MiB e repositórios Git aninhados;
- proteção contra travessia de diretórios em ZIP;
- troca atômica e rollback de saída;
- parsing de HDR, loudness, RIFE, stems e VMAF.
- validação de volumes separados, proteção das entradas e avisos de qualidade extrema;
- ordenação de versões, canal HTTPS e manifesto de integridade do portátil;
- portão de release com consistência de versão, compilação e scripts do Windows.

## Validação adicional — UX MegaPack Phase 6

Ambiente de desenvolvimento do MegaPack: Linux headless/Xvfb, Python 3.13, FFmpeg do sistema. Esta validação é complementar e não substitui os testes Windows/NVIDIA acima.

- 58 testes automatizados aprovados;
- `compileall` do código e dos testes;
- GUI abriu em 1024×700 e navegou pela aba IA local;
- filtros Todos / No render / Experimentais validados;
- opt-in experimental testado sem executar downloads;
- `Selecionar necessários` confirmado como restrito aos quatro componentes integrados;
- light/dark alternados sem exceção;
- parser de progresso aceita apenas percentuais explícitos do log e não produz ETA global;
- smoke básico de render preservou 1280×720/30 fps, 2,4 s e áudio dominante de 880 Hz.

Os downloads reais de componentes não foram executados no container: o caminho gerenciado usa PowerShell/Windows e alguns pacotes experimentais têm dezenas de GB. Antes do 1.0 estável, a tela IA local ainda deve receber um smoke de instalação em uma máquina Windows limpa.

## Validação adicional — UX MegaPack Phase 7

Ambiente de desenvolvimento do MegaPack: Linux headless/Xvfb, Python 3.13. Esta validação é complementar e não substitui os testes Windows/NVIDIA da RC.

- 62 testes automatizados aprovados;
- `compileall` do código e dos testes;
- cinco estados transversais validados: info, processando, concluído, atenção e bloqueado;
- Central de atividade validada com detalhe técnico, limite de histórico, supressão de duplicata e atualização enquanto aberta;
- troca light/dark/light exercitada com a Central aberta;
- layout principal exercitado em 1024×700;
- preflight, fila recuperada, render/preview, IA local, atualização e recuperação usam a mesma semântica sem alterar `RenderSettings` ou o pipeline;
- confirmações de risco permanecem modais; conclusão normal e erros recuperáveis preferem feedback persistente;
- pacote final extraído em pasta limpa, `compileall` repetido e suíte reexecutada com 62/62 aprovações.

## Renders reais pequenos

As mídias foram geradas localmente: vídeo 320×180/24 fps com tom de 440 Hz e música WAV de 2,4 s com tom de 880 Hz.

| Fluxo | Resultado verificado |
|---|---|
| Loop musical | 1280×720, 30 fps, 2,4 s, áudio dominante 880 Hz |
| VFX Aurora + Pulso | 1280×720, 30 fps, 2,4 s, áudio dominante 880 Hz |
| Normalização | −13,95 LUFS, proteção de pico, áudio dominante 880 Hz |
| RIFE NCNN/Vulkan | 1280×720, 48 fps exatos, áudio preservado |
| Real-ESRGAN | upscale e exportação concluídos, 1280×720/24 fps |
| Demucs + VFX | baixo+bateria usados na reação; música final permaneceu 880 Hz |
| Cancelamento | árvore de processos encerrada, parcial removido e arquivo anterior preservado |
| HDR10 | BT.2020, SMPTE ST 2084 e 10-bit preservados no vídeo original sem VFX |
| VMAF | filtro libvmaf executado e relatório JSON analisado |

A confirmação por frequência demonstra que o áudio original de 440 Hz do clipe não vazou para os fluxos musicais.

## Portátil

- ZIP montado somente com código, documentação e bootstrap;
- manifesto SHA-256 gerado;
- pacote extraído em pasta limpa;
- `uv` 0.12.1 baixado e validado por SHA-256;
- Python 3.13.7 instalado dentro do pacote;
- dependências e CinePulse instalados no ambiente privado;
- PATH isolado para simular ausência de FFmpeg;
- FFmpeg 9.0 completo baixado, validado e instalado em `components\ffmpeg`;
- diagnóstico executado a partir do pacote extraído.
- atualizador preparado para baixar, verificar, instalar no reinício e restaurar a versão anterior em caso de falha;
- manifesto interno permite detectar arquivos ausentes ou alterados.

## Instalação completa RC2

- instalação limpa executada em `G:\CinePulse` sem reutilizar os componentes legados;
- Real-ESRGAN e RIFE baixados das releases oficiais e promovidos somente após SHA-256;
- PyTorch 2.11.0 CUDA 12.6 e torchaudio instalados no ambiente privado do Demucs;
- quatro pesos `htdemucs_ft` baixados e validados pelo hash completo;
- CUDA confirmada na NVIDIA GeForce RTX 4070 Laptop GPU;
- FFmpeg 9.0 privado confirmou o filtro `libvmaf`;
- diagnóstico final confirmou Real-ESRGAN, RIFE, Demucs e VMAF como instalados;
- integridade final: 55 arquivos do núcleo conferidos, nenhum ausente ou alterado;
- segunda execução concluiu em poucos segundos sem baixar novamente os componentes.

## MSI

- MSI x64 compilado com WiX 6.0.2 usando SDK .NET privado e verificado;
- banco Windows Installer validado, com as exceções documentadas do harvest per-user;
- extração administrativa real aprovada;
- launcher e manifesto de instalação encontrados dentro do MSI;
- atalhos do Menu Iniciar e da Área de Trabalho incluídos;
- instalação completa acionada automaticamente em janela visível após o MSI, usando PowerShell 7 quando disponível e registrando log permanente;
- instalação portátil validada em `G:\CinePulse`, com atalho real apontando para `G:\CinePulse\CinePulse.cmd`;
- extração administrativa não aciona downloads, preservando cenários corporativos de implantação.

O SHA-256 definitivo de cada artefato fica no manifesto externo criado ao lado do pacote, evitando inserir no próprio arquivo um hash circular e inevitavelmente desatualizado.

## Limites desta validação

- BasicVSR++, CLAP, Depth Anything, SAM 2, CoTracker, CodeFormer e LTX continuam detectados, mas não integrados ao render principal;
- não foi realizado benchmark de qualidade ou tempo em vídeo musical longo;
- assinatura Authenticode depende de certificado e fica para a distribuição pública;
- o aceite 1.0 com músicas longas, 8K/120 e a fila real será feito pelo usuário;
- a ativação pública do atualizador depende apenas do endereço definitivo `dono/repositorio` no empacotamento;
- os testes automatizados não substituem a avaliação artística dos VFX, transições e interpolação em cada clipe.

## UX MegaPack Phase 8 — validação de polish

Ambiente desta passagem: Linux/Xvfb, Tk 8.6 e FFmpeg local. Esse ambiente valida estrutura e regressão, mas **não substitui o aceite visual final no Windows**.

Validações concluídas:

- suíte automatizada: **69/69 PASS**;
- `compileall` de `src` e `tests`: PASS;
- GUI 1440×900: layout wide PASS;
- GUI 1024×700: Home, Projeto, Qualidade, Visual, Fila e IA local empilham os splits PASS;
- rodapé 1024×700: estado ocioso mostra resumo + preview + render + `Fila +` + feedback sem corte; estado ativo prioriza ações + progresso + feedback: PASS;
- preset selecionado sem aplicação permanece explicitamente diferente do preset ativo;
- aplicação de preset limpa o estado pendente;
- ajuste manual depois do preset fica marcado como `ajustes manuais`;
- F1/guia rápido abre sem bloquear o editor;
- light → dark → light com guia aberto: PASS;
- navegação por atalhos e Central de atividade: PASS;
- onboarding pode ser dispensado e persistido;
- callbacks Tk do Studio são rastreados/cancelados no encerramento; duas instâncias sequenciais no mesmo processo encerraram sem comandos Tcl órfãos;
- stop/restart rápido da animação do Visual Lab não cria cadeias concorrentes de playback;
- render básico sintético após o polish: 1280×720, 30 fps, 2,4 s, áudio presente, frequência dominante final 880 Hz: PASS.

Pendente para aceite 1.0 estável:

- checklist Windows em `WINDOWS_UX_ACCEPTANCE.md`;
- DPI real 100/125/150/200%;
- multi-monitor Windows;
- fila real com pelo menos dois renders;
- render longo no perfil principal e 8K/120 na máquina de destino.

## Core Integrity MegaPack Phase 1 — RenderPlan

Ambiente desta passagem: Linux/Xvfb, Python 3.13 e FFmpeg local. O objetivo desta fase foi centralizar as decisões do pipeline **sem ainda alterar a política de qualidade auditada**.

Validações concluídas:

- suíte automatizada: **82/82 PASS**;
- `compileall` de `src` e `tests`: PASS;
- `RenderPlan` determinístico com fingerprint/serialização: PASS;
- matriz unitária cobre master 60 fps, fonte 120 fps, Real-ESRGAN x2 target-unaware, RIFE base/final, VFX 320×180/60, HDR/10-bit e distinção ainda pendente entre Preservar/Lanczos;
- GUI abre a aba Qualidade com o novo card de plano em ambiente headless;
- preflight inclui o plano serializado e riscos com códigos da auditoria;
- worker usa o plano para master, RIFE base/final e etapa Real-ESRGAN;
- render musical sintético real: fonte 640×360/30, música WAV 2 s → saída 1280×720/60 HEVC 10-bit + AAC: PASS;
- log do render registrou fingerprint e etapa real `Master de estúdio → 1280×720/60 yuv420p`;
- relatório final registrou o mesmo fingerprint e a sequência completa de etapas.

Importante: CP-001/002/003/004/006/007 **não são marcados como corrigidos nesta Phase 1**. Eles agora são detectados e exibidos pelo contrato único; a Phase 2 começa a alterar a política para eliminá-los.

Validação do artefato empacotado:

- ZIP testado por CRC e extraído em pasta limpa: PASS;
- `compileall` no conteúdo extraído: PASS;
- suíte no conteúdo extraído: **82/82 PASS**;
- release gate no conteúdo extraído: PASS;
- GUI do conteúdo extraído abriu a aba Qualidade: PASS;
- render sintético real iniciado a partir do conteúdo extraído: 1280×720/60 HEVC 10-bit + AAC: PASS;
- fingerprint do RenderPlan presente no log desse render: PASS.

## Core Integrity MegaPack Phase 2 — preservação espacial/temporal

Ambiente desta passagem: Linux, Python 3.13 e FFmpeg 7.1.5 local. O foco foi validar a nova política target-aware sem reivindicar ainda correção de HDR/10-bit ou do canvas interno dos VFX.

Validações concluídas:

- suíte automatizada: **93/93 PASS**;
- `compileall` de `src` e `tests`: PASS;
- release gate: PASS;
- `git diff --check`: PASS;
- matriz RenderPlan: 8K/120 → 1080p/120 mantém master 1080p/120, sem RIFE e sem Real-ESRGAN;
- Real-ESRGAN é SKIP quando `contain`/`cover` não exigem upscale e RUN quando a escala realmente ultrapassa 1×;
- RIFE base é sempre SKIP e o worker não possui mais a execução dessa passagem;
- RIFE final ocorre no máximo uma vez e apenas se o FPS efetivo for menor que o destino;
- Preservar e Lanczos geram filter chains espacialmente diferentes;
- `fps`/`minterpolate` não são inseridos quando fonte e destino já possuem a mesma cadência;
- smoke FFmpeg Preservar: 320×180/120 → canvas 640×360/120, **120 frames**, sem upscale dos pixels da fonte;
- smoke FFmpeg VFX: base 120 fps + layer 60 fps → saída **120 fps / 120 frames**, comprovando remoção do retime fixo da base;
- CP-003 continua aberto para a resolução/amostragem do próprio layer VFX;
- CP-007 continua aberto para intermediários 10-bit/HDR.


## Core Integrity MegaPack Phase 3 — VFX/envelope

Ambiente: Linux, Python 3.13 e FFmpeg 7.1.5 local.

Validações concluídas:

- suíte automatizada: **103/103 PASS**;
- `compileall` de `src` e `tests`: PASS;
- release gate: PASS;
- `git diff --check`: PASS;
- RenderPlan 1920×1080/60 + VFX: internal 1920×1080/60, sem CP-003;
- RenderPlan 3840×2160/120 + VFX: internal 3840×2160/120;
- RenderPlan 7680×4320/120 + VFX: internal 3840×2160/120 + `CI-P3-VFX-8K`;
- slice de preview e slice final compartilham valores idênticos nos mesmos timestamps quando partem do mesmo envelope completo;
- cache SSD reabre análise sem nova decodificação;
- smoke FFmpeg real: base 640×360/120 + VFX target-aware → 640×360/120, 120 frames;
- análise do smoke usa WAV completo de 3 s mesmo com janela renderizada de 1 s;
- smoke real do worker preview → final: preview de 1 s analisa música completa de 2,4 s e final reutiliza `cache RAM` da mesma análise;
- CP-007 permanece explicitamente pendente para Phase 4;
- inspeção perceptiva 8K a 100% permanece portão manual para 1.0.

## Core Integrity MegaPack Phase 4 — color pipeline

Ambiente: Linux/Xvfb, Python 3.13 e FFmpeg 7.1.5 local com `zscale`, `tonemap`, libx265 e FFV1.

Validações concluídas:

- suíte automatizada: **115/115 PASS**;
- `compileall` de `src` e `tests`: PASS;
- release gate: PASS;
- HDR10 limpo → HDR10/BT.2020/PQ/10-bit: PASS;
- HDR10 em modo musical, obrigando master intermediário → HDR10/BT.2020/PQ/10-bit: PASS;
- HDR10 + VFX → SDR BT.709/10-bit, sem flag HDR: PASS;
- SDR10 em modo musical → SDR10 após master: PASS;
- SDR10 full range → `color_range=pc` preservado: PASS;
- VFX graph `yuv420p10le` + FFV1: PASS;
- smoke worker básico: PASS;
- smoke áudio/loudness: PASS;
- smoke VFX: PASS;
- SDR 8-bit final codificado como Main/yuv420p, sem promoção fictícia Main10: PASS;
- BT.2020 + transfer SDR não é classificado automaticamente como HDR: PASS;
- RenderPlan atualizado para `core-integrity-phase4-color-pipeline`, com CP-007 em `resolved_audit_codes`.

Portões ainda manuais:

- monitor HDR real e padrões de luminância;
- avaliação perceptiva de highlight roll-off/tone mapping;
- NVENC Main10 no Windows da máquina-alvo;
- HDR10 mastering metadata avançada (MaxCLL/MaxFALL/master-display);
- render longo e 8K/120 reais.


## Core Integrity MegaPack Phase 7 — Verification & Render History

Ambiente: Linux/Xvfb, Python 3.13 e FFmpeg/FFprobe locais.

Validações concluídas:

- suíte automatizada: **159/159 PASS**;
- `compileall` de `src` e `tests`: PASS;
- quick verify unitário cobre resolução, FPS, CFR, frame count, codec, áudio esperado/inesperado, canais, sample rate e sync;
- `tests/integration_verification.py`: worker real + deep verify em saída 1280×720/30: 72/72 quadros, CFR `true`, HEVC/AAC, 48 kHz, decode até EOF, A/V delta 0.000 s: PASS;
- worker real com deep verify criou `job.json`, `render.log`, `plan.json`, `contracts.json` e `verification.json`: PASS;
- relatório final recebeu seção VERIFICAÇÃO TÉCNICA e caminho do histórico: PASS;
- matriz MP4/MOV/MKV/WebM reexecutada com a nova verificação: PASS;
- migração de queue legado para schema 2 e presets legado para schema 1: PASS;
- backup `.bak`, escrita atômica e rejeição de schema futuro: PASS;
- export de suporte redigindo paths absolutos: PASS.

Pendente para fases posteriores: integração automática dos `integration_*.py` ao CI (Phase 9), mutex/instância e hardening de distribuição (Phase 8).


## Core Integrity MegaPack Phase 8 — Runtime & Distribution

Ambiente desta passagem: Linux, Python 3.13 e ferramentas Python/FFmpeg locais. O objetivo foi validar contratos de distribuição que podem ser comprovados fora do Windows sem fingir execução de MSI/PowerShell/SignTool.

Validações concluídas:

- suíte automatizada: **176/176 PASS**;
- `compileall` de `src`, `tests` e `scripts`: PASS;
- release gate Python: PASS;
- geração SBOM: CycloneDX 1.5, componentes diretos/hashes esperados: PASS;
- portable marker versus modo instalado: PASS;
- `InstanceGuard` bloqueia segunda instância e recupera stale lock em backend testável: PASS;
- smoke de duas instâncias reais do entrypoint sob Xvfb: primeira permanece aberta, segunda encerra com log `Segunda instância bloqueada`: PASS;
- resolver único prioriza `pwsh` em teste controlado: PASS;
- bootstrap contém `--python-preference only-managed`, remove `Find-SystemPython` e separa roots de runtime/componentes: PASS;
- `requirements.lock` contém hash obrigatório: PASS;
- WiX usa versão dinâmica, launchers instalados e `CinePulseIcon`: PASS estático;
- `assets/cinepulse.ico` possui cabeçalho ICO real e múltiplos tamanhos gerados: PASS estrutural;
- hook Authenticode está presente no build MSI e não marca o artefato como assinado sem certificado: PASS estático/unitário;
- verificação de assinatura destacada possui caminho de sucesso e falha fatal cobertos por testes: PASS;
- RenderPlan atualizado para `core-integrity-phase8-runtime-distribution`, com CP-019/CP-020 ainda em `pending_audit_codes`: PASS.

Não executado neste ambiente e obrigatório para o aceite Windows/Phase 9:

- parsing/executação real dos scripts PowerShell;
- build WiX/MSI real;
- install → upgrade → repair → uninstall;
- named mutex Win32 em processo real;
- runtime em Windows limpo sem Python/FFmpeg do sistema;
- atalhos, Apps e Recursos e ícone no shell;
- update/rollback com uma chave de assinatura CinePulse real;
- Authenticode com certificado real;
- lock transitivo completo de Demucs/PyTorch/SoundFile por wheel/hash.

## Core Integrity MegaPack Phase 9 — CI & Release Gates

Ambiente desta passagem: Linux/Xvfb, Python 3.13.5 e FFmpeg 7.1.5. O objetivo foi transformar os smokes acumulados em portões reproduzíveis e preparar os gates Windows/GPU sem reivindicar execução que não ocorreu neste ambiente.

Validações concluídas localmente:

- suíte unitária: **185/185 PASS**;
- `scripts/release_gate.py`: PASS;
- `compileall` de `src`, `tests` e `scripts`: PASS;
- workflows `quality.yml`, `release-candidate.yml` e `gpu-acceptance.yml`: parse YAML PASS;
- `ci_gate.py --profile source`: PASS, com relatório JSON e SBOM;
- `ci_gate.py --profile cpu`: PASS para smoke básico, áudio, cancelamento/recovery, delivery matrix, Storage Engine, deep verification e chunks neurais;
- `ci_gate.py --profile media`: PASS para VFX, HDR10, HDR→SDR com VFX, SDR10 e full range;
- cancelamento Linux revelou um defeito real: subprocessos FFmpeg/IA/RIFE/Demucs não estavam isolados em nova sessão POSIX; `popen_group_kwargs()` agora é aplicado aos processos canceláveis e `integration_cancel.py` passa sem encerrar o runner;
- ações de CI possuem timeout por etapa para impedir jobs presos indefinidamente;
- scripts de build aceitam Python explícito da máquina de build sem alterar a exigência de runtime gerenciado para o produto distribuído;
- `Test-Updater.ps1` passou a aceitar a versão do gate em vez de fixar RC5;
- foi criado gate MSI install/repair/uninstall protegido por `CINEPULSE_CI_ALLOW_MSI_LIFECYCLE=1`, com bootstrap suprimido no runner descartável.

Não executado neste ambiente:

- PowerShell parser real;
- build WiX/MSI real;
- install/repair/uninstall MSI real;
- updater PowerShell real;
- named mutex Win32;
- Authenticode/Minisign com credenciais reais;
- RIFE/Real-ESRGAN/Demucs reais em GPU NVIDIA.

Esses itens agora possuem workflows/gates explícitos e só podem ser considerados aprovados após uma execução verde no ambiente correspondente.


## Final Audit & Release Candidate Acceptance

Passagem final local em Linux/Xvfb após a Phase 9:

- pytest direto: **187/187 PASS** após declarar `pythonpath = ["src"]`;
- unittest com `PYTHONPATH=src`: **187/187 PASS**;
- release gate Python: PASS;
- compileall: PASS;
- `final_audit.py`: PASS;
- texto “GPU automática” removido da interface; `Aceleração automática` agora explicita que somente etapas compatíveis usam GPU;
- RenderPlan expõe o dispositivo por etapa e CP-016 deixa `pending_audit_codes`;
- `studio.py`: 6.149 linhas; `loop_engine.py`: 1.067 linhas — CP-032/CP-033 permanecem abertos;
- `requirements.lock` continua contendo apenas NumPy como runtime principal hash-locked — CP-020 permanece parcial;
- `update-channel.json` não possui manifesto de produção configurado nesta cópia — CP-019 permanece parcial.

Decisão: código apto a seguir para Release Candidate controlado, condicionado ao gate Windows/NVIDIA. `1.0.0` estável ainda não aprovado.
