# Segurança

## Relatar uma vulnerabilidade

Não publique detalhes exploráveis em uma issue. Use o canal privado de segurança do repositório quando ele estiver configurado.

Inclua versão do CinePulse, impacto e passos mínimos. Não envie mídias pessoais, tokens ou logs sem revisar o conteúdo.

## Política de componentes

- downloads automáticos exigem HTTPS e SHA-256 fixado;
- arquivos são baixados para staging, validados e instalados de forma atômica;
- ZIPs com caminhos fora da pasta de destino são rejeitados;
- atualizações não devem ocorrer durante renderização;
- credenciais nunca devem ser necessárias para render local;
- modelos e executáveis não entram no repositório de código.

Ative secret scanning, push protection e revisão obrigatória no GitHub antes da primeira contribuição externa.

