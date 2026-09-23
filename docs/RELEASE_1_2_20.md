# CinePulse 1.2.20

Esta release candidata consolida a rodada de hardening executada após a 1.2.19. O foco é impedir corrupção silenciosa, estado otimista, reutilização de cache incorreto, processo órfão e promoção parcial de outputs.

## Integridade de pacote e bootstrap

Portable e MSI convergem no mesmo contrato de manifesto, e o empacotador só publica o ZIP quando o próprio runtime consegue verificar o manifesto gerado. O bootstrap deixa de confiar apenas em markers: UV, FFmpeg, RIFE e Real-ESRGAN precisam corresponder ao conteúdo realmente instalado.

## Recovery e persistência

A descoberta de recovery passa a ser read-only de verdade. Backup-only e primary corrompido permanecem preservados para auditoria, sem reparo automático durante startup. O recovery RIFE usa checkpoints duráveis e promove a saída final em um único replace atômico, preservando o arquivo anterior se a publicação falhar.

## Worker, cancelamento e subprocessos

Comandos presos em processing após crash são reconciliados sob lease. Restoration, VFX, modo clássico, Aurora, prefetch/background e caminhos neurais do Studio encerram árvores de processo e fecham pipes deterministicamente também em exceções e cancelamentos.

## Caches e componentes

Caches de mídia/stems deixam de depender apenas de caminho, tamanho e mtime: a identidade passa a incluir conteúdo. Demucs/Real-ESRGAN vinculam cache aos componentes/modelos críticos. Archives experimentais ganham limites estruturais, tamanho exato + SHA-256 e fingerprint da árvore instalada.

## Evidência física

Uma rodada EXTREME em 23/09/2026 no Acer Predator PHN16-72 com RTX 4070 Laptop confirmou capacidade física para CUDA/PyTorch, NVDEC, NVENC 1080p60, NVDEC→CUDA→NVENC 4K60, RIFE 1080p, Real-ESRGAN 1080p→4K, Demucs CUDA, recovery RIFE 8K e HEVC NVENC 8K120 bounded.

Essa execução usou uma instalação 1.2.0 e, portanto, não promove o gate físico da 1.2.20. O GPU Acceptance continua pendente até repetir a bateria com os bytes desta build candidata.
