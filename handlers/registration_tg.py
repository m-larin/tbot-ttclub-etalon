# handlers/registration_tg.py
import logging
from datetime import datetime
from telebot.types import Message, CallbackQuery
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.telegram import get_tg_tournaments_keyboard, get_tg_cancel_registration_keyboard, get_tg_group_message_markup
from handlers.common import is_admin, send_notification_to_both
from context import get_db, get_tg_bot, get_tg_username
from instance.config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

# Словари для состояний
user_states = {}
user_temp_data = {}

def register_handlers():
    """Регистрация обработчиков для Telegram."""
    bot = get_tg_bot()
    db = get_db()
    tg_username = get_tg_username()

    @bot.message_handler(commands=['register'])
    async def cmd_register(message: Message):
        """Показать список турниров для регистрации."""
        tournaments = await db.get_tournaments()
        if not tournaments:
            await bot.reply_to(message, "📭 Нет активных турниров.")
            return
        
        keyboard = await get_tg_tournaments_keyboard(tournaments, "reg")
        await bot.send_message(
            message.chat.id,
            "🏆 Выберите турнир:",
            reply_markup=keyboard
        )

    @bot.message_handler(commands=['participants'])
    async def cmd_participants(message: Message):
        """Показать список турниров для просмотра участников."""
        tournaments = await db.get_tournaments()
        if not tournaments:
            await bot.reply_to(message, "Нет активных турниров.")
            return
        
        keyboard = await get_tg_tournaments_keyboard(tournaments, "view")
        await bot.send_message(
            message.chat.id,
            "👥 Выберите турнир:",
            reply_markup=keyboard
        )

    @bot.message_handler(commands=['my_registrations'])
    async def cmd_my_registrations(message: Message):
        """Показать регистрации пользователя."""
        registrations = await db.get_user_registrations(message.from_user.id)
        if not registrations:
            await bot.reply_to(message, "📭 Вы еще никого не зарегистрировали.")
            return
        
        text = "📋 Ваши регистрации:\n\n"
        current_tournament = None
        for reg in registrations:
            if current_tournament != reg['tournament_name']:
                current_tournament = reg['tournament_name']
                date_obj = datetime.fromisoformat(reg['tournament_date'])
                text += f"\n🏆 {reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}):\n"
            text += f"   • {reg['full_name']} ({reg['city']})\n"
        
        await bot.reply_to(message, text)

    @bot.message_handler(commands=['cancel_registration'])
    async def cmd_cancel_registration(message: Message):
        """Показать регистрации для отмены."""
        registrations = await db.get_user_registrations(message.from_user.id)
        if not registrations:
            await bot.reply_to(message, "📭 Нет активных регистраций.")
            return
        
        keyboard = await get_tg_cancel_registration_keyboard(registrations)
        await bot.send_message(
            message.chat.id,
            "Выберите регистрацию для отмены:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('reg_'))
    async def process_registration_tournament(call: CallbackQuery):
        """Выбор турнира для регистрации."""
        tournament_id = int(call.data.split('_')[1])
        tournament = await db.get_tournament(tournament_id)
        
        if not tournament:
            await bot.answer_callback_query(call.id, "❌ Турнир не найден.", show_alert=True)
            return
        
        user_temp_data[call.from_user.id] = {'tournament_id': tournament_id}
        user_states[call.from_user.id] = 'waiting_full_name'
        
        # Отвечаем на callback
        await bot.answer_callback_query(call.id, "✅ Турнир выбран!")
        
        # Отправляем НОВОЕ сообщение с вопросом (НЕ редактируем старое)
        await bot.send_message(
            call.message.chat.id,
            "Введите ФИО участника:\nВ случае парного турнира введите ФИО обоих участников через запятую:"
        )

    @bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'waiting_full_name')
    async def process_full_name(message: Message):
        """Ввод ФИО участника."""
        full_name = message.text.strip()
        if not full_name or len(full_name) < 2:
            await bot.reply_to(message, "❌ Введите корректное ФИО.")
            return
        
        user_temp_data[message.from_user.id]['full_name'] = full_name
        user_states[message.from_user.id] = 'waiting_city'
        await bot.reply_to(message, "Введите город:")

    @bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'waiting_city')
    async def process_city(message: Message):
        """Ввод города и завершение регистрации."""
        city = message.text.strip()
        if not city or len(city) < 2:
            await bot.reply_to(message, "❌ Введите корректное название города.")
            return
        
        data = user_temp_data.get(message.from_user.id, {})
        tournament_id = data.get('tournament_id')
        full_name = data.get('full_name')
        
        if not tournament_id or not full_name:
            await bot.reply_to(message, "❌ Ошибка данных. Начните заново /register")
            user_states.pop(message.from_user.id, None)
            user_temp_data.pop(message.from_user.id, None)
            return
        
        success = await db.register_participant(tournament_id, message.from_user.id, full_name, city)
        
        if success:
            tournament = await db.get_tournament(tournament_id)
            date_obj = datetime.fromisoformat(tournament['date'])
            
            await bot.reply_to(
                message,
                f"✅ Участник зарегистрирован!\n\n"
                f"🏆 {tournament['name']}\n"
                f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
                f"👤 {full_name}\n"
                f"🏙️ {city}"
            )
            
            # Отправляем обновление в оба мессенджера
            participants = await db.get_participants(tournament_id)
            text = f"📢 <b>Обновление списка участников!</b>\n\n🏆 {tournament['name']}\n👥 Всего: {len(participants)}\n\n"
            for i, p in enumerate(participants, 1):
                text += f"{i}. {p['full_name']} ({p['city']})\n"
            
            # Используем tg_username из контекста
            tg_keyboard = get_tg_group_message_markup(tg_username)
            
            await send_notification_to_both(
                text=text,
                parse_mode_tg='HTML',
                keyboard_tg=tg_keyboard
            )
        else:
            await bot.reply_to(message, "❌ Ошибка регистрации.")
        
        user_states.pop(message.from_user.id, None)
        user_temp_data.pop(message.from_user.id, None)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('view_'))
    async def process_view_participants(call: CallbackQuery):
        """Показать участников турнира."""
        tournament_id = int(call.data.split('_')[1])
        tournament = await db.get_tournament(tournament_id)
        
        if not tournament:
            await bot.edit_message_text(
                "❌ Турнир не найден.",
                call.message.chat.id,
                call.message.message_id
            )
            return
        
        participants = await db.get_participants(tournament_id)
        date_obj = datetime.fromisoformat(tournament['date'])
        
        text = f"🏆 {tournament['name']}\n📅 {date_obj.strftime('%d.%m.%Y')}\n👥 Участников: {len(participants)}\n\n"
        if participants:
            for i, p in enumerate(participants, 1):
                text += f"{i}. {p['full_name']} ({p['city']})\n"
        else:
            text += "Пока нет участников."
        
        await bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id
        )
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('cancel_') and not call.data.startswith('cancel_confirm_') and call.data != 'cancel_all')
    async def process_cancel_selection(call: CallbackQuery):
        """Начало отмены регистрации."""
        registration_id = int(call.data.split('_')[1])
        
        keyboard = InlineKeyboardMarkup(row_width=2)
        yes_btn = InlineKeyboardButton("✅ Да", callback_data=f"cancel_confirm_{registration_id}")
        no_btn = InlineKeyboardButton("❌ Нет", callback_data="cancel_all")
        keyboard.add(yes_btn, no_btn)
        
        await bot.edit_message_text(
            "Вы уверены?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('cancel_confirm_'))
    async def process_cancel_confirm(call: CallbackQuery):
        """Подтверждение отмены регистрации."""
        registration_id = int(call.data.split('_')[2])
        tournament_id = await db.get_tournament_id_by_registration(registration_id)
        
        success = await db.cancel_registration(registration_id, call.from_user.id)
        
        if success:
            await bot.answer_callback_query(call.id, "✅ Отменено!")
            await bot.edit_message_text(
                "✅ Регистрация отменена.",
                call.message.chat.id,
                call.message.message_id
            )
            
            if tournament_id:
                tournament = await db.get_tournament(tournament_id)
                participants = await db.get_participants(tournament_id)
                text = f"📢 <b>Обновление списка участников!</b>\n\n🏆 {tournament['name']}\n👥 Всего: {len(participants)}\n\n"
                for i, p in enumerate(participants, 1):
                    text += f"{i}. {p['full_name']} ({p['city']})\n"
                
                # Используем tg_username из контекста
                tg_keyboard = get_tg_group_message_markup(tg_username)
                
                await send_notification_to_both(
                    text=text,
                    parse_mode_tg='HTML',
                    keyboard_tg=tg_keyboard
                )
        else:
            await bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_all")
    async def process_cancel_all(call: CallbackQuery):
        """Отмена действия."""
        await bot.edit_message_text(
            "❌ Отменено.",
            call.message.chat.id,
            call.message.message_id
        )
        await bot.answer_callback_query(call.id)
    
    logger.info("✅ Telegram registration handlers registered")