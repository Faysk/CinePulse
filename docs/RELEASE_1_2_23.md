# CinePulse 1.2.23

A 1.2.23 fecha uma janela de integridade no handoff do updater portátil descoberta após a Stable 1.2.22.

## Handoff vinculado ao descritor verificado

Antes de encerrar o CinePulse, `launch_staged()` agora lê e valida o `pending-update.json` preparado. O descritor precisa usar schema 1, corresponder exatamente à versão do update em andamento e apontar para uma origem existente dentro de `.runtime/updates`.

Depois da validação, o CinePulse calcula o SHA-256 dos bytes exatos do descritor e grava esse digest no helper PowerShell de handoff.

Quando o processo principal termina, o helper recalcula o SHA-256 de `pending-update.json` imediatamente antes do relaunch. Se o descritor tiver mudado, o update é abortado em vez de iniciar a transação portátil com um estado diferente daquele aprovado.

## Compatibilidade

O fluxo MSI não muda: ele continua validando nome, confinamento e SHA-256 do pacote MSI preparado antes do handoff.

O formato do `pending-update.json` também permanece schema 1; não há migração de estado para usuários existentes.

## Cobertura

A suíte inclui regressões para:

- handoff portátil válido contendo o digest esperado;
- descriptor de versão divergente;
- origem fora da área privada `.runtime/updates`;
- presença da verificação `Get-FileHash -Algorithm SHA256` no helper.

Closes #97.

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente pela issue #4.
