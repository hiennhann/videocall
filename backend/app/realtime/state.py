from asyncio import Event, Lock
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.schemas.rooms import MediaState

if TYPE_CHECKING:
    from app.models import CallParticipant


@dataclass(slots=True)
class Connection:
    peer_id: str
    user_id: str
    display_name: str
    role: str
    family_id: UUID | None
    ip: str
    room_code: str | None = None
    lock: Lock = field(default_factory=Lock)

    @property
    def is_guest(self) -> bool:
        return self.family_id is None


@dataclass(slots=True)
class Peer:
    connection: Connection
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    media: MediaState = field(
        default_factory=lambda: MediaState(audio=True, video=True, screen=False)
    )
    history: "CallParticipant | None" = None
    invite_id: UUID | None = None

    @property
    def id(self) -> str:
        return self.connection.peer_id

    @property
    def user_id(self) -> str:
        return self.connection.user_id

    def public(self) -> dict[str, Any]:
        return {
            "peer_id": self.id,
            "user_id": self.user_id,
            "display_name": self.connection.display_name,
            "is_guest": self.connection.is_guest,
            "media": self.media.model_dump(),
            "hand_raised": False,
        }


@dataclass(frozen=True, slots=True)
class HeldSeat:
    joined_at: datetime
    expires_at: float
    invite_id: UUID | None = None
    family_id: UUID | None = None


@dataclass(slots=True)
class RoomPresence:
    code: str
    owner_id: str | None
    empty_since: datetime | None
    peers: dict[str, Peer] = field(default_factory=dict)
    held_seats: dict[str, HeldSeat] = field(default_factory=dict)
    banned: set[str] = field(default_factory=set)
    preferred_host: str | None = None
    lock: Lock = field(default_factory=Lock)
    mode: str = "meeting"
    speaker_id: str | None = None
    published_by: str | None = None

    def live_speaker(self) -> str | None:
        if self.speaker_id in self.peers:
            return self.speaker_id
        return self.host_id()

    def expire_seats(self, now: float) -> None:
        for user_id, seat in list(self.held_seats.items()):
            if seat.expires_at <= now:
                del self.held_seats[user_id]

    def host(self) -> Peer | None:
        owner = next((peer for peer in self.peers.values() if peer.user_id == self.owner_id), None)
        if owner is not None:
            return owner
        preferred = next(
            (peer for peer in self.peers.values() if peer.user_id == self.preferred_host), None
        )
        if preferred is not None:
            return preferred
        return min(
            self.peers.values(),
            key=lambda peer: (peer.connection.is_guest, peer.joined_at),
            default=None,
        )

    def host_id(self) -> str | None:
        peer = self.host()
        return peer.id if peer else None


class RoomStateStore:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomPresence] = {}
        self._connections: dict[str, Connection] = {}
        self._users_online: dict[str, set[str]] = {}
        self.presence_changed = Event()

    def presence_counts(self) -> dict[str, int]:
        return {
            "rooms_with_participants": sum(bool(room.peers) for room in self._rooms.values()),
            "online_accounts": len(
                {
                    connection.user_id
                    for connection in self._connections.values()
                    if not connection.is_guest
                }
            ),
        }

    def _notify_presence(self) -> None:
        self.presence_changed.set()
        self.presence_changed = Event()

    def get_room(self, code: str) -> RoomPresence | None:
        return self._rooms.get(code)

    def list_rooms(self) -> tuple[RoomPresence, ...]:
        return tuple(self._rooms.values())

    def get_connection(self, peer_id: str) -> Connection | None:
        return self._connections.get(peer_id)

    def add_connection(self, connection: Connection) -> None:
        self._connections[connection.peer_id] = connection
        self._users_online.setdefault(connection.user_id, set()).add(connection.peer_id)
        self._notify_presence()

    def remove_connection(self, peer_id: str) -> None:
        connection = self._connections.pop(peer_id, None)
        if connection is not None:
            peers = self._users_online[connection.user_id]
            peers.discard(peer_id)
            if not peers:
                del self._users_online[connection.user_id]
            self._notify_presence()

    def connections_for(self, user_id: str) -> tuple[Connection, ...]:
        return tuple(self._connections[sid] for sid in self._users_online.get(user_id, ()))

    def connection_count(self) -> int:
        return len(self._connections)

    def ensure_room(
        self, code: str, owner_id: UUID | None, empty_since: datetime, mode: str = "meeting"
    ) -> RoomPresence:
        presence = self.get_room(code)
        if presence is None:
            presence = RoomPresence(
                code, str(owner_id) if owner_id else None, empty_since, mode=mode
            )
            self._rooms[code] = presence
        return presence

    def add_peer(self, room: RoomPresence, peer: Peer) -> None:
        room.peers[peer.id] = peer
        peer.connection.room_code = room.code
        room.empty_since = None
        self._notify_presence()

    def remove_peer(self, room: RoomPresence, peer: Peer) -> None:
        room.peers.pop(peer.id, None)
        peer.connection.room_code = None
        if not room.peers:
            room.empty_since = datetime.now(UTC)
        self._notify_presence()

    def remove_room(self, room: RoomPresence) -> None:
        for peer in list(room.peers.values()):
            self.remove_peer(room, peer)
        self._rooms.pop(room.code, None)
