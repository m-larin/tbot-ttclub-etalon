# handlers/__init__.py
# Импортируем роутеры для MAX
from .common_max import router as common_max_router
from .admin_max import router as admin_max_router
from .registration_max import router as registration_max_router

# Импортируем функции регистрации для MAX
from .common_max import register_handlers as register_common_max
from .admin_max import register_handlers as register_admin_max
from .registration_max import register_handlers as register_registration_max

# Импортируем функции регистрации для Telegram
from .registration_tg import register_handlers as register_tg_registration
from .admin_tg import register_handlers as register_tg_admin

__all__ = [
    # MAX роутеры
    'common_max_router',
    'admin_max_router',
    'registration_max_router',
    # MAX регистрация
    'register_common_max',
    'register_admin_max',
    'register_registration_max',
    # Telegram регистрация
    'register_tg_registration',
    'register_tg_admin',
]