# Inicialização portátil

Execute `CinePulse.cmd`. Na primeira abertura, o iniciador cria um ambiente Python dentro de `.runtime`, instala somente as dependências do aplicativo e mantém configurações em `data`. Se Python não existir, baixa o inicializador `uv` em versão fixada, confere SHA-256 e instala Python portátil na própria pasta.

- `CinePulse.cmd`: inicialização normal e portátil.
- `installer\Start-CinePulse.ps1 -Repair`: recria apenas o ambiente interno.
- `installer\Start-CinePulse.ps1 -Diagnostics`: gera um diagnóstico local sem listar projetos ou nomes de mídia.
- `installer\Start-CinePulse.ps1 -NonPortable`: guarda dados em `%LOCALAPPDATA%\CinePulse`.
- `installer\Start-CinePulse.ps1 -ForcePortableRuntime`: força o Python gerenciado pelo CinePulse, útil para validar o pacote final.
- `installer\Start-CinePulse.ps1 -ApplyUpdateOnly`: aplica uma atualização já verificada sem abrir a interface, útil para manutenção e testes.

Se FFmpeg/FFprobe não estiverem no sistema, o iniciador baixa a build completa 9.0 em versão fixada, confere SHA-256 e instala em `components\ffmpeg`. Essa build é GPL-3.0 e permanece fora do repositório. Modelos e demais ferramentas também ficam em `components`.

## Atualizações

Depois que o repositório público for definido, monte releases com:

```powershell
.\scripts\Build-Portable.ps1 -Repository 'dono/CinePulse'
```

O pacote recebe o endereço do canal. O botão **Verificar atualizações** baixa apenas por HTTPS, confere o SHA-256 do ZIP e prepara a nova versão. A aplicação ocorre antes da próxima abertura; se a cópia falhar, os arquivos anteriores são restaurados. `data`, `components` e `.runtime` não são substituídos.
