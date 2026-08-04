# Componentes de IA

Estados usados pelo CinePulse:

- **detectado**: os arquivos esperados existem;
- **integrado**: o pipeline consegue chamar o componente;
- **validado**: houve execução reproduzível, saída verificada e comparação;
- **experimental**: funciona em condições limitadas, sem garantia de estabilidade;
- **estável**: possui testes de regressão e licença revisada para a forma de distribuição.

O pipeline principal da 1.0 usa somente componentes com integração reproduzível: Real-ESRGAN, RIFE, Demucs e VMAF. Eles continuam opcionais e possuem fallback ou desativação segura quando aplicável.

BasicVSR++, CLAP, Depth Anything, SAM 2, CoTracker, CodeFormer e LTX podem ser detectados na instalação de desenvolvimento, mas **não são funções da 1.0**. Ter os arquivos no disco não altera o render. Cada um só poderá entrar no produto depois de receber pipeline, interface, fallback, testes e revisão de licença próprios.

O catálogo público não baixa modelos automaticamente sem URL imutável, licença conhecida e SHA-256 revisado.
