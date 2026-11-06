# Частные технические задания на модули ИС Energy Lab

Основание: Техническое задание на ИС Energy Lab (документ «ТЗ и ЧТЗ», ГОСТ 34.602-2020) и ЧТЗ-1…ЧТЗ-5 к нему.
ЧТЗ-1…5 делят систему по подсистемам (ЧТЗ-1 — сайт школы вожатых, следующий этап; ЧТЗ-2…5 — Energy Lab). Документы этой папки — следующий уровень: задание на разработку
отдельного программного модуля. Модуль = пакет кода + таблицы БД + экраны/методы API + тесты приёмки.

| Шифр | Модуль | Подсистема ТЗ | Код | Тесты приёмки | Готовность |
|---|---|---|---|---|---|
| [М-01](M01-auth.md) | Аутентификация, роли, аудит | ЧТЗ-4 | `app/security.py`, `app/deps.py`, `app/routers/auth.py`, `admin.py` | `test_flow.py::test_login_lockout`, `test_csrf_required`, `test_admin.py` | реализован |
| [М-02](M02-public.md) | Публичный сайт: афиша, анкета гостя, доска вопросов | ЧТЗ-2 | `app/routers/public.py` | `test_public_pages`, `test_full_flow` (анкета) | реализован |
| [М-03](M03-projects.md) | Проекты и станции, жизненный цикл | ЧТЗ-4 | `app/routers/cabinet.py` | `test_full_flow` шаги 1, 4, 6 | реализован |
| [М-04](M04-expertise.md) | Экспертиза: методы А, Б, В | ЧТЗ-3 | `app/expertise/{scoring,delphi,risk}.py`, `app/routers/expertise.py` | `test_expertise_math.py`, `test_second_round_shows_medians` | реализован |
| [М-05](M05-forecast.md) | Прогноз, рекомендация, компетентность (метод Г) | ЧТЗ-3 | `app/expertise/{forecast,competence,service}.py` | `test_expertise_math.py`, `test_full_flow` шаг 6 | реализован |
| [М-06](M06-tasks-discussions.md) | Задачи и обсуждения по отделам | ЧТЗ-4 | `app/routers/cabinet.py` | `test_bot_api`, `test_full_flow` | реализован |
| [М-07](M07-tickets.md) | Билеты Timepad и фактические результаты | ЧТЗ-2, ЧТЗ-4 | `cabinet.py` (импорт CSV), `public.py` (виджет) | `test_full_flow` шаг 5 | реализован (импорт CSV); API Timepad — этап 2 |
| [М-08](M08-bot-api.md) | API бота, n8n, Telegram/VK, уведомления | ЧТЗ-5 | `app/routers/api_bot.py`, `app/notify.py`, `n8n/workflows/` | `test_bot_api`, `test_moderation_notifies_bot_author` | реализован; workflow n8n — шаблон |
| [М-09](M09-export-backup.md) | Выгрузка в Google Диск, дублирование, резервные копии | ТЗ (SYS) | `app/export.py`, `deploy/backup.sh` | `test_export_placeholders` | реализован; шаблоны Google — ждём от заказчика |
| [М-10](M10-cicd.md) | Сборка, проверка и развёртывание (CI/CD) | ТЗ (SYS) | `.github/workflows/`, `Dockerfile`, `docker-compose.prod.yml`, `deploy/` | конвейер CI | реализован; секреты задаёт заказчик |

Правила для всех модулей:

* язык интерфейса и сообщений — русский; даты `ДД.ММ.ГГГГ`, деньги `1 300 ₽`;
* каждое изменяющее действие в кабинете — POST с CSRF-токеном; значимые действия пишутся в `audit_log`;
* персональные данные (ФИО, e-mail, телефоны, ответы гостей) хранятся только в БД на российском сервере (152-ФЗ, ст. 18 ч. 5);
  на внешний сервер (n8n, Telegram) уходят только идентификаторы чатов и тексты уведомлений;
* параметры методов (пороги, веса, η) — в `app/config.py → METHOD`, не в коде функций;
* требование считается выполненным, когда на него есть автоматический тест или ручной сценарий приёмки из раздела 9 ЧТЗ.
