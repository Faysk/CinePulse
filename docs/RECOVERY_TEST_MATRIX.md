# Matriz de testes — recuperação, falhas e aceite

**Status:** plano de validação normativo

**Responsável:** mantenedores do CinePulse

**Atualizado em:** 31 de agosto de 2026
**Regra:** cenário não executado é pendência, nunca PASS

## 1. Objetivo

Provar que o CinePulse não apenas conclui renders em condições ideais, mas também preserva, explica e retoma corretamente quando processos, arquivos, volumes ou a própria máquina falham.

## 2. Camadas de teste

| Camada | Ambiente | Finalidade |
|---|---|---|
| unitário | qualquer CI | schema, transições, cálculo, validação e decisões puras |
| integração sintética | CPU/FFmpeg local | subprocessos, checkpoints, mídia curta e promoção |
| fault injection | processo/FS controlado | interrupção em cada fronteira |
| Windows | Windows real | paths, locks, volumes, PowerShell e processo |
| GPU | NVIDIA alvo | RIFE, NVENC, VRAM e política UHD |
| storage físico | SSD/HDD/USB | staging, desconexão, throughput e fechamento |
| perceptivo | amostras e inspeção humana | fronteiras, movimento, preto/freeze e qualidade |
| render longo | máquina de destino | estabilidade, temperatura, ETA e retenção reais |

Fixtures automatizadas devem ser sintéticas e pequenas. Mídia pessoal não entra no repositório, CI ou bundle de evidência.

## 3. Invariantes globais

Todo cenário de falha deve confirmar:

1. entrada e saída final anterior permanecem intactas;
2. parcial não é apresentado como final;
3. última unidade `committed` continua reutilizável;
4. unidade em produção é refeita ou colocada em quarentena;
5. manifesto permanece válido ou recuperável por backup;
6. log/evento registra fase, tentativa e causa;
7. segundo processo não assume ownership indevidamente;
8. cleanup não ocorre automaticamente;
9. resultado retomado cumpre o mesmo contrato do controle sem falha.

## 4. Fixtures

### F0 — mídia básica

- 4 s, 320×180, 30 fps, áudio estéreo 48 kHz;
- padrão temporal numerado por quadro;
- cor e tom conhecidos;
- hash final determinístico quando codec lossless for usado.

### F1 — chunks residuais

- contagens que geram segmentos 16, 17 e 18;
- um último chunk com cauda mesclada;
- timestamps exatos para 120 fps.

### F2 — defeitos

- PNG truncado após assinatura;
- PNG sem `IEND`;
- quadro preto;
- sequência congelada intencional e inesperada;
- segmento com pacote faltante;
- gap de índice;
- PTS duplicado/descontínuo;
- MKV legível com duração arredondada incorreta;
- MP4 sem `moov`;
- MP4 com trailer inválido.

### F3 — schemas

- fila legada;
- manifesto schema 1;
- manifesto truncado + backup;
- schema futuro;
- referência órfã;
- scratch sem histórico suficiente.

## 5. Matriz unitária — manifesto e estado

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-001 | P0 | round-trip do manifesto | JSON determinístico, mesma revisão/fingerprint | RH-FUN-001, RH-MIG-001 |
| RT-002 | P0 | transição válida | revisão incrementa uma vez e evento é emitido | RH-FUN-001 |
| RT-003 | P0 | transição inválida | exceção, nenhuma escrita | RH-FUN-014 |
| RT-004 | P0 | schema futuro | recusa sem backup/mutação | RH-MIG-001, RH-MIG-006 |
| RT-005 | P0 | manifesto truncado com backup válido | restaura/classifica e registra recuperação | RH-MIG-002 |
| RT-006 | P0 | manifesto e backup inválidos | `blocked/fatal_integrity`, preservação total | RH-FUN-014 |
| RT-007 | P0 | compare-and-swap de revisão | segundo writer perde sem sobrescrever | RH-FUN-008 |
| RT-008 | P0 | PID reciclado com start time diferente | lease não é considerada do mesmo owner | RH-FUN-009 |
| RT-009 | P0 | heartbeat atrasado, processo vivo | não toma lease | RH-FUN-009 |
| RT-010 | P0 | heartbeat stale, processo ausente | permite auditoria antes de takeover | RH-FUN-009 |
| RT-011 | P1 | erro retryable | mantém tentativa e cria retry separado | RH-FUN-011, RH-OBS-003 |
| RT-012 | P1 | redaction | paths/volume IDs removidos de export | RH-OBS-004 |

## 6. Matriz unitária — mídia e planejamento

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-020 | P0 | PNG válido | aceito | RH-QUA-001 |
| RT-021 | P0 | assinatura inválida | rejeitado | RH-QUA-001 |
| RT-022 | P0 | PNG sem IEND | rejeitado mesmo com exit code zero | RH-QUA-001 |
| RT-023 | P0 | sequência 16/17/18 | contagem final exata | RH-QUA-006 |
| RT-024 | P0 | concat de milhares de durações | soma igual a frames/fps na tolerância | RH-QUA-007 |
| RT-025 | P0 | gap de segmento | retomada bloqueada antes de mutação | RH-FUN-006 |
| RT-026 | P0 | segmento codec/dimensão errados | rejeitado | RH-QUA-002 |
| RT-027 | P0 | quadro preto | detector genérico sinaliza | RH-QUA-004 |
| RT-028 | P0 | cena estática legítima | não classifica como freeze inválido | RH-QUA-005 |
| RT-029 | P0 | freeze inserido em movimento | detector sinaliza intervalo | RH-QUA-005 |
| RT-030 | P0 | fronteira duplicada | gate sinaliza | RH-QUA-008 |
| RT-031 | P1 | modelo RIFE muda | invalida somente dependentes | RH-QUA-012 |
| RT-032 | P1 | política faststart por tamanho/destino | argumentos corretos sem alterar codecs | RH-STO-006 |

## 7. Integração — protocolo de commit

Cada estágio deve executar os seguintes pontos de falha:

| ID | Pri. | Ponto injetado | Resultado exigido |
|---|---|---|---|
| RT-040 | P0 | antes de criar parcial | unidade permanece `planned` |
| RT-041 | P0 | durante escrita parcial | parcial ignorado/quarentenado na retomada |
| RT-042 | P0 | depois de fechar, antes de validar | arquivo é revalidado, não assumido |
| RT-043 | P0 | durante validação | unidade não avança |
| RT-044 | P0 | depois de validar, antes de promover | retomada repete validação/promoção |
| RT-045 | P0 | depois de promover, antes do manifesto | reconciliação reconhece e revalida artefato |
| RT-046 | P0 | durante escrita do manifesto | backup/recovery mantém revisão anterior |
| RT-047 | P0 | depois do manifesto, antes de cleanup | unidade confirmada; temporários podem ser limpos depois |
| RT-048 | P0 | durante cleanup | commit não é perdido; limpeza é idempotente |

Executar RT-040–048 em upscale, RIFE, master, delivery e pelo menos um estágio VFX aplicável.

## 8. Integração — worker e concorrência

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-060 | P0 | fechar UI com worker ativo | worker segue e UI reconecta | RH-FUN-003, RH-FUN-004 |
| RT-061 | P0 | pausar e fechar | pausa na fronteira e nenhum subprocesso permanece | RH-FUN-005 |
| RT-062 | P0 | matar worker | job vira interrupted/auditing e retoma | RH-FUN-002 |
| RT-063 | P0 | matar FFmpeg filho | árvore/erro registrados; unidade refeita | RH-FUN-002 |
| RT-064 | P0 | abrir segunda instância | não inicia segundo subprocesso | RH-FUN-008 |
| RT-065 | P0 | dois comandos resume simultâneos | somente um adquire lease | RH-FUN-008 |
| RT-066 | P0 | pausa/resume três vezes | contagem/hash lossless igual ao controle | RH-FUN-005 |
| RT-067 | P0 | cancelar | tentativa cancelled, dados recuperáveis preservados | RH-FUN-013 |
| RT-068 | P1 | retry | attempt novo, histórico anterior intacto | RH-FUN-011 |
| RT-069 | P1 | relógio do sistema muda | timeout usa contador monotônico internamente | RH-OBS-002 |

## 9. Integração — descoberta e migração

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-080 | P0 | job recoverable conhecido | reaparece na fila | RH-FUN-007, RH-UX-001 |
| RT-081 | P0 | job ativo | aparece como ativo, sem botão retomar | RH-UX-005 |
| RT-082 | P0 | scratch high confidence | classifica e oferece auditoria | RH-MIG-003 |
| RT-083 | P0 | scratch medium confidence | exige confirmação, não muta | RH-MIG-003 |
| RT-084 | P0 | scratch low confidence | bloqueia e preserva | RH-MIG-003 |
| RT-085 | P0 | migração da fila falha após manifesto | fila antiga válida; manifesto redescobrível | RH-MIG-002, RH-MIG-007 |
| RT-086 | P0 | rollback de feature | manifests preservados e caminho legado abre | RH-MIG-005 |
| RT-087 | P0 | downgrade com schema novo | versão antiga recusa sem mutar | RH-MIG-006 |
| RT-088 | P1 | fonte muda de letra com volume identity | reconecta após confirmação | RH-STO-001 |
| RT-089 | P1 | fonte diferente no mesmo path | bloqueia mismatch | RH-FUN-006 |

## 10. Integração — armazenamento

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-100 | P0 | espaço insuficiente no preflight | não inicia fase | RH-STO-002 |
| RT-101 | P0 | espaço cai abaixo da margem durante fase | pausa/erro seguro antes de promoção | RH-STO-003 |
| RT-102 | P0 | volume removido durante parcial | job não completa; parcial preservado | RH-STO-011 |
| RT-103 | P0 | staging interrompido | cópia retoma sem apagar origem | RH-STO-004, RH-STO-008 |
| RT-104 | P0 | cópia completa com tamanho divergente | não promove staged master | RH-STO-008 |
| RT-105 | P0 | USB lento detectado | aviso e alternativa de SSD | RH-STO-005, RH-UX-005 |
| RT-106 | P0 | MP4 sem moov | parcial rejeitado/preservado | RH-FUN-010 |
| RT-107 | P0 | erro ao escrever trailer | nunca promove final | RH-STO-011 |
| RT-108 | P0 | final anterior existe | rollback o mantém após falha | RH-STO-007 |
| RT-109 | P1 | cleanup | inventário exato; somente alvos confirmados removidos | RH-STO-009 |
| RT-110 | P1 | cache ausente | job reinicia fase ou bloqueia; fonte intacta | RH-STO-010 |

Falhas de volume físico devem ser simuladas com abstração em CI e repetidas em hardware descartável no aceite; não desconectar de forma destrutiva um volume com dados pessoais.

## 11. GPU e qualidade 8K

| ID | Pri. | Cenário | Resultado exigido | Ambiente |
|---|---|---|---|---|
| RT-120 | P0 | RIFE 8K UHD serial | PNGs íntegros, contagem exata, zero preto da fixture | Windows/NVIDIA |
| RT-121 | P0 | alvo residual 17 | rota nativa + retime, zero preto | Windows/NVIDIA |
| RT-122 | P0 | paralelismo não aprovado | política força conservador | unit + GPU |
| RT-123 | P0 | pressão de VRAM | erro/retry seguro, sem commit parcial | Windows/NVIDIA |
| RT-124 | P0 | encode HEVC 8K/120 curto | contêiner fecha e contrato passa | Windows/NVIDIA |
| RT-125 | P1 | amostra de fronteiras | inspeção não mostra preto, freeze ou salto | humano |
| RT-126 | P1 | GPU baixa durante I/O | heartbeat/progresso impedem falso hang | Windows/storage |
| RT-127 | P1 | temperatura/throttle | ETA amplia faixa e job continua válido | Windows/NVIDIA |

## 12. Verificação e promoção

| ID | Pri. | Cenário | Resultado exigido | Requisitos |
|---|---|---|---|---|
| RT-140 | P0 | quick verify passa | ainda registra se count/deep não ocorreram | RH-QUA-009, RH-UX-004 |
| RT-141 | P0 | frame count divergente | não promove | RH-QUA-009 |
| RT-142 | P0 | codec/áudio divergente | não promove | RH-QUA-009 |
| RT-143 | P0 | delta A/V excedido | não promove | RH-QUA-009 |
| RT-144 | P0 | count-frames interrompido | retoma/reexecuta verificação sem reencode | RH-FUN-002 |
| RT-145 | P0 | deep verify falha no fim | não promove | RH-QUA-010 |
| RT-146 | P0 | promoção interrompida | final antigo ou novo completo, nunca mistura | RH-FUN-010 |
| RT-147 | P1 | parcial copiado antes da aprovação | UI mantém aviso; bytes não são alterados pela verificação | RH-UX-004 |

## 13. Interface e compreensão

| ID | Pri. | Cenário | Resultado exigido |
|---|---|---|---|
| RT-160 | P0 | job redescoberto | origem, fase e próxima ação visíveis |
| RT-161 | P0 | interpolação 100%, master pendente | usuário não interpreta como conclusão |
| RT-162 | P0 | encode 100%, verifying | texto diz que arquivo ainda não foi aprovado |
| RT-163 | P0 | lease ativa | botão retomar indisponível |
| RT-164 | P0 | descarte | inventário/bytes e confirmação explícita |
| RT-165 | P1 | 1024×700 | ações e estado sem corte |
| RT-166 | P1 | DPI 100/125/150/200 | layout e foco preservados |
| RT-167 | P1 | teclado/leitor de tela | estado e ações acessíveis |
| RT-168 | P1 | ETA sem amostra | mostra “calculando”, não zero/infinito |
| RT-169 | P1 | erro técnico | resumo simples + detalhe copiável redigido |

## 14. Render longo e aceite físico

### L1 — soak sintético

- duração suficiente para atravessar horas;
- múltiplas pausas e reinício controlado;
- volume com espaço monitorado;
- relatório de temperatura, throughput e commits;
- saída comparada ao controle.

### L2 — 8K/120 controlado

- fonte de teste autorizada;
- RIFE/Real-ESRGAN conforme RenderPlan;
- interrupção planejada após pelo menos três fases;
- retomada exclusivamente pela interface;
- staging se recomendado;
- quick verify, count-frames e deep verify conforme gate;
- inspeção perceptiva amostrada;
- promoção e cleanup simulada sem apagar evidência.

### L3 — armazenamento USB descartável

- volume sem dados pessoais;
- simulação controlada de indisponibilidade;
- confirmação de preservação/blocked;
- migração para SSD interno;
- nunca executar teste destrutivo em volume de produção.

## 15. Evidência por cenário

Formato mínimo:

```json
{
  "scenario": "RT-062",
  "commit": "<sha>",
  "environment": {},
  "fixture": "F0",
  "fault_point": "rife.unit.after_partial_write",
  "expected": [],
  "observed": [],
  "artifacts": [],
  "result": "pass|fail|skip",
  "skip_reason": null,
  "started_at": "...",
  "finished_at": "..."
}
```

Evidência humana inclui comando/gate, resumo, logs redigidos e hashes apenas de fixtures/saídas sintéticas.

## 16. Gates de release

### Gate A — source

- todos os P0 unitários;
- schema/migração;
- lint/compile/source hygiene;
- documentação/links/IDs.

### Gate B — CPU/media

- commit protocol;
- worker/concorrência simulada;
- FFmpeg sintético;
- verificação e promoção;
- storage abstraído.

### Gate C — Windows

- locks/process tree;
- volume identity;
- close/reopen UI;
- MSI/portátil e PowerShell.

### Gate D — GPU

- RIFE UHD;
- Real-ESRGAN aplicável;
- NVENC;
- pressão de VRAM e cancelamento.

### Gate E — físico/perceptivo

- render longo;
- SSD/USB controlados;
- inspeção amostrada;
- recuperação pela interface.

## 17. Regra de aprovação

- release de desenvolvimento: Gates A e B;
- RC Windows: A, B e C;
- RC com IA anunciada: A–D;
- estável com recuperação genérica: A–E e todos os requisitos P0 aceitos;
- qualquer `skip` em gate obrigatório bloqueia a reivindicação correspondente.
