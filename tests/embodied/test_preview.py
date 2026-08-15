from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import ssl
import stat
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEPENDENCIES = ("numpy", "aiohttp", "aiortc", "av", "cryptography")
_MISSING = tuple(
    name for name in _DEPENDENCIES if importlib.util.find_spec(name) is None
)
_HAS_DEPENDENCIES = not _MISSING
_SKIP_REASON = f"missing preview dependencies: {', '.join(_MISSING)}"

if _HAS_DEPENDENCIES:
    import numpy as np
    from aiohttp import ClientSession, TCPConnector
    from aiortc import RTCPeerConnection, RTCSessionDescription

    from vegapunk.embodied.preview import (
        PreviewServer,
        SimulationFrameTrack,
        ensure_self_signed_certificate,
    )


@dataclass(frozen=True)
class FakeCameraSlot:
    """A camera slot declaration standing in for the simulation module's."""

    slot_id: str
    width: int
    height: int
    preview_port: int


class FakeFrameBus:
    """The newest frame per slot, as the simulation thread would publish it."""

    def __init__(self) -> None:
        self._frames: dict[str, "np.ndarray"] = {}
        self.read_count = 0

    def publish(self, slot_id: str, frame: "np.ndarray") -> None:
        self._frames[slot_id] = frame

    def latest(self, slot_id: str) -> Optional["np.ndarray"]:
        self.read_count += 1
        return self._frames.get(slot_id)


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _solid_frame(width: int, height: int, level: int) -> "np.ndarray":
    return np.full((height, width, 3), level, dtype=np.uint8)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SimulationFrameTrackTest(unittest.IsolatedAsyncioTestCase):
    """The track must publish the present, never block, and never queue."""

    async def test_placeholder_frame_before_the_simulation_publishes(self) -> None:
        track = SimulationFrameTrack(FakeFrameBus(), "head", 32, 16, fps=120.0)

        frame = await track.recv()

        self.assertEqual((frame.width, frame.height), (32, 16))
        self.assertEqual(frame.format.name, "yuv420p")

    async def test_published_frame_reaches_the_encoder(self) -> None:
        frames = FakeFrameBus()
        frames.publish("leftWrist", _solid_frame(32, 16, 200))
        track = SimulationFrameTrack(frames, "leftWrist", 32, 16, fps=120.0)

        frame = await track.recv()
        recovered = frame.reformat(format="rgb24").to_ndarray()

        self.assertEqual(recovered.shape, (16, 32, 3))
        self.assertGreater(int(recovered.mean()), 150)

    async def test_frame_of_wrong_geometry_is_replaced_not_encoded(self) -> None:
        frames = FakeFrameBus()
        frames.publish("head", _solid_frame(64, 32, 255))
        track = SimulationFrameTrack(frames, "head", 32, 16, fps=120.0)

        frame = await track.recv()
        recovered = frame.reformat(format="rgb24").to_ndarray()

        self.assertEqual((frame.width, frame.height), (32, 16))
        self.assertLess(int(recovered.mean()), 100)

    async def test_presentation_timestamps_advance_at_the_declared_rate(self) -> None:
        track = SimulationFrameTrack(FakeFrameBus(), "head", 32, 16, fps=30.0)

        first = await track.recv()
        second = await track.recv()

        self.assertEqual(first.pts, 0)
        self.assertEqual(second.pts - first.pts, 3000)
        self.assertEqual(second.time_base.denominator, 90000)

    async def test_recv_paces_itself_without_busy_waiting(self) -> None:
        track = SimulationFrameTrack(FakeFrameBus(), "head", 32, 16, fps=25.0)
        ticks = 0

        async def count_ticks() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.001)
                ticks += 1

        counter = asyncio.ensure_future(count_ticks())
        started = time.monotonic()
        await track.recv()
        await track.recv()
        await track.recv()
        elapsed = time.monotonic() - started
        counter.cancel()

        self.assertGreaterEqual(elapsed, 0.06)
        self.assertGreater(ticks, 10)

    async def test_latest_frame_wins_over_an_earlier_one(self) -> None:
        frames = FakeFrameBus()
        track = SimulationFrameTrack(frames, "head", 32, 16, fps=120.0)
        frames.publish("head", _solid_frame(32, 16, 10))
        await track.recv()
        frames.publish("head", _solid_frame(32, 16, 240))

        frame = await track.recv()
        recovered = frame.reformat(format="rgb24").to_ndarray()

        self.assertGreater(int(recovered.mean()), 150)

    async def test_a_stopped_track_refuses_to_produce_frames(self) -> None:
        track = SimulationFrameTrack(FakeFrameBus(), "head", 32, 16, fps=120.0)
        track.stop()

        with self.assertRaises(Exception):
            await track.recv()

    def test_invalid_geometry_and_rate_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            SimulationFrameTrack(FakeFrameBus(), "head", 0, 16)
        with self.assertRaises(ValueError):
            SimulationFrameTrack(FakeFrameBus(), "head", 32, 16, fps=0.0)


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class SelfSignedCertificateTest(unittest.TestCase):
    """The certificate exists only to satisfy the GUI's https requirement."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.directory = Path(self._directory.name) / "preview"

    def test_generated_pair_is_reused_on_the_next_start(self) -> None:
        first = ensure_self_signed_certificate(self.directory, ("192.168.1.5",))
        original = first.certificate.read_bytes()

        second = ensure_self_signed_certificate(self.directory, ("192.168.1.5",))

        self.assertEqual(first, second)
        self.assertEqual(second.certificate.read_bytes(), original)

    def test_subject_alternative_names_cover_loopback_and_extra_hosts(self) -> None:
        from cryptography import x509

        paths = ensure_self_signed_certificate(
            self.directory, ("192.168.1.5", "robot.local")
        )
        certificate = x509.load_pem_x509_certificate(paths.certificate.read_bytes())
        names = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value

        self.assertIn("localhost", names.get_values_for_type(x509.DNSName))
        self.assertIn("robot.local", names.get_values_for_type(x509.DNSName))
        addresses = [str(value) for value in names.get_values_for_type(x509.IPAddress)]
        self.assertIn("127.0.0.1", addresses)
        self.assertIn("192.168.1.5", addresses)

    def test_a_new_host_forces_a_new_certificate(self) -> None:
        first = ensure_self_signed_certificate(self.directory)
        original = first.certificate.read_bytes()

        ensure_self_signed_certificate(self.directory, ("192.168.1.5",))

        self.assertNotEqual(first.certificate.read_bytes(), original)

    def test_key_and_certificate_are_owner_only(self) -> None:
        paths = ensure_self_signed_certificate(self.directory)

        for path in (paths.certificate, paths.private_key):
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600, f"{path} is not owner-only")


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class PreviewServerTest(unittest.IsolatedAsyncioTestCase):
    """The server implements exactly the GUI's fixed-port offer exchange."""

    async def asyncSetUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.frames = FakeFrameBus()
        self.slot = FakeCameraSlot("head", 32, 16, _free_port())
        self.server = PreviewServer(
            self.frames,
            (self.slot,),
            host="127.0.0.1",
            fps=60.0,
            cert_dir=Path(self._directory.name),
        )
        await self.server.start()
        self.addAsyncCleanup(self.server.stop)
        self.origin = f"https://127.0.0.1:{self.slot.preview_port}"
        self.ssl_context = ssl.create_default_context(
            cafile=str(Path(self._directory.name) / "cert.pem")
        )

    def _session(self) -> "ClientSession":
        session = ClientSession(connector=TCPConnector(ssl=self.ssl_context))
        self.addAsyncCleanup(session.close)
        return session

    def test_endpoints_report_the_url_the_gui_needs(self) -> None:
        endpoint = self.server.endpoints[0]

        self.assertEqual(endpoint.slot_id, "head")
        self.assertEqual(endpoint.url, f"{self.origin}/")

    async def test_offer_is_answered_with_a_video_answer(self) -> None:
        peer = RTCPeerConnection()
        self.addAsyncCleanup(peer.close)
        peer.addTransceiver("video", direction="recvonly")
        await peer.setLocalDescription(await peer.createOffer())

        async with self._session() as session:
            response = await session.post(
                f"{self.origin}/offer",
                data=json.dumps(
                    {
                        "sdp": peer.localDescription.sdp,
                        "type": peer.localDescription.type,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(response.status, 200)
            payload = await response.json()

        self.assertEqual(payload["type"], "answer")
        self.assertIn("m=video", payload["sdp"])
        await peer.setRemoteDescription(
            RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
        )
        self.assertEqual(len(self.server.connections), 1)

    async def test_a_negotiated_viewer_receives_simulated_frames(self) -> None:
        self.frames.publish("head", _solid_frame(32, 16, 210))
        peer = RTCPeerConnection()
        self.addAsyncCleanup(peer.close)
        received: asyncio.Future = asyncio.get_running_loop().create_future()

        @peer.on("track")
        def on_track(track) -> None:
            async def pull() -> None:
                try:
                    frame = await track.recv()
                except Exception as error:
                    if not received.done():
                        received.set_exception(error)
                    return
                if not received.done():
                    received.set_result(frame)

            asyncio.ensure_future(pull())

        peer.addTransceiver("video", direction="recvonly")
        await peer.setLocalDescription(await peer.createOffer())
        async with self._session() as session:
            response = await session.post(
                f"{self.origin}/offer",
                data=json.dumps(
                    {
                        "sdp": peer.localDescription.sdp,
                        "type": peer.localDescription.type,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            payload = await response.json()
        await peer.setRemoteDescription(
            RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
        )

        frame = await asyncio.wait_for(received, timeout=20.0)

        self.assertEqual((frame.width, frame.height), (32, 16))

    async def test_a_closed_connection_is_forgotten_and_its_track_stopped(self) -> None:
        peer = RTCPeerConnection()
        self.addAsyncCleanup(peer.close)
        peer.addTransceiver("video", direction="recvonly")
        await peer.setLocalDescription(await peer.createOffer())
        async with self._session() as session:
            response = await session.post(
                f"{self.origin}/offer",
                data=json.dumps(
                    {
                        "sdp": peer.localDescription.sdp,
                        "type": peer.localDescription.type,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            payload = await response.json()
        await peer.setRemoteDescription(
            RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
        )
        served = self.server.connections[0]
        track = served.getSenders()[0].track

        await served.close()
        for _ in range(100):
            if not self.server.connections:
                break
            await asyncio.sleep(0.02)

        self.assertEqual(self.server.connections, ())
        self.assertEqual(track.readyState, "ended")

    async def test_stopping_the_server_drops_every_connection(self) -> None:
        peer = RTCPeerConnection()
        self.addAsyncCleanup(peer.close)
        peer.addTransceiver("video", direction="recvonly")
        await peer.setLocalDescription(await peer.createOffer())
        async with self._session() as session:
            response = await session.post(
                f"{self.origin}/offer",
                data=json.dumps(
                    {
                        "sdp": peer.localDescription.sdp,
                        "type": peer.localDescription.type,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            payload = await response.json()
        await peer.setRemoteDescription(
            RTCSessionDescription(sdp=payload["sdp"], type=payload["type"])
        )

        await self.server.stop()

        self.assertEqual(self.server.connections, ())
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", self.slot.preview_port)), 0)

    async def test_preflight_and_cors_let_the_gui_call_across_origins(self) -> None:
        async with self._session() as session:
            response = await session.options(f"{self.origin}/offer")

            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])

    async def test_a_body_that_is_not_an_offer_is_rejected(self) -> None:
        async with self._session() as session:
            for body in ("not json", json.dumps({"type": "answer", "sdp": "x"}), "[]"):
                response = await session.post(
                    f"{self.origin}/offer",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )

                self.assertEqual(response.status, 400, body)
        self.assertEqual(self.server.connections, ())

    async def test_starting_twice_is_refused(self) -> None:
        with self.assertRaises(RuntimeError):
            await self.server.start()


@unittest.skipUnless(_HAS_DEPENDENCIES, _SKIP_REASON)
class PreviewServerThreadTest(unittest.TestCase):
    """A simulation keeps the main thread, so streaming must run beside it."""

    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.slots = (
            FakeCameraSlot("head", 32, 16, _free_port()),
            FakeCameraSlot("leftWrist", 32, 16, _free_port()),
        )
        self.server = PreviewServer(
            FakeFrameBus(),
            self.slots,
            host="127.0.0.1",
            cert_dir=Path(self._directory.name),
        )

    def test_background_thread_binds_every_slot_and_stops_cleanly(self) -> None:
        endpoints = self.server.run_in_thread()
        self.addCleanup(self.server.shutdown)

        self.assertEqual([endpoint.slot_id for endpoint in endpoints], ["head", "leftWrist"])
        for slot in self.slots:
            with socket.socket() as probe:
                self.assertEqual(
                    probe.connect_ex(("127.0.0.1", slot.preview_port)),
                    0,
                    f"port {slot.preview_port} should be served",
                )

        self.server.shutdown()

        for slot in self.slots:
            with socket.socket() as probe:
                self.assertNotEqual(probe.connect_ex(("127.0.0.1", slot.preview_port)), 0)

    def test_a_taken_port_fails_loudly_and_releases_the_others(self) -> None:
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", self.slots[1].preview_port))
            blocker.listen(1)

            with self.assertRaises(OSError):
                self.server.run_in_thread()

        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(("127.0.0.1", self.slots[0].preview_port)), 0)

    def test_no_slots_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            PreviewServer(FakeFrameBus(), (), cert_dir=Path(self._directory.name))


if __name__ == "__main__":
    unittest.main()
