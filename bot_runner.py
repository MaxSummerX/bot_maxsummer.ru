from telegram_bot import setup_bot

if __name__ == '__main__':
    app = setup_bot()
    app.run_polling()