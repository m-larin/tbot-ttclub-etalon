# handlers/registration_max.py
import logging
from datetime import datetime
from maxapi import Router
from maxapi.filters.command import Command
from maxapi.types import MessageCreated, MessageCallback
from maxapi.context import MemoryContext
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.types import CallbackButton
from maxapi.enums.parse_mode import ParseMode
from states.registration import RegistrationStates, CancelStates
from keyboards.max import (
    get_max_registration_tournaments_keyboard,
    get_max_view_tournaments_keyboard,
    get_max_cancel_registration_keyboard,
    get_max_group_message_markup,
)
from keyboards.telegram import get_tg_group_message_markup
from payloads import (
    TournamentRegistrationPayload,
    TournamentViewPayload,
    CancelRegistrationPayload,
    CancelConfirmPayload,
    CancelAllPayload,
)
from handlers.common import is_admin, send_notification_to_both
from context import get_max_bot, get_max_username, get_db
from instance.config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)
router = Router()

def register_handlers():
    """Регистрация обработчиков."""
    logger.info("✅ Registration MAX handlers registered")

@router.message_created(Command("register"))
async def cmd_register(event: MessageCreated):
    """Регистрация участника."""
    db = get_db()
    tournaments = await db.get_tournaments()
    if not tournaments:
        await event.message.answer("📭 Нет активных турниров.")
        return
    
    keyboard = await get_max_registration_tournaments_keyboard(tournaments)
    await event.message.answer("🏆 Выберите турнир:", attachments=[keyboard])

@router.message_callback(TournamentRegistrationPayload.filter())
async def process_registration_tournament(event: MessageCallback, payload: TournamentRegistrationPayload, context: MemoryContext):
    """Выбор турнира для регистрации."""
    db = get_db()
    bot = get_max_bot()
    
    tournament = await db.get_tournament(payload.tournament_id)
    if not tournament:
        await event.answer("❌ Турнир не найден.")
        return
    
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
    bot = get_max_bot()
    
    success = await db.register_participant(tournament_id, event.from_user.user_id, full_name, city)
    
    if success:
        tournament = await db.get_tournament(tournament_id)
        date_obj = datetime.fromisoformat(tournament['date'])
        
        await event.message.answer(
            f"✅ Участник зарегистрирован!\n\n"
            f"🏆 {tournament['name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
            f"👤 {full_name}\n"
            f"🏙️ {city}"
        )
        
        # Отправляем обновление в оба мессенджера
        participants = await db.get_participants(tournament_id)
        text = f"📢 <b>Обновление списка участников!</b>\n\n🏆 {tournament['name']}\n📅 {date_obj.strftime('%d.%m.%Y')}\n👥 Всего: {len(participants)}\n\n"
        for i, p in enumerate(participants, 1):
            text += f"{i}. {p['full_name']} ({p['city']})\n"
        
        max_username = get_max_username()
        max_keyboard = get_max_group_message_markup(max_username)
        tg_keyboard = get_tg_group_message_markup("ttc_etalon_bot")
        
        await send_notification_to_both(
            text=text,
            parse_mode_tg='HTML',
            keyboard_tg=tg_keyboard,
            keyboard_max=max_keyboard.as_markup()
        )
    else:
        await event.message.answer("❌ Ошибка регистрации.")
    
    await context.clear()

@router.message_created(Command("participants"))
async def cmd_participants(event: MessageCreated):
    """Просмотр участников."""
    db = get_db()
    tournaments = await db.get_tournaments()
    if not tournaments:
        await event.message.answer("Нет активных турниров.")
        return
    
    keyboard = await get_max_view_tournaments_keyboard(tournaments)
    await event.message.answer("👥 Выберите турнир:", attachments=[keyboard])

@router.message_callback(TournamentViewPayload.filter())
async def process_view_participants(event: MessageCallback, payload: TournamentViewPayload):
    """Показать участников."""
    db = get_db()
    bot = get_max_bot()
    
    tournament = await db.get_tournament(payload.tournament_id)
    if not tournament:
        await event.answer("❌ Турнир не найден.")
        return
    
    participants = await db.get_participants(payload.tournament_id)
    date_obj = datetime.fromisoformat(tournament['date'])
    
    text = f"🏆 {tournament['name']}\n📅 {date_obj.strftime('%d.%m.%Y')}\n👥 Участников: {len(participants)}\n\n"
    if participants:
        for i, p in enumerate(participants, 1):
            text += f"{i}. {p['full_name']} ({p['city']})\n"
    else:
        text += "Пока нет участников."
    
    await event.answer("👥 Список готов!")
    await bot.send_message(chat_id=event.chat.chat_id, text=text)

@router.message_created(Command("my_registrations"))
async def cmd_my_registrations(event: MessageCreated):
    """Мои регистрации."""
    db = get_db()
    registrations = await db.get_user_registrations(event.from_user.user_id)
    if not registrations:
        await event.message.answer("📭 Вы еще никого не зарегистрировали.")
        return
    
    text = "📋 Ваши регистрации:\n\n"
    current_tournament = None
    for reg in registrations:
        if current_tournament != reg['tournament_name']:
            current_tournament = reg['tournament_name']
            date_obj = datetime.fromisoformat(reg['tournament_date'])
            text += f"\n🏆 {reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}):\n"
        text += f"   • {reg['full_name']} ({reg['city']})\n"
    
    await event.message.answer(text)

@router.message_created(Command("cancel_registration"))
async def cmd_cancel_registration(event: MessageCreated):
    """Отмена регистрации."""
    db = get_db()
    registrations = await db.get_user_registrations(event.from_user.user_id)
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
        await event.answer("✅ Отменено!")
        await bot.send_message(
            chat_id=event.chat.chat_id,
            text="✅ Регистрация отменена."
        )
        
        if tournament_id:
            tournament = await db.get_tournament(tournament_id)
            date_obj = datetime.fromisoformat(tournament['date'])
            participants = await db.get_participants(tournament_id)
            text = f"📢 <b>Обновление списка участников!</b>\n\n🏆 {tournament['name']}\n📅 {date_obj.strftime('%d.%m.%Y')}\n👥 Всего: {len(participants)}\n\n"
            for i, p in enumerate(participants, 1):
                text += f"{i}. {p['full_name']} ({p['city']})\n"
            
            max_username = get_max_username()
            max_keyboard = get_max_group_message_markup(max_username)
            tg_keyboard = get_tg_group_message_markup("ttc_etalon_bot")
            
            await send_notification_to_both(
                text=text,
                parse_mode_tg='HTML',
                keyboard_tg=tg_keyboard,
                keyboard_max=max_keyboard.as_markup()
            )
    else:
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