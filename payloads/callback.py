"""Callback-payload'ы для инлайн-кнопок MAX."""
from maxapi.filters.callback_payload import CallbackPayload

class TournamentRegistrationPayload(CallbackPayload, prefix="reg"):
    """Выбор турнира для регистрации участника."""
    tournament_id: int

class TournamentViewPayload(CallbackPayload, prefix="view"):
    """Выбор турнира для просмотра участников."""
    tournament_id: int

class TournamentDeletePayload(CallbackPayload, prefix="del"):
    """Выбор турнира для удаления."""
    tournament_id: int

class TournamentDeleteConfirmPayload(CallbackPayload, prefix="delete_confirm"):
    """Подтверждение удаления турнира."""
    tournament_id: int

class CancelRegistrationPayload(CallbackPayload, prefix="cancel"):
    """Выбор регистрации для отмены."""
    registration_id: int

class CancelConfirmPayload(CallbackPayload, prefix="cancel_confirm"):
    """Подтверждение отмены регистрации."""
    registration_id: int

class CancelAllPayload(CallbackPayload, prefix="cancel_all"):
    """Отмена текущего действия."""

class DeleteCancelPayload(CallbackPayload, prefix="delete_cancel"):
    """Отмена удаления турнира."""
