# CinePulse 1.1.3 — Loop Storage Hotfix

CinePulse 1.1.3 corrige um bloqueio de armazenamento que afetava principalmente projetos em **Loop musical** com destinos de alta resolução e alto FPS, como 8K/120.

## O que foi corrigido

- A estimativa de armazenamento agora distingue a **duração do clipe reutilizável** da **duração total do projeto**.
- Pré-processamento de cor, Real-ESRGAN, master e transição de loop são estimados pela duração efetivamente materializada do clipe, em vez de herdarem automaticamente a duração inteira da música.
- O relatório de pré-verificação passa a expor a duração materializada por etapa, facilitando a auditoria de estimativas de scratch e cache.
- Em Loop musical, RIFE agora interpola o **clipe reutilizável uma única vez antes da expansão temporal** quando o destino exige aumento de FPS. O master e os VFX reutilizam esse resultado na cadência alvo.
- Projetos de **Melhorar vídeo original** preservam a política de RIFE final one-shot, evitando uma mudança desnecessária no fluxo já validado desse modo.
- Quando o VFX é a última etapa visual de um Loop musical, a composição do projeto inteiro é codificada **diretamente para a saída final**. O CinePulse deixa de materializar um master FFV1 de VFX com a duração total da música no scratch.
- O contrato de armazenamento foi alinhado ao fluxo realmente executado pelo worker, incluindo color prepass, cache neural, RIFE do clipe, master/transição, VFX e entrega final.
- O caminho fundido VFX + entrega mantém `AtomicOutput`, verificação final e descarte seguro em caso de cancelamento ou falha.

## Regressões cobertas

A suíte automatizada inclui um cenário de referência com clipe curto e timeline longa — incluindo **clipe de 10 s + projeto de 264 s + destino 8K/120** — para impedir que Real-ESRGAN, master, transição ou RIFE do clipe voltem a escalar pela duração inteira da música.

Também são cobertos:

- compatibilidade do argumento legado de duração do estimador;
- color prepass usando a duração do clipe;
- ausência de RIFE final duplicado em Loop musical otimizado;
- manutenção do RIFE final one-shot em vídeo original;
- VFX full-length por streaming sem intermediário FFV1 full-length no scratch;
- separação explícita entre duração do clipe e duração do projeto na integração de preflight.

## Observação sobre 8K/120

Este hotfix corrige a **arquitetura de cálculo e materialização de armazenamento**. A graduação física de 8K/120 continua sendo um gate separado que exige execução em hardware NVIDIA real compatível. A ausência desse teste físico não é tratada como aprovação implícita.
