#!/bin/bash
# Backup script for SQLite database (users_data.db)

set -euo pipefail

BACKUP_DIR="./backups"
SOURCE_FILE="users_data.db"

mkdir -p "$BACKUP_DIR"

if [ -f "$SOURCE_FILE" ]; then
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    cp "$SOURCE_FILE" "$BACKUP_DIR/users_data_$TIMESTAMP.db"

    # Keep only the last 30 backups
    ls -1t "$BACKUP_DIR"/users_data_*.db 2>/dev/null | tail -n +31 | xargs -r rm --
    echo "Backup completed: $BACKUP_DIR/users_data_$TIMESTAMP.db"
else
    echo "Source file $SOURCE_FILE not found. Nothing to backup."
fi
