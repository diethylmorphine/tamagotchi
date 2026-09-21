import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User

from backend import bot as handlers


def message(text="/start", reply=None):
    return Message(
        message_id=10, date=datetime.now(UTC), chat=Chat(id=7, type="private"),
        from_user=User(id=7, is_bot=False, first_name="Игрок"),
        text=text, reply_to_message=reply,
    )


def configure(monkeypatch):
    monkeypatch.setattr(handlers, "get_settings", lambda: SimpleNamespace(
        webapp_url="https://example.com", admin_telegram_ids=[11, 12],
    ))
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    return answer


def test_start_opens_russian_menu_and_menu_does_not_reenable(monkeypatch):
    answer = configure(monkeypatch)
    settings = AsyncMock()
    monkeypatch.setattr(handlers, "set_reminders", settings)
    asyncio.run(handlers.start(message()))
    settings.assert_awaited_once_with(7, True)
    rows = answer.call_args.kwargs["reply_markup"].inline_keyboard
    assert rows[0][0].web_app.url == "https://example.com"
    assert rows[1][0].callback_data == "menu:notifications"
    assert rows[2][0].callback_data == "menu:report"
    assert rows[3][0].url == "https://t.me/iamdiethylmorphine"
    asyncio.run(handlers.menu(message("/menu")))
    assert settings.await_count == 1


def test_notification_buttons_save_explicit_state_for_sender(monkeypatch):
    answer = configure(monkeypatch)
    settings = AsyncMock()
    monkeypatch.setattr(handlers, "set_reminders", settings)
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())
    for data, enabled, next_action in (
        ("notifications:off", False, "notifications:on"),
        ("notifications:on", True, "notifications:off"),
    ):
        query = CallbackQuery(
            id="callback", from_user=message().from_user, chat_instance="chat",
            message=message(), data=data,
        )
        asyncio.run(handlers.menu_action(query))
        settings.assert_awaited_with(7, enabled)
        keyboard = answer.call_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].callback_data == next_action


def report_message(text="Не работает кнопка", author=99):
    prompt = message(handlers.REPORT_PROMPT).model_copy(update={
        "from_user": User(id=author, is_bot=True, first_name="Питомец"),
    })
    return message(text, reply=prompt)


def test_report_reaches_admin_when_another_admin_blocks_bot(monkeypatch):
    answer = configure(monkeypatch)
    bot = SimpleNamespace(id=99, send_message=AsyncMock(side_effect=[
        TelegramForbiddenError(method=SendMessage(chat_id=11, text="test"), message="blocked"),
        None,
    ]))
    asyncio.run(handlers.receive_report(report_message(), bot))
    assert bot.send_message.await_count == 2
    assert "Telegram ID: 7" in bot.send_message.call_args.args[1]
    assert "отправлено" in answer.call_args.args[0]


def test_report_failure_does_not_claim_success(monkeypatch):
    answer = configure(monkeypatch)
    bot = SimpleNamespace(id=99, send_message=AsyncMock(side_effect=TelegramForbiddenError(
        method=SendMessage(chat_id=11, text="test"), message="blocked",
    )))
    asyncio.run(handlers.receive_report(report_message(), bot))
    assert "Не удалось" in answer.call_args.args[0]


def test_reports_require_bot_prompt_and_valid_text(monkeypatch):
    configure(monkeypatch)
    bot = SimpleNamespace(id=99, send_message=AsyncMock())
    for incoming in (
        report_message(author=77), report_message("/cancel"), report_message("x" * 3001),
    ):
        asyncio.run(handlers.receive_report(incoming, bot))
    bot.send_message.assert_not_awaited()


@pytest.mark.parametrize("command, subscription", [
    ("/stop", False), ("/start", True), ("/menu", None), ("/cancel", None), ("/report", None),
])
def test_commands_replying_to_report_prompt_keep_their_routing(monkeypatch, command, subscription):
    answer = configure(monkeypatch)
    settings = AsyncMock()
    delivery = AsyncMock()
    monkeypatch.setattr(handlers, "set_reminders", settings)
    monkeypatch.setattr(Bot, "send_message", delivery)
    incoming = report_message(command).model_copy(update={
        "entities": [MessageEntity(type="bot_command", offset=0, length=len(command))],
    })

    async def run():
        async with Bot(token="99:" + "a" * 35) as bot:
            await handlers.dispatcher.feed_update(bot, Update(update_id=1, message=incoming))

    asyncio.run(run())
    delivery.assert_not_awaited()
    if subscription is None:
        settings.assert_not_awaited()
    else:
        settings.assert_awaited_once_with(7, subscription)
    assert answer.await_count == 1
    if command == "/stop":
        assert "отключены" in answer.call_args.args[0]
    elif command == "/report":
        assert answer.call_args.args[0] == handlers.REPORT_PROMPT
    else:
        assert "Твой маленький питомец" in answer.call_args.args[0]
