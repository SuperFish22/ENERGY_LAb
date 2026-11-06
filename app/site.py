"""Настройки главной страницы: значения по умолчанию из config.py + то, что руководитель сохранил в кабинете."""
import copy

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
    "vk_url": "https://vk.ru/planeta.energy",
}
TEXT_LABELS = {
    "eyebrow": "Подпись над заголовком",
    "lead": "Текст под заголовком",
    "request_intro": "Текст у формы заявки",
    "crew_intro": "Текст блока «Кто создаёт тусовки»",
    "vk_url": "Ссылка на сообщество ВКонтакте",
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
