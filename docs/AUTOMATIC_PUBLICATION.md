# Atualização do Market Health pelo Colab

O notebook v0.3.2 coleta preços, calcula o histórico, exporta os arquivos ao Drive, executa os testes e publica automaticamente o CSV agregado em `data/market_health/` no GitHub. O painel Streamlit usa esse diretório, sem upload manual.

## Configuração única

1. No GitHub, crie um personal access token fine-grained em https://github.com/settings/personal-access-tokens/new.
2. Selecione o proprietário `ulysses78-sys` e somente o repositório `minervini-market-health`.
3. Em Repository permissions, permita **Contents: Read and write**. Defina prazo de expiração. Não é necessário acesso a Workflows, administração ou outros repositórios.
4. No Colab, abra Secrets (ícone de chave), crie `MARKET_HEALTH_GITHUB_TOKEN` e habilite Notebook access para o v0.3.2. Cole o token somente no campo do secret.
5. Execute todas as células do notebook. A última célula imprime `published` ou `already_present` e o link do snapshot verificado.

## Comportamento e limites

- A publicação exige o calendário XNYS completo, esquema fechado de campos agregados, fontes e alertas reconhecidos, contagens, limites, soma dos componentes e regimes consistentes. NO_DATA continua sendo ausência de dados, sem score inventado.
- O publisher envia exclusivamente esse agregado validado. Colunas inesperadas bloqueiam a publicação antes de autenticar. Não lê carteiras ou operações.
- Cada execução usa um arquivo datado. Uma nova tentativa do mesmo arquivo confirma o conteúdo existente; conteúdo diferente nunca é sobrescrito.
- Falha de autenticação ou rede preserva os arquivos exportados no Drive. Renove o secret quando o token expirar. Não cole credenciais no notebook, chat ou repositório.
- Este fluxo automatiza a publicação ao terminar a execução do Colab. A coleta ainda depende de iniciar o notebook; não há agendamento diário nesta etapa.
- Constituintes atuais introduzem viés de sobrevivência. Coverage_pct representa disponibilidade dos componentes do score, não percentual de ações cobertas.

Referência da API e permissão Contents: https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents

