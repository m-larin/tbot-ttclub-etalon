# bot.py
"""
Бот регистрации на турнир. Позволяет выполнять операции из двух мессенджеров MAX и Telegram
"""
import asyncio
import logging

from maxapi import Bot as MaxBot, Dispatcher
from maxapi.types import BotCommand as MaxBotCommand
from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand as TgBotCommand

from context import init_context
from database.db import Database
from handlers import (
    common_max_router,
    admin_max_router,
    registration_max_router,
    register_common_max,
    register_admin_max,
    register_registration_max,
    register_tg_registration,
    register_tg_admin,
)
from instance.config import (
    TELEGRAM_TOKEN,
    MAX_TOKEN,
    LOG_FILE,
    DB_FILE
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def create_tg_bot() -> AsyncTeleBot:
    """Создание Telegram бота."""
    return AsyncTeleBot(TELEGRAM_TOKEN)


async def init_max_bot() -> MaxBot:
    """Создание MAX бота."""
    max_bot = MaxBot(token=MAX_TOKEN)
    me = await max_bot.get_me()
    logger.info("🤖 MAX бот: @%s", me.username)
    return max_bot


async def set_tg_commands(tg_bot: AsyncTeleBot) -> None:
    """Установка меню команд для Telegram."""
    commands = [
        TgBotCommand("register", "📝 Зарегистрировать участника на турнир"),
        TgBotCommand("participants", "👥 Посмотреть участников турнира"),
        TgBotCommand("my_registrations", "✅ Мои регистрации"),
        TgBotCommand("cancel_registration", "❌ Отменить регистрацию"),
        TgBotCommand("help", "ℹ️ Справка по командам"),
        TgBotCommand("start", "🚀 Начать работу с ботом"),
        TgBotCommand("add_tournament", "➕ Добавить новый турнир (админ)"),
        TgBotCommand("delete_tournament", "❌ Удалить турнир (админ)"),
    ]
    try:
        await tg_bot.set_my_commands(commands)
        logger.info("✅ Установлены команды для Telegram")
    except Exception as e:
        logger.error("❌ Ошибка установки команд Telegram: %s", e)


async def set_max_commands(max_bot: MaxBot) -> None:
    """Установка меню команд для MAX."""
    commands = [
        MaxBotCommand(name="register", description="📝 Зарегистрировать участника на турнир"),
        MaxBotCommand(name="participants", description="👥 Посмотреть участников турнира"),
        MaxBotCommand(name="my_registrations", description="✅ Мои регистрации"),
        MaxBotCommand(name="cancel_registration", description="❌ Отменить регистрацию"),
        MaxBotCommand(name="help", description="ℹ️ Справка по командам"),
        MaxBotCommand(name="start", description="🚀 Начать работу с ботом"),
        MaxBotCommand(name="add_tournament", description="➕ Добавить новый турнир (админ)"),
        MaxBotCommand(name="delete_tournament", description="❌ Удалить турнир (админ)"),
    ]
    try:
        await max_bot.set_commands(*commands)
        logger.info("✅ Установлены команды для MAX")
    except Exception as e:
        logger.error("❌ Ошибка установки команд MAX: %s", e)


async def run_tg_polling(tg_bot: AsyncTeleBot) -> None:
    """Запуск polling для Telegram."""
    logger.info("🚀 Запуск Telegram polling...")
    await tg_bot.polling(non_stop=True, request_timeout=60)


async def run_max_polling(max_bot: MaxBot, dp: Dispatcher) -> None:
    """Запуск polling для MAX."""
    logger.info("🚀 Запуск MAX polling...")
    await dp.start_polling(max_bot)


async def main() -> None:
    """Главная функция запуска обоих ботов."""
    # Инициализация базы данных
    db = Database(DB_FILE)
    await db.init_db()
    logger.info("✅ База данных инициализирована")

    # Создаем Telegram бота
    tg_bot = create_tg_bot()
    tg_info = await tg_bot.get_me()
    tg_username = tg_info.username
    logger.info("🤖 Telegram бот: @%s", tg_username)
    await set_tg_commands(tg_bot)

    # Создаем MAX бота
    max_bot = await init_max_bot()
    await set_max_commands(max_bot)

    # Инициализируем глобальный контекст
    init_context(
        db=db,
        tg_bot=tg_bot,
        max_bot=max_bot,
        tg_username=tg_username,
        max_username=(await max_bot.get_me()).username
    )

    # Регистрируем обработчики для Telegram
    register_tg_registration()
    register_tg_admin()

    # Регистрируем обработчики для MAX
    register_common_max()
    register_admin_max()
    register_registration_max()

    # Создаем диспетчер для MAX и подключаем роутеры
    dp = Dispatcher()
    dp.include_routers(
        common_max_router,
        admin_max_router,
        registration_max_router
    )

    logger.info("🚀 Бот запущен! Нажмите Ctrl+C для остановки")

    try:
        tg_task = asyncio.create_task(run_tg_polling(tg_bot))
        max_task = asyncio.create_task(run_max_polling(max_bot, dp))
        await asyncio.gather(tg_task, max_task, return_exceptions=True)
    except KeyboardInterrupt:
        logger.info("👋 Остановка по Ctrl+C")
    except Exception as e:
        logger.error("❌ Ошибка: %s", e)
    finally:
        if tg_bot:
            try:
                await tg_bot.close()
            except Exception:
                pass
        if max_bot:
            try:
                await max_bot.close_session()
            except Exception:
                pass
        logger.info("✅ Боты остановлены")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
