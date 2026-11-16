import asyncio
import base64
import hmac
import os
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from ipaddress import IPv4Address
from time import monotonic, time
from typing import Annotated

from aiortc import (
    RTCBundlePolicy,
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import MediaStreamTrack
from aiortc.sdp import SessionDescription
from av import VideoFrame
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.schemas.rooms import PeerId, RoomCode
from app.sfu.control import Mode, control_token

WORKER_CONNECTION_LIMIT = 15


class LiveVideo(MediaStreamTrack):
    kind = "video"

    def __init__(self, source: MediaStreamTrack) -> None:
        super().__init__()
        self.source = source
        self.next_frame = 0.0

    async def recv(self) -> VideoFrame:
        while True:
            frame = await self.source.recv()
            now = monotonic()
            if now + 0.005 >= self.next_frame:
                self.next_frame = now + 1 / 15
                break
        scale = min(1, 640 / frame.width, 360 / frame.height)
        if scale < 1:
            width = max(2, int(frame.width * scale) // 2 * 2)
            height = max(2, int(frame.height * scale) // 2 * 2)
            frame = frame.reformat(width=width, height=height, format="yuv420p")
        return frame


class Offer(BaseModel):
    mode: Mode
    sdp: Annotated[str, Field(min_length=1, max_length=20 * 1024)]


@dataclass(slots=True)
class LivePeer:
    pc: RTCPeerConnection
    mode: Mode
    tracks: dict[str, MediaStreamTrack] = field(default_factory=dict)
    relay: MediaRelay = field(default_factory=MediaRelay)
    timeout: asyncio.TimerHandle | None = None


class Worker:
    def __init__(self, host: str, turn_url: str, secret: str) -> None:
        self.host = host
        self.turn_url = turn_url
        self.secret = secret
        self.rooms: dict[str, dict[str, LivePeer]] = {}
        self.lock = asyncio.Lock()

    def ice_servers(self, peer_id: str) -> list[RTCIceServer]:
        if not self.turn_url:
            return []
        username = f"{int(time()) + 86400}:sfu-{peer_id}"
        digest = hmac.digest(self.secret.encode(), username.encode(), "sha1")
        return [
            RTCIceServer(
                self.turn_url, username=username, credential=base64.b64encode(digest).decode()
            )
        ]

    async def remove(self, room: str, peer_id: str | None = None) -> None:
        peers = self.rooms.get(room, {})
        target = peers.get(peer_id) if peer_id else None
        if peer_id is None or (target is not None and target.mode == "publish"):
            removed = list(self.rooms.pop(room, {}).values())
        elif peer_id in peers:
            removed = [peers.pop(peer_id)]
        else:
            return
        for peer in removed:
            if peer.timeout is not None:
                peer.timeout.cancel()
            for track in peer.tracks.values():
                track.stop()
        await asyncio.gather(*(peer.pc.close() for peer in removed))

    async def remove_if_current(self, room: str, peer_id: str, peer: LivePeer) -> None:
        async with self.lock:
            if self.rooms.get(room, {}).get(peer_id) is peer:
                await self.remove(room, peer_id)

    async def negotiate(self, room: str, peer_id: str, offer: Offer) -> str:
        try:
            media = SessionDescription.parse(offer.sdp).media
        except (ValueError, AssertionError, IndexError):
            raise HTTPException(422) from None
        direction = "sendonly" if offer.mode == "publish" else "recvonly"
        if (
            {item.kind for item in media} != {"audio", "video"}
            or len(media) != 2
            or any(item.direction != direction for item in media)
        ):
            raise HTTPException(422)
        if offer.mode == "publish":
            await self.remove(room)
        else:
            await self.remove(room, peer_id)
        if sum(map(len, self.rooms.values())) >= WORKER_CONNECTION_LIMIT:
            raise HTTPException(503)
        peers = self.rooms.setdefault(room, {})
        publisher = next((peer for peer in peers.values() if peer.mode == "publish"), None)
        if offer.mode == "view" and (publisher is None or not publisher.tracks):
            if not peers:
                self.rooms.pop(room, None)
            raise HTTPException(409)

        pc = RTCPeerConnection(
            RTCConfiguration(
                iceServers=self.ice_servers(peer_id), bundlePolicy=RTCBundlePolicy.MAX_BUNDLE
            )
        )
        peer = LivePeer(pc, offer.mode)
        peers[peer_id] = peer

        @pc.on("connectionstatechange")
        async def state_changed() -> None:
            if pc.connectionState == "connected" and peer.timeout is not None:
                peer.timeout.cancel()
                peer.timeout = None
            if pc.connectionState in {"failed", "closed"}:
                await self.remove_if_current(room, peer_id, peer)

        if offer.mode == "publish":

            @pc.on("track")
            def receive(track: MediaStreamTrack) -> None:
                peer.tracks[track.kind] = LiveVideo(track) if track.kind == "video" else track

        peer.timeout = asyncio.get_running_loop().call_later(
            25, lambda: asyncio.create_task(self.remove_if_current(room, peer_id, peer))
        )
        try:
            await pc.setRemoteDescription(
                RTCSessionDescription(await self.local_offer(offer.sdp), "offer")
            )
            if publisher is not None:
                for track in publisher.tracks.values():
                    proxy = publisher.relay.subscribe(track, buffered=False)
                    peer.tracks[track.kind] = proxy
                    pc.addTrack(proxy)
            async with asyncio.timeout(7):
                await pc.setLocalDescription(await pc.createAnswer())
            return self.answer(pc.localDescription.sdp)
        except (ValueError, AssertionError, IndexError, TypeError):
            await self.remove(room, peer_id)
            raise HTTPException(422) from None
        except (TimeoutError, OSError):
            await self.remove(room, peer_id)
            raise HTTPException(503) from None

    def answer(self, sdp: str) -> str:
        if not self.host:
            return sdp
        lines = []
        for line in sdp.splitlines():
            if line.startswith("a=candidate:"):
                fields = line.split()
                if fields[7] == "host" and ":" not in fields[4]:
                    if self.turn_url.startswith("turn:coturn:"):
                        lines.append(line)
                    fields[4] = self.host
                    line = " ".join(fields)
            lines.append(line)
        return "\r\n".join(lines) + "\r\n"

    async def local_offer(self, sdp: str) -> str:
        if not self.host or not self.turn_url.startswith("turn:coturn:"):
            return sdp
        lines = sdp.splitlines()
        matches = []
        for index, line in enumerate(lines):
            if line.startswith("a=candidate:"):
                fields = line.split()
                if (
                    len(fields) >= 8
                    and fields[4] == self.host
                    and fields[7] == "relay"
                    and fields[5].isdigit()
                    and 49152 <= int(fields[5]) <= 49162
                ):
                    matches.append((index, fields))
        if not matches:
            return sdp
        addresses = await asyncio.get_running_loop().getaddrinfo(
            "coturn",
            None,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
        )
        # Coturn and the SFU share this bridge. Reach the local relay socket directly.
        for index, fields in matches:
            fields[4] = addresses[0][4][0]
            lines[index] = " ".join(fields)
        return "\r\n".join(lines) + "\r\n"


def create_app() -> FastAPI:
    secret = os.environ["TURN_SECRET"]
    host = os.getenv("SFU_HOST", "")
    if host:
        host = str(IPv4Address(host))
    worker = Worker(host, os.getenv("SFU_TURN_URL", ""), secret)
    token = f"Bearer {control_token(secret)}"

    async def authorize(authorization: Annotated[str, Header()] = "") -> None:
        if not hmac.compare_digest(authorization.encode(), token.encode()):
            raise HTTPException(403)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for room in list(worker.rooms):
            await worker.remove(room)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.put("/rooms/{room}/{peer_id}", dependencies=[Depends(authorize)])
    async def negotiate(room: RoomCode, peer_id: PeerId, offer: Offer) -> dict[str, str]:
        async with worker.lock:
            return {"type": "answer", "sdp": await worker.negotiate(room, peer_id, offer)}

    @app.delete("/rooms/{room}", dependencies=[Depends(authorize)])
    @app.delete("/rooms/{room}/{peer_id}", dependencies=[Depends(authorize)])
    async def remove(room: RoomCode, peer_id: PeerId | None = None) -> Response:
        async with worker.lock:
            await worker.remove(room, peer_id)
        return Response(status_code=204)

    return app
