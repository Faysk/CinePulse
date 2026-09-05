from pathlib import Path


def prepend_changelog() -> None:
    path = Path("CHANGELOG.md")
    text = path.read_text(encoding="utf-8")
    if "## 1.1.3 — 2026-09-05" in text:
        return
    marker = "# Changelog\n\n"
    if not text.startswith(marker):
        raise SystemExit("CHANGELOG header anchor not found")
    entry = '''## 1.1.3 — 2026-09-05

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

'''
    path.write_text(marker + entry + text[len(marker):], encoding="utf-8", newline="\n")


def polish_studio() -> None:
    path = Path("src/cinepulse/studio.py")
    text = path.read_text(encoding="utf-8")

    old_ai = '''                    temp_paths, temp_dirs, stage_threads("neural_gpu", gpu_active=True), progress_base, 20,
                    cache_source_video=settings.video, cache_quota_gb=settings.cache_quota_gb,
                                    chunk_budget_gb=realesrgan_budget.chunk_budget_gb,
                    overlap_extract=realesrgan_budget.overlap_extract,
                    overlap_pack=realesrgan_budget.overlap_pack,
                    runtime_guard=h5_ai_guard,
)'''
    new_ai = '''                    temp_paths, temp_dirs, stage_threads("neural_gpu", gpu_active=True), progress_base, 20,
                    cache_source_video=settings.video,
                    cache_quota_gb=settings.cache_quota_gb,
                    chunk_budget_gb=realesrgan_budget.chunk_budget_gb,
                    overlap_extract=realesrgan_budget.overlap_extract,
                    overlap_pack=realesrgan_budget.overlap_pack,
                    runtime_guard=h5_ai_guard,
                )'''
    if old_ai not in text:
        raise SystemExit("Studio Real-ESRGAN formatting anchor not found")
    text = text.replace(old_ai, new_ai, 1)

    old_rife = '''                        settings.use_cpu, stage_threads("neural_gpu", gpu_active=True), temp_paths, progress_base, base_rife_weight,
                        color_plan=color_plan,
                                            chunk_budget_gb=rife_budget.chunk_budget_gb,
                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
                        runtime_guard=h5_rife_guard,
)'''
    new_rife = '''                        settings.use_cpu,
                        stage_threads("neural_gpu", gpu_active=True),
                        temp_paths,
                        progress_base,
                        base_rife_weight,
                        color_plan=color_plan,
                        chunk_budget_gb=rife_budget.chunk_budget_gb,
                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
                        runtime_guard=h5_rife_guard,
                    )'''
    if old_rife not in text:
        raise SystemExit("Studio base RIFE formatting anchor not found")
    text = text.replace(old_rife, new_rife, 1)

    old_final = '''                        settings.use_cpu, stage_threads("neural_gpu", gpu_active=True), temp_paths, progress_base, rife_weight,
                        color_plan=color_plan,
                                            chunk_budget_gb=rife_budget.chunk_budget_gb,
                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
                        runtime_guard=h5_rife_guard,
)'''
    new_final = '''                        settings.use_cpu,
                        stage_threads("neural_gpu", gpu_active=True),
                        temp_paths,
                        progress_base,
                        rife_weight,
                        color_plan=color_plan,
                        chunk_budget_gb=rife_budget.chunk_budget_gb,
                        overlap_extract=(rife_budget.overlap_extract and not settings.use_cpu),
                        runtime_guard=h5_rife_guard,
                    )'''
    if old_final not in text:
        raise SystemExit("Studio final RIFE formatting anchor not found")
    text = text.replace(old_final, new_final, 1)
    path.write_text(text, encoding="utf-8", newline="\n")


prepend_changelog()
polish_studio()
print("final Preview polish applied")
