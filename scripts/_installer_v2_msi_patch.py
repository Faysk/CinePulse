from pathlib import Path

path = Path('scripts/Build-Msi.ps1')
text = path.read_text(encoding='utf-8-sig')


def once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    text = text.replace(old, new, 1)


once(
    "$WixExe = Join-Path $WixRoot 'wix.exe'\n$BuildTools = Get-Content",
    "$WixExe = Join-Path $WixRoot 'wix.exe'\n$WixExtensionCache = Join-Path $RuntimeRoot 'wix-extension-cache'\n$BuildTools = Get-Content",
    'wix extension cache root',
)

once(
    "$DotnetExe = Join-Path $DotnetRoot 'dotnet.exe'\n$Archive = Join-Path",
    "$DotnetExe = Join-Path $DotnetRoot 'dotnet.exe'\n$WixUiExtension = \"WixToolset.UI.wixext/$($BuildTools.wix.version)\"\n$Archive = Join-Path",
    'wix ui extension ref',
)

anchor = """    & $DotnetExe tool install wix --tool-path $WixRoot --version $BuildTools.wix.version
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível instalar o WiX Toolset.' }
}

if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }
"""
replacement = """    & $DotnetExe tool install wix --tool-path $WixRoot --version $BuildTools.wix.version
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível instalar o WiX Toolset.' }
}

# The install-directory wizard lives in WixToolset.UI.wixext. Keep the
# extension cache inside CinePulse build runtime instead of the user profile.
New-Item -ItemType Directory -Path $WixExtensionCache -Force | Out-Null
$env:WIX_EXTENSION = $WixExtensionCache
& $WixExe extension add -g $WixUiExtension
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar a extensão de UI do WiX.' }

if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }
"""
once(anchor, replacement, 'wix ui extension acquisition')

once(
    """& $WixExe build (Join-Path $ProjectRoot 'installer\\wix\\Product.wxs') `
    -arch x64 -bindpath \"Payload=$Payload\" -d ProductVersion=$MsiVersion -out $Output
""",
    """& $WixExe build (Join-Path $ProjectRoot 'installer\\wix\\Product.wxs') `
    -arch x64 -ext $WixUiExtension -bindpath \"Payload=$Payload\" -d ProductVersion=$MsiVersion -out $Output
""",
    'wix build extension',
)

path.write_text(text, encoding='utf-8-sig')
print('CINEPULSE_INSTALLER_V2_MSI_PATCH_OK')
