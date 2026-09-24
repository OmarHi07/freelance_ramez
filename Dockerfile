# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    PORT=8000

WORKDIR /app

# gettext is only needed to rebuild translation files (makemessages/compilemessages).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect static files at build time. These placeholder values exist only for this
# build step; real values are provided by the hosting platform at runtime.
RUN DJANGO_SECRET_KEY=build-only-placeholder-not-used-at-runtime-0123456789abcdef \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/media \
    && chown -R app:app /app/media
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz/' % os.environ.get('PORT', '8000'), timeout=4)"

# Run database migrations as a separate release/pre-deploy step:  python manage.py migrate --noinput
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
