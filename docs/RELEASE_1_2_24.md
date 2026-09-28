# CinePulse 1.2.24

A 1.2.24 é um hotfix de persistência sobre a Stable 1.2.23. Ela fecha a lacuna encontrada na issue #95 no lock cross-process por path sem alterar o hardening do updater introduzido na 1.2.23.

## Timeout end-to-end

`path_mutation_transaction(path, timeout=...)` agora trata o valor informado como um único orçamento para toda a aquisição:

- a contenção no `threading.RLock` do processo respeita o timeout;
- chamadas aninhadas na mesma thread continuam reentrantes;
- somente o tempo restante é repassado ao named mutex do Windows ou ao `flock` POSIX;
- o contrato existente de `TimeoutError` é preservado quando qualquer camada esgota o orçamento.

Antes deste hotfix, uma segunda thread podia ficar presa no lock local por tempo indefinido e só então começar a contar o timeout do lock do sistema operacional.

## Cobertura

A suíte adiciona uma regressão com duas threads reais. Uma mantém o path ocupado enquanto a segunda tenta entrar com orçamento curto; a segunda deve expirar dentro desse orçamento e nunca aguardar a liberação do holder.

Os testes existentes de reentrância e serialização entre processos permanecem ativos para garantir que a correção não enfraqueça o contrato introduzido na 1.2.22.

## Compatibilidade

A 1.2.24 parte diretamente da 1.2.23 e preserva a vinculação criptográfica do `pending-update.json` implementada em #97/#103.

## Escopo físico

A issue #4 continua sendo a fonte de verdade para aceite físico NVIDIA/8K/120 e graduation de caminhos Preview. A 1.2.24 não altera esse status.
