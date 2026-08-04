# Inicialização portátil

Execute `CinePulse.cmd`. Na primeira abertura, o instalador prepara tudo antes de liberar a interface: Python privado, FFmpeg completo, Real-ESRGAN, RIFE, PyTorch CUDA, Demucs e os quatro pesos `htdemucs_ft`. Todos os downloads possuem versão fixa e hash; uma falha interrompe a abertura em vez de deixar um programa parcialmente funcional.

O primeiro preparo baixa aproximadamente 3,5 GB e pode ocupar mais espaço durante a instalação. As próximas aberturas apenas verificam os marcadores e arquivos obrigatórios.

- `CinePulse.cmd`: inicialização normal e portátil.
- `installer\Start-CinePulse.ps1 -Repair`: recria apenas o ambiente interno.
- `installer\Start-CinePulse.ps1 -Diagnostics`: gera um diagnóstico local sem listar projetos ou nomes de mídia.
- `installer\Start-CinePulse.ps1 -NonPortable`: guarda dados em `%LOCALAPPDATA%\CinePulse`.
- `installer\Start-CinePulse.ps1 -ForcePortableRuntime`: força o Python gerenciado pelo CinePulse, útil para validar o pacote final.
- `installer\Start-CinePulse.ps1 -ApplyUpdateOnly`: aplica uma atualização já verificada sem abrir a interface, útil para manutenção e testes.
- `installer\Start-CinePulse.ps1 -InstallOnly`: instala ou repara componentes e encerra sem abrir a interface.
- `installer\Start-CinePulse.ps1 -CoreOnly`: instala somente o núcleo e FFmpeg; recursos de IA ficam desativados.

O CinePulse usa sua própria build FFmpeg 9.0 mesmo se houver outra no sistema, garantindo codecs, HDR e libvmaf consistentes. Essa build é GPL-3.0 e permanece fora do repositório. Modelos e ferramentas também ficam em `components`.

## MSI para Windows

`scripts\Build-Msi.ps1` gera um MSI x64 validado e um manifesto SHA-256. O MSI instala o núcleo no perfil do usuário, cria o atalho no Menu Iniciar e abre automaticamente a instalação completa dos componentes. Essa janela pode continuar por alguns minutos depois que o assistente do MSI fechar. O SDK .NET e o WiX usados para compilar ficam apenas em `.runtime` do desenvolvedor e não entram no pacote final.

## Atualizações

Depois que o repositório público for definido, monte releases com:

```powershell
.\scripts\Build-Portable.ps1 -Repository 'dono/CinePulse'
```

O pacote recebe o endereço do canal. O botão **Verificar atualizações** baixa apenas por HTTPS, confere o SHA-256 do ZIP e prepara a nova versão. A aplicação ocorre antes da próxima abertura; se a cópia falhar, os arquivos anteriores são restaurados. `data`, `components` e `.runtime` não são substituídos.
