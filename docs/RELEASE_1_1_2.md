# CinePulse 1.1.2 — Complete Product Hardening

CinePulse 1.1.2 fecha a auditoria pós-1.1.1 com foco em integridade de estado, concorrência, cancelamento, atualização segura e confiabilidade do processo de release. Esta versão não amplia artificialmente claims de GPU/extremo: capacidades que dependem de hardware físico continuam separadas dos gates automatizados.

## Correções principais

- preflight deixa de inferir arquivo/diretório pelo sufixo e passa a tratar corretamente diretórios existentes com ponto no nome;
- `AtomicOutput` elimina a janela em que um crash poderia remover a saída final válida antes da promoção do novo artefato;
- checagem de processo trata `PermissionError` de forma conservadora, evitando classificar processo vivo como lock stale;
- JobLease usa assinaturas Win32 pointer-sized e fencing de mutação cross-process/host, reduzindo races de takeover/heartbeat/release;
- single-instance lock fora do Windows passa a registrar token de início do processo e nonce de ownership, recuperando PID reuse sem apagar lock de outro processo;
- cancelamento POSIX aguarda SIGTERM e escala para SIGKILL quando necessário, em vez de abandonar filhos resistentes;
- persistência de fila e presets recupera estado corrompido a partir de `.bak` validado, preserva evidência do arquivo inválido e recusa downgrade silencioso de schema futuro;
- cancelamento do worker respeita transições válidas da máquina de estados, inclusive o caminho `pause_requested -> paused -> cancelled`;
- updater passa a impor limites de manifesto, assinatura, download, quantidade de entradas e tamanho expandido;
- extração de update rejeita path traversal, drives indevidos, symlinks, entradas criptografadas e duplicatas case-insensitive;
- staging de update limpa artefatos incompletos após qualquer falha e valida HTTPS também para links de notas;
- orientação de update do MSI passa a refletir corretamente o layout autocontido escolhido pelo usuário;
- workflows temporários com permissão de escrita são removidos antes da release, mantendo `publish-release.yml` como único writer permanente;
- metadados de versão de pacote, portátil, MSI e RC ficam sincronizados em `1.1.2`;
- publisher passa a derivar o arquivo de release notes da própria versão e a publicar automaticamente quando os metadados de versão chegam à `main`.

## Distribuição

A distribuição continua autocontida por diretório no Windows. Python privado, componentes, modelos, dados, cache e temporários permanecem sob a raiz CinePulse escolhida na instalação. O driver NVIDIA continua sendo dependência do sistema operacional; o runtime CUDA usado pelo stack neural permanece isolado no ambiente do CinePulse.

Os artefatos oficiais da release são:

- `CinePulse-1.1.2-windows-portable.zip`;
- `CinePulse-1.1.2-Setup.msi`;
- `CinePulse-1.1.2-Setup-manifest.json`;
- `CinePulse-1.1.2-SBOM.cdx.json`;
- `SHA256SUMS.txt`.

## Gates obrigatórios antes da publicação

A publicação só pode ocorrer depois de:

- Quality em Windows/Linux para a matriz suportada, incluindo Python 3.14.7;
- integrações CPU e integridade de mídia;
- Recovery Reliability;
- Installer v2 Acceptance;
- Release Candidate Windows completo;
- build e validação do portátil;
- teste do updater e rollback transacional;
- build, validação, install, repair e uninstall do MSI;
- geração de SBOM e SHA256SUMS;
- verificação de versão sincronizada e release notes correspondentes.

## Limites mantidos honestamente

O gate físico `cinepulse-gpu` continua sendo evidência separada. Enquanto não houver execução física bem-sucedida no runner NVIDIA alvo, 8K/120 neural, recuperação extrema e aceitação perceptiva associada não são promovidos para “fisicamente aceitos” apenas porque CI, build e testes automatizados passaram.

10K/12K e 144/240/480 fps permanecem experimentais conforme a política atual do projeto.
