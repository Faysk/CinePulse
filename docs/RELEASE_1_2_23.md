# CinePulse 1.2.23

A 1.2.23 fecha a issue #94 e endurece a fronteira entre o staging verificado do updater portátil e o relaunch que aplica a atualização.

## Updater portátil fail-closed

Antes do handoff, `launch_staged()` agora exige exatamente `.runtime/pending-update.json`, relê os bytes do descritor e valida:

- schema 1;
- versão igual ao `UpdateInfo` aprovado;
- origem presente;
- origem confinada a `.runtime/updates`;
- diretório de origem realmente existente.

Depois dessa validação, o CinePulse calcula o SHA-256 dos bytes exatos do descritor e embute esse digest no helper PowerShell.

Quando o processo principal termina, o helper usa `Get-FileHash -Algorithm SHA256` imediatamente antes do relaunch. Se `pending-update.json` mudou no intervalo, o helper aborta em vez de iniciar o bootstrap com estado diferente daquele que foi aprovado.

## Compatibilidade

O fluxo MSI permanece inalterado e continua revalidando o SHA-256 do pacote preparado antes do handoff.

## Cobertura

A suíte inclui regressões para:

- descritor válido vinculado ao hash entregue ao helper;
- versão divergente entre descritor e atualização;
- origem do descritor fora da área privada de updates;
- ordem da verificação de hash antes de `Start-Process`.

## Escopo físico

A issue #4 continua sendo a fonte de verdade para aceite físico NVIDIA/8K/120. Esta release não promove capacidade física com base apenas em CI hospedado.
