# handlers/common_max.py
import logging
from maxapi import Router
from maxapi.filters.command import Command, CommandStart
from maxapi.types import MessageCreated, BotStarted
from context import get_max_bot
from instance.config import ADMIN_USER_IDS

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
    
    welcome = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для регистрации на турниры.\n\n"
        "📚 Команды:\n"
        "/register - зарегистрировать участника\n"
        "/participants - посмотреть участников\n"
        "/my_registrations - мои регистрации\n"
        "/cancel_registration - отменить регистрацию\n"
        "/help - справка"
    )
    if user.user_id in ADMIN_USER_IDS:
        welcome += "\n\n🔑 Админ-команды:\n/add_tournament\n/delete_tournament"
    
    await bot.send_message(chat_id=event.chat_id, text=welcome)

@router.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    """Команда /start."""
    user = event.from_user
    welcome = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для регистрации на турниры.\n\n"
        "📚 Команды:\n"
        "/register - зарегистрировать участника\n"
        "/participants - посмотреть участников\n"
        "/my_registrations - мои регистрации\n"
        "/cancel_registration - отменить регистрацию\n"
        "/help - справка"
    )
    if user.user_id in ADMIN_USER_IDS:
        welcome += "\n\n🔑 Админ-команды:\n/add_tournament\n/delete_tournament"
    
    await event.message.answer(welcome)

@router.message_created(Command("help"))
async def cmd_help(event: MessageCreated):
    """Команда /help."""
    user = event.from_user
    help_text = (
        "📚 Справка:\n\n"
        "/start - начать работу\n"
        "/register - регистрация участника\n"
        "/participants - список участников\n"
        "/my_registrations - ваши регистрации\n"
        "/cancel_registration - отменить регистрацию\n"
        "/help - эта справка"
    )
    if user.user_id in ADMIN_USER_IDS:
        help_text += "\n\nАдмин:\n/add_tournament\n/delete_tournament"
    
    await event.message.answer(help_text)