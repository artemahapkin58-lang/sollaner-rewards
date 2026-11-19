# Sollaner Rewards — бесплатный тестовый запуск на Render

## Важно
Эта версия использует Telegram webhook и тип сервиса Render **Web Service** на тарифе Free.
Бесплатный Web Service может засыпать после периода без запросов и запускаться с задержкой.
Файловая система бесплатного сервиса Render временная: SQLite-база может сброситься при перезапуске, пересоздании или новом деплое. Не используй эту версию для хранения ценных балансов без отдельной постоянной базы данных.

## Что загрузить в GitHub
Замени старые файлы этими файлами из папки:
- `main.py`
- `requirements.txt`
- `render.yaml`
- `.env.example`
- `README_RU.md`

Не загружай токен бота в GitHub.

## Render
Создай **New → Web Service**, выбери GitHub-репозиторий `sollaner-rewards`.
Если Render предложит настройки вручную:
- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `python main.py`
- Instance Type: Free

Environment Variables:
- `BOT_TOKEN` — токен от BotFather
- `ADMIN_IDS` — Telegram ID администратора (число; несколько ID через запятую)
- `WEBHOOK_SECRET` — можно сгенерировать случайную длинную строку; если Render применил `render.yaml`, значение создастся автоматически.

После успешного деплоя открой адрес Render в браузере. Должно появиться:
`Sollaner Rewards is running`

## Проверка
Напиши боту `/start`, затем добавь его в группу и выдай права, необходимые для чтения сообщений.
Чтобы бот видел обычные сообщения в группе, отключи Privacy Mode через BotFather (`/setprivacy` → выбрать бота → Disable), затем удали и добавь бота в группу заново.

Подарки в этой версии выдаются администратором вручную после одобрения заявки.
