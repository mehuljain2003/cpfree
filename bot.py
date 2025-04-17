from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
import subprocess
import os
import signal
import pytz

TOKEN = "YOUR_BOT_TOKEN_HERE"
SCRIPT = "cpfree.py"
LOG_FILE = "log.txt"

process = None  # Global to track running process

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is up. Use /run, /stop, /status, /logs.")

async def run_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global process
    if process and process.poll() is None:
        await update.message.reply_text("Script is already running.")
        return

    await update.message.reply_text("Running script...")
    with open(LOG_FILE, "w") as log_file:
        process = subprocess.Popen(
            ["python3", SCRIPT],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )

async def stop_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global process
    if process and process.poll() is None:
        os.kill(process.pid, signal.SIGTERM)
        await update.message.reply_text("Script stopped.")
    else:
        await update.message.reply_text("Script is not running.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global process
    if process and process.poll() is None:
        await update.message.reply_text("Script is running.")
    else:
        await update.message.reply_text("Script is not running.")

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            content = f.read()[-4000:] or "No output yet."
            await update.message.reply_text(f"Logs:\n{content}")
    else:
        await update.message.reply_text("Log file not found.")

from apscheduler.schedulers.asyncio import AsyncIOScheduler
scheduler = AsyncIOScheduler(timezone=pytz.utc)
job_queue = JobQueue(scheduler=scheduler)
app = ApplicationBuilder().token(TOKEN).job_queue(job_queue).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("run", run_script))
app.add_handler(CommandHandler("stop", stop_script))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("logs", logs))

app.run_polling()
