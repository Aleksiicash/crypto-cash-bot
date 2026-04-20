import os
import json
from telegram import (
    Update,
    WebAppInfo,
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
MANAGER_ID = os.getenv("MANAGER_ID")

REQUESTS = {}
REQUEST_COUNTER = 1
PENDING_REPLIES = {}


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
            f"Telegram ID: {chat.id}"
        )
    else:
        manager_text = (
            f"💰 Запрос на обмен CC #{req_id}\n\n"
            f"Сегодня CC: {data.get('daily_cc', '0')}\n"
            f"Копилка CC: {data.get('bank_cc', '0')}\n"
            f"Всего CC: {data.get('total_cc', '0')}\n"
            f"Эквивалент: ${data.get('usd_value', '0.00')}\n\n"
            f"Клиент: {username_text}\n"
            f"Telegram ID: {chat.id}"
        )

    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "💬 Ответить клиенту",
                    callback_data=f"reply:{req_id}"
                )
            ]
        ]
    )

    await update.message.reply_text(
        f"✅ Заявка #{req_id} отправлена.\n"
        f"Ожидайте ответ менеджера в этом чате."
    )

    if MANAGER_ID:
        await context.bot.send_message(
            chat_id=int(MANAGER_ID),
            text=manager_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            manager_text,
            reply_markup=reply_markup
        )


async def reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if MANAGER_ID and str(query.message.chat_id) != str(MANAGER_ID):
        await query.message.reply_text("Эта кнопка доступна только менеджеру.")
        return

    data = query.data
    if not data.startswith("reply:"):
        return

    req_id = int(data.split(":")[1])

    if req_id not in REQUESTS:
        await query.message.reply_text("Заявка не найдена.")
        return

    manager_chat_id = query.message.chat_id
    PENDING_REPLIES[manager_chat_id] = req_id

    await query.message.reply_text(
        f"✍️ Напиши сообщение для заявки #{req_id}.\n"
        f"Оно будет отправлено клиенту следующим сообщением."
    )


async def handle_manager_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    manager_chat_id = update.effective_chat.id

    if MANAGER_ID and str(manager_chat_id) != str(MANAGER_ID):
        return

    if manager_chat_id not in PENDING_REPLIES:
        return

    req_id = PENDING_REPLIES[manager_chat_id]

    if req_id not in REQUESTS:
        await update.message.reply_text("Заявка не найдена.")
        del PENDING_REPLIES[manager_chat_id]
        return

    client_chat_id = REQUESTS[req_id]["chat_id"]
    text = update.message.text or ""

    await context.bot.send_message(
        chat_id=client_chat_id,
        text=f"💬 Ответ менеджера по заявке #{req_id}:\n\n{text}"
    )

    await update.message.reply_text(
        f"✅ Ответ по заявке #{req_id} отправлен клиенту."
    )

    del PENDING_REPLIES[manager_chat_id]


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(reply_button))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_manager_message
        )
    )

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()


