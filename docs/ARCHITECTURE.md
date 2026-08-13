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

