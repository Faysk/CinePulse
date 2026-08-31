# Recovery & Reliability Mega Pack — Phase 5: Storage Resilience

**Status:** implementation candidate
**Base:** Phase 4 (`69f4991f1ac4f07b9d39ac8ce836997289e80827`)
**Gate alvo:** G5

## Entrega

O volume físico passa a fazer parte do contrato operacional do render.

### Volume identity

Novo `volume_identity.py` resolve:

- identidade estável do volume (`Volume GUID`/serial no Windows quando disponível; `st_dev` no Unix);
- mount point;
- filesystem quando o Windows expõe;
- drive type;
- bus class conservadora;
- capacidade e espaço livre.

Letra de unidade deixa de ser tratada como identidade suficiente. O campo de bus permanece `unknown` quando o sistema operacional não fornece prova barata/confiável; não inferimos USB só porque o path começa com `G:`.

### StorageGuard

- valida espaço necessário + reserva antes de fase grande;
- revalida margem durante escrita longa;
- quando a margem cai abaixo do limite, gera `StorageBlocked` antes da promoção;
- política de `faststart` evita segunda passada completa em entrega local muito grande ou volume removível/network.

### ResumableStager

- cópia entre volumes usa parcial + checkpoint de bytes;
- identidade/tamanho/mtime da origem são persistidos;
- interrupção retoma do byte confirmado;
- parcial órfão sem checkpoint é recusado para evitar confiar em arquivo desconhecido;
- origem permanece intacta durante todo o processo;
- validação opcional de SHA-256 e validator de mídia ocorre antes da promoção;
- destino só recebe nome final via `os.replace` após a cópia completa validar;
- estado final registra volumes, bytes e checksum quando solicitado.

## Testes

- mesma montagem produz mesma identidade;
- espaço insuficiente bloqueia;
- faststart é recusado para os casos grandes de risco;
- staging interrompido retoma sem apagar origem;
- mudança da origem invalida o staging anterior;
- validator falhando impede promoção.

## Limites

Identificação precisa do barramento físico para discos USB apresentados como `DRIVE_FIXED` exige integração adicional com Storage Management/WMI. Nesta phase o sistema prefere `unknown` a inventar certeza. O aceite físico USB/SSD entra na Phase 7.

## Gate G5

A lógica de volume, margem e staging reiniciável está implementada. O gate físico só é `aceito` após cenários reais de remoção controlada de volume, SSD interno e arquivo grande em Windows.
