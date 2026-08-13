# UX Phase 2 — Visual Lab v1

Status: **implementado no MegaPack de desenvolvimento**

## Objetivo

Permitir que o usuário entenda e experimente VFX antes de pagar o custo de um preview renderizado, sem criar um segundo motor visual ou prometer resultados falsos.

## Fluxo

1. Selecionar/combinar efeitos pelos cards.
2. Escolher uma direção musical ou ajustar parâmetros manualmente.
3. Ver o resultado imediatamente em `Original`, `A/B` ou `Resultado`.
4. Percorrer/animar a timeline demonstrativa para observar mudanças de reatividade.
5. Comparar quatro variações rápidas e aplicar uma delas se fizer sentido.
6. Escolher a linguagem da transição com miniaturas explicativas.
7. Usar `Gerar preview` para validação temporal e musical real antes do render final.

## Limites deliberados

- O preview interativo não executa Real-ESRGAN, RIFE, Demucs, normalização, encode final ou VMAF.
- A música do preview interativo é um envelope sintético determinístico; a interface informa isso.
- As miniaturas de transição são guias semânticos estáticos; a emenda real continua no pipeline FFmpeg.
- Falha ao extrair um frame do vídeo não bloqueia o editor: usa-se o cenário local de demonstração.

## Quality gates desta fase

- 35 testes automatizados passando.
- `compileall` sem erro.
- smoke test da GUI abre, troca para Visual e transições, altera VFX, timeline, A/B e transição.
- smoke test adicional em modo escuro.
- nenhum caminho do render principal foi substituído.
- layout da aba foi extraído para `ui/visual_view.py` para conter crescimento do `studio.py`.

## Próxima fase

Projeto: clareza de entrada/saída, metadados, validação inline e enquadramento.
