"""Запуск: python -m bot.main. Три потока: Telegram, VK (если настроен), доставка уведомлений."""
from __future__ import annotations

import logging
import signal
import sys
import threading

from bot.config import Config
from bot.lab import Lab
from bot.outbox import run as run_outbox
from bot.telegram import Telegram, TelegramPoller
from bot.vk import VK, VKPoller


def main() -> int:
    cfg = Config()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("bot")
    problems = cfg.problems()
    for p in problems:
        log.error(p)
    if problems:
        return 2
    lab = Lab(cfg.lab_url, cfg.bot_api_token)
    me = lab.me({"channel": "telegram", "user_id": "0"})
    if me.status == 401:
        log.error("Сайт %s отклонил BOT_API_TOKEN (401) — проверьте, что токены совпадают", cfg.lab_url)
        return 2
    if not me.ok:
        log.warning("Сайт %s ответил %s — продолжаю, буду пробовать дальше", cfg.lab_url, me.status or "нет связи")

    senders, workers = {}, []
    stop = threading.Event()
    if cfg.telegram_token:
        tg = Telegram(cfg.telegram_token)
        senders["telegram"] = tg.send
        workers.append(("telegram", TelegramPoller(tg, lab, senders, cfg.poll_timeout).run))
    if cfg.vk_token:
        vk = VK(cfg.vk_token, cfg.vk_group_id)
        senders["vk"] = vk.send
        workers.append(("vk", VKPoller(vk, lab, senders).run))
    workers.append(("outbox", lambda s: run_outbox(lab, senders, cfg.outbox_every, s)))

    def shutdown(*_):
        log.info("Остановка…")
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    threads = [threading.Thread(target=fn, args=(stop,), name=name, daemon=True) for name, fn in workers]
    for t in threads:
        t.start()
    log.info("Бот запущен: %s; сайт %s", ", ".join(n for n, _ in workers), cfg.lab_url)
    while not stop.is_set():
        stop.wait(1)
        if not any(t.is_alive() for t in threads):
            log.error("Все потоки остановились")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
