"""
Telegram бот для регистрации на турниры.
Позволяет регистрировать участников, просматривать списки и отменять регистрации.
"""
import sqlite3
import logging
import signal
import json
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, List, Optional, Generator, Any

from telebot import TeleBot, types
from instance.config import (
    ACCESS_TOKEN,
    GROUP_CHAT_ID,
    ADMIN_USER_IDS,
    LOG_FILE,
    DB_FILE,
    POLLING_TIMEOUT
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

# Состояния для регистрации турниров и сбора данных
ADDING_TOURNAMENT_NAME = 1
ADDING_TOURNAMENT_DATE = 2
ASKING_FULL_NAME = 3
ASKING_CITY = 4
CONFIRM_CANCEL = 5

# Хранилище состояний и данных пользователей
user_states: Dict[int, int] = {}
user_data: Dict[int, Dict] = {}
temp_registration: Dict[int, Dict] = {}
cancel_data: Dict[int, Dict] = {}


class Database:
    """Класс для работы с базой данных SQLite"""

    def __init__(self, db_name: str = DB_FILE):
        self.db_name = db_name
        self.init_db()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self) -> None:
        """Инициализация таблиц в базе данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица турниров
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tournaments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    created_by INTEGER NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            ''')

            # Таблица участников
            cursor.execute('''
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

            conn.commit()

    def add_tournament(self, name: str, date: str, created_by: int) -> int:
        """Добавление нового турнира"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tournaments (name, date, created_at, created_by) VALUES (?, ?, ?, ?)",
                (name, date, datetime.now().isoformat(), created_by)
            )
            conn.commit()
            return cursor.lastrowid

    def get_tournaments(self, only_active: bool = True) -> List[Dict[str, Any]]:
        """Получение списка турниров"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if only_active:
                cursor.execute(
                    "SELECT * FROM tournaments WHERE is_active = 1 AND date >= date('now') ORDER BY date"
                )
            else:
                cursor.execute("SELECT * FROM tournaments ORDER BY date")

            tournaments = []
            for row in cursor.fetchall():
                tournaments.append(dict(row))
            return tournaments

    def get_tournament(self, tournament_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о турнире"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_tournament(self, tournament_id: int) -> None:
        """Удаление турнира (мягкое удаление)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tournaments SET is_active = 0 WHERE id = ?",
                (tournament_id,)
            )
            conn.commit()

    def register_participant(self, tournament_id: int, registered_by: int,
                             full_name: str, city: str) -> bool:
        """Регистрация участника на турнир"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO participants
                       (tournament_id, registered_by, full_name, city, registered_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (tournament_id, registered_by, full_name, city, datetime.now().isoformat())
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error("Ошибка при регистрации: %s", e)
            return False

    def cancel_registration(self, registration_id: int, registered_by: int) -> bool:
        """Отмена регистрации участника (только свои регистрации)"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM participants WHERE id = ? AND registered_by = ?",
                    (registration_id, registered_by)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error("Ошибка при отмене регистрации: %s", e)
            return False

    def get_participants(self, tournament_id: int) -> List[Dict[str, Any]]:
        """Получение списка участников турнира"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *
                FROM participants
                WHERE tournament_id = ?
                ORDER BY registered_at
            ''', (tournament_id,))

            participants = []
            for row in cursor.fetchall():
                participants.append(dict(row))
            return participants

    def get_user_registrations(self, registered_by: int) -> List[Dict[str, Any]]:
        """Получение списка регистраций, сделанных пользователем"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*, t.name as tournament_name, t.date as tournament_date
                FROM participants p
                JOIN tournaments t ON p.tournament_id = t.id
                WHERE p.registered_by = ?
                  AND t.is_active = 1
                  AND t.date >= date('now')
                ORDER BY t.date, p.registered_at
            ''', (registered_by,))

            registrations = []
            for row in cursor.fetchall():
                registrations.append(dict(row))
            return registrations

    def get_registration_count(self, tournament_id: int) -> int:
        """Получение количества участников на турнире"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM participants WHERE tournament_id = ?",
                (tournament_id,)
            )
            row = cursor.fetchone()
            return row['count'] if row else 0

    def get_tournament_id_by_registration(self, registration_id: int) -> Optional[int]:
        """Получение ID турнира по ID регистрации"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tournament_id FROM participants WHERE id = ?",
                (registration_id,)
            )
            row = cursor.fetchone()
            return row['tournament_id'] if row else None


# Инициализация бота и базы данных
bot = TeleBot(ACCESS_TOKEN)
db = Database()


def get_user_display_name(user) -> str:
    """Получение отображаемого имени пользователя"""
    if user.username:
        return f"@{user.username}"
    if user.first_name or user.last_name:
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    return f"ID: {user.id}"


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_USER_IDS


def log_user_action(user, action: str, details: Dict = None) -> None:
    """Логирование действий пользователя"""
    log_message = f"👤 Пользователь: {get_user_display_name(user)} (ID: {user.id}) | Действие: {action}"
    if details:
        log_message += f" | Подробности: {json.dumps(details, ensure_ascii=False)}"
    logger.info(log_message)


def get_tournaments_keyboard(tournaments_list: List[Dict], callback_data_prefix: str) -> types.InlineKeyboardMarkup:
    """Создание клавиатуры со списком турниров"""
    keyboard = types.InlineKeyboardMarkup()
    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        count = db.get_registration_count(tournament['id'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {count} уч."
        button = types.InlineKeyboardButton(
            button_text,
            callback_data=f"{callback_data_prefix}_{tournament['id']}"
        )
        keyboard.add(button)
    return keyboard


def handle_registration_callback(call: types.CallbackQuery, data: str, user_id: int, user) -> None:
    """Обработка callback для регистрации"""
    tournament_id = int(data.split('_')[1])
    tournament = db.get_tournament(tournament_id)

    if not tournament:
        log_user_action(user, "register_failed_tournament_not_found", {
            "tournament_id": tournament_id
        })
        bot.answer_callback_query(call.id, "❌ Турнир не найден.")
        return

    log_user_action(user, "register_new_participant_start", {
        "tournament_id": tournament_id,
        "tournament_name": tournament['name']
    })

    temp_registration[user_id] = {'tournament_id': tournament_id}
    user_states[user_id] = ASKING_FULL_NAME

    bot.edit_message_text(
        "Введите ФИО участника (например: Иванов Иван Иванович):",
        call.message.chat.id,
        call.message.message_id
    )


def handle_view_callback(call: types.CallbackQuery, data: str, user) -> None:
    """Обработка callback для просмотра участников"""
    tournament_id = int(data.split('_')[1])
    tournament = db.get_tournament(tournament_id)

    log_user_action(user, "view_participants", {
        "tournament_id": tournament_id,
        "tournament_name": tournament['name'] if tournament else "Unknown"
    })

    show_participants(call, tournament_id)


def handle_cancel_callback(call: types.CallbackQuery, data: str, user_id: int, _user) -> None:
    """Обработка callback для отмены регистрации (начало)"""
    registration_id = int(data.split('_')[1])

    cancel_data[user_id] = {'registration_id': registration_id}
    user_states[user_id] = CONFIRM_CANCEL

    keyboard = types.InlineKeyboardMarkup()
    yes_button = types.InlineKeyboardButton(
        "✅ Да, отменить",
        callback_data=f"cancel_confirm_{registration_id}"
    )
    no_button = types.InlineKeyboardButton("❌ Нет, оставить", callback_data="cancel_all")
    keyboard.add(yes_button, no_button)

    bot.edit_message_text(
        "Вы уверены, что хотите отменить эту регистрацию?",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=keyboard
    )


def handle_cancel_confirm_callback(call: types.CallbackQuery, data: str, user_id: int, user) -> None:
    """Обработка callback для подтверждения отмены регистрации"""
    registration_id = int(data.split('_')[2])

    tournament_id = db.get_tournament_id_by_registration(registration_id)
    success = db.cancel_registration(registration_id, user_id)

    if success:
        log_user_action(user, "cancel_registration_success", {
            "registration_id": registration_id
        })

        bot.answer_callback_query(call.id, "✅ Регистрация отменена!")
        bot.edit_message_text(
            "✅ Регистрация успешно отменена.",
            call.message.chat.id,
            call.message.message_id
        )

        if tournament_id:
            send_participants_to_group(tournament_id)
    else:
        log_user_action(user, "cancel_registration_failed", {
            "registration_id": registration_id
        })
        bot.answer_callback_query(call.id, "❌ Не удалось отменить регистрацию.")

    user_states.pop(user_id, None)
    cancel_data.pop(user_id, None)


def handle_delete_callback(call: types.CallbackQuery, data: str, user_id: int, user) -> None:
    """Обработка callback для удаления турнира"""
    if not is_admin(user_id):
        log_user_action(user, "delete_tournament_unauthorized", {
            "tournament_id": int(data.split('_')[1])
        })
        bot.answer_callback_query(call.id, "⛔ У вас нет прав для удаления турниров.")
        return

    tournament_id = int(data.split('_')[1])
    tournament = db.get_tournament(tournament_id)

    if tournament:
        db.delete_tournament(tournament_id)

        log_user_action(user, "delete_tournament_success", {
            "tournament_id": tournament_id,
            "tournament_name": tournament['name'],
            "participants_count": db.get_registration_count(tournament_id)
        })

        bot.answer_callback_query(call.id, "✅ Турнир удален!")
        bot.edit_message_text(
            f"✅ Турнир '{tournament['name']}' успешно удален.",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        log_user_action(user, "delete_tournament_failed_not_found", {
            "tournament_id": tournament_id
        })
        bot.answer_callback_query(call.id, "❌ Турнир не найден.")


@bot.message_handler(commands=['start'])
def start(message: types.Message) -> None:
    """Обработчик команды /start"""
    user = message.from_user
    log_user_action(user, "start_command")

    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для регистрации на турниры. Вот что я умею:\n\n"
        "📝 /register - зарегистрировать участника на турнир\n"
        "👥 /participants - посмотреть участников турнира\n"
        "✅ /my_registrations - показать мои регистрации\n"
        "❌ /cancel_registration - отменить свою регистрацию\n"
        "ℹ️ /help - показать справку\n\n"
    )

    if is_admin(user.id):
        welcome_message += (
            "Для администраторов:\n"
            "➕ /add_tournament - добавить новый турнир\n"
            "❌ /delete_tournament - удалить турнир\n"
        )

    bot.reply_to(message, welcome_message)


@bot.message_handler(commands=['help'])
def help_command(message: types.Message) -> None:
    """Обработчик команды /help"""
    user = message.from_user
    user_id = user.id

    log_user_action(user, "help_command")

    help_text = (
        "📚 Справка по командам:\n\n"
        "Для всех пользователей:\n"
        "/start - начать работу с ботом\n"
        "/register - зарегистрировать участника на турнир\n"
        "/participants - посмотреть участников турнира\n"
        "/my_registrations - ваши регистрации\n"
        "/cancel_registration - отменить свою регистрацию\n"
        "/help - эта справка\n\n"
    )

    if is_admin(user_id):
        help_text += (
            "Для администраторов:\n"
            "/add_tournament - добавить новый турнир\n"
            "/delete_tournament - удалить турнир\n"
        )

    bot.reply_to(message, help_text)


@bot.message_handler(commands=['register'])
def register_command(message: types.Message) -> None:
    """Показать список доступных турниров для регистрации"""
    user = message.from_user
    tournaments_list = db.get_tournaments()

    log_user_action(user, "register_command", {"tournaments_count": len(tournaments_list)})

    if not tournaments_list:
        bot.reply_to(message, "📭 На данный нет активных турниров для регистрации.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')})"
        callback_data = f"reg_{tournament['id']}"

        button = types.InlineKeyboardButton(button_text, callback_data=callback_data)
        keyboard.add(button)

    bot.send_message(message.chat.id, "🏆 Выберите турнир для регистрации участника:", reply_markup=keyboard)


@bot.message_handler(commands=['participants'])
def participants_command(message: types.Message) -> None:
    """Показать список турниров для просмотра участников"""
    user = message.from_user
    tournaments_list = db.get_tournaments()

    log_user_action(user, "participants_command", {"tournaments_count": len(tournaments_list)})

    if not tournaments_list:
        bot.reply_to(message, "Нет активных турниров.")
        return

    keyboard = get_tournaments_keyboard(tournaments_list, "view")
    bot.send_message(message.chat.id, "👥 Выберите турнир для просмотра участников:", reply_markup=keyboard)


@bot.message_handler(commands=['my_registrations'])
def my_registrations(message: types.Message) -> None:
    """Показать регистрации, сделанные пользователем"""
    user = message.from_user
    user_id = user.id
    registrations = db.get_user_registrations(user_id)

    log_user_action(user, "my_registrations_command", {"registrations_count": len(registrations)})

    if not registrations:
        bot.reply_to(message, "📭 Вы еще никого не зарегистрировали на турниры.")
        return

    text = "📋 Ваши регистрации:\n\n"
    current_tournament = None

    for reg in registrations:
        if current_tournament != reg['tournament_name']:
            current_tournament = reg['tournament_name']
            date_obj = datetime.fromisoformat(reg['tournament_date'])
            text += f"\n🏆 {reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}):\n"

        text += f"   • {reg['full_name']} ({reg['city']})\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['cancel_registration'])
def cancel_registration_start(message: types.Message) -> None:
    """Показать список регистраций для отмены"""
    user = message.from_user
    user_id = user.id
    registrations = db.get_user_registrations(user_id)

    log_user_action(user, "cancel_registration_start", {"registrations_count": len(registrations)})

    if not registrations:
        bot.reply_to(message, "📭 У вас нет активных регистраций для отмены.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for reg in registrations:
        date_obj = datetime.fromisoformat(reg['tournament_date'])
        button_text = f"{reg['tournament_name']} ({date_obj.strftime('%d.%m.%Y')}) - {reg['full_name']}"
        callback_data = f"cancel_{reg['id']}"
        button = types.InlineKeyboardButton(button_text, callback_data=callback_data)
        keyboard.add(button)

    cancel_all_button = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_all")
    keyboard.add(cancel_all_button)

    bot.send_message(
        message.chat.id,
        "Выберите регистрацию для отмены:",
        reply_markup=keyboard
    )


@bot.message_handler(commands=['add_tournament'])
def add_tournament_start(message: types.Message) -> None:
    """Начало добавления турнира (только для админа)"""
    user = message.from_user

    if not is_admin(user.id):
        log_user_action(user, "add_tournament_unauthorized")
        bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
        return

    log_user_action(user, "add_tournament_start")

    user_states[user.id] = ADDING_TOURNAMENT_NAME
    bot.reply_to(message, "Введите название турнира:")


@bot.message_handler(commands=['delete_tournament'])
def delete_tournament_start(message: types.Message) -> None:
    """Начало удаления турнира (только для админа)"""
    user = message.from_user

    if not is_admin(user.id):
        log_user_action(user, "delete_tournament_unauthorized")
        bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
        return

    tournaments_list = db.get_tournaments()

    log_user_action(user, "delete_tournament_start", {"tournaments_count": len(tournaments_list)})

    if not tournaments_list:
        bot.reply_to(message, "Нет активных турниров для удаления.")
        return

    keyboard = get_tournaments_keyboard(tournaments_list, "del")
    cancel_button = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")
    keyboard.add(cancel_button)

    bot.send_message(message.chat.id, "Выберите турнир для удаления:", reply_markup=keyboard)


def show_participants(call: types.CallbackQuery, tournament_id: int) -> None:
    """Показать список участников турнира"""
    tournament = db.get_tournament(tournament_id)
    if not tournament:
        bot.edit_message_text(
            "❌ Турнир не найден.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    participants = db.get_participants(tournament_id)

    date_obj = datetime.fromisoformat(tournament['date'])
    text = f"🏆 Турнир: {tournament['name']}\n"
    text += f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
    text += f"👥 Участников: {len(participants)}\n\n"

    if participants:
        for i, participant in enumerate(participants, 1):
            text += f"{i}. {participant['full_name']} ({participant['city']})\n"
    else:
        text += "Пока нет зарегистрированных участников."

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id
    )


def send_participants_to_group(tournament_id: int) -> None:
    """Отправка списка участников в группу"""
    tournament = db.get_tournament(tournament_id)
    if not tournament:
        return

    participants = db.get_participants(tournament_id)

    date_obj = datetime.fromisoformat(tournament['date'])
    text = "📢 <b>Обновление списка участников!</b>\n\n"
    text += f"🏆 Турнир: {tournament['name']}\n"
    text += f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
    text += f"👥 Всего участников: {len(participants)}\n\n"

    if participants:
        text += "Список участников:\n"
        for i, participant in enumerate(participants, 1):
            text += f"{i}. {participant['full_name']} ({participant['city']})\n"
    else:
        text += "Пока нет зарегистрированных участников."

    try:
        bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode='HTML',
            reply_markup=get_group_message_markup()
        )
        logger.info("Отправлено обновление участников в группу для турнира %s", tournament['name'])
    except Exception as e:
        logger.error("Ошибка при отправке в группу: %s", e)

def send_tournament_info_to_group(tournament_id: int) -> None:
    """Отправка информации о созданном турнире в группу"""
    tournament = db.get_tournament(tournament_id)
    if not tournament:
        return

    date_obj = datetime.fromisoformat(tournament['date'])
    text = "📢 <b>Начата запись на турнир!</b>\n\n"
    text += f"🏆 Турнир: {tournament['name']}\n"
    text += f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"

    try:
        bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode='HTML',
            reply_markup=get_group_message_markup()
        )
        logger.info("Отправлена информация о начале записи на турнир в группу для турнира %s", tournament['name'])
    except Exception as e:
        logger.error("Ошибка при отправке в группу: %s", e)

def get_group_message_markup():
    """Формирование кнопки с открытием бота в сообщение группе"""
    keyboard = types.InlineKeyboardMarkup(keyboard=[
        [types.InlineKeyboardButton(text="Регистрация", url="t.me/ttc_etalon_bot")]
    ])
    return keyboard

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call: types.CallbackQuery) -> None:
    """Обработка нажатий на инлайн-кнопки"""
    try:
        data = call.data
        user = call.from_user
        user_id = user.id

        log_user_action(user, "button_click", {"button_data": data})

        if data.startswith('reg_'):
            handle_registration_callback(call, data, user_id, user)

        elif data.startswith('view_'):
            handle_view_callback(call, data, user)

        elif data.startswith('cancel_') \
                and data not in ('cancel_all', 'cancel_confirm_') \
                and not data.startswith('cancel_confirm_'):
            handle_cancel_callback(call, data, user_id, user)

        elif data.startswith('cancel_confirm_'):
            handle_cancel_confirm_callback(call, data, user_id, user)

        elif data == "cancel_all":
            user_states.pop(user_id, None)
            cancel_data.pop(user_id, None)

            bot.answer_callback_query(call.id, "❌ Действие отменено.")
            bot.edit_message_text(
                "❌ Действие отменено.",
                call.message.chat.id,
                call.message.message_id
            )

        elif data.startswith('del_'):
            handle_delete_callback(call, data, user_id, user)

        elif data == "cancel_delete":
            log_user_action(user, "delete_tournament_cancelled")
            bot.answer_callback_query(call.id, "❌ Удаление отменено.")
            bot.edit_message_text(
                "❌ Удаление отменено.",
                call.message.chat.id,
                call.message.message_id
            )

    except Exception as e:
        logger.error("Ошибка в callback_handler: %s", e)
        bot.answer_callback_query(call.id, "❌ Произошла ошибка.")


def handle_tournament_name_input(user_id: int, message: types.Message) -> None:
    """Обработка ввода названия турнира"""
    user_data[user_id] = {'tournament_name': message.text}
    user_states[user_id] = ADDING_TOURNAMENT_DATE

    log_user_action(message.from_user, "add_tournament_name_entered", {"tournament_name": message.text})

    bot.reply_to(
        message,
        "Теперь введите дату турнира в формате ДД.ММ.ГГГГ\n"
        "Например: 25.12.2024"
    )


def handle_tournament_date_input(user_id: int, message: types.Message) -> None:
    """Обработка ввода даты турнира"""
    try:
        date_str = message.text
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")

        date_with_time = datetime.combine(date_obj.date(), datetime.min.time()).isoformat()

        tournament_name = user_data.get(user_id, {}).get('tournament_name', 'Турнир')
        tournament_id = db.add_tournament(tournament_name, date_with_time, user_id)

        log_user_action(message.from_user, "add_tournament_success", {
            "tournament_name": tournament_name,
            "tournament_date": date_str,
            "tournament_id": tournament_id
        })

        bot.reply_to(
            message,
            f"✅ Турнир '{tournament_name}' на {date_obj.strftime('%d.%m.%Y')} успешно добавлен!"
        )

        user_states.pop(user_id, None)
        user_data.pop(user_id, None)

    except ValueError:
        log_user_action(message.from_user, "add_tournament_invalid_date", {"entered_date": message.text})
        bot.reply_to(
            message,
            "❌ Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ\n"
            "Например: 25.12.2024"
        )


def handle_full_name_input(user_id: int, message: types.Message) -> None:
    """Обработка ввода ФИО участника"""
    temp_registration[user_id] = temp_registration.get(user_id, {})
    temp_registration[user_id]['full_name'] = message.text
    user_states[user_id] = ASKING_CITY

    log_user_action(message.from_user, "participant_data_entered", {"field": "full_name"})

    bot.reply_to(message, "Введите город, который представляет участник:")


def handle_city_input(user_id: int, message: types.Message) -> None:
    """Обработка ввода города участника"""
    try:
        data = temp_registration.get(user_id, {})
        if not data or 'full_name' not in data:
            log_user_action(message.from_user, "registration_error_missing_data")
            bot.reply_to(message, "❌ Ошибка данных. Начните регистрацию заново через /register")
            user_states.pop(user_id, None)
            temp_registration.pop(user_id, None)
            return

        tournament_id = data['tournament_id']
        full_name = data['full_name']
        city = message.text

        success = db.register_participant(tournament_id, user_id, full_name, city)

        if success:
            tournament = db.get_tournament(tournament_id)

            log_user_action(message.from_user, "registration_complete", {
                "tournament_id": tournament_id,
                "tournament_name": tournament['name'],
                "participant_name": full_name
            })

            participant_text = (
                f"✅ Участник успешно зарегистрирован!\n\n"
                f"🏆 Турнир: {tournament['name']}\n"
                f"📅 Дата: {datetime.fromisoformat(tournament['date']).strftime('%d.%m.%Y')}\n\n"
                f"Данные участника:\n"
                f"• {full_name}\n"
                f"• {city}"
            )

            bot.reply_to(message, participant_text)

            send_participants_to_group(tournament_id)
        else:
            log_user_action(message.from_user, "registration_failed_db_error")
            bot.reply_to(message, "❌ Не удалось зарегистрировать участника. Попробуйте позже.")

        user_states.pop(user_id, None)
        temp_registration.pop(user_id, None)

    except Exception as e:
        logger.error("Ошибка при регистрации: %s", e)
        log_user_action(message.from_user, "registration_error", {"error": str(e)})
        bot.reply_to(message, "❌ Произошла ошибка при регистрации. Попробуйте позже.")

        user_states.pop(user_id, None)
        temp_registration.pop(user_id, None)


@bot.message_handler(func=lambda message: True)
def handle_messages(message: types.Message) -> None:
    """Обработка всех остальных сообщений"""
    user = message.from_user
    user_id = user.id
    state = user_states.get(user_id)

    if state == ADDING_TOURNAMENT_NAME:
        if not is_admin(user_id):
            log_user_action(user, "unauthorized_tournament_add_attempt", {"message": message.text[:50]})
            bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
            user_states.pop(user_id, None)
            return
        handle_tournament_name_input(user_id, message)

    elif state == ADDING_TOURNAMENT_DATE:
        if not is_admin(user_id):
            log_user_action(user, "unauthorized_tournament_add_attempt", {"message": message.text[:50]})
            bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
            user_states.pop(user_id, None)
            return
        handle_tournament_date_input(user_id, message)

    elif state == ASKING_FULL_NAME:
        handle_full_name_input(user_id, message)

    elif state == ASKING_CITY:
        handle_city_input(user_id, message)


def signal_term_handler(signum, *_args) -> None:
    """Обработка сигнала о прерывание процесса"""
    logger.info('Бот остановлен сигналом: %s', signum)
    bot.stop_polling()


if __name__ == '__main__':
    logger.info("Бот запущен...")
    logger.info("Администраторы: %s", ADMIN_USER_IDS)
    logger.info("Таймаут polling: %s секунд", POLLING_TIMEOUT)

    signal.signal(signal.SIGTERM, signal_term_handler)

    bot.infinity_polling(timeout=POLLING_TIMEOUT, logger_level=logging.INFO)
    logger.info('Бот остановлен')
