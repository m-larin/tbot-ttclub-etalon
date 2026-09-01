# context.py
"""
Глобальный контекст приложения.
Хранит все общие объекты для доступа из любого модуля.
"""

import logging
from typing import Optional
from telebot.async_telebot import AsyncTeleBot
from maxapi import Bot as MaxBot
from database.db import Database

logger = logging.getLogger(__name__)

# Глобальные переменные
_db: Optional[Database] = None
_tg_bot: Optional[AsyncTeleBot] = None
_max_bot: Optional[MaxBot] = None
_tg_bot_username: Optional[str] = None
_max_bot_username: Optional[str] = None

def init_context(db: Database, tg_bot: AsyncTeleBot, max_bot: MaxBot, tg_username: str, max_username: str):
    """
    Инициализация глобального контекста.
    Вызывается один раз при запуске бота.
    """
    global _db, _tg_bot, _max_bot, _tg_bot_username, _max_bot_username
    
    _db = db
    _tg_bot = tg_bot
    _max_bot = max_bot
    _tg_bot_username = tg_username
    _max_bot_username = max_username
    
    logger.info("✅ Контекст инициализирован")
    logger.info(f"   Telegram бот: @{_tg_bot_username}")
    logger.info(f"   MAX бот: @{_max_bot_username}")

def get_db() -> Database:
    """Получение экземпляра базы данных."""
    if _db is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _db

def get_tg_bot() -> AsyncTeleBot:
    """Получение экземпляра Telegram бота."""
    if _tg_bot is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _tg_bot

def get_max_bot() -> MaxBot:
    """Получение экземпляра MAX бота."""
    if _max_bot is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _max_bot

def get_tg_username() -> str:
    """Получение username Telegram бота."""
    if _tg_bot_username is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _tg_bot_username

def get_max_username() -> str:
    """Получение username MAX бота."""
    if _max_bot_username is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _max_bot_username

# Для удобства можно использовать свойства
db = property(get_db)
tg_bot = property(get_tg_bot)
max_bot = property(get_max_bot)
tg_username = property(get_tg_username)
max_username = property(get_max_username)