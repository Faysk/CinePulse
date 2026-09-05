# Privacidade

CinePulse é local-first:

- mídia e projetos permanecem no computador;
- não existe envio automático de telemetria ou diagnóstico para servidores do CinePulse;
- o histórico técnico de cada render pode registrar **telemetria local de hardware** — por exemplo CPU, RAM, disco e, quando disponível, utilização/VRAM/potência/temperatura da GPU NVIDIA — para diagnóstico, auditoria e decisões conservadoras de buffering durante aquele processamento;
- a telemetria de hardware fica nos arquivos locais do histórico de render e não contém os frames do vídeo nem o áudio da mídia;
- diagnósticos podem registrar versões, hardware, espaço, estado dos componentes e caminhos locais necessários ao suporte; bundles de suporte usam a rotina de redação de caminhos antes da exportação;
- relatórios e bundles só são compartilhados quando o usuário decide fazê-lo;
- downloads opcionais acessam somente as origens informadas ao usuário.

A Restauração Preview, os benchmarks de hardware e os mecanismos H1–H5 também funcionam localmente. A medição de throughput do scratch grava apenas um arquivo temporário pequeno no volume selecionado, faz `fsync` e remove o arquivo imediatamente; ela não envia o conteúdo para fora da máquina.

Se um recurso remoto for adicionado no futuro, ele deverá ser opt-in, explicar o que será enviado e funcionar separadamente do núcleo local.
