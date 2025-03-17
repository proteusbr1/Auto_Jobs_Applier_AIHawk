#!/bin/bash
# Database backup and recovery script for AIHawk application

set -e

# Configuration
BACKUP_DIR="/var/backups/aihawk"
POSTGRES_CONTAINER="aihawk_db_1"
POSTGRES_USER="postgres"
POSTGRES_DB="aihawk"
RETENTION_DAYS=7
S3_BUCKET="aihawk-backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="aihawk_backup_${TIMESTAMP}.sql.gz"
LOG_FILE="/var/log/aihawk/backup.log"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# Log function
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Error handling
error_exit() {
    log "ERROR: $1"
    exit 1
}

# Create backup
create_backup() {
    log "Starting database backup..."
    
    # Create database dump and compress it
    docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_DIR/$BACKUP_FILE" || error_exit "Failed to create database backup"
    
    # Check if backup file was created successfully
    if [ -f "$BACKUP_DIR/$BACKUP_FILE" ]; then
        BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
        log "Backup created successfully: $BACKUP_FILE (Size: $BACKUP_SIZE)"
    else
        error_exit "Backup file was not created"
    fi
    
    # Upload to S3 if AWS CLI is available
    if command -v aws &> /dev/null; then
        log "Uploading backup to S3..."
        aws s3 cp "$BACKUP_DIR/$BACKUP_FILE" "s3://$S3_BUCKET/" || log "WARNING: Failed to upload backup to S3"
    else
        log "AWS CLI not found, skipping S3 upload"
    fi
}

# Restore from backup
restore_backup() {
    if [ -z "$1" ]; then
        error_exit "No backup file specified for restoration"
    fi
    
    RESTORE_FILE="$1"
    
    if [ ! -f "$RESTORE_FILE" ]; then
        error_exit "Backup file does not exist: $RESTORE_FILE"
    fi
    
    log "Starting database restoration from $RESTORE_FILE..."
    
    # Confirm before proceeding
    read -p "This will overwrite the current database. Are you sure? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Restoration cancelled by user"
        exit 0
    fi
    
    # Restore database
    gunzip -c "$RESTORE_FILE" | docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" || error_exit "Failed to restore database"
    
    log "Database restored successfully from $RESTORE_FILE"
}

# Clean up old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days..."
    
    # Local cleanup
    find "$BACKUP_DIR" -name "aihawk_backup_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete
    
    # S3 cleanup if AWS CLI is available
    if command -v aws &> /dev/null; then
        log "Cleaning up old backups from S3..."
        
        # Get list of backups older than retention period
        CUTOFF_DATE=$(date -d "$RETENTION_DAYS days ago" +"%Y-%m-%d")
        
        # List objects and filter by date
        aws s3 ls "s3://$S3_BUCKET/" | grep "aihawk_backup_" | while read -r line; do
            # Extract date from listing
            FILE_DATE=$(echo "$line" | awk '{print $1}')
            FILE_NAME=$(echo "$line" | awk '{print $4}')
            
            # Compare dates
            if [[ "$FILE_DATE" < "$CUTOFF_DATE" ]]; then
                log "Deleting old S3 backup: $FILE_NAME"
                aws s3 rm "s3://$S3_BUCKET/$FILE_NAME"
            fi
        done
    fi
    
    log "Cleanup completed"
}

# List available backups
list_backups() {
    log "Available local backups:"
    find "$BACKUP_DIR" -name "aihawk_backup_*.sql.gz" -type f | sort
    
    if command -v aws &> /dev/null; then
        log "Available S3 backups:"
        aws s3 ls "s3://$S3_BUCKET/" | grep "aihawk_backup_"
    fi
}

# Download backup from S3
download_from_s3() {
    if [ -z "$1" ]; then
        error_exit "No backup file specified for download"
    fi
    
    S3_FILE="$1"
    LOCAL_FILE="$BACKUP_DIR/$(basename "$S3_FILE")"
    
    log "Downloading $S3_FILE from S3..."
    aws s3 cp "s3://$S3_BUCKET/$S3_FILE" "$LOCAL_FILE" || error_exit "Failed to download backup from S3"
    
    log "Backup downloaded to $LOCAL_FILE"
    echo "$LOCAL_FILE"
}

# Main execution
case "$1" in
    backup)
        create_backup
        ;;
    restore)
        if [[ "$2" == s3://* ]]; then
            # Extract the file name from the S3 URL
            S3_FILE=$(basename "$2")
            LOCAL_FILE=$(download_from_s3 "$S3_FILE")
            restore_backup "$LOCAL_FILE"
        else
            restore_backup "$2"
        fi
        ;;
    cleanup)
        cleanup_old_backups
        ;;
    list)
        list_backups
        ;;
    *)
        echo "Usage: $0 {backup|restore <file>|cleanup|list}"
        echo "  backup - Create a new backup"
        echo "  restore <file> - Restore from a backup file (local or s3://bucket/file)"
        echo "  cleanup - Remove backups older than $RETENTION_DAYS days"
        echo "  list - Show available backups"
        exit 1
        ;;
esac

exit 0
