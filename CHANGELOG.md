# Changelog

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
