# CinePulse 1.2.25

A 1.2.25 fecha a janela TOCTOU residual do updater portátil identificada em #111.

## Descriptor vinculado até o apply

A 1.2.23 já fazia o helper validar o SHA-256 de `pending-update.json` antes de relançar o CinePulse. Ainda existia, porém, um pequeno intervalo entre essa validação e a leitura posterior do arquivo pelo aplicador transacional.

Agora o digest aprovado atravessa o relaunch em `CINEPULSE_EXPECTED_PENDING_SHA256`. O aplicador lê `pending-update.json` uma única vez como bytes, calcula o SHA-256 desses bytes e, quando existe um digest herdado, exige correspondência exata antes de interpretar o JSON.

O JSON é então decodificado a partir dos mesmos bytes já validados. Não existe uma segunda leitura do descriptor entre a verificação criptográfica e o uso dos seus metadados.

## Compatibilidade e recovery

O caminho de retry/recovery manual continua compatível quando não existe digest herdado. Nessa situação o aplicador mantém as validações estruturais, de confinamento e de manifesto existentes.

Após cada tentativa de apply, o bootstrap remove a variável de ambiente do digest para impedir estado residual dentro do processo relançado.

## Cobertura

O smoke Windows agora prova que:

- um digest divergente é bloqueado antes de remover ou copiar qualquer payload gerenciado;
- o descriptor e a origem permanecem disponíveis para retry;
- um digest correto atravessa a falha injetada, executa rollback e permite retry;
- o apply final continua substituindo a árvore gerenciada e preservando dados mutáveis.

Os contratos Python também exigem a propagação do digest pelo helper e que o aplicador consuma os mesmos bytes que valida.

Closes #111.

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente em #4.
