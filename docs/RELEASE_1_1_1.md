# CinePulse 1.1.1 — Reliability Hardening

CinePulse 1.1.1 é uma release de correção e endurecimento pós-1.1.0. O foco é confiabilidade real de instalação, atualização portátil, runtime Windows e gates de distribuição, sem ampliar claims de capacidades Preview/extremas.

## Correções principais

- atualizador portátil passa a tratar o payload gerenciado como uma transação completa, preservando somente `.runtime`, `components`, `data`, `cache` e `temp`;
- o pacote recebido é validado pelo `cinepulse-files.json` antes da troca e a árvore final é validada novamente depois da aplicação;
- fault injection cobre falha depois da remoção e depois da cópia, provando rollback sem mistura de versões;
- o wrapper PowerShell do updater deixa de usar `$LASTEXITCODE` depois de chamar outro `.ps1` e passa a propagar exceções corretamente;
- staging de update valida SemVer, HTTPS e SHA-256 também na fronteira de staging, não apenas no fluxo de descoberta;
- mutex Win32 usa `HANDLE` pointer-sized corretamente em Python 64-bit;
- Python privado se autorrepara quando está ausente, corrompido ou quando a versão gerenciada muda, forçando reinstalação das dependências quando necessário;
- cache do `uv` fica vinculado a versão e SHA-256 do artefato;
- FFmpeg e componentes gerenciados deixam de reutilizar apenas por existência: versão/SHA do manifesto participam do readiness;
- Real-ESRGAN/RIFE exigem versão + SHA para reutilização e a promoção de componentes é reversível em falha após promote;
- readiness do Demucs passa a incluir Python, Torch, Demucs, SoundFile, CUDA runtime e índice Torch;
- Quality passa a testar também o runtime distribuído Python 3.14.7;
- Installer v2 Acceptance vira gate permanente de `main` com versão dinâmica;
- Release Candidate fica vinculado à versão real declarada pelo código;
- GPU Acceptance passa a preparar o runtime autocontido de release antes dos testes físicos.

## Distribuição

A release continua usando o Installer v2 autocontido: a pasta escolhida pelo usuário contém Python privado, componentes, modelos, dados, cache e temporários do CinePulse. O driver NVIDIA permanece uma dependência do Windows; o runtime CUDA usado pelo PyTorch permanece privado ao ambiente neural do projeto.

## Gates exigidos antes da publicação

A publicação de 1.1.1 só ocorre após:

- Quality em Windows/Linux incluindo Python 3.14.7;
- Recovery Reliability;
- Installer v2 Acceptance em Windows;
- Release Candidate Windows completo;
- build e validação do portátil;
- rollback/update transacional real;
- build, validação, install, repair e uninstall do MSI;
- geração de SBOM e SHA256SUMS.

## Limites mantidos honestamente

O gate físico NVIDIA/8K continua separado quando não há runner `cinepulse-gpu` online. 8K/120 neural, aceitação perceptiva extrema e promoção de capacidades Preview não são declaradas como fisicamente aprovadas por esta release apenas porque os gates automatizados passaram.
