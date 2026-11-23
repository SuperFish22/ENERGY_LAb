"""Настройки бота из переменных окружения (файл .env рядом с docker-compose.yml на сервере бота)."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Config:
    lab_url: str = field(default_factory=lambda: _env("LAB_URL", "http://localhost:8000").rstrip("/"))
    bot_api_token: str = field(default_factory=lambda: _env("BOT_API_TOKEN"))
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    vk_token: str = field(default_factory=lambda: _env("VK_GROUP_TOKEN"))
    vk_group_id: str = field(default_factory=lambda: _env("VK_GROUP_ID"))
    outbox_every: int = field(default_factory=lambda: int(_env("OUTBOX_EVERY_SEC", "15")))
    poll_timeout: int = field(default_factory=lambda: int(_env("TELEGRAM_POLL_TIMEOUT", "25")))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    def problems(self) -> list[str]:
        out = []
        if not self.bot_api_token:
            out.append("BOT_API_TOKEN не задан — сайт не пустит бота в /api/bot")
        if not self.telegram_token and not self.vk_token:
            out.append("Нет ни TELEGRAM_BOT_TOKEN, ни VK_GROUP_TOKEN — боту некуда подключаться")
        if self.vk_token and not self.vk_group_id:
            out.append("Для VK нужен VK_GROUP_ID")
        return out
