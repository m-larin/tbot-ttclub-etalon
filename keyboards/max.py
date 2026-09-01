"""Клавиатуры для бота MAX."""
from datetime import datetime
from maxapi.types import CallbackButton, LinkButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from database.db import Database
from payloads import (
    TournamentRegistrationPayload,
    TournamentViewPayload,
    TournamentDeletePayload,
    CancelRegistrationPayload,
    CancelAllPayload,
)

db = Database()


async def get_max_tournaments_keyboard(tournaments_list, payload_class):
    """Создание клавиатуры со списком турниров для MAX."""
    builder = InlineKeyboardBuilder()

    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        count = await db.get_registration_count(tournament['id'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {count} уч."

        payload = payload_class(tournament_id=tournament['id'])

        builder.row(
            CallbackButton(
                text=button_text,
                payload=payload.pack()
            )
        )

    return builder.as_markup()


async def get_max_registration_tournaments_keyboard(tournaments_list):
    """Клавиатура для выбора турнира при регистрации в MAX."""
    return await get_max_tournaments_keyboard(tournaments_list, TournamentRegistrationPayload)


async def get_max_view_tournaments_keyboard(tournaments_list):
    """Клавиатура для выбора турнира при просмотре в MAX."""
    return await get_max_tournaments_keyboard(tournaments_list, TournamentViewPayload)


async def get_max_delete_tournaments_keyboard(tournaments_list):
    """Клавиатура для выбора турнира при удалении в MAX."""
    return await get_max_tournaments_keyboard(tournaments_list, TournamentDeletePayload)


def get_max_group_message_markup(bot_username: str):
    """Клавиатура с кнопкой для открытия чата с ботом в MAX."""
    builder = InlineKeyboardBuilder()
    url = f"https://max.ru/{bot_username}?start=help"
    builder.row(
        LinkButton(
            text="📝 Регистрация тут!",
            url=url
        )
    )
    return builder


async def get_max_cancel_registration_keyboard(registrations):
    """Клавиатура для отмены регистрации в MAX."""
    builder = InlineKeyboardBuilder()

    for reg in registrations:
        date_obj = datetime.fromisoformat(reg['tournament_date'])
        button_text = f"{reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}) - {reg['full_name']}"
        payload = CancelRegistrationPayload(registration_id=reg['id'])
        builder.row(
            CallbackButton(
                text=button_text,
                payload=payload.pack()
            )
        )

    builder.row(
        CallbackButton(
            text="❌ Отмена",
            payload=CancelAllPayload().pack()
        )
    )

    return builder.as_markup()
