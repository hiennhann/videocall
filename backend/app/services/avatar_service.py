import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode
from app.models import User
from app.schemas.settings import SettingsSchema
from app.services.user_service import editable_user

MAX_PIXELS = 25_000_000
SIZES = (256, 64)


def process_avatar(data: bytes) -> tuple[str, dict[int, bytes]]:
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as source:
            if source.width * source.height > MAX_PIXELS:
                raise AuthError(ErrorCode.IMAGE_TOO_LARGE)
            source.load()
            ImageOps.exif_transpose(source, in_place=True)
            with ImageOps.fit(source, (256, 256), Image.Resampling.LANCZOS) as resized:
                # Chỉ sao chép pixel ở cỡ nhỏ, không sao chép metadata hay toàn bộ ảnh gốc.
                with Image.new("RGBA", (256, 256)) as clean:
                    clean.paste(resized)
                    output = {}
                    for size in SIZES:
                        with ImageOps.fit(clean, (size, size), Image.Resampling.LANCZOS) as image:
                            buffer = BytesIO()
                            image.save(buffer, format="WEBP", quality=85, method=4)
                            output[size] = buffer.getvalue()
        return sha256(b"".join(output.values())).hexdigest(), output
    except Image.DecompressionBombError:
        raise AuthError(ErrorCode.IMAGE_TOO_LARGE) from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise AuthError(ErrorCode.INVALID_IMAGE) from None


class AvatarService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._slots = asyncio.Semaphore(2)
        self._writes = asyncio.Lock()

    async def upload_policy(
        self, db: AsyncSession, user_id: UUID | None, policy: SettingsSchema
    ) -> None:
        await editable_user(db, user_id)
        if not policy.allow_avatar_upload:
            raise AuthError(ErrorCode.FEATURE_DISABLED)

    def path(self, user_id: UUID, key: str, size: int) -> Path:
        return self.root / str(user_id) / f"{key}-{size}.webp"

    def _write(self, user_id: UUID, key: str, images: dict[int, bytes]) -> None:
        directory = self.root / str(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        for size, data in images.items():
            temporary = None
            try:
                with NamedTemporaryFile(dir=directory, delete=False) as file:
                    temporary = Path(file.name)
                    file.write(data)
                temporary.replace(self.path(user_id, key, size))
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def _remove(self, user_id: UUID, key: str) -> None:
        for size in SIZES:
            self.path(user_id, key, size).unlink(missing_ok=True)

    async def replace(
        self, db: AsyncSession, user_id: UUID, data: bytes, policy: SettingsSchema
    ) -> User:
        await self.upload_policy(db, user_id, policy)
        if len(data) > policy.avatar_max_kb * 1024:
            raise AuthError(ErrorCode.IMAGE_TOO_LARGE)
        async with self._slots:
            key, images = await asyncio.to_thread(process_avatar, data)
        # App chạy một worker: giữ khóa cả qua commit và dọn tệp, tránh PUT/DELETE
        # đồng thời xóa bộ ảnh có cùng hash vừa được đặt lại làm ảnh hiện tại.
        async with self._writes:
            user = await editable_user(db, user_id, lock=True)
            old_key = user.avatar_key
            try:
                await asyncio.to_thread(self._write, user_id, key, images)
                user.avatar_key = key
                user.avatar_updated_at = datetime.now(UTC)
                await db.flush()
            except Exception:
                await db.rollback()
                if key != old_key:
                    await asyncio.to_thread(self._remove, user_id, key)
                raise
            # Commit trước khi xóa tệp cũ: DB luôn tham chiếu bộ ảnh đã ghi đủ.
            await db.commit()
            if old_key and old_key != key:
                await asyncio.to_thread(self._remove, user_id, old_key)
            return user

    async def delete(self, db: AsyncSession, user_id: UUID) -> None:
        async with self._writes:
            user = await editable_user(db, user_id, lock=True)
            old_key = user.avatar_key
            user.avatar_key = None
            user.avatar_updated_at = None
            await db.commit()
            if old_key:
                await asyncio.to_thread(self._remove, user_id, old_key)
