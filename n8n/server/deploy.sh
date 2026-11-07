#!/usr/bin/env bash
# Обновление сценариев Energy Lab в работающем контейнере n8n из папки ./workflows (её присылает GitHub Actions).
# Трогает только сценарии из ./workflows (по их постоянным ID), остальные сценарии n8n не меняются.
# Сохраняет то, что настроено руками: подключённые учётные данные и включён ли сценарий.
set -euo pipefail
cd "$(dirname "$0")"
C="${N8N_CONTAINER:-n8n}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
docker inspect "$C" >/dev/null 2>&1 || { echo "Контейнер $C не найден"; exit 1; }

echo "1/4 Сохраняю текущее состояние сценариев и список учётных данных"
# временная папка внутри контейнера: создаём от root и отдаём пользователю node, под которым работает n8n
docker exec -u root "$C" sh -c 'rm -rf /tmp/elab && mkdir -p /tmp/elab/cur && chown -R node:node /tmp/elab'
docker exec "$C" sh -c 'n8n export:workflow --all --separate --output=/tmp/elab/cur >/dev/null 2>&1 || true
  n8n export:credentials --all --output=/tmp/elab/creds.json >/dev/null 2>&1 || echo "[]" > /tmp/elab/creds.json'
docker cp "$C:/tmp/elab/cur" "$TMP/cur" >/dev/null 2>&1 || mkdir -p "$TMP/cur"
docker cp "$C:/tmp/elab/creds.json" "$TMP/creds.json" >/dev/null 2>&1 || echo "[]" > "$TMP/creds.json"

echo "2/4 Подставляю учётные данные и статус «включён»"
mkdir -p "$TMP/new"
python3 - "$TMP" <<'PY'
import glob, json, os, sys
tmp = sys.argv[1]
try:
    creds = json.load(open(f"{tmp}/creds.json"))
except ValueError:
    creds = []
by_name = {c["name"]: c["id"] for c in creds}           # учётные данные ищем по имени
current = {}
for f in glob.glob(f"{tmp}/cur/*.json"):
    w = json.load(open(f)); current[w.get("id")] = w
activate = []
for f in sorted(glob.glob("workflows/*.json")):
    w = json.load(open(f))
    old = current.get(w["id"])
    old_nodes = {n["name"]: n for n in (old or {}).get("nodes", [])}
    missing = []
    for n in w["nodes"]:
        for ctype, ref in (n.get("credentials") or {}).items():
            prev = (old_nodes.get(n["name"], {}).get("credentials") or {}).get(ctype)
            if prev and prev.get("id"):
                n["credentials"][ctype] = prev                  # как было настроено руками
            elif ref.get("name") in by_name:
                n["credentials"][ctype] = {"id": by_name[ref["name"]], "name": ref["name"]}
            else:
                missing.append(ref.get("name"))
    want = bool(old and old.get("active")) and not missing
    w["active"] = False                                     # включаем после импорта отдельной командой
    w.pop("tags", None)                                     # теги при импорте создаются заново → ошибка UNIQUE
    if want:
        activate.append(w["id"])
    json.dump(w, open(f"{tmp}/new/{os.path.basename(f)}", "w"), ensure_ascii=False)
    note = f"; нет учётных данных: {', '.join(sorted(set(missing)))}" if missing else ""
    print(f"   {w['name']}: {'будет включён' if want else 'выключен'}{note}")
open(f"{tmp}/activate.txt", "w").write("\n".join(activate))
PY

echo "3/4 Импортирую"
docker exec -u root "$C" rm -rf /tmp/elab/new
docker cp "$TMP/new" "$C:/tmp/elab/new" >/dev/null
docker exec -u root "$C" chown -R node:node /tmp/elab/new        # docker cp кладёт файлы от чужого пользователя
docker exec "$C" n8n import:workflow --separate --input=/tmp/elab/new

echo "4/4 Включаю сценарии, которые были включены, и перезапускаю n8n"
while read -r id; do
  [ -n "$id" ] || continue
  docker exec "$C" n8n publish:workflow --id="$id" >/dev/null 2>&1 \
    || docker exec "$C" n8n update:workflow --id="$id" --active=true >/dev/null 2>&1 \
    || echo "   не удалось включить $id автоматически — включите в интерфейсе n8n"
done < "$TMP/activate.txt"
docker exec -u root "$C" rm -rf /tmp/elab
docker restart "$C" >/dev/null
echo "Готово"
