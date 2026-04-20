import os, json, logging
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(format="%(asctime)s | %(name)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger("crypto_cash_direct_bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-mini-app-url")
CITY_NAME = os.getenv("CITY_NAME", "Краснодар")

def app_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Открыть терминал", web_app=WebAppInfo(url=MINI_APP_URL))]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        try:
            await context.bot.set_chat_menu_button(
                chat_id=update.effective_chat.id,
                menu_button=MenuButtonWebApp(text="Открыть терминал", web_app=WebAppInfo(url=MINI_APP_URL))
            )
        except Exception as exc:
            logger.warning("Could not set menu button: %s", exc)

    text = (
        "<b>CRYPTO CASH</b>\n"
        "Private exchange desk\n\n"
        f"Безопасный обмен USDT, USDC, USD, EUR, RUB в {escape(CITY_NAME)}.\n"
        "Конфиденциальность клиента — наш приоритет.\n\n"
        "Открой терминал кнопкой ниже."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=app_keyboard())

async def app_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Открой терминал:", reply_markup=app_keyboard())

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.web_app_data:
        return

    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.reply_text("Получены некорректные данные из mini app.")
        return

    kind = payload.get("type")
    if kind == "exchange_request":
        text = (
            "<b>Новая заявка из mini app</b>\n\n"
            f"Имя: {escape(str(payload.get('name', '—')))}\n"
            f"Контакт: {escape(str(payload.get('contact', '—')))}\n"
            f"Направление: {escape(str(payload.get('direction', '—')))}\n"
            f"Сумма: {escape(str(payload.get('amount', '—')))}\n"
            f"Комментарий: {escape(str(payload.get('comment', '—')))}\n"
            f"Сегодня CC: {escape(str(payload.get('daily_cc', 0)))}\n"
            f"Копилка CC: {escape(str(payload.get('bank_cc', 0)))}\n"
            f"Всего CC: {escape(str(payload.get('total_cc', 0)))}\n"
            f"Эквивалент: ${escape(str(payload.get('usd_value', '0.00')))}"
        )
        await message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    if kind == "cc_withdraw_request":
        text = (
            "<b>Запрос на обмен CC</b>\n\n"
            f"Сегодня CC: {escape(str(payload.get('daily_cc', 0)))}\n"
            f"Копилка CC: {escape(str(payload.get('bank_cc', 0)))}\n"
            f"Всего CC: {escape(str(payload.get('total_cc', 0)))}\n"
            f"Эквивалент: ${escape(str(payload.get('usd_value', '0.00')))}"
        )
        await message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    await message.reply_text("Получен неизвестный тип данных из mini app.")

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("app", app_cmd))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
