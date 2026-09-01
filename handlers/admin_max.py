"""Административные обработчики MAX: создание и удаление турниров."""
import logging
from datetime import datetime
from maxapi import Router
from maxapi.filters.command import Command
from maxapi.types import MessageCreated, MessageCallback, BotAdded
from maxapi.context import MemoryContext
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types import CallbackButton
from states.registration import TournamentStates
from keyboards.max import (
    get_max_delete_tournaments_keyboard,
    get_max_group_message_markup,
)
from payloads import TournamentDeletePayload, TournamentDeleteConfirmPayload, DeleteCancelPayload
from handlers.common import (
    is_admin,
    notify_group_from_max,
    get_tournament_or_notify,
    get_tournaments_or_notify,
)
from context import get_max_bot, get_max_username, get_db

logger = logging.getLogger(__name__)
router = Router()

def register_handlers():
    """Регистрация обработчиков."""
    logger.info("✅ Admin MAX handlers registered")

@router.bot_added()
async def on_bot_added(event: BotAdded):
    """Бот добавлен в группу."""
    chat_id = event.chat_id
    bot = get_max_bot()
    username = get_max_username()

    logger.info("🤖 Бот добавлен в чат: %s", chat_id)

    keyboard = get_max_group_message_markup(username)

    await bot.send_message(
        chat_id=chat_id,
        text=f"✅ Бот добавлен в чат!\n📌 ID: {chat_id}",
        attachments=[keyboard.as_markup()]
    )

@router.message_created(Command("add_tournament"))
async def cmd_add_tournament(event: MessageCreated, context: MemoryContext):
    """Добавление турнира."""
    user = event.from_user
    if not is_admin(user.user_id):
        await event.message.answer("⛔ У вас нет прав.")
        return

    await context.set_state(TournamentStates.waiting_for_name)
    await event.message.answer("Введите название турнира:")

@router.message_created(TournamentStates.waiting_for_name)
async def process_tournament_name(event: MessageCreated, context: MemoryContext):
    """Обработка названия турнира."""
    user = event.from_user
    if not is_admin(user.user_id):
        await context.clear()
        await event.message.answer("⛔ У вас нет прав.")
        return

    await context.update_data(tournament_name=event.message.body.text)
    await context.set_state(TournamentStates.waiting_for_date)
    await event.message.answer("Введите дату (ДД.ММ.ГГГГ):")

@router.message_created(TournamentStates.waiting_for_date)
async def process_tournament_date(event: MessageCreated, context: MemoryContext):
    """Обработка даты турнира."""
    user = event.from_user
    if not is_admin(user.user_id):
        await context.clear()
        await event.message.answer("⛔ У вас нет прав.")
        return

    try:
        date_str = event.message.body.text
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        date_iso = datetime.combine(date_obj.date(), datetime.min.time()).isoformat()

        data = await context.get_data()
        tournament_name = data.get('tournament_name', 'Турнир')

        db = get_db()
        tournament_id = await db.add_tournament(tournament_name, date_iso, user.user_id)

        if tournament_id == 0:
            await event.message.answer("❌ Ошибка создания турнира.")
            return

        await event.message.answer(f"✅ Турнир '{tournament_name}' на {date_str} добавлен!")
        await context.clear()

        # Текст уведомления
        text = f"📢 <b>Началась запись на турнир!</b>\n\n🏆 {tournament_name}\n📅 {date_str}"

        # Отправляем в оба мессенджера
        await notify_group_from_max(text)

        logger.info("✅ Уведомление отправлено в оба мессенджера для турнира '%s'", tournament_name)

    except ValueError:
        await event.message.answer("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    except Exception as e:
        logger.error("❌ Ошибка: %s", e)
        await event.message.answer("❌ Произошла ошибка при создании турнира.")

@router.message_created(Command("delete_tournament"))
async def cmd_delete_tournament(event: MessageCreated):
    """Удаление турнира."""
    user = event.from_user
    if not is_admin(user.user_id):
        await event.message.answer("⛔ У вас нет прав.")
        return

    tournaments = await get_tournaments_or_notify(event, "Нет активных турниров.")
    if not tournaments:
        return

    keyboard = await get_max_delete_tournaments_keyboard(tournaments)
    await event.message.answer("Выберите турнир:", attachments=[keyboard])

@router.message_callback(TournamentDeletePayload.filter())
async def process_delete_selection(event: MessageCallback, payload: TournamentDeletePayload):
    """Запрос подтверждения удаления."""
    user = event.from_user
    if not is_admin(user.user_id):
        await event.answer("⛔ У вас нет прав.")
        return

    bot = get_max_bot()

    tournament = await get_tournament_or_notify(event, payload.tournament_id)
    if not tournament:
        return

    confirm_payload = TournamentDeleteConfirmPayload(tournament_id=payload.tournament_id)
    cancel_payload = DeleteCancelPayload()

    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(text="✅ Да, удалить", payload=confirm_payload.pack()),
        CallbackButton(text="❌ Отмена", payload=cancel_payload.pack()),
    )

    await event.answer("❓ Подтвердите удаление.")
    await bot.send_message(
        chat_id=event.chat.chat_id,
        text=f"⚠️ Удалить '{tournament['name']}'?",
        attachments=[builder.as_markup()]
    )

@router.message_callback(TournamentDeleteConfirmPayload.filter())
async def process_delete_confirm(event: MessageCallback, payload: TournamentDeleteConfirmPayload):
    """Подтверждение удаления."""
    user = event.from_user
    if not is_admin(user.user_id):
        await event.answer("⛔ У вас нет прав.")
        return

    db = get_db()
    bot = get_max_bot()

    tournament = await db.get_tournament(payload.tournament_id)
    if tournament:
        await db.delete_tournament(payload.tournament_id)
        await event.answer("✅ Турнир удален!")
        await bot.send_message(
            chat_id=event.chat.chat_id,
            text=f"✅ Турнир '{tournament['name']}' удален."
        )
        logger.info("Админ %s удалил турнир '%s'", user.user_id, tournament['name'])
    else:
        await event.answer("❌ Турнир не найден.")

@router.message_callback(DeleteCancelPayload.filter())
async def process_delete_cancel(event: MessageCallback):
    """Отмена удаления."""
    bot = get_max_bot()
    await event.answer("❌ Отменено.")
    await bot.send_message(
        chat_id=event.chat.chat_id,
        text="❌ Удаление отменено."
    )
