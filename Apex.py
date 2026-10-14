import os
import sys
import subprocess
import threading
import time
import psutil
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "7985785104"))
BOT_NAME  = "Apex"
HOST_DIR  = Path("./apex_hosted")
MAX_FILE  = 10 * 1024 * 1024
# ==========================================

HOST_DIR.mkdir(exist_ok=True)
RUNNING = {}


# ---------- Render ke liye chhota HTTP server ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Apex is alive!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server running on port {port}")
    server.serve_forever()


# ---------- Baaki saara logic ----------
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def human_size(b):
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f}{u}"
        b /= 1024
    return f"{b:.1f}TB"


def stream_output(proc, name, chat_id, bot, restart, filepath):
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            line = line.rstrip()
            if line:
                try:
                    bot.send_message(chat_id, f"📄 `{name}`\n```\n{line[:3500]}\n```",
                                     parse_mode="Markdown")
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        proc.wait()
        if proc.pid in RUNNING:
            del RUNNING[proc.pid]
        exit_code = proc.returncode
        if restart and exit_code is not None and filepath and Path(filepath).exists():
            try:
                bot.send_message(chat_id, f"🔄 `{name}` crash hua. Restart...",
                                 parse_mode="Markdown")
                time.sleep(3)
                new_proc = subprocess.Popen(
                    [sys.executable, filepath],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    cwd=str(Path(filepath).parent),
                    text=True, bufsize=1,
                )
                RUNNING[new_proc.pid] = {
                    "proc": new_proc, "name": name,
                    "started": datetime.now().strftime("%H:%M:%S"),
                    "restart": True, "filepath": filepath, "chat_id": chat_id,
                }
                threading.Thread(
                    target=stream_output,
                    args=(new_proc, name, chat_id, bot, True, filepath),
                    daemon=True
                ).start()
            except Exception as e:
                bot.send_message(chat_id, f"Restart fail: {e}")
        else:
            bot.send_message(chat_id, f"`{name}` band (exit {exit_code}).",
                             parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Tu admin nahi hai.")
        return
    await update.message.reply_text(
        f"👑 *{BOT_NAME} Hosting Bot*\n\n"
        f"Python file bhej — auto run ho jayegi.\n"
        f"Caption me `restart` likh — crash pe auto-restart.\n\n"
        f"*Commands:* /start /status /list /files /run /kill /stopall /del /clean",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    await update.message.reply_text(
        f"🤖 *{BOT_NAME} Status*\n\n"
        f"🕒 `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
        f"⚙️ Running: `{len(RUNNING)}`\n"
        f"💾 Files: `{len(list(HOST_DIR.glob('*.py')))}`\n"
        f"🧠 CPU: `{cpu}%`\n"
        f"📊 RAM: `{mem.percent}%`",
        parse_mode="Markdown"
    )


async def list_procs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not RUNNING:
        await update.message.reply_text("📭 Koi process nahi chal raha.")
        return
    msg = "📋 *Running:*\n"
    for pid, info in RUNNING.items():
        r = "🔄" if info.get("restart") else "▶️"
        msg += f"\n{r} PID `{pid}` — `{info['name']}`"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def kill_proc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/kill <pid>`", parse_mode="Markdown")
        return
    try:
        pid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid PID.")
        return
    if pid in RUNNING:
        RUNNING[pid]["restart"] = False
        RUNNING[pid]["proc"].terminate()
        await update.message.reply_text(f"✅ PID `{pid}` band.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ PID nahi mila.")


async def stop_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    count = 0
    for pid, info in list(RUNNING.items()):
        try:
            info["restart"] = False
            info["proc"].terminate()
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"🛑 {count} band kar diye.")


async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    files = list(HOST_DIR.glob("*.py"))
    if not files:
        await update.message.reply_text("📭 Koi saved file nahi.")
        return
    msg = "💾 *Files:*\n"
    for f in files:
        msg += f"\n📄 `{f.name}`"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def run_saved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/run name.py`", parse_mode="Markdown")
        return
    fpath = HOST_DIR / context.args[0]
    if not fpath.exists():
        await update.message.reply_text("❌ File nahi mili.")
        return
    await _launch(update, context, str(fpath), context.args[0], restart=False)


async def del_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/del name.py`", parse_mode="Markdown")
        return
    fpath = HOST_DIR / context.args[0]
    if fpath.exists():
        fpath.unlink()
        await update.message.reply_text("🗑 Delete ho gayi.")
    else:
        await update.message.reply_text("❌ File nahi mili.")


async def clean_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    count = 0
    for f in HOST_DIR.glob("*.py"):
        f.unlink()
        count += 1
    await update.message.reply_text(f"🧹 {count} files delete.")


async def _launch(update, context, filepath, name, restart=False):
    try:
        proc = subprocess.Popen(
            [sys.executable, filepath],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(Path(filepath).parent), text=True, bufsize=1,
        )
        RUNNING[proc.pid] = {
            "proc": proc, "name": name,
            "started": datetime.now().strftime("%H:%M:%S"),
            "restart": restart, "filepath": filepath,
            "chat_id": update.effective_chat.id,
        }
        threading.Thread(
            target=stream_output,
            args=(proc, name, update.effective_chat.id, context.bot, restart, filepath),
            daemon=True
        ).start()
        await update.message.reply_text(
            f"✅ Hosted!\n📄 `{name}`\n🆔 PID `{proc.pid}`\n🔄 Auto: `{'ON' if restart else 'OFF'}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Launch fail: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized.")
        return
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".py"):
        await update.message.reply_text("❌ Sirf .py file bhej.")
        return
    if doc.file_size > MAX_FILE:
        await update.message.reply_text("❌ File 10MB se badi.")
        return
    restart = bool(update.message.caption and "restart" in update.message.caption.lower())
    safe_name = f"{int(time.time())}_{doc.file_name}"
    filepath = HOST_DIR / safe_name
    msg = await update.message.reply_text(f"📥 Download: `{doc.file_name}`...", parse_mode="Markdown")
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(str(filepath))
    except Exception as e:
        await msg.edit_text(f"❌ Download fail: {e}")
        return
    await msg.edit_text(f"🚀 Run: `{doc.file_name}`...", parse_mode="Markdown")
    await _launch(update, context, str(filepath), safe_name, restart=restart)


async def error_handler(update, context):
    print(f"[ERROR] {context.error}")


def main():
    print(f"🤖 {BOT_NAME} Bot start ho raha hai...")

    # Render ke liye health server thread
    threading.Thread(target=start_health_server, daemon=True).start()

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN environment variable set nahi hai!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("list", list_procs))
    app.add_handler(CommandHandler("files", list_files))
    app.add_handler(CommandHandler("run", run_saved))
    app.add_handler(CommandHandler("kill", kill_proc))
    app.add_handler(CommandHandler("stopall", stop_all))
    app.add_handler(CommandHandler("del", del_file))
    app.add_handler(CommandHandler("clean", clean_all))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_error_handler(error_handler)

    print(f"✅ {BOT_NAME} LIVE!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()