# handlers/admin_tg.py
import logging
from datetime import datetime
from telebot.types import Message, CallbackQuery
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.telegram import get_tg_tournaments_keyboard, get_tg_group_message_markup
from handlers.common import is_admin, send_notification_to_both
from context import get_db, get_tg_bot, get_tg_username
from instance.config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

# Словари для состояний (FSM для Telegram)
user_states = {}
user_data = {}

def register_handlers():
    """Регистрация обработчиков для Telegram."""
    bot = get_tg_bot()
    db = get_db()
    tg_username = get_tg_username()

    @bot.message_handler(commands=['add_tournament'])
    async def cmd_add_tournament(message: Message):
        """Начало добавления турнира (только для админов)."""
        if not is_admin(message.from_user.id):
            await bot.reply_to(message, "⛔ У вас нет прав.")
            return
        
        user_states[message.from_user.id] = 'add_tournament_name'
        await bot.reply_to(message, "Введите название турнира:")

    @bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'add_tournament_name')
    async def process_tournament_name(message: Message):
        """Обработка названия турнира."""
        user_data[message.from_user.id] = {'tournament_name': message.text}
        user_states[message.from_user.id] = 'add_tournament_date'
        await bot.reply_to(
            message,
            "Теперь введите дату турнира в формате ДД.ММ.ГГГГ\nНапример: 25.12.2024"
        )

    @bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'add_tournament_date')
    async def process_tournament_date(message: Message):
        """Обработка даты турнира."""
        try:
            date_str = message.text
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
            date_iso = datetime.combine(date_obj.date(), datetime.min.time()).isoformat()
            
            data = user_data.get(message.from_user.id, {})
            tournament_name = data.get('tournament_name', 'Турнир')
            
            db = get_db()
            tournament_id = await db.add_tournament(tournament_name, date_iso, message.from_user.id)
            
            if tournament_id == 0:
                await bot.reply_to(message, "❌ Ошибка при создании турнира.")
                return
            
            await bot.reply_to(
                message,
                f"✅ Турнир '{tournament_name}' на {date_obj.strftime('%d.%m.%Y')} успешно добавлен!"
            )
            
            # Отправляем уведомление в оба мессенджера
            text = f"📢 <b>Началась запись на турнир!</b>\n\n🏆 {tournament_name}\n📅 {date_str}"
            
            # Используем tg_username из контекста
            tg_keyboard = get_tg_group_message_markup(tg_username)
            
            await send_notification_to_both(
                text=text,
                parse_mode_tg='HTML',
                keyboard_tg=tg_keyboard
            )
            
            # Очищаем состояние
            user_states.pop(message.from_user.id, None)
            user_data.pop(message.from_user.id, None)
            
        except ValueError:
            await bot.reply_to(
                message,
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ"
            )

    @bot.message_handler(commands=['delete_tournament'])
    async def cmd_delete_tournament(message: Message):
        """Начало удаления турнира (только для админов)."""
        if not is_admin(message.from_user.id):
            await bot.reply_to(message, "⛔ У вас нет прав.")
            return
        
        db = get_db()
        tournaments = await db.get_tournaments()
        if not tournaments:
            await bot.reply_to(message, "Нет активных турниров.")
            return
        
        keyboard = await get_tg_tournaments_keyboard(tournaments, "del")
        await bot.send_message(
            message.chat.id,
            "Выберите турнир для удаления:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('del_'))
    async def process_delete_tournament(call: CallbackQuery):
        """Обработка удаления турнира."""
        if not is_admin(call.from_user.id):
            await bot.answer_callback_query(call.id, "⛔ У вас нет прав.", show_alert=True)
            return
        
        tournament_id = int(call.data.split('_')[1])
        db = get_db()
        tournament = await db.get_tournament(tournament_id)
        
        if tournament:
            await db.delete_tournament(tournament_id)
            await bot.edit_message_text(
                f"✅ Турнир '{tournament['name']}' успешно удален.",
                call.message.chat.id,
                call.message.message_id
            )
            logger.info(f"Админ {call.from_user.id} удалил турнир {tournament['name']}")
        else:
            await bot.edit_message_text(
                "❌ Турнир не найден.",
                call.message.chat.id,
                call.message.message_id
            )
        
        await bot.answer_callback_query(call.id)

    @bot.message_handler(commands=['test_notification'])
    async def cmd_test_notification(message: Message):
        """Тестовая команда для проверки отправки уведомления."""
        if not is_admin(message.from_user.id):
            await bot.reply_to(message, "⛔ У вас нет прав.")
            return
        
        text = "🧪 <b>Тестовое уведомление!</b>\n\nЭто сообщение отправлено из обоих мессенджеров."
        
        # Используем tg_username из контекста
        tg_keyboard = get_tg_group_message_markup(tg_username)
        
        await send_notification_to_both(
            text=text,
            parse_mode_tg='HTML',
            keyboard_tg=tg_keyboard
        )
        await bot.reply_to(message, "✅ Тестовое уведомление отправлено!")
    
    logger.info("✅ Telegram admin handlers registered")