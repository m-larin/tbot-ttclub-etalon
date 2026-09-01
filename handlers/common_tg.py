"""Общие команды бота Telegram (/start, /help)."""
import logging
from telebot.types import Message
from handlers.common import build_welcome_message, build_help_message, log_user_action
from context import get_tg_bot

logger = logging.getLogger(__name__)

def register_handlers():
    """Регистрация обработчиков для Telegram."""
    bot = get_tg_bot()

    @bot.message_handler(commands=['start'])
    async def cmd_start(message: Message):
        """Команда /start."""
        user = message.from_user
        log_user_action(user, "start_command")
        await bot.reply_to(message, build_welcome_message(user.first_name, user.id))

    @bot.message_handler(commands=['help'])
    async def cmd_help(message: Message):
        """Команда /help."""
        user = message.from_user
        log_user_action(user, "help_command")
        await bot.reply_to(message, build_help_message(user.id))

    logger.info("✅ Telegram common handlers registered")
