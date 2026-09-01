"""Обработчики регистрации и отмены регистрации на турниры для MAX."""
import logging
from maxapi import Router
from maxapi.filters.command import Command
from maxapi.types import MessageCreated, MessageCallback
from maxapi.context import MemoryContext
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types import CallbackButton
from states.registration import RegistrationStates, CancelStates
from keyboards.max import (
    get_max_registration_tournaments_keyboard,
    get_max_view_tournaments_keyboard,
    get_max_cancel_registration_keyboard,
)
from payloads import (
    TournamentRegistrationPayload,
    TournamentViewPayload,
    CancelRegistrationPayload,
    CancelConfirmPayload,
    CancelAllPayload,
)
from handlers.common import (
    format_registration_confirmation,
    format_participants_list,
    format_user_registrations,
    format_participants_update_text,
    notify_group_from_max,
    get_tournament_or_notify,
    get_tournaments_or_notify,
    log_user_action,
)
from context import get_max_bot, get_db

logger = logging.getLogger(__name__)
router = Router()

def register_handlers():
    """Регистрация обработчиков."""
    logger.info("✅ Registration MAX handlers registered")

@router.message_created(Command("register"))
async def cmd_register(event: MessageCreated):
    """Регистрация участника."""
    tournaments = await get_tournaments_or_notify(event, "📭 Нет активных турниров.")
    log_user_action(event.from_user, "register_command", {"tournaments_count": len(tournaments) if tournaments else 0})
    if not tournaments:
        return

    keyboard = await get_max_registration_tournaments_keyboard(tournaments)
    await event.message.answer("🏆 Выберите турнир:", attachments=[keyboard])

@router.message_callback(TournamentRegistrationPayload.filter())
async def process_registration_tournament(
    event: MessageCallback, payload: TournamentRegistrationPayload, context: MemoryContext
):
    """Выбор турнира для регистрации."""
    bot = get_max_bot()

    tournament = await get_tournament_or_notify(event, payload.tournament_id)
    if not tournament:
        log_user_action(event.from_user, "register_failed_tournament_not_found", {
            "tournament_id": payload.tournament_id
        })
        return

    log_user_action(event.from_user, "register_new_participant_start", {
        "tournament_id": payload.tournament_id,
        "tournament_name": tournament['name'],
    })

    await context.update_data(tournament_id=payload.tournament_id)
    await context.set_state(RegistrationStates.waiting_for_full_name)

    await event.answer("✅ Турнир выбран!")
    await bot.send_message(
        chat_id=event.chat.chat_id,
        text="Введите ФИО участника:"
    )

@router.message_created(RegistrationStates.waiting_for_full_name)
async def process_full_name(event: MessageCreated, context: MemoryContext):
    """Ввод ФИО."""
    full_name = event.message.body.text.strip()
    if not full_name or len(full_name) < 2:
        await event.message.answer("❌ Введите корректное ФИО.")
        return

    await context.update_data(full_name=full_name)
    await context.set_state(RegistrationStates.waiting_for_city)
    log_user_action(event.from_user, "participant_data_entered", {"field": "full_name"})
    await event.message.answer("Введите город:")

@router.message_created(RegistrationStates.waiting_for_city)
async def process_city(event: MessageCreated, context: MemoryContext):
    """Ввод города и завершение регистрации."""
    city = event.message.body.text.strip()
    if not city or len(city) < 2:
        await event.message.answer("❌ Введите корректный город.")
        return

    data = await context.get_data()
    tournament_id = data.get('tournament_id')
    full_name = data.get('full_name')

    if not tournament_id or not full_name:
        await event.message.answer("❌ Ошибка. Начните заново /register")
        await context.clear()
        return

    db = get_db()

    success = await db.register_participant(tournament_id, event.from_user.user_id, full_name, city)

    if success:
        tournament = await db.get_tournament(tournament_id)
        log_user_action(event.from_user, "registration_complete", {
            "tournament_id": tournament_id,
            "tournament_name": tournament['name'],
            "participant_name": full_name,
        })
        await event.message.answer(format_registration_confirmation(tournament, full_name, city))

        # Отправляем обновление в оба мессенджера
        participants = await db.get_participants(tournament_id)
        text = format_participants_update_text(tournament, participants)
        await notify_group_from_max(text)
    else:
        log_user_action(event.from_user, "registration_failed_db_error")
        await event.message.answer("❌ Ошибка регистрации.")

    await context.clear()

@router.message_created(Command("participants"))
async def cmd_participants(event: MessageCreated):
    """Просмотр участников."""
    tournaments = await get_tournaments_or_notify(event, "Нет активных турниров.")
    log_user_action(event.from_user, "participants_command", {
        "tournaments_count": len(tournaments) if tournaments else 0
    })
    if not tournaments:
        return

    keyboard = await get_max_view_tournaments_keyboard(tournaments)
    await event.message.answer("👥 Выберите турнир:", attachments=[keyboard])

@router.message_callback(TournamentViewPayload.filter())
async def process_view_participants(event: MessageCallback, payload: TournamentViewPayload):
    """Показать участников."""
    bot = get_max_bot()

    tournament = await get_tournament_or_notify(event, payload.tournament_id)
    if not tournament:
        return

    log_user_action(event.from_user, "view_participants", {
        "tournament_id": payload.tournament_id,
        "tournament_name": tournament['name'],
    })

    db = get_db()
    participants = await db.get_participants(payload.tournament_id)
    text = format_participants_list(tournament, participants)

    await event.answer("👥 Список готов!")
    await bot.send_message(chat_id=event.chat.chat_id, text=text)

@router.message_created(Command("my_registrations"))
async def cmd_my_registrations(event: MessageCreated):
    """Мои регистрации."""
    db = get_db()
    registrations = await db.get_user_registrations(event.from_user.user_id)
    log_user_action(event.from_user, "my_registrations_command", {"registrations_count": len(registrations)})
    if not registrations:
        await event.message.answer("📭 Вы еще никого не зарегистрировали.")
        return

    text = format_user_registrations(registrations)
    await event.message.answer(text)

@router.message_created(Command("cancel_registration"))
async def cmd_cancel_registration(event: MessageCreated):
    """Отмена регистрации."""
    db = get_db()
    registrations = await db.get_user_registrations(event.from_user.user_id)
    log_user_action(event.from_user, "cancel_registration_start", {"registrations_count": len(registrations)})
    if not registrations:
        await event.message.answer("📭 Нет активных регистраций.")
        return

    keyboard = await get_max_cancel_registration_keyboard(registrations)
    await event.message.answer("Выберите регистрацию:", attachments=[keyboard])

@router.message_callback(CancelRegistrationPayload.filter())
async def process_cancel_selection(event: MessageCallback, payload: CancelRegistrationPayload, context: MemoryContext):
    """Начало отмены."""
    bot = get_max_bot()

    await context.update_data(registration_id=payload.registration_id)
    await context.set_state(CancelStates.confirming)

    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(
            text="✅ Да, отменить",
            payload=CancelConfirmPayload(registration_id=payload.registration_id).pack()
        ),
        CallbackButton(
            text="❌ Нет, оставить",
            payload=CancelAllPayload().pack()
        ),
    )

    await event.answer("❓ Подтвердите отмену.")
    await bot.send_message(
        chat_id=event.chat.chat_id,
        text="Вы уверены?",
        attachments=[builder.as_markup()]
    )

@router.message_callback(CancelConfirmPayload.filter())
async def process_cancel_confirm(event: MessageCallback, payload: CancelConfirmPayload, context: MemoryContext):
    """Подтверждение отмены."""
    db = get_db()
    bot = get_max_bot()

    tournament_id = await db.get_tournament_id_by_registration(payload.registration_id)
    success = await db.cancel_registration(payload.registration_id, event.from_user.user_id)

    if success:
        log_user_action(event.from_user, "cancel_registration_success", {"registration_id": payload.registration_id})
        await event.answer("✅ Отменено!")
        await bot.send_message(
            chat_id=event.chat.chat_id,
            text="✅ Регистрация отменена."
        )

        if tournament_id:
            tournament = await db.get_tournament(tournament_id)
            participants = await db.get_participants(tournament_id)
            text = format_participants_update_text(tournament, participants)
            await notify_group_from_max(text)
    else:
        log_user_action(event.from_user, "cancel_registration_failed", {"registration_id": payload.registration_id})
        await event.answer("❌ Ошибка.")

    await context.clear()

@router.message_callback(CancelAllPayload.filter())
async def process_cancel_all(event: MessageCallback, context: MemoryContext):
    """Отмена действия."""
    bot = get_max_bot()
    await context.clear()
    await event.answer("❌ Отменено.")
    await bot.send_message(
        chat_id=event.chat.chat_id,
        text="❌ Действие отменено."
    )
