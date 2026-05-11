---
title: "Туториал: Telegram-бот для конвертации валют"
date: 2026-05-12
slug: "tutorial"
description: "Пошаговое руководство по созданию асинхронного Telegram-бота на Python с реальными курсами валют, inline-кнопками и диалогом /convert."
---

## Введение

В этом руководстве создаётся Telegram-бот для конвертации валют с нуля.
Бот показывает актуальные курсы и конвертирует суммы через внешний API.
Руководство рассчитано на начинающих разработчиков.

**Стек технологий:**

- Python 3.10+
- `python-telegram-bot` 22.x (асинхронный API)
- `requests` — HTTP-запросы к API курсов
- `open.er-api.com` — бесплатный API курсов валют

**Поддерживаемые валюты:** USD, EUR, RUB, GBP, CNY, JPY, CHF, TRY

---

## Этап 1. Подготовка окружения

### 1.1 Установка Python

Скачайте Python 3.10 или новее: https://python.org

```bash
python --version
```

### 1.2 Создание виртуального окружения

```bash
python -m venv .venv

# активировать:
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux / macOS
```

### 1.3 Установка зависимостей

Файл `requirements.txt`:

```
python-telegram-bot==22.7
requests>=2.31.0
```

```bash
pip install -r requirements.txt
```

> **Python 3.13+:** требуется `python-telegram-bot >= 21.0`.
> Бот проверяет совместимость автоматически через `_ensure_ptb_version()`.

### 1.4 Регистрация бота в Telegram

1. Найдите **@BotFather** в Telegram
2. Напишите `/newbot` и следуйте инструкциям
3. Скопируйте полученный токен

### 1.5 Сохранение токена

Создайте файл `.env` рядом с `bot.py`:

```
BOT_TOKEN=7412345678:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> Добавьте `.env` в `.gitignore` — токен не должен попасть в репозиторий.

---

## Этап 2. Архитектура

Весь бот находится в одном файле `bot.py`. Код разбит на логические блоки:

```
bot.py
├── Конфигурация       — API_URL, CURRENCIES, состояния диалога
├── load_env_file()    — чтение .env без сторонних библиотек
├── fetch_rates()      — асинхронный HTTP-запрос к API
├── get_rate()         — извлечение курса конкретной пары
├── format_amount()    — форматирование сумм: 22625.5 → "22,625.50"
├── format_rate()      — форматирование курса: 90.5 → "90.5000"
├── build_currency_keyboard() — inline-клавиатура с валютами
├── Обработчики команд — /start, /help, /cancel, /rate, /convert
├── build_app()        — сборка Application с хэндлерами
└── main()             — точка входа
```

### Схема потока данных

```
Пользователь
    │  команда
    ▼
Telegram API
    │  polling
    ▼
Application (build_app)
    │
    ├──► Обработчики (/start /help /rate /convert)
    │
    └──► API-клиент (fetch_rates)
              │  GET /v6/latest/{base}
              ▼
         open.er-api.com
              │  {rates: {...}}
              ▼
         Обработчик → ответ пользователю
```

---

## Этап 3. Разбор кода

### 3.1 Конфигурация

```python
API_URL = "https://open.er-api.com/v6/latest/{base}"
TIMEOUT_S = 5

CURRENCIES = ["USD", "EUR", "RUB", "GBP", "CNY", "JPY", "CHF", "TRY"]
BUTTONS_PER_ROW = 4

# Состояния ConversationHandler
SELECT_FROM  = 0
SELECT_TO    = 1
ENTER_AMOUNT = 2
```

Состояния диалога — просто числа, `range(3)` генерирует 0, 1, 2.

### 3.2 Загрузка .env без сторонних библиотек

```python
def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            # пропускаем пустые строки и комментарии
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            # не перезаписываем уже установленные переменные
            if key and key not in os.environ and value:
                os.environ[key] = value
```

Функция разбирает `.env` вручную — без `python-dotenv`. Это уменьшает
количество зависимостей проекта.

### 3.3 Асинхронный запрос к API курсов

```python
async def fetch_rates(base: str) -> Optional[dict]:
    url = API_URL.format(base=base)

    def _do_request() -> dict:
        return requests.get(url, timeout=TIMEOUT_S).json()

    try:
        # requests — синхронная библиотека.
        # asyncio.to_thread() запускает её в пуле потоков,
        # не блокируя event loop бота.
        data = await asyncio.to_thread(_do_request)
    except Exception:
        logging.exception("API request failed: %s", url)
        return None

    # валидируем ответ
    if data.get("result") != "success":
        logging.error("API error: %s", data.get("error-type"))
        return None

    rates = data.get("rates")
    if not isinstance(rates, dict):
        return None

    return rates


async def get_rate(from_code: str, to_code: str) -> Optional[float]:
    rates = await fetch_rates(from_code)
    if not rates:
        return None
    try:
        return float(rates.get(to_code))
    except (TypeError, ValueError):
        return None
```

**Ключевой момент:** `requests` — синхронная библиотека. Прямой вызов
заблокировал бы весь event loop и бот перестал бы реагировать на
сообщения. `asyncio.to_thread()` решает это, выполняя запрос в отдельном
потоке.

### 3.4 Inline-клавиатура

```python
def build_currency_keyboard(
    *, exclude: Optional[str] = None, prefix: str
) -> InlineKeyboardMarkup:
    items = [c for c in CURRENCIES if c != exclude]
    rows = []
    for i in range(0, len(items), BUTTONS_PER_ROW):
        row = [
            InlineKeyboardButton(text=code, callback_data=f"{prefix}:{code}")
            for code in items[i : i + BUTTONS_PER_ROW]
        ]
        rows.append(row)
    return InlineKeyboardMarkup(rows)
```

Кнопки разбиваются по 4 в ряд. **Префикс** в `callback_data` позволяет
различать нажатия на шагах «ИЗ» и «В» с помощью паттернов в
`CallbackQueryHandler`:

```python
# Шаг 1 — клавиатура ИЗ
build_currency_keyboard(prefix="FROM")
# → callback_data = "FROM:USD", "FROM:EUR", ...

# Шаг 2 — клавиатура В (без уже выбранной валюты)
build_currency_keyboard(exclude="USD", prefix="TO")
# → callback_data = "TO:EUR", "TO:RUB", ...
```

### 3.5 Обработчик /rate

```python
async def rate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg  = update.effective_message
    args = context.args

    if len(args) < 2 or len(args) > 3:
        await msg.reply_text("Формат: /rate <ИЗ> <В> [сумма]")
        return

    from_code = args[0].upper()
    to_code   = args[1].upper()

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
        await msg.reply_text(f"Не удалось получить курс для {from_code} → {to_code}.")
        return

    if amount is None:
        await msg.reply_text(f"1 {from_code} = {format_rate(rate)} {to_code}")
    else:
        result = amount * rate
        await msg.reply_text(
            f"{format_amount(amount)} {from_code} = {format_amount(result)} {to_code}\n"
            f"Курс: {format_rate(rate)}"
        )
```

Цепочка валидации: формат аргументов → поддержка валюты → валюты не
совпадают → корректность суммы → успешный ответ API.

### 3.6 Шаги диалога /convert

**Шаг 1 — точка входа, выбор валюты «ИЗ»:**

```python
async def convert_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(
        "Выбери валюту, ИЗ которой конвертируем:",
        reply_markup=build_currency_keyboard(prefix="FROM"),
    )
    return SELECT_FROM
```

**Шаг 2 — обработка нажатия, выбор валюты «В»:**

```python
async def convert_select_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, code = query.data.split(":", 1)          # "FROM:USD" → "USD"
    context.user_data["from"] = code
    await query.edit_message_text(
        f"Валюта ИЗ: {code}\n\nТеперь выбери валюту, В которую:",
        reply_markup=build_currency_keyboard(exclude=code, prefix="TO"),
    )
    return SELECT_TO
```

**Шаг 3 — ввод суммы и результат:**

```python
async def convert_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    amount    = float(update.effective_message.text.replace(",", ""))
    from_code = context.user_data["from"]
    to_code   = context.user_data["to"]
    rate      = await get_rate(from_code, to_code)
    result    = amount * rate
    await update.effective_message.reply_text(
        f"{format_amount(amount)} {from_code} = {format_amount(result)} {to_code}\n"
        f"Курс: {format_rate(rate)}"
    )
    context.user_data.pop("from", None)
    context.user_data.pop("to", None)
    return ConversationHandler.END
```

### 3.7 Сборка приложения

```python
def build_app(token: str) -> Application:
    request = HTTPXRequest(
        connect_timeout=20, read_timeout=20,
        write_timeout=20,   pool_timeout=20
    )
    app = (
        Application.builder()
        .token(token)
        .request(request)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  start_cmd))
    app.add_handler(CommandHandler("help",   help_cmd))
    app.add_handler(CommandHandler("rate",   rate_cmd))

    conv = ConversationHandler(
        entry_points=[CommandHandler("convert", convert_entry)],
        states={
            SELECT_FROM:  [CallbackQueryHandler(convert_select_from,  pattern=r"^FROM:")],
            SELECT_TO:    [CallbackQueryHandler(convert_select_to,    pattern=r"^TO:")],
            ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, convert_enter_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_cmd)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    return app
```

### 3.8 Справочник функций

| Функция | Назначение | Возвращает |
|---|---|---|
| `load_env_file()` | Читает `.env` без сторонних библиотек | `None` |
| `build_currency_keyboard()` | Строит inline-клавиатуру с валютами | `InlineKeyboardMarkup` |
| `fetch_rates()` | Асинхронный HTTP-запрос к API, валидация ответа | `Optional[dict]` |
| `get_rate()` | Извлекает курс конкретной пары | `Optional[float]` |
| `format_amount()` | `22625.5` → `"22,625.50"` | `str` |
| `format_rate()` | `90.5` → `"90.5000"` | `str` |
| `post_init()` | Устанавливает меню команд после запуска | `None` (async) |
| `build_app()` | Собирает `Application` с хэндлерами | `Application` |
| `_ensure_ptb_version()` | Проверяет совместимость библиотеки с Python | `None` / `RuntimeError` |
| `main()` | Точка входа: логгирование, `.env`, запуск polling | `None` |

---

## Этап 4. Диаграмма последовательности /convert

```
Пользователь          Бот                    open.er-api.com
     │                  │                           │
     │── /convert ────► │                           │
     │◄─ кнопки ИЗ ─────│                           │
     │── FROM:USD ─────► │                           │
     │◄─ кнопки В ───────│                           │
     │── TO:RUB ────────► │                           │
     │◄─ "Введи сумму" ──│                           │
     │── "100" ──────────►│                           │
     │                  │── GET /v6/latest/USD ─────►│
     │                  │◄─ {rates: {RUB: 90.5}} ───│
     │◄─ 100.00 USD = 9,050.00 RUB ────────────────│
```

---

## Этап 5. Диаграмма состояний ConversationHandler

```
      /convert
         │
         ▼
┌──────────────────┐
│   SELECT_FROM    │  ◄── CallbackQueryHandler (pattern ^FROM:)
└────────┬─────────┘
         │ callback FROM:XXX
         ▼
┌──────────────────┐
│    SELECT_TO     │  ◄── CallbackQueryHandler (pattern ^TO:)
└────────┬─────────┘
         │ callback TO:XXX
         ▼
┌──────────────────┐
│   ENTER_AMOUNT   │  ◄── MessageHandler (TEXT & ~COMMAND)
└────────┬─────────┘
         │ число
         ▼
  ConversationHandler.END

  /cancel на любом шаге → END
  allow_reentry=True → /convert перезапускает диалог без END
```

---

## Этап 6. Модификация проекта

В качестве творческой модификации добавлена расширенная версия команды
`/rate` с необязательным третьим аргументом — суммой для конвертации.

**Стандартная реализация** возвращает только курс за 1 единицу.
**Модифицированная версия** позволяет получить готовый результат за один
запрос, без запуска полного диалога `/convert`.

```
/rate USD RUB       → 1 USD = 90.5000 RUB
/rate USD RUB 250   → 250.00 USD = 22,625.00 RUB
                      Курс: 90.5000
/rate USD RUB 1,500 → 1,500.00 USD = 135,750.00 RUB
```

Детали реализации:

- Принимает строго 2 или 3 аргумента: `len(args) < 2 or len(args) > 3`
- Запятая как разделитель тысяч: `args[2].replace(",", "")` — принимает `"1,000"` и `"1000"`
- Проверка знака: `amount <= 0` отклоняется с сообщением об ошибке
- Форматирование через `format_amount()` — использует `f"{x:,.2f}"`

---

## Этап 7. Запуск

```bash
python bot.py
```

Ожидаемый вывод в консоли:

```
2026-01-01 12:00:00,000 - __main__ - INFO - Starting currency bot
2026-01-01 12:00:00,500 - __main__ - INFO - Меню команд обновлено
```

Найдите бота в Telegram и напишите `/start`. Для остановки — **Ctrl+C**.

---

## Итог

| Команда | Описание |
|---|---|
| `/start` | Приветствие и список команд |
| `/help` | Подробная инструкция |
| `/rate <ИЗ> <В>` | Курс: `1 USD = 90.5000 RUB` |
| `/rate <ИЗ> <В> <сумма>` | Конвертация: `250.00 USD = 22,625.00 RUB` |
| `/convert` | Пошаговая конвертация через inline-кнопки |
| `/cancel` | Отмена текущего диалога |

---

## Ссылки

- [python-telegram-bot](https://python-telegram-bot.org) — документация библиотеки
- [open.er-api.com](https://open.er-api.com) — бесплатный API курсов валют
- [Telegram Bot API](https://core.telegram.org/bots/api) — официальная документация
- [Исходный код](https://github.com/zhilinka/project-practice-2026/tree/main/src) — репозиторий проекта
