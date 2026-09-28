# CinePulse 1.2.28

A 1.2.28 consolida as correções do pipeline NVIDIA desenvolvidas durante a aceitação física e fecha a lacuna que permanecia desde as primeiras releases Stable: o workflow canônico de GPU agora conclui com sucesso no `main` em hardware real.

## Aceite físico NVIDIA concluído

A validação final foi executada pelo `GPU Acceptance` #907 (run `36470808107`) sobre o commit `8a50aa1b8b9efaa1ca005ba4294a8f4a5009f545`, usando:

- NVIDIA GeForce RTX 4070 Laptop GPU;
- 8188 MB de VRAM;
- driver NVIDIA 617.14;
- GPU index 0.

O job físico concluiu todos os gates obrigatórios: inventário NVIDIA, runtime hash-locked, isolamento, NVDEC, resident NVDEC/CUDA/NVENC, Real-ESRGAN, RIFE, Composer CUDA, GPU integration gate, recovery RIFE 8K UHD e upload das evidências.

## Composer CUDA e NVDEC-resident

A rodada física revelou e corrigiu diferenças reais entre o caminho CPU-reference e o caminho CUDA:

- metadata BT.709 é preservada também no remux da referência;
- o envelope de paridade YUV420 é limitado e explícito, em vez de exigir equivalência RGB irreal após quantização/chroma subsampling;
- o caminho NVDEC-resident normaliza frames CUDA NV12 para yuv420p dentro da GPU com `scale_cuda` antes de `overlay_cuda`;
- o workflow distingue corretamente “candidato não promovido” de erro de execução.

Evidência final no `main`:

- Composer cpu-upload: `accepted=true`, speedup 8.29481×, PSNR 55.854865 dB, SSIM 0.999045, `max_abs_error=38`;
- Composer nvdec-resident: `accepted=true`, speedup 8.78450×, PSNR 55.854865 dB, SSIM 0.999045, `max_abs_error=38`.

## NVDEC e entrega resident

A release continua fail-closed por rota e por contrato. Um workflow físico verde não promove automaticamente qualquer caminho:

- NVDEC puro manteve paridade perfeita, mas speedup 0.8658×; portanto não foi promovido;
- resident 1080p60 foi aceito fisicamente com speedup 1.03037×, PSNR 999 e SSIM 1.0;
- resident 4K60 não cumpriu os thresholds de qualidade/performance e permanece não promovido.

## RIFE, Real-ESRGAN e recovery 8K

Real-ESRGAN e RIFE registraram evidências físicas aceitas. O recovery RIFE 8K UHD concluiu com:

`RECOVERY_GPU_8K_ACCEPTANCE_OK uhd=True jobs=1:1:1 native=4 target=5`

A política conserva `1:1:1` quando concorrência maior não está comprovada, evitando transformar utilização máxima em risco de corrupção ou instabilidade.

## Graduação de #4

Com o aceite canônico concluído no `main`, a regra de graduação da issue #4 foi satisfeita. Os contratos 8K/120 neural/GPU e recovery cobertos por essa matriz deixam de ser “fisicamente não provados” e passam a ter aceite físico documentado no hardware alvo.

Isso não amplia o escopo para 10K/12K nem para 144/240/480 fps, que continuam experimentais até possuírem evidência própria.

Closes #4.
