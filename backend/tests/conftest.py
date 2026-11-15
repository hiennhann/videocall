import pytest


@pytest.fixture
def app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "ENV": "test",
        "DATABASE_URL": "postgresql+asyncpg://videocall:test@127.0.0.1:1/videocall_test",
        "JWT_SECRET": "test-only-signing-key-with-at-least-32-bytes",
        "TURN_SECRET": "test-only-turn-secret",
        "TURN_URLS": "stun:turn.example.com:3478",
        "ALLOWED_ORIGINS": "http://localhost:8000",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
