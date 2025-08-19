#!/bin/bash

# Subscription Cycle Management Cron Job
# This script should be run daily to process subscription cycles

# Configuration
PROJECT_DIR="/home/fanff/fanfan/django_ai_agent"
VENV_DIR="$PROJECT_DIR/venv"
LOG_DIR="$PROJECT_DIR/logs"
PYTHON="$VENV_DIR/bin/python"
MANAGE="$PROJECT_DIR/manage.py"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log file with date
LOG_FILE="$LOG_DIR/subscription_cron_$(date +%Y%m%d).log"

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log "Starting subscription cycle processing..."

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Activate virtual environment and run processing
source "$VENV_DIR/bin/activate" || {
    log "ERROR: Failed to activate virtual environment"
    exit 1
}

# Process subscription cycles
log "Processing subscription cycles..."
$PYTHON "$MANAGE" process_subscription_cycles >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    log "Subscription cycle processing completed successfully"
else
    log "ERROR: Subscription cycle processing failed"
    exit 1
fi

# Clean up old log files (keep only last 30 days)
find "$LOG_DIR" -name "subscription_cron_*.log" -mtime +30 -delete

log "Cron job completed"