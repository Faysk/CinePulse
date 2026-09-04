# CinePulse 1.1.0 — Installer v2 / Self-Contained Runtime

## Objetivo

O CinePulse 1.1.0 muda o contrato da distribuição Windows: a pasta escolhida pelo usuário passa a ser a raiz efetiva da instalação e do runtime do aplicativo.

Exemplo: se o usuário instalar em `D:\CinePulse`, o CinePulse mantém sob essa raiz o runtime Python, componentes, modelos, dados, caches e temporários do processo. O projeto não depende do Python do sistema e não instala CUDA Toolkit globalmente.

## Contrato de isolamento

A instalação direciona para a raiz do CinePulse:

- `.runtime` — Python gerenciado e runtimes privados;
- `components` — FFmpeg, Real-ESRGAN, RIFE e componentes locais;
- `data` — logs, preferências e dados mutáveis;
- `cache` — caches de uv/pip, Torch, Hugging Face, Numba, Matplotlib e bytecode;
- `temp` — `TEMP`, `TMP`, `TMPDIR` e temporários observados pelo Python.

O launcher define `PYTHONNOUSERSITE=1` para impedir que pacotes do perfil Python global contaminem o runtime privado.

A preferência de GPU NVIDIA é expressa somente na árvore de processos do CinePulse. O Installer v2 não grava `HKCU\Software\Microsoft\DirectX\UserGpuPreferences`.

## Runtime de referência

- CPython 3.14.7
- NumPy 2.5.2 no core lock Windows validado
- PyTorch 2.13.0 + CUDA 13.2 (`2.13.0+cu132`)
- Demucs 4.1.0
- SoundFile 0.14.0
- TorchAudio não é dependência obrigatória do runtime mínimo

Os locks são gerados para Windows x64 / Python 3.14.7 e usam hashes. O core lock é provado por instalação real em venv limpo; o lock neural é resolvido contra o índice CUDA oficial do PyTorch.

## MSI

O MSI expõe seleção de diretório via `WixUI_InstallDir` e usa `INSTALLFOLDER` como diretório selecionável.

O gate automatizado executa em Windows descartável:

1. build do ZIP portátil;
2. build e validação do MSI;
3. instalação em pasta não padrão;
4. repair preservando a pasta escolhida;
5. uninstall removendo o payload principal.

O bootstrap pesado é suprimido apenas no teste de lifecycle do MSI; o resolvedor neural é validado separadamente no mesmo acceptance.

## Evidência já obtida durante o desenvolvimento

O acceptance Windows anterior provou:

- `tempfile` usando `CinePulse\temp`;
- stack neural resolvendo 33 pacotes em Python 3.14.7;
- `torch==2.13.0+cu132` pelo índice oficial CUDA 13.2;
- MSI criado e validado;
- `install=pass repair=pass uninstall=pass` em diretório customizado.

Durante a auditoria dos logs foi encontrado um falso-verde: o `requirements.lock` ainda continha um hash de wheel do NumPy para CPython 3.13 e o PowerShell não encerrava o step no primeiro erro de comando nativo. O 1.1.0 corrige os dois problemas:

- locks agora são regenerados do zero para Python 3.14.7/Windows x64;
- o core lock foi instalado com `--require-hashes` e importou NumPy 2.5.2;
- workflows de acceptance/release verificam `$LASTEXITCODE` após comandos nativos críticos.

## Política de release

O Installer v2 somente pode ser promovido a `main` quando o acceptance Windows do SHA final estiver verde. O workflow `Release Candidate` repete os contratos de runtime, isolamento, neural lock, ZIP, updater e MSI em PR/tag.

Capacidades de recuperação genérica continuam Preview/shadow e não são promovidas a Stable apenas por esta release do instalador.

## Limite externo inevitável

O driver NVIDIA continua fora da pasta do CinePulse porque é um driver de dispositivo do Windows. O CinePulse não instala nem modifica esse driver automaticamente. O runtime CUDA usado pelo PyTorch permanece privado ao ambiente Python do projeto.
