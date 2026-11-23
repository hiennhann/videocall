FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/videocall

COPY backend/pyproject.toml ./
RUN python -c "import tomllib; print(*tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies'], sep='\n')" > /tmp/requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && useradd --system --user-group --no-create-home app \
    && mkdir -p /var/lib/videocall/avatars \
    && chown app:app /var/lib/videocall/avatars

FROM runtime AS sfu
RUN python -c "import tomllib; print(*tomllib.load(open('pyproject.toml', 'rb'))['project']['optional-dependencies']['sfu'], sep='\n')" > /tmp/requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
COPY backend/app/__init__.py app/
COPY backend/app/core/__init__.py backend/app/core/errors.py app/core/
COPY backend/app/sfu/ app/sfu/
COPY backend/app/schemas/__init__.py backend/app/schemas/rooms.py app/schemas/
USER app
EXPOSE 8080
CMD ["uvicorn", "app.sfu.worker:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-proxy-headers", "--no-access-log"]

FROM runtime AS app
COPY backend/app/ app/
COPY backend/alembic.ini ./
COPY backend/migrations/ migrations/
COPY client/ client/

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:create_asgi_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
