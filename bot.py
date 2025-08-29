# bot.py

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from stats import get_stats
from datetime import datetime, timedelta
import os

TOKEN = "7822949362:AAHzvt_QcyC8NenIYF5kejErWgp4OZLv3CQ"

def format_result(result, start, end):
    return (
        f"📊 Доход с {start.date()} по {end.date()}:\n"
        f"🇷🇺 {result['rub']} ₽\n"
        f"🇺🇦 {result['uah']} ₴\n"
        f"💵 ≈ {result['usd']} $\n"
    )

async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    result = get_stats(today, tomorrow)
    await update.message.reply_text(format_result(result, today, tomorrow))

async def month_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = now
    result = get_stats(start, end)
    await update.message.reply_text(format_result(result, start, end))

async def range_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("❌ Используй формат:\n`/range 2025-07-01 2025-07-06`", parse_mode='Markdown')
        return

    try:
        start = datetime.strptime(args[0], "%Y-%m-%d")
        end = datetime.strptime(args[1], "%Y-%m-%d") + timedelta(days=1)
        result = get_stats(start, end)
        await update.message.reply_text(format_result(result, start, end))
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("month", month_handler))
    app.add_handler(CommandHandler("range", range_handler))

    print("✅ Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
