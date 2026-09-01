"""Общие команды бота MAX (/start, /help)."""
import logging
from maxapi import Router
from maxapi.filters.command import Command, CommandStart
from maxapi.types import MessageCreated, BotStarted
from context import get_max_bot
from handlers.common import build_welcome_message, build_help_message, log_user_action

logger = logging.getLogger(__name__)
router = Router()

def register_handlers():
    """Регистрация обработчиков."""
    logger.info("✅ Common MAX handlers registered")

@router.bot_started()
async def on_bot_started(event: BotStarted):
    """При первом открытии бота."""
    user = event.from_user
    bot = get_max_bot()
    log_user_action(user, "bot_started")

    welcome = build_welcome_message(user.first_name, user.user_id)
    await bot.send_message(chat_id=event.chat_id, text=welcome)

@router.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    """Команда /start."""
    user = event.from_user
    log_user_action(user, "start_command")
    await event.message.answer(build_welcome_message(user.first_name, user.user_id))

@router.message_created(Command("help"))
async def cmd_help(event: MessageCreated):
    """Команда /help."""
    user = event.from_user
    log_user_action(user, "help_command")
    await event.message.answer(build_help_message(user.user_id))
