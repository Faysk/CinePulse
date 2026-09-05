# CinePulse 1.2.0 — Preview Labs + One-click Update

CinePulse 1.2.0 reúne o núcleo Stable já validado com três grandes áreas novas entregues de forma isolada e conservadora: **atualização pelo próprio aplicativo**, **Restauração Preview** e **Overlay Composer / Music Visualizer Preview**, além do Hardware Utilization MegaPack H0–H8.

## Atualização dentro do CinePulse

- Ao abrir, o CinePulse faz uma consulta curta e assíncrona à release Stable mais recente no GitHub.
- Se houver uma versão final nova, aparece `Atualizar vX.Y.Z` sem bloquear a interface.
- Um clique baixa o asset correto para MSI ou Portable, valida origem e SHA-256, aguarda render/fila/instalação de IA terminar e então aplica a atualização.
- O MSI usa MajorUpgrade e reabre o launcher instalado; o Portable reutiliza a transação existente com manifesto, backup, verificação pós-cópia e rollback.
- Falha de rede na checagem automática é silenciosa e não impede o uso local.
- Usuários que ainda estão na 1.1.3 precisam instalar a 1.2.0 uma última vez pelo método atual; a 1.1.3 não possui o código do novo updater. Depois disso, versões Stable futuras podem ser descobertas pelo próprio CinePulse.

## Restauração Preview

- Detecta e permite revisar textos, QR codes e overlays persistentes antes da remoção.
- Reconstrução temporal e restauração de cor usam guardas fail-closed para fonte alterada, VFR, memória e baixa confiança.
- Export Preview é separado do Render Stable, cancelável e promovido atomicamente.
- O envelope estrutural inclui planejamento experimental até 12K/120, sem transformar isso em promessa física de desempenho.

## Hardware Utilization MegaPack H0–H8

- Telemetria local por etapa para CPU, RAM, disco e métricas NVIDIA quando disponíveis.
- Scheduler de CPU, tuning de Real-ESRGAN/RIFE, headroom RAM/VRAM/NVMe e overlap limitado por backpressure.
- NVDEC/CUDA/NVENC e compositor GPU são **evidence-gated**: capacidade detectada não é permissão para substituir o caminho de referência.
- TensorRT continua opcional e Preview-only, condicionado a uma baseline NCNN aprovada para a mesma máquina.
- Overnight mede trabalho neural realmente concluído; temperatura alta isoladamente não reduz carga se o throughput continua melhor e estável.

## Overlay Composer / Music Visualizer Preview

- Layers PNG, GIF, APNG, WebP e vídeo com alpha.
- X/Y, escala, opacidade, z-order, blends, rotação, loop, spin, pulse e reação a beat.
- Waveform, spectrum e visualizador circular, com binding `master/vocals/drums/bass/other`.
- Save/load, preview limitado para a interface e export CPU determinístico como referência de correção.
- Stems dirigem a reatividade visual e não substituem silenciosamente a trilha final.

## Segurança, recuperação e distribuição

- Quality, Recovery Reliability, Installer v2 Acceptance e Release Candidate continuam sendo gates permanentes.
- Cancelamento por árvore de processos, `AtomicOutput`, recuperação, locks hashados, build Portable, MSI e install/repair/uninstall permanecem parte da aceitação.
- O updater aceita apenas release Stable final `x.y.z`, asset esperado da release oficial e SHA-256 válido; o fallback `SHA256SUMS.txt` precisa pertencer à mesma release.
- A consulta automática de versão e seus metadados normais de rede estão documentados em `docs/PRIVACY.md`.

## O que ainda não é uma promessa física

Esta release **não** declara PASS físico para RTX 4070, utilização sustentada de GPU/VRAM/NVMe, CUDA/TensorRT, 8K/120 ou 12K/120 apenas porque o código e o CI hospedado passaram. Esses gates continuam separados e exigem execução real no hardware alvo. Até existir evidência exata, os caminhos experimentais permanecem bloqueados, Preview-only ou com fallback conservador.
