# Recovery & Reliability Mega Pack — Phase 2: Worker & Ownership

**Status:** implementation candidate
**Base:** Phase 1 (`d5ac2dbfd54c6e741578133ac73159a88fef8307`)
**Gate alvo:** G2

## Entrega

A vida do job deixa de depender conceitualmente da janela Tk. Esta phase cria o runtime de ownership que será usado pelos StageAdapters e, no rollout, lançado como processo independente da UI.

### Lease

- `JobLease` grava `pid`, token real de início do processo, `nonce`, host, heartbeat, fase/unidade, contador monotônico de progresso e subprocessos conhecidos;
- aquisição final usa criação exclusiva (`O_EXCL`), impedindo dois owners na corrida final;
- heartbeat velho sozinho não autoriza takeover;
- PID vivo com mesmo start token mantém ownership mesmo com heartbeat atrasado;
- PID reciclado é diferenciado pelo start token (`/proc` no Unix e `GetProcessTimes` no Windows);
- subprocesso registrado ainda vivo impede takeover enquanto pode haver escrita ativa;
- lease stale é preservada como evidência antes da nova aquisição;
- release é ownership-aware e preserva registro `released-*`.

### Protocolo local

- novo `WorkerCommandQueue` persistente em arquivos;
- comandos: `start`, `pause`, `resume`, `cancel`, `status`, `shutdown`;
- submit → inbox → claim atômico → processing → reply/done;
- fechar a UI não elimina comandos, respostas ou ownership do job.

### RenderWorker

- novo `RenderWorker` sem import ou dependência Tk;
- adquire lease antes de colocar o manifesto em `running`;
- executor recebe `WorkerContext` e só observa pause/cancel em `checkpoint()` seguro;
- pause: `running -> pause_requested -> paused`;
- resume: `paused -> recoverable -> preflight -> running`;
- cancelamento preserva manifesto/artefatos e marca `cancelled`;
- exceção recebe erro `WORKER-FAILED` e estado `blocked`;
- execução concluída entra em `verifying`, nunca declara arquivo final aprovado sozinha.

## Rollout deliberado

O `RenderWorker` é a fundação desacoplada; a UI atual ainda não lança esse runtime por padrão. A ligação ao pipeline acontece pelos StageAdapters na Phase 3 e a troca do launcher entra no anel opt-in/RC da Phase 8. Isso evita reescrever `studio.py` de uma vez e mantém comparação com rc.6.

## Testes

- segunda aquisição com heartbeat fresco é recusada;
- heartbeat stale não rouba owner vivo;
- PID reciclado permite takeover somente após token divergir;
- subprocesso vivo bloqueia takeover;
- contador de progresso é monotônico;
- comandos persistem e são acknowledged;
- worker conclui em `verifying`;
- pause para na fronteira e retoma o mesmo job;
- cancelamento preserva manifesto;
- falha do executor é estruturada e bloqueada.

## Gate G2

Código e testes cobrem ownership/protocolo. O aceite físico de fechar/reabrir a UI durante render real permanece no Gate G7/G8, quando o novo launcher estiver habilitado no anel RC; até lá a feature permanece opt-in e não é anunciada ao usuário final.
