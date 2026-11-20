import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import update

from app.models import User


@pytest.fixture(autouse=True)
def avatar_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("AVATAR_STORAGE_DIR", str(tmp_path))
    return tmp_path


@pytest_asyncio.fixture
async def headers(client: AsyncClient) -> dict[str, str]:
    credentials = {"email": f"e1-{uuid4().hex}@example.com", "password": "test-password-one"}
    assert (
        await client.post("auth/register", json={**credentials, "display_name": "Profile Tester"})
    ).status_code == 201
    response = await client.post("auth/login", json=credentials)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def picture(color: str = "red") -> bytes:
    output = BytesIO()
    with Image.new("RGB", (400, 200), color) as image:
        image.save(output, format="PNG")
    return output.getvalue()


async def upload(client: AsyncClient, headers: dict[str, str], color: str = "red"):
    # Tên và MIME cố ý sai: backend phải xác định định dạng từ nội dung.
    return await client.put(
        "me/avatar",
        headers=headers,
        files={"file": ("untrusted.svg", picture(color), "application/octet-stream")},
    )


async def test_partial_profile_update_preserves_omitted_values(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    original = (await client.get("me", headers=headers)).json()
    assert original["privacy"] == {"discoverable_by_email": True, "show_online_status": True}
    assert original["birth_date"] is None and original["avatar_url"] is None
    updated = await client.patch(
        "me",
        headers=headers,
        json={
            "display_name": "  New\u0000 Name  ",
            "birth_date": "2004-05-20",
            "privacy": {"discoverable_by_email": False},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_name"] == "New Name"
    assert updated.json()["privacy"] == {"discoverable_by_email": False, "show_online_status": True}
    partial = await client.patch(
        "me", headers=headers, json={"privacy": {"show_online_status": False}}
    )
    assert partial.json()["birth_date"] == "2004-05-20"
    assert partial.json()["privacy"]["discoverable_by_email"] is False
    assert partial.json()["email"] == original["email"]
    assert (await client.patch("me", headers=headers, json={})).json() == partial.json()
    cleared = await client.patch("me", headers=headers, json={"birth_date": None})
    assert cleared.json()["birth_date"] is None
    assert (await client.get("me", headers=headers)).json() == cleared.json()


@pytest.mark.parametrize(
    "patch,code",
    [
        (
            {"birth_date": (datetime.now(UTC).date() + timedelta(days=1)).isoformat()},
            "INVALID_BIRTH_DATE",
        ),
        ({"birth_date": "1899-12-31"}, "INVALID_BIRTH_DATE"),
        ({"birth_date": "1900-01-01"}, "INVALID_BIRTH_DATE"),
        ({"birth_date": "2024-02-30"}, "VALIDATION_ERROR"),
        ({"birth_date": 0}, "VALIDATION_ERROR"),
        ({"display_name": None}, "VALIDATION_ERROR"),
        ({"display_name": "a"}, "VALIDATION_ERROR"),
        ({"privacy": None}, "VALIDATION_ERROR"),
        ({"privacy": {"show_online_status": None}}, "VALIDATION_ERROR"),
        ({"privacy": {"discoverable_by_email": "false"}}, "VALIDATION_ERROR"),
        ({"email": "changed@example.com"}, "VALIDATION_ERROR"),
        ({"role": "admin"}, "VALIDATION_ERROR"),
    ],
)
async def test_invalid_profile_is_rejected_without_changes(
    client: AsyncClient, headers: dict[str, str], patch: dict, code: str
) -> None:
    before = (await client.get("me", headers=headers)).json()
    response = await client.patch("me", headers=headers, json=patch)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == code
    assert (await client.get("me", headers=headers)).json() == before


async def test_upload_replace_public_cache_and_delete(
    client: AsyncClient, headers: dict[str, str], avatar_directory: Path, app: FastAPI
) -> None:
    uploaded = await upload(client, headers)
    assert uploaded.status_code == 200, uploaded.text
    profile = uploaded.json()
    for key, size in (("avatar_url", 256), ("avatar_thumb_url", 64)):
        response = await client.get(f"http://test{profile[key]}")  # Ảnh nằm ngoài /api/v1.
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/webp"
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        with Image.open(BytesIO(response.content)) as image:
            assert image.size == (size, size)
    same = await upload(client, headers)
    assert same.json()["avatar_url"] == profile["avatar_url"]
    replaced = await upload(client, headers, "blue")
    assert replaced.status_code == 200
    assert replaced.json()["avatar_url"] != profile["avatar_url"]
    assert (await client.get(f"http://test{profile['avatar_url']}")).status_code == 404
    assert len(list(avatar_directory.rglob("*.webp"))) == 2
    async with app.state.session_factory() as db:
        user = await db.get(User, UUID(profile["id"]))
        assert user.avatar_updated_at is not None
    assert (await client.delete("me/avatar", headers=headers)).status_code == 204
    assert (await client.delete("me/avatar", headers=headers)).status_code == 204
    empty = (await client.get("me", headers=headers)).json()
    assert empty["avatar_url"] is None and empty["avatar_thumb_url"] is None
    assert (await client.get(f"http://test{replaced.json()['avatar_url']}")).status_code == 404
    assert not list(avatar_directory.rglob("*.webp"))


async def test_invalid_size_and_disabled_upload_preserve_existing_avatar(
    client: AsyncClient, headers: dict[str, str], app: FastAPI, avatar_directory: Path
) -> None:
    original = (await upload(client, headers)).json()
    for data, status, code in (
        (b"<svg><script/></svg>", 400, "INVALID_IMAGE"),
        (b"x" * (2048 * 1024 + 1), 413, "IMAGE_TOO_LARGE"),
        (b"x" * (2048 * 1024 + 20000), 413, "IMAGE_TOO_LARGE"),
    ):
        response = await client.put(
            "me/avatar", headers=headers, files={"file": ("a.png", data, "image/png")}
        )
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
    invalid = await client.put("me/avatar", headers=headers, files={"other": ("a.png", picture())})
    assert invalid.status_code == 400
    policy = await app.state.settings_service.get(None)
    app.state.settings_service._cached = policy.model_copy(update={"avatar_max_kb": 100})
    limited = await client.put(
        "me/avatar", headers=headers, files={"file": ("a.png", b"x" * 102401)}
    )
    assert limited.status_code == 413
    app.state.settings_service._cached = policy.model_copy(update={"allow_avatar_upload": False})
    disabled = await upload(client, headers)
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "FEATURE_DISABLED"
    public = (await client.get("config/public")).json()
    assert public["allow_avatar_upload"] is False and public["avatar_max_kb"] == 2048
    assert (await client.get("me", headers=headers)).json()["avatar_url"] == original["avatar_url"]
    assert len(list(avatar_directory.rglob("*.webp"))) == 2
    assert (await client.delete("me/avatar", headers=headers)).status_code == 204


async def test_guest_and_disabled_account_cannot_mutate_profile(
    client: AsyncClient, headers: dict[str, str], app: FastAPI
) -> None:
    assert (await upload(client, {})).status_code == 401
    guest = (await client.post("auth/guest", json={"display_name": "Guest"})).json()
    guest_headers = {"Authorization": f"Bearer {guest['access_token']}"}
    assert (await client.get("me", headers=guest_headers)).status_code == 200
    for response in (
        await upload(client, guest_headers),
        await client.delete("me/avatar", headers=guest_headers),
        await client.patch("me", headers=guest_headers, json={"birth_date": "2004-01-01"}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "GUEST_NOT_ALLOWED"
    user = (await client.get("me", headers=headers)).json()
    async with app.state.session_factory() as db:
        await db.execute(update(User).where(User.id == UUID(user["id"])).values(is_active=False))
        await db.commit()
    response = await upload(client, headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


async def test_concurrent_avatar_mutations_keep_only_current_files(
    client: AsyncClient, headers: dict[str, str], avatar_directory: Path
) -> None:
    results = await asyncio.gather(
        upload(client, headers, "red"),
        upload(client, headers, "blue"),
        client.delete("me/avatar", headers=headers),
        upload(client, headers, "red"),
    )
    assert all(response.status_code in (200, 204) for response in results)
    profile = (await client.get("me", headers=headers)).json()
    files = {path.name for path in avatar_directory.rglob("*.webp")}
    assert files == (
        {profile[key].rsplit("/", 1)[1] for key in ("avatar_url", "avatar_thumb_url")}
        if profile["avatar_url"]
        else set()
    )


async def test_disk_failure_rolls_back_and_removes_partial_new_files(
    client: AsyncClient,
    headers: dict[str, str],
    app: FastAPI,
    avatar_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = (await upload(client, headers)).json()
    service = app.state.avatar_service
    write = service._write

    def failing_write(*args):
        write(*args)
        raise OSError("simulated disk failure")

    monkeypatch.setattr(service, "_write", failing_write)
    with pytest.raises(OSError, match="simulated disk failure"):
        await upload(client, headers, "blue")
    assert (await client.get("me", headers=headers)).json()["avatar_url"] == original["avatar_url"]
    assert (await client.get(f"http://test{original['avatar_url']}")).status_code == 200
    assert len(list(avatar_directory.rglob("*.webp"))) == 2
