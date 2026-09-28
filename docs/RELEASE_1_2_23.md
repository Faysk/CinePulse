# CinePulse 1.2.23

A 1.2.23 fecha uma janela de integridade no handoff do updater Portable sem alterar o fluxo MSI nem as capacidades de processamento de vídeo.

## Handoff Portable vinculado ao estado validado

Antes de encerrar o processo principal, o CinePulse agora lê e valida o `pending-update.json` preparado. O descritor precisa usar o schema suportado, declarar exatamente a versão que está sendo aplicada e apontar para uma origem existente dentro da área privada `.runtime/updates`.

Depois dessa validação, o SHA-256 exato dos bytes do descritor é incorporado ao helper PowerShell de handoff. Quando o processo principal termina, o helper recalcula o hash imediatamente antes do relaunch e aborta se o arquivo tiver mudado.

Isso evita que um descritor stale, trocado ou corrompido entre staging e handoff seja consumido silenciosamente pelo bootstrap.

## Compatibilidade

O updater MSI continua usando o mesmo contrato anterior, incluindo a revalidação do SHA-256 do pacote MSI preparado. A mudança desta release é limitada ao caminho Portable.

## Cobertura

A suíte inclui regressões para:

- versão do descritor diferente da versão preparada;
- schema incompatível;
- origem fora de `.runtime/updates`;
- verificação do SHA-256 no helper antes de `Start-Process`.

A publicação Stable continua condicionada aos gates canônicos de Quality, Release Candidate e Publish Release.

A aceitação física NVIDIA/8K/120 permanece acompanhada separadamente pela issue #4.
