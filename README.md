# Моти — Telegram Tamagochi

Скелет Telegram Mini App: **aiogram 3 + FastAPI + Supabase Postgres + Vercel**.
Один проект и домен: FastAPI отдаёт HTML, API и принимает webhook Telegram.
Frontend — простой HTML/CSS/JS без сборки, чтобы сначала развивать механику.

## Структура

```text
main.py                          # FastAPI, маршруты, webhook, статика
backend/
  auth.py                        # Проверка подписи и срока Telegram initData
  bot.py                         # aiogram: /start и кнопка Mini App
  config.py                      # Переменные окружения
  game.py                        # Чистая логика питомца
  repository.py                  # Supabase REST, условные обновления
frontend/
  index.html                     # Экран питомца
  assets/app.js                  # Telegram SDK и вызовы API
  assets/style.css               # Минимальные стили
supabase/migrations/0001_pets.sql # Таблица, ограничения и RLS
scripts/set_webhook.py           # Регистрация webhook и кнопки меню
tests/                           # Авторизация, механика, API
vercel.json                      # FastAPI preset
pyproject.toml                   # Зависимости проекта и настройки инструментов
uv.lock                          # Зафиксированные версии для сборки Vercel
.env.example                     # Шаблон настроек
```

## Что уже работает в коде

- `/start` отправляет кнопку открытия игры в личном чате.
- Первый авторизованный вход создаёт одного питомца на Telegram ID.
- Сытость, настроение, энергия, чистота: 0–100.
- За час отсутствия: −4 сытости, −3 настроения, −2 энергии, −3 чистоты.
- Покормить: +25 сытости; поиграть: +25 настроения, −15 энергии, −5 сытости.
- Искупать: +30 чистоты; отдохнуть: +30 энергии.
- Успешное действие даёт 10 XP, каждые 100 XP — новый уровень.
- Общая пауза между действиями — 10 секунд. При основном показателе >95 действие отклоняется.
- Питомец не умирает. Сон пока мгновенное восстановление, без режима сна.

Время и награды определяет сервер. Показатели пересчитываются при чтении, а сохраняются
при действии. Поэтому фоновые таймеры и cron для деградации не нужны.
Обновление использует `WHERE version = previous_version`: одновременные запросы не
перезаписывают прогресс. После конфликта правила проверяются заново.

## Локальный запуск (PowerShell, Python 3.12+)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Заполнить .env своими значениями
.\.venv\Scripts\python -m uvicorn main:app --reload
```

Открыть `http://127.0.0.1:8000`: вне Telegram виден каркас с подсказкой входа,
игровые запросы требуют настоящего `initData`. Swagger: `/docs`, healthcheck: `/api/health`.
Для полноценной локальной игры нужен HTTPS-туннель на порт 8000: его адрес записать
в `WEBAPP_URL` и запустить регистрацию webhook. Используйте отдельного тестового бота:
у одного бота только один webhook, регистрация заменяет предыдущий адрес.

## Supabase

1. Создать проект Supabase.
2. Выполнить миграции из `supabase/migrations/` в порядке номера в SQL Editor.
   Если `0001_pets.sql` уже выполнялся, запустить только `0002_pet_names.sql`.
   Она добавляет выбор имени без сброса существующих питомцев.
3. Из настроек API скопировать URL проекта и **legacy `service_role` key** в
   `SUPABASE_URL` и `SUPABASE_SERVICE_ROLE_KEY`.

Ключ доступен только Python backend. Frontend не обращается в Supabase напрямую.
У таблицы включён RLS, права `anon` и `authenticated` отозваны; backend с
`service_role` проверяет Telegram-подпись и ограничивает запросы ID владельца.
Supabase Auth для этого скелета не используется.

## Vercel и Telegram

1. Создать бота через `@BotFather`, получить `BOT_TOKEN`.
2. Загрузить проект в Git и импортировать в Vercel, Root Directory — корень репозитория.
   Preset — **FastAPI**. Пользовательские Build Command и Output Directory не нужны.
3. Добавить переменные из `.env.example` в Vercel:
   - `BOT_TOKEN` — токен бота;
   - `WEBAPP_URL` — постоянный HTTPS production-адрес проекта, без пути;
   - `WEBHOOK_SECRET` — случайная строка 16–256 символов `[A-Za-z0-9_-]`;
   - `SUPABASE_URL` и `SUPABASE_SERVICE_ROLE_KEY`;
   - `INIT_DATA_TTL_SECONDS` — по умолчанию 3600.
4. Выполнить deploy/redeploy после настройки переменных. `/api/health` должен отвечать
   `{"status":"ok"}`; это проверка приложения, не соединения с БД.
5. Production-домен должен быть доступен Telegram без Vercel login/deployment protection.
6. В локальном `.env` указать те же значения и выполнить:

```powershell
.\.venv\Scripts\python -m scripts.set_webhook
```

Скрипт зарегистрирует `/api/telegram/webhook` с секретом и кнопку меню «Мой питомец».
Затем отправить `/start` боту и открыть игру. Для Main Mini App в профиле бота можно
дополнительно задать тот же URL через `@BotFather`.

Webhook обрабатывается до ответа HTTP; long polling на Vercel не запускается.
Не назначайте production-боту случайные preview URL. При истечении авторизации
пользователь должен закрыть и заново открыть Mini App.

## API

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/health` | Проверка процесса |
| GET | `/api/pet` | Создать при первом входе / получить питомца |
| POST | `/api/pet/actions` | `{"action":"feed"}`; также `play`, `wash`, `rest` |
| PATCH | `/api/pet/name` | `{"name":"Пиксель"}` — первое имя или переименование, 1–24 символа |
| POST | `/api/telegram/webhook` | Обновления Telegram с секретным заголовком |

Игровые запросы: `Authorization: tma <Telegram.WebApp.initData>`.
ID пользователя и показатели из тела запроса не принимаются.

## Проверки

Vercel устанавливает зависимости из `pyproject.toml` и `uv.lock`.
После изменения зависимостей обновить lock-файл командой `uv lock`.
`requirements.txt` — экспорт для локального запуска через pip; обновлять его командой
`uv export --no-dev --no-hashes --no-emit-project --output-file requirements.txt`.
Для локальной установки через uv можно использовать `uv sync --locked`.

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

Тесты не требуют реальных ключей. Проверяют подпись/срок авторизации, офлайн-изменения,
награды, паузу между действиями, конфликт обновлений и доступность маршрутов.
Реальную миграцию и сквозной сценарий Telegram → Vercel → Supabase нужно проверить
после подключения сервисов.

## Следующие этапы

- Выбор вида питомца и дополнительные спрайты.
- Инвентарь, магазин, задания и баланс экономики.
- Сон по времени, уведомления отдельным запланированным заданием.
- Журнал действий и ключи идемпотентности перед добавлением покупок/валюты.
- Распределённый rate limit и мониторинг ошибок перед публичным запуском.

Сейчас сетевые ошибки не вызывают автоматический повтор действия; кнопка повторного
подключения перечитывает состояние. Webhook `/start` пока не хранит `update_id`, поэтому
повторная доставка Telegram может отправить повторное приветствие.

Архитектура сверена с документацией:
[Vercel FastAPI](https://vercel.com/docs/frameworks/backend/fastapi),
[aiogram Webhook](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html),
[Telegram Mini Apps](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app),
[Supabase API security](https://supabase.com/docs/guides/api/securing-your-api).
