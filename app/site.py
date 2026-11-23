"""Настройки главной страницы: значения по умолчанию из config.py + то, что руководитель сохранил в кабинете."""
import copy
import re
import time
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app import models as m
from app.config import PRICING

TEXTS_DEFAULT = {
    "eyebrow": "Energy Lab · творческая лаборатория отряда ENERGY",
    "lead": "Квизы, иммерсивные квесты, ролевые игры и вечеринки. Приходите на наши мероприятия или закажите "
            "тусовку под ключ — на день рождения, выпускной или для своей компании.",
    "request_intro": "Соберём праздник под ваш повод: придумаем легенду, станции и ведущих, найдём площадку. "
                     "Продюсер свяжется с вами в течение двух рабочих дней и пришлёт смету.",
    "crew_intro": "Energy Lab — творческая лаборатория педагогического отряда ENERGY. Вожатые и организаторы "
                  "с опытом лагерных смен работают пятью отделами, и каждый проект проходит проверку всех пяти, "
                  "прежде чем вы на него придёте.",
}
TEXT_LABELS = {
    "eyebrow": "Подпись над заголовком",
    "lead": "Текст под заголовком",
    "request_intro": "Текст вверху страницы «Заказать мероприятие»",
    "crew_intro": "Текст блока «Кто создаёт тусовки»",
}


def _get(db: Session, key: str):
    row = db.get(m.SiteSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value) -> None:
    row = db.get(m.SiteSetting, key)
    if row:
        row.value = value
    else:
        db.add(m.SiteSetting(key=key, value=value))


def texts(db: Session) -> dict:
    saved = _get(db, "texts") or {}
    return {k: (saved.get(k) or v) for k, v in TEXTS_DEFAULT.items()}


def save_texts(db: Session, data: dict) -> None:
    _set(db, "texts", {k: str(data.get(k, "")).strip()[:1000] for k in TEXTS_DEFAULT})


def pricing(db: Session) -> dict:
    """Параметры калькулятора. Опции хранятся как {ключ: [название, цена]}."""
    cfg = copy.deepcopy(PRICING)
    cfg["options"] = {k: list(v) for k, v in cfg["options"].items()}
    saved = _get(db, "pricing") or {}
    for k in ("min_guests", "team_per_hour", "hours_default", "margin", "min_history"):
        if k in saved:
            cfg[k] = saved[k]
    if "base_per_guest" in saved:
        cfg["base_per_guest"].update(saved["base_per_guest"])
    if "options" in saved:
        cfg["options"] = {k: list(v) for k, v in saved["options"].items()}
    return cfg


def save_pricing(db: Session, data: dict) -> None:
    _set(db, "pricing", data)


# ------------------------------------------------------------------ соцсети (spec 005)
# Ключ → (название, допустимые домены). Ссылка принимается только на домен своей сети и только https.
NETWORKS = {
    "vk": ("ВКонтакте", {"vk.com", "vk.ru", "m.vk.com", "m.vk.ru"}),
    "telegram": ("Telegram", {"t.me", "telegram.me"}),
    "instagram": ("Instagram", {"instagram.com", "www.instagram.com"}),
    "youtube": ("YouTube", {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}),
    "bot": ("Бот для вопросов (Telegram)", {"t.me", "telegram.me"}),   # не иконка: кнопка «Написать оператору»
}
ICONS = ("vk", "telegram", "instagram", "youtube")
SOCIALS_DEFAULT = {"vk": "https://vk.ru/planeta.energy", "telegram": "", "instagram": "", "youtube": "", "bot": ""}
META_NOTE = "Instagram принадлежит компании Meta, деятельность которой признана экстремистской и запрещена в России."


def social_url(key: str, raw: str) -> str | None:
    """Нормализованная ссылка или None, если она не ведёт в эту соцсеть. Для Telegram можно написать @ник."""
    raw = (raw or "").strip()
    if key in ("telegram", "bot") and re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", raw):
        return "https://t.me/" + raw.lstrip("@")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if host not in NETWORKS[key][1] or parts.username or port not in (None, 443) or len(raw) > 300:
        return None
    return "https://" + raw.split("://", 1)[1]


def socials(db: Session) -> dict:
    saved = _get(db, "socials")
    if saved is None:                                     # раньше ссылка на VK хранилась среди текстов
        old = (_get(db, "texts") or {}).get("vk_url")
        saved = {**SOCIALS_DEFAULT, **({"vk": old} if old else {})}
    return {k: saved.get(k, "") or "" for k in NETWORKS}


def save_socials(db: Session, data: dict) -> list[str]:
    """Сохраняет правильные ссылки; неправильные оставляет прежними и возвращает список ошибок."""
    cur, errors = socials(db), []
    for k, (name, _) in NETWORKS.items():
        raw = (data.get(k) or "").strip()
        if not raw:
            cur[k] = ""
            continue
        url = social_url(k, raw)
        if url:
            cur[k] = url
        else:
            errors.append(f"{name} — нужна ссылка на {', '.join(sorted(NETWORKS[k][1])[:2])}")
    _set(db, "socials", cur)
    _cache["at"] = 0
    return errors


_cache: dict = {"at": 0.0, "value": {}}


def _cached() -> dict:
    if time.time() - _cache["at"] > 60:
        from app.db import SessionLocal
        try:
            with SessionLocal() as db:
                _cache["value"] = socials(db)
        except Exception:                                  # нет таблицы (миграции не применены) — без ссылок
            _cache["value"] = {}
        _cache["at"] = time.time()
    return _cache["value"]


def social_links() -> list[dict]:
    """Иконки соцсетей для шапки и подвала любых страниц (глобальная функция шаблонов). Кэш 60 с."""
    cur = _cached()
    return [{"key": k, "name": NETWORKS[k][0], "url": cur[k]} for k in ICONS if cur.get(k)]


def bot_url() -> str:
    return _cached().get("bot", "")
