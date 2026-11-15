from asyncio import Lock
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import Setting
from app.schemas.settings import SettingsPatch, SettingsSchema
from app.services.audit_service import AuditActor, record_audit

DEFAULTS = SettingsSchema().model_dump()


class SettingsService:
    def __init__(self) -> None:
        self._cached: SettingsSchema | None = None
        self._lock = Lock()

    async def _load(self, db: AsyncSession) -> SettingsSchema:
        rows = await db.scalars(select(Setting))
        return SettingsSchema.model_validate({row.key: row.value for row in rows})

    async def get(self, db: AsyncSession) -> SettingsSchema:
        async with self._lock:
            if self._cached is None:
                self._cached = await self._load(db)
            return self._cached

    async def patch(
        self, db: AsyncSession, actor: AuditActor, patch: SettingsPatch
    ) -> SettingsSchema:
        unknown = patch.keys() - DEFAULTS.keys()
        if unknown:
            raise AuthError(
                ErrorCode.UNKNOWN_SETTING,
                fields={key: "Khóa không tồn tại." for key in sorted(unknown)},
            )

        async with self._lock:
            before = (await self._load(db)).model_dump()
            merged = before | {
                key: DEFAULTS[key] if value is None else value for key, value in patch.items()
            }
            try:
                settings = SettingsSchema.model_validate(merged)
            except ValidationError as exc:
                fields = {str(error["loc"][0]): "Giá trị không hợp lệ." for error in exc.errors()}
                raise AuthError(ErrorCode.VALIDATION_ERROR, fields=fields) from None

            changes = {}
            for key in patch:
                value = merged[key]
                if value == DEFAULTS[key]:
                    await db.execute(delete(Setting).where(Setting.key == key))
                else:
                    statement = insert(Setting).values(key=key, value=value, updated_by=actor.id)
                    await db.execute(
                        statement.on_conflict_do_update(
                            index_elements=[Setting.key],
                            set_={"value": value, "updated_by": actor.id, "updated_at": func.now()},
                        )
                    )
                if before[key] != value:
                    changes[key] = {"before": before[key], "after": value}

            record_audit(db, actor, "settings.update", "settings", detail=changes)
            try:
                await db.commit()
            finally:
                self._cached = None
            return settings


def settings_metadata(settings: SettingsSchema) -> dict[str, dict[str, Any]]:
    fields = SettingsSchema.model_json_schema()["properties"]
    names = {"boolean": "bool", "integer": "int", "string": "str"}
    output = {}
    for key, value in settings.model_dump().items():
        field = fields[key]
        entry = {
            "value": value,
            "default": DEFAULTS[key],
            "is_default": value == DEFAULTS[key],
            "type": "enum" if "enum" in field else names[field["type"]],
            "category": field["category"],
            "description": field["description"],
        }
        for source, target in (
            ("minimum", "min"),
            ("maximum", "max"),
            ("maxLength", "max_length"),
            ("enum", "options"),
        ):
            if source in field:
                entry[target] = field[source]
        output[key] = entry
    return output
