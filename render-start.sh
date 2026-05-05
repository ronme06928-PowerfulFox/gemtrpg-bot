#!/usr/bin/env bash
set -o errexit

echo "Starting Gunicorn..."
gunicorn -c gunicorn_config.py app:app
