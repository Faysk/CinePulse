# CinePulse 1.2.24

A 1.2.24 fecha a issue #98 e complementa o hardening de lifecycle do Studio sem alterar o comportamento funcional normal das rotas neurais.

## Real-ESRGAN

A thread que drena stdout agora só é iniciada depois que a execução entrou na fronteira `try/finally` do subprocesso. Se `Thread.start()` falhar depois do `Popen()`, o filho é encerrado, stdout é fechado, a exceção original é preservada e `self._process` é limpo.

## Demucs

A separação de stems recebe o mesmo contrato. O cleanup também remove o diretório de staging parcial quando a reader thread não chega a iniciar, impedindo processo órfão e cache parcial reutilizável.

## Cobertura

As regressões simulam uma falha real de `Thread.start()` depois que o subprocesso já existe e exigem reap do filho, fechamento do pipe, limpeza da referência foreground e preservação do erro original.

## Compatibilidade com 1.2.23

A branch parte diretamente da Stable 1.2.23 e preserva o hardening do handoff do updater portátil entregue nessa versão.

## Escopo físico

A issue #4 continua separada como fonte de verdade para aceite físico NVIDIA/8K/120. Esta release não promove capacidades Preview sem evidência física válida.
