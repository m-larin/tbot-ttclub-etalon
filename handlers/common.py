# handlers/common.py
import logging
from context import get_tg_bot, get_max_bot, get_tg_username, get_max_username
from instance.config import ADMIN_USER_IDS, TELEGRAM_GROUP_CHAT_ID, MAX_GROUP_CHAT_ID

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора."""
    return user_id in ADMIN_USER_IDS

async def send_notification_to_both(text: str, parse_mode_tg=None, keyboard_tg=None, keyboard_max=None):
    """
    Отправка уведомления в оба мессенджера.
    Использует объекты из глобального контекста.
    """
    tg_bot = get_tg_bot()
    max_bot = get_max_bot()
    
    logger.info(f"📌 send_notification_to_both вызван")
    logger.info(f"📌 TELEGRAM_GROUP_CHAT_ID: {TELEGRAM_GROUP_CHAT_ID}")
    logger.info(f"📌 MAX_GROUP_CHAT_ID: {MAX_GROUP_CHAT_ID}")
    
    # Отправка в Telegram
    try:
        if tg_bot:
            logger.info(f"📤 Отправка в Telegram группу {TELEGRAM_GROUP_CHAT_ID}...")
            logger.info(f"📝 Текст: {text[:100]}...")
            
            if keyboard_tg:
                await tg_bot.send_message(
                    chat_id=TELEGRAM_GROUP_CHAT_ID,
                    text=text,
                    parse_mode=parse_mode_tg,
                    reply_markup=keyboard_tg
                )
            else:
                await tg_bot.send_message(
                    chat_id=TELEGRAM_GROUP_CHAT_ID,
                    text=text,
                    parse_mode=parse_mode_tg
                )
            logger.info(f"✅ Сообщение отправлено в Telegram группу {TELEGRAM_GROUP_CHAT_ID}")
        else:
            logger.warning("⚠️ tg_bot is None, пропускаем отправку в Telegram")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
    
    # Отправка в MAX
    try:
        if max_bot:
            from maxapi.enums.parse_mode import ParseMode
            
            logger.info(f"📤 Отправка в MAX группу {MAX_GROUP_CHAT_ID}...")
            logger.info(f"📝 Текст: {text[:100]}...")
            
            parse_mode = ParseMode.HTML if parse_mode_tg else None
            
            attachments = None
            if keyboard_max:
                attachments = [keyboard_max]
            
            await max_bot.send_message(
                chat_id=MAX_GROUP_CHAT_ID,
                text=text,
                parse_mode=parse_mode,
                attachments=attachments
            )
            logger.info(f"✅ Сообщение отправлено в MAX группу {MAX_GROUP_CHAT_ID}")
        else:
            logger.warning("⚠️ max_bot is None, пропускаем отправку в MAX")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в MAX: {e}")