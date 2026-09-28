#!/usr/bin/env bash
# Render build command: installs dependencies and collects static files.
# Deliberately does NOT run migrate here - Render's build step runs on a
# separate, disk-less instance, so it can't reach the persistent disk where
# db.sqlite3 lives. Migrations run instead from the start command, below.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
