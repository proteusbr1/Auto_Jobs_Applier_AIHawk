#!/bin/bash

# Auto_Jobs_Applier_AIHawk Cron Job Script
PROJECT_DIR="/home/proteusbr/Auto_Jobs_Applier_AIHawk"

# Make sure the log directory exists
mkdir -p "$PROJECT_DIR/log"
LOG_FILE="$PROJECT_DIR/log/cron.log"

# Redirect all output to cron.log
exec >> "$LOG_FILE" 2>&1

# Insert a timestamp
echo "----- $(date) -----"

# Navigate to the project directory
cd "$PROJECT_DIR" || { echo "Failed to navigate to project directory"; exit 1; }

# Check if the process is already running
if pgrep -f "python main.py" > /dev/null; then
    echo "Process already running. Skipping this run."
    exit 0
else
    echo "Starting new process."
    
    # Activate the virtual environment
    source "$PROJECT_DIR/.venv/bin/activate" || {
        echo "Failed to activate virtual environment";
        exit 1;
    }
    
    # Run the Python script
    python main.py || { 
        echo "Python main script failed"; 
        exit 1; 
    }
    
    # Run log management script to clean up and optimize logs
    echo "Running log management..."
    python log_manager.py --consolidate-cron --rotate-cron --max-cron-size 500 || {
        echo "Log management failed, but continuing execution";
    }
    
    # Deactivate the virtual environment
    deactivate
    
    echo "Script executed successfully."
fi