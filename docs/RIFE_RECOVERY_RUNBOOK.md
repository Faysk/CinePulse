# Runbook — recuperação segura de render RIFE interrompido

**Status:** operacional para o layout de chunks da Phase 6

**Última revisão:** 31 de agosto de 2026

**Público:** mantenedores e suporte técnico local
**Risco:** alto; o procedimento manipula centenas de gigabytes e não deve ser improvisado

## 1. Quando usar

Use este runbook quando um render interrompido possuir:

- histórico persistente do job;
- fonte original disponível;
- cache de entrada da etapa RIFE disponível;
- diretório de chunks `rife_*` com segmentos FFV1;
- configuração suficiente para reconstruir resolução, FPS, duração e entrega.

Não use o render comum da interface sobre os mesmos caminhos. Não use este procedimento para um layout desconhecido, segmentos não FFV1 ou contrato que não possa ser reconstruído.

## 2. Princípios de segurança

1. **Preservar primeiro.** Nenhum segmento, cache, master ou parcial existente é apagado para “tentar de novo”.
2. **Um processo por job.** Antes de iniciar, procurar Python/FFmpeg que já referencie o estado ou o parcial.
3. **Sequência contígua.** Uma lacuna invalida a retomada automática até diagnóstico.
4. **Commit validado.** Arquivos `.partial` nunca contam como progresso confirmado.
5. **Identidade da fonte/cache.** Caminho, tamanho e mtime devem continuar compatíveis com o contrato registrado.
6. **Promoção atômica.** A entrega só recebe o nome final depois da verificação.
7. **Falha preserva evidência.** Um parcial rejeitado recebe outro nome; não é sobrescrito silenciosamente.

## 3. Artefatos e fases

| Fase | Evidência principal | Condição de saída |
|---|---|---|
| `validated` | inventário da fonte, cache e segmentos | contrato reconstruído sem divergência |
| `repair` | auditoria e commits de reparo | todos os segmentos existentes sem o preto determinístico |
| `rife` | `segment_NNNNN.mkv` contíguos | segmentos e quadros totais completos |
| `master_ready` | `recovered_rife_master.mkv` | contagem/duração exatas |
| `final_encoding` | MP4 parcial + progresso | encoder fechou o contêiner |
| `complete` | resultado + job + saída final | contrato técnico passou e parcial foi promovido |

O arquivo `recovery-state.json` é escrito por arquivo temporário e `os.replace`. Ele é a visão resumida; o log append-only contém a explicação completa.

## 4. Diagnóstico inicial somente leitura

Antes de qualquer processo de recuperação:

- conferir se outro recuperador ou FFmpeg do mesmo job está ativo;
- registrar tamanho e data da fonte, cache, chunk root, master e parciais;
- ler `job.json`, `recovery-state.json` e o fim de `recovery.log`;
- contar apenas `segment_?????.mkv`;
- confirmar que os índices começam em 1 e são contíguos;
- executar `validate` antes de `resume`;
- conferir espaço nos volumes do scratch, master e saída;
- identificar se os volumes são internos ou USB.

Exemplo parametrizado:

```powershell
$python = '<projeto>\.venv\Scripts\python.exe'
$common = @(
  '--app-root', '<instalacao-cinepulse>',
  '--history-dir', '<logs>\renders\<job-id>',
  '--chunk-root', '<scratch>\job_x\rife_x',
  '--cache', '<dados>\cache\ai\<chave>.mkv',
  '--source', '<entrada>',
  '--output', '<saida>',
  '--timeout-minutes', '20'
)
& $python -m cinepulse.rife_recovery validate @common
```

`validate` não deve reprocessar segmentos nem promover saída.

## 5. Auditoria e reparo de quadros pretos

Execute o reparador antes de retomar quando o job for 8K/RIFE antigo ou houver suspeita visual:

```powershell
& $python -m cinepulse.rife_black_repair @common
```

O reparo é seguro somente se cada segmento novo:

- possuir a mesma quantidade de pacotes do segmento substituído;
- estiver em FFV1, na resolução e no FPS esperados;
- contiver PNGs estruturalmente íntegros durante a geração;
- não contiver pacotes correspondentes ao quadro preto determinístico;
- tiver o original preservado em `black-frame-quarantine`;
- for promovido apenas depois dessas validações.

O detector rápido de tamanho de pacote é específico para FFV1 level 3, yuv420p e 7680×4320 da ocorrência. Para outra resolução, pixel format ou encoder, não reutilizar a constante sem nova calibração cruzada por decodificação.

## 6. Retomada

Depois da validação/reparo:

```powershell
& $python -m cinepulse.rife_recovery resume @common
```

O recuperador deve:

- revalidar tudo antes de alterar dados;
- derivar o próximo segmento da sequência contígua, não de um percentual antigo;
- usar RIFE nativo 2× em UHD/serial para a rota segura 8K;
- ajustar temporalmente somente quando o segmento exigir 17/18 quadros;
- atualizar o checkpoint depois de cada commit;
- auditar todos os segmentos novamente antes do master;
- reutilizar master/parcial apenas se passarem pelo contrato atual.

## 7. Pausa e retomada

Para pedir pausa cooperativa, criar `STOP_RECOVERY` no diretório do job. O processo deve terminar a fronteira segura que estiver executando e parar sem apagar commits anteriores.

Antes de continuar:

1. confirmar que o processo anterior saiu;
2. remover somente a sentinela `STOP_RECOVERY`;
3. executar novamente `validate`;
4. executar `resume` com os mesmos caminhos.

Matar o processo pode deixar diretórios de entrada/saída temporários ou um `.partial`. A próxima execução deve colocá-los em quarentena ou ignorá-los; nunca deve contá-los como segmento confirmado.

## 8. Concatenação do master

O manifesto deve declarar para cada segmento:

```text
duration = packet_count / target_fps
```

Não confiar na duração arredondada individual do Matroska quando milhares de segmentos curtos forem concatenados. O master só pode ser reutilizado quando resolução, FPS, codec, contagem e duração estiverem dentro do contrato.

Um master parcial que falhou a validação deve ser preservado com nome diagnóstico, sem ocupar o caminho do master confirmado.

## 9. Escolha do volume para a entrega

Antes do encode final, calcular espaço para:

- master local, caso seja staged;
- MP4 parcial completo;
- saída anterior/backup, se existir;
- margem operacional do sistema de arquivos.

Para masters de centenas de GiB:

- preferir SSD/NVMe interno para leitura e saída;
- usar cópia reiniciável e não bufferizada ao mover de HDD/USB;
- validar tamanho e duração da cópia antes de reutilizá-la;
- manter o master original até o aceite final;
- evitar `faststart` em uma entrega local muito grande, salvo necessidade explícita de streaming progressivo.

## 10. Verificação e promoção

Contrato mínimo antes da promoção:

- largura e altura exatas;
- FPS médio e nominal compatíveis com CFR;
- contagem real de quadros igual ao esperado;
- duração dentro da tolerância;
- codec de vídeo e áudio esperados;
- canais e sample rate esperados;
- delta A/V dentro da tolerância;
- nenhum problema reportado;
- contêiner legível depois de o encoder fechar.

O quick verify com contagem real pode levar horas em 8K/120. `decoded_to_eof=false` significa que o deep verify separado não foi executado. A UI futura deve dizer isso de forma explícita.

Somente depois do resultado aprovado:

1. promover o parcial com `os.replace`;
2. gravar `recovery-result.json`;
3. marcar `recovery-state.json` como `complete`;
4. atualizar `job.json` para `success`, `recovered=true`;
5. manter logs e evidências.

## 11. Como interpretar desempenho

O pipeline não é uma única carga GPU:

| Etapa | Limitador provável |
|---|---|
| extração PNG | leitura/decodificação e disco |
| RIFE | GPU/Vulkan e VRAM |
| FFV1 por segmento | CPU e escrita |
| concatenação copy | leitura/escrita e metadados |
| HEVC NVENC | alimentação do encoder, GPU e disco |
| contagem/verificação | leitura e decodificação/probe |

GPU baixa isoladamente não prova subutilização. Avaliar progresso de quadros, taxa de I/O, VRAM, temperatura, clocks e fase atual em conjunto.

## 12. Critérios de bloqueio

Parar e preservar tudo quando ocorrer qualquer um destes casos:

- fonte/cache mudaram de identidade;
- sequência de segmentos possui lacuna inexplicada;
- segmento novo não tem a contagem esperada;
- PNG truncado, quadro preto ou erro de codec persiste após a rota segura;
- master diverge em duração/quadros;
- não há espaço com margem no destino;
- parcial não fecha o contêiner;
- já existe outro processo do mesmo job;
- os parâmetros necessários não podem ser reconstruídos com evidência.

## 13. Testes relacionados

- `tests/test_rife_recovery.py`: distribuição exata de quadros, sequência contígua, timeline de concatenação, cache identity e remoção seletiva de `faststart`;
- `tests/test_matroska_quality.py`: leitura estrutural dos pacotes Matroska;
- caso real: [pós-mortem 8K/120](INCIDENT_2026-08-26_RIFE_8K120.md).
