# CinePulse 1.2.23

A 1.2.23 é um patch de confiabilidade para a serialização de estado durável introduzida na 1.2.22.

## Timeout de mutações duráveis

`path_mutation_transaction(..., timeout=N)` agora trata o timeout como um orçamento único para toda a aquisição do lock. Antes, a espera pelo `threading.RLock` entre threads do mesmo processo não tinha limite; só o mutex/flock cross-process recebia o timeout.

Com esta release:

- o lock local também respeita o timeout solicitado;
- o mutex/flock recebe apenas o tempo restante do mesmo deadline monotônico;
- reentrância na mesma thread continua suportada;
- falha de aquisição retorna `TimeoutError` sem deixar o lock local preso.

## Cobertura

A regressão mantém uma thread segurando o mesmo path e prova que outra chamada com `timeout=0.05` encerra por timeout antes de o holder ser liberado. A cobertura cross-process existente continua validando ausência de lost update.

## Escopo físico

O aceite físico NVIDIA/8K/120 continua separado na issue #4. Esta correção não promove caminhos Preview nem transforma CI hospedado em evidência de hardware.
