# database/db.py
import sqlite3
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name: str = "tournaments.db"):
        self.db_name = db_name

    async def _execute(self, query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
        """Асинхронная обертка для выполнения SQL-запросов."""

        def _sync_execute():
            conn = sqlite3.connect(self.db_name)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            if fetchone:
                result = cursor.fetchone()
            elif fetchall:
                result = cursor.fetchall()
            else:
                result = None
            conn.commit()
            conn.close()
            return result

        return await asyncio.to_thread(_sync_execute)

    async def init_db(self):
        """Инициализация таблиц."""
        await self._execute('''
                            CREATE TABLE IF NOT EXISTS tournaments
                            (
                                id
                                INTEGER
                                PRIMARY
                                KEY
                                AUTOINCREMENT,
                                name
                                TEXT
                                NOT
                                NULL,
                                date
                                TEXT
                                NOT
                                NULL,
                                created_at
                                TEXT
                                NOT
                                NULL,
                                created_by
                                INTEGER
                                NOT
                                NULL,
                                is_active
                                INTEGER
                                DEFAULT
                                1
                            )
                            ''')
        await self._execute('''
                            CREATE TABLE IF NOT EXISTS participants
                            (
                                id
                                INTEGER
                                PRIMARY
                                KEY
                                AUTOINCREMENT,
                                tournament_id
                                INTEGER
                                NOT
                                NULL,
                                registered_by
                                INTEGER
                                NOT
                                NULL,
                                full_name
                                TEXT
                                NOT
                                NULL,
                                city
                                TEXT
                                NOT
                                NULL,
                                registered_at
                                TEXT
                                NOT
                                NULL,
                                FOREIGN
                                KEY
                            (
                                tournament_id
                            ) REFERENCES tournaments
                            (
                                id
                            ) ON DELETE CASCADE
                                )
                            ''')
        logger.info("✅ База данных инициализирована")

    async def add_tournament(self, name: str, date: str, created_by: int) -> int:
        """Добавление нового турнира."""
        try:
            # Вставляем запись
            query = "INSERT INTO tournaments (name, date, created_at, created_by) VALUES (?, ?, ?, ?)"
            params = (name, date, datetime.now().isoformat(), created_by)
            await self._execute(query, params)

            # Получаем ID через отдельный запрос в том же соединении
            # Используем другой подход - получаем последний ID через SELECT
            result = await self._execute("SELECT last_insert_rowid() as id", fetchone=True)

            if result and result['id']:
                tournament_id = result['id']
                logger.info(f"✅ Турнир добавлен с ID: {tournament_id}")
                return tournament_id
            else:
                # Если last_insert_rowid не сработал, пробуем получить максимальный ID
                max_result = await self._execute("SELECT MAX(id) as id FROM tournaments", fetchone=True)
                if max_result and max_result['id']:
                    logger.info(f"✅ Турнир добавлен с ID (MAX): {max_result['id']}")
                    return max_result['id']
                else:
                    logger.error("❌ Не удалось получить ID добавленного турнира")
                    return 0
        except Exception as e:
            logger.error(f"❌ Ошибка добавления турнира: {e}")
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
        logger.info(f"✅ Турнир с ID {tournament_id} удален (мягкое удаление)")

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
            logger.error(f"❌ Ошибка регистрации участника: {e}")
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
            logger.error(f"❌ Ошибка отмены регистрации: {e}")
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
                WHERE p.registered_by = ? \
                  AND t.is_active = 1 \
                  AND t.date >= date ('now')
                ORDER BY t.date, p.registered_at \
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
