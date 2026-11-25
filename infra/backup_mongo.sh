#!/bin/sh
# Backup diário do MongoDB (.pt e .fr): dump comprimido local + cópia para o armazenamento S3/R2.
# Cron na VM (03:40 todos os dias):  40 3 * * * /opt/construpilot/infra/backup_mongo.sh >> /var/log/cp-backup.log 2>&1
# Retenção: 14 dias locais. No R2, configurar uma regra de ciclo de vida de 30 dias no bucket de backups.
# Para a cópia remota: rclone configurado com um remote "r2" (rclone config) e BACKUP_BUCKET em infra/.env.
set -eu
cd "$(dirname "$0")"
. ./.env
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p backups
FILE="backups/mongo-$STAMP.archive.gz"
docker compose exec -T mongo mongodump --quiet --archive --gzip \
  --username "$MONGO_ROOT_USER" --password "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin > "$FILE"
[ -s "$FILE" ] || { echo "ERRO: backup vazio"; exit 1; }
sha256sum "$FILE" > "$FILE.sha256"
if command -v rclone >/dev/null 2>&1 && [ -n "${BACKUP_BUCKET:-}" ]; then
  rclone copy "$FILE" "r2:$BACKUP_BUCKET/mongo/" && rclone copy "$FILE.sha256" "r2:$BACKUP_BUCKET/mongo/"
fi
find backups -name 'mongo-*.archive.gz*' -mtime +14 -delete
echo "$STAMP backup ok: $(du -h "$FILE" | cut -f1)"
