# Модель данных: доска задач и календарь задач

Миграция: `migrations/versions/0005_task_board_and_calendar.py` (down_revision `0004`).

## tasks (изменение)

| Поле | Тип | По умолчанию | Назначение |
|---|---|---|---|
| status | varchar(20) | `todo` | + значение `review` («На проверке») |
| position | integer, not null | `id * 1000` при миграции | порядок в колонке |
| priority | varchar(10), not null | `normal` | `normal` или `high` |
| done_at | timestamp, null | — | когда переведена в `done`. При миграции у выполненных = `created_at` |
| updated_at | timestamp, null | — | последнее изменение, для `SEQUENCE` и `LAST-MODIFIED` в подписке |

Индекс: `(status, position)`.

`TASK_STATUSES = {"todo": "К выполнению", "in_progress": "В работе", "review": "На проверке", "done": "Выполнено"}`.
Название `done` в интерфейсе меняется с «Готово» на «Выполнено», как на доске.

### Переходы

| Из \ В | todo | in_progress | review | done |
|---|---|---|---|---|
| todo | — | И, А, Р | И, А, Р | А, Р; И → превращается в review |
| in_progress | И, А, Р | — | И, А, Р | А, Р; И → превращается в review |
| review | А, Р (комментарий обязателен) | А, Р (комментарий обязателен) | — | А, Р |
| done | А, Р | А, Р | А, Р | — |

И — исполнитель, А — автор, Р — руководитель. Если исполнитель — сам автор (или руководитель), у него права автора,
и «Выполнено» ставится сразу. Остальные переходы дают 403 («Менять статус может исполнитель, автор или руководитель»)
или 422 с пояснением. Реализация: `app/tasks_board.py → resolve_target(), can_move()`; тест: `test_transition_rules`.

## task_events (новая)

| Поле | Тип | Назначение |
|---|---|---|
| id | integer PK | |
| task_id | FK tasks.id, ON DELETE CASCADE | |
| user_id | FK users.id, ON DELETE SET NULL | кто изменил (null — бот без привязки или система) |
| field | varchar(20) | `status`, `due_date`, `assignee` |
| old_value | varchar(50), null | |
| new_value | varchar(50), null | |
| comment | text, null | обязателен при возврате с проверки |
| source | varchar(10) | `cabinet`, `telegram`, `vk` |
| created_at | timestamp | |

Индекс: `(task_id, created_at)`.

## calendar_feeds (новая)

| Поле | Тип | Назначение |
|---|---|---|
| id | integer PK | |
| user_id | FK users.id, unique, ON DELETE CASCADE | одна подписка на человека |
| token | varchar(64), unique | секрет ссылки (`token_urlsafe(32)` — 43 символа) |
| enabled | boolean | включена ли |
| consent_at | timestamp | когда подтверждено предупреждение о передаче названий |
| created_at | timestamp | когда выпущен текущий токен |

## Производные значения (не хранятся)

- **Готовность проекта**: `done / всего` по задачам проекта; просроченные — `due_date < сегодня` и статус не `done`.
- **Доля в срок** (P3): задачи проекта в `done`, у которых `done_at::date <= due_date`, делённые на задачи со сроком.
- **Время в работе** (P3): медиана от первого события `→ in_progress` до `→ done` по `task_events`.
