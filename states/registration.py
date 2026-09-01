# states/registration.py
from maxapi.context import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_city = State()

class TournamentStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

class CancelStates(StatesGroup):
    confirming = State()
