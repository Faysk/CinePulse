# CinePulse 1.2.16

Esta release endurece a descoberta de trabalho preservado após encerramento/crash. O objetivo é simples: um job que ainda existe no disco nunca deve desaparecer da recuperação apenas porque o manifesto principal foi perdido ou ficou corrompido.

## Backup-only

`RecoveryService.discover()` agora procura tanto `manifest.json` quanto `manifest.json.bak`. Se só o backup existir, o `JobStore` valida o backup, restaura o manifesto principal por escrita atômica e o job volta a ser classificado normalmente.

## Manifesto irrecuperável continua visível

Se manifesto e backup estiverem ambos ilegíveis, o job é exposto como `blocked/unreadable` em vez de ser omitido. O card mantém o diretório do histórico e oferece apenas ações seguras de inspeção/preservação; nenhum progresso ou fonte é inventado.

## Evidência preservada

A descoberta sintética não reescreve os dois arquivos corrompidos. Isso preserva a evidência para diagnóstico manual ou ferramentas futuras de repair.

## Sem mudança de pipeline

Não há mudança em modelo, FPS, qualidade, full-utilization, encode, GPU fallback ou formato de saída. A alteração é restrita à visibilidade e segurança do estado persistido de recovery.
