# CinePulse 1.2.20

Esta release consolida o hardening acumulado depois da 1.2.19 e fecha uma janela de inconsistência no handoff do updater portátil.

## Updater portátil vinculado ao staging verificado

Antes de fechar o CinePulse, o launcher agora lê e valida o `pending-update.json` preparado: schema, versão, origem e confinamento da origem dentro de `.runtime/updates` precisam corresponder ao update que acabou de ser verificado.

O SHA-256 exato desse descritor é entregue ao helper PowerShell. Depois que o processo principal termina, o helper recalcula o hash antes de relançar o CinePulse; se o descritor mudou no intervalo, o update é abortado em vez de aplicar estado diferente daquele que foi aprovado no staging.

## Hardening acumulado pós-1.2.19

A release também incorpora as correções já presentes na `main` para tornar caches e evidências sensíveis ao conteúdo real, serializar publicações/checkpoints concorrentes, reforçar promoção crash-safe na recuperação, reaper determinístico de subprocessos e integridade de componentes experimentais/TensorRT.

## Compatibilidade e segurança

O fluxo Stable continua exigindo SHA-256 para os pacotes oficiais e mantém o rollback transacional do updater portátil. O MSI continua fazendo a revalidação do próprio pacote no handoff; esta release dá ao descritor portátil uma proteção equivalente contra troca de estado entre preparação e aplicação.

A aceitação física de GPU/8K/120 permanece separada na issue #4 e não é promovida por esta release.
