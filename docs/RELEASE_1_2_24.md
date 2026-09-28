# CinePulse 1.2.24

A 1.2.24 preserva integralmente o hardening do updater portátil da 1.2.23 e corrige a semântica de timeout da serialização de estado durável.

## Timeout de mutações duráveis

`path_mutation_transaction(..., timeout=N)` agora trata o timeout como um orçamento único para toda a aquisição do lock.

Na implementação anterior, a espera pelo `threading.RLock` entre threads do mesmo processo não tinha limite; somente o mutex/flock cross-process recebia o timeout. Sob contenção local, uma chamada podia portanto ultrapassar o limite solicitado e ainda assim adquirir o lock.

Com esta release:

- o lock local respeita o timeout solicitado;
- o mutex/flock recebe somente o tempo restante do mesmo deadline monotônico;
- reentrância na mesma thread continua suportada;
- falha de aquisição retorna `TimeoutError` sem deixar o lock local preso.

## Cobertura

A regressão mantém uma thread segurando o mesmo path e prova que outra chamada com `timeout=0.05` encerra por timeout antes de o holder ser liberado. A cobertura cross-process existente continua validando ausência de lost update.

## Compatibilidade com 1.2.23

Esta release parte diretamente da `main` contendo a correção #97 da 1.2.23 e preserva a validação/hash do `pending-update.json` no handoff portátil.

## Escopo físico

O aceite físico NVIDIA/8K/120 continua separado na issue #4. Esta correção não promove caminhos Preview nem transforma CI hospedado em evidência de hardware.
