FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libharfbuzz0b \
    libfontconfig1 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/instance /app/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 10000
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 2 --timeout 120"]
