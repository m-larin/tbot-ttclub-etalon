# keyboards/__init__.py
from .max import (
    get_max_registration_tournaments_keyboard,
    get_max_view_tournaments_keyboard,
    get_max_delete_tournaments_keyboard,
    get_max_cancel_registration_keyboard,
    get_max_group_message_markup,
)
from .telegram import (
    get_tg_tournaments_keyboard,
    get_tg_group_message_markup,
    get_tg_cancel_registration_keyboard,
)