#!/bin/bash

# One-time cleanup script for log files
# This script will clean up existing log files and optimize the log structure

echo "Starting one-time log cleanup..."

# Navigate to the project directory
cd "$(dirname "$0")" || { echo "Failed to navigate to project directory"; exit 1; }

# Make sure the log directory exists
mkdir -p "./log"

# Activate the virtual environment
source "./virtual/bin/activate" || { 
    echo "Failed to activate virtual environment"; 
    exit 1; 
}

# Run log manager with more aggressive settings for initial cleanup
echo "Running initial cleanup with log manager..."
python log_manager.py --max-age 3 --max-size 500 --consolidate-cron

# Count and display log files before and after
echo "Log files before cleanup:"
find ./log -type f | wc -l

# Remove old app log archives (keep only the most recent ones)
echo "Removing old app log archives..."
find ./log -name "app.*.log.zip" -type f -mtime +3 -delete

# Count and display log files after cleanup
echo "Log files after cleanup:"
find ./log -type f | wc -l

# Calculate total size of log directory
echo "Total size of log directory:"
du -sh ./log

# Deactivate the virtual environment
deactivate

echo "Log cleanup completed successfully."
