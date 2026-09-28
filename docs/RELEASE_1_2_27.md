# CinePulse 1.2.27

A 1.2.27 fecha a lacuna de vínculo entre a versão declarada no descriptor portátil e o diretório de staging usado como origem.

## Staging vinculado à versão

O updater já exige schema válido, versão igual ao `UpdateInfo`, origem existente dentro de `.runtime/updates` e binding SHA-256 do descriptor até o apply.

Ainda era possível declarar a versão atual e apontar `source` para o staging privado de outra versão sob o mesmo `.runtime/updates`.

Agora `_validate_portable_pending_handoff()` exige que a origem esteja em `.runtime/updates/<versão preparada>` ou em um subdiretório desse staging.

## Compatibilidade

A mensagem existente para origem realmente fora da área privada de updates é preservada. O fluxo MSI permanece inalterado.

Descriptors corretos da mesma versão continuam seguindo o mesmo handoff criptograficamente vinculado. O hotfix de CI publicado na 1.2.26 também permanece incorporado.

## Cobertura

A regressão cria um descriptor cuja versão coincide com o `UpdateInfo`, mas cuja origem aponta para `.runtime/updates/9.9.9/...`; o handoff deve falhar antes de iniciar o helper.

Closes #118.

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente em #4.
