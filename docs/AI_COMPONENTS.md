# Componentes de IA

Estados usados pelo CinePulse:

- **detectado**: os arquivos esperados existem;
- **integrado**: o pipeline consegue chamar o componente;
- **validado**: houve execução reproduzível, saída verificada e comparação;
- **experimental**: funciona em condições limitadas, sem garantia de estabilidade;
- **estável**: possui testes de regressão e licença revisada para a forma de distribuição.

O pipeline principal da 1.0 usa somente componentes com integração reproduzível: Real-ESRGAN, RIFE, Demucs e VMAF. Eles continuam opcionais e possuem fallback ou desativação segura quando aplicável.

BasicVSR++, CLAP, Depth Anything, SAM 2, CoTracker, CodeFormer e LTX podem ser baixados pelo modo experimental da tela **IA local**, mas **não são funções integradas ao render da 1.0**. Ter os arquivos no disco não altera o render. O usuário precisa ativar a opção avançada, revisar as licenças mostradas e confirmar que assume espaço, compatibilidade e uso. Cada motor só entra no pipeline depois de receber integração, fallback e validação próprios.

As ações **Selecionar necessários** e **Instalar necessários** incluem somente os componentes integrados faltantes. Experimentais só entram em uma instalação quando o modo avançado está ativo e o usuário os seleciona explicitamente. Video Depth Anything Large e CoTracker usam licenças não comerciais; CodeFormer usa a licença S-Lab; LTX-2 usa sua licença comunitária com restrições próprias. O conjunto LTX-2.3 inclui o checkpoint 22B destilado e o upscaler espacial e soma aproximadamente 44 GB sozinho. A confirmação do CinePulse não substitui nem remove essas condições.

O catálogo público não baixa modelos automaticamente sem URL imutável, licença conhecida e SHA-256 revisado.
## Como a tela IA local apresenta esses estados

A interface da Phase 6 separa a presença de arquivos da integração funcional:

- **Pronto no render**: componente integrado e detectado;
- **Faltando**: componente integrado ausente, acompanhado do fallback/impacto real;
- **Experimental • aceite necessário**: pacote fora do render e ainda bloqueado para seleção;
- **Disponível para baixar • não integrado**: opt-in experimental ativo, mas sem função no render;
- **Arquivos instalados • fora do render**: checkpoints/código detectados, sem ativação funcional.

`Selecionar necessários` e `Instalar necessários` trabalham apenas com Real-ESRGAN, RIFE, Demucs e VMAF. Ativar o modo experimental nunca coloca todos os experimentais na seleção automaticamente.

O inspector mostra download aproximado e licença antes da instalação. O percentual exibido durante downloads representa apenas a atividade/arquivo que informou explicitamente aquele percentual; não é ETA nem progresso global inventado.

O botão **Reverificar** força uma nova detecção dos componentes locais. A detecção do Demucs usa o mesmo requisito de manifesto `htdemucs_ft.yaml` do motor de stems.
