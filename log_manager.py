#!/usr/bin/env python3
"""
Log Manager

This script manages log files by:
1. Consolidating logs where possible
2. Implementing better rotation and cleanup policies
3. Removing old log files to save disk space
"""

import os
import sys
import shutil
import glob
import time
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import logging

# Configure basic logging for this script
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("LogManager")

# Constants
LOG_DIR = Path("./log")
MAX_LOG_AGE_DAYS = 7  # Keep logs for 7 days by default
MAX_TOTAL_LOG_SIZE_MB = 1000  # 1GB total log size limit
MAX_CRON_LOG_SIZE_KB = 500  # 500KB size limit for cron.log


def get_file_size_mb(file_path):
    """Get file size in megabytes."""
    try:
        return os.path.getsize(file_path) / (1024 * 1024)
    except (FileNotFoundError, OSError):
        return 0


def get_file_age_days(file_path):
    """Get file age in days."""
    try:
        mtime = os.path.getmtime(file_path)
        file_datetime = datetime.fromtimestamp(mtime)
        age = datetime.now() - file_datetime
        return age.days
    except (FileNotFoundError, OSError):
        return 0


def clean_old_logs(max_age_days=MAX_LOG_AGE_DAYS):
    """Remove log files older than max_age_days."""
    if not LOG_DIR.exists():
        logger.warning(f"Log directory {LOG_DIR} does not exist.")
        return

    logger.info(f"Cleaning log files older than {max_age_days} days...")
    
    # Get all log files
    log_files = list(LOG_DIR.glob("*.log")) + list(LOG_DIR.glob("*.log.zip"))
    
    # Sort by modification time (oldest first)
    log_files.sort(key=lambda x: os.path.getmtime(x))
    
    removed_count = 0
    removed_size_mb = 0
    
    for file_path in log_files:
        age_days = get_file_age_days(file_path)
        
        # Skip active log files
        if file_path.name in ["app.log", "chromedriver.log", "cron.log", "cron_runs.log"]:
            continue
            
        if age_days > max_age_days:
            size_mb = get_file_size_mb(file_path)
            try:
                os.remove(file_path)
                removed_count += 1
                removed_size_mb += size_mb
                logger.info(f"Removed {file_path.name} (Age: {age_days} days, Size: {size_mb:.2f} MB)")
            except OSError as e:
                logger.error(f"Failed to remove {file_path}: {e}")
    
    logger.info(f"Cleaned up {removed_count} old log files (Total: {removed_size_mb:.2f} MB)")


def rotate_cron_log(max_size_kb=MAX_CRON_LOG_SIZE_KB):
    """Rotate cron.log if it exceeds the maximum size."""
    cron_log_path = LOG_DIR / "cron.log"
    
    if not cron_log_path.exists():
        logger.warning(f"Cron log file {cron_log_path} does not exist.")
        return
    
    # Get file size in KB
    size_kb = os.path.getsize(cron_log_path) / 1024
    
    if size_kb > max_size_kb:
        logger.info(f"Rotating cron.log (Current size: {size_kb:.2f} KB, Limit: {max_size_kb} KB)")
        
        # Create timestamp for the rotated log filename
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        rotated_log_path = LOG_DIR / f"cron.{timestamp}.log"
        
        try:
            # Rename the current log file
            shutil.copy2(cron_log_path, rotated_log_path)
            
            # Create a new empty log file
            with open(cron_log_path, 'w') as f:
                f.write(f"# Log rotated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Previous log saved as {rotated_log_path.name}\n")
            
            logger.info(f"Successfully rotated cron.log to {rotated_log_path.name}")
            
            # Compress the rotated log file
            try:
                shutil.make_archive(str(rotated_log_path), 'zip', LOG_DIR, rotated_log_path.name)
                os.remove(rotated_log_path)
                logger.info(f"Compressed rotated log to {rotated_log_path.name}.zip")
            except Exception as e:
                logger.error(f"Failed to compress rotated log: {e}")
                
        except Exception as e:
            logger.error(f"Failed to rotate cron.log: {e}")
    else:
        logger.info(f"Cron log size is {size_kb:.2f} KB, below the limit of {max_size_kb} KB. No rotation needed.")


def enforce_total_size_limit(max_size_mb=MAX_TOTAL_LOG_SIZE_MB):
    """Ensure total log size stays under the specified limit."""
    if not LOG_DIR.exists():
        logger.warning(f"Log directory {LOG_DIR} does not exist.")
        return
        
    logger.info(f"Enforcing total log size limit of {max_size_mb} MB...")
    
    # Get all log files
    log_files = list(LOG_DIR.glob("*.log")) + list(LOG_DIR.glob("*.log.zip"))
    
    # Skip active log files (but include rotated cron logs)
    active_logs = ["app.log", "chromedriver.log", "cron_runs.log"]
    archive_files = [f for f in log_files if f.name not in active_logs and not f.name == "cron.log"]
    
    # Sort by modification time (oldest first)
    archive_files.sort(key=lambda x: os.path.getmtime(x))
    
    # Calculate total size
    total_size_mb = sum(get_file_size_mb(f) for f in log_files)
    
    removed_count = 0
    removed_size_mb = 0
    
    # Remove oldest archives until we're under the limit
    for file_path in archive_files:
        if total_size_mb <= max_size_mb:
            break
            
        size_mb = get_file_size_mb(file_path)
        try:
            os.remove(file_path)
            removed_count += 1
            removed_size_mb += size_mb
            total_size_mb -= size_mb
            logger.info(f"Removed {file_path.name} to stay under size limit (Size: {size_mb:.2f} MB)")
        except OSError as e:
            logger.error(f"Failed to remove {file_path}: {e}")
    
    logger.info(f"Removed {removed_count} log files to enforce size limit (Total: {removed_size_mb:.2f} MB)")
    logger.info(f"Current total log size: {total_size_mb:.2f} MB")


def consolidate_cron_logs():
    """Consolidate cron_runs.log into cron.log if needed."""
    cron_runs_path = LOG_DIR / "cron_runs.log"
    cron_log_path = LOG_DIR / "cron.log"
    
    if cron_runs_path.exists() and cron_runs_path.stat().st_size > 0:
        logger.info("Consolidating cron_runs.log into cron.log...")
        
        try:
            with open(cron_runs_path, 'r') as source:
                content = source.read()
                
            with open(cron_log_path, 'a') as target:
                target.write("\n# Consolidated from cron_runs.log\n")
                target.write(content)
                
            # Clear the cron_runs.log file
            with open(cron_runs_path, 'w') as f:
                pass
                
            logger.info("Successfully consolidated cron logs")
        except Exception as e:
            logger.error(f"Failed to consolidate cron logs: {e}")


def main():
    """Main function to manage logs."""
    parser = argparse.ArgumentParser(description="Manage log files for Auto_Jobs_Applier_AIHawk")
    parser.add_argument("--max-age", type=int, default=MAX_LOG_AGE_DAYS,
                        help=f"Maximum age of log files in days (default: {MAX_LOG_AGE_DAYS})")
    parser.add_argument("--max-size", type=int, default=MAX_TOTAL_LOG_SIZE_MB,
                        help=f"Maximum total size of log files in MB (default: {MAX_TOTAL_LOG_SIZE_MB})")
    parser.add_argument("--max-cron-size", type=int, default=MAX_CRON_LOG_SIZE_KB,
                        help=f"Maximum size of cron.log in KB (default: {MAX_CRON_LOG_SIZE_KB})")
    parser.add_argument("--consolidate-cron", action="store_true",
                        help="Consolidate cron_runs.log into cron.log")
    parser.add_argument("--rotate-cron", action="store_true",
                        help="Rotate cron.log if it exceeds the maximum size")
    
    args = parser.parse_args()
    
    # Create log directory if it doesn't exist
    os.makedirs(LOG_DIR, exist_ok=True)
    
    logger.info("Starting log management...")
    
    # Perform log management tasks
    if args.rotate_cron:
        rotate_cron_log(args.max_cron_size)
    
    clean_old_logs(args.max_age)
    enforce_total_size_limit(args.max_size)
    
    if args.consolidate_cron:
        consolidate_cron_logs()
    
    logger.info("Log management completed successfully")


if __name__ == "__main__":
    main()
