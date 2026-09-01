"""FSM-состояния диалогов бота MAX."""
from maxapi.context import State, StatesGroup

class RegistrationStates(StatesGroup):
    """Состояния регистрации участника на турнир."""
    waiting_for_full_name = State()
    waiting_for_city = State()

class TournamentStates(StatesGroup):
    """Состояния создания турнира."""
    waiting_for_name = State()
    waiting_for_date = State()

class CancelStates(StatesGroup):
    """Состояния отмены регистрации."""
    confirming = State()
