"""Асинхронный слой доступа к базе данных турниров."""
import sqlite3
import asyncio
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class Database:
    """Асинхронная обёртка над SQLite для хранения турниров и участников."""

    def __init__(self, db_name: str = "tournaments.db"):
        # Определяем путь к БД
        if os.path.isabs(db_name):
            self.db_name = db_name
        else:
            # Получаем директорию проекта
            current_dir = os.path.dirname(os.path.abspath(__file__))  # database/
            project_dir = os.path.dirname(current_dir)                # корень проекта

            # Создаем поддиректорию data, если её нет
            data_dir = os.path.join(project_dir, "data")
            os.makedirs(data_dir, exist_ok=True)

            self.db_name = os.path.join(data_dir, db_name)

        self._lock = asyncio.Lock()
        logger.info("📁 Путь к БД: %s", self.db_name)

    async def _execute(self, query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
        """Асинхронная обертка для выполнения SQL-запросов с блокировкой."""

        async with self._lock:
            def _sync_execute():
                conn = None
                try:
                    conn = sqlite3.connect(self.db_name, timeout=30.0)
                    conn.row_factory = sqlite3.Row

                    # Включаем WAL-режим для лучшей конкурентности
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")

                    cursor = conn.cursor()
                    cursor.execute(query, params)

                    if fetchone:
                        result = cursor.fetchone()
                    elif fetchall:
                        result = cursor.fetchall()
                    else:
                        result = None

                    conn.commit()
                    logger.info("✅ Выполнен запрос: %s...", query[:100])
                    return result

                except sqlite3.OperationalError as e:
                    logger.error("❌ Ошибка SQLite: %s", e)
                    logger.error("   Запрос: %s...", query[:100])
                    logger.error("   Файл БД: %s", self.db_name)
                    raise
                finally:
                    if conn:
                        conn.close()

            return await asyncio.to_thread(_sync_execute)

    async def init_db(self):
        """Инициализация таблиц."""
        await self._execute('''
            CREATE TABLE IF NOT EXISTS tournaments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')
        await self._execute('''
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tournament_id INTEGER NOT NULL,
                registered_by INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                city TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                FOREIGN KEY (tournament_id) REFERENCES tournaments (id) ON DELETE CASCADE
            )
        ''')
        logger.info("✅ База данных инициализирована")

    async def add_tournament(self, name: str, date: str, created_by: int) -> int:
        """Добавление нового турнира."""
        try:
            query = "INSERT INTO tournaments (name, date, created_at, created_by) VALUES (?, ?, ?, ?)"
            params = (name, date, datetime.now().isoformat(), created_by)
            await self._execute(query, params)

            result = await self._execute("SELECT last_insert_rowid() as id", fetchone=True)
            if result and result['id']:
                tournament_id = result['id']
                logger.info("✅ Турнир добавлен с ID: %s", tournament_id)
                return tournament_id

            max_result = await self._execute("SELECT MAX(id) as id FROM tournaments", fetchone=True)
            if max_result and max_result['id']:
                logger.info("✅ Турнир добавлен с ID (MAX): %s", max_result['id'])
                return max_result['id']
            return 0
        except Exception as e:
            logger.error("❌ Ошибка добавления турнира: %s", e)
            return 0

    async def get_tournaments(self, only_active: bool = True) -> List[Dict[str, Any]]:
        """Получение списка турниров."""
        if only_active:
            query = "SELECT * FROM tournaments WHERE is_active = 1 AND date >= date('now') ORDER BY date"
        else:
            query = "SELECT * FROM tournaments ORDER BY date"
        rows = await self._execute(query, fetchall=True)
        return [dict(row) for row in rows] if rows else []

    async def get_tournament(self, tournament_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о турнире."""
        query = "SELECT * FROM tournaments WHERE id = ?"
        row = await self._execute(query, (tournament_id,), fetchone=True)
        return dict(row) if row else None

    async def delete_tournament(self, tournament_id: int) -> None:
        """Мягкое удаление турнира."""
        query = "UPDATE tournaments SET is_active = 0 WHERE id = ?"
        await self._execute(query, (tournament_id,))

    async def register_participant(self, tournament_id: int, registered_by: int, full_name: str, city: str) -> bool:
        """Регистрация участника."""
        try:
            query = """INSERT INTO participants
                       (tournament_id, registered_by, full_name, city, registered_at)
                       VALUES (?, ?, ?, ?, ?)"""
            params = (tournament_id, registered_by, full_name, city, datetime.now().isoformat())
            await self._execute(query, params)
            return True
        except Exception as e:
            logger.error("❌ Ошибка регистрации: %s", e)
            return False

    async def cancel_registration(self, registration_id: int, registered_by: int) -> bool:
        """Отмена регистрации (только свои)."""
        try:
            query = "DELETE FROM participants WHERE id = ? AND registered_by = ?"
            await self._execute(query, (registration_id, registered_by))
            check_query = "SELECT COUNT(*) as cnt FROM participants WHERE id = ? AND registered_by = ?"
            row = await self._execute(check_query, (registration_id, registered_by), fetchone=True)
            return row['cnt'] == 0 if row else False
        except Exception as e:
            logger.error("❌ Ошибка отмены: %s", e)
            return False

    async def get_participants(self, tournament_id: int) -> List[Dict[str, Any]]:
        """Список участников турнира."""
        query = "SELECT * FROM participants WHERE tournament_id = ? ORDER BY registered_at"
        rows = await self._execute(query, (tournament_id,), fetchall=True)
        return [dict(row) for row in rows] if rows else []

    async def get_user_registrations(self, registered_by: int) -> List[Dict[str, Any]]:
        """Регистрации пользователя."""
        query = '''
            SELECT p.*, t.name as tournament_name, t.date as tournament_date
            FROM participants p
            JOIN tournaments t ON p.tournament_id = t.id
            WHERE p.registered_by = ? AND t.is_active = 1 AND t.date >= date('now')
            ORDER BY t.date, p.registered_at
        '''
        rows = await self._execute(query, (registered_by,), fetchall=True)
        return [dict(row) for row in rows] if rows else []

    async def get_registration_count(self, tournament_id: int) -> int:
        """Количество участников."""
        query = "SELECT COUNT(*) as count FROM participants WHERE tournament_id = ?"
        row = await self._execute(query, (tournament_id,), fetchone=True)
        return row['count'] if row else 0

    async def get_tournament_id_by_registration(self, registration_id: int) -> Optional[int]:
        """ID турнира по ID регистрации."""
        query = "SELECT tournament_id FROM participants WHERE id = ?"
        row = await self._execute(query, (registration_id,), fetchone=True)
        return row['tournament_id'] if row else None
