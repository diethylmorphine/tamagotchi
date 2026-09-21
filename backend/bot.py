import logging

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from fastapi import HTTPException

from backend.config import get_settings
from backend.reminders import ReminderRepository
from backend.repository import PetRepository

router = Router()
logger = logging.getLogger(__name__)
DEV_CHANNEL = "https://t.me/iamdiethylmorphine"
REPORT_PROMPT = (
    "🐞 Опиши ошибку одним текстовым сообщением в ответ на это сообщение.\n\n"
    "Что ты делал, что ожидал и что произошло? "
    "Текст и твой Telegram ID будут переданы разработчику для ответа. "
    "Не отправляй пароли и другие секреты.\n\n"
    "Отмена: /cancel"
)


def pet_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Открыть питомца", web_app=WebAppInfo(url=str(get_settings().webapp_url)),
        )
    ]])


def menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        *pet_keyboard().inline_keyboard,
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="menu:notifications")],
        [InlineKeyboardButton(text="🐞 Сообщить об ошибке", callback_data="menu:report")],
        [InlineKeyboardButton(text="📢 Подписаться на канал разработчика", url=DEV_CHANNEL)],
    ])


def notification_keyboard(enabled: bool):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔕 Отключить уведомления" if enabled else "🔔 Включить уведомления",
            callback_data="notifications:off" if enabled else "notifications:on",
        ),
    ], [InlineKeyboardButton(text="← Главное меню", callback_data="menu:home")]])


async def show_menu(message: Message):
    await message.answer(
        "🐾 Твой маленький питомец\n\n"
        "Открой игру, настрой уведомления или напиши разработчику об ошибке.\n"
        "Вернуться в это меню: /menu",
        reply_markup=menu_keyboard(),
    )


async def set_reminders(user_id: int, enabled: bool):
    async with httpx.AsyncClient(timeout=10) as client:
        await PetRepository(client).get_or_create(user_id)
        await ReminderRepository(client).enable(user_id, enabled)


@router.message(CommandStart())
async def start(message: Message):
    if message.chat.type != "private":
        await message.answer("Открой личный чат со мной, чтобы завести питомца.")
        return
    await set_reminders(message.chat.id, True)
    await show_menu(message)


@router.message(Command("menu", "cancel"), F.chat.type == "private")
async def menu(message: Message):
    await show_menu(message)


async def ask_report(message: Message):
    if not get_settings().admin_telegram_ids:
        await message.answer(
            "Приём сообщений об ошибках пока не настроен. Новости — в канале разработчика.",
            reply_markup=menu_keyboard(),
        )
        return
    await message.answer(REPORT_PROMPT, reply_markup=ForceReply(
        selective=True, input_field_placeholder="Что пошло не так?",
    ))


@router.message(Command("report"), F.chat.type == "private")
async def report(message: Message):
    await ask_report(message)


@router.callback_query(F.data.in_({
    "menu:home", "menu:notifications", "menu:report", "notifications:on", "notifications:off",
}))
async def menu_action(query: CallbackQuery):
    message = query.message
    if not isinstance(message, Message) or message.chat.type != "private":
        await query.answer("Открой личный чат с ботом.", show_alert=True)
        return
    await query.answer()
    if query.data == "menu:home":
        await show_menu(message)
    elif query.data == "menu:report":
        await ask_report(message)
    else:
        try:
            if query.data in {"notifications:on", "notifications:off"}:
                enabled = query.data == "notifications:on"
                await set_reminders(query.from_user.id, enabled)
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    enabled = await ReminderRepository(client).is_enabled(query.from_user.id)
        except HTTPException:
            await message.answer("Не удалось проверить или изменить подписку. Попробуй ещё раз.")
            return
        await message.answer(
            "🔔 Уведомления включены.\nЯ напомню об уходе и сообщу, когда питомец выспится."
            if enabled else "🔕 Уведомления отключены.\nВключи их, чтобы получать напоминания.",
            reply_markup=notification_keyboard(enabled),
        )


@router.message(Command("stop"))
async def stop(message: Message):
    if message.chat.type != "private":
        return
    await set_reminders(message.chat.id, False)
    await message.answer("Напоминания отключены.", reply_markup=notification_keyboard(False))


# Commands must be registered before the general report-reply handler.
@router.message(F.chat.type == "private", F.reply_to_message.text == REPORT_PROMPT)
async def receive_report(message: Message, bot: Bot):
    original = message.reply_to_message
    if not original.from_user or original.from_user.id != bot.id:
        return
    if not message.text or len(message.text) > 3000:
        await message.answer("Нужен текст до 3000 символов. Начни заново: /report")
        return
    if message.text.startswith("/"):
        await show_menu(message)
        return
    delivered = False
    for admin_id in set(get_settings().admin_telegram_ids):
        try:
            await bot.send_message(
                admin_id,
                f"🐞 Сообщение об ошибке\nTelegram ID: {message.chat.id}\n\n{message.text}",
                parse_mode=None,
            )
            delivered = True
        except TelegramAPIError:
            logger.warning("Could not deliver a bug report to an administrator")
    await message.answer(
        "Спасибо! Сообщение об ошибке отправлено разработчику."
        if delivered else "Не удалось отправить сообщение разработчику. Попробуй позже: /report",
        reply_markup=menu_keyboard(),
    )


dispatcher = Dispatcher(disable_fsm=True)
dispatcher.include_router(router)
