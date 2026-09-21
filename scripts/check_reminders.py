"""Read-only delivery diagnostics. Never sends messages or prints credentials."""

import asyncio
import json

import httpx

from backend.config import get_settings


async def main():
    try:
        settings = get_settings()
    except Exception:
        print("Configuration is missing or invalid; check .env against .env.example.")
        return
    token = settings.bot_token.get_secret_value()
    placeholder = "replace" in token or token.startswith("123456:")
    print(json.dumps({
        "local_bot_token_configured": not placeholder,
        "local_cron_secret_configured": bool(settings.cron_secret),
    }))
    if placeholder:
        print("Set real local credentials before checking the deployed services.")
        return
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
            result = response.json().get("result", {})
            print(json.dumps({
                "telegram_http": response.status_code,
                "webhook_set": bool(result.get("url")),
                "webhook_matches_app": result.get("url", "").rstrip("/") ==
                str(settings.webapp_url).rstrip("/") + "/api/telegram/webhook",
                "pending_updates": result.get("pending_update_count"),
                "webhook_has_error": bool(result.get("last_error_message")),
            }))
        except (httpx.HTTPError, ValueError):
            print("Telegram diagnostic request failed.")
        key = settings.supabase_service_role_key.get_secret_value()
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        for table, select in (
            ("pets", "name_chosen,species"),
            ("pet_reminders", "enabled,last_care_at,sleep_notified_at"),
        ):
            try:
                response = await client.get(
                    str(settings.supabase_url).rstrip("/") + "/rest/v1/" + table,
                    headers=headers, params={"select": select, "limit": "1000"},
                )
                report = {"table": table, "http": response.status_code}
                if response.is_success:
                    rows = response.json()
                    report["rows_up_to_1000"] = len(rows)
                    if table == "pets":
                        report["named"] = sum(row["name_chosen"] for row in rows)
                    else:
                        report["enabled"] = sum(row["enabled"] for row in rows)
                        report["ever_claimed"] = sum(
                            bool(row["last_care_at"] or row["sleep_notified_at"]) for row in rows
                        )
                print(json.dumps(report))
            except (httpx.HTTPError, ValueError):
                print(f"{table} diagnostic request failed.")
        try:
            response = await client.get(str(settings.webapp_url).rstrip("/") + "/api/health")
            print(json.dumps({"production_health_http": response.status_code}))
        except httpx.HTTPError:
            print("Production health check failed.")
    print("Check scheduler runs separately with scripts/diagnose_reminders.sql in Supabase.")


if __name__ == "__main__":
    asyncio.run(main())
