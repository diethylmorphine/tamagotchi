from aiogram import Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from backend.config import get_settings

router = Router()


@router.message(CommandStart())
async def start(message: Message):
    if message.chat.type != "private":
        await message.answer("Открой личный чат со мной, чтобы завести питомца.")
        return
    await message.answer(
        "Твой Моти ждёт! Корми, играй, купай и помогай ему отдыхать 🐣",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Открыть питомца",
                web_app=WebAppInfo(url=str(get_settings().webapp_url)),
            )
        ]]),
    )


dispatcher = Dispatcher(disable_fsm=True)
dispatcher.include_router(router)

