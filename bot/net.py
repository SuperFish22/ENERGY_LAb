"""Минимальный HTTP-клиент на стандартной библиотеке. В тестах подменяется на функцию с той же сигнатурой."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any, Protocol


class Transport(Protocol):
    def __call__(self, method: str, url: str, *, params: dict | None = None, json_body: Any = None,
                 form: dict | None = None, headers: dict | None = None, timeout: float = 30) -> tuple[int, Any]: ...


def request(method: str, url: str, *, params: dict | None = None, json_body: Any = None, form: dict | None = None,
            headers: dict | None = None, timeout: float = 30) -> tuple[int, Any]:
    """(HTTP-статус, разобранный JSON или текст). Сетевые ошибки — исключение OSError."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    data = None
    hdrs = {"User-Agent": "EnergyLabBot/1.0", **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode()
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text) if text else None
    except ValueError:
        return status, text


Requester = Callable[..., tuple[int, Any]]
