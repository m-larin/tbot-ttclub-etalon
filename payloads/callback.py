# payloads/callback.py
from maxapi.filters.callback_payload import CallbackPayload

class TournamentRegistrationPayload(CallbackPayload, prefix="reg"):
    tournament_id: int

class TournamentViewPayload(CallbackPayload, prefix="view"):
    tournament_id: int

class TournamentDeletePayload(CallbackPayload, prefix="del"):
    tournament_id: int

class TournamentDeleteConfirmPayload(CallbackPayload, prefix="delete_confirm"):
    tournament_id: int

class CancelRegistrationPayload(CallbackPayload, prefix="cancel"):
    registration_id: int

class CancelConfirmPayload(CallbackPayload, prefix="cancel_confirm"):
    registration_id: int

class CancelAllPayload(CallbackPayload, prefix="cancel_all"):
    pass

class DeleteCancelPayload(CallbackPayload, prefix="delete_cancel"):
    pass
