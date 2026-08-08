# Changelog

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
