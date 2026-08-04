# Arquitetura

## Camadas atuais

- `app.py`: inicialização e log persistente;
- `paths.py`: separa código, dados do usuário e componentes portáteis;
- `studio.py`: interface e orquestração migradas do aplicativo funcional;
- `loop_engine.py`: análise de mídia e compatibilidade com o fluxo clássico;
- `vfx.py` e `aurora.py`: geração visual reativa;
- `ai_suite.py`: inventário local das IAs;
- `component_manager.py`: catálogo e instalação verificada;
- `diagnostics.py`: diagnóstico reproduzível sem nomes de projetos.

## Próxima modularização

O arquivo `studio.py` ainda é grande porque foi preservado para reduzir risco durante a migração. A divisão seguinte deverá extrair, com testes, `ui`, `render_pipeline`, `ffmpeg`, `queue`, `presets`, `audio` e `quality`. Não reescrever tudo de uma vez.

