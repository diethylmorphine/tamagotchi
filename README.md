# Tamagotchi-Fawn

Telegram Mini App virtual pet game built with FastAPI, aiogram, Supabase Postgres, and a plain HTML/CSS/JavaScript frontend.

## Preview

<!-- TODO: add an up-to-date screenshot or GIF of the game here. -->

## Tech stack

- Python 3.12+, FastAPI, aiogram 3
- Supabase Postgres via its REST API
- HTML, CSS, and JavaScript (no frontend build step)
- Vercel deployment

## Quick start

- [Local setup](#run-locally)
- [Supabase setup](#configure-supabase)
- [Tests and lint](#checks)
- [Project history and known limitations](docs/CHANGELOG.md)
- [Deployment and Telegram webhook](docs/releases/2026-09-21-pets.md)
- [Detailed project and operations guide](docs/README.md)

## Run locally

Use a separate test bot: registering a webhook replaces the current webhook for that bot. A real Mini App session also needs a reachable HTTPS URL and a Supabase project.

1. Create a bot with `@BotFather` and a Supabase project. Apply every migration in `supabase/migrations/` in filename order in the Supabase SQL Editor.
2. Create a virtual environment and install the development dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

3. Copy `.env.example` to `.env`; set `BOT_TOKEN`, `WEBAPP_URL`, `WEBHOOK_SECRET`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`. Use a random webhook secret with at least 16 characters. Add Telegram admin IDs only if testing admin tools.
4. Start the app:

   ```powershell
   .\.venv\Scripts\python -m uvicorn main:app --reload
   ```

5. Open `http://127.0.0.1:8000` to see the shell. Outside Telegram, gameplay requests cannot authenticate: for a real game session, expose port 8000 through an HTTPS tunnel, set its address as `WEBAPP_URL`, then register the webhook/menu with `python -m scripts.set_webhook`.

### What requires external services

- A valid Telegram `initData` and Telegram bot are required for authenticated gameplay and webhook handling.
- A Supabase project with the migrations applied is required to persist pets and profiles.
- HTTPS tunneling is required for Telegram to open the local Mini App and deliver webhooks.
- Reminder delivery additionally requires the configured `CRON_SECRET` and the scheduled Supabase `pg_cron`/`pg_net` setup documented in [the operations guide](docs/README.md).
- Without those services, the local page shell and automated unit tests work, but there is no end-to-end playable account.

## Data & Privacy

- On authenticated sessions, the backend records a player's Telegram ID, first and last name, username, pet name, pet state, XP, and reminder preferences in Supabase. Telegram IDs identify the pet record; profile fields are refreshed from verified Telegram `initData`.
- A user-submitted bug report contains the report text and Telegram ID and is sent to the Telegram IDs configured in `ADMIN_TELEGRAM_IDS`. Reports are not stored in the app database.
- The repository has no self-service account deletion endpoint. To delete a user's app data, an operator with Supabase access can delete that row in `public.pets`; `public.pet_reminders` references it with `ON DELETE CASCADE`. Use the SQL Editor and substitute the user's numeric Telegram ID:

  ```sql
  delete from public.pets where telegram_id = 123456789;
  ```

- Telegram's own messages and data retained by Telegram are outside this database deletion.

## Checks

The test suite uses mocked services and does not need real credentials:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m ruff check .
```

## Project notes

- Server time determines game actions and rewards. Pet state is recalculated on read and persisted on actions; conditional `version` updates prevent concurrent requests from silently overwriting one another.
- Planned work and known limitations are listed in [the detailed guide](docs/README.md). Historical release notes are in [docs/releases](docs/releases/).
