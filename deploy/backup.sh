#!/usr/bin/env bash
# Ежедневная резервная копия (SYS-07, SYS-15). Cron: 0 3 * * * /opt/energy-lab/deploy/backup.sh
# 1) pg_dump → 2) шифрование GPG открытым ключом руководителей → 3) хранение 14 копий
# 4) копия на Google Диск через rclone (remote "gdrive", папка «Резервные копии»), если rclone настроен.
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
mkdir -p backups
STAMP=$(date +%Y-%m-%d_%H%M)
FILE="backups/energy_lab_${STAMP}.sql.gz.gpg"
COMPOSE="${COMPOSE_FILE:-docker-compose.server.yml}"     # на сервере с другим сайтом — server, иначе prod
[ -f "$COMPOSE" ] || COMPOSE=docker-compose.prod.yml
docker compose -f "$COMPOSE" exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip | gpg --batch --yes --trust-model always --encrypt --recipient "$BACKUP_GPG_RECIPIENT" -o "$FILE"
# фото (media) и документы/вложения (files) — отдельным зашифрованным архивом
FILES_ARCHIVE="backups/energy_lab_files_${STAMP}.tar.gz.gpg"
docker compose -f "$COMPOSE" exec -T web tar czf - -C /app media files \
  | gpg --batch --yes --trust-model always --encrypt --recipient "$BACKUP_GPG_RECIPIENT" -o "$FILES_ARCHIVE"
ls -1t backups/energy_lab_2*.gpg | tail -n +15 | xargs -r rm --
ls -1t backups/energy_lab_files_*.gpg | tail -n +8 | xargs -r rm --
if command -v rclone >/dev/null && rclone listremotes | grep -q '^gdrive:'; then
  rclone copy "$FILE" "gdrive:Резервные копии/" && rclone copy "$FILES_ARCHIVE" "gdrive:Резервные копии/" \
    && rclone delete --min-age 15d "gdrive:Резервные копии/"
fi
# 5) обезличивание покупателей старше 30 дней и чистка очереди уведомлений (app/maintenance.py)
docker compose -f "$COMPOSE" exec -T web python -m app.maintenance
echo "OK $FILE $FILES_ARCHIVE"
