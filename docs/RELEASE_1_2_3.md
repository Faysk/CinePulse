# CinePulse 1.2.3

CinePulse 1.2.3 é uma release de desempenho e confiabilidade sobre a base 1.2.2. O objetivo é aproveitar melhor GPU, VRAM, RAM e scratch sem reduzir qualidade, trocar modelo, alterar FPS, simplificar cor/HDR ou enfraquecer os contratos de integridade.

## GPU, VRAM e Real-ESRGAN

O Real-ESRGAN passa a separar de forma explícita o orçamento de host-feed de CPU da concorrência Vulkan da GPU.

- placas de 8 GB podem testar maior concorrência em geometrias seguras quando existe headroom livre suficiente;
- placas de 12 GB+ e 24 GB podem escalar a concorrência física sem exigir que o host-feed neural use todos os threads lógicos;
- políticas fisicamente aprovadas continuam limitadas pela VRAM livre no momento do render;
- pressão transitória de VRAM reduz a política ativa sem apagar evidência física válida quando o hardware/driver continuam compatíveis;
- OOM e falhas de integridade continuam recuando para uma política de menor ou igual pressão.

A chave de tuning inclui CPU, GPU, driver, geometria, componente verificado e envelope de host, evitando reaproveitar medições de um contexto incompatível.

## RAM, page cache e scratch

Os chunks neurais deixam de ficar artificialmente presos ao envelope legado de 4 GiB quando a máquina possui telemetria completa e memória disponível.

- Real-ESRGAN pode usar worksets host maiores, até o teto definido pela política;
- RIFE usa um teto separado e mais conservador por materializar mais quadros;
- a concorrência total de worksets continua rigidamente limitada;
- preflight, runtime e RenderHistory usam os mesmos budgets;
- scratch contabiliza os worksets simultâneos reais em vez de apenas um lote isolado.

Telemetria ausente continua fail-closed para o envelope conservador.

## Telemetria NVIDIA e multi-GPU

A telemetria passa a observar NVENC e NVDEC além de uso geral de GPU/VRAM. Quando o driver não expõe os novos campos, o sampler recua automaticamente para a consulta compatível anterior.

Em máquinas com múltiplas GPUs, a seleção da GPU ativa considera também atividade de encode, decode e memory engine, reduzindo a chance de escolher um adaptador ocioso apenas por compute momentâneo.

## Demucs e cache reativo

O caminho de stems recebeu hardening adicional:

- o mix temporário mantém extensão final `.wav`, para que o FFmpeg identifique corretamente o container durante o staging;
- arquivos WAV pequenos/inválidos não são aceitos como cache reutilizável;
- diretórios `.demucs-partial-*` deixados por crash nunca são usados como fonte de cache;
- somente stems completamente produzidos são promovidos para o cache definitivo;
- cancelamento ou erro remove o staging parcial sem substituir um resultado válido anterior.

## RIFE sob pressão de VRAM

Foi corrigido um caso em que o RIFE podia abortar em OOM antes de recalcular um fallback mais conservador.

Agora, quando uma execução já está no baseline `2:2:2` e a VRAM livre cai suficientemente durante a execução, o runtime pode recuar para `1:1:1` antes de desistir. Esse rollback não altera modelo, geometria, FPS ou qualidade; ele reduz apenas a pressão de concorrência.

## Segurança e aceitação

Os gates de software continuam separados da aceitação física.

Quality, Recovery Reliability, Installer v2 Acceptance e Release Candidate validam o comportamento reproduzível em CI. GPU Acceptance continua dependendo de runner NVIDIA físico e não é tratado como PASS enquanto essa evidência não existir.

CinePulse 1.2.3 não introduz nova alegação física para 8K/120, 10K/12K, TensorRT ou qualquer rota acelerada sem evidência compatível.
