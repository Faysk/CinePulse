<p align="center"><img src="assets/cinepulse-mark.svg" width="128" alt="CinePulse"></p>

# CinePulse

**Local AI video enhancement and music-reactive visual studio.**

CinePulse transforma clipes curtos e músicas em vídeos contínuos, melhora vídeos existentes e cria VFX sincronizados com o áudio. O processamento acontece localmente e o usuário escolhe entre velocidade, qualidade e uso de recursos.

> Estado Stable: `1.1.3`. O instalador Windows 1.1 é autocontido por diretório: Python, runtime, componentes, modelos, dados, caches e temporários ficam sob a pasta do CinePulse escolhida pelo usuário. A 1.1.3 corrige o planejamento/materialização de armazenamento em loops longos, interpola o clipe reutilizável com RIFE antes da expansão temporal e evita intermediário VFX lossless full-length quando a entrega pode ser fundida. Real-ESRGAN, RIFE, Demucs e VMAF integram o pipeline principal. A recuperação genérica de renders permanece em **Preview/shadow por padrão** até completar os gates físicos específicos; o fluxo estável não anuncia retomada genérica como capacidade aceita.

> O branch/PR de **Restauração Preview** é experimental e separado do Stable: inclui detecção/revisão de textos, QR codes e overlays persistentes, reconstrução temporal, controles de restauração de cor e envelope estrutural de entrega de até 12K/120. 8K+/alta cadência e 12K/120 continuam sem selo de desempenho físico até execução no hardware real.

## O que já funciona no Stable

- loop de vídeo durante toda a música, removendo o áudio original do clipe;
- vídeo original ou formatos 16:9, 9:16, IMAX digital e Cinema Wide;
- perfil estável com teto de contrato em 8K/120 fps; 8K/120 é classificado como carga extrema e sua aceitação física depende do hardware/runner validado, enquanto 10K/12K e 144/240/480 fps permanecem experimentais e bloqueados no perfil estável;
- preview de 1 a 30 segundos e comparação A/B;
- upscale Lanczos e Real-ESRGAN;
- interpolação FFmpeg, GPU NVIDIA quando disponível e modo CPU;
- interpolação neural RIFE com fallback automático e política conservadora para UHD/extremo;
- VFX dirigidos opcionalmente por stems do Demucs;
- aurora, espectro, barras, onda, círculo, partículas, pulso e energia musical;
- combinação de efeitos, cor, ocupação, intensidade e foco por faixa musical;
- transições de loop, presets, fila, estimativa de espaço por etapa, progresso, quick/deep verify e relatório final;
- scratch disk configurável, cache com quota/LRU e processamento Real-ESRGAN/RIFE em lotes para limitar temporários;
- histórico técnico persistente por render (`job.json`, log, RenderPlan, contratos e verificação), com fila/presets versionados e migráveis;
- dados, cache, componentes e previews isolados do código-fonte;
- intermediários visuais lossless, promoção atômica de artefatos e normalização LUFS em duas passagens;
- infraestrutura de recuperação crash-safe com manifesto/lease/checkpoints; descoberta/retomada genérica fica em Preview/shadow até aceite físico;
- gerenciador de IA local com capacidades integradas separadas de arquivos experimentais, seleção segura, licenças e instalação verificada;
- dependências core e neurais fixadas em locks com hashes no pacote distribuído;
- instalador Windows com diretório selecionável e ciclo install/repair/uninstall validado em pasta não padrão.

## Restauração Preview

No branch experimental, a área **Restauração Preview** permanece isolada de `RenderSettings` e do botão de render Stable. O usuário analisa a fonte, revisa as regiões candidatas antes da remoção e exporta para um arquivo separado por promoção atômica. A análise de overlays é vinculada à identidade do arquivo (caminho resolvido, tamanho e `mtime_ns`); se a fonte for substituída no mesmo caminho, o resultado antigo é invalidado e uma nova análise é exigida.

O export temporal usa janela RGB limitada e fail-closed para fontes com forte indício de VFR, memória temporal acima do limite ou FFprobe indisponível. Cancelamento encerra decoder/encoder em árvore e remove o temporário, sem substituir uma saída anterior válida.

## Início rápido no Windows

1. Para a experiência mais simples, instale o MSI e escolha a pasta desejada no assistente. O CinePulse mantém o runtime e os dados dessa instalação sob essa raiz.
2. No pacote portátil, extraia o ZIP e execute `Install-CinePulse.cmd` uma vez. A janela mostra as etapas, grava `data/logs/installer.log` e cria o atalho da Área de Trabalho.
3. No portátil, abra por `CinePulse.cmd`; no MSI, use os atalhos instalados, que acionam o launcher dedicado. A interface só abre quando os componentes obrigatórios estiverem prontos.

### Contrato autocontido do 1.1

Se a instalação for feita, por exemplo, em `D:\CinePulse`, o CinePulse direciona para essa raiz:

- `.runtime` — Python gerenciado e runtimes privados;
- `components` — FFmpeg, Real-ESRGAN, RIFE e componentes locais;
- `data` — configurações, logs e dados mutáveis;
- `cache` — caches de uv/pip, Torch, Hugging Face, Numba, Matplotlib e bytecode;
- `temp` — `TEMP`, `TMP`, `TMPDIR` e temporários do Python/processamento.

O processo também usa `PYTHONNOUSERSITE=1`, evitando consumir pacotes Python do perfil global do usuário. O CinePulse não instala CUDA Toolkit globalmente; o runtime CUDA necessário ao caminho neural vem com o PyTorch fixado pelo projeto. O driver NVIDIA continua sendo responsabilidade do Windows/usuário porque é um driver de sistema.

O runtime de referência do instalador 1.1 usa **CPython 3.14.7**, core lock hashado e stack neural validada com **PyTorch 2.13.0 + CUDA 13.2**, **Demucs 4.1.0** e **SoundFile 0.14.0**. TorchAudio não faz parte do runtime mínimo exigido.

Para reutilizar os componentes da instalação de desenvolvimento existente, sem copiá-los para o Git:

```powershell
.\scripts\Migrate-LocalComponents.ps1 -SourceTools 'G:\edit\tools'
```

Não execute essa migração durante um render importante; ela movimenta vários gigabytes pelo disco.

## Fluxo recomendado da interface

1. Use **Projeto** para escolher vídeo/música, conferir metadados e enquadramento.
2. Experimente VFX em **Início** ou **Visual e transições**; esse preview é leve e serve para descoberta.
3. Revise **Qualidade e saída** para escala, FPS, VRAM e compatibilidade.
4. Gere um **preview renderizado** curto antes do vídeo final.
5. Use a **Fila** para processar variações sequencialmente.

`F1` abre os primeiros passos a qualquer momento. `Ctrl+1` a `Ctrl+6` navegam pelas abas; os demais atalhos aparecem no próprio guia. Tema, última aba e geometria da janela são lembrados localmente.

## Privacidade

O CinePulse é local-first. Vídeos, músicas e resultados não são enviados automaticamente para servidores. O histórico de render pode registrar **telemetria local de hardware** (CPU, RAM, disco e, quando disponível, métricas NVIDIA como utilização, VRAM, potência e temperatura) para diagnóstico e ajuste conservador do pipeline; esses dados ficam no computador e não são transmitidos automaticamente. Relatórios só são compartilhados quando o usuário decide fazê-lo. Veja [PRIVACY.md](docs/PRIVACY.md).

## Componentes opcionais

Modelos e binários não ficam neste repositório. O catálogo informa finalidade e licença, e o gerenciador somente aceita download automático quando a versão e o SHA-256 estiverem fixados. Veja [AI_COMPONENTS.md](docs/AI_COMPONENTS.md).

## Limites reais

O perfil estável atual é conservador: possui teto de contrato em 8K/120 fps, mas cargas extremas continuam condicionadas à capacidade real do encoder/GPU e aos gates físicos do hardware alvo. 10K/12K e 144/240/480 fps permanecem experimentais até existir matriz comprovada de encoder/hardware. O tempo, o tamanho e a compatibilidade dependem de resolução de origem, duração, GPU, VRAM, codec e plataforma de destino. Interpolação não cria detalhe verdadeiro; upscale não recupera informação que não existe na fonte.

A recuperação genérica de jobs é entregue em modo Preview/shadow por padrão. O código mantém manifestos duráveis, checkpoints, lease/heartbeat, validação e mecanismos de migração, mas o Stable 1.1 não promete retomada genérica pela interface sem o aceite físico correspondente.

O canal remoto de auto-update do portátil fica desativado por padrão no build estável. Quando ativado para distribuição, ele exige manifesto assinado e configuração explícita de confiança; instalações MSI continuam sendo atualizadas por um MSI mais novo.

## Desenvolvimento

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Consulte [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) e o [roadmap](docs/ROADMAP.md).
Os resultados reproduzíveis da versão atual estão em [VALIDATION.md](docs/VALIDATION.md).
Para renders interrompidos, consulte o [índice de recuperação](docs/RECOVERY_INDEX.md), que separa o pós-mortem real, o runbook técnico e o desenho/rollout da retomada genérica.

Para montar o ZIP portátil reproduzível:

```powershell
.\scripts\Build-Portable.ps1
```

O pacote-base não embute modelos. Na primeira abertura, baixa um Python gerenciado pelo CinePulse, FFmpeg, Real-ESRGAN, RIFE, PyTorch/Demucs e os pesos usados. O runtime distribuído não usa o Python do sistema como base. Dependências core e neurais são resolvidas a partir dos locks hashados incluídos no pacote; downloads bootstrap com hash conhecido são verificados antes de liberar a interface.

Para gerar também o instalador Windows:

```powershell
.\scripts\Build-Msi.ps1
```

Para publicar um canal remoto do portátil, use `-Repository 'dono/CinePulse'` junto de chaves/Minisign válidos; builds estáveis sem essa configuração mantêm o auto-update remoto desativado. Instalações MSI atualizam o núcleo por um MSI mais novo, não pelo self-updater portátil.

## Licença

O código próprio do CinePulse usa a licença MIT. FFmpeg, modelos e ferramentas externas mantêm suas respectivas licenças e não são relicenciados pelo projeto. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de distribuir um pacote.
