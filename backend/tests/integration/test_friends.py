import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from limits import parse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.models import FriendRequest, Friendship, User
from app.services.friend_service import canonical_pair


@dataclass
class Actor:
    id: UUID
    email: str
    headers: dict[str, str]


async def actor(client: AsyncClient, app: FastAPI, name: str = "Friend Tester") -> Actor:
    email = f"friends-{uuid4().hex}@example.com"
    async with app.state.session_factory() as db:
        user = await app.state.auth_service.register(db, email, name, "test-password-one")
        user_id = user.id
    response = await client.post(
        "auth/login", json={"email": email, "password": "test-password-one"}
    )
    assert response.status_code == 200, response.text
    return Actor(user_id, email, {"Authorization": f"Bearer {response.json()['access_token']}"})


def error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


async def send(client: AsyncClient, first: Actor, second: Actor) -> Response:
    return await client.post(
        "friends/requests", headers=first.headers, json={"to_user_id": str(second.id)}
    )


async def befriend(client: AsyncClient, first: Actor, second: Actor) -> None:
    request = await send(client, first, second)
    assert request.status_code == 201, request.text
    response = await client.post(
        f"friends/requests/{request.json()['id']}/accept", headers=second.headers
    )
    assert response.status_code == 200, response.text


async def test_exact_search_does_not_expose_private_fields_or_hidden_accounts(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app, "Private Profile")
    await client.patch("me", headers=second.headers, json={"birth_date": "2004-05-20"})
    found = await client.get(
        "users/search", headers=first.headers, params={"email": second.email.upper()}
    )
    assert found.status_code == 200, found.text
    assert set(found.json()["items"][0]) == {"id", "display_name", "avatar_url", "relationship"}
    assert second.email not in found.text and "2004-05-20" not in found.text
    assert found.json()["items"][0]["relationship"] == "none"
    unknown = await client.get(
        "users/search", headers=first.headers, params={"email": "absent@example.com"}
    )
    assert unknown.json() == {"items": []}
    await client.patch(
        "me", headers=second.headers, json={"privacy": {"discoverable_by_email": False}}
    )
    hidden = await client.get("users/search", headers=first.headers, params={"email": second.email})
    assert hidden.status_code == unknown.status_code and hidden.content == unknown.content
    assert (
        await client.get("users/search", headers=first.headers, params={"email": first.email})
    ).json() == {"items": []}
    error(
        await client.get("users/search", headers=first.headers, params={"email": "friends-"}),
        422,
        "VALIDATION_ERROR",
    )
    await client.patch(
        "me", headers=second.headers, json={"privacy": {"discoverable_by_email": True}}
    )
    async with app.state.session_factory() as db:
        await db.execute(update(User).where(User.id == second.id).values(is_active=False))
        await db.commit()
    assert (
        await client.get("users/search", headers=first.headers, params={"email": second.email})
    ).json() == {"items": []}
    error(await send(client, first, second), 404, "USER_NOT_FOUND")
    error(await send(client, first, first), 404, "USER_NOT_FOUND")


async def test_friend_lifecycle_and_request_ownership(client: AsyncClient, app: FastAPI) -> None:
    first, second, outsider = (
        await actor(client, app),
        await actor(client, app),
        await actor(client, app),
    )
    request = await send(client, first, second)
    assert request.status_code == 201
    request_id = request.json()["id"]
    assert request.json()["from"]["id"] == str(first.id)
    assert (await client.get("friends/requests", headers=second.headers)).json()["items"][0][
        "id"
    ] == request_id
    for caller in (first, outsider):
        for action in ("accept", "decline"):
            error(
                await client.post(
                    f"friends/requests/{request_id}/{action}", headers=caller.headers
                ),
                404,
                "REQUEST_NOT_FOUND",
            )
    error(
        await client.delete(f"friends/requests/{request_id}", headers=second.headers),
        404,
        "REQUEST_NOT_FOUND",
    )
    accepted = await client.post(f"friends/requests/{request_id}/accept", headers=second.headers)
    assert accepted.status_code == 200
    assert accepted.json()["id"] == str(first.id) and accepted.json()["is_online"] is False
    for caller in (first, second):
        assert (await client.get("friends", headers=caller.headers)).json()["total"] == 1
        for direction in ("incoming", "outgoing"):
            assert (
                await client.get(
                    "friends/requests", headers=caller.headers, params={"direction": direction}
                )
            ).json() == {"items": []}
    error(await send(client, first, second), 409, "ALREADY_FRIENDS")
    assert (await client.delete(f"friends/{second.id}", headers=first.headers)).status_code == 204
    assert (await client.get("friends", headers=second.headers)).json()["total"] == 0
    error(await client.delete(f"friends/{second.id}", headers=first.headers), 404, "NOT_FRIENDS")


async def test_silent_decline_cooldown_and_cancel_cannot_bypass_it(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app)
    request = (await send(client, first, second)).json()
    before = (
        await client.get(
            "friends/requests", headers=first.headers, params={"direction": "outgoing"}
        )
    ).json()
    assert (
        await client.post(f"friends/requests/{request['id']}/decline", headers=second.headers)
    ).status_code == 204
    assert (await client.get("friends/requests", headers=second.headers)).json() == {"items": []}
    assert (
        await client.get(
            "friends/requests", headers=first.headers, params={"direction": "outgoing"}
        )
    ).json() == before
    found = await client.get("users/search", headers=first.headers, params={"email": second.email})
    assert found.json()["items"][0]["relationship"] == "request_sent"
    limited = await send(client, first, second)
    error(limited, 429, "REQUEST_COOLDOWN")
    assert 0 < int(limited.headers["retry-after"]) <= 86400
    assert (
        await client.delete(f"friends/requests/{request['id']}", headers=first.headers)
    ).status_code == 204
    error(await send(client, first, second), 429, "REQUEST_COOLDOWN")
    assert (
        await client.get("users/search", headers=first.headers, params={"email": second.email})
    ).json()["items"][0]["relationship"] == "none"
    async with app.state.session_factory() as db:
        await db.execute(
            update(FriendRequest)
            .where(FriendRequest.id == UUID(request["id"]))
            .values(responded_at=datetime.now(UTC) - timedelta(hours=25))
        )
        await db.commit()
    resent = await send(client, first, second)
    assert resent.status_code == 201
    outgoing = (
        await client.get(
            "friends/requests", headers=first.headers, params={"direction": "outgoing"}
        )
    ).json()["items"]
    assert len(outgoing) == 1 and outgoing[0]["id"] == resent.json()["id"]


async def test_expired_requests_cannot_be_accepted_and_allow_new_request(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app)
    request_id = UUID((await send(client, first, second)).json()["id"])
    async with app.state.session_factory() as db:
        await db.execute(
            update(FriendRequest)
            .where(FriendRequest.id == request_id)
            .values(created_at=datetime.now(UTC) - timedelta(days=31))
        )
        await db.commit()
    error(
        await client.post(f"friends/requests/{request_id}/accept", headers=second.headers),
        404,
        "REQUEST_NOT_FOUND",
    )
    for caller, direction in ((first, "outgoing"), (second, "incoming")):
        assert (
            await client.get(
                "friends/requests", headers=caller.headers, params={"direction": direction}
            )
        ).json() == {"items": []}
    async with app.state.session_factory() as db:
        await app.state.friend_service.expire_requests(db)
        assert (await db.get(FriendRequest, request_id)).status == "expired"
    assert (await send(client, first, second)).status_code == 201


async def test_crossed_and_duplicate_requests_are_serialized(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second, third = (
        await actor(client, app),
        await actor(client, app),
        await actor(client, app),
    )
    duplicates = await asyncio.gather(send(client, first, second), send(client, first, second))
    assert sorted(response.status_code for response in duplicates) == [201, 409]
    crossed = await asyncio.gather(send(client, first, third), send(client, third, first))
    assert all(response.status_code == 201 for response in crossed)
    assert {response.json()["status"] for response in crossed} == {"pending", "accepted"}
    async with app.state.session_factory() as db:
        friendships = list(
            await db.scalars(
                select(Friendship).where(
                    Friendship.user_a_id == canonical_pair(first.id, third.id)[0],
                    Friendship.user_b_id == canonical_pair(first.id, third.id)[1],
                )
            )
        )
        assert len(friendships) == 1 and friendships[0].user_a_id < friendships[0].user_b_id


async def test_counter_request_after_decline_clears_old_masked_request(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app)
    request_id = (await send(client, first, second)).json()["id"]
    await client.post(f"friends/requests/{request_id}/decline", headers=second.headers)
    assert (await send(client, second, first)).status_code == 201
    accepted = await send(client, first, second)
    assert accepted.status_code == 201 and accepted.json()["status"] == "accepted"
    await client.delete(f"friends/{second.id}", headers=first.headers)
    assert (
        await client.get(
            "friends/requests", headers=first.headers, params={"direction": "outgoing"}
        )
    ).json() == {"items": []}


async def test_block_removes_friendships_requests_and_hides_both_directions(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second, third = (
        await actor(client, app),
        await actor(client, app),
        await actor(client, app),
    )
    await befriend(client, first, second)
    pending = (await send(client, third, first)).json()["id"]
    for target in (second, third):
        assert (
            await client.post("blocks", headers=first.headers, json={"user_id": str(target.id)})
        ).status_code == 201
        for caller, other in ((first, target), (target, first)):
            assert (
                await client.get(
                    "users/search", headers=caller.headers, params={"email": other.email}
                )
            ).json() == {"items": []}
            error(await send(client, caller, other), 404, "USER_NOT_FOUND")
    assert (
        await client.post("blocks", headers=first.headers, json={"user_id": str(second.id)})
    ).status_code == 201
    assert (await client.get("friends", headers=second.headers)).json()["total"] == 0
    assert (
        await client.get(
            "friends/requests", headers=third.headers, params={"direction": "outgoing"}
        )
    ).json() == {"items": []}
    error(
        await client.post(f"friends/requests/{pending}/accept", headers=first.headers),
        404,
        "REQUEST_NOT_FOUND",
    )
    blocks = (await client.get("blocks", headers=first.headers)).json()["items"]
    assert {item["user"]["id"] for item in blocks} == {str(second.id), str(third.id)}
    assert all("email" not in item["user"] for item in blocks)
    for target in (second, third):
        assert (
            await client.delete(f"blocks/{target.id}", headers=first.headers)
        ).status_code == 204
    assert (await client.get("friends", headers=first.headers)).json()["total"] == 0
    assert (await send(client, third, first)).status_code == 201


async def test_feature_flags_and_guest_permissions(client: AsyncClient, app: FastAPI) -> None:
    first, second = await actor(client, app), await actor(client, app)
    guest = (await client.post("auth/guest", json={"display_name": "Visitor"})).json()
    guest_headers = {"Authorization": f"Bearer {guest['access_token']}"}
    for path in ("friends", "friends/requests", "blocks", f"users/search?email={second.email}"):
        error(await client.get(path, headers=guest_headers), 403, "GUEST_NOT_ALLOWED")
    error(
        await client.post(
            "friends/requests", headers=guest_headers, json={"to_user_id": str(first.id)}
        ),
        403,
        "GUEST_NOT_ALLOWED",
    )
    error(await client.get("friends"), 401, "UNAUTHENTICATED")
    policy = await app.state.settings_service.get(None)
    app.state.settings_service._cached = policy.model_copy(update={"friends_enabled": False})
    error(await send(client, first, second), 403, "FEATURE_DISABLED")
    error(await client.get("friends", headers=first.headers), 403, "FEATURE_DISABLED")
    assert (
        await client.post("blocks", headers=first.headers, json={"user_id": str(second.id)})
    ).status_code == 201
    assert (await client.delete(f"blocks/{second.id}", headers=first.headers)).status_code == 204
    app.state.settings_service._cached = policy.model_copy(update={"friend_search_enabled": False})
    error(
        await client.get("users/search", headers=first.headers, params={"email": second.email}),
        403,
        "FEATURE_DISABLED",
    )
    assert (await send(client, first, second)).status_code == 201


async def seed_users(app: FastAPI, count: int) -> list[User]:
    users = [
        User(
            id=uuid4(),
            email=f"seed-{uuid4().hex}@example.com",
            display_name=f"Seed {index:02}",
            password_hash=app.state.auth_service._dummy_password_hash,
        )
        for index in range(count)
    ]
    async with app.state.session_factory() as db:
        db.add_all(users)
        await db.commit()
    return users


async def test_friend_limit_is_enforced_during_concurrent_acceptance(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second, third = (
        await actor(client, app),
        await actor(client, app),
        await actor(client, app),
    )
    others = await seed_users(app, 9)
    async with app.state.session_factory() as db:
        db.add_all(
            [
                Friendship(
                    user_a_id=canonical_pair(first.id, user.id)[0],
                    user_b_id=canonical_pair(first.id, user.id)[1],
                )
                for user in others
            ]
        )
        await db.commit()
    policy = await app.state.settings_service.get(None)
    assert policy.max_friends_per_user == 200
    app.state.settings_service._cached = policy.model_copy(update={"max_friends_per_user": 10})
    requests = [(await send(client, user, first)).json()["id"] for user in (second, third)]
    accepted = await asyncio.gather(
        *[
            client.post(f"friends/requests/{request_id}/accept", headers=first.headers)
            for request_id in requests
        ]
    )
    assert sorted(response.status_code for response in accepted) == [200, 409]
    error(
        next(response for response in accepted if response.status_code == 409),
        409,
        "FRIEND_LIMIT_REACHED",
    )
    assert (await client.get("friends", headers=first.headers)).json()["total"] == 10


async def test_masked_declines_count_towards_outgoing_limit(
    client: AsyncClient, app: FastAPI
) -> None:
    first, target = await actor(client, app), await actor(client, app)
    others = await seed_users(app, 5)
    async with app.state.session_factory() as db:
        rows = [
            FriendRequest(
                from_user_id=first.id,
                to_user_id=user.id,
                status="declined" if index == 0 else "pending",
                responded_at=datetime.now(UTC) if index == 0 else None,
            )
            for index, user in enumerate(others)
        ]
        db.add_all(rows)
        await db.commit()
    policy = await app.state.settings_service.get(None)
    app.state.settings_service._cached = policy.model_copy(
        update={"max_pending_friend_requests": 5}
    )
    error(await send(client, first, target), 409, "FRIEND_LIMIT_REACHED")
    assert (
        await client.delete(f"friends/requests/{rows[1].id}", headers=first.headers)
    ).status_code == 204
    assert (await send(client, first, target)).status_code == 201


async def test_search_rate_limits_apply_per_user_per_day_and_per_ip(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second, third = (
        await actor(client, app),
        await actor(client, app),
        await actor(client, app),
    )
    for _ in range(20):
        assert (
            await client.get(
                "users/search", headers=first.headers, params={"email": "absent@example.com"}
            )
        ).status_code == 200
    limited = await client.get(
        "users/search", headers=first.headers, params={"email": "absent@example.com"}
    )
    error(limited, 429, "RATE_LIMITED")
    assert int(limited.headers["retry-after"]) > 0
    for _ in range(200):
        app.state.limiter.limiter.hit(parse("200/day"), "friend_search_user", str(second.id))
    error(
        await client.get(
            "users/search", headers=second.headers, params={"email": "absent@example.com"}
        ),
        429,
        "RATE_LIMITED",
    )
    for _ in range(60):
        app.state.limiter.limiter.hit(parse("60/minute"), "friend_search_ip", "127.0.0.1")
    error(
        await client.get(
            "users/search", headers=third.headers, params={"email": "absent@example.com"}
        ),
        429,
        "RATE_LIMITED",
    )


async def test_database_rejects_reversed_friendship_and_self_request(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app)
    low, high = canonical_pair(first.id, second.id)
    for row in (
        Friendship(user_a_id=high, user_b_id=low),
        FriendRequest(from_user_id=first.id, to_user_id=first.id),
    ):
        async with app.state.session_factory() as db:
            db.add(row)
            with pytest.raises(IntegrityError):
                await db.flush()


async def test_concurrent_block_and_request_leave_no_pending_relation(
    client: AsyncClient, app: FastAPI
) -> None:
    first, second = await actor(client, app), await actor(client, app)
    sent, blocked = await asyncio.gather(
        send(client, first, second),
        client.post("blocks", headers=second.headers, json={"user_id": str(first.id)}),
    )
    assert sent.status_code in (201, 404) and blocked.status_code == 201
    async with app.state.session_factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(FriendRequest)
                .where(
                    FriendRequest.from_user_id == first.id,
                    FriendRequest.to_user_id == second.id,
                    FriendRequest.status == "pending",
                )
            )
            == 0
        )
