FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/videocall

COPY backend/pyproject.toml ./
COPY backend/app/ app/
RUN python -m pip install --no-cache-dir . \
    && useradd --system --user-group --no-create-home app \
    && mkdir -p /var/lib/videocall/avatars \
    && chown app:app /var/lib/videocall/avatars

COPY backend/alembic.ini ./
COPY backend/migrations/ migrations/
COPY client/ client/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:create_asgi_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]

FROM runtime AS sfu
USER root
RUN python -m pip install --no-cache-dir '.[sfu]'
USER app
CMD ["uvicorn", "app.sfu.worker:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-proxy-headers", "--no-access-log"]

FROM runtime AS app
