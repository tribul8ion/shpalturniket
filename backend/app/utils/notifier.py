"""
Уведомления: отправка сообщений в Telegram на основе config.json
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Dict, Any
import json

import httpx


class TelegramNotifier:
    """Простой Telegram notifier. Читает конфиг при каждом отправлении, чтобы не держать состояние."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path(__file__).parent.parent.parent.parent
        self._config_path = self.base_dir / "config.json"

    def _read_config(self) -> Dict[str, Any]:
        if not self._config_path.exists():
            return {}
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_token_and_chats(self) -> tuple[str | None, List[int]]:
        cfg = self._read_config()
        token = cfg.get("TOKEN")
        raw = cfg.get("chat_id", [])
        chat_ids: List[int] = []
        try:
            if isinstance(raw, list):
                for x in raw:
                    try:
                        chat_ids.append(int(x))
                    except Exception:
                        pass
            elif isinstance(raw, str):
                parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
                for p in parts:
                    try:
                        chat_ids.append(int(p))
                    except Exception:
                        pass
            elif raw is not None:
                chat_ids.append(int(raw))
        except Exception:
            pass
        return token, chat_ids

    async def send_message(self, text: str, parse_mode: str = "HTML") -> None:
        token, chat_ids = self._get_token_and_chats()
        if not token or not chat_ids:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            tasks = [
                client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode})
                for chat_id in chat_ids
            ]
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception:
                pass


notifier = TelegramNotifier()

