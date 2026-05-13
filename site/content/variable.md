---
title: "Вариативная часть: Telegram-бот для конвертации валют"
date: 2026-05-12
---

# 💱 Currency Bot — Telegram-бот для конвертации валют

> Учебный проект в рамках проектной практики  
> Московский политехнический университет, кафедра информационных технологий  
> Группа 251-333 | Направление: 09.03.02 Информационные системы и технологии

---

## 📋 Описание

**Currency Bot** (`@mospolytech_currency_bot`) — это Telegram-бот на Python,
который позволяет получать актуальные курсы валют и конвертировать суммы
в режиме реального времени через внешний API.

### Что умеет бот:

- 💱 Показывает актуальный курс любой из 8 поддерживаемых валют
- 🔢 Конвертирует сумму одной командой `/rate`
- 🎛️ Пошаговая конвертация через inline-кнопки `/convert`
- ❌ Отмена текущего диалога командой `/cancel`
- ⚠️ Корректно обрабатывает ошибки и недоступность API

---

## 🛠️ Стек технологий

| Технология | Назначение |
|---|---|
| Python 3.10+ | Язык программирования |
| python-telegram-bot 22.x | Асинхронная работа с Telegram Bot API |
| requests | HTTP-запросы к API курсов валют |
| open.er-api.com | Источник актуальных курсов валют |
| asyncio | Асинхронное выполнение запросов |
| Git / GitHub | Контроль версий |

---

## 💬 Поддерживаемые валюты

`USD` `EUR` `RUB` `GBP` `CNY` `JPY` `CHF` `TRY`

---

## 🚀 Установка и запуск

### 1. Клонируй репозиторий

```bash
git clone https://github.com/zhilinka/project-practice-2026
cd project-practice-2026/src
```

### 2. Создай виртуальное окружение

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Linux / macOS
```

### 3. Установи зависимости

```bash
pip install -r requirements.txt
```

### 4. Настрой токен

Создай файл `.env` в папке `src/`:

```
BOT_TOKEN=ВАШ_ТОКЕН_ЗДЕСЬ
```

### 5. Запусти бота

```bash
python bot.py
```

---

## 💬 Использование

| Команда | Результат |
|---|---|
| `/start` | Приветствие и список команд |
| `/help` | Подробная инструкция |
| `/rate USD RUB` | Курс доллара к рублю |
| `/rate USD RUB 100` | Сколько рублей за 100 долларов |
| `/convert` | Пошаговая конвертация через кнопки |
| `/cancel` | Отмена текущего диалога |

### Пример ответа бота:

```
100.00 USD = 9,050.00 RUB
Курс: 90.5000
```

---

## 📁 Структура репозитория

```
project-practice-2026/
├── src/
│   ├── bot.py           # Основной код бота
│   └── requirements.txt
├── docs/                # Документация в Markdown
│   ├── tutorial.md      # Туториал по созданию бота
│   ├── partner-report.md
│   ├── final-report.md
│   └── journal.md
├── site/                # Статический сайт на Hugo
├── reports/             # Отчёты по практике
│   ├── report.docx
│   └── report.pdf
└── info/
    └── DESCRIPTION.md
```

---

## 👥 Команда

| Участник | Роль |
|---|---|
| Жилин Константин Владимирович | Репозиторий, статический сайт, документация |
| Беджанов Азамат Асланович | Разработка Telegram-бота |

---

## 📚 Полезные ссылки

- [Документация Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot](https://python-telegram-bot.org)
- [ExchangeRate API](https://open.er-api.com)
- [Официальная документация Git](https://git-scm.com/book/ru/v2)
- [Сайт проекта](https://zhilinka.github.io/project-practice-2026/)
