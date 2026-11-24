#!/usr/bin/env bash
# Chilli backup: a database dump (pg_dump) and the images folder.
#
# Run on the server from the Chilli folder, by hand or from cron (docs/guides/install.md):
#   bash deploy/backup.sh
#
# Backups go to BACKUP_DIR (default /opt/chilli-backups). Those older than KEEP_DAYS days are deleted
# from the server's disk. If .env has BACKUP_REMOTE (e.g. u123@u123.your-storagebox.de:chilli), the
# folder is also sent there with rsync over SSH. The remote folder mirrors the local one (--delete):
# it keeps the same KEEP_DAYS days, so it does not grow forever.
#
# Restoring: docs/guides/install.md, section "Restoring a backup".

set -euo pipefail

cd "$(dirname "$0")/.."

# Only the variables we need are read; the rest of .env (secrets) is not loaded into the shell.
env_value() {
    grep -E "^$1=" .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

BACKUP_DIR="${BACKUP_DIR:-$(env_value BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-/opt/chilli-backups}"
KEEP_DAYS="${KEEP_DAYS:-$(env_value BACKUP_KEEP_DAYS)}"
KEEP_DAYS="${KEEP_DAYS:-14}"
BACKUP_REMOTE="${BACKUP_REMOTE:-$(env_value BACKUP_REMOTE)}"
BACKUP_SSH_PORT="${BACKUP_SSH_PORT:-$(env_value BACKUP_SSH_PORT)}"
BACKUP_SSH_PORT="${BACKUP_SSH_PORT:-22}"

stamp="$(date +%Y-%m-%d-%H%M)"
mkdir -p "$BACKUP_DIR"

# Into a temporary file first: an interrupted backup does not pass for a complete one.
db_file="$BACKUP_DIR/db-$stamp.dump"
docker compose exec -T db pg_dump -U chilli -d chilli --format=custom > "$db_file.part"
mv "$db_file.part" "$db_file"

images_file="$BACKUP_DIR/images-$stamp.tar.gz"
docker compose exec -T api tar -C /data -czf - images > "$images_file.part"
mv "$images_file.part" "$images_file"

echo "backup: $db_file ($(du -h "$db_file" | cut -f1)), $images_file ($(du -h "$images_file" | cut -f1))"

# Removing old backups on the server.
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'images-*.tar.gz' \) \
    -mtime "+$KEEP_DAYS" -delete

if [ -n "$BACKUP_REMOTE" ]; then
    rsync -a --delete -e "ssh -p $BACKUP_SSH_PORT -o BatchMode=yes" "$BACKUP_DIR/" "$BACKUP_REMOTE/"
    echo "sent to: $BACKUP_REMOTE"
else
    echo "BACKUP_REMOTE not set: the backup stays on this server only"
fi
