#!/bin/sh
set -e

# ожидание Postgres
if [ -n "$DJANGO_DB_HOST" ]; then
  echo "Waiting for Postgres at $DJANGO_DB_HOST:$DJANGO_DB_PORT..."
  until nc -z "$DJANGO_DB_HOST" "$DJANGO_DB_PORT"; do
    sleep 0.5
  done
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py seed_witemebel --fresh --products 160
python manage.py create_superuser --email adm1n@witemebel.local --password s3cret \
# optional: healthcheck мигалка (создай /healthz view заранее)
# python manage.py check --deploy || true

# gunicorn
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3} \
  --threads ${GUNICORN_THREADS:-2} \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
