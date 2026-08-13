# CinePulse — checklist de aceite UX no Windows

Use este checklist antes de declarar o MegaPack Visual & UX pronto para a 1.0 estável.

## Matriz visual mínima

Testar em Windows com a GPU de destino:

| Resolução lógica | Escala | Resultado esperado |
|---|---:|---|
| 1024×700 | 100% | todas as abas utilizáveis via scroll, splits empilhados e rodapé sem cortar ações/feedback |
| 1366×768 | 100% | sem corte horizontal de controles principais |
| 1920×1080 | 100% | layout wide, duas colunas onde aplicável |
| 1920×1080 | 125% | textos/inputs sem sobreposição |
| 1920×1080 | 150% | navegação e ações continuam acessíveis |
| monitor compatível | 200% | janela permanece recuperável e utilizável |

## Primeiro uso

- abrir instalação limpa;
- confirmar Home com `Primeiros passos`;
- abrir Projeto pelo card;
- voltar à Home e dispensar com `Entendi`;
- reiniciar: o card não deve reaparecer;
- `F1` deve continuar abrindo o guia.

## Persistência

- mudar para dark;
- ir para uma aba diferente;
- mover/redimensionar janela;
- fechar normalmente;
- reabrir e conferir tema, aba e geometria;
- mover o app para outro monitor, fechar e remover o monitor;
- reabrir e confirmar que a janela volta para uma área visível.

## Presets

- aplicar um preset A;
- selecionar preset B sem aplicar;
- confirmar `ainda não aplicado` e que os controles continuam no preset A;
- aplicar B;
- alterar intensidade manualmente;
- confirmar `ajustes manuais`.

## Teclado

- `F1`;
- `Ctrl+1…6`;
- `Ctrl+Tab` / `Ctrl+Shift+Tab`;
- `Ctrl+O`;
- `Ctrl+Shift+O`;
- `Ctrl+Shift+S`;
- `Ctrl+P`;
- `Ctrl+L`;
- `Ctrl+Shift+A`;
- `Esc` no guia e Central de atividade;
- Tab/Shift+Tab nos formulários principais;
- Enter/Space em botões focados.

Nenhum atalho deve apagar dados ou iniciar render final acidentalmente.

Fechar e reabrir o Studio duas vezes no mesmo processo de teste não deve produzir erros `invalid command name` de callbacks Tcl pendentes.

## Mouse/scroll

Em todas as seis abas:

- wheel sobre label/card deve rolar a aba;
- wheel sobre Treeview deve rolar a Treeview, não a página;
- scrollbar vertical deve acompanhar corretamente;
- nenhum painel deve ficar inacessível em 1024×700.

## Rodapé responsivo

Em 1024×700:

- ocioso: resumo, `Gerar preview`, `Criar vídeo final`, `Fila +` e feedback devem permanecer inteiros;
- `Cancelar` não deve reservar espaço quando não há job;
- durante render/preview: resumo longo e utilidades secundárias cedem espaço para ações, barra, estágio e feedback;
- ao terminar/cancelar, o rodapé deve voltar ao estado ocioso sem deixar widgets órfãos;
- em layout wide, utilidades, relógio/ETA e progresso voltam ao rodapé completo.

## Light/dark

Conferir pelo menos:

- textos muted;
- campos readonly;
- estados selecionados;
- status success/warning/error;
- onboarding;
- Central de atividade;
- preview preto;
- Treeviews;
- foco de teclado.

Cor nunca pode ser o único indicador de estado.

## Fluxo real de produto

1. selecionar vídeo;
2. selecionar música;
3. escolher saída;
4. conferir enquadramento;
5. alterar qualidade;
6. configurar VFX;
7. gerar preview real;
8. adicionar duas variações à fila;
9. executar A e B sequencialmente;
10. abrir saída e relatório;
11. reiniciar o CinePulse e verificar a fila persistida.

## Hardware/IA

- Real-ESRGAN ausente + selecionado: bloqueio claro;
- RIFE ausente + selecionado: warning + fallback FFmpeg;
- Demucs ausente: VFX ainda funciona sem stems;
- VMAF ausente: métrica indisponível, render não bloqueado;
- experimental instalado continua `fora do render`.

## Critério de aceite

A 1.0 UX só recebe aceite quando:

- não houver controle principal inacessível nas combinações acima;
- não houver estado falso de preset/IA/fila;
- preview imediato e preview renderizado estiverem conceitualmente claros;
- operações destrutivas mantiverem confirmação;
- um render real longo e uma fila de pelo menos dois itens concluírem no Windows de destino.
