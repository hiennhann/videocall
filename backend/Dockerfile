FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/videocall

COPY backend/pyproject.toml ./
COPY backend/app/ app/
RUN python -m pip install --no-cache-dir . \
    && useradd --system --user-group --no-create-home app

COPY backend/alembic.ini ./
COPY backend/migrations/ migrations/
COPY client/ client/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:create_asgi_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
