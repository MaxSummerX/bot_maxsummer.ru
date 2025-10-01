import os
import requests
import logging

from slugify import slugify
from mistralai import Mistral
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)

load_dotenv()

raw_ids = os.getenv("TELEGRAM_USER_ID")
if not raw_ids:
    raise ValueError('TELEGRAM_USER_ID пуст или не задан в файле .env')

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = os.getenv("API_URL")
DRF_TOKEN = os.getenv("DRF_TOKEN")
TELEGRAM_USER_IDS = set(map(int, raw_ids.split(',')))
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL")

SELECT_MODE, TITLE, BODY, GENERATE_INPUT, CONFIRM_PUBLISH = range(5)

logging.basicConfig(level=logging.INFO)

mistral_client = Mistral(api_key=MISTRAL_API_KEY)


def is_authorized(user_id: int) -> bool:
    return user_id in TELEGRAM_USER_IDS



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔️ Доступ запрещён.")
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton("✍️ Написать пост вручную", callback_data="manual"),
            InlineKeyboardButton("🤖 Сгенерировать пост", callback_data="generate")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите режим:", reply_markup=reply_markup)
    return SELECT_MODE



async def select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "manual":
        await query.edit_message_text("✍️ Введите заголовок поста:")
        return TITLE
    elif query.data == 'generate':
        await query.edit_message_text("🤖 Введите запрос для генерации статьи:")
        return GENERATE_INPUT
    return ConversationHandler.END



async def get_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Теперь отправьте тело поста (Markdown поддерживается):")
    return BODY



async def get_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
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



async def send_long_message(text, update: Update, reply_markup=None):
    max_length = 4096
    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
    for num, part in enumerate(parts):
        if num == len(parts) - 1 and reply_markup:
            await update.message.reply_text(part, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(part, parse_mode='Markdown')



async def handle_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    context.user_data['prompt'] = prompt

    try:
        response = mistral_client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
        context.user_data['generated'] = reply

        keyword =[[
            InlineKeyboardButton("✅ Опубликовать", callback_data='publish'),
            InlineKeyboardButton("❌ Отмена", callback_data='cancel')
        ]]
        markup = InlineKeyboardMarkup(keyword)

        await send_long_message(reply, update, reply_markup=markup)
        return CONFIRM_PUBLISH

    except Exception as e:
        await update.message.reply_text(f"Ошибка генерации: {str(e)}")
        return ConversationHandler.END



async def handle_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'publish':
        title = context.user_data.get('prompt', 'AI-пост').strip()[:100]
        slug = slugify(title)
        body = context.user_data['generated']
        data = {
            "title": title,
            "body": body,
            "status": "PB",
            "slug": slug
        }
        headers = {
            "Authorization": f"Token {DRF_TOKEN}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(API_URL, json=data, headers=headers)
            if response.status_code == 201:
                await query.edit_message_text("✅ Пост опубликован.")
            else:
                await query.edit_message_text(f"❌ Ошибка {response.status_code}:\n{response.text}")
        except Exception as e:
            await query.edit_message_text(f"Ошибка публикации: {str(e)}")
    else:
        await query.edit_message_text("❌ Операция отменена.")

    return ConversationHandler.END



def setup_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_MODE: [CallbackQueryHandler(select_mode)],
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_title)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body)],
            GENERATE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_generation)],
            CONFIRM_PUBLISH: [CallbackQueryHandler(handle_decision)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)
    return app