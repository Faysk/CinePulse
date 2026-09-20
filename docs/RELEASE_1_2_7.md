# CinePulse 1.2.7

Esta release fecha a integridade temporal do pipeline CFR. A 1.2.6 já distribuía corretamente a contagem de frames entre chunks; a 1.2.7 remove os últimos limites por timestamp decimal que ainda podiam cortar um frame na concatenação ou na entrega final.

## Master RIFE sem corte por duração

O concat FFV1 não usa mais `-t duration`. Os segmentos já têm timeline explícita `frames/fps`; depois da montagem, o CinePulse lê estruturalmente o Matroska e exige exatamente `total_target_count` pacotes antes de aceitar o master.

## Recovery mais estrito

Um master de recovery existente só é reutilizado se, além da geometria/FPS/duração aceitáveis, tiver exatamente a contagem esperada de pacotes. O concat de recovery também não usa mais `-t` e valida a contagem após a montagem.

## Entrega final orientada por frames

O encode final usa `-frames:v round(project_duration*target_fps)` em vez de cortar todo o mux por um timestamp decimal. Isso preserva a cadência CFR esperada e deixa o áudio terminar naturalmente.

## Verificação final estrita

O Studio passa `frame_tolerance=0` para a verificação final e recusa promoção se o FFprobe não conseguir informar a contagem exata. Assim, uma perda ou sobra de apenas um frame deixa de passar como aceitável.

## VFX

O render VFX também passa a ser limitado por quantidade de quadros. O overlay declara explicitamente `eof_action=repeat`, `shortest=0` e `repeatlast=1`, então um layer reativo que termina alguns milissegundos antes não encurta a base.

## Recovery preserva o áudio do job

O recovery deixa de assumir estéreo/48 kHz e passa a restaurar `expect_audio`, canais e sample rate a partir do contrato persistido do render. Jobs silenciosos continuam silenciosos. Quando o job original usava normalização/masterização, o recovery repete a análise loudness de duas passagens quando possível e usa o mesmo fallback dinâmico do Studio se a medição falhar. Partials antigos sem prova dessa masterização são preservados como rejeitados e um encode novo é criado.

## Recovery preserva o backend do job

Jobs criados com `use_cpu=True` continuam em CPU durante a recuperação: RIFE usa o índice CPU (`-g -1`) e o envelope CPU-safe, e a entrega final usa o encoder CPU previsto pelo perfil. Jobs GPU continuam no adaptador selecionado. O recovery não troca mais silenciosamente CPU por GPU.

## Proteções mantidas

Continuam ativos AtomicOutput, verificação final, validação de PNG/mídia, fallback pós-falha real, cancelamento seguro, full-utilization e pinning multi-GPU.
