# Changelog

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
