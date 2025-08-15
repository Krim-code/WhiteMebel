# Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Системные либы для Pillow/psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libjpeg-dev netcat-openbsd \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
    
# Зависимости
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Код
COPY . /app/

# entrypoint
COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
CMD ["/entrypoint.sh"]
