"""Общие вспомогательные функции для обработчиков MAX и Telegram."""
import json
import logging
from datetime import datetime
from typing import Optional
from maxapi.enums.parse_mode import ParseMode
from context import get_tg_bot, get_max_bot, get_max_username, get_db
from keyboards.max import get_max_group_message_markup
from keyboards.telegram import get_tg_group_message_markup
from instance.config import ADMIN_USER_IDS, TELEGRAM_GROUP_CHAT_ID, MAX_GROUP_CHAT_ID

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора."""
    return user_id in ADMIN_USER_IDS


def get_user_id(user) -> Optional[int]:
    """Получение ID пользователя (MAX использует user_id, Telegram - id)."""
    return getattr(user, 'user_id', None) or getattr(user, 'id', None)


def get_user_display_name(user) -> str:
    """Получение отображаемого имени пользователя для логов."""
    username = getattr(user, 'username', None)
    if username:
        return f"@{username}"
    full_name = f"{user.first_name or ''} {getattr(user, 'last_name', '') or ''}".strip()
    if full_name:
        return full_name
    return f"ID: {get_user_id(user)}"


def build_welcome_message(first_name: str, user_id: int) -> str:
    """Формирует приветственное сообщение для команды /start."""
    text = (
        f"👋 Привет, {first_name}!\n\n"
        "Я бот для регистрации на турниры.\n\n"
        "📚 Команды:\n"
        "/register - зарегистрировать участника\n"
        "/participants - посмотреть участников\n"
        "/my_registrations - мои регистрации\n"
        "/cancel_registration - отменить регистрацию\n"
        "/help - справка"
    )
    if is_admin(user_id):
        text += "\n\n🔑 Админ-команды:\n/add_tournament\n/delete_tournament"
    return text


def build_help_message(user_id: int) -> str:
    """Формирует текст справки для команды /help."""
    text = (
        "📚 Справка:\n\n"
        "/start - начать работу\n"
        "/register - регистрация участника\n"
        "/participants - список участников\n"
        "/my_registrations - ваши регистрации\n"
        "/cancel_registration - отменить регистрацию\n"
        "/help - эта справка"
    )
    if is_admin(user_id):
        text += "\n\nАдмин:\n/add_tournament\n/delete_tournament"
    return text


def log_user_action(user, action: str, details: Optional[dict] = None) -> None:
    """Логирование действий пользователя (общее для MAX и Telegram)."""
    log_message = (
        f"👤 Пользователь: {get_user_display_name(user)} "
        f"(ID: {get_user_id(user)}) | Действие: {action}"
    )
    if details:
        log_message += f" | Подробности: {json.dumps(details, ensure_ascii=False)}"
    logger.info(log_message)

async def send_notification_to_both(text: str, parse_mode_tg=None, keyboard_tg=None, keyboard_max=None):
    """
    Отправка уведомления в оба мессенджера.
    Использует объекты из глобального контекста.
    """
    tg_bot = get_tg_bot()
    max_bot = get_max_bot()

    logger.info("📌 send_notification_to_both вызван")
    logger.info("📌 TELEGRAM_GROUP_CHAT_ID: %s", TELEGRAM_GROUP_CHAT_ID)
    logger.info("📌 MAX_GROUP_CHAT_ID: %s", MAX_GROUP_CHAT_ID)

    # Отправка в Telegram
    try:
        if tg_bot:
            logger.info("📤 Отправка в Telegram группу %s...", TELEGRAM_GROUP_CHAT_ID)
            logger.info("📝 Текст: %s...", text[:100])

            if keyboard_tg:
                await tg_bot.send_message(
                    chat_id=TELEGRAM_GROUP_CHAT_ID,
                    text=text,
                    parse_mode=parse_mode_tg,
                    reply_markup=keyboard_tg
                )
            else:
                await tg_bot.send_message(
                    chat_id=TELEGRAM_GROUP_CHAT_ID,
                    text=text,
                    parse_mode=parse_mode_tg
                )
            logger.info("✅ Сообщение отправлено в Telegram группу %s", TELEGRAM_GROUP_CHAT_ID)
        else:
            logger.warning("⚠️ tg_bot is None, пропускаем отправку в Telegram")
    except Exception as e:
        logger.error("❌ Ошибка отправки в Telegram: %s", e)

    # Отправка в MAX
    try:
        if max_bot:
            logger.info("📤 Отправка в MAX группу %s...", MAX_GROUP_CHAT_ID)
            logger.info("📝 Текст: %s...", text[:100])

            parse_mode = ParseMode.HTML if parse_mode_tg else None

            attachments = None
            if keyboard_max:
                attachments = [keyboard_max]

            await max_bot.send_message(
                chat_id=MAX_GROUP_CHAT_ID,
                text=text,
                parse_mode=parse_mode,
                attachments=attachments
            )
            logger.info("✅ Сообщение отправлено в MAX группу %s", MAX_GROUP_CHAT_ID)
        else:
            logger.warning("⚠️ max_bot is None, пропускаем отправку в MAX")
    except Exception as e:
        logger.error("❌ Ошибка отправки в MAX: %s", e)


def format_registration_confirmation(tournament: dict, full_name: str, city: str) -> str:
    """Формирует текст подтверждения регистрации участника."""
    date_obj = datetime.fromisoformat(tournament['date'])
    return (
        f"✅ Участник зарегистрирован!\n\n"
        f"🏆 {tournament['name']}\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
        f"👤 {full_name}\n"
        f"🏙️ {city}"
    )


def format_participants_list(tournament: dict, participants: list) -> str:
    """Формирует текст со списком участников турнира."""
    date_obj = datetime.fromisoformat(tournament['date'])
    text = (
        f"🏆 {tournament['name']}\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
        f"👥 Участников: {len(participants)}\n\n"
    )
    if participants:
        for i, p in enumerate(participants, 1):
            text += f"{i}. {p['full_name']} ({p['city']})\n"
    else:
        text += "Пока нет участников."
    return text


def format_user_registrations(registrations: list) -> str:
    """Формирует текст со списком регистраций пользователя."""
    text = "📋 Ваши регистрации:\n\n"
    current_tournament = None
    for reg in registrations:
        if current_tournament != reg['tournament_name']:
            current_tournament = reg['tournament_name']
            date_obj = datetime.fromisoformat(reg['tournament_date'])
            text += f"\n🏆 {reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}):\n"
        text += f"   • {reg['full_name']} ({reg['city']})\n"
    return text


def format_participants_update_text(tournament: dict, participants: list, include_date: bool = True) -> str:
    """Формирует текст уведомления об обновлении списка участников турнира."""
    text = f"📢 <b>Обновление списка участников!</b>\n\n🏆 {tournament['name']}\n"
    if include_date:
        date_obj = datetime.fromisoformat(tournament['date'])
        text += f"📅 {date_obj.strftime('%d.%m.%Y')}\n"
    text += f"👥 Всего: {len(participants)}\n\n"
    for i, p in enumerate(participants, 1):
        text += f"{i}. {p['full_name']} ({p['city']})\n"
    return text


async def notify_group_from_max(text: str) -> None:
    """Отправляет уведомление в обе группы из хендлеров MAX (с кнопками MAX и Telegram)."""
    max_username = get_max_username()
    max_keyboard = get_max_group_message_markup(max_username)
    tg_keyboard = get_tg_group_message_markup("ttc_etalon_bot")
    await send_notification_to_both(
        text=text,
        parse_mode_tg='HTML',
        keyboard_tg=tg_keyboard,
        keyboard_max=max_keyboard.as_markup(),
    )


async def notify_group_from_tg(text: str, tg_username: str) -> None:
    """Отправляет уведомление в обе группы из хендлеров Telegram (без кнопки MAX)."""
    tg_keyboard = get_tg_group_message_markup(tg_username)
    await send_notification_to_both(
        text=text,
        parse_mode_tg='HTML',
        keyboard_tg=tg_keyboard,
    )


async def get_tournament_or_notify(event, tournament_id: int) -> Optional[dict]:
    """Получает турнир по ID для MAX callback или уведомляет об ошибке через event.answer()."""
    db = get_db()
    tournament = await db.get_tournament(tournament_id)
    if not tournament:
        await event.answer("❌ Турнир не найден.")
        return None
    return tournament


async def get_tournaments_or_notify(event, empty_text: str) -> Optional[list]:
    """Получает список активных турниров для MAX или уведомляет об их отсутствии."""
    db = get_db()
    tournaments = await db.get_tournaments()
    if not tournaments:
        await event.message.answer(empty_text)
        return None
    return tournaments
