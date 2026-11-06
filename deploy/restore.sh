#!/usr/bin/env bash
# Восстановление из копии: ./deploy/restore.sh backups/energy_lab_2026-11-20_0300.sql.gz.gpg
# Нужен закрытый ключ GPG руководителя (на сервере его нет — импортируйте на время восстановления).
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
gpg --decrypt "$1" | gunzip | docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
