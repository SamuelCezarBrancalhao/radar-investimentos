# 📡 Radar de Investimentos

App pessoal para iPhone que mostra **dados reais da B3** (ações, FIIs, ETFs e BDRs), lê **notícias de sites confiáveis com IA** e manda **alertas no Telegram**.

- **Tabelas**: preço, variação no dia, 7 dias, 30 dias e 12 meses, P/L, P/VP, dividendos, ROE, dívida, vacância de FIIs etc.
- **Nota de 0 a 10** por fórmula simples e transparente (o app mostra como é calculada).
- **Possibilidades da IA**: a IA lê as notícias do dia e diz o que pode subir ou cair, com chance (baixa, média ou alta), prazo, motivo, contraponto e o **link das notícias** de onde tirou isso.
- **Alertas no Telegram**: quando algo da sua lista sobe ou cai forte, quando chega no preço que você definiu, quando a IA vê uma possibilidade forte, e um resumo todo fim de tarde.

> ⚠️ Possibilidades não são certezas. Ninguém prevê o mercado. O app junta informação para você estudar e decidir; ele **não é recomendação de investimento**. A compra você faz no seu banco ou corretora (ex.: Nubank).

---

## Como funciona

```
GitHub Actions (grátis, na nuvem)                    Seu iPhone
┌────────────────────────────────────────┐
│ a cada 30 min no pregão:               │
│   brapi + Fundamentus + Yahoo + BC  ───┼──► Telegram (alertas)
│ 08h45, 12h45 e 18h15:                  │
│   notícias (InfoMoney, Valor, G1...)   │
│   → IA (Claude) → possibilidades    ───┼──► Telegram (possibilidades + resumo)
│ publica a página do app             ───┼──► Safari → "Tela de Início" (app)
└────────────────────────────────────────┘
```

**Fontes de dados (todas públicas):** brapi.dev (cotações da B3), Fundamentus (indicadores), Yahoo Finance (histórico), Banco Central (Selic, IPCA, dólar), feeds de InfoMoney, Money Times, G1, Agência Brasil, Exame e Google Notícias (filtrado para Valor, Estadão, Folha, Reuters, Bloomberg e outros veículos confiáveis). As cotações têm atraso de 15 a 30 minutos.

---

## Configuração (uns 20 minutos, uma vez só)

### 1. Criar o repositório no GitHub

1. Entre em <https://github.com/new>.
2. Nome: `radar-investimentos` (ou outro que quiser).
3. Marque **Public**. A página do app no GitHub Pages é grátis só para repositório público. Fica público o código e os dados de mercado (que já são públicos). Suas chaves e senhas ficam guardadas em "Secrets", que **não** aparecem para ninguém.
4. **Não** marque "Add a README". Clique em **Create repository**.

### 2. Enviar os arquivos

**Jeito fácil (pelo site):** na página do repositório vazio, clique em **uploading an existing file** e arraste **todo o conteúdo** da pasta `radar-investimentos` (incluindo a pasta `.github`). Clique em **Commit changes**.

> Se a pasta `.github` não for junto (o Windows às vezes esconde), crie o arquivo manualmente: **Add file → Create new file**, nome `.github/workflows/radar.yml`, e cole o conteúdo do arquivo.

**Jeito com Git (no terminal, dentro da pasta):**

```bash
git init -b main
git add .
git commit -m "Radar de Investimentos"
git remote add origin https://github.com/SEU_USUARIO/radar-investimentos.git
git push -u origin main
```

### 3. Criar o bot do Telegram

1. No Telegram, procure **@BotFather** (tem o selo azul de verificado).
2. Mande `/newbot`, escolha um nome (ex.: "Meu Radar") e um usuário terminado em `bot` (ex.: `meu_radar_123_bot`).
3. Ele responde com um **token** parecido com `123456789:AAH...`. Guarde: é a senha do seu bot.
4. Abra a conversa com o seu bot novo e mande qualquer mensagem (ex.: "oi").
5. No navegador, abra este endereço trocando `SEU_TOKEN` pelo token:
   `https://api.telegram.org/botSEU_TOKEN/getUpdates`
6. Procure `"chat":{"id":` e anote o número que vem depois (ex.: `987654321`). Esse é o seu **chat id**.

### 4. (Opcional) Chave da IA, da Anthropic

Sem ela, tabelas e alertas por regras funcionam normalmente, mas não há a análise de notícias.

1. Crie uma conta em <https://console.anthropic.com>.
2. Em **Billing**, adicione créditos (mínimo de US$ 5).
3. Em **API Keys**, clique em **Create Key** e copie a chave (começa com `sk-ant-`).

**Custo estimado** (cerca de 70 análises por mês). Você escolhe o modelo no `config.yaml`:

| Modelo | Qualidade | Custo por mês |
|---|---|---|
| `claude-opus-5-5` (padrão) | o mais inteligente | ~US$ 10 a 15 |
| `claude-sonnet-5-5` | intermediário | ~US$ 5 a 7 |
| `claude-haiku-5-5` | básico | ~US$ 0,50 |

Dica: em **Billing → Limits** você pode definir um limite de gasto mensal.

### 5. Guardar as chaves no GitHub (Secrets)

No repositório: **Settings → Secrets and variables → Actions → New repository secret**. Crie:

| Nome | Valor |
|---|---|
| `TELEGRAM_TOKEN` | o token do BotFather |
| `TELEGRAM_CHAT_ID` | o número do chat id |
| `ANTHROPIC_API_KEY` | a chave da Anthropic (opcional) |

### 6. Ligar o robô

1. Vá na aba **Actions** do repositório. Se aparecer um botão verde para habilitar workflows, clique.
2. Clique em **Radar** (na esquerda) → **Run workflow** → modo **teste** → **Run workflow**.
   Em menos de 1 minuto deve chegar "✅ Radar conectado!" no Telegram.
3. Rode de novo com o modo **resumo**. Esse demora uns 3 minutos e cria a página do app.

### 7. Ativar a página do app

1. **Settings → Pages**.
2. Em **Source**, escolha **Deploy from a branch**, branch **gh-pages**, pasta **/ (root)** → **Save**.
3. Em 1 ou 2 minutos aparece o endereço: `https://SEU_USUARIO.github.io/radar-investimentos/`

### 8. Instalar no iPhone

1. Abra o endereço no **Safari**.
2. Toque em **Compartilhar** (quadrado com a seta) → **Adicionar à Tela de Início**.
3. Pronto: o ícone do Radar fica junto dos seus apps e abre em tela cheia.

---

## Personalizar (arquivo `config.yaml`)

Edite direto no GitHub (abra o arquivo → ícone de lápis → **Commit changes**):

- **`minha_lista`**: os ativos que você acompanha de perto. Dá para colocar preço-alvo:
  ```yaml
  - ticker: PETR4
    nome: Petrobras
    avisar_abaixo: 38.50
  ```
- **`alertas`**: a partir de quantos % de alta ou queda avisar, filtros de "caiu, mas os números são bons" e de "FII com desconto", e a chance mínima da IA para mandar notificação.
- **`ia.modelo`**: troque para `claude-haiku-5-5` se quiser gastar bem menos.
- **`noticias`**: adicione ou remova sites e buscas.

## Horários (Brasília, dias úteis)

| Quando | O que faz |
|---|---|
| A cada 30 min, das 10h às 17h30 | atualiza cotações e manda alertas da sua lista e de altas/quedas fortes |
| 08h45 e 12h45 | lê notícias, roda a IA e manda as possibilidades fortes |
| 18h15 | resumo do dia, possibilidades e filtros "para estudar" |
| Domingo 19h | notícias do fim de semana |

O GitHub às vezes atrasa os horários em 5 a 20 minutos. É normal.

## Bom saber

- **Se ficar 60 dias sem mexer no repositório**, o GitHub pausa os horários automáticos e manda um e-mail. Basta clicar para reativar, ou editar qualquer coisa no `config.yaml`.
- **A nota é uma fórmula**, não uma opinião: ajuda a filtrar, não a prever. Os indicadores vêm do último balanço publicado.
- **A IA só usa as notícias que o robô coletou** e precisa citar de quais notícias tirou cada possibilidade. Possibilidades sem notícia real por trás são descartadas automaticamente.
- **"Caiu, mas os números são bons"** pode ser oportunidade ou armadilha. Sempre leia o motivo da queda.

## Rodar no seu computador (opcional)

```bash
pip install -r requirements.txt
```

```bash
python -m radar --modo resumo --sem-telegram
```

```bash
python -m http.server 8000 --directory publicar
```

Depois abra <http://localhost:8000> no navegador.
