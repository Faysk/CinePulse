# Componentes de IA

Estados usados pelo CinePulse:

- **detectado**: os arquivos esperados existem;
- **integrado**: o pipeline consegue chamar o componente;
- **validado**: houve execução reproduzível, saída verificada e comparação;
- **experimental**: funciona em condições limitadas, sem garantia de estabilidade;
- **estável**: possui testes de regressão e licença revisada para a forma de distribuição.

O pipeline principal da 1.0 usa somente componentes com integração reproduzível: Real-ESRGAN, RIFE, Demucs e VMAF. Eles continuam opcionais e possuem fallback ou desativação segura quando aplicável.

BasicVSR++, CLAP, Depth Anything, SAM 2, CoTracker, CodeFormer e LTX podem ser baixados pelo modo experimental da tela **IA local**, mas **não são funções integradas ao render da 1.0**. Ter os arquivos no disco não altera o render. O usuário precisa ativar a opção avançada, revisar as licenças mostradas e confirmar que assume espaço, compatibilidade e uso. Cada motor só entra no pipeline depois de receber integração, fallback e validação próprios.

O botão **Instalar tudo disponível** inclui os experimentais somente quando o modo avançado está marcado. Video Depth Anything Large e CoTracker usam licenças não comerciais; CodeFormer usa a licença S-Lab; LTX-2 usa sua licença comunitária com restrições próprias. O conjunto LTX-2.3 inclui o checkpoint 22B destilado e o upscaler espacial e soma aproximadamente 44 GB sozinho. A confirmação do CinePulse não substitui nem remove essas condições.

O catálogo público não baixa modelos automaticamente sem URL imutável, licença conhecida e SHA-256 revisado.
