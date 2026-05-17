# claude-telegram-bot

Conecta o **Claude Code do seu PC** ao **Telegram**. Você manda mensagem (texto, áudio ou arquivo) pro bot no celular, ele repassa pro Claude Code rodando em casa, e devolve a resposta. Sessão persistente por usuário — o Claude lembra das mensagens anteriores.

Funciona como **secretária pessoal técnica**: ela tem acesso ao teu setup completo (arquivos, ferramentas, agenda local) e te responde no celular.

```
[Telegram no celular]                                                   
       │                                                                
       │ mensagem (texto/áudio/arquivo)                                 
       ▼                                                                
[bot.py rodando no seu PC]                                              
       │                                                                
       │ subprocess: claude -p --session-id <UUID> "<texto>"            
       ▼                                                                
[Claude Code lê CLAUDE.md (personalidade) + faz o trabalho]             
       │                                                                
       │ stdout                                                         
       ▼                                                                
[Resposta volta pro Telegram, dividida em chunks se for longa]          
```

## Pré-requisitos

- **PC com Windows / macOS / Linux** ligado quando você quiser usar o bot
- **Python 3.10+** instalado
- **Claude Code instalado** e funcionando no terminal (`claude --help` deve responder)
- **Conta Telegram** no seu celular
- ~30-60 minutos pra configurar tudo na primeira vez

---

## Passo a passo

### Passo 1 — Clonar este repositório

Abra um terminal (PowerShell no Windows, Terminal no Mac/Linux) e:

```bash
cd ~/Documents              # ou onde você quiser
git clone https://github.com/jorgepenna87/claude-telegram-bot.git
cd claude-telegram-bot
```

> Não tem `git` instalado? Baixe o ZIP pelo botão verde "Code" → "Download ZIP" no GitHub e extraia.

### Passo 2 — Criar ambiente Python e instalar dependências

```bash
python -m venv .venv
```

Ativar o venv:
- **Windows PowerShell:** `.\.venv\Scripts\Activate.ps1`
- **macOS/Linux:** `source .venv/bin/activate`

Instalar deps:
```bash
pip install -r bot/requirements.txt
```

### Passo 3 — Criar o bot no Telegram (via @BotFather)

1. No Telegram, busque o usuário **@BotFather** e abra a conversa
2. Mande `/newbot`
3. Escolha um nome pro bot (aparece no topo da conversa): ex. "Sofia"
4. Escolha um username (precisa terminar em "bot"): ex. `sofia_da_carla_bot`
5. O BotFather responde com um token tipo `7234567890:AAH...` — **COPIE isso** (é o `TELEGRAM_BOT_TOKEN`)

### Passo 4 — Configurar o `.env`

```bash
cd bot
cp .env.example .env          # macOS/Linux
# OU no Windows:
copy .env.example .env
```

Abra o `.env` num editor de texto (notepad, VS Code, qualquer um) e cole:

```
TELEGRAM_BOT_TOKEN=cole_o_token_que_o_BotFather_te_deu
ALLOWED_USER_IDS=
BOT_NAME=Sofia
```

`ALLOWED_USER_IDS` você descobre no próximo passo — deixa vazio por enquanto.

### Passo 5 — Descobrir teu user_id no Telegram

1. No terminal (com venv ativado), rode pela primeira vez:
   ```bash
   python bot.py
   ```
   Vai aparecer erro `ALLOWED_USER_IDS é obrigatório` — esperado. Volte o terminal.

2. **Alternativa rápida pra descobrir o ID:** no Telegram, busque **@userinfobot**, mande `/start`, ele te responde com teu `user_id` (número de 9-10 dígitos).

3. Volte no `.env` e cole o número em `ALLOWED_USER_IDS=`:
   ```
   ALLOWED_USER_IDS=123456789
   ```

> **Querendo dar acesso a outras pessoas** (cônjuge, sócio, filho)? Peça pra cada uma fazer o mesmo no @userinfobot, e adicione os IDs separados por vírgula: `ALLOWED_USER_IDS=123456789,987654321`.

### Passo 6 — Personalizar o `CLAUDE.md`

Esse arquivo é onde mora a **personalidade** do seu agente. O Claude Code lê toda vez que recebe mensagem.

```bash
cd ..    # volta pra raiz do projeto
cp CLAUDE.md.template CLAUDE.md
```

Abra `CLAUDE.md` no editor e:

1. **Substitua os `[colchetes]`** com seus dados reais (nome, profissão, rotina)
2. Defina o **tom** que você quer (curto, formal, com emoji, etc.)
3. Defina as **regras de OK** — o que o agente pode fazer sozinho vs o que precisa te perguntar antes

**Não sabe por onde começar?** Veja os 3 exemplos em `examples/`:
- [Secretária de escritório](examples/personalidade-secretaria.md)
- [Tutor de estudos](examples/personalidade-tutor.md)
- [Coach de produtividade pessoal](examples/personalidade-coach.md)

Copie o que se parece mais com seu caso, cole no seu `CLAUDE.md`, e adapte.

### Passo 7 — (Opcional, mas recomendado) Habilitar áudio

Pra mandar áudio pro bot e ele transcrever (com Whisper), você precisa de uma chave gratuita da Groq:

1. Acesse https://console.groq.com/keys
2. Crie conta (login com Google)
3. Crie uma API key e copie
4. Cole no `.env`:
   ```
   GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
   WHISPER_LANG=pt
   ```

Groq tem tier grátis generoso (14.400 minutos/mês de Whisper). Mais que suficiente pra uso pessoal.

Se você não quiser áudio, só deixe vazio — o bot vai aceitar texto e arquivos só.

### Passo 8 — Rodar o bot

No terminal com venv ativado:

```bash
cd bot
python bot.py
```

Deve aparecer:
```
INFO claude-bridge: Bot Sofia iniciado. claude=/usr/local/bin/claude | cwd=...
```

Agora vai no Telegram, abra a conversa com seu bot, mande `/start`. Ele deve responder com a saudação + UUID da sessão.

Mande qualquer coisa pra testar:
- "qual a capital da França?"
- Manda um áudio
- Manda um PDF

O bot pipa pro Claude Code, que lê teu `CLAUDE.md` e responde no tom que você configurou.

---

## Como manter o bot rodando 24/7

### Windows — Task Scheduler

1. Win+R → `taskschd.msc`
2. Create Basic Task
   - Name: `Telegram Bot`
   - Trigger: At log on (do seu user)
   - Action: Start a program
     - Program: `C:\Users\seuuser\claude-telegram-bot\.venv\Scripts\python.exe`
     - Arguments: `bot.py`
     - Start in: `C:\Users\seuuser\claude-telegram-bot\bot`
3. Conditions: desmarcar "Start only if on AC power" se for laptop

### macOS — launchd

Crie `~/Library/LaunchAgents/com.user.claude-telegram-bot.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.claude-telegram-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/seuuser/claude-telegram-bot/.venv/bin/python</string>
        <string>/Users/seuuser/claude-telegram-bot/bot/bot.py</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/seuuser/claude-telegram-bot/bot</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
```
Carregue: `launchctl load ~/Library/LaunchAgents/com.user.claude-telegram-bot.plist`

### Linux — systemd user

Crie `~/.config/systemd/user/claude-telegram-bot.service`:
```ini
[Unit]
Description=Claude Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/claude-telegram-bot/bot
ExecStart=%h/claude-telegram-bot/.venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```
Ative: `systemctl --user enable --now claude-telegram-bot`

---

## Comandos disponíveis no Telegram

| Comando | O que faz |
|---|---|
| `/start` | Boas-vindas + UUID da sessão atual |
| `/whoami` | Mostra seu user_id, username, nome, se está autorizado |
| `/reset` | Zera a sessão (o bot esquece tudo da conversa anterior) |
| `/sessao` | Mostra o UUID completo da sessão atual |
| (texto) | Vai direto pro Claude |
| (áudio) | Transcrito pelo Whisper, depois vai pro Claude |
| (arquivo/foto) | Salvo em `Inbox/Telegram/`, Claude é avisado pra processar |

---

## Como adicionar/remover usuários autorizados

Edite `bot/.env`, mude `ALLOWED_USER_IDS=...` (separe por vírgula), e **reinicie o bot** (Ctrl+C e rode `python bot.py` de novo, ou reinicie o serviço).

---

## Como funciona por baixo

Cada `user_id` do Telegram tem um arquivo `bot/sessions/{user_id}.session` com um UUID. O `bot.py` invoca:

```bash
claude -p --session-id <UUID> "<sua mensagem>"
```

Na primeira mensagem do user, é `--session-id` (cria sessão nova). Nas seguintes, `--resume` (continua de onde parou).

A pasta de trabalho do Claude (`CLAUDE_WORK_DIR`) é a raiz deste repo por padrão. O Claude vai ler o `CLAUDE.md` daí e ter acesso a qualquer arquivo da pasta.

---

## Privacidade e segurança

- **Allowlist obrigatória:** ninguém que não esteja em `ALLOWED_USER_IDS` consegue usar o bot
- **Token do Telegram + chave Groq** ficam no `.env` (gitignored, não vai pro repo)
- **Sessões** ficam local em `bot/sessions/` (gitignored)
- **Áudios** baixados ficam em `Inbox/Telegram/` — você pode apagar manualmente
- **Whisper Groq:** o áudio é enviado pra API da Groq pra transcrição. Não use o bot pra conteúdo sensível se isso te preocupa. (Alternativa: usar Whisper local via `whisper.cpp`, mas precisa de mais setup)

---

## Resolução de problemas

| Erro | Causa | Fix |
|---|---|---|
| `TELEGRAM_BOT_TOKEN é obrigatório` | `.env` vazio ou não foi lido | Confira o `.env` na pasta `bot/` |
| `Você não está autorizado` | Seu user_id não está em `ALLOWED_USER_IDS` | Adicione no `.env` e reinicie |
| `Não encontrei o binário do claude` | Claude Code não instalado ou fora do PATH | `claude --help` no terminal pra confirmar |
| `Timeout após 600s` | Comando demorado demais | Suba `CLAUDE_TIMEOUT_SECONDS` no `.env` |
| Bot recebe mas não responde | Erro no claude (verifica logs do terminal) | Olha o stderr no terminal onde rodou `python bot.py` |
| Áudio: "GROQ_API_KEY não está no .env" | Whisper desabilitado | Pegue chave em console.groq.com/keys |

---

## Licença

MIT. Use livremente, adapte, distribua. Origem deste template: https://github.com/jorgepenna87/claude-telegram-bot
