# CinePulse 1.2.5

Hotfix de robustez e polimento do modo de utilização total introduzido na 1.2.4.

## Correção crítica do Real-ESRGAN

A 1.2.4 removeu o probe dinâmico de headroom, mas uma chamada do worker ainda tentava acessar `neural_headroom.vram_free_mb`. Em projetos que realmente entravam no Real-ESRGAN isso podia gerar `NameError` antes do upscale. A 1.2.5 remove a referência órfã e passa explicitamente `None` para o parâmetro de compatibilidade, que não governa mais concorrência.

## CPU e interface

O runtime continua usando todos os threads lógicos disponíveis. A aba Qualidade deixa de mostrar controles manuais de threads e perfis de utilização, porque eles já não tinham efeito real no render. Presets e filas antigos continuam compatíveis; o campo legado `cpu_threads` é canonicalizado para a capacidade lógica atual.

## Fallback somente após falha real

Não voltamos a medir RAM/VRAM/temperatura para reduzir carga preventivamente. A melhoria é reativa:

- RIFE começa agressivo e, se houver OOM real, pode descer até `1:1:1`;
- Real-ESRGAN começa no envelope estático máximo e pode descer para o fallback conservador e depois `1:1:1` se o OOM persistir;
- falhas de integridade não são mascaradas por uma sequência infinita de retries.

## Concorrência e staging

O diretório temporário nativo do RIFE agora inclui PID + `time_ns`, evitando que duas invocações no mesmo processo usem o mesmo staging e apaguem trabalho uma da outra.

## Proteções mantidas

AtomicOutput, validação de PNG/mídia, contagem de frames, cancelamento seguro, cache/staging do Demucs e verificação final continuam ativos.
