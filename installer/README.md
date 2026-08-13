# Runtime e distribuição no Windows

## Pacote portátil

No ZIP portátil, execute `Install-CinePulse.cmd` uma vez e depois abra por `CinePulse.cmd`.

Contrato do portátil:

```text
Código/runtime root  → pasta extraída
Python gerenciado    → .runtime\python
Componentes          → components
Dados/logs/cache     → data
```

O bootstrap usa a versão de Python fixada em `bootstrap-manifest.json` por meio do `uv` em modo **only-managed**. O Python instalado pelo usuário não é usado como base do runtime distribuído.

A instalação prepara FFmpeg, Real-ESRGAN, RIFE e, quando solicitado, PyTorch/Demucs. Downloads gerenciados possuem versão/hash no manifesto correspondente e são promovidos depois da validação.

Comandos principais:

- `CinePulse.cmd`: abertura portátil normal;
- `Install-CinePulse.cmd`: instalação/reparo completo visível;
- `installer\Start-CinePulse.ps1 -Repair`: recria o ambiente interno;
- `installer\Start-CinePulse.ps1 -Diagnostics`: gera diagnóstico local;
- `installer\Start-CinePulse.ps1 -ApplyUpdateOnly`: aplica update portátil já verificado;
- `installer\Start-CinePulse.ps1 -InstallOnly`: instala/repara e encerra;
- `installer\Start-CinePulse.ps1 -CoreOnly`: prepara apenas núcleo/FFmpeg.

## Instalação MSI

O MSI usa launchers diferentes:

```text
CinePulse-Installed.cmd
Install-CinePulse-Installed.cmd
```

Eles forçam `-NonPortable`. Dados grandes não ficam misturados com os arquivos controlados pelo Windows Installer:

```text
Dados           → %LOCALAPPDATA%\CinePulse
Runtime         → %LOCALAPPDATA%\CinePulse\runtime
Componentes     → %LOCALAPPDATA%\CinePulse\components
Logs            → %LOCALAPPDATA%\CinePulse\logs
```

O WiX cria atalhos no Menu Iniciar/Área de Trabalho apontando somente para o launcher instalado. A versão MSI é derivada da versão da release e o payload não contém o marcador `.cinepulse-portable`.

Instalações MSI **não** usam o self-updater portátil para sobrescrever o programa. O núcleo é atualizado instalando um MSI CinePulse mais novo; dados/componentes do usuário permanecem separados.

`installer\Remove-CinePulse-UserData.ps1` permite limpeza explícita de runtime/cache/temp/logs e, com opção dedicada, componentes.

## PowerShell

A aplicação e o bootstrap usam uma política única: PowerShell 7 primeiro, Windows PowerShell como fallback. A UI não força mais `powershell.exe` independentemente do ambiente.

## Atualizações portáteis e assinatura

Build básico:

```powershell
.\scripts\Build-Portable.ps1 -Repository 'dono/CinePulse'
```

Esse canal mantém HTTPS + SHA-256. Para ativar o modo assinado, forneça uma chave pública, uma chave privada e um executável Minisign reais ao build. O pacote então recebe canal schema 2, verificador e URL de assinatura.

Quando `require_signature=true`, o CinePulse verifica os **bytes crus** do manifesto antes de interpretar o JSON e só depois aplica as verificações de versão/SHA-256 do artefato. Falha de assinatura aborta a atualização.

Nenhuma chave privada deve entrar no repositório.

## Authenticode do MSI

`Build-Msi.ps1` aceita `-SignTool` e `-CertificateThumbprint`. Quando fornecidos, assina, aplica timestamp e verifica o MSI. Sem certificado, o script emite aviso e registra `authenticode_signed=false`; não existe assinatura fictícia.

## SBOM e dependências

O build portátil gera `sbom.cdx.json` (CycloneDX 1.5) antes de calcular `cinepulse-files.json`. O lock principal exige hashes. O grafo transitivo completo de Demucs/PyTorch/SoundFile ainda precisa ser congelado por plataforma antes do 1.0 estável.

## Validação Windows pendente

O aceite de release deve executar em Windows real:

- build do ZIP/ MSI;
- install → upgrade → repair → uninstall;
- runtime em máquina sem Python/FFmpeg do sistema;
- atalhos/ícone;
- update/rollback;
- assinatura do manifesto com chave de release;
- Authenticode quando houver certificado.
