# Privacidade

CinePulse é local-first:

- mídia, projetos, frames, áudio e resultados de IA permanecem no computador;
- não existe envio automático de telemetria, inventário de mídia ou dados de projeto para servidores do CinePulse;
- o histórico técnico de cada render pode registrar **telemetria local de hardware** — por exemplo CPU, RAM, disco e, quando disponível, utilização, VRAM, potência, temperatura, clocks e P-state da GPU NVIDIA — para diagnóstico, auditoria e decisões conservadoras de buffering durante o processamento;
- essa telemetria fica nos arquivos locais do histórico de render e não contém frames do vídeo nem áudio da mídia;
- diagnósticos locais podem registrar versões, hardware, espaço, estado dos componentes e caminhos locais necessários ao suporte; bundles de suporte usam a rotina de redação de caminhos antes da exportação;
- relatórios e bundles de suporte só são compartilhados quando o usuário decide fazê-lo;
- logo após abrir, o aplicativo faz uma verificação HTTPS curta da release Stable mais recente no GitHub para descobrir atualizações;
- essa verificação envia apenas metadados normais da conexão HTTP, incluindo o endereço IP visto pelo GitHub e o `User-Agent` `CinePulse/<versão>`; nenhum caminho local, mídia, projeto, hardware detalhado ou identificador criado pelo CinePulse é anexado ao pedido;
- falha ou bloqueio de rede nessa verificação não impede o uso local do programa;
- downloads de atualização ou componentes só ocorrem quando necessários e usam as origens documentadas.

A Restauração Preview, os benchmarks de hardware e os mecanismos H0–H8 também funcionam localmente. A medição de throughput do scratch grava apenas um arquivo temporário pequeno no volume selecionado, faz `fsync` e remove o arquivo imediatamente; ela não envia o conteúdo para fora da máquina.

A checagem automática de versão existe para o botão de atualização no aplicativo e não é usada como analytics. Recursos remotos futuros devem declarar claramente quais dados saem da máquina e permanecer separados do processamento local de mídia.
