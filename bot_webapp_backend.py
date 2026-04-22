import os
import json
import hmac
import hashlib
import logging
import threading
from urllib.parse import parse_qsl

import requests
from flask import Flask, request, jsonify
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

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL")
MANAGER_ID = os.getenv("MANAGER_ID")
PORT = int(os.getenv("PORT", "10000"))
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")

REQUESTS = {}
REQUEST_COUNTER = 1
PENDING_REPLIES = {}

flask_app = Flask(__name__)


def telegram_api(method: str, payload: dict):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    response = requests.post(url, json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


def verify_telegram_init_data(init_data: str, bot_token: str):
    if not init_data:
        raise ValueError("Empty initData")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash != received_hash:
        raise ValueError("Invalid initData hash")

    user = {}
    if "user" in parsed:
        try:
            user = json.loads(parsed["user"])
        except Exception:
            user = {}

    return parsed, user


def next_request_id():
    global REQUEST_COUNTER
    req_id = REQUEST_COUNTER
    REQUEST_COUNTER += 1
    return req_id


def build_manager_text(req_id: int, data: dict, username_text: str, chat_id):
    request_type = data.get("type") or data.get("action") or data.get("request_type") or ""

    client_name = data.get("name") or data.get("client_name") or data.get("first_name") or "—"
    direction = data.get("direction") or data.get("exchange_direction") or "—"
    amount = data.get("amount") or data.get("sum") or data.get("amount_text") or "—"
    comment = data.get("comment") or data.get("notes") or data.get("comment_text") or "—"
    daily_cc = data.get("daily_cc", "0")
    bank_cc = data.get("bank_cc", "0")
    total_cc = data.get("total_cc", "0")
    usd_value = data.get("usd_value", "0.00")

    if request_type == "exchange_request":
        return (
            f"📩 Новая заявка #{req_id}\n\n"
            f"Имя: {client_name}\n"
            f"Направление: {direction}\n"
            f"Сумма: {amount}\n"
            f"Комментарий: {comment}\n"
            f"Сегодня CC: {daily_cc}\n"
            f"Копилка CC: {bank_cc}\n"
            f"Всего CC: {total_cc}\n"
            f"Эквивалент: ${usd_value}\n\n"
            f"Клиент: {username_text}\n"
            f"Telegram ID: {chat_id}"
        )

    return (
        f"💰 Запрос на обмен CC #{req_id}\n\n"
        f"Сегодня CC: {daily_cc}\n"
        f"Копилка CC: {bank_cc}\n"
        f"Всего CC: {total_cc}\n"
        f"Эквивалент: ${usd_value}\n\n"
        f"Клиент: {username_text}\n"
        f"Telegram ID: {chat_id}"
    )


@flask_app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS, GET"
    return resp


@flask_app.route("/health", methods=["GET"])
def health():
    return {"ok": True}


@flask_app.route("/api/me", methods=["OPTIONS", "POST"])
def api_me():
    if request.method == "OPTIONS":
        return ("", 204)

    if not BOT_TOKEN:
        return jsonify({"ok": False, "error": "BOT_TOKEN missing"}), 500

    body = request.get_json(silent=True) or {}
    init_data = body.get("initData", "")

    try:
        _, user = verify_telegram_init_data(init_data, BOT_TOKEN)
    except Exception:
        logging.exception("initData verification failed in /api/me")
        return jsonify({"ok": False, "error": "initData verification failed"}), 403

    if not user:
        return jsonify({"ok": False, "error": "user missing"}), 400

    full_name = " ".join([part for part in [user.get("first_name", ""), user.get("last_name", "")] if part]).strip() or "Клиент"
    username = ("@" + user["username"]) if user.get("username") else full_name

    return jsonify({
        "ok": True,
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "display_name": username,
            "full_name": full_name,
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", "")
        }
    })


@flask_app.route("/api/webapp-submit", methods=["OPTIONS", "POST"])
def webapp_submit():
    if request.method == "OPTIONS":
        return ("", 204)

    if not BOT_TOKEN:
        return jsonify({"ok": False, "error": "BOT_TOKEN missing"}), 500

    body = request.get_json(silent=True) or {}
    init_data = body.get("initData", "")
    data = body.get("data", {})

    logging.info("API /api/webapp-submit body: %s", body)

    try:
        _, user = verify_telegram_init_data(init_data, BOT_TOKEN)
    except Exception:
        logging.exception("initData verification failed")
        return jsonify({"ok": False, "error": "initData verification failed"}), 403

    user_id = user.get("id")
    username_text = f"@{user.get('username')}" if user.get("username") else "нет username"
    chat_id = user_id

    if not user_id:
        return jsonify({"ok": False, "error": "user_id missing"}), 400

    req_id = next_request_id()
    REQUESTS[req_id] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "data": data,
    }

    manager_text = build_manager_text(req_id, data, username_text, chat_id)
    reply_markup = {
        "inline_keyboard": [[{"text": "💬 Ответить клиенту", "callback_data": f"reply:{req_id}"}]]
    }

    try:
        manager_target = int(MANAGER_ID) if MANAGER_ID else chat_id
        telegram_api("sendMessage", {
            "chat_id": manager_target,
            "text": manager_text,
            "reply_markup": reply_markup
        })

        telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": f"✅ Заявка #{req_id} отправлена.\nОжидайте ответ менеджера в этом чате."
        })
    except Exception:
        logging.exception("Failed to send Telegram messages from API")
        return jsonify({"ok": False, "error": "telegram send failed"}), 500

    return jsonify({"ok": True, "request_id": req_id})


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
        logging.exception("Ошибка чтения JSON из web_app_data")
        await update.message.reply_text("Ошибка чтения заявки.")
        return

    req_id = next_request_id()

    REQUESTS[req_id] = {
        "chat_id": chat.id,
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "data": data,
    }

    username_text = f"@{user.username}" if user and user.username else "нет username"
    manager_text = build_manager_text(req_id, data, username_text, chat.id)

    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Ответить клиенту", callback_data=f"reply:{req_id}")]]
    )

    if MANAGER_ID:
        await context.bot.send_message(
            chat_id=int(MANAGER_ID),
            text=manager_text,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(manager_text, reply_markup=reply_markup)

    await update.message.reply_text(
        f"✅ Заявка #{req_id} отправлена.\nОжидайте ответ менеджера в этом чате."
    )


async def reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if MANAGER_ID and str(query.message.chat_id) != str(MANAGER_ID):
        await query.message.reply_text("Эта кнопка доступна только менеджеру.")
        return

    if not query.data.startswith("reply:"):
        return

    req_id = int(query.data.split(":")[1])

    if req_id not in REQUESTS:
        await query.message.reply_text("Заявка не найдена.")
        return

    PENDING_REPLIES[query.message.chat_id] = req_id

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

    await update.message.reply_text(f"✅ Ответ по заявке #{req_id} отправлен клиенту.")
    del PENDING_REPLIES[manager_chat_id]


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def main():
    if not BOT_TOKEN:
        raise ValueError("Не задан BOT_TOKEN")
    if not MINI_APP_URL:
        raise ValueError("Не задан MINI_APP_URL")

    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(reply_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manager_message))

    logging.info("Bot + API started...")
    app.run_polling()


if __name__ == "__main__":
    main()
