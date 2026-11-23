"""Генератор шаблонов сценариев n8n для Energy Lab. Запуск: python gen_n8n.py <папка>"""
import json
import os
import sys
import uuid
from pathlib import Path

OUT = Path(sys.argv[1])
# Адрес сайта подставляется прямо в сценарии: в n8n 2.x доступ узлов к переменным окружения закрыт по умолчанию,
# и открывать его ради одного адреса незачем (переменные n8n могут содержать секреты).
LAB_URL = os.environ.get("LAB_URL", "https://lab.energy-academia.duckdns.org").rstrip("/")
API = "={{ $env.LAB_URL }}/api/bot"
CRED_LAB = {"httpHeaderAuth": {"id": "", "name": "Energy Lab Bot API"}}


def node(name, type_, params, pos, version=1, creds=None):
    n = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, name + type_)), "name": name, "type": type_,
         "typeVersion": version, "position": pos, "parameters": params}
    if creds:
        n["credentials"] = creds
    if type_ in ("n8n-nodes-base.telegramTrigger", "n8n-nodes-base.webhook"):
        # Постоянный webhookId: адрес вебхука /webhook/<uuid>/... без имени узла (кириллица и «:» в имени
        # дают адрес, на который n8n отвечает 404, и Telegram пишет «Wrong response from the webhook»)
        n["webhookId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "energy-lab-webhook:" + name))
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


# Постоянные ID: повторный импорт (n8n import:workflow) обновляет сценарий, а не создаёт копию.
WF_IDS = {"telegram-bot.json": "elabTelegramBot1", "notifications-outbox.json": "elabNotifyOutbox",
          "vk-bot-inbound.json": "elabVkInbound001", "google-sheets-registry.json": "elabGSheetRegist",
          "google-docs-from-template.json": "elabGDocTemplate"}


def wf(name, nodes, conns, tags):
    return {"name": name, "nodes": nodes, "connections": conns, "active": False,
            "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
            # без тегов: n8n при импорте пытается создать тег заново и падает на UNIQUE(tag_entity.name)
            "meta": {"templateCredsSetupCompleted": False},
            "pinData": {}}


def link(*pairs):
    c = {}
    for src, dst, out in pairs:
        c.setdefault(src, {"main": []})
        while len(c[src]["main"]) <= out:
            c[src]["main"].append([])
        c[src]["main"][out].append({"node": dst, "type": "main", "index": 0})
    return c


# Telegram-бот, доставка уведомлений и VK-бот с 17.11.2026 — Python-сервис bot/ (см. bot/README.md).
# В n8n остаётся только выгрузка в Google Таблицу и документы из шаблона Google Docs.

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
for fname, obj in (("google-sheets-registry.json", g), ("google-docs-from-template.json", d)):
    obj = {"id": WF_IDS[fname], **obj}
    text = json.dumps(obj, ensure_ascii=False, indent=2).replace("{{ $env.LAB_URL }}", LAB_URL)
    (OUT / fname).write_text(text, encoding="utf-8")
    print(fname, len(obj["nodes"]), "узлов")
