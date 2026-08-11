#!/bin/bash
# Backup script for reports.json

BACKUP_DIR="./backups"
SOURCE_FILE="reports.json"

mkdir -p "$BACKUP_DIR"

if [ -f "$SOURCE_FILE" ]; then
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    cp "$SOURCE_FILE" "$BACKUP_DIR/reports_$TIMESTAMP.json"
    
    # Keep only the last 30 backups
    ls -1t "$BACKUP_DIR"/reports_*.json | tail -n +31 | xargs -r rm --
    echo "Backup completed: $BACKUP_DIR/reports_$TIMESTAMP.json"
else
    echo "Source file $SOURCE_FILE not found. Nothing to backup."
fi
