---
title: План развития Tamagotchi FWN
status: Draft
version: 1
date: 2026-09-12
related: [docs/specs/2026-09-12-0206-daily-pet-progression.md, docs/specs/2026-09-12-0206-exploration-room-collection.md, docs/adr/0001-atomic-game-rewards.md, docs/research/2026-09-12-0206-feature-opportunities-review.md]
---

# План развития Tamagotchi FWN

Сначала выпустить реакции и цели, затем безопасные награды, после них прогулки и комнату.

Goal: Добавить реакции, вехи и ежедневные задания без потери текущего прогресса.

Architecture: Чистые правила Python, серверная авторизация, атомарные транзакции Postgres, HTML/CSS/JS без сборки.

Tech Stack: FastAPI, aiogram 3, Supabase Postgres, Vercel, vanilla JavaScript.

Global Constraints: Сервер определяет время и награды; один питомец на Telegram ID; питомец не умирает; сон сохраняет текущие правила; миграции аддитивные; существующие незакоммиченные изменения сохраняются.

## Контекст и карта переиспользования

План описывает будущее внедрение, не выполненную реализацию. Сначала прочитать [спецификацию A](../specs/2026-09-12-0206-daily-pet-progression.md), [спецификацию B](../specs/2026-09-12-0206-exploration-room-collection.md) и [ADR](../adr/0001-atomic-game-rewards.md). Приступая к коду, сверить сигнатуры и рабочий diff: параллельно изменяются сон и рейтинг.

| Файл | Что переиспользовать |
|---|---|
| `backend/game.py` | Pet, evolve, act, sleep_remaining, present |
| `backend/repository.py` | PetRepository, HTTP-обработка ошибок, version |
| `backend/auth.py` | telegram_user, admin_user |
| `main.py` | зависимости API, repository, текущие маршруты |
| `frontend/assets/app.js` | request, render, run, sync, диалоги |
| `frontend/index.html`, `frontend/assets/style.css` | экран, уход, визуальная тема |
| `tests/test_game.py`, `tests/test_api.py`, `tests/test_admin.py` | pure-rule тесты, dependency overrides, конфликты |
| `supabase/migrations/` | аддитивные миграции и закрытые права |

Вести ровно одну задачу в состоянии `[wip]`, отмечать её шаги сразу после выполнения. Маркеры: `[ ]`, `[wip]`, `[x]`, `[f]`. После неудачной проверки исправить причину и повторить её до перехода дальше. Коммиты и deployment выполняются только в рамках отдельного запроса пользователя. Номера новых миграций выбрать после сверки последнего занятого номера.

## Очерёдность

| Выпуск | Задачи | Ориентир для одного разработчика | Условие готовности |
|---|---|---|---|
| A0: питомец оживает | A1-A2 | 2-3 дня | Реакции и вехи работают на текущем pet |
| A1: ежедневные цели | A3-A6 | 7-11 дней | Пройдены реальные транзакционные тесты |
| B: исследование и комната | B1-B3 | 8-12 дней | Прогулка, находка, покупка и установка проходят сквозной сценарий |

Оценки не являются обещанием сроков, не включают ожидание инфраструктуры и создание полного комплекта арта. A0 можно выпускать независимо. A3 предшествует A4, A4 предшествует A5; A6 завершает A1. B1 и B2 требуют A6; B3 завершает B.

## A1. Реакции состояния

Files: Modify `backend/game.py`, `frontend/assets/app.js`, `frontend/assets/style.css`, `frontend/index.html`; Test `tests/test_game.py`.

Interfaces: consumes Pet, datetime; produces `mood: str` в present. Детерминированное правило новой функции:

```python
def mood_for(pet: Pet, now: datetime) -> str:
    current = evolve(pet, now)
    if sleep_remaining(current, now) > 0:
        return "sleeping"
    needs = (("satiety", "hungry"), ("energy", "tired"),
             ("hygiene", "dirty"), ("happiness", "lonely"))
    stat, mood = min(needs, key=lambda item: getattr(current, item[0]))
    if getattr(current, stat) < 30:
        return mood
    return "happy" if all(getattr(current, s) >= 70 for s, _ in needs) else "calm"
```

- [ ] Добавить тесты сна, ничьих и порогов 29.9/30/70; увидеть отказ без реализации.
- [ ] Добавить mood_for и поле mood в present, отобразить подпись и состояние спрайта.
- [ ] Проверить reduced-motion и текстовую доступность вручную в браузере.
- [ ] Запустить `python -m pytest tests/test_game.py`; устранить ошибки до перехода.

Результат: питомец объясняет текущую потребность, сон имеет высший приоритет.

## A2. Вехи развития

Files: Modify `backend/game.py`, `frontend/assets/app.js`, `frontend/index.html`; Test `tests/test_game.py`.

Interfaces: consumes xp:int; produces current_title:str, next_milestone:dict|None. Добавить точные данные:

```python
MILESTONES = ((2, "Знакомые"), (5, "Друзья"), (10, "Неразлучные"))
```

- [ ] Написать тесты xp=0/99/100/399/400/899/900 и административного снижения уровня.
- [ ] Вычислить текущий титул как последний доступный, до уровня 2 использовать «Первая встреча»; xp_remaining = (target_level - 1) * 100 - xp.
- [ ] Показать следующую цель; после уровня 10 показать завершение всех вех.
- [ ] Прогнать `python -m pytest tests/test_game.py tests/test_admin.py`; исправить отказы.

Результат: существующие игроки видят свои вехи без миграции и повторных выплат.

## A3. Атомарные действия и ключи запросов

Files: Create `backend/progression.py`, новые SQL-миграции, `tests/test_progression_transactions.py`; Modify `backend/repository.py`, `main.py`; Test `tests/test_api.py`.

Interfaces: `commit_action(pet: Pet, previous_version: int, key: UUID, payload_hash: str) -> dict | None`; None означает конфликт версии, dict содержит сохранённый ответ. Новый RPC `commit_pet_action` принимает только серверные параметры. `get_request_result(user_id: int, key: UUID, payload_hash: str) -> dict | None` вызывается до act; mismatch даёт 409. RPC повторно проверяет ключ внутри транзакции.

- [ ] Написать интеграционные тесты для таблиц и атомарности из спецификации A на отдельном тестовом Postgres.
- [ ] Добавить таблицы, уникальные ограничения, RLS, права service_role и RPC; хранить полный успешный ответ.
- [ ] Встроить RPC в actions, сохранив цикл повторного чтения при version-конфликте и существующие проверки act.
- [ ] Проверить rollback при ошибке между записью события и прогресса, два конкурентных запроса, replay после потери ответа, несовпадение payload.
- [ ] Запустить `python -m pytest tests/test_api.py tests/test_progression_transactions.py` с тестовой БД; исправить ошибки. Пропущенные DB-тесты не считаются успехом.

Результат: одно намерение даёт одно действие, один event и одну запись дневного прогресса.

## A4. Задания и получение листочков

Files: Modify `backend/progression.py`, `backend/repository.py`, `main.py`; Create `tests/test_progression.py`; Test `tests/test_progression_transactions.py`.

Interfaces: GET /api/progression и POST /api/progression/claims по спецификации A; RPC `claim_daily_reward`. Код исходных правил:

```python
TASKS = {"care_once": (1, 5), "care_variety": (2, 10), "care_three": (3, 10)}
ACTION_BITS = {"feed": 1, "play": 2, "wash": 4, "rest": 8}

def task_progress(task_id: str, count: int, mask: int) -> int:
    target, _ = TASKS[task_id]
    return min(target, mask.bit_count() if task_id == "care_variety" else count)
```

- [ ] Написать проверки UTC-полуночи, rest, исключения отказов/тиков/админки, суммарных 25 листочков.
- [ ] Добавить чтение прогресса и списка прошлых дней с неполученными наградами; пустой день возвращает нули.
- [ ] Реализовать атомарный claim с проверкой завершения и уникальности владельца/дня/task_id.
- [ ] Проверить два разных ключа для одной задачи, чужого владельца, вчерашний claim и баланс после таймаута.
- [ ] Запустить тесты progression и транзакций, исправить ошибки до перехода.

Результат: за один календарный UTC-день невозможно получить больше 25 листочков за эти задания.

## A5. Экран заданий и безопасный повтор

Files: Modify `frontend/index.html`, `frontend/assets/app.js`, `frontend/assets/style.css`.

Interfaces: прежний request расширяется заголовком Idempotency-Key; pending хранит key, method, path, body и владельца текущей сессии. UUID создаётся через `crypto.randomUUID()`.

- [ ] Добавить карточки заданий, баланс, UTC-сброс и неполученные награды прошлых дней.
- [ ] Добавить сохранение pending перед отправкой и повтор того же намерения; очистить после подтверждения, исключить отправку pending другого аккаунта.
- [ ] После replay перечитать pet и progression, сохранив текущие диалоги сна и рейтинга.
- [ ] Проверить вручную потерю сети, перезагрузку, двойной клик, смену дня и 401; при ошибке исправить и повторить сценарий.

Результат: понятный экран с восстановлением после неопределённого результата запроса.

## A6. Проверка и подготовка выпуска A

Files: Modify `README.md`; Test `tests/`, SQL-миграции и frontend.

Interfaces: существующие API и новые API A; входные старые строки pets должны оставаться совместимыми.

- [ ] Применить миграции на тестовой копии данных, проверить сохранность имён, XP, sleep_started_at и профилей.
- [ ] Выполнить `.\.venv\Scripts\python -m pytest` и `.\.venv\Scripts\python -m ruff check .`, устранить отказы.
- [ ] Выполнить реальные DB-тесты и ручной Telegram-сценарий: вход, уход, сон, задания, claim, повтор после таймаута, администрирование, рейтинг.
- [ ] Добавить минимальное серверное событие session_open для оценки возвратов; исключить админские действия из отчётов, проверить дедупликацию сессии.
- [ ] Описать порядок migration-before-code, обязательное обновление клиента и отключение новых кнопок при откате backend; additive-таблицы при откате сохранять.

Результат: проверенный кандидат выпуска; production-развёртывание не является частью планирования.

## B1. Прогулки и альбом

Files: Create `backend/expeditions.py`, `tests/test_expeditions.py`, миграция expeditions/collection_items; Modify repository, game, main, frontend.

Interfaces: start/current/claim по спецификации B; состояния active/ready/claimed, серверные start/end. Константы: `EXPEDITION_SECONDS = 900`, `EXPEDITION_ENERGY_COST = 10`.

- [ ] Добавить тесты уровня и потребностей, границ времени, гонки sleep/start и повторного claim.
- [ ] Реализовать транзакционный start с проверкой pet.version и взаимоисключением активностей; выбрать reward_id при старте.
- [ ] Реализовать claim с уникальным событием expedition_claim, коллекцию и возврат без cron.
- [ ] Добавить таймер, альбом из шести находок, текстовые состояния.
- [ ] Прогнать тесты expeditions вместе с game и DB-конкуренцией; исправить отказы.

Результат: прогулка продолжается офлайн и выдаёт ровно одну находку.

## B2. Каталог и комната

Files: Create `backend/shop.py`, `tests/test_shop.py`, миграция owned_decor/room_slots; Modify repository, main, frontend.

Interfaces: GET /api/room, POST /api/shop/purchases, PATCH /api/room по спецификации B; RPC `purchase_decor`. Цена определяется серверным каталогом из шести ID.

- [ ] Добавить тесты нехватки средств, повторной покупки, параллельных расходов и чужого предмета.
- [ ] Реализовать покупку: кошелёк блокируется до проверки баланса, списание и владение сохраняются атомарно.
- [ ] Реализовать установку предмета по слоту, бесплатный default и чтение комнаты.
- [ ] Прогнать shop и транзакционные тесты; устранить ошибки.

Результат: баланс не уходит в минус, купленный предмет сохраняется после повторного входа.

## B3. Оформление и сквозная проверка B

Files: Create SVG-ассеты декора и находок в `frontend/assets/`; Modify frontend и README.

Interfaces: UI вкладок Питомец/Альбом/Комната, существующий API B.

- [ ] Создать шесть находок и шесть украшений в текущем пиксельном стиле, подключить доступные названия и состояния.
- [ ] Проверить узкий Telegram WebView, reduced-motion, отсутствие горизонтальной прокрутки, возврат из фона.
- [ ] Пройти полный путь: задания, листочки, покупка, установка, прогулка, офлайн-возврат, находка.
- [ ] Запустить всю регрессию и DB-тесты, исправить отказы, описать выпуск и откат.

Результат: коллекция и комната работают с реальными сохранениями.

## Проверка результата и самопроверка

- [ ] Каждое правило спецификаций A/B покрыто соответствующей задачей и проверкой.
- [ ] Ни один клиентский параметр не определяет владельца, цену, время или награду.
- [ ] Сон, рейтинг, имя и администрирование сохраняют поведение.
- [ ] Параллельные запросы и потеря ответа проверены на реальной тестовой БД.
- [ ] Пользовательский прогресс сохраняется при миграции и откате приложения.

После тестовой недели оценить долю вернувшихся на следующий день игроков, долю получивших хотя бы одну награду и долю завершивших первую прогулку. До измерения добавить минимальные серверные события session_open и expedition_claim; game_events/reward_claims уже дают данные ухода и выплат. Админские действия исключаются. Это будущая оценка гипотез, исходных метрик пока нет; не заявлять рост удержания без измерений.

Следующие кандидаты P3 описаны в [анализе](../research/2026-09-12-0206-feature-opportunities-review.md); они не входят в обязательства A/B. Stardust registry пропущен: CLI недоступен, применён разрешённый workflow без CLI.
