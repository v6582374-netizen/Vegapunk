"""WebRTC preview of simulated robot cameras, for the existing GUI camera view.

The GUI's camera panel is a finished, unchangeable client: one fixed HTTPS port
per camera slot, a single ``POST /offer`` exchange, a ``recvonly`` video
transceiver and no ICE servers. This module is the server half of exactly that
contract and nothing more. It turns the newest frame of each slot into an
encoded video track, so a simulated run can be watched with the same panel that
watches a real G1.

The module's whole reason to exist is a threading constraint it refuses to
violate: MuJoCo may only render on the thread owning its GL context. Nothing
here imports MuJoCo, holds a simulator, or renders. Frames arrive only as
``uint8`` RGB arrays read from a ``FrameSource`` that the simulation thread
fills. Streaming can therefore run in a background event loop while the
simulation keeps the main thread.

Four refusals shape the rest:

- It never queues frames. A track publishes the latest array at its own
  cadence, so a slow encoder falls behind in time, never in memory, and the
  viewer always sees the present rather than a replayed backlog.
- It never blocks or raises when a slot has no frame yet. A viewer that
  connects before the simulation starts gets a placeholder frame, because a
  black panel that recovers is better than a connection that fails.
- It never trusts a published array's shape. A frame that does not match the
  slot's declared geometry is replaced by the placeholder rather than handed to
  an encoder that requires constant frame size.
- It never binds a public interface by default. The default host is loopback
  and LAN exposure has to be asked for explicitly.

Security, stated plainly: ``POST /offer`` has no authentication of any kind.
Anyone who can reach the port can watch the robot's cameras. The TLS
certificate is self-signed, so it proves nothing about the peer either; it
exists only because the GUI requires ``https``. Bind beyond loopback only on a
network you trust, and stop the server when you are done watching.
"""

from __future__ import annotations

import asyncio
import fractions
import ipaddress
import json
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol, Sequence

import numpy as np
from aiohttp import web
from aiortc import (
    MediaStreamTrack,
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.mediastreams import MediaStreamError
from av import VideoFrame
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

DEFAULT_CERT_DIR = Path(".scratch/embodied-sim-preview")
DEFAULT_PREVIEW_HOST = "127.0.0.1"
DEFAULT_PREVIEW_FPS = 30.0

PREVIEW_SECURITY_NOTICE = (
    "The camera preview is unauthenticated: anyone who can reach these ports "
    "can watch the robot's cameras. The TLS certificate is self-signed and "
    "identifies nobody. Keep the bind host on loopback unless the network is "
    "trusted, and stop the preview once finished."
)

_VIDEO_CLOCK_RATE = 90000
_VIDEO_TIME_BASE = fractions.Fraction(1, _VIDEO_CLOCK_RATE)
_PLACEHOLDER_LEVEL = 24
_CERTIFICATE_DAYS = 365
_CERTIFICATE_RENEW_MARGIN_DAYS = 7
_FILE_MODE = 0o600
_DIRECTORY_MODE = 0o700
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",
}
_CLOSING_STATES = frozenset({"failed", "closed"})


class FrameSource(Protocol):
    """The only seam to the simulation: the newest frame of one slot.

    ``latest`` must not block and must return ``None`` while a slot has
    produced nothing. Implementations are read concurrently from a streaming
    event loop while another thread publishes, so they carry the thread safety.
    """

    def latest(self, slot_id: str) -> Optional[np.ndarray]:
        """Return the newest ``uint8`` RGB frame, or ``None`` if there is none."""


class CameraSlotView(Protocol):
    """The subset of a camera slot declaration that streaming needs.

    Geometry and port are facts owned by the simulation module. Restating them
    as a protocol keeps this module free of that import, and free of the
    render-side fields it must never touch.
    """

    slot_id: str
    width: int
    height: int
    preview_port: int


@dataclass(frozen=True)
class CertificatePaths:
    """A reusable self-signed certificate and its private key on disk."""

    certificate: Path
    private_key: Path


@dataclass(frozen=True)
class PreviewEndpoint:
    """Where one slot is served, for printing to whoever wants to watch."""

    slot_id: str
    host: str
    port: int

    @property
    def url(self) -> str:
        """Return the origin the GUI derives its ``/offer`` request from."""
        return f"https://{self.host}:{self.port}/"


class SimulationFrameTrack(MediaStreamTrack):
    """A video track that samples one slot's newest frame at a fixed cadence.

    The track owns pacing, not the publisher. It emits frames on its own clock
    and reads whatever is currently available, which decouples the encoder's
    rate from the simulation's step rate in both directions: a fast simulation
    is downsampled, a stalled one repeats its last frame.
    """

    kind = "video"

    def __init__(
        self,
        frames: FrameSource,
        slot_id: str,
        width: int,
        height: int,
        fps: float = DEFAULT_PREVIEW_FPS,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("frame geometry must be positive")
        if fps <= 0:
            raise ValueError("fps must be positive")
        super().__init__()
        self._frames = frames
        self._slot_id = slot_id
        self._width = width
        self._height = height
        self._fps = float(fps)
        self._pts_step = max(1, int(round(_VIDEO_CLOCK_RATE / self._fps)))
        self._placeholder = np.full(
            (height, width, 3), _PLACEHOLDER_LEVEL, dtype=np.uint8
        )
        self._started_at: Optional[float] = None
        self._pts = 0

    @property
    def slot_id(self) -> str:
        """Return the slot this track samples."""
        return self._slot_id

    async def recv(self) -> VideoFrame:
        """Return the next encodable frame, waiting only to hold the cadence."""
        if self.readyState != "live":
            raise MediaStreamError
        pts = await self._next_pts()
        source = self._current_array()
        frame = VideoFrame.from_ndarray(source, format="rgb24").reformat(
            format="yuv420p"
        )
        frame.pts = pts
        frame.time_base = _VIDEO_TIME_BASE
        return frame

    async def _next_pts(self) -> int:
        """Advance the presentation clock, sleeping until its next tick."""
        if self._started_at is None:
            self._started_at = time.monotonic()
            self._pts = 0
            return self._pts
        self._pts += self._pts_step
        target = self._started_at + self._pts / _VIDEO_CLOCK_RATE
        delay = target - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        return self._pts

    def _current_array(self) -> np.ndarray:
        """Return the newest usable frame, or the placeholder in its absence."""
        frame = self._frames.latest(self._slot_id)
        if not self._is_usable(frame):
            return self._placeholder
        return np.ascontiguousarray(frame)

    def _is_usable(self, frame: Optional[np.ndarray]) -> bool:
        """Report whether a published frame matches the declared geometry."""
        return (
            isinstance(frame, np.ndarray)
            and frame.dtype == np.uint8
            and frame.shape == (self._height, self._width, 3)
        )


def ensure_self_signed_certificate(
    directory: Path = DEFAULT_CERT_DIR,
    extra_hosts: Sequence[str] = (),
) -> CertificatePaths:
    """Return a reusable self-signed certificate covering the given hosts.

    An existing pair is reused when it is still valid and already names every
    required host, so restarting the preview does not force the operator to
    trust a new certificate in the browser again. Anything else is regenerated.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = CertificatePaths(
        certificate=directory / "cert.pem",
        private_key=directory / "key.pem",
    )
    names = _subject_alternative_names(extra_hosts)
    if _certificate_is_reusable(paths, names):
        return paths
    _write_certificate(paths, names)
    return paths


def _subject_alternative_names(extra_hosts: Sequence[str]) -> tuple[x509.GeneralName, ...]:
    """Build the SAN entries, always including loopback, without duplicates."""
    candidates = ["localhost", "127.0.0.1", *extra_hosts]
    names: list[x509.GeneralName] = []
    seen: set[str] = set()
    for candidate in candidates:
        host = candidate.strip()
        if not host or host in seen:
            continue
        seen.add(host)
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    return tuple(names)


def _certificate_is_reusable(
    paths: CertificatePaths, names: Sequence[x509.GeneralName]
) -> bool:
    """Report whether the stored pair is still valid and names every host."""
    if not paths.certificate.is_file() or not paths.private_key.is_file():
        return False
    try:
        certificate = x509.load_pem_x509_certificate(paths.certificate.read_bytes())
    except ValueError:
        return False
    deadline = datetime.now(timezone.utc) + timedelta(
        days=_CERTIFICATE_RENEW_MARGIN_DAYS
    )
    if certificate.not_valid_after_utc <= deadline:
        return False
    try:
        extension = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
    except x509.ExtensionNotFound:
        return False
    present = set(extension.value)
    return present.issuperset(names)


def _write_certificate(
    paths: CertificatePaths, names: Sequence[x509.GeneralName]
) -> None:
    """Generate a fresh key and certificate, readable only by their owner."""
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "vegapunk-embodied-sim-preview")]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=_CERTIFICATE_DAYS))
        .add_extension(x509.SubjectAlternativeName(list(names)), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write_private_file(
        paths.private_key,
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    _write_private_file(
        paths.certificate, certificate.public_bytes(serialization.Encoding.PEM)
    )


def _write_private_file(path: Path, payload: bytes) -> None:
    """Write a secret file with owner-only permissions from the start."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(_DIRECTORY_MODE)
    path.touch(mode=_FILE_MODE, exist_ok=True)
    path.chmod(_FILE_MODE)
    path.write_bytes(payload)


class PreviewServer:
    """One HTTPS ``/offer`` endpoint per camera slot, sharing a frame source.

    The server holds no simulation state. It answers offers, adds a track per
    connection and forgets connections as they close, which is the entire
    lifecycle the GUI exercises.
    """

    def __init__(
        self,
        frames: FrameSource,
        slots: Sequence[CameraSlotView],
        host: str = DEFAULT_PREVIEW_HOST,
        fps: float = DEFAULT_PREVIEW_FPS,
        cert_dir: Path = DEFAULT_CERT_DIR,
    ) -> None:
        if not slots:
            raise ValueError("at least one camera slot is required")
        if fps <= 0:
            raise ValueError("fps must be positive")
        self._frames = frames
        self._slots = tuple(slots)
        self._host = host
        self._fps = float(fps)
        self._cert_dir = Path(cert_dir)
        self._runners: list[web.AppRunner] = []
        self._connections: set[RTCPeerConnection] = set()
        self._tracks: set[SimulationFrameTrack] = set()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def endpoints(self) -> tuple[PreviewEndpoint, ...]:
        """Return where each slot is served."""
        return tuple(
            PreviewEndpoint(slot.slot_id, self._host, slot.preview_port)
            for slot in self._slots
        )

    @property
    def connections(self) -> tuple[RTCPeerConnection, ...]:
        """Return the peer connections currently held, newest order unspecified."""
        return tuple(self._connections)

    def build_app(self, slot: CameraSlotView) -> web.Application:
        """Return the single-route application that serves one slot."""
        app = web.Application()
        app.router.add_post("/offer", self._offer_handler(slot))
        app.router.add_options("/offer", self._preflight_handler)
        return app

    async def start(self) -> None:
        """Serve every slot over TLS, failing if a port is already taken."""
        if self._runners:
            raise RuntimeError("preview server is already started")
        context = self._ssl_context()
        try:
            for slot in self._slots:
                runner = web.AppRunner(self.build_app(slot), access_log=None)
                await runner.setup()
                self._runners.append(runner)
                site = web.TCPSite(
                    runner, self._host, slot.preview_port, ssl_context=context
                )
                await site.start()
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Close every connection and release every port."""
        connections = tuple(self._connections)
        self._connections.clear()
        for connection in connections:
            await connection.close()
        for track in tuple(self._tracks):
            track.stop()
        self._tracks.clear()
        runners = tuple(self._runners)
        self._runners.clear()
        for runner in runners:
            await runner.cleanup()

    def run_in_thread(self) -> tuple[PreviewEndpoint, ...]:
        """Start the server on a background event loop and return its endpoints.

        This is the entry point for a simulation that must keep the main thread
        for rendering. It returns once every port is bound, so a caller that
        prints the endpoints is telling the truth about them.
        """
        if self._thread is not None:
            raise RuntimeError("preview server is already running in a thread")
        started = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self.start())
            except BaseException as error:
                failure.append(error)
                started.set()
                loop.close()
                self._loop = None
                return
            started.set()
            try:
                loop.run_forever()
            finally:
                loop.run_until_complete(self.stop())
                loop.close()

        thread = threading.Thread(
            target=run, name="embodied-sim-preview", daemon=True
        )
        self._thread = thread
        thread.start()
        started.wait()
        if failure:
            self._thread = None
            raise failure[0]
        return self.endpoints

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop the background loop and wait for its thread to finish."""
        thread = self._thread
        loop = self._loop
        self._thread = None
        if thread is None:
            return
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout)
        self._loop = None

    def _ssl_context(self) -> ssl.SSLContext:
        """Return a TLS context using the reusable self-signed certificate."""
        paths = ensure_self_signed_certificate(self._cert_dir, (self._host,))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(paths.certificate), str(paths.private_key))
        return context

    def _offer_handler(self, slot: CameraSlotView):
        """Bind one slot to an ``/offer`` request handler."""

        async def handler(request: web.Request) -> web.Response:
            return await self._handle_offer(slot, request)

        return handler

    async def _preflight_handler(self, request: web.Request) -> web.Response:
        """Answer the GUI's cross-origin preflight."""
        return web.Response(status=204, headers=_CORS_HEADERS)

    async def _handle_offer(
        self, slot: CameraSlotView, request: web.Request
    ) -> web.Response:
        """Answer one WebRTC offer with a live track for this slot."""
        offer = await self._read_offer(request)
        if offer is None:
            return web.json_response(
                {"error": "expected a JSON WebRTC offer"},
                status=400,
                headers=_CORS_HEADERS,
            )
        connection = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        track = SimulationFrameTrack(
            self._frames, slot.slot_id, slot.width, slot.height, self._fps
        )
        self._connections.add(connection)
        self._tracks.add(track)

        @connection.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            if connection.connectionState in _CLOSING_STATES:
                await self._forget(connection, track)

        connection.addTrack(track)
        try:
            await connection.setRemoteDescription(offer)
            answer = await connection.createAnswer()
            await connection.setLocalDescription(answer)
        except Exception:
            await self._forget(connection, track)
            raise
        return web.json_response(
            {
                "sdp": connection.localDescription.sdp,
                "type": connection.localDescription.type,
            },
            headers=_CORS_HEADERS,
        )

    async def _read_offer(
        self, request: web.Request
    ) -> Optional[RTCSessionDescription]:
        """Parse the request body into an offer, or report it unusable."""
        try:
            payload = json.loads(await request.text())
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        sdp = payload.get("sdp")
        kind = payload.get("type")
        if not isinstance(sdp, str) or not sdp or kind != "offer":
            return None
        return RTCSessionDescription(sdp=sdp, type=kind)

    async def _forget(
        self, connection: RTCPeerConnection, track: SimulationFrameTrack
    ) -> None:
        """Drop a finished connection and stop the track that fed it."""
        self._connections.discard(connection)
        if track in self._tracks:
            self._tracks.discard(track)
            track.stop()
        await connection.close()
