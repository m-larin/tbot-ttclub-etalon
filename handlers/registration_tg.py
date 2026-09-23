"""Обработчики регистрации и отмены регистрации на турниры для Telegram."""
import logging
from telebot.types import Message, CallbackQuery
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.telegram import (
    get_tg_tournaments_keyboard,
    get_tg_cancel_tournaments_keyboard,
    get_tg_cancel_registration_keyboard,
)
from handlers.common import (
    is_admin,
    get_cancellable_registrations,
    format_cancel_participants_prompt,
    format_registration_confirmation,
    format_participants_list,
    format_user_registrations,
    format_participants_update_text,
    notify_group_from_tg,
    log_user_action,
)
from context import get_db, get_tg_bot, get_tg_username

logger = logging.getLogger(__name__)

# Словари для состояний
user_states = {}
user_temp_data = {}

# Хендлеры регистрируются как вложенные функции, чтобы замыкаться на bot/tg_username,
# поэтому их число закономерно превышает лимит statements.
def register_handlers():  # pylint: disable=too-many-statements
    """Регистрация обработчиков для Telegram."""
    bot = get_tg_bot()
    db = get_db()
    tg_username = get_tg_username()

    @bot.message_handler(commands=['register'])
    async def cmd_register(message: Message):
        """Показать список турниров для регистрации."""
        tournaments = await db.get_tournaments()
        log_user_action(message.from_user, "register_command", {"tournaments_count": len(tournaments)})
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
        log_user_action(message.from_user, "participants_command", {"tournaments_count": len(tournaments)})
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
        log_user_action(message.from_user, "my_registrations_command", {"registrations_count": len(registrations)})
        if not registrations:
            await bot.reply_to(message, "📭 Вы еще никого не зарегистрировали.")
            return

        text = format_user_registrations(registrations)
        await bot.reply_to(message, text)

    @bot.message_handler(commands=['cancel_registration'])
    async def cmd_cancel_registration(message: Message):
        """Показать турниры с регистрациями для отмены (админам — регистрации всех пользователей)."""
        registrations = await get_cancellable_registrations(message.from_user.id)
        log_user_action(message.from_user, "cancel_registration_start", {
            "registrations_count": len(registrations),
            "as_admin": is_admin(message.from_user.id),
        })
        if not registrations:
            await bot.reply_to(message, "📭 Нет активных регистраций.")
            return

        keyboard = get_tg_cancel_tournaments_keyboard(registrations)
        await bot.send_message(
            message.chat.id,
            "🏆 Выберите турнир:",
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('unreg_'))
    async def process_cancel_tournament(call: CallbackQuery):
        """Выбор турнира при отмене регистрации — показать участников."""
        tournament_id = int(call.data.split('_')[1])
        registrations = await get_cancellable_registrations(call.from_user.id, tournament_id)

        if not registrations:
            log_user_action(call.from_user, "cancel_registration_no_registrations", {"tournament_id": tournament_id})
            await bot.answer_callback_query(call.id)
            await bot.edit_message_text(
                "📭 Нет регистраций на этот турнир.",
                call.message.chat.id,
                call.message.message_id
            )
            return

        log_user_action(call.from_user, "cancel_registration_tournament_selected", {
            "tournament_id": tournament_id,
            "tournament_name": registrations[0]['tournament_name'],
        })

        keyboard = get_tg_cancel_registration_keyboard(registrations)
        await bot.answer_callback_query(call.id)
        await bot.edit_message_text(
            format_cancel_participants_prompt(registrations),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=keyboard
        )

    @bot.callback_query_handler(func=lambda call: call.data and call.data.startswith('reg_'))
    async def process_registration_tournament(call: CallbackQuery):
        """Выбор турнира для регистрации."""
        tournament_id = int(call.data.split('_')[1])
        tournament = await db.get_tournament(tournament_id)

        if not tournament:
            log_user_action(call.from_user, "register_failed_tournament_not_found", {"tournament_id": tournament_id})
            await bot.answer_callback_query(call.id, "❌ Турнир не найден.", show_alert=True)
            return

        log_user_action(call.from_user, "register_new_participant_start", {
            "tournament_id": tournament_id,
            "tournament_name": tournament['name'],
        })

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
        log_user_action(message.from_user, "participant_data_entered", {"field": "full_name"})
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
            log_user_action(message.from_user, "registration_complete", {
                "tournament_id": tournament_id,
                "tournament_name": tournament['name'],
                "participant_name": full_name,
            })
            await bot.reply_to(message, format_registration_confirmation(tournament, full_name, city))

            # Отправляем обновление в оба мессенджера
            participants = await db.get_participants(tournament_id)
            text = format_participants_update_text(tournament, participants)
            await notify_group_from_tg(text, tg_username)
        else:
            log_user_action(message.from_user, "registration_failed_db_error")
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

        log_user_action(call.from_user, "view_participants", {
            "tournament_id": tournament_id,
            "tournament_name": tournament['name'],
        })

        participants = await db.get_participants(tournament_id)
        text = format_participants_list(tournament, participants)

        await bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id
        )
        await bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: (
        call.data
        and call.data.startswith('cancel_')
        and not call.data.startswith('cancel_confirm_')
        and call.data not in ('cancel_all', 'cancel_delete')
    ))
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

        admin = is_admin(call.from_user.id)
        success = await db.cancel_registration(registration_id, None if admin else call.from_user.id)

        if success:
            log_user_action(call.from_user, "cancel_registration_success", {
                "registration_id": registration_id,
                "as_admin": admin,
            })
            await bot.answer_callback_query(call.id, "✅ Отменено!")
            await bot.edit_message_text(
                "✅ Регистрация отменена.",
                call.message.chat.id,
                call.message.message_id
            )

            if tournament_id:
                tournament = await db.get_tournament(tournament_id)
                participants = await db.get_participants(tournament_id)
                text = format_participants_update_text(tournament, participants)
                await notify_group_from_tg(text, tg_username)
        else:
            log_user_action(call.from_user, "cancel_registration_failed", {"registration_id": registration_id})
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
