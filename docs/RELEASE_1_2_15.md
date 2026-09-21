# CinePulse 1.2.15

CinePulse 1.2.15 padroniza os fallbacks auxiliares com o contrato já usado na finalização e no recovery: tentar CPU é uma reação a falha real de GPU, não uma segunda tentativa genérica para qualquer erro.

## Fallback GPU classificado

A comparação A/B, a extração CUDA foreground e o prefetch CUDA agora verificam `looks_like_gpu_runtime_failure()` antes de repetir pela CPU. Isso evita esconder erros de disco cheio, input quebrado, filtro inválido ou outras falhas não-GPU atrás de uma tentativa CPU que não poderia resolver a causa.

O mismatch explícito de contagem de frames da extração CUDA continua sendo tratado como falha da rota acelerada, porque a integridade observada já prova que o fast-path não entregou o contrato solicitado.

## CI Linux resiliente a repositórios de terceiros

Os jobs CPU integration e Media integrity precisam apenas de pacotes dos arquivos oficiais do Ubuntu. GitHub-hosted runners podem conter sources APT adicionais. A 1.2.15 remove, apenas dentro desses jobs descartáveis, arquivos em `/etc/apt/sources.list.d/` que apontem para `packages.microsoft.com` antes do `apt-get update`. Assim um 403 de um fornecedor não relacionado não transforma a saúde do CinePulse em falso negativo.

## O que não mudou

Full-utilization, contagem exata de frames, áudio frame-bound, fallbacks NVENC→CPU, recovery crash-safe, AtomicOutput e verificação final permanecem inalterados.
