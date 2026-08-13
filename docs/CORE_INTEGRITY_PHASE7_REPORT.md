# Core Integrity MegaPack — Phase 7

## Escopo

Phase 7 implementa **Verification & Render History** e fecha os achados CP-014, CP-023 e CP-029 da auditoria de 13/08/2026 no caminho ativo do Studio.

A fase não altera a intenção artística do render. Ela torna o resultado comprovável, persistente e recuperável entre sessões.

## Implementação concluída

### 1. Verificação técnica estruturada

Novo módulo `src/cinepulse/verification.py`.

A verificação rápida agora confere:

- resolução final;
- FPS efetivo;
- cadência CFR (`r_frame_rate` versus `avg_frame_rate`);
- duração;
- contagem de quadros lidos pelo FFprobe;
- presença ou ausência de áudio conforme o projeto;
- codec de vídeo e áudio esperados pelo DeliveryPlan;
- canais;
- sample rate;
- diferença de término entre streams de áudio e vídeo.

Erros contratuais bloqueiam a promoção do arquivo parcial.

### 2. Verificação profunda opcional

A aba **Qualidade e saída → Áudio e verificação final** ganhou:

`Verificação profunda — decodificar o arquivo final até o fim e conferir A/V`.

Quando habilitada em um render final, o CinePulse executa a verificação rápida e depois decodifica os streams esperados com FFmpeg `-xerror` até EOF. Corrupção ou erro de decode impede que a saída seja anunciada como válida.

Preview continua usando quick verify para evitar custo desnecessário.

### 3. Histórico persistente por job_id

Novo módulo `src/cinepulse/render_history.py`.

Cada preview/render cria:

```text
data/logs/renders/<job_id>/
    job.json
    render.log
    plan.json
    contracts.json
    verification.json
```

`job.json` registra versão, estado, início/fim, preview/final, fila, saída, relatório e snapshot de `RenderSettings`.

`render.log` recebe comandos, decisões, etapas, fallbacks, avisos e erros mesmo depois que a interface é fechada.

`plan.json` persiste o RenderPlan exato/fingerprint.

`contracts.json` persiste contratos de cor, entrega, storage e expectativa da verificação.

`verification.json` persiste o resultado técnico, inclusive frame count, CFR, codecs, canais, sample rate, A/V delta e decode EOF.

### 4. Exportação de suporte com paths redigidos

`export_redacted_history()` produz ZIP de suporte removendo caminhos absolutos Windows/POSIX dos arquivos textuais/JSON, preservando basename/extensão para diagnóstico.

A função está pronta para futura ação de UI; a Phase 7 não adiciona upload nem telemetria.

### 5. Relatório humano enriquecido

O relatório final agora inclui uma seção **VERIFICAÇÃO TÉCNICA** com:

- quick/deep;
- PASS/FAIL;
- quadros lidos versus esperados;
- CFR;
- decode até EOF;
- delta A/V;
- warnings estruturados, quando existirem;
- caminho local do histórico técnico.

### 6. Fila e presets versionados

Novo módulo `src/cinepulse/state_store.py`.

Fila:

```json
{
  "schema": 2,
  "kind": "cinepulse.queue",
  "items": []
}
```

Presets:

```json
{
  "schema": 1,
  "kind": "cinepulse.presets",
  "items": {}
}
```

O loader reconhece o formato legado, migra automaticamente, mantém compatibilidade com configurações antigas e cria `.bak` antes da promoção atômica da nova versão.

Schemas futuros desconhecidos são rejeitados em vez de reinterpretados silenciosamente.

A fila também persiste o caminho de histórico técnico por item e oferece o botão **Histórico técnico** no inspector.

## RenderPlan

Arquitetura atual:

`core-integrity-phase7-verification-history`

Códigos tratados acrescentados ao contrato:

- CP-014;
- CP-023;
- CP-029.

## Validação executada

- suíte automatizada: **159/159 PASS**;
- smoke Studio básico: PASS;
- Delivery Matrix MP4/MOV/MKV/WebM após a nova verificação: PASS;
- `tests/integration_verification.py`: worker real + deep verify 1280×720/30 fps, 72/72 quadros, CFR, AAC 48 kHz, decode EOF e A/V delta 0.000 s: PASS;
- histórico real do worker contendo `job.json`, `render.log`, `plan.json`, `contracts.json` e `verification.json`: PASS;
- migração e backup de fila/presets cobertos por testes;
- export de suporte com redaction de paths coberto por testes.

## Estado dos achados

- **CP-014:** tratado por quick/deep verify estruturado;
- **CP-023:** tratado por histórico/log persistente por `job_id`;
- **CP-029:** tratado por schema, validação, backup e migração de fila/presets.

## Limites deliberados

- deep verify aumenta I/O/tempo porque lê o arquivo completo; por isso é opcional;
- A/V sync é validado pelo contrato temporal dos streams e não substitui inspeção perceptiva labial em conteúdo real;
- export redigido existe no domínio técnico, mas ainda não recebeu botão dedicado fora do inspector de histórico;
- integração dos scripts `integration_*.py` ao discovery/CI continua reservada para Phase 9;
- mutex de segunda instância, MSI/portátil, runtime fixado e SBOM continuam para Phase 8.

## Próxima fronteira

Phase 8 — Runtime & Distribution:

- separar comportamento MSI/portátil;
- Python gerenciado obrigatório no portátil;
- descoberta única de PowerShell;
- mutex por usuário e lock real de render;
- locks reprodutíveis/SBOM;
- assinatura de manifesto e branding Windows.
