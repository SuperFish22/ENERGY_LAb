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
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip | gpg --batch --yes --trust-model always --encrypt --recipient "$BACKUP_GPG_RECIPIENT" -o "$FILE"
ls -1t backups/*.gpg | tail -n +15 | xargs -r rm --
if command -v rclone >/dev/null && rclone listremotes | grep -q '^gdrive:'; then
  rclone copy "$FILE" "gdrive:Резервные копии/" && rclone delete --min-age 15d "gdrive:Резервные копии/"
fi
# 5) обезличивание покупателей старше 30 дней и чистка очереди уведомлений (app/maintenance.py)
docker compose -f docker-compose.prod.yml exec -T web python -m app.maintenance
echo "OK $FILE"
