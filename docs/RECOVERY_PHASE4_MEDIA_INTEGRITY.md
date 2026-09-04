# Recovery & Reliability Mega Pack — Phase 4: Media Integrity

**Status:** implementation candidate
**Base:** Phase 3 (`e863241b0e8bf52387d93309aaeba601ceeb7262`)
**Gate alvo:** G4

## Entrega

A validação deixa de depender apenas de metadata, exit code ou do fast path específico de tamanho FFV1 observado no incidente.

### Detector genérico de sinal

Novo `frame_quality.py` trabalha sobre luma reduzida e mede:

- média e desvio de luminância para preto real;
- MAE entre frames consecutivos;
- intervalos de freeze;
- contexto de movimento ao redor do freeze;
- timeline PTS com gaps, duplicações ou reversão.

Uma cena legitimamente estática não é classificada como freeze apenas porque vários frames são iguais. O alerta exige contexto de movimento em pelo menos uma borda do intervalo.

### Decode de qualidade

`decode_luma_frames()` usa FFmpeg para reduzir o vídeo a amostras grayscale 64×36. O objetivo é detectar defeitos grosseiros de sinal com custo muito menor que análise perceptiva full-resolution. Esse gate não declara qualidade artística.

### QualityStage

`media_quality_validator()` combina:

1. contrato estrutural da Phase 3 (size/FPS/codec/pix_fmt/frame count);
2. black/freeze por sinal;
3. PTS por FFprobe.

Qualquer falha impede `ValidationResult.passed`, portanto o `AtomicStageAdapter` não promove a unidade.

### Relação com `matroska_quality.py`

O detector de pacote FFV1 8K continua válido como fast path calibrado para o incidente e como ferramenta forense. Ele não é mais o desenho do detector universal. O gate genérico é independente de resolução, codec e tamanho exato do pacote.

## Testes

- quadro preto detectado sem usar tamanho de pacote;
- cena estática legítima não gera falso freeze;
- freeze inserido entre movimento é detectado;
- duplicate PTS e gap são sinalizados;
- structural + signal + timeline passam juntos no caso válido;
- black frame torna o quality validator reprovado.

## Limites

- thresholds são conservadores e devem ser calibrados no Gate físico/perceptivo;
- inspeção artística de oclusão/motion warping continua humana/amostrada;
- análise full video muito longo pode ser configurada por amostragem no rollout; segmentos curtos podem ser analisados integralmente em baixa resolução.

## Gate G4

A lógica genérica está implementada e testável em CI. O requisito só recebe estado `aceito` para RIFE 8K depois da matriz Windows/NVIDIA e inspeção física prevista na Phase 7.
