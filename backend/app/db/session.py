import asyncio
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from asyncpg import PostgresError
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def migration_heads() -> frozenset[str]:
    return frozenset(ScriptDirectory(MIGRATIONS_DIR).get_heads())


def current_revisions(connection: Connection) -> tuple[str, ...]:
    return MigrationContext.configure(connection).get_current_heads()


async def database_is_ready(engine: AsyncEngine, expected_heads: frozenset[str]) -> bool:
    try:
        async with asyncio.timeout(3), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revisions = await connection.run_sync(current_revisions)
    except (OSError, PostgresError, SQLAlchemyError):
        return False
    return frozenset(revisions) == expected_heads
