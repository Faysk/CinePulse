# Validação da versão 1.0.0-rc.3

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
