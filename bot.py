import os
import json
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
MANAGER_ID = os.getenv("MANAGER_ID")

# Заявки в памяти процесса
REQUESTS = {}
REQUEST_COUNTER = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("🚀 Открыть терминал", web_app=WebAppInfo(url=MINI_APP_URL))]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Crypto Cash — private exchange desk.\n\n"
        "Безопасный обмен USDT / USD / EUR / RUB\n\n"
        "👇 Открой терминал:",
        reply_markup=reply_markup
    )


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global REQUEST_COUNTER

    if not update.message or not update.message.web_app_data:
        return

    user = update.effective_user
    chat = update.effective_chat

    try:
        data = json.loads(update.message.web_app_data.data)
    except Exception:
        await update.message.reply_text("Ошибка чтения заявки.")
        return

    req_id = REQUEST_COUNTER
    REQUEST_COUNTER += 1

    REQUESTS[req_id] = {
        "chat_id": chat.id,
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "data": data,
    }

    username_text = f"@{user.username}" if user and user.username else "нет username"

    if data.get("type") == "exchange_request":
        manager_text = (
            f"📩 Новая заявка #{req_id}\n\n"
            f"Имя: {data.get('name', '—')}\n"
            f"Направление: {data.get('direction', '—')}\n"
            f"Сумма: {data.get('amount', '—')}\n"
            f"Комментарий: {data.get('comment', '—')}\n"
            f"Сегодня CC: {data.get('daily_cc', '0')}\n"
            f"Копилка CC: {data.get('bank_cc', '0')}\n"
            f"Всего CC: {data.get('total_cc', '0')}\n"
            f"Эквивалент: ${data.get('usd_value', '0.00')}\n\n"
            f"Клиент: {username_text}\n"
            f"Telegram ID: {chat.id}\n\n"
            f"Ответить клиенту:\n"
            f"/reply {req_id} ваш текст"
        )
    else:
        manager_text = (
            f"💰 Запрос на обмен CC #{req_id}\n\n"
            f"Сегодня CC: {data.get('daily_cc', '0')}\n"
            f"Копилка CC: {data.get('bank_cc', '0')}\n"
            f"Всего CC: {data.get('total_cc', '0')}\n"
            f"Эквивалент: ${data.get('usd_value', '0.00')}\n\n"
            f"Клиент: {username_text}\n"
            f"Telegram ID: {chat.id}\n\n"
            f"Ответить клиенту:\n"
            f"/reply {req_id} ваш текст"
        )

    # Сообщение клиенту
    await update.message.reply_text(
        f"✅ Заявка #{req_id} отправлена.\n"
        f"Ожидайте ответ менеджера в этом чате."
    )

    # Сообщение менеджеру
    if MANAGER_ID:
        await context.bot.send_message(chat_id=int(MANAGER_ID), text=manager_text)
    else:
        # запасной вариант — в этот же чат
        await update.message.reply_text(manager_text)


async def reply_to_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not MANAGER_ID:
        await update.message.reply_text("MANAGER_ID не задан.")
        return

    if str(update.effective_chat.id) != str(MANAGER_ID):
        await update.message.reply_text("Команда доступна только менеджеру.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /reply ID_заявки текст")
        return

    try:
        req_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID заявки должен быть числом.")
        return

    if req_id not in REQUESTS:
        await update.message.reply_text("Заявка не найдена.")
        return

    text = " ".join(context.args[1:])
    client_chat_id = REQUESTS[req_id]["chat_id"]

    await context.bot.send_message(
        chat_id=client_chat_id,
        text=f"💬 Ответ менеджера по заявке #{req_id}:\n\n{text}"
    )

    await update.message.reply_text(f"Ответ по заявке #{req_id} отправлен клиенту.")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_to_client))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
