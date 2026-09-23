"""Общие вспомогательные функции для клавиатур MAX и Telegram."""
from datetime import datetime


def group_registrations_by_tournament(registrations) -> list:
    """Группирует регистрации по турнирам (с сохранением порядка) и считает их количество."""
    tournaments = {}
    for reg in registrations:
        tournament = tournaments.setdefault(reg['tournament_id'], {
            'id': reg['tournament_id'],
            'name': reg['tournament_name'],
            'date': reg['tournament_date'],
            'count': 0,
        })
        tournament['count'] += 1
    return list(tournaments.values())


def format_cancel_tournament_button(tournament: dict) -> str:
    """Текст кнопки турнира в меню отмены регистрации."""
    date_obj = datetime.fromisoformat(tournament['date'])
    return f"{tournament['name']} ({date_obj.strftime('%d.%m.%Y')}) - {tournament['count']} рег."


def format_cancel_participant_button(reg: dict) -> str:
    """Текст кнопки участника в меню отмены регистрации."""
    return f"{reg['full_name']} ({reg['city']})"
