# Arquitetura

## Camadas atuais

- `app.py`: inicialização e log persistente;
- `paths.py`: separa código, dados do usuário e componentes portáteis;
- `render_plan.py`: fonte única e pura das etapas de render, specs, fingerprint e riscos estruturais;
- `color_pipeline.py`: contrato HDR/SDR, bit depth, gamut, transfer, range, tone mapping, dithering e metadata de saída;
- `studio.py`: interface e orquestração migradas do aplicativo funcional;
- `loop_engine.py`: análise de mídia e compatibilidade com o fluxo clássico;
- `vfx.py`: VFX ativos target-aware; `vfx_policy.py`: canvas/cadência; `music_envelope.py`: análise musical completa/cache; `aurora.py`: compatibilidade do fluxo clássico;
- `ai_suite.py`: inventário local das IAs;
- `rife_recovery.py`: reconstrução do contrato de um job RIFE interrompido, checkpoint por segmento, concatenação com timeline exata, entrega e promoção atômica;
- `rife_black_repair.py`: auditoria e substituição atômica de segmentos RIFE com o defeito preto determinístico observado em 8K;
- `matroska_quality.py`: inspeção estrutural rápida dos pacotes FFV1/Matroska usada pelo gate específico de recuperação;
- `component_manager.py`: catálogo e instalação verificada;
- `diagnostics.py`: diagnóstico reproduzível sem nomes de projetos;
- `ui/tokens.py`: design tokens compartilhados;
- `ui/preview.py`: preview leve, frame de demonstração/extração e composição VFX;
- `ui/visual_lab.py`: helpers puros de variações, reatividade demonstrativa e transições;
- `ui/visual_view.py`: construção Tk da aba Visual e transições, fora do `studio.py`;
- `ui/project_lab.py`: leitura de metadados para UX e prévia geométrica de enquadramento;
- `ui/project_view.py`: construção Tk da aba Projeto, fora do `studio.py`;
- `ui/quality_lab.py`: estimativas consultivas de carga, escala, FPS, VRAM e tamanho;
- `ui/quality_view.py`: construção Tk da aba Qualidade e saída;
- `ui/queue_lab.py`: apresentação testável de estado, perfil, progresso e agrupamento da fila;
- `ui/queue_view.py`: construção Tk do workspace da Fila;
- `ui/ai_lab.py`: contrato visual de capacidades integradas/experimentais, licenças, seleção e progresso;
- `ui/ai_view.py`: construção Tk do gerenciador de IA local;
- `ui/feedback_lab.py` / `ui/feedback_view.py`: semântica global de estados e Central de atividade;
- `ui/polish_lab.py`: estado de UI, geometria segura, compactação e atalhos;
- `ui/polish_view.py`: onboarding, guia rápido e registro dos splits responsivos;
- `ui/platform_support.py`: hooks best-effort de DPI do Windows.

## Próxima modularização

O arquivo `studio.py` ainda é grande porque foi preservado para reduzir risco durante a migração. O Core Integrity MegaPack iniciou a extração do domínio técnico com `render_plan.py`: UI, preflight e worker compartilham o mesmo modelo de decisão. Na Phase 2 esse contrato passou a impor preservação espacial/temporal, Real-ESRGAN target-aware e RIFE one-shot. Na Phase 3 o caminho ativo de VFX ganhou política target-aware e envelope musical compartilhado/cacheado. A Phase 4 extraiu a política de cor para `color_pipeline.py`, mantendo no `studio.py` apenas a orquestração FFmpeg enquanto a futura modularização move a execução para `pipeline`/`encoders`. `aurora.py` permanece associado ao fluxo clássico que será isolado na futura limpeza CP-033.

## Recuperação de renders longos

O recuperador RIFE foi criado e validado depois de uma interrupção física em um render 8K/120. Ele opera sobre o layout de chunks da Phase 6, mas ainda não é o mecanismo genérico da fila.

O contrato técnico é:

1. reconstruir identidade e expectativa a partir do histórico, fonte, cache e chunks;
2. aceitar como progresso somente segmentos contíguos já validados;
3. gerar cada nova unidade em caminho parcial e promovê-la atomicamente;
4. persistir fase e contagens em checkpoint atômico;
5. auditar o defeito visual conhecido antes do master;
6. derivar a timeline da contagem exata de pacotes;
7. reutilizar master ou entrega órfã somente depois de validar o contrato atual;
8. verificar a entrega antes de trocar o nome parcial pelo final.

Os módulos de recuperação não apagam automaticamente cache, segmentos ou parciais rejeitados. A descoberta automática desses jobs e a apresentação na interface permanecem trabalho futuro. Consulte [Recuperação de renders](RECOVERY_INDEX.md), [Programa de robustez](RECOVERY_HARDENING_PROGRAM.md) e [Manifesto/máquina de estados](RECOVERY_MANIFEST_AND_STATE_MACHINE.md).
