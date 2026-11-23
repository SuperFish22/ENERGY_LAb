# Контракты: адреса доски, календаря и подписки

Все адреса `/cabinet/*` требуют входа. Все `POST` требуют CSRF-токен в поле формы `csrf_token` (скрипт доски отправляет его в `FormData`).

## Доска и календарь

| Метод и адрес | Параметры | Ответ |
|---|---|---|
| `GET /cabinet/tasks` | `view=board` (по умолчанию), `calendar` или `list`; `scope=mine`, `dept` или `all` (только руководитель); `event`, `dept_id`, `assignee`, `flag=overdue` или `nodue`; для календаря `mode=month` или `week`, `d=YYYY-MM-DD` | HTML |
| `POST /cabinet/tasks/{id}/move` | `status`, `expected` (статус, который видел пользователь, — защита от одновременных правок), `before_id` (необязательно, карточка, перед которой встать), `comment` (обязателен при возврате с проверки) | `Accept: application/json` → `{"ok": true, "status": "review", "status_name": "На проверке", "position": 3000}`. Иначе 303 обратно. Ошибки: 403 `{"error": "Менять статус может исполнитель, автор или руководитель"}`, 422 `{"error": "Напишите, что исправить"}`, 409 `{"error": "Задачу уже переместил(а) …", "status": "…"}` |
| `POST /cabinet/tasks/{id}/due` (P3) | `due_date` | 303. 403, если не автор и не руководитель |
| `GET /cabinet/tasks/{id}` (P3) | — | HTML: карточка с историей |
| `GET /cabinet/projects/{id}?tab=tasks` | те же фильтры, `event` подставлен | HTML |

Старый `POST /cabinet/tasks/{id}/status` остаётся как обёртка над `move`, чтобы не ломать существующие формы.

## Подписка на календарь

| Метод и адрес | Параметры | Ответ |
|---|---|---|
| `POST /cabinet/profile/calendar` | `action=enable` (нужно `consent=1`), `rotate` или `disable` | 303 на `/cabinet/profile#calendar`, flash-сообщение. Запись в аудит `calendar_feed_<action>` |
| `GET /cal/{token}.ics` | — | `200 text/calendar; charset=utf-8`, `Content-Disposition: inline; filename="energy-lab.ics"`, `Cache-Control: private, max-age=900`. Неизвестный, отключённый токен или неактивный пользователь — `404` с пустым телом |

### Пример ответа `.ics`

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Energy Lab//Tasks//RU
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Energy Lab — мои задачи
X-WR-TIMEZONE:Europe/Moscow
REFRESH-INTERVAL;VALUE=DURATION:PT1H
X-PUBLISHED-TTL:PT1H
BEGIN:VEVENT
UID:task-42@lab.energy-academia.duckdns.org
DTSTAMP:20261113T090000Z
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261121
SUMMARY:[В работе] Закупить реквизит — Ночь в музее
DESCRIPTION:Статус: В работе\nОткрыть: https://lab…/cabinet/tasks
URL:https://lab.energy-academia.duckdns.org/cabinet/tasks
SEQUENCE:3
END:VEVENT
BEGIN:VEVENT
UID:event-7@lab.energy-academia.duckdns.org
DTSTAMP:20261113T090000Z
DTSTART:20261129T160000Z
DTEND:20261129T190000Z
SUMMARY:Старт: Ночь в музее
LOCATION:Пространство ENERGY
END:VEVENT
END:VCALENDAR
```

## API бота (изменения)

| Адрес | Изменение |
|---|---|
| `POST /api/bot/tasks/{id}/status` | `status` принимает `todo`, `in_progress`, `review`, `done`. Исполнитель с `done` при чужом авторе получает `review` и ответ `{"ok": true, "status": "review", "status_name": "На проверке", "note": "Отправлено на проверку автору"}` |
| `GET /api/bot/tasks` | без изменений формата. Включает задачи в `review` |
