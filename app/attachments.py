"""Документы проектов и вложения задач (spec 004).

* Файлы хранятся в FILES_DIR — отдельно от MEDIA_DIR, который раздаётся открыто по /media.
  Скачать файл можно только через /cabinet/files/{id} с проверкой прав.
* Тип файла определяется по содержимому (сигнатуре), расширение лишь уточняет контейнер (DOCX/XLSX/PPTX — это ZIP).
* Ссылки принимаются только на Яндекс Диск и Google Диск/Документы (https), чтобы через сайт не раздавали
  произвольные адреса. Сами диски сайт не открывает: доступ к папке настраивает владелец.
"""
from __future__ import annotations

import os
import re
import secrets
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import settings
from app.media import image_ext

FILE_MAX = 20 * 1024 * 1024
ZIP_EXT = {"docx", "xlsx", "pptx", "odt", "ods", "odp", "zip"}
OLE_EXT = {"doc", "xls", "ppt"}
TEXT_EXT = {"txt", "csv", "md"}
ACCEPT = ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp,.zip,.txt,.csv,.md,.jpg,.jpeg,.png,.webp"


def detect(data: bytes, filename: str) -> str | None:
    """Расширение для сохранения или None, если тип не разрешён / содержимое не совпадает с расширением."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return ext if ext in ZIP_EXT else None
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return ext if ext in OLE_EXT else None
    img = image_ext(data)
    if img:
        return img.lstrip(".")
    if ext in TEXT_EXT:
        try:
            data[:65536].decode("utf-8")
        except UnicodeDecodeError:
            return None
        return ext if b"\x00" not in data[:65536] else None
    return None


def safe_name(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name)
    return (name or "файл")[:200]


async def save_upload(upload, subdir: str) -> tuple[str, str, int] | str:
    """(путь относительно FILES_DIR, исходное имя, размер) или текст ошибки."""
    if upload is None or not getattr(upload, "filename", ""):
        return "Выберите файл"
    data = await upload.read(FILE_MAX + 1)
    if not data:
        return "Файл пустой"
    if len(data) > FILE_MAX:
        return "Файл больше 20 МБ — положите его на Яндекс Диск или Google Диск и прикрепите ссылку"
    original = safe_name(upload.filename)
    ext = detect(data, original)
    if not ext:
        return ("Такой файл загрузить нельзя: подходят PDF, Word, Excel, PowerPoint, OpenDocument, ZIP, TXT/CSV "
                "и картинки JPG/PNG/WebP")
    folder = os.path.join(settings.files_dir, subdir)
    os.makedirs(folder, exist_ok=True)
    name = f"{secrets.token_hex(12)}.{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return f"{subdir}/{name}", original, len(data)


def full_path(att: m.Attachment) -> str | None:
    if not att.file or ".." in att.file or att.file.startswith("/"):
        return None
    path = os.path.join(settings.files_dir, att.file)
    return path if os.path.isfile(path) else None


def remove_file(att: m.Attachment) -> None:
    path = full_path(att)
    if path:
        os.remove(path)


# ------------------------------------------------------------------ ссылки на диски
def parse_link(url: str) -> tuple[str, str] | str:
    """(нормализованная ссылка, провайдер) или текст ошибки."""
    url = (url or "").strip()
    if not url:
        return "Вставьте ссылку"
    if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", url, re.I) and not re.match(r"^https?://", url, re.I):
        return "Такая ссылка не подходит"                   # javascript:, data:, ftp: …
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "Такая ссылка не подходит"
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" and host:
        url = "https://" + url.split("://", 1)[1]
    if parts.username or parts.password or port not in (None, 443):
        return "Такая ссылка не подходит"
    path = parts.path or ""
    if host in ("disk.yandex.ru", "disk.yandex.com", "disk.yandex.by", "disk.yandex.kz", "disk.360.yandex.ru",
                "yadi.sk"):
        provider = "yandex"
    elif host == "drive.google.com":
        provider = "gdrive"
    elif host == "docs.google.com":
        provider = {"/document/": "gdocs", "/spreadsheets/": "gsheets", "/presentation/": "gslides",
                    "/forms/": "gforms"}.get(next((p for p in ("/document/", "/spreadsheets/", "/presentation/",
                                                                 "/forms/") if path.startswith(p)), ""), "gdrive")
    else:
        return "Прикрепить можно ссылку на Яндекс Диск (disk.yandex.ru, yadi.sk) или Google Диск (drive.google.com, " \
               "docs.google.com)"
    if len(url) > 500:
        return "Слишком длинная ссылка"
    return url, provider


def title_from_link(url: str, provider: str) -> str:
    return f"{m.LINK_PROVIDERS[provider]}: {urlsplit(url).path.rstrip('/').rsplit('/', 1)[-1][:40] or 'папка'}"


# ------------------------------------------------------------------ права
def event_participants(db: Session, ev: m.Event) -> set[int]:
    """Кто считается участником проекта: автор, назначенные эксперты, ответственные блоков, исполнители задач."""
    ids = {ev.author_id}
    ids |= set(db.scalars(select(m.Expert.user_id).join(m.EventExpert, m.EventExpert.expert_id == m.Expert.id)
                          .where(m.EventExpert.event_id == ev.id)))
    ids |= {b.responsible_id for b in ev.stations if b.responsible_id}
    ids |= set(db.scalars(select(m.Task.assignee_id).where(m.Task.event_id == ev.id)))
    ids |= set(db.scalars(select(m.Task.author_id).where(m.Task.event_id == ev.id)))
    return {i for i in ids if i}


def can_see_event_docs(db: Session, user: m.User, ev: m.Event) -> bool:
    return user.has_role("head") or user.id in event_participants(db, ev)


def can_delete(user: m.User, att: m.Attachment, owner_id: int | None) -> bool:
    """Удалить может тот, кто добавил, владелец (автор проекта/задачи) или руководитель."""
    return user.has_role("head") or att.uploaded_by == user.id or (owner_id is not None and owner_id == user.id)


def human_size(n: int | None) -> str:
    if not n:
        return ""
    for unit in ("Б", "КБ", "МБ"):
        if n < 1024 or unit == "МБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return ""
