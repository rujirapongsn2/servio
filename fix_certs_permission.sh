#!/bin/bash

# Fix SSL Certificate Permissions for Nginx
# This script ensures that the unprivileged Nginx container can read the SSL certificates.

CERT_DIR="nginx/certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

echo "Checking SSL certificates in $CERT_DIR..."

if [ ! -d "$CERT_DIR" ]; then
    echo "ERROR: Directory $CERT_DIR does not exist."
    exit 1
fi

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "WARNING: Certificates not found. Running start.sh logic might be needed first."
    exit 1
fi

echo "Setting permissions (644) for $CERT_FILE and $KEY_FILE..."

# Set permissions to read-only for all (644) so Nginx user (UID 101) can read them
chmod 644 "$CERT_FILE" "$KEY_FILE"

if [ $? -eq 0 ]; then
    echo "Successfully updated certificate permissions."
    echo "You can now restart Nginx with: docker compose restart nginx"
else
    echo "Failed to update permissions. Try running with sudo."
    exit 1
fi

