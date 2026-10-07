#!/usr/bin/env bash
set -euo pipefail
python manage.py migrate --noinput
python manage.py inicializar_grupos
python manage.py bootstrap_direccion
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 2
