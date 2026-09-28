# CinePulse 1.2.24

A 1.2.24 é um hotfix de lifecycle sobre a Stable 1.2.23. Ela fecha a lacuna registrada na issue #98 nos subprocessos neurais do Studio.

## Cleanup na inicialização da reader thread

Real-ESRGAN e Demucs criam um subprocesso e uma thread para drenar o stdout. A inicialização dessa thread agora acontece dentro da mesma fronteira `try/finally` que possui o processo.

Se `threading.Thread.start()` falhar depois de `subprocess.Popen()`:

- a exceção original continua sendo propagada;
- qualquer child ainda vivo é encerrado e reapado pelo finalizador compartilhado;
- o stdout capturado é fechado;
- `self._process` é limpo quando ainda aponta para aquele processo.

O fluxo normal de sucesso e cancelamento mantém o contrato anterior.

## Cobertura

A suíte adiciona regressões específicas para falha de startup da reader thread em:

- `VideoOptimizerStudio._run_ai` (Real-ESRGAN);
- `VideoOptimizerStudio._prepare_reactive_audio` (Demucs).

Os testes exigem reap do processo, fechamento do pipe, limpeza do foreground handle e preservação da exceção original.

## Escopo físico

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente pela issue #4 e não é promovida por este hotfix.

Closes #98.
