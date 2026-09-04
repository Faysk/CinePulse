from pathlib import Path

path = Path('src/cinepulse/studio.py')
text = path.read_text(encoding='utf-8-sig')
old = (
    '"Esta cópia não sobrescreve arquivos instalados. Atualize instalando um MSI CinePulse mais recente; '
    'seus dados e componentes permanecem em %LOCALAPPDATA%\\\\CinePulse.",'
)
new = (
    '"Esta cópia não sobrescreve arquivos instalados. Atualize instalando um MSI CinePulse mais recente; '
    'dados, componentes, cache e temporários permanecem dentro da pasta CinePulse escolhida na instalação.",'
)
count = text.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one installed-update text match, got {count}')
path.write_text(text.replace(old, new, 1), encoding='utf-8-sig')
print('CINEPULSE_STUDIO_INSTALLER_V2_TEXT_PATCH_OK')
