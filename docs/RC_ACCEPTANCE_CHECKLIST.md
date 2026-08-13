# CinePulse — Checklist de aceite do Release Candidate

Use esta lista **depois** dos gates automatizados. Ela registra o que só a máquina e a mídia reais conseguem provar.

## A. Gate automatizado Windows

- [ ] `Invoke-RcAcceptance.ps1` conclui com `CINEPULSE_RC_AUTOMATED_ACCEPTANCE_OK`.
- [ ] `release-light-windows.json` está `passed=true`.
- [ ] PowerShell release contract passa sem erro de parser.
- [ ] build portátil conclui.
- [ ] updater/rollback do portátil conclui.
- [ ] build MSI conclui.
- [ ] validação do payload MSI conclui.
- [ ] install → repair → uninstall MSI passa em VM/runner descartável.
- [ ] segunda instância real é bloqueada por mutex Win32.
- [ ] instalação MSI não recria `.cinepulse-portable`.
- [ ] portátil inicia numa máquina sem depender de Python/FFmpeg previamente instalados.

## B. Gate NVIDIA

- [ ] `nvidia-smi` identifica a GPU esperada.
- [ ] Real-ESRGAN real passa.
- [ ] RIFE real passa.
- [ ] Demucs/CUDA real passa.
- [ ] nenhum fallback CPU é confundido com sucesso GPU.
- [ ] VRAM máxima observada é registrada.
- [ ] emendas entre chunks do RIFE são inspecionadas visualmente.

## C. Render real principal

- [ ] projeto musical longo com mídia do usuário conclui.
- [ ] áudio final está correto do início ao EOF.
- [ ] reação musical do preview corresponde ao mesmo trecho no final.
- [ ] transição do loop não apresenta salto perceptível.
- [ ] VFX não apresentam aliasing/pixelização perceptível no destino.
- [ ] fila com pelo menos 3 projetos conclui e restaura estado após reinício.
- [ ] cancelamento durante IA, VFX, RIFE e encode preserva a saída anterior.

## D. 8K / 120 fps

- [ ] fonte que já possui 120 fps não passa por interpolação desnecessária.
- [ ] Real-ESRGAN é ignorado quando o destino não exige upscale.
- [ ] render 8K/120 conclui na máquina-alvo.
- [ ] deep verify confirma geometria, FPS, frames, áudio e EOF.
- [ ] scratch/cache não excedem o volume previsto de forma perigosa.
- [ ] inspeção a 100% não revela degradação inaceitável dos VFX.

## E. HDR / 10-bit

- [ ] HDR limpo permanece HDR/10-bit.
- [ ] HDR + etapa SDR-only sai explicitamente SDR, sem metadata falsa.
- [ ] highlight roll-off do tone mapping é aceitável.
- [ ] gradientes 10-bit não apresentam banding anormal.
- [ ] full/limited range está correto.
- [ ] NVENC Main10 real é validado no Windows.

## F. Distribuição e segurança

- [ ] manifesto de atualização aponta para endpoint de release real.
- [ ] manifesto assinado é aceito.
- [ ] assinatura inválida é recusada antes do parse/conteúdo.
- [ ] Authenticode do MSI é validado, se houver certificado disponível.
- [ ] SBOM acompanha o artefato de release.
- [ ] dependências neurais possuem estratégia de lock/hashes aprovada antes do `1.0.0`.

## G. Dívidas deliberadas

- [ ] CP-011 recebeu decisão: FFV1/mezzanine ou evidência perceptiva que justifique intermediário atual.
- [ ] CP-027 continua registrado se seleção temporal avançada não entrar no primeiro RC.
- [ ] CP-032 possui plano de modularização incremental, sem rewrite.
- [ ] CP-033 possui plano para extrair utilitários e isolar/aposentar o app clássico.

## Resultado

- [ ] **RC aceito para distribuição controlada**.
- [ ] **RC rejeitado — corrigir e repetir os gates**.
- [ ] **1.0 estável aprovado** — marcar somente quando todos os gates obrigatórios de stable estiverem verdes.
