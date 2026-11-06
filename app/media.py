"""Сохранение загруженных изображений в MEDIA_DIR с проверкой содержимого (а не только расширения)."""
import os
import secrets

from app.config import settings

IMAGE_SIGNATURES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG": ".png", b"RIFF": ".webp"}
IMAGE_MAX = 8 * 1024 * 1024


def image_ext(data: bytes) -> str | None:
    ext = next((e for sig, e in IMAGE_SIGNATURES.items() if data.startswith(sig)), None)
    if ext == ".webp" and data[8:12] != b"WEBP":
        return None
    return ext


async def save_image(upload, subdir: str) -> str | None:
    """Возвращает путь относительно MEDIA_DIR или None, если файл не картинка / больше 8 МБ."""
    if upload is None or not hasattr(upload, "read"):
        return None
    data = await upload.read(IMAGE_MAX + 1)
    ext = image_ext(data) if data else None
    if not ext or len(data) > IMAGE_MAX:
        return None
    folder = os.path.join(settings.media_dir, subdir)
    os.makedirs(folder, exist_ok=True)
    name = f"{secrets.token_hex(8)}{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(data)
    return f"{subdir}/{name}"


def remove(path: str | None, allowed_prefixes=("events/", "team/")) -> None:
    if path and path.startswith(allowed_prefixes) and ".." not in path:
        full = os.path.join(settings.media_dir, path)
        if os.path.isfile(full):
            os.remove(full)
