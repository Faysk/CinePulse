# CinePulse 1.2.24

A 1.2.24 publica a correção da issue #98 sobre lifecycle excepcional das rotas neurais do Studio.

## Real-ESRGAN

A thread que drena stdout agora é iniciada dentro da mesma fronteira `try/finally` que protege o subprocesso. Se `Thread.start()` falhar depois que o `Popen()` já criou o filho, o processo é reaped, stdout é fechado, a exceção original permanece visível e `self._process` é limpo.

## Demucs

A separação de stems recebe o mesmo contrato de cleanup. Uma falha ao iniciar a reader thread não deixa o processo Demucs órfão nem uma referência foreground presa.

## Cobertura

A suíte inclui regressões que simulam `Thread.start()` falhando depois da criação do subprocesso em Real-ESRGAN e Demucs, verificando reap do filho, fechamento do pipe e limpeza de `self._process`.

## Base

A release parte da Stable 1.2.23 e preserva o hardening do handoff do updater portátil já publicado nessa versão.

## Escopo físico

A issue #4 continua separada como fonte de verdade para aceite físico NVIDIA/8K/120. Esta release não promove capacidades Preview sem evidência física válida.
