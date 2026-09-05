# Privacidade

CinePulse é local-first:

- mídia, projetos, frames, áudio e resultados de IA permanecem no computador;
- o CinePulse não envia telemetria de uso, inventário de mídia ou dados de projeto para um servidor do projeto;
- diagnósticos locais podem registrar versões, hardware, espaço e estado dos componentes sem enumerar vídeos ou músicas;
- logo após abrir, o aplicativo faz uma verificação HTTPS curta da release Stable mais recente no GitHub para descobrir atualizações;
- essa verificação envia apenas metadados normais da conexão HTTP, incluindo o endereço IP visto pelo GitHub e o `User-Agent` `CinePulse/<versão>`; nenhum caminho local, mídia, projeto, hardware detalhado ou identificador criado pelo CinePulse é anexado ao pedido;
- falha ou bloqueio de rede nessa verificação não impede o uso local do programa;
- downloads de atualização ou componentes só ocorrem quando necessários e usam as origens documentadas;
- relatórios e bundles de suporte só são compartilhados quando o usuário decide fazê-lo.

A checagem automática de versão existe para o botão de atualização solicitado no aplicativo e não é usada como analytics. Recursos remotos futuros devem declarar claramente quais dados saem da máquina e permanecer separados do processamento local de mídia.
