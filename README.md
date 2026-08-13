<p align="center"><img src="assets/cinepulse-mark.svg" width="128" alt="CinePulse"></p>

# CinePulse

**Local AI video enhancement and music-reactive visual studio.**

CinePulse transforma clipes curtos e músicas em vídeos contínuos, melhora vídeos existentes e cria VFX sincronizados com o áudio. O processamento acontece localmente e o usuário escolhe entre velocidade, qualidade e uso de recursos.

> Estado: `1.0.0-rc.5`. Real-ESRGAN, RIFE, Demucs e VMAF integram o pipeline principal. Em máquinas híbridas, o CinePulse prioriza a GPU NVIDIA dedicada desde a abertura. A tela **IA local** também pode baixar componentes experimentais mediante aceite explícito das licenças e riscos; esses arquivos não são anunciados como funções prontas do render.

## O que já funciona

- loop de vídeo durante toda a música, removendo o áudio original do clipe;
- vídeo original ou formatos 16:9, 9:16, IMAX digital e Cinema Wide;
- perfil estável validado até 8K/120 fps; 10K/12K e 144/240/480 fps permanecem visíveis como experimentais e são bloqueados até existir validação específica;
- preview de 1 a 30 segundos e comparação A/B;
- upscale Lanczos e Real-ESRGAN;
- interpolação FFmpeg, GPU NVIDIA quando disponível e modo CPU;
- interpolação neural RIFE com fallback automático;
- VFX dirigidos opcionalmente por stems do Demucs;
- aurora, espectro, barras, onda, círculo, partículas, pulso e energia musical;
- combinação de efeitos, cor, ocupação, intensidade e foco por faixa musical;
- transições de loop, presets, fila, estimativa de espaço por etapa, progresso, quick/deep verify e relatório final;
- scratch disk configurável, cache com quota/LRU e processamento Real-ESRGAN/RIFE em lotes para limitar temporários;
- histórico técnico persistente por render (`job.json`, log, RenderPlan, contratos e verificação), com fila/presets versionados e migráveis;
- dados, cache, componentes e previews isolados do código-fonte.
- render atômico, recuperação após interrupção e normalização LUFS em duas passagens.
- gerenciador de IA local com capacidades integradas separadas de arquivos experimentais, seleção segura, licenças e instalação verificada.

## Início rápido no Windows

1. Para a experiência mais simples, instale o MSI. Ele cria atalhos no Menu Iniciar e na Área de Trabalho e abre uma janela visível para preparar todos os componentes.
2. No pacote portátil, extraia o ZIP e execute `Install-CinePulse.cmd` uma vez. A janela mostra as etapas, grava `data/logs/installer.log` e cria o atalho da Área de Trabalho.
3. No portátil, abra por `CinePulse.cmd`; no MSI, use os atalhos instalados, que acionam o launcher não-portátil dedicado. A interface só abre quando os componentes obrigatórios estiverem prontos.

Para reutilizar os componentes da instalação de desenvolvimento existente, sem copiá-los para o Git:

```powershell
.\scripts\Migrate-LocalComponents.ps1 -SourceTools 'G:\edit\tools'
```

Não execute essa migração durante um render importante; ela movimenta vários gigabytes pelo disco.

## Fluxo recomendado da interface

1. Use **Projeto** para escolher vídeo/música, conferir metadados e enquadramento.
2. Experimente VFX em **Início** ou **Visual e transições**; esse preview é leve e serve para descoberta.
3. Revise **Qualidade e saída** para escala, FPS, VRAM e compatibilidade.
4. Gere um **preview renderizado** curto antes do vídeo final.
5. Use a **Fila** para processar variações sequencialmente.

`F1` abre os primeiros passos a qualquer momento. `Ctrl+1` a `Ctrl+6` navegam pelas abas; os demais atalhos aparecem no próprio guia. Tema, última aba e geometria da janela são lembrados localmente.

## Privacidade

O CinePulse não envia vídeos, músicas, nomes de arquivos ou diagnóstico para servidores. Não há telemetria. Downloads opcionais de componentes acessam apenas as fontes mostradas ao usuário. Veja [PRIVACY.md](docs/PRIVACY.md).

## Componentes opcionais

Modelos e binários não ficam neste repositório. O catálogo informa finalidade e licença, e o gerenciador somente aceita download automático quando a versão e o SHA-256 estiverem fixados. Veja [AI_COMPONENTS.md](docs/AI_COMPONENTS.md).

## Limites reais

O perfil estável atual é conservador e bloqueia combinações acima de 8K/120 fps. 10K/12K e 144/240/480 fps permanecem experimentais até existir matriz comprovada de encoder/hardware. O tempo, o tamanho e a compatibilidade dependem de resolução de origem, duração, GPU, VRAM, codec e plataforma de destino. Interpolação não cria detalhe verdadeiro; upscale não recupera informação que não existe na fonte.

## Desenvolvimento

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Consulte [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) e o [roadmap](docs/ROADMAP.md).
Os resultados reproduzíveis da versão atual estão em [VALIDATION.md](docs/VALIDATION.md).

Para montar o ZIP portátil reproduzível, depois de abrir o CinePulse ao menos uma vez:

```powershell
.\scripts\Build-Portable.ps1
```

O pacote-base não embute modelos. Na primeira abertura, baixa um Python gerenciado pelo CinePulse, FFmpeg, Real-ESRGAN, RIFE, PyTorch/Demucs e os pesos usados. O runtime distribuído não usa o Python do sistema como base. Versões/hashes disponíveis no bootstrap são verificados antes de liberar a interface.

Para gerar também o instalador Windows:

```powershell
.\scripts\Build-Msi.ps1
```

Ao publicar no GitHub, use `-Repository 'dono/CinePulse'`; isso ativa o canal de atualização portátil. Para exigir assinatura do manifesto, o build também precisa receber chave pública, chave privada e um verificador Minisign reais. Instalações MSI atualizam o núcleo por um MSI mais novo, não pelo self-updater portátil.

## Licença

O código próprio do CinePulse usa a licença MIT. FFmpeg, modelos e ferramentas externas mantêm suas respectivas licenças e não são relicenciados pelo projeto. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de distribuir um pacote.
