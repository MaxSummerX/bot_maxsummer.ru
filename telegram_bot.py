import requests
import logging
from slugify import slugify
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://maxsummer.ru/api/?format=api"
DRF_TOKEN = os.getenv("DRF_TOKEN")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", 0))

TITLE, BODY = range(2)

logging.basicConfig(level=logging.INFO)


def is_authorized(user_id: int) -> bool:
    return user_id == TELEGRAM_USER_ID



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return ConversationHandler.END

    await update.message.reply_text("Привет! Отправь заголовок поста.")
    return TITLE



async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Теперь отправь тело поста (поддерживается Markdown).")
    return BODY



async def get_body(update:Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data['title']
    body = update.message.text
    slug = slugify(title)

    data = {
        "title": title,
        "body": body,
        "status": "PB", # Published
        "slug": slug
    }

    headers = {
        "Authorization": f"Token {DRF_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(API_URL, json=data, headers=headers)
        if response.status_code == 201:
            await update.message.reply_text("✅ Пост опубликован.")
        else:
            await update.message.reply_text(f"❌ Ошибка {response.status_code}:\n{response.text}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

    return ConversationHandler.END



async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Операция отменена')
    return ConversationHandler.END



def setup_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)
    return app

