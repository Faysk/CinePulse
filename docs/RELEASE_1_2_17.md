# CinePulse 1.2.17

Esta release fecha uma lacuna no recovery de saída final interrompida. O CinePulse já preservava o `.partial` e pedia confirmação antes de promovê-lo, mas a validação de startup era permissiva demais: bastava o container ser legível, ter alguma duração e resolução não-zero.

## Recovery do partial agora usa o contrato completo

O `render.json` passa a persistir a expectativa de mídia necessária para recuperar com segurança:

- largura e altura;
- FPS e duração CFR frame-bound;
- presença/ausência de áudio;
- codec de vídeo e áudio;
- canais e sample rate;
- nível de verificação quick/deep.

Antes de oferecer a promoção, o CinePulse executa `quick_verify` com tolerância de frames igual a zero e exige que o FFprobe informe a contagem exata. Um arquivo truncado porém reproduzível não passa mais como resultado final.

## Deep Verify preservado

Se o render original foi configurado com Deep Verify, o startup recovery também precisa decodificar a saída até EOF antes de promover. O recovery não rebaixa silenciosamente a garantia pedida pelo usuário.

## Journals antigos

Journals anteriores que não possuem o contrato completo não são adivinhados. O partial é preservado para inspeção/manual recovery, mas não é promovido automaticamente.

## Proteções mantidas

AtomicOutput, promoção atômica, full-utilization, fallback GPU→CPU, recovery de jobs/checkpoints e toda a verificação final da 1.2.16 permanecem inalterados.
