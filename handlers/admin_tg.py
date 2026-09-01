"""Административные обработчики Telegram: создание и удаление турниров."""
import logging
from datetime import datetime
from telebot.types import Message, CallbackQuery
from keyboards.telegram import get_tg_delete_tournaments_keyboard
from handlers.common import is_admin, notify_group_from_tg, log_user_action
from context import get_db, get_tg_bot, get_tg_username

logger = logging.getLogger(__name__)

# Словари для состояний (FSM для Telegram)
user_states = {}
user_data = {}

# Хендлеры регистрируются как вложенные функции, чтобы замыкаться на bot/tg_username,
# поэтому их число закономерно превышает лимит statements.
def register_handlers():  # pylint: disable=too-many-statements
    """Регистрация обработчиков для Telegram."""
    bot = get_tg_bot()
    tg_username = get_tg_username()

    @bot.message_handler(commands=['add_tournament'])
    async def cmd_add_tournament(message: Message):
        """Начало добавления турнира (только для админов)."""
        if not is_admin(message.from_user.id):
            log_user_action(message.from_user, "add_tournament_unauthorized")
            await bot.reply_to(message, "⛔ У вас нет прав.")
            return

        log_user_action(message.from_user, "add_tournament_start")
        user_states[message.from_user.id] = 'add_tournament_name'
        await bot.reply_to(message, "Введите название турнира:")

    @bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == 'add_tournament_name')
    async def process_tournament_name(message: Message):
        """Обработка названия турнира."""
        user_data[message.from_user.id] = {'tournament_name': message.text}
        user_states[message.from_user.id] = 'add_tournament_date'
        log_user_action(message.from_user, "add_tournament_name_entered", {"tournament_name": message.text})
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

            log_user_action(message.from_user, "add_tournament_success", {
                "tournament_name": tournament_name,
                "tournament_date": date_str,
                "tournament_id": tournament_id,
            })

            await bot.reply_to(
                message,
                f"✅ Турнир '{tournament_name}' на {date_obj.strftime('%d.%m.%Y')} успешно добавлен!"
            )

            # Отправляем уведомление в оба мессенджера
            text = f"📢 <b>Началась запись на турнир!</b>\n\n🏆 {tournament_name}\n📅 {date_str}"
            await notify_group_from_tg(text, tg_username)

            # Очищаем состояние
            user_states.pop(message.from_user.id, None)
            user_data.pop(message.from_user.id, None)

        except ValueError:
            log_user_action(message.from_user, "add_tournament_invalid_date", {"entered_date": message.text})
            await bot.reply_to(
                message,
                "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ"
            )

    @bot.message_handler(commands=['delete_tournament'])
    async def cmd_delete_tournament(message: Message):
        """Начало удаления турнира (только для админов)."""
        if not is_admin(message.from_user.id):
            log_user_action(message.from_user, "delete_tournament_unauthorized")
            await bot.reply_to(message, "⛔ У вас нет прав.")
            return

        db = get_db()
        tournaments = await db.get_tournaments()
        log_user_action(message.from_user, "delete_tournament_start", {"tournaments_count": len(tournaments)})
        if not tournaments:
            await bot.reply_to(message, "Нет активных турниров.")
            return

        keyboard = await get_tg_delete_tournaments_keyboard(tournaments)
        await bot.send_message(
            message.chat.id,
            "Выберите турнир для удаления:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('del_'))
    async def process_delete_tournament(call: CallbackQuery):
        """Обработка удаления турнира."""
        if not is_admin(call.from_user.id):
            log_user_action(call.from_user, "delete_tournament_unauthorized")
            await bot.answer_callback_query(call.id, "⛔ У вас нет прав.", show_alert=True)
            return

        tournament_id = int(call.data.split('_')[1])
        db = get_db()
        tournament = await db.get_tournament(tournament_id)

        if tournament:
            await db.delete_tournament(tournament_id)
            log_user_action(call.from_user, "delete_tournament_success", {
                "tournament_id": tournament_id,
                "tournament_name": tournament['name'],
            })
            await bot.edit_message_text(
                f"✅ Турнир '{tournament['name']}' успешно удален.",
                call.message.chat.id,
                call.message.message_id
            )
            logger.info("Админ %s удалил турнир %s", call.from_user.id, tournament['name'])
        else:
            log_user_action(call.from_user, "delete_tournament_failed_not_found", {"tournament_id": tournament_id})
            await bot.edit_message_text(
                "❌ Турнир не найден.",
                call.message.chat.id,
                call.message.message_id
            )

        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
    async def process_cancel_delete(call: CallbackQuery):
        """Отмена удаления турнира."""
        log_user_action(call.from_user, "delete_tournament_cancelled")
        await bot.edit_message_text(
            "❌ Удаление отменено.",
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
        await notify_group_from_tg(text, tg_username)
        await bot.reply_to(message, "✅ Тестовое уведомление отправлено!")

    logger.info("✅ Telegram admin handlers registered")
