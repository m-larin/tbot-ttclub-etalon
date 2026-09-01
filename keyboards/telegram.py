"""Клавиатуры для бота Telegram."""
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import Database

db = Database()

async def get_tg_tournaments_keyboard(tournaments_list, callback_prefix: str) -> InlineKeyboardMarkup:
    """Создание клавиатуры со списком турниров для Telegram."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        count = await db.get_registration_count(tournament['id'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {count} уч."
        button = InlineKeyboardButton(
            button_text,
            callback_data=f"{callback_prefix}_{tournament['id']}"
        )
        keyboard.add(button)
    return keyboard

def get_tg_group_message_markup(bot_username: str) -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой для открытия чата с ботом в Telegram."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    button = InlineKeyboardButton(
        text="📝 Регистрация тут!",
        url=f"https://t.me/{bot_username}"
    )
    keyboard.add(button)
    return keyboard

async def get_tg_cancel_registration_keyboard(registrations) -> InlineKeyboardMarkup:
    """Клавиатура для отмены регистрации в Telegram."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    for reg in registrations:
        date_obj = datetime.fromisoformat(reg['tournament_date'])
        button_text = f"{reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}) - {reg['full_name']}"
        button = InlineKeyboardButton(
            button_text,
            callback_data=f"cancel_{reg['id']}"
        )
        keyboard.add(button)

    cancel_button = InlineKeyboardButton("❌ Отмена", callback_data="cancel_all")
    keyboard.add(cancel_button)
    return keyboard
