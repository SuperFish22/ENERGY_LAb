"""Генератор шаблонов сценариев n8n для Energy Lab. Запуск: python gen_n8n.py <папка>"""
import json
import sys
import uuid
from pathlib import Path

OUT = Path(sys.argv[1])
API = "={{ $env.LAB_URL }}/api/bot"
CRED_LAB = {"httpHeaderAuth": {"id": "", "name": "Energy Lab Bot API"}}
CRED_TG = {"telegramApi": {"id": "", "name": "Telegram ENERGY bot"}}


def node(name, type_, params, pos, version=1, creds=None):
    n = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name + type_)), "name": name, "type": type_,
         "typeVersion": version, "position": pos, "parameters": params}
    if creds:
        n["credentials"] = creds
    return n


def http(name, method, path, pos, body=None, query=None):
    p = {"method": method, "url": f"{API}{path}", "authentication": "genericCredentialType",
         "genericAuthType": "httpHeaderAuth", "options": {"response": {"response": {"neverError": True,
                                                                                    "fullResponse": False}}}}
    if query:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
    if body:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    return node(name, "n8n-nodes-base.httpRequest", p, pos, 4.2, CRED_LAB)


def code(name, js, pos):
    return node(name, "n8n-nodes-base.code", {"jsCode": js}, pos, 2)


def wf(name, nodes, conns, tags):
    return {"name": name, "nodes": nodes, "connections": conns, "active": False,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
            "tags": [{"name": t} for t in tags], "meta": {"templateCredsSetupCompleted": False},
            "pinData": {}}


def link(*pairs):
    c = {}
    for src, dst, out in pairs:
        c.setdefault(src, {"main": []})
        while len(c[src]["main"]) <= out:
            c[src]["main"].append([])
        c[src]["main"][out].append({"node": dst, "type": "main", "index": 0})
    return c


# ---------------------------------------------------------------- 1. Telegram-бот
PARSE = r"""// Разбор входящего сообщения или нажатия кнопки → маршрут (номер выхода Switch)
const u = $json;
const msg = u.message || (u.callback_query && u.callback_query.message) || {};
const from = (u.message && u.message.from) || (u.callback_query && u.callback_query.from) || {};
const chatId = msg.chat ? msg.chat.id : from.id;
const who = { channel: 'telegram', user_id: String(from.id) };
const name = [from.first_name, from.last_name].filter(Boolean).join(' ');
let text = (u.message && u.message.text) || '';
const cb = u.callback_query ? u.callback_query.data : '';
const replyTo = u.message && u.message.reply_to_message ? (u.message.reply_to_message.text || '') : '';
const ROUTES = { start: 0, link: 1, unlink: 2, tasks: 3, task_status: 4, ask_menu: 5, ask: 6,
                 discussions: 7, reply: 8, question: 9, afisha: 10, sos: 11, help: 12 };
let route = 'help', args = {};
if (cb.startsWith('task:')) { const [, id, st] = cb.split(':'); route = 'task_status'; args = { id, status: st }; }
else if (cb.startsWith('ask:')) { route = 'help'; args = { hint: `Напишите одним сообщением:\n/ask ${cb.slice(4)} Тема вопроса | подробности` }; }
else if (/^\/start/.test(text)) route = 'start';
else if (/^\/link\s+\d{6}/.test(text)) { route = 'link'; args = { code: text.match(/\d{6}/)[0] }; }
else if (/^\/unlink/.test(text)) route = 'unlink';
else if (/^\/tasks|^мои задачи/i.test(text)) route = 'tasks';
else if (/^\/ask\s+[A-Z]+\s+.+/.test(text)) {
  const m = text.match(/^\/ask\s+([A-Z]+)\s+(.+)$/s); const [title, ...rest] = m[2].split('|');
  route = 'ask'; args = { department_code: m[1], title: title.trim().slice(0, 200), text: rest.join('|').trim() || null };
}
else if (/^\/ask|^вопрос отделу/i.test(text)) route = 'ask_menu';
else if (/^\/discussions|^обсуждения/i.test(text)) route = 'discussions';
else if (/^\/question\s+.{3,}/s.test(text)) { route = 'question'; args = { text: text.replace(/^\/question\s+/, '') }; }
else if (/^\/afisha|^афиша/i.test(text)) route = 'afisha';
else if (/^\/sos|^sos/i.test(text)) { route = 'sos'; args = { text: text.replace(/^\/?sos\s*/i, '') || null }; }
else if (replyTo && /#обсуждение(\d+)/.test(replyTo)) { route = 'reply'; args = { id: replyTo.match(/#обсуждение(\d+)/)[1], text }; }
return [{ json: { route: ROUTES[route], routeName: route, chatId, who, name, args } }];
"""

FORMAT = r"""// Ответ API → текст для пользователя
const p = $('Разбор команды').first().json;
const r = $json;
const err = r.detail ? (typeof r.detail === 'string' ? r.detail : 'Проверьте команду') : null;
let text = '', keyboard = null;
switch (p.routeName) {
  case 'start': text = r.linked ? `Привет, ${r.full_name}! Центр управления на связи 🚀\n/tasks — мои задачи\n/ask — вопрос отделу\n/discussions — обсуждения отдела\n/afisha — ближайшие запуски\n/sos — экстренная связь`
                                : 'Привет! Это бот Energy Lab.\nЧтобы видеть свои задачи, получите код в кабинете: Профиль и бот → «Получить код привязки», и отправьте сюда /link КОД.\n/afisha — ближайшие запуски, /question — вопрос на доску.'; break;
  case 'link': text = err || `Готово, ${r.full_name}. Аккаунт привязан, уведомления будут приходить сюда.`; break;
  case 'unlink': text = err || 'Аккаунт отвязан. Уведомлений больше не будет.'; break;
  case 'tasks':
    if (err) { text = err; break; }
    if (!r.tasks.length) { text = 'Открытых задач нет. Чистая орбита ✨'; break; }
    text = 'Ваши задачи:\n' + r.tasks.map((t, i) => `${i + 1}. ${t.title}${t.event ? ' — ' + t.event : ''}\n   ${t.status_name}${t.due_date ? ', срок ' + t.due_date : ''}${t.overdue ? ' ⚠️ просрочено' : ''}`).join('\n');
    keyboard = { inline_keyboard: r.tasks.slice(0, 8).map((t, i) => [
      { text: `${i + 1} → в работу`, callback_data: `task:${t.id}:in_progress` },
      { text: `${i + 1} → готово`, callback_data: `task:${t.id}:done` }]) };
    break;
  case 'task_status': text = err || `Статус задачи: ${r.status_name}`; break;
  case 'ask_menu':
    text = 'Какому отделу вопрос?';
    keyboard = { inline_keyboard: (r.departments || []).map(d => [{ text: d.name, callback_data: `ask:${d.code}` }]) }; break;
  case 'ask': text = err || `Вопрос отправлен отделу. Эксперты получат уведомление.\n${r.url}`; break;
  case 'discussions':
    text = err || (r.discussions.length ? 'Открытые обсуждения:\n' + r.discussions.map(d => `#обсуждение${d.id} ${d.title} (${d.messages})\n${d.url}`).join('\n') + '\n\nЧтобы ответить — ответьте (reply) на это сообщение строкой с нужным #обсуждением.' : 'Открытых обсуждений нет.'); break;
  case 'reply': text = err || 'Ответ добавлен в обсуждение.'; break;
  case 'question': text = err || 'Вопрос отправлен модератору. Ответ придёт сюда.'; break;
  case 'afisha': text = (r.events || []).length ? 'Ближайшие запуски:\n' + r.events.map(e => `${e.date} — ${e.title} (${e.age}), ${e.price} ₽\n${e.url}`).join('\n') : 'Пока нет мероприятий в продаже.'; break;
  case 'sos': text = r.reply || 'Если есть угроза жизни или здоровью — звоните 112.'; break;
  default: text = p.args.hint || 'Команды: /tasks, /ask, /discussions, /afisha, /question ТЕКСТ, /sos, /link КОД';
}
return [{ json: { chatId: p.chatId, text, reply_markup: keyboard ? JSON.stringify(keyboard) : '' , sos: p.routeName === 'sos' ? r : null } }];
"""

who = "={{ $('Разбор команды').first().json.who"
q_who = {"channel": "telegram", "user_id": "={{ $('Разбор команды').first().json.who.user_id }}"}
x0, y0 = 700, 0
calls = [
    ("API: кто я", "GET", "/me", None, q_who),
    ("API: привязать", "POST", "/link", "={{ JSON.stringify({ ...$json.who, code: $json.args.code }) }}", None),
    ("API: отвязать", "POST", "/unlink", "={{ JSON.stringify($json.who) }}", None),
    ("API: мои задачи", "GET", "/tasks", None, q_who),
    ("API: статус задачи", "POST", "=/tasks/{{ $json.args.id }}/status",
     "={{ JSON.stringify({ ...$json.who, status: $json.args.status }) }}", None),
    ("API: отделы", "GET", "/departments", None, None),
    ("API: вопрос отделу", "POST", "/discussions", "={{ JSON.stringify({ ...$json.who, ...$json.args }) }}", None),
    ("API: обсуждения", "GET", "/discussions", None, q_who),
    ("API: ответ в обсуждение", "POST", "=/discussions/{{ $json.args.id }}/messages",
     "={{ JSON.stringify({ ...$json.who, text: $json.args.text }) }}", None),
    ("API: вопрос на доску", "POST", "/questions",
     "={{ JSON.stringify({ ...$json.who, name: $json.name, text: $json.args.text }) }}", None),
    ("API: афиша", "GET", "/events", None, None),
    ("API: SOS", "POST", "/sos", "={{ JSON.stringify({ ...$json.who, name: $json.name, text: $json.args.text }) }}",
     None),
]
nodes = [
    node("Telegram: входящие", "n8n-nodes-base.telegramTrigger", {"updates": ["message", "callback_query"],
                                                                   "additionalFields": {}}, [0, 300], 1.1, CRED_TG),
    code("Разбор команды", PARSE, [220, 300]),
    node("Маршрут", "n8n-nodes-base.switch", {"mode": "expression", "numberOutputs": 13,
                                               "output": "={{ $json.route }}"}, [440, 300], 3),
    code("Текст ответа", FORMAT, [1000, 300]),
    node("Telegram: ответ", "n8n-nodes-base.telegram",
         {"chatId": "={{ $json.chatId }}", "text": "={{ $json.text }}",
          "additionalFields": {"appendAttribution": False, "reply_markup": "={{ $json.reply_markup }}"}},
         [1220, 300], 1.2, CRED_TG),
    node("Это SOS?", "n8n-nodes-base.if", {"conditions": {"options": {"caseSensitive": True}, "combinator": "and",
                                                           "conditions": [{"leftValue": "={{ !!$json.sos }}",
                                                                           "rightValue": True,
                                                                           "operator": {"type": "boolean",
                                                                                        "operation": "true"}}]}},
         [1220, 520], 2),
    code("SOS: список дежурных", r"""const s = $json.sos; const p = $('Разбор команды').first().json;
const text = `🆘 SOS от ${p.name || 'участника'} (${p.who.channel}): ${p.args.text || 'без описания'}`;
return (s.duty || []).map(d => ({ json: { ...d, text } }));""", [1440, 520]),
    node("SOS: дежурным в Telegram", "n8n-nodes-base.telegram",
         {"chatId": "={{ $json.chat_id }}", "text": "={{ $json.text }}", "additionalFields": {"appendAttribution": False}},
         [1660, 520], 1.2, CRED_TG),
]
pairs = [("Telegram: входящие", "Разбор команды", 0), ("Разбор команды", "Маршрут", 0)]
for i, (name, method, path, body, query) in enumerate(calls):
    n = http(name, method, path, [x0, y0 + i * 90], body, query)
    if path.startswith("="):
        n["parameters"]["url"] = "={{ $env.LAB_URL }}/api/bot" + path[1:]
    nodes.append(n)
    pairs += [("Маршрут", name, i), (name, "Текст ответа", 0)]
pairs += [("Маршрут", "Текст ответа", 12), ("Текст ответа", "Telegram: ответ", 0), ("Текст ответа", "Это SOS?", 0),
          ("Это SOS?", "SOS: список дежурных", 0), ("SOS: список дежурных", "SOS: дежурным в Telegram", 0)]
bot = wf("Energy Lab — Telegram-бот", nodes, link(*pairs), ["energy-lab", "telegram"])

# ---------------------------------------------------------------- 2. Очередь уведомлений
SPLIT = "return ($json.items || []).map(i => ({ json: i }));"
notes_nodes = [
    node("Каждую минуту", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}}, [0, 200], 1.2),
    http("API: очередь", "GET", "/notifications", [220, 200], query={"limit": "50"}),
    code("По одному", SPLIT, [440, 200]),
    node("Канал", "n8n-nodes-base.switch", {"mode": "expression", "numberOutputs": 2,
                                             "output": "={{ $json.channel === 'vk' ? 1 : 0 }}"}, [660, 200], 3),
    node("Telegram: отправить", "n8n-nodes-base.telegram",
         {"chatId": "={{ $json.chat_id }}", "text": "={{ $json.text }}", "additionalFields": {"appendAttribution": False}},
         [880, 100], 1.2, CRED_TG),
    node("VK: отправить", "n8n-nodes-base.httpRequest",
         {"method": "POST", "url": "https://api.vk.com/method/messages.send", "sendBody": True,
          "contentType": "form-urlencoded",
          "bodyParameters": {"parameters": [
              {"name": "user_id", "value": "={{ $json.chat_id }}"},
              {"name": "random_id", "value": "={{ $json.id }}"},
              {"name": "message", "value": "={{ $json.text }}"},
              {"name": "access_token", "value": "={{ $env.VK_GROUP_TOKEN }}"},
              {"name": "v", "value": "5.199"}]}, "options": {}}, [880, 300], 4.2),
    node("Вернуть id", "n8n-nodes-base.code",
         {"jsCode": "return $('По одному').all().filter((_, i) => i < $input.all().length).map((x, i) => ({ json: { id: $('Канал').all()[i] ? $('Канал').all()[i].json.id : x.json.id } }));",
          "mode": "runOnceForAllItems"}, [1100, 200], 2),
    http("API: отметить отправленным", "POST", "/notifications/{{ $json.id }}/sent", [1320, 200]),
]
notes_nodes[-1]["parameters"]["url"] = "={{ $env.LAB_URL }}/api/bot/notifications/{{ $json.id }}/sent"
# Простой и надёжный вариант: id берём из исходного элемента через pairedItem
notes_nodes[-2]["parameters"]["jsCode"] = "// id уведомления берём из исходного элемента очереди (связь элементов n8n)\nreturn $input.all().map((x, i) => ({ json: { id: $('По одному').itemMatching(i).json.id } }));"
notes = wf("Energy Lab — доставка уведомлений", notes_nodes, link(
    ("Каждую минуту", "API: очередь", 0), ("API: очередь", "По одному", 0), ("По одному", "Канал", 0),
    ("Канал", "Telegram: отправить", 0), ("Канал", "VK: отправить", 1),
    ("Telegram: отправить", "Вернуть id", 0), ("VK: отправить", "Вернуть id", 0),
    ("Вернуть id", "API: отметить отправленным", 0)), ["energy-lab", "уведомления"])

# ---------------------------------------------------------------- 3. VK-бот (Callback API)
VK_PARSE = r"""// VK Callback API: confirmation — вернуть строку подтверждения; message_new — передать в разбор
const b = $json.body || {};
if (b.type === 'confirmation') return [{ json: { confirm: true } }];
if (b.secret !== $env.VK_SECRET) return [];
const o = (b.object && b.object.message) || {};
let text = o.text || '';
const payload = o.payload ? JSON.parse(o.payload) : null;
return [{ json: { confirm: false, peer: o.peer_id, user_id: String(o.from_id), text, payload } }];
"""
vk_nodes = [
    node("VK: вебхук", "n8n-nodes-base.webhook", {"httpMethod": "POST", "path": "energy-lab-vk",
                                                   "responseMode": "responseNode", "options": {}}, [0, 200], 2),
    code("VK: разбор", VK_PARSE, [220, 200]),
    node("Подтверждение?", "n8n-nodes-base.if", {"conditions": {"options": {"caseSensitive": True},
                                                                 "combinator": "and", "conditions": [
        {"leftValue": "={{ $json.confirm }}", "rightValue": True,
         "operator": {"type": "boolean", "operation": "true"}}]}}, [440, 200], 2),
    node("Ответ: строка подтверждения", "n8n-nodes-base.respondToWebhook",
         {"respondWith": "text", "responseBody": "={{ $env.VK_CONFIRMATION }}", "options": {}}, [660, 100], 1.1),
    node("Ответ: ok", "n8n-nodes-base.respondToWebhook", {"respondWith": "text", "responseBody": "ok",
                                                           "options": {}}, [660, 300], 1.1),
    node("Передать в общий разбор", "n8n-nodes-base.executeWorkflow",
         {"source": "parameter", "workflowJson": "", "mode": "each",
          "options": {}}, [880, 300], 1.1),
]
vk = wf("Energy Lab — VK-бот (вход)", vk_nodes, link(
    ("VK: вебхук", "VK: разбор", 0), ("VK: разбор", "Подтверждение?", 0),
    ("Подтверждение?", "Ответ: строка подтверждения", 0), ("Подтверждение?", "Ответ: ok", 1),
    ("Ответ: ok", "Передать в общий разбор", 0)), ["energy-lab", "vk"])

# ---------------------------------------------------------------- 4. Google Диск: реестр и документы
ROWS = "return ($json.rows || []).map(r => ({ json: r }));"
g_nodes = [
    node("Каждую ночь 02:30", "n8n-nodes-base.scheduleTrigger",
         {"rule": {"interval": [{"field": "cronExpression", "expression": "30 2 * * *"}]}}, [0, 200], 1.2),
    http("API: реестр", "GET", "/export/registry", [220, 200]),
    code("Строки", ROWS, [440, 200]),
    node("Google Таблица: реестр", "n8n-nodes-base.googleSheets",
         {"operation": "appendOrUpdate",
          "documentId": {"__rl": True, "mode": "id", "value": "={{ $env.GSHEET_REGISTRY_ID }}"},
          "sheetName": {"__rl": True, "mode": "name", "value": "Реестр"},
          "columns": {"mappingMode": "autoMapInputData", "matchingColumns": ["CODE"], "value": {}},
          "options": {}}, [660, 200], 4.5, {"googleApi": {"id": "", "name": "Google сервисный аккаунт"}}),
]
g = wf("Energy Lab — дублирование в Google Таблицу", g_nodes, link(
    ("Каждую ночь 02:30", "API: реестр", 0), ("API: реестр", "Строки", 0), ("Строки", "Google Таблица: реестр", 0)),
    ["energy-lab", "google"])

DOC_PREP = r"""// Метки {{KEY}} → список действий замены для Google Docs
const ph = $json.placeholders || {};
return [{ json: { code: ph.CODE, title: `${ph.CODE} ${ph.TITLE}`,
  actions: Object.entries(ph).map(([k, v]) => ({ action: 'replaceAll', text: `{{${k}}}`, replaceText: v == null ? '—' : String(v) })) } }];
"""
d_nodes = [
    node("Запуск по коду мероприятия", "n8n-nodes-base.webhook",
         {"httpMethod": "POST", "path": "energy-lab-doc", "authentication": "headerAuth", "options": {}},
         [0, 200], 2, {"httpHeaderAuth": {"id": "", "name": "Energy Lab → n8n"}}),
    http("API: метки проекта", "GET", "/export/events/{{ $json.body.code }}", [220, 200]),
    code("Подготовить замены", DOC_PREP, [440, 200]),
    node("Google Диск: копия шаблона", "n8n-nodes-base.googleDrive",
         {"operation": "copy", "fileId": {"__rl": True, "mode": "id",
                                           "value": "={{ $('Запуск по коду мероприятия').first().json.body.template_id || $env.GDOC_TEMPLATE_ID }}"},
          "name": "={{ $json.title }}", "sameFolder": False,
          "folderId": {"__rl": True, "mode": "id", "value": "={{ $env.GDRIVE_FOLDER_ID }}"}, "options": {}},
         [660, 200], 3, {"googleApi": {"id": "", "name": "Google сервисный аккаунт"}}),
    node("Google Docs: заменить метки", "n8n-nodes-base.httpRequest",
         {"method": "POST", "url": "=https://docs.googleapis.com/v1/documents/{{ $json.id }}:batchUpdate",
          "authentication": "predefinedCredentialType", "nodeCredentialType": "googleApi",
          "sendBody": True, "specifyBody": "json",
          "jsonBody": "={{ JSON.stringify({ requests: $('Подготовить замены').first().json.actions.map(a => ({ replaceAllText: { containsText: { text: a.text, matchCase: true }, replaceText: a.replaceText } })) }) }}",
          "options": {}}, [880, 200], 4.2, {"googleApi": {"id": "", "name": "Google сервисный аккаунт"}}),
]
d_nodes[1]["parameters"]["url"] = "={{ $env.LAB_URL }}/api/bot/export/events/{{ $json.body.code }}"
d = wf("Energy Lab — документ из шаблона Google Docs", d_nodes, link(
    ("Запуск по коду мероприятия", "API: метки проекта", 0), ("API: метки проекта", "Подготовить замены", 0),
    ("Подготовить замены", "Google Диск: копия шаблона", 0),
    ("Google Диск: копия шаблона", "Google Docs: заменить метки", 0)), ["energy-lab", "google"])

OUT.mkdir(parents=True, exist_ok=True)
for fname, obj in (("telegram-bot.json", bot), ("notifications-outbox.json", notes), ("vk-bot-inbound.json", vk),
                   ("google-sheets-registry.json", g), ("google-docs-from-template.json", d)):
    (OUT / fname).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(fname, len(obj["nodes"]), "узлов")
