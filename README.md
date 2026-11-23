# Energy Lab — «Запускаем ваши проекты»

Информационная система для проведения экспертно-оценочных тренингов направления Energy Lab педагогического отряда ENERGY.
Выпускная квалификационная работа, НИУ «МЭИ», ИнЭИ, кафедра БИТ. Автор — А. С. Рыбаков (ИЭозс-65-23), руководитель — А. В. Ермаков.

**Что умеет**

* описывать проекты мероприятий и их сценарий по времени (блоки, карусель станций);
* проводить экспертизу силами пяти отделов: взвешенные критерии, метод Дельфи, риск блоков сценария;
* прогнозировать явку, продажи, бюджет и оценку гостей по похожим прошлым мероприятиям;
* вести решения руководителей и публикацию в афише, продавать билеты через Timepad;
* собирать анкеты гостей, вносить факт и пересчитывать компетентность экспертов;
* давать каждому участнику личный кабинет с доской задач, документами, уведомлениями и обсуждениями по отделам;
* работать через бота Telegram или VK (Python-сервис `bot/`).

## Быстрый старт (разработка)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
make dev                    # SQLite, справочники + демо-данные, http://localhost:8000
```

Демо-входы (пароль `demo12345`): `oleg@energy.local`, `katya@energy.local` — руководители;
`script@`, `tech@`, `smi@energy.local` — эксперты; `member@energy.local` — участник; `support@energy.local` — оператор поддержки.
Демо-цифры прошлых мероприятий условные — замените их реальными (см. `docs/guides/admin.md`, п. 5.2).

Через Docker с PostgreSQL: `cp .env.example .env`, заполнить, `docker compose up --build`.
Вход администратора по умолчанию без `.env`: `ADMIN_EMAIL`/`ADMIN_PASSWORD` из `app/config.py`.

## Запуск на Windows: сайт и бот

Нужен Python 3.12 (на 3.13+ пока нет готовых пакетов для части зависимостей). Путь к папке проекта лучше без кириллицы.

**Первый раз**

```powershell
cd C:\Users\fish\Documents\Lab+Energy\ENERGY_Lab\energy-lab
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1          # если ругается на политику: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python -m alembic upgrade head
python -m app.seed --demo               # справочники и демо-данные (один раз, на пустую базу)
```

**Окно 1 — сайт**

```powershell
cd C:\Users\fish\Documents\Lab+Energy\ENERGY_Lab\energy-lab
.\venv\Scripts\Activate.ps1
python -m alembic upgrade head          # после каждого обновления кода — применить новые миграции
uvicorn app.main:app --reload
```

Сайт — http://127.0.0.1:8000. Вход: `admin@energy.local` / `admin12345`, демо-пользователи — пароль `demo12345`.

**Окно 2 — бот Telegram**

```powershell
cd C:\Users\fish\Documents\Lab+Energy\ENERGY_Lab\energy-lab
.\venv\Scripts\Activate.ps1
$env:TELEGRAM_BOT_TOKEN = "токен от @BotFather"
$env:LAB_URL = "http://127.0.0.1:8000"
$env:BOT_API_TOKEN = "dev-bot-token"    # токен локального сайта по умолчанию (пока в проекте нет .env)
python -m bot.main
```

В окне должно появиться «Бот запущен: telegram, outbox». Токен бота вводится только в этом окне — не храните его в файлах репозитория.

**Проверка:** в Telegram `/start` → на сайте «Профиль» → «Бот и уведомления» → «Получить код привязки» → боту
`/link КОД` → `/tasks`. Поставьте себе задачу с другой учётной записи — через ~15 секунд придёт уведомление с кнопками,
на сайте загорится колокольчик.

* Пока бот запущен локально, он забирает сообщения этого Telegram-бота у сервера. Для опытов удобнее отдельный
  тестовый бот у @BotFather.
* Кнопка «Открыть на сайте» локально не появляется: Telegram принимает только https-ссылки; ссылка остаётся в тексте.
* Остановить — `Ctrl+C` в окне. Частые ошибки: `Activate.ps1 cannot be loaded` — команда `Set-ExecutionPolicy` выше;
  порт 8000 занят — `uvicorn app.main:app --reload --port 8010` и `$env:LAB_URL = "http://127.0.0.1:8010"`;
  в логе бота «401» — `BOT_API_TOKEN` не совпадает с сайтом.

## Проверки

```bash
make lint     # ruff
make test     # pytest + покрытие
```

Контрольный пример из раздела 2.3 ВКР (S = 3,96, W ≈ 0,78, R = 4/12/16, Q ≈ 0,84) — `tests/test_expertise_math.py`.

## Структура

```
app/
  expertise/      методы А–Г: scoring, delphi, risk, forecast, competence, service
  routers/        public (сайт), auth, cabinet (кабинет), expertise, admin, api_bot (API для бота)
  templates/      Jinja2: public/*, cabinet/*, partials/*
  static/         lab.css — космическая дизайн-система, logo.svg
  export.py       метки для шаблонов Google Диска и реестр
  maintenance.py  обезличивание старых покупателей, чистка очереди
migrations/       Alembic (PostgreSQL 16)
tests/            pytest: математика методов, сквозной сценарий, бот, администрирование
deploy/           nginx.conf, backup.sh, restore.sh
bot/              бот Telegram/VK и доставка уведомлений (Python, без зависимостей) — bot/README.md
n8n/workflows/    выгрузка в Google Таблицу и документы из шаблона Google Docs
specs/            спецификации фич (Spec Kit)
docs/
  chtz/           ЧТЗ на 10 модулей
  guides/         Руководство пользователя (ЭЛ.И3) и администратора (ЭЛ.ИА), ГОСТ 34 / РД 50-34.698
  faq/            FAQ в комиксах
.github/workflows CI (проверки) и Deploy (публикация образа и выкладка с подтверждением)
```

## Развёртывание

Схема: сервер в РФ (сайт, кабинет, PostgreSQL), внешний сервер (бот `bot/` и n8n для Google), GitHub Actions.
Подробно — [Руководство администратора](docs/guides/admin.md). Кратко:

1. Создайте репозиторий на GitHub и загрузите код.
2. В **Settings → Environments** создайте окружение `production` с обязательным подтверждением руководителями.
3. В **Settings → Secrets → Actions** добавьте `SSH_HOST`, `SSH_PORT`, `SSH_USER`, `SSH_KEY`, `GHCR_READ_TOKEN`.
4. На сервере: `git clone` в `/opt/energy-lab`, заполните `.env` по `.env.example`, получите сертификат,
   впишите домен и IP n8n в `deploy/nginx.conf`, выполните `docker compose -f docker-compose.prod.yml up -d`.
5. Бот — на внешнем сервере: `~/energy-bot/bot/.env` по `bot/.env.example`, выкладка GitHub Actions «bot» (см. `bot/README.md`).
6. Выгрузки в Google — сценарии `n8n/workflows` (см. `n8n/README.md`).

Секреты хранятся только в `.env` на сервере и в GitHub Secrets — в репозиторий они не попадают.

## Что ещё нужно от заказчика

| Нужно | Для чего |
|---|---|
| Данные 4+ прошедших мероприятий (гости, билеты, цена, затраты, оценки) | реальная база аналогов для прогноза |
| Список экипажа: экспертов по отделам, e-mail | приглашения |
| Репозиторий GitHub, домен, сервер в РФ | развёртывание |
| Аккаунт организатора Timepad, пример выгрузки заказов | продажи и импорт |
| Токен бота Telegram, сообщество VK, IP сервера n8n | бот и уведомления |
| Шаблоны Google Docs с метками `{{…}}`, Google Таблица, сервисный аккаунт | выгрузка и дублирование |
| GPG-ключ руководителей | шифрование резервных копий |
