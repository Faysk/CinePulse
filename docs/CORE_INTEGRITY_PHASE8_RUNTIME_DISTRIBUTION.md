# Core Integrity Phase 8 — Runtime & Distribution

## Objetivo

Separar de forma explícita os contratos de execução **portátil** e **instalado por MSI**, eliminar dependências acidentais do ambiente do usuário e tornar distribuição/atualização verificáveis antes do `1.0 estável`.

A Phase 8 trata diretamente CP-010, CP-017, CP-018, CP-030 e CP-031. CP-019 e CP-020 recebem infraestrutura importante, mas permanecem abertos até existir uma release realmente assinada e um lock transitivo completo das dependências pesadas.

## Dois modos de distribuição

### Portátil

Entrada normal:

```text
CinePulse.cmd
Install-CinePulse.cmd
```

Contrato:

- marcador `.cinepulse-portable` presente;
- runtime Python privado em `<CinePulse>/.runtime/python`;
- componentes em `<CinePulse>/components`;
- dados em `<CinePulse>/data`;
- atualização in-place/rollback permanece disponível apenas neste modo.

### Instalado por MSI

Entradas dedicadas:

```text
CinePulse-Installed.cmd
Install-CinePulse-Installed.cmd
```

Ambas passam `-NonPortable` ao bootstrap.

Contrato:

```text
Programa        → pasta instalada pelo MSI
Dados           → %LOCALAPPDATA%\CinePulse
Runtime         → %LOCALAPPDATA%\CinePulse\runtime
Componentes     → %LOCALAPPDATA%\CinePulse\components
Logs            → %LOCALAPPDATA%\CinePulse\logs
```

O MSI não cria/recria o marcador portátil e seus atalhos nunca chamam `CinePulse.cmd`.

A aplicação instalada também não usa o self-updater portátil para sobrescrever arquivos gerenciados pelo Windows Installer. A atualização do núcleo instalado deve ocorrer por um MSI mais novo.

## Runtime Python gerenciado

`installer/Start-CinePulse.ps1` não procura mais Python do sistema para criar o ambiente de distribuição.

O bootstrap usa a versão de Python fixada em `bootstrap-manifest.json` e cria o ambiente com:

```text
uv venv --python <versão-fixada> --python-preference only-managed
```

A versão efetiva é conferida antes de o runtime ser aceito.

O lock de runtime usa instalação com:

```text
--require-hashes --only-binary=:all:
```

Assim, remover/atualizar um Python instalado pelo usuário não é parte do contrato do CinePulse distribuído.

## Descoberta única de PowerShell

Novo módulo:

```text
src/cinepulse/runtime_distribution.py
```

`find_powershell()` é usado pelos fluxos internos que precisam abrir o instalador/reparo:

1. PowerShell 7 em localização conhecida;
2. `pwsh` descoberto no PATH;
3. Windows PowerShell como fallback.

A UI deixa de possuir uma decisão paralela hardcoded em `powershell.exe`.

## Single-instance guard

A entrada principal agora adquire `InstanceGuard` antes de criar o Studio.

No Windows:

```text
Local\CinePulse-<hash por usuário>
```

é utilizado como named mutex.

Em ambientes não-Windows, o mesmo contrato é coberto por PID lock atômico com recuperação de lock stale, permitindo teste em CI sem fingir que Win32 existe.

Uma segunda instância não chega ao fluxo de render.

## MSI

`installer/wix/Product.wxs` passa a:

- receber `ProductVersion` do build em vez de manter `1.0.0` fixo;
- usar os launchers `*-Installed.cmd`;
- registrar `assets/cinepulse.ico` em atalhos e Apps e Recursos;
- manter o marcador portátil fora do payload instalado.

`Build-Msi.ps1` converte SemVer/RC para versão compatível com Windows Installer de forma monotônica e recompõe `cinepulse-files.json` depois de transformar o payload portátil em payload instalado.

## Assinaturas

### Manifesto de atualização portátil

A Phase 8 adiciona suporte a canal assinado:

```text
installer/update-channel.json schema 2
require_signature = true
public_key = ...
manifest_signature_url = ...
```

Novo módulo:

```text
src/cinepulse/signatures.py
```

Quando o canal exige assinatura, `update_manager.py`:

1. baixa os bytes crus do manifesto por HTTPS;
2. baixa a assinatura destacada;
3. verifica a assinatura com a chave pública confiável;
4. **somente depois** interpreta o JSON;
5. mantém a verificação SHA-256 do ZIP como segunda camada.

`Build-Portable.ps1` consegue assinar `cinepulse-update.json` quando recebe uma chave de assinatura e um executável Minisign reais.

**Estado:** infraestrutura pronta, mas CP-019 não é marcado como fechado até uma release pública realmente usar uma chave privada CinePulse protegida e distribuir o verificador/chave pública correspondentes.

### Authenticode do MSI

`Build-Msi.ps1` aceita `CertificateThumbprint` + `SignTool` e, quando configurado:

1. assina o MSI com SHA-256;
2. aplica timestamp;
3. executa verificação Authenticode;
4. registra `authenticode_signed=true` no manifesto do setup.

Sem certificado, o build informa explicitamente que o MSI é não assinado.

A Phase 8 não inventa uma assinatura inexistente.

## Lock e SBOM

`requirements.lock` passa a exigir hash para o runtime principal.

Novo gerador:

```text
scripts/generate_sbom.py
```

Produz `sbom.cdx.json` em formato CycloneDX 1.5 com o núcleo e componentes diretos fixados pelo projeto, incluindo hashes quando já existem nos manifests.

Isso melhora substancialmente CP-020, mas o próprio SBOM marca como pendente o lock transitivo completo do ambiente Demucs/PyTorch/SoundFile. Portanto CP-020 permanece aberto até todos os wheels transitivos distribuídos serem fixados com hashes por plataforma/Python.

## Branding do Windows

`assets/cinepulse.ico` passa a ser usado por:

- janela principal no Windows, best effort;
- atalhos do Menu Iniciar;
- atalho da Área de Trabalho;
- registro do MSI/Apps e Recursos.

## Limpeza de dados instalados

`installer/Remove-CinePulse-UserData.ps1` oferece uma operação explícita para remover cache/temp/runtime/logs e, opcionalmente, componentes.

O MSI preserva dados do usuário por padrão; remoção de grandes componentes/dados privados não ocorre silenciosamente durante uninstall/upgrade.

## Critérios de aceite implementados nesta fase

- MSI e portátil possuem launchers e roots distintos;
- MSI não usa self-update portátil;
- runtime distribuído não depende de Python do sistema;
- descoberta de PowerShell é centralizada;
- segunda instância é bloqueada antes da UI;
- versão MSI deriva da release;
- ícone Windows é um arquivo ICO real e entra no WiX;
- build possui hook Authenticode verificável;
- update manager suporta manifesto assinado e falha de assinatura é fatal;
- runtime lock exige hash;
- build portátil gera SBOM;
- diagnóstico informa modo, roots e PowerShell resolvido.

## Pendências deliberadas

- executar build/install/upgrade/repair/uninstall real do MSI em Windows;
- validar launchers e bootstrap PowerShell no Windows real;
- emitir uma release com chave Minisign real e validar update/rollback assinado;
- obter/usar certificado Authenticode real;
- completar lock transitivo hashado de Demucs/PyTorch/SoundFile;
- integrar esses gates ao CI Windows na Phase 9.
