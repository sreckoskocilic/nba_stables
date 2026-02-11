#!/bin/bash
# NBA Stables - Update Script
# Run this on the server to pull latest changes

set -e

cd /opt/nba_stables

echo "Pulling latest changes..."
git pull

echo "Rebuilding and restarting..."
docker-compose up -d --build

echo "Done! App updated."
docker-compose logs --tail=20
