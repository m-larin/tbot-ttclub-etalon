import telebot
from telebot import types
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager
import logging
import time
import signal
import json
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

# Хранилище состояний и данных пользователей
user_states = {}
user_data = {}
temp_registration = {}  # Временное хранение данных регистрации


# Класс для работы с базой данных
class Database:
    def __init__(self, db_name: str = DB_FILE):
        self.db_name = db_name
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Инициализация таблиц в базе данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица турниров
            cursor.execute('''
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

            # Таблица участников (теперь храним ФИО и город для каждой регистрации)
            cursor.execute('''
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

            conn.commit()

    # Методы для работы с турнирами
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

    def get_tournaments(self, only_active: bool = True) -> List[Dict]:
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

    def get_tournament(self, tournament_id: int) -> Optional[Dict]:
        """Получение информации о турнире"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_tournament(self, tournament_id: int):
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
            logger.error(f"Ошибка при регистрации: {e}")
            return False

    def get_participants(self, tournament_id: int) -> List[Dict]:
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

    def get_user_registrations(self, registered_by: int) -> List[Dict]:
        """Получение списка регистраций, сделанных пользователем"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           SELECT t.*, p.full_name, p.city, p.registered_at as reg_date
                           FROM tournaments t
                                    JOIN participants p ON t.id = p.tournament_id
                           WHERE p.registered_by = ?
                             AND t.is_active = 1
                             AND t.date >= date ('now')
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


# Инициализация бота и базы данных
bot = telebot.TeleBot(ACCESS_TOKEN)
db = Database()


# Вспомогательная функция для получения информации о пользователе
def get_user_display_name(user) -> str:
    """Получение отображаемого имени пользователя"""
    if user.username:
        return f"@{user.username}"
    elif user.first_name or user.last_name:
        return f"{user.first_name or ''} {user.last_name or ''}".strip()
    else:
        return f"ID: {user.id}"


# Вспомогательная функция для проверки прав администратора
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_USER_IDS


# Функция для логирования действий пользователя
def log_user_action(user, action: str, details: Dict = None):
    """Логирование действий пользователя"""
    log_message = f"👤 Пользователь: {get_user_display_name(user)} (ID: {user.id}) | Действие: {action}"
    if details:
        log_message += f" | Подробности: {json.dumps(details, ensure_ascii=False)}"
    logger.info(log_message)


# Функции для работы с ботом
@bot.message_handler(commands=['start'])
def start(message):
    """Обработчик команды /start"""
    user = message.from_user

    # Логируем действие
    log_user_action(user, "start_command")

    welcome_message = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для регистрации на турниры. Вот что я умею:\n\n"
        "📝 /register - зарегистрировать участника на турнир\n"
        "👥 /participants - посмотреть участников турнира\n"
        "✅ /my_registrations - показать мои регистрации\n"
        "ℹ️ /help - показать справку\n\n"
    )

    # Добавляем админские команды в справку, если пользователь администратор
    if is_admin(user.id):
        welcome_message += (
            "Для администраторов:\n"
            "➕ /add_tournament - добавить новый турнир\n"
            "❌ /delete_tournament - удалить турнир\n"
        )

    bot.reply_to(message, welcome_message)


@bot.message_handler(commands=['help'])
def help_command(message):
    """Обработчик команды /help"""
    user = message.from_user
    user_id = user.id

    # Логируем действие
    log_user_action(user, "help_command")

    help_text = (
        "📚 Справка по командам:\n\n"
        "Для всех пользователей:\n"
        "/start - начать работу с ботом\n"
        "/register - зарегистрировать участника на турнир\n"
        "/participants - посмотреть участников турнира\n"
        "/my_registrations - ваши регистрации\n"
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
def register_command(message):
    """Показать список доступных турниров для регистрации"""
    user = message.from_user
    tournaments_list = db.get_tournaments()

    # Логируем действие
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
def participants_command(message):
    """Показать список турниров для просмотра участников"""
    user = message.from_user
    tournaments_list = db.get_tournaments()

    # Логируем действие
    log_user_action(user, "participants_command", {"tournaments_count": len(tournaments_list)})

    if not tournaments_list:
        bot.reply_to(message, "Нет активных турниров.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        count = db.get_registration_count(tournament['id'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {count} уч."
        button = types.InlineKeyboardButton(button_text, callback_data=f"view_{tournament['id']}")
        keyboard.add(button)

    bot.send_message(message.chat.id, "👥 Выберите турнир для просмотра участников:", reply_markup=keyboard)


@bot.message_handler(commands=['my_registrations'])
def my_registrations(message):
    """Показать регистрации, сделанные пользователем"""
    user = message.from_user
    user_id = user.id
    registrations = db.get_user_registrations(user_id)

    # Логируем действие
    log_user_action(user, "my_registrations_command", {"registrations_count": len(registrations)})

    if not registrations:
        bot.reply_to(message, "📭 Вы еще никого не зарегистрировали на турниры.")
        return

    text = "📋 Ваши регистрации:\n\n"
    current_tournament = None

    for reg in registrations:
        if current_tournament != reg['name']:
            current_tournament = reg['name']
            date_obj = datetime.fromisoformat(reg['date'])
            text += f"\n🏆 {reg['name']} ({date_obj.strftime('%d.%m.%Y')}):\n"

        text += f"   • {reg['full_name']} ({reg['city']})\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['add_tournament'])
def add_tournament_start(message):
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
def delete_tournament_start(message):
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

    keyboard = types.InlineKeyboardMarkup()
    for tournament in tournaments_list:
        date_obj = datetime.fromisoformat(tournament['date'])
        count = db.get_registration_count(tournament['id'])
        button_text = f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {count} уч."
        button = types.InlineKeyboardButton(button_text, callback_data=f"del_{tournament['id']}")
        keyboard.add(button)

    cancel_button = types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete")
    keyboard.add(cancel_button)

    bot.send_message(message.chat.id, "Выберите турнир для удаления:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Обработка нажатий на инлайн-кнопки"""
    try:
        data = call.data
        user = call.from_user
        user_id = user.id

        # Логируем нажатие на кнопку
        log_user_action(user, f"button_click", {"button_data": data})

        # Обработка регистрации
        if data.startswith('reg_'):
            tournament_id = int(data.split('_')[1])
            tournament = db.get_tournament(tournament_id)

            if not tournament:
                log_user_action(user, "register_failed_tournament_not_found", {
                    "tournament_id": tournament_id
                })
                bot.answer_callback_query(call.id, "❌ Турнир не найден.")
                return

            # Начинаем сбор данных для регистрации
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

        elif data.startswith('view_'):
            tournament_id = int(data.split('_')[1])
            tournament = db.get_tournament(tournament_id)

            log_user_action(user, "view_participants", {
                "tournament_id": tournament_id,
                "tournament_name": tournament['name'] if tournament else "Unknown"
            })

            show_participants(call, tournament_id)

        elif data.startswith('del_'):
            # Проверяем права администратора
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

                bot.answer_callback_query(call.id, f"✅ Турнир удален!")
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

        elif data == "cancel_delete":
            log_user_action(user, "delete_tournament_cancelled")
            bot.answer_callback_query(call.id, "❌ Удаление отменено.")
            bot.edit_message_text(
                "❌ Удаление отменено.",
                call.message.chat.id,
                call.message.message_id
            )

    except Exception as e:
        logger.error(f"Ошибка в callback_handler: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка.")


def show_participants(call, tournament_id: int):
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
        for i, p in enumerate(participants, 1):
            text += f"{i}. {p['full_name']} ({p['city']})\n"
    else:
        text += "Пока нет зарегистрированных участников."

    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id
    )


def send_participants_to_group(tournament_id: int):
    """Отправка списка участников в группу"""
    tournament = db.get_tournament(tournament_id)
    if not tournament:
        return

    participants = db.get_participants(tournament_id)

    date_obj = datetime.fromisoformat(tournament['date'])
    text = f"📢 <b>Обновление списка участников!</b>\n\n"
    text += f"🏆 Турнир: {tournament['name']}\n"
    text += f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
    text += f"👥 Всего участников: {len(participants)}\n\n"

    if participants:
        text += "Список участников:\n"
        for i, p in enumerate(participants, 1):
            text += f"{i}. {p['full_name']} ({p['city']})\n"
    else:
        text += "Пока нет зарегистрированных участников."

    try:
        bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode='HTML'
        )
        logger.info(f"Отправлено обновление участников в группу для турнира {tournament['name']}")
    except Exception as e:
        logger.error(f"Ошибка при отправке в группу: {e}")


@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    """Обработка всех остальных сообщений"""
    user = message.from_user
    user_id = user.id
    state = user_states.get(user_id)

    # Обработка добавления турнира (админ)
    if state == ADDING_TOURNAMENT_NAME:
        if not is_admin(user_id):
            log_user_action(user, "unauthorized_tournament_add_attempt", {"message": message.text[:50]})
            bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
            del user_states[user_id]
            return

        user_data[user_id] = {'tournament_name': message.text}
        user_states[user_id] = ADDING_TOURNAMENT_DATE

        log_user_action(user, "add_tournament_name_entered", {"tournament_name": message.text})

        bot.reply_to(
            message,
            "Теперь введите дату турнира в формате ДД.ММ.ГГГГ\n"
            "Например: 25.12.2024"
        )

    elif state == ADDING_TOURNAMENT_DATE:
        if not is_admin(user_id):
            log_user_action(user, "unauthorized_tournament_add_attempt", {"message": message.text[:50]})
            bot.reply_to(message, "⛔ У вас нет прав для выполнения этой команды.")
            del user_states[user_id]
            return

        try:
            date_str = message.text
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")

            # Добавляем время 00:00 для совместимости с форматом ISO
            date_with_time = datetime.combine(date_obj.date(), datetime.min.time()).isoformat()

            tournament_name = user_data.get(user_id, {}).get('tournament_name', 'Турнир')
            tournament_id = db.add_tournament(tournament_name, date_with_time, user_id)

            log_user_action(user, "add_tournament_success", {
                "tournament_name": tournament_name,
                "tournament_date": date_str,
                "tournament_id": tournament_id
            })

            bot.reply_to(
                message,
                f"✅ Турнир '{tournament_name}' на {date_obj.strftime('%d.%m.%Y')} успешно добавлен!"
            )

            # Очищаем состояния
            del user_states[user_id]
            del user_data[user_id]

        except ValueError:
            log_user_action(user, "add_tournament_invalid_date", {"entered_date": message.text})
            bot.reply_to(
                message,
                "❌ Неверный формат даты. Пожалуйста, используйте формат ДД.ММ.ГГГГ\n"
                "Например: 25.12.2024"
            )

    # Обработка сбора данных участника при регистрации
    elif state == ASKING_FULL_NAME:
        temp_registration[user_id] = temp_registration.get(user_id, {})
        temp_registration[user_id]['full_name'] = message.text
        user_states[user_id] = ASKING_CITY

        log_user_action(user, "participant_data_entered", {"field": "full_name"})

        bot.reply_to(message, "Введите город, который представляет участник:")

    elif state == ASKING_CITY:
        try:
            data = temp_registration.get(user_id, {})
            if not data or 'full_name' not in data:
                log_user_action(user, "registration_error_missing_data")
                bot.reply_to(message, "❌ Ошибка данных. Начните регистрацию заново через /register")
                del user_states[user_id]
                if user_id in temp_registration:
                    del temp_registration[user_id]
                return

            # Регистрируем участника
            tournament_id = data['tournament_id']
            full_name = data['full_name']
            city = message.text

            success = db.register_participant(tournament_id, user_id, full_name, city)

            if success:
                tournament = db.get_tournament(tournament_id)

                log_user_action(user, "registration_complete", {
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

                # Отправляем обновленный список в группу
                send_participants_to_group(tournament_id)
            else:
                log_user_action(user, "registration_failed_db_error")
                bot.reply_to(message, "❌ Не удалось зарегистрировать участника. Попробуйте позже.")

            # Очищаем временные данные
            del user_states[user_id]
            if user_id in temp_registration:
                del temp_registration[user_id]

        except Exception as e:
            logger.error(f"Ошибка при регистрации: {e}")
            log_user_action(user, "registration_error", {"error": str(e)})
            bot.reply_to(message, "❌ Произошла ошибка при регистрации. Попробуйте позже.")

            # Очищаем временные данные в случае ошибки
            if user_id in user_states:
                del user_states[user_id]
            if user_id in temp_registration:
                del temp_registration[user_id]


def signal_term_handler(sig_num, frame):
    """Обработка сигнала о прерывание процесса"""
    logger.info('Бот остановлен сигналом: %s; frame: %s', sig_num, frame)
    bot.stop_polling()


# Запуск бота
if __name__ == '__main__':
    logger.info("Бот запущен...")
    logger.info(f"Администраторы: {ADMIN_USER_IDS}")
    logger.info(f"Таймаут polling: {POLLING_TIMEOUT} секунд")

    signal.signal(signal.SIGTERM, signal_term_handler)

    bot.infinity_polling(none_stop=True, timeout=POLLING_TIMEOUT)
    logger.info('Бот остановлен')