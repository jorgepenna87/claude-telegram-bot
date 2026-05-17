#!/usr/bin/env python3
"""Ponte Telegram -> Claude Code com sessão persistente por usuário.

Recebe texto, áudio e arquivos pelo Telegram, repassa pro `claude -p
--session-id <uuid>` rodando localmente, e devolve a resposta. Cada user_id
mantém sua própria sessão (continuidade de conversa). Allowlist via .env.

Comandos:
  /start  - boas-vindas e sessão atual
  /whoami - dados do user (útil pra descobrir teu user_id)
  /reset  - zera a sessão do user (esquece tudo)
  /sessao - mostra o UUID da sessão atual
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_DIR = Path(__file__).resolve().parent
load_dotenv(BOT_DIR / ".env")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
BOT_NAME = os.environ.get("BOT_NAME", "Assistente").strip()
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if x.strip()
}
WORK_DIR = Path(
    os.environ.get("CLAUDE_WORK_DIR", str(BOT_DIR.parent))
).expanduser().resolve()
INBOX = WORK_DIR / "Inbox" / "Telegram"
INBOX.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = BOT_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
WHISPER_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
WHISPER_LANG = os.environ.get("WHISPER_LANG", "pt").strip()
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_TIMEOUT_SECONDS", "600"))

CLAUDE_BIN = (
    shutil.which("claude")
    or shutil.which("claude.cmd")
    or shutil.which("claude.exe")
    or "claude"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("claude-bridge")


def is_allowed(update: Update) -> bool:
    return bool(
        update.effective_user and update.effective_user.id in ALLOWED_USER_IDS
    )


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def safe_name(name: str) -> str:
    keep = "-_.() "
    cleaned = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return cleaned[:120] or "file"


def session_file(user_id: int) -> Path:
    return SESSIONS_DIR / f"{user_id}.session"


def session_marker(user_id: int) -> Path:
    """Existe se a sessão já foi criada no Claude (use --resume daqui)."""
    return SESSIONS_DIR / f"{user_id}.active"


def get_session_id(user_id: int) -> str:
    f = session_file(user_id)
    if f.exists():
        sid = f.read_text(encoding="utf-8").strip()
        if sid:
            return sid
    sid = str(uuid.uuid4())
    f.write_text(sid, encoding="utf-8")
    log.info("Nova sessão para user=%s: %s", user_id, sid)
    return sid


def mark_session_active(user_id: int) -> None:
    session_marker(user_id).touch()


def is_session_active(user_id: int) -> bool:
    return session_marker(user_id).exists()


def reset_session(user_id: int) -> str:
    sid = str(uuid.uuid4())
    session_file(user_id).write_text(sid, encoding="utf-8")
    m = session_marker(user_id)
    if m.exists():
        m.unlink()
    log.info("Reset sessão user=%s -> %s", user_id, sid)
    return sid


async def transcribe_voice(file_path: Path) -> str:
    if not WHISPER_API_KEY:
        return ""
    async with httpx.AsyncClient(timeout=120) as client:
        with open(file_path, "rb") as f:
            r = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {WHISPER_API_KEY}"},
                files={"file": (file_path.name, f, "audio/ogg")},
                data={"model": "whisper-large-v3", "language": WHISPER_LANG},
            )
            r.raise_for_status()
            return r.json().get("text", "").strip()


def _claude_sync(
    prompt: str, session_id: str, resume: bool
) -> tuple[int, str, str]:
    if resume:
        args = [CLAUDE_BIN, "-p", "--resume", session_id, prompt]
    else:
        args = [CLAUDE_BIN, "-p", "--session-id", session_id, prompt]
    try:
        res = subprocess.run(
            args,
            cwd=str(WORK_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLAUDE_TIMEOUT,
            shell=False,
        )
        return res.returncode, res.stdout or "", res.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout após {CLAUDE_TIMEOUT}s"
    except FileNotFoundError as e:
        return -2, "", f"Não encontrei o binário do claude: {e}"


async def run_claude(prompt: str, user_id: int) -> tuple[int, str, str]:
    sid = get_session_id(user_id)
    resume = is_session_active(user_id)
    log.info(
        "claude -p (%d chars, session=%s, user=%s, mode=%s)",
        len(prompt), sid, user_id, "resume" if resume else "new",
    )
    loop = asyncio.get_running_loop()
    rc, out, err = await loop.run_in_executor(
        None, functools.partial(_claude_sync, prompt, sid, resume)
    )
    if rc == 0 and not resume:
        mark_session_active(user_id)
    return rc, out, err


def chunks(text: str, size: int = 4000):
    text = text.strip()
    if not text:
        yield "(sem resposta)"
        return
    for i in range(0, len(text), size):
        yield text[i:i + size]


async def reply_long(update: Update, text: str) -> None:
    for piece in chunks(text):
        await update.message.reply_text(piece)


async def dispatch(update: Update, prompt: str) -> None:
    user_id = update.effective_user.id
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception as e:
        log.warning("send_action falhou (ignorado): %s", e)
    rc, out, err = await run_claude(prompt, user_id)
    if rc != 0:
        body = f"Claude saiu com código {rc}.\n\nstderr:\n{err[:1500]}"
        if out:
            body += f"\n\nstdout:\n{out[:500]}"
        await reply_long(update, body)
        return
    await reply_long(update, out)


async def handle_text(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        log.warning(
            "Bloqueado: user=%s",
            update.effective_user.id if update.effective_user else "?",
        )
        return
    text = update.message.text or ""
    if not text.strip():
        return
    log.info("Texto de %s: %s", update.effective_user.id, text[:80])
    await dispatch(update, text)


async def handle_voice(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    if not WHISPER_API_KEY:
        await update.message.reply_text(
            "Recebi áudio, mas GROQ_API_KEY não está no .env."
        )
        return
    await update.message.reply_text("Transcrevendo áudio...")
    tg_file = await voice.get_file()
    target = INBOX / f"{ts()}_voice.ogg"
    await tg_file.download_to_drive(custom_path=str(target))
    try:
        text = await transcribe_voice(target)
    except Exception as e:
        log.exception("Whisper falhou")
        await update.message.reply_text(f"Falha na transcrição: {e}")
        return
    if not text:
        await update.message.reply_text("Whisper não entendeu o áudio.")
        return
    await update.message.reply_text(f"Transcrição: {text}")
    await dispatch(update, text)


async def handle_document(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    msg = update.message
    if msg.document:
        tg_file = await msg.document.get_file()
        original = msg.document.file_name or "document"
    elif msg.photo:
        tg_file = await msg.photo[-1].get_file()
        original = "photo.jpg"
    else:
        return
    target = INBOX / f"{ts()}_{safe_name(original)}"
    await msg.reply_text(f"Recebendo {original}...")
    await tg_file.download_to_drive(custom_path=str(target))
    caption = (msg.caption or "").strip()
    pieces = [
        "[Arquivo recebido via Telegram]",
        f"Caminho: {target}",
    ]
    if caption:
        pieces.append(f"Mensagem do usuário: {caption}")
    else:
        pieces.append(
            "Sem mensagem. Identifique o tipo de arquivo e faça o "
            "apropriado, ou pergunte ao usuário o que fazer."
        )
    await dispatch(update, "\n".join(pieces))


async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        uid = update.effective_user.id if update.effective_user else "?"
        await update.message.reply_text(
            f"Você não está autorizado. Seu user_id: {uid}\n\n"
            "Peça pro dono do bot adicionar este id em ALLOWED_USER_IDS."
        )
        return
    sid = get_session_id(update.effective_user.id)
    await update.message.reply_text(
        f"{BOT_NAME} conectado. Manda texto, áudio ou arquivo.\n\n"
        f"Sessão: {sid[:8]}...\n"
        "Comandos: /reset (nova sessão) | /sessao | /whoami"
    )


async def cmd_whoami(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if not u:
        return
    allowed = "sim" if u.id in ALLOWED_USER_IDS else "não"
    await update.message.reply_text(
        f"user_id: {u.id}\nusername: @{u.username or '(sem)'}\n"
        f"nome: {u.full_name}\nautorizado: {allowed}"
    )


async def cmd_reset(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    sid = reset_session(update.effective_user.id)
    await update.message.reply_text(
        f"Sessão zerada. Nova: {sid[:8]}...\n"
        "Esqueci as mensagens anteriores."
    )


async def cmd_sessao(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    sid = get_session_id(update.effective_user.id)
    await update.message.reply_text(f"Sessão: {sid}")


def main() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not ALLOWED_USER_IDS:
        missing.append("ALLOWED_USER_IDS")
    if missing:
        print(
            f"ERRO: configure no .env: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("sessao", cmd_sessao))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(
        MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    log.info(
        "Bot %s iniciado. claude=%s | cwd=%s | inbox=%s | sessions=%s "
        "| users=%s | whisper=%s",
        BOT_NAME, CLAUDE_BIN, WORK_DIR, INBOX, SESSIONS_DIR, ALLOWED_USER_IDS,
        "on" if WHISPER_API_KEY else "off",
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
