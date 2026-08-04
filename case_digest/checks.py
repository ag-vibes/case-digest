from __future__ import annotations

import requests

from .config import Settings
from .pyrogram_compat import Client


def check_integrations(settings: Settings, include_telegram: bool = True) -> list[str]:
    messages: list[str] = []
    required = {
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
        "TAVILY_API_KEY": settings.tavily_api_key,
        "TELEGRAM_TOKEN": settings.telegram_token,
        "TELEGRAM_CHAT_ID": settings.telegram_chat_id,
    }
    if include_telegram:
        required.update(
            {"API_ID": settings.api_id, "API_HASH": settings.api_hash, "SESSION_STRING": settings.session_string}
        )
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Не заданы переменные: {', '.join(missing)}")

    bot_url = f"https://api.telegram.org/bot{settings.telegram_token}"
    bot = requests.get(f"{bot_url}/getMe", timeout=20)
    bot.raise_for_status()
    messages.append("Telegram bot: OK")
    chat = requests.get(
        f"{bot_url}/getChat", params={"chat_id": settings.telegram_chat_id}, timeout=20
    )
    chat.raise_for_status()
    messages.append(f"Telegram channel: OK ({settings.telegram_chat_id})")

    tavily = requests.get(
        "https://api.tavily.com/usage",
        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
        timeout=20,
    )
    tavily.raise_for_status()
    messages.append("Tavily: OK")

    if include_telegram:
        app = Client(
            "case_digest_check",
            api_id=settings.api_id,
            api_hash=settings.api_hash,
            session_string=settings.session_string,
            in_memory=True,
        )
        with app:
            app.get_me()
        messages.append("Telegram reader session: OK")
    return messages
