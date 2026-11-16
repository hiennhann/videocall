"""Measure a local one-publisher aiortc relay with synthetic VP8 video."""

import argparse
import asyncio
import json
import logging
import math
import multiprocessing
import platform
import re
from fractions import Fraction
from importlib.metadata import version
from multiprocessing.connection import Connection
from statistics import median
from time import monotonic, monotonic_ns

import psutil
from aiortc import (
    RTCConfiguration,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import MediaStreamTrack
from av import VideoFrame

WIDTH, HEIGHT, FPS = 640, 360, 15
CELL_SIZE = 12
FRAME_CLOCK = 90_000
HOST_UDP = re.compile(r"^a=candidate:\S+ \d+ udp \d+ \S+ (\d+) typ host\b", re.I | re.M)


class VideoClock(VideoStreamTrack):
    def __init__(self) -> None:
        super().__init__()
        self.index = 0
        self.started = 0.0

    async def recv(self) -> VideoFrame:
        if self.index == 0:
            self.started = monotonic()
        await asyncio.sleep(max(0, self.started + self.index / FPS - monotonic()))
        stamp = monotonic_ns() // 1_000_000
        frame = VideoFrame(WIDTH, HEIGHT, "yuv420p")
        y, u, v = frame.planes
        pattern = bytes(32 + (column + self.index * 5) % 180 for column in range(WIDTH))
        data = bytearray(pattern.ljust(y.line_size, b"\x40") * HEIGHT)
        # Encode the timestamp on six rows of eight black/white tiles.
        for row, byte in enumerate(stamp.to_bytes(6, "big")):
            cells = b"".join(
                (b"\xeb" if byte & (1 << bit) else b"\x10") * CELL_SIZE for bit in range(7, -1, -1)
            )
            for line in range(row * CELL_SIZE, (row + 1) * CELL_SIZE):
                start = line * y.line_size
                data[start : start + len(cells)] = cells
        y.update(data)
        u.update(b"\x80" * u.buffer_size)
        v.update(b"\x80" * v.buffer_size)
        frame.pts = self.index * (FRAME_CLOCK // FPS)
        frame.time_base = Fraction(1, FRAME_CLOCK)
        self.index += 1
        return frame


def read_delay(frame: VideoFrame) -> float:
    plane = frame.reformat(format="yuv420p").planes[0]
    pixels = bytes(plane)
    stamp = 0
    for row in range(6):
        line = (row * CELL_SIZE + CELL_SIZE // 2) * plane.line_size
        for col in range(8):
            stamp = (stamp << 1) | (pixels[line + col * CELL_SIZE + CELL_SIZE // 2] > 128)
    return monotonic_ns() / 1_000_000 - stamp


async def serve(pipe: Connection) -> None:
    relay = MediaRelay()
    source: list[MediaStreamTrack] = []
    peers: list[RTCPeerConnection] = []
    try:
        while request := await asyncio.to_thread(pipe.recv):
            role, offer = request
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            peers.append(pc)
            if role == "publisher":
                pc.on("track", source.append)
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer, type="offer"))
            if role == "viewer":
                pc.addTrack(relay.subscribe(source[0], buffered=False))
            await pc.setLocalDescription(await pc.createAnswer())
            pipe.send(pc.localDescription.sdp)
    finally:
        await asyncio.gather(*(pc.close() for pc in peers))
        pipe.close()


def relay_process(pipe: Connection) -> None:
    asyncio.run(serve(pipe))


async def consume(
    track: MediaStreamTrack, ready: asyncio.Event, samples: list[float], measuring: asyncio.Event
) -> None:
    while True:
        frame = await track.recv()
        ready.set()
        if measuring.is_set():
            delay = read_delay(frame)
            if 0 < delay < 10_000:
                samples.append(delay)


async def measure(viewers: int, seconds: int) -> dict:
    context = multiprocessing.get_context("spawn")
    pipe, child_pipe = context.Pipe()
    child = context.Process(target=relay_process, args=(child_pipe,))
    child.start()
    child_pipe.close()
    process = psutil.Process(child.pid)
    peers: list[RTCPeerConnection] = []
    tasks: list[asyncio.Task] = []
    readiness: list[asyncio.Event] = []
    samples: list[list[float]] = []
    ports: set[int] = set()
    measuring = asyncio.Event()
    vp8 = [
        codec
        for codec in RTCRtpSender.getCapabilities("video").codecs
        if codec.mimeType == "video/VP8"
    ]

    async def connect(role: str) -> None:
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        peers.append(pc)
        if role == "publisher":
            transceiver = pc.addTransceiver(VideoClock(), direction="sendonly")
        else:
            recorded: list[float] = []
            ready = asyncio.Event()
            samples.append(recorded)
            readiness.append(ready)

            @pc.on("track")
            def accept(track: MediaStreamTrack) -> None:
                tasks.append(asyncio.create_task(consume(track, ready, recorded, measuring)))

            transceiver = pc.addTransceiver("video", direction="recvonly")
        transceiver.setCodecPreferences(vp8)
        await pc.setLocalDescription(await pc.createOffer())
        pipe.send((role, pc.localDescription.sdp))
        if not await asyncio.to_thread(pipe.poll, 12):
            raise TimeoutError("Relay answer timed out")
        answer = pipe.recv()
        ports.update(map(int, HOST_UDP.findall(answer)))
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))

    try:
        async with asyncio.timeout(30):
            await connect("publisher")
            for _ in range(viewers):
                await connect("viewer")
            await asyncio.gather(*(ready.wait() for ready in readiness))
        await asyncio.sleep(1)
        cpu_start = process.cpu_times()
        ram = process.memory_info().rss
        start = monotonic()
        measuring.set()
        for _ in range(seconds):
            await asyncio.sleep(1)
            ram = max(ram, process.memory_info().rss)
        measuring.clear()
        elapsed = monotonic() - start
        cpu_end = process.cpu_times()
        cpu_seconds = cpu_end.user + cpu_end.system - cpu_start.user - cpu_start.system
        delays = sorted(delay for received in samples for delay in received)
        fps = [len(received) / elapsed for received in samples]
        return {
            "viewers": viewers,
            "window_seconds": round(elapsed, 2),
            "viewers_with_frames": sum(bool(received) for received in samples),
            "min_fps": round(min(fps), 1),
            "median_fps": round(median(fps), 1),
            "p50_ms": round(median(delays), 1) if delays else None,
            "p95_ms": round(delays[math.ceil(len(delays) * 0.95) - 1], 1) if delays else None,
            "relay_cpu_pct_one_core": round(100 * cpu_seconds / elapsed, 1),
            "relay_rss_peak_mib": round(ram / 1024**2, 1),
            "udp_host_ports": sorted(ports),
        }
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*(pc.close() for pc in peers), return_exceptions=True)
        try:
            if child.is_alive():
                pipe.send(None)
        except (OSError, EOFError):
            pass
        finally:
            pipe.close()
        child.join(timeout=5)
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        child.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewers", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--seconds", type=int, default=12)
    args = parser.parse_args()
    if args.seconds < 1 or any(not 1 <= count <= 12 for count in args.viewers):
        parser.error("Use a positive duration and 1–12 viewers per local trial.")
    print(
        json.dumps(
            {
                "system": platform.system(),
                "logical_cpus": psutil.cpu_count(),
                "video": f"{WIDTH}x{HEIGHT} {FPS} fps VP8",
                "versions": {
                    package: version(package) for package in ("aiortc", "aioice", "av", "psutil")
                },
            }
        ),
        flush=True,
    )
    for viewers in args.viewers:
        print(json.dumps(await measure(viewers, args.seconds)), flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
