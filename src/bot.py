import asyncio
import importlib.metadata
import logging
import os
import sys
import warnings
from typing import Optional

import requests
from telegram.warnings import PTBUserWarning
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

API_URL = "https://open.er-api.com/v6/latest/{base}"
TIMEOUT_S = 5

CURRENCIES = ["USD", "EUR", "RUB", "GBP", "CNY", "JPY", "CHF", "TRY"]
BUTTONS_PER_ROW = 4

SELECT_FROM = 0
SELECT_TO = 1
ENTER_AMOUNT = 2


def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ and value:
                    os.environ[key] = value
    except Exception:
        logging.exception("Failed to read .env file: %s", path)


def build_currency_keyboard(*, exclude: Optional[str] = None, prefix: str) -> InlineKeyboardMarkup:
    items = [c for c in CURRENCIES if c != exclude]
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(items), BUTTONS_PER_ROW):
        row = [
            InlineKeyboardButton(text=code, callback_data=f"{prefix}:{code}")
            for code in items[i : i + BUTTONS_PER_ROW]
        ]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def fetch_rates(base: str) -> Optional[dict]:
    url = API_URL.format(base=base)

    def _do_request() -> dict:
        return requests.get(url, timeout=TIMEOUT_S).json()

    try:
        data = await asyncio.to_thread(_do_request)
    except Exception:
        logging.exception("API request failed: %s", url)
        return None

    if not isinstance(data, dict):
        logging.error("API returned non-dict payload for %s", url)
        return None

    if data.get("result") != "success":
        logging.error("API error for %s: %s", url, data.get("error-type"))
        return None

    rates = data.get("rates")
    if not isinstance(rates, dict):
        logging.error("API payload missing rates for %s", url)
        return None

    return rates


async def get_rate(from_code: str, to_code: str) -> Optional[float]:
    rates = await fetch_rates(from_code)
    if not rates:
        return None
    raw = rates.get(to_code)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def format_amount(x: float) -> str:
    return f"{x:,.2f}"


def format_rate(x: float) -> str:
    return f"{x:.4f}"


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я конвертирую валюты по актуальным курсам.\n\n"
        "Команды:\n"
        "/rate <ИЗ> <В> [сумма] — курс или конвертация суммы\n"
        "/convert — пошаговая конвертация\n"
        "/help — подробная инструкция\n"
        "/cancel — отмена текущего диалога"
    )
    await update.effective_message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Как пользоваться:\n\n"
        "/rate <ИЗ> <В> [сумма]\n"
        "Примеры:\n"
        "- /rate USD EUR\n"
        "- /rate USD RUB 100\n\n"
        "/convert\n"
        "- выбери валюту ИЗ\n"
        "- выбери валюту В\n"
        "- введи сумму обычным текстом\n\n"
        f"Поддерживаемые валюты: {', '.join(CURRENCIES)}\n\n"
        "Примечания:\n"
        "- Сумма должна быть числом (например: 10 или 10.5)\n"
        "- Курсы берутся с open.er-api.com"
    )
    await update.effective_message.reply_text(text)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("from", None)
    context.user_data.pop("to", None)
    await update.effective_message.reply_text("Отменено.")
    return ConversationHandler.END


async def rate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    args = context.args
    if len(args) < 2 or len(args) > 3:
        await msg.reply_text("Формат: /rate <ИЗ> <В> [сумма]\nПример: /rate USD EUR 100")
        return

    from_code = args[0].upper()
    to_code = args[1].upper()
    if from_code not in CURRENCIES or to_code not in CURRENCIES:
        await msg.reply_text(f"Неподдерживаемая валюта. Доступны: {', '.join(CURRENCIES)}")
        return
    if from_code == to_code:
        await msg.reply_text("Валюты «ИЗ» и «В» должны отличаться.")
        return

    amount: Optional[float] = None
    if len(args) == 3:
        try:
            amount = float(args[2].replace(",", ""))
        except ValueError:
            await msg.reply_text("Сумма должна быть числом, например 100 или 12.5")
            return
        if amount <= 0:
            await msg.reply_text("Сумма должна быть больше 0.")
            return

    rate = await get_rate(from_code, to_code)
    if rate is None:
        await msg.reply_text(f"Не удалось получить курс для {from_code} → {to_code}. Попробуй позже.")
        return

    if amount is None:
        await msg.reply_text(f"1 {from_code} = {format_rate(rate)} {to_code}")
        return

    result = amount * rate
    await msg.reply_text(
        f"{format_amount(amount)} {from_code} = {format_amount(result)} {to_code}\n"
        f"Курс: {format_rate(rate)}"
    )


async def convert_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выбери валюту, ИЗ которой конвертируем:",
        reply_markup=build_currency_keyboard(prefix="FROM"),
    )
    return SELECT_FROM


async def convert_select_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query or not query.data:
        return SELECT_FROM

    await query.answer()
    try:
        prefix, code = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("Что-то пошло не так. Запусти /convert заново.")
        return ConversationHandler.END

    if prefix != "FROM" or code not in CURRENCIES:
        await query.edit_message_text("Некорректный выбор. Запусти /convert заново.")
        return ConversationHandler.END

    context.user_data["from"] = code
    await query.edit_message_text(
        f"Валюта ИЗ: {code}\n\nТеперь выбери валюту, В которую конвертируем:",
        reply_markup=build_currency_keyboard(exclude=code, prefix="TO"),
    )
    return SELECT_TO


async def convert_select_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query or not query.data:
        return SELECT_TO

    await query.answer()
    try:
        prefix, code = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_text("Что-то пошло не так. Запусти /convert заново.")
        return ConversationHandler.END

    from_code = context.user_data.get("from")
    if prefix != "TO" or code not in CURRENCIES or not from_code or code == from_code:
        await query.edit_message_text("Некорректный выбор. Запусти /convert заново.")
        return ConversationHandler.END

    context.user_data["to"] = code
    await query.edit_message_text(f"Валюта В: {code}\n\nТеперь введи сумму:")
    return ENTER_AMOUNT


async def convert_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.effective_message
    text = (msg.text or "").strip()

    try:
        amount = float(text.replace(",", ""))
    except ValueError:
        await msg.reply_text("Введи число (например 100 или 12.5):")
        return ENTER_AMOUNT

    if amount <= 0:
        await msg.reply_text("Сумма должна быть больше 0. Попробуй ещё раз:")
        return ENTER_AMOUNT

    from_code = context.user_data.get("from")
    to_code = context.user_data.get("to")
    if not from_code or not to_code:
        await msg.reply_text("Состояние диалога потеряно. Запусти /convert заново.")
        return ConversationHandler.END

    rate = await get_rate(from_code, to_code)
    if rate is None:
        await msg.reply_text(f"Не удалось получить курс для {from_code} → {to_code}. Попробуй позже.")
        return ConversationHandler.END

    result = amount * rate
    await msg.reply_text(
        f"{format_amount(amount)} {from_code} = {format_amount(result)} {to_code}\n"
        f"Курс: {format_rate(rate)}"
    )

    context.user_data.pop("from", None)
    context.user_data.pop("to", None)
    return ConversationHandler.END


async def post_init(app: Application) -> None:
    commands = [
        BotCommand("start", "Приветствие и список команд"),
        BotCommand("help", "Как пользоваться ботом"),
        BotCommand("rate", "Курс или конвертация: /rate USD EUR 100"),
        BotCommand("convert", "Пошаговая конвертация"),
        BotCommand("cancel", "Отмена текущего диалога"),
    ]
    try:
        await app.bot.set_my_commands(commands)
        logging.getLogger(__name__).info("Меню команд обновлено")
    except Exception:
        logging.exception("Не удалось обновить меню команд")


def build_app(token: str) -> Application:
    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20, pool_timeout=20)
    app = Application.builder().token(token).request(request).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("rate", rate_cmd))

    conv = ConversationHandler(
        entry_points=[CommandHandler("convert", convert_entry)],
        states={
            SELECT_FROM: [CallbackQueryHandler(convert_select_from, pattern=r"^FROM:")],
            SELECT_TO: [CallbackQueryHandler(convert_select_to, pattern=r"^TO:")],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, convert_enter_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    return app


def _ensure_ptb_version() -> None:
    """python-telegram-bot 20.x ломается на Python 3.13+ (Updater/__slots__)."""
    if sys.version_info < (3, 13):
        return
    try:
        installed = importlib.metadata.version("python-telegram-bot")
    except importlib.metadata.PackageNotFoundError:
        return
    parts = installed.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return
    if (major, minor) >= (21, 0):
        return
    raise RuntimeError(
        f"В этом venv стоит python-telegram-bot {installed}, он несовместим с Python "
        f"{sys.version_info.major}.{sys.version_info.minor}. Обнови зависимости (из папки currency-bot):\n"
        r"  .\.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt"
    )


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Смешанный сценарий /convert: команда → callback → текст. Для личного чата
    # per_message=False достаточно; PTB только предупреждает — шум в консоли.
    warnings.filterwarnings(
        "ignore",
        category=PTBUserWarning,
        message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked.*",
    )

    _ensure_ptb_version()

    if not os.getenv("BOT_TOKEN"):
        load_env_file(".env")

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError('BOT_TOKEN is not set. Set it in the environment, e.g. in ".env".')

    logging.getLogger(__name__).info("Starting currency bot")
    build_app(token).run_polling(bootstrap_retries=3)


if __name__ == "__main__":
    main()

