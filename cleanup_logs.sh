#!/bin/bash

# Regular log maintenance script for Auto_Jobs_Applier_AIHawk
# This script manages log files to prevent excessive disk usage

echo "Starting log maintenance at $(date)..."

# Navigate to the project directory
cd "$(dirname "$0")" || { echo "Failed to navigate to project directory"; exit 1; }

# Make sure the log directory exists
mkdir -p "./log"

# Activate the virtual environment
source "./virtual/bin/activate" || { 
    echo "Failed to activate virtual environment"; 
    exit 1; 
}

# Run log manager with rotation and cleanup
echo "Running log management..."
python log_manager.py --max-age 7 --max-size 1000 --max-cron-size 500 --rotate-cron --consolidate-cron

# Calculate and display log statistics
echo "Log statistics after maintenance:"
echo "Number of log files:"
find ./log -type f | wc -l

echo "Total size of log directory:"
du -sh ./log

echo "Largest log files:"
find ./log -type f -exec du -h {} \; | sort -hr | head -5

# Deactivate the virtual environment
deactivate

echo "Log maintenance completed successfully at $(date)."
