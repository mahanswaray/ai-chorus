#!/bin/bash

# Check if service name argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <service_name>"
  echo "Available services: chatgpt, claude, gemini"
  exit 1
fi

SERVICE_NAME="$1"
SOURCE_USER_DATA_DIR="/Users/swarajraibagi/Library/Application Support/Google/Chrome"
BACKUP_BASE_DIR="/Users/swarajraibagi/Documents/chrome_backups"
PROFILE_NAME="Profile 3" # Or adjust if needed per service

# --- Service Specific Configuration ---
URL=""
DEBUG_PORT=""

case "$SERVICE_NAME" in
  "chatgpt")
    URL="https://chat.openai.com"
    DEBUG_PORT=9222
    ;;
  "claude")
    URL="https://claude.ai/new"
    DEBUG_PORT=9223
    ;;
  "gemini")
    URL="https://gemini.google.com/u/1/app"
    DEBUG_PORT=9224
    ;;
  *)
    echo "Error: Unknown service name '$SERVICE_NAME'"
    echo "Available services: chatgpt, claude, gemini"
    exit 1
    ;;
esac

# --- Actions ---

# Define the specific backup directory for this service
SERVICE_BACKUP_DIR="$BACKUP_BASE_DIR/$SERVICE_NAME"

echo "Setting up $SERVICE_NAME..."
echo "Source User Data: $SOURCE_USER_DATA_DIR"
echo "Target Backup Dir: $SERVICE_BACKUP_DIR"
echo "URL: $URL"
echo "Debug Port: $DEBUG_PORT"

# Create the base backup directory if it doesn't exist
mkdir -p "$BACKUP_BASE_DIR"

# Remove existing backup for this service if it exists, then copy
echo "Copying profile data..."
rm -rf "$SERVICE_BACKUP_DIR"
cp -R "$SOURCE_USER_DATA_DIR" "$SERVICE_BACKUP_DIR"
# Using -R is generally preferred for copying directories over -r in bash

echo "Launching Chrome for $SERVICE_NAME..."
open -n -a "Google Chrome" --args \
  --user-data-dir="$SERVICE_BACKUP_DIR" \
  --profile-directory="$PROFILE_NAME" \
  --remote-debugging-port="$DEBUG_PORT" \
  "$URL"

echo "$SERVICE_NAME setup complete."


