# Roadmap

## Fechado no candidato 1.0

- loop musical e melhoria de vídeo original;
- preview, comparação A/B, presets e fila recuperável;
- formatos horizontal, vertical, IMAX e Cinema Wide;
- VFX musicais personalizáveis, direção por frequências e stems do Demucs;
- Real-ESRGAN, RIFE com fallback, normalização LUFS, HDR e VMAF;
- pré-verificação de entrada, escrita, espaço, VRAM, resolução e FPS;
- saída atômica, cancelamento da árvore de processos e recuperação após interrupção;
- modo portátil, diagnóstico, integridade, atualizador com rollback e portão de release.

## Aceite do usuário para 1.0 estável

- preview com vídeo e música reais;
- render musical longo no perfil de uso principal;
- render 8K/120 fps na máquina de destino;
- fila com mais de um projeto;
- conferência visual de transição, VFX, cor e reação musical.

## Core Integrity MegaPack — consolidação antes do 1.0 estável

- Phase 1: `RenderPlan` como fonte única de verdade — concluída;
- Phase 2: preservar resolução/FPS e tornar Real-ESRGAN/RIFE target-aware — concluída;
- Phase 3: VFX escaláveis e envelope musical único — concluída;
- Phase 4: color pipeline 10-bit/HDR/SDR explícito — concluída;
- Phase 5: codecs, contêineres, áudio e perfis de entrega — concluída;
- Phase 6: storage engine, scratch, chunking e cache LRU — concluída;
- Phase 7: verificação profunda e histórico persistente por render — concluída;
- Phase 8: runtime, MSI/portátil, locks, assinatura-ready e SBOM — concluída em código;
- Phase 9: CI/release gates de integração e aceite Windows — concluída em código;
- Final Audit & RC Acceptance: concluída em código; gate físico Windows/NVIDIA pendente.

Novas IAs permanecem fora do caminho crítico até a consolidação técnica acima. A promoção para `1.0.0` exige ainda o aceite físico documentado em `RC_ACCEPTANCE_CHECKLIST.md`.

## Depois da 1.0 / infraestrutura opcional

- assinatura Authenticode operacional quando houver certificado de distribuição;
- matriz comunitária de GPUs e tempos de render;
- BasicVSR++, CLAP, Depth Anything, SAM 2, CoTracker, CodeFormer e LTX somente após integração, licença e validação próprias;
- novas extensões de VFX sem aumentar a complexidade do fluxo principal.
