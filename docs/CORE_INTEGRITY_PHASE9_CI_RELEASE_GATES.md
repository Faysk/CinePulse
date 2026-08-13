# Core Integrity Phase 9 — CI & Release Gates

## Objetivo

Transformar as validações manuais acumuladas nas Phases 1–8 em portões reproduzíveis. A Phase 9 separa três níveis de evidência: código-fonte, integração CPU e aceite GPU/Windows de distribuição.

## Gate único em Python

`scripts/ci_gate.py` é o orquestrador portável. Perfis:

- `source`: contrato da release, `compileall`, 185 testes unitários e geração de SBOM;
- `cpu`: smoke básico/áudio, cancelamento/recovery, delivery matrix, Storage Engine, deep verification e contrato de chunks neurais;
- `media`: VFX, HDR e SDR10/full-range em job separado para paralelizar os smokes mais caros;
- `release-light`: `source + cpu + media`, usado no Release Candidate Windows;
- `gpu`: RIFE, Real-ESRGAN e Demucs reais, reservado a runner NVIDIA preparado.

Cada execução produz `artifacts/ci/gate-<profile>.json` com plataforma, Python, comandos, duração e status de cada etapa. Em Linux sem DISPLAY o gate usa `xvfb-run` automaticamente para testes Tk.

## Workflow Quality

`.github/workflows/quality.yml` roda em push para `main` e pull requests.

1. Matriz de fonte em Windows e Linux, Python 3.11 e 3.13.
2. Integração CPU em Linux com FFmpeg/Xvfb.
3. Evidências JSON são publicadas como artifacts mesmo em falha.

A matriz existe para validar o contrato `requires-python >= 3.11` sem depender apenas da versão usada pelo desenvolvedor.

## Workflow Release Candidate

`.github/workflows/release-candidate.yml` é executável manualmente e em tags `v*`.

No Windows ele:

1. executa `release-light`;
2. executa o portão PowerShell;
3. monta o ZIP portátil;
4. testa aplicação isolada do updater preservando dados mutáveis;
5. monta e valida o MSI;
6. publica ZIP/MSI/manifests/evidências como artifact de CI.

`Build-Portable.ps1` e `Build-Msi.ps1` agora aceitam `-BuildPython`. Isso remove a dependência artificial de já ter inicializado `.runtime` na máquina de build sem alterar o contrato do runtime distribuído, que continua obrigatoriamente gerenciado.

## Workflow GPU Acceptance

`.github/workflows/gpu-acceptance.yml` é deliberadamente `workflow_dispatch` e usa um runner:

`[self-hosted, Windows, X64, cinepulse-gpu]`

Ele exige inventário NVIDIA e executa o perfil `gpu`. Isso evita fingir cobertura de Real-ESRGAN/RIFE/Demucs em runners sem hardware/componentes reais.

## Testes de integração históricos

Os antigos arquivos `integration_*.py` continuam scripts explícitos, pois representam smokes end-to-end e não unit tests. A lacuna da auditoria é fechada pelo `ci_gate.py`: todos os smokes leves fazem parte de um gate obrigatório de PR/release em vez de ficarem esquecidos fora do padrão `test*.py`.

## Distribuição

A Phase 9 não declara o MSI aprovado em Windows apenas porque o código do workflow existe. O aceite definitivo exige uma execução verde de `Release Candidate` em GitHub Actions/Windows. Da mesma forma, assinatura Minisign/Authenticode continua dependente de chaves/certificado reais.

## Limites deliberados

- 8K/120 real, render musical longo e inspeção HDR perceptiva continuam gates de máquina-alvo;
- GPU acceptance precisa de runner self-hosted configurado e componentes instalados;
- CP-019 continua parcial até uma release pública assinada;
- CP-020 continua parcial até lock transitivo hashado de toda a stack neural;
- modularização de `studio.py` e isolamento do pipeline legado permanecem CP-032/CP-033.
