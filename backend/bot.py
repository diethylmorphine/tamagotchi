import httpx
from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from backend.config import get_settings
from backend.reminders import ReminderRepository
from backend.repository import PetRepository

router = Router()


def pet_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Открыть питомца", web_app=WebAppInfo(url=str(get_settings().webapp_url)),
        )
    ]])


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
    await message.answer(
        "Tamagotchi-Fawn\nОткрой игру, чтобы выбрать имя и начать.\n\n"
        "Я напомню об уходе и сообщу, когда питомец выспится. "
        "Отключить напоминания: /stop. Включить снова: /start.",
        reply_markup=pet_keyboard(),
    )


@router.message(Command("stop"))
async def stop(message: Message):
    if message.chat.type != "private":
        return
    await set_reminders(message.chat.id, False)
    await message.answer("Напоминания отключены. Включить снова: /start.")


dispatcher = Dispatcher(disable_fsm=True)
dispatcher.include_router(router)
