"""Пароли (scrypt), CSRF-токены, ограничение попыток входа, журнал событий."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict

from sqlalchemy.orm import Session

from app import models as m

N, R, P, KEYLEN = 2 ** 14, 8, 1, 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=KEYLEN)
    return f"scrypt${N}${R}${P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt, digest = encoded.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                            dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(dk.hex(), digest)
    except ValueError:
        return False


def csrf_token(session: dict) -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def check_csrf(session: dict, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(session.get("csrf", ""), token)


class LoginLimiter:
    """5 неверных попыток → блокировка на 15 минут (CAB-02). Хранится в памяти процесса."""

    def __init__(self, attempts: int = 5, window: int = 900):
        self.attempts, self.window = attempts, window
        self.fails: dict[str, list[float]] = defaultdict(list)

    def blocked(self, key: str) -> bool:
        now = time.time()
        self.fails[key] = [t for t in self.fails[key] if now - t < self.window]
        return len(self.fails[key]) >= self.attempts

    def fail(self, key: str) -> None:
        self.fails[key].append(time.time())

    def reset(self, key: str) -> None:
        self.fails.pop(key, None)


limiter = LoginLimiter()


def audit(db: Session, user_id: int | None, action: str, obj: str | None = None, details: str | None = None):
    db.add(m.AuditLog(user_id=user_id, action=action, object=obj, details=details))
