"""Настройки приложения. Все значения читаются из переменных окружения (.env)."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    app_name: str = "Energy Lab"
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./energy_lab.db"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "dev-secret-change-me"))
    bot_api_token: str = field(default_factory=lambda: _env("BOT_API_TOKEN", "dev-bot-token"))
    base_url: str = field(default_factory=lambda: _env("BASE_URL", "http://localhost:8000"))
    admin_email: str = field(default_factory=lambda: _env("ADMIN_EMAIL", "admin@energy.local"))
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD", "admin12345"))
    secure_cookies: bool = field(default_factory=lambda: _env("SECURE_COOKIES", "0") == "1")
    timezone: str = "Europe/Moscow"
    media_dir: str = field(default_factory=lambda: _env("MEDIA_DIR", "./media"))


# Параметры методики экспертной оценки (ЧТЗ-3, раздел 3). Меняются без правки формул.
METHOD = {
    "w_threshold": 0.5,          # порог согласованности Кендалла
    "max_rounds": 2,             # максимум туров Дельфи
    "kappa": 1.0,                # калибровка риска провала, при 1.0 совпадает с формулой ВКР
    "risk_zones": (6, 14),       # зелёная до 6, жёлтая до 14, дальше красная
    "k_neighbors": 3,
    "feature_weights": {"format": 0.35, "price": 0.20, "capacity": 0.15, "season": 0.10, "score": 0.20},
    "eta": 0.2,                  # скорость обучения компетентности
    "competence_bounds": (0.5, 1.0),
    "initial_competence": {"head": 1.0, "dept_head": 0.8, "other": 0.7},
}

# Калькулятор стоимости тусовки на главной (предварительная оценка; точную смету делает продюсерский отдел).
# Себестоимость на гостя по группе формата берётся из «разборов полёта», если их хватает, иначе — из этих значений.
PRICING = {
    "base_per_guest": {"Интеллектуальные": 150, "Квестовые": 300, "Игровые": 250, "Развлекательные": 200},
    "min_guests": 10,
    "team_per_hour": 2500,       # ведущие и актёры, за час программы
    "hours_default": 3,
    "margin": 0.15,              # развитие Lab: реквизит, обучение команды
    "options": {                 # дополнительные услуги, ₽ за мероприятие
        "venue": ("Площадка ENERGY", 6000),
        "photo": ("Фотограф и альбом", 5000),
        "dj": ("DJ и звук", 7000),
        "props": ("Тематический декор", 4000),
    },
    "min_history": 2,            # сколько проведённых мероприятий группы нужно, чтобы брать данные из базы
}

settings = Settings()
