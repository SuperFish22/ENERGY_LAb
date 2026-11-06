# Сценарии n8n для Energy Lab

n8n работает на **внешнем** сервере вместе с Telegram-ботом. Energy Lab (сервер в РФ) в мессенджеры сама не ходит:
n8n вызывает её закрытый API `/api/bot/*` и забирает очередь уведомлений. Персональные данные остаются в БД в РФ.

| Файл | Что делает | Готовность |
|---|---|---|
| `telegram-bot.json` | команды `/start`, `/link`, `/unlink`, `/tasks` (с кнопками «в работу»/«готово»), `/ask`, `/discussions`, ответ в обсуждение (reply), `/question`, `/afisha`, `/sos` с рассылкой дежурным | рабочий шаблон |
| `notifications-outbox.json` | раз в минуту забирает `/api/bot/notifications`, отправляет в Telegram или VK, отмечает отправленным | рабочий шаблон |
| `vk-bot-inbound.json` | приём сообщений сообщества VK (Callback API): подтверждение сервера, проверка секрета | каркас, этап 2 |
| `google-sheets-registry.json` | каждую ночь обновляет Google Таблицу «Реестр» (ключ — `CODE`) | ждёт таблицу |
| `google-docs-from-template.json` | по вебхуку `{code, template_id}` копирует шаблон Google Docs и заменяет метки `{{KEY}}` | ждёт шаблоны |

Файлы собраны скриптом `generate.py` (`python n8n/generate.py n8n/workflows`) — правьте скрипт, а не JSON руками.

## Установка

1. В n8n: **Workflows → Import from File** — по очереди все `.json`.
2. **Credentials**:
   * «Energy Lab Bot API» — тип *Header Auth*: имя `Authorization`, значение `Bearer <BOT_API_TOKEN из .env сервера>`;
   * «Telegram ENERGY bot» — тип *Telegram API*, токен от @BotFather;
   * «Google сервисный аккаунт» — тип *Google API (Service Account)*; дайте сервисному аккаунту доступ «Редактор» к таблице и папке;
   * «Energy Lab → n8n» — *Header Auth* для вебхука документов (любой длинный секрет).
3. **Переменные окружения n8n** (`.env` контейнера n8n):
   ```
   LAB_URL=https://lab.example.ru
   VK_GROUP_TOKEN=…          # ключ доступа сообщества с правом «сообщения»
   VK_SECRET=…               # секрет Callback API
   VK_CONFIRMATION=…         # строка подтверждения Callback API
   GSHEET_REGISTRY_ID=…      # ID Google Таблицы с листом «Реестр»
   GDRIVE_FOLDER_ID=…        # папка для документов проектов
   GDOC_TEMPLATE_ID=…        # шаблон по умолчанию
   N8N_BLOCK_ENV_ACCESS_IN_NODE=false
   ```
4. В каждом импортированном узле с ключом выберите созданный credential (n8n не переносит их при импорте).
5. Активируйте workflow. Проверка: напишите боту `/start`.

## На сервере Energy Lab

В `deploy/nginx.conf` замените `N8N_SERVER_IP` на IP сервера n8n — остальным адресам `/api/bot/` закрыт.

## Если узел не открылся после импорта

Версии узлов указаны под n8n 1.x (Switch v3, HTTP Request v4.2, Code v2, Google Sheets v4.5). Если ваша версия старше —
обновите n8n или пересоздайте узел с теми же параметрами: URL, тело запроса и код в узлах самодостаточны.
