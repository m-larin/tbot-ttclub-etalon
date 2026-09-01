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
_DB: Optional[Database] = None
_TG_BOT: Optional[AsyncTeleBot] = None
_MAX_BOT: Optional[MaxBot] = None
_TG_BOT_USERNAME: Optional[str] = None
_MAX_BOT_USERNAME: Optional[str] = None


def init_context(db: Database, tg_bot: AsyncTeleBot, max_bot: MaxBot,
                 tg_username: str, max_username: str) -> None:
    """
    Инициализация глобального контекста.
    Вызывается один раз при запуске бота.
    """
    # Используем globals() вместо global для избежания предупреждения
    globals().update({
        '_DB': db,
        '_TG_BOT': tg_bot,
        '_MAX_BOT': max_bot,
        '_TG_BOT_USERNAME': tg_username,
        '_MAX_BOT_USERNAME': max_username,
    })

    logger.info("✅ Контекст инициализирован")
    # Используем % форматирование вместо f-string
    logger.info("   Telegram бот: @%s", tg_username)
    logger.info("   MAX бот: @%s", max_username)


def get_db() -> Database:
    """Получение экземпляра базы данных."""
    if _DB is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _DB


def get_tg_bot() -> AsyncTeleBot:
    """Получение экземпляра Telegram бота."""
    if _TG_BOT is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _TG_BOT


def get_max_bot() -> MaxBot:
    """Получение экземпляра MAX бота."""
    if _MAX_BOT is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _MAX_BOT


def get_tg_username() -> str:
    """Получение username Telegram бота."""
    if _TG_BOT_USERNAME is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _TG_BOT_USERNAME


def get_max_username() -> str:
    """Получение username MAX бота."""
    if _MAX_BOT_USERNAME is None:
        raise RuntimeError("Контекст не инициализирован. Вызовите init_context()")
    return _MAX_BOT_USERNAME
