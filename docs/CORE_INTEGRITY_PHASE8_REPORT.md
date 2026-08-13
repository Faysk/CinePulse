# Core Integrity MegaPack — Phase 8

## Escopo

Phase 8 implementa **Runtime & Distribution** sobre a base acumulada das Phases 1–7. O foco é fechar divergências entre MSI e portátil, remover dependências acidentais do ambiente Windows do usuário, bloquear segunda instância e preparar uma cadeia de distribuição verificável.

Achados diretamente tratados no caminho implementado:

- CP-010 — MSI e portátil misturados;
- CP-017 — descoberta inconsistente de PowerShell;
- CP-018 — pacote portátil dependente de Python do sistema;
- CP-030 — segunda instância não efetivamente bloqueada;
- CP-031 — branding Windows incompleto.

Achados fortalecidos, mas deliberadamente ainda abertos:

- CP-019 — assinatura de update/AuthentiCode precisa de chaves/certificados reais em release;
- CP-020 — lock com hashes/SBOM implementados para o núcleo, mas o grafo transitivo pesado ainda não está totalmente pinado por wheel/hash.

## Implementação concluída

### 1. Contratos MSI e portátil separados

Foram adicionados:

```text
CinePulse-Installed.cmd
Install-CinePulse-Installed.cmd
```

Os launchers instalados sempre passam `-NonPortable`. O MSI aponta exclusivamente para esses arquivos e não depende do marcador `.cinepulse-portable`.

No modo instalado, dados, runtime e componentes passam a viver sob `%LOCALAPPDATA%\CinePulse`; no portátil permanecem ao lado do pacote.

A UI instalada informa que o núcleo deve ser atualizado por MSI e não executa sobrescrita in-place do self-updater portátil.

### 2. Python gerenciado obrigatório

`Start-CinePulse.ps1` remove o fallback para `Find-SystemPython`.

O ambiente é criado com a versão fixada no bootstrap e `uv --python-preference only-managed`. A instalação do lock usa hashes obrigatórios e somente wheels binários.

### 3. PowerShell centralizado

Novo `runtime_distribution.py` fornece `find_powershell()` e é consumido pela UI para instalação/reparo de componentes.

A regra única prioriza PowerShell 7 e só usa Windows PowerShell como fallback.

### 4. Single-instance real

`app.py` adquire `InstanceGuard` antes de construir a janela.

- Windows: named mutex por usuário;
- CI/non-Windows: PID lock atômico testável e recuperável quando stale.

### 5. MSI corrigido

WiX passa a usar:

- versão dinâmica de build;
- launcher instalado;
- instalador instalado `-NonPortable -InstallOnly`;
- `cinepulse.ico` em atalhos/registro;
- payload sem marcador portátil.

`Build-Msi.ps1` converte versões RC/estável para um esquema monotônico compatível com MSI e recalcula o manifesto de integridade depois de transformar o payload.

### 6. Update assinado — infraestrutura

Novo `signatures.py` verifica assinaturas destacadas. `update_manager.py` consegue exigir assinatura do manifesto antes de interpretar seu JSON.

`Build-Portable.ps1` recebe chave pública, chave privada e executável de assinatura para produzir `cinepulse-update.json.minisig` e canal schema 2.

Nenhuma chave privada fictícia é incluída no repositório.

### 7. Authenticode — infraestrutura

`Build-Msi.ps1` possui caminho explícito para SignTool/certificado/thumbprint, assinatura SHA-256, timestamp e verificação pós-assinatura.

Sem certificado, o build permanece claramente não assinado.

### 8. SBOM e lock

Novo `scripts/generate_sbom.py` produz CycloneDX 1.5. O build portátil inclui o SBOM antes de gerar o manifesto de integridade.

O lock principal passa a incluir hash de wheel e o bootstrap exige `--require-hashes`.

O lock transitivo completo do stack Demucs/PyTorch continua registrado como pendência em vez de ser fingido como reproduzível.

### 9. Diagnóstico e cleanup

Diagnóstico passa a registrar:

- portable/installed;
- roots de programa/dados/componentes;
- PowerShell resolvido.

Foi adicionado `Remove-CinePulse-UserData.ps1` para limpeza explícita de runtime/cache/temp/logs e componentes opcionais.

## RenderPlan

Arquitetura atual:

`core-integrity-phase8-runtime-distribution`

Códigos acrescentados como resolvidos:

- CP-010;
- CP-017;
- CP-018;
- CP-030;
- CP-031.

`pending_audit_codes` mantém explicitamente:

- CP-011;
- CP-016;
- CP-019;
- CP-020;
- CP-027;
- CP-032;
- CP-033.

## Validação executada neste ambiente

Ambiente disponível: Linux, Python 3.13 e ferramentas Python/FFmpeg locais.

Validações possíveis aqui:

- suíte automatizada Phase 8: **176 testes**;
- `compileall` de `src`, `tests` e `scripts`;
- release gate Python;
- geração CycloneDX do SBOM;
- testes do contrato portable/installed;
- bloqueio de segunda instância e recuperação de stale lock;
- smoke do entrypoint em dois processos reais no backend de lock não-Windows, com a segunda instância recusada;
- escolha centralizada de PowerShell por mocks;
- verificação estática do WiX e dos launchers instalados;
- validação do cabeçalho/arquivo ICO;
- testes de comando e falha fatal da verificação de assinatura.

## Limite de validação do ambiente

Este ambiente **não possui Windows/PowerShell/WiX/SignTool nem certificado de assinatura**. Portanto não são reivindicados aqui como executados:

- build MSI real;
- install/upgrade/repair/uninstall MSI;
- execução real dos launchers `.cmd`/PowerShell;
- verificação Win32 visual dos atalhos/ícone;
- assinatura Authenticode real;
- update real assinado com chave privada CinePulse.

Esses itens passam a ser gate obrigatório Windows na Phase 9/release candidate.

## Estado dos achados

| Achado | Estado após Phase 8 |
|---|---|
| CP-010 MSI vs portátil | **tratado em código**; aceite Windows ainda pendente |
| CP-017 PowerShell inconsistente | **tratado em código** |
| CP-018 Python do sistema | **tratado em código** |
| CP-019 canal sem assinatura | **parcial** — verificação/build prontos, chave/release real pendentes |
| CP-020 dependências reproduzíveis | **parcial** — hash/SBOM do núcleo, lock transitivo pesado pendente |
| CP-030 segunda instância | **tratado em código**; mutex Win32 requer smoke Windows |
| CP-031 branding Windows | **tratado no payload/WiX/UI**; aceite visual Windows pendente |

## Próxima fronteira

Phase 9 — CI & Release Gates:

- colocar integrações leves no discovery/gate automático;
- matriz Windows para build portátil/MSI;
- install → upgrade → repair → uninstall;
- update/rollback, inclusive canal assinado;
- smoke de runtime sem Python/FFmpeg do sistema;
- gates separados para GPU/HDR/renders pesados;
- fechar ou reclassificar CP-019/CP-020 com evidência de release real.
