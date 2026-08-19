"""The hardware seam: the real G1, and the asymmetry that makes it safe.

Every other module in this package can be exercised without a robot in the
room. This one cannot, and that changes what it is allowed to assume. It owns
three things that only physical hardware can settle, and it is built around a
single asymmetry: reading and stopping are always permitted, commanding motion
never is unless a named human said so.

``LinkAttestation``   what the robot itself can be observed to say
``MotionAuthority``   the named grant without which nothing here moves
``RealG1``            the ``RobotInterface`` a live G1 fills

The asymmetry is the design. A seam that exposed one ``command`` method would
make "observe the robot" and "move the robot" the same capability, and every
caller would then be one typo away from motion. Here the read path needs no
grant, ``hold`` needs no grant because stopping is never the dangerous
direction, and ``command_joint_positions`` refuses without a grant that names
a person and what they authorized. A missing grant is not a misconfiguration
to be defaulted; it is the normal state of a robot nobody has cleared.

Three refusals:

- It refuses to command without a ``MotionAuthority``. Not a flag, not an
  environment variable: a value someone had to construct with their name in
  it, scoped to one skill revision and one embodiment digest.
- It refuses to report an instantaneous sample as a peak. Telemetry arrives far
  faster than anyone reads it, and the envelope bounds every instant, so the
  adapter accumulates the largest magnitude seen between reads. An adapter that
  forwarded the latest sample would open a silent envelope hole precisely where
  a position servo does its overshooting.
- It refuses to attest what it cannot observe. The link can prove a cadence and
  a reachable image service. It cannot prove which hand is bolted to the wrist,
  whether a guardian is standing there, or whether the workspace is clear.
  Those stay unverified until a human clears them by name.

On this laboratory's G1 specifically: the end effector is a BrainCo Revo 2,
not the Dex1-1 the published ``unifolm-vla-base`` G1 checkpoint was trained
for. That is a fact about the room, so it lives here as a declared constant
rather than being inferred, and it is why ``assess_policy_compatibility``
against that checkpoint reports adaptation rather than a match. The mismatch
is not a defect in the profile; it is the profile doing its job.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.runtime import RobotState

END_EFFECTOR_BRAINCO_REVO2 = "brainco_revo2"
"""The hand actually mounted on this laboratory's G1.

Declared, not detected. No joint-state topic reports a manufacturer, so this
is a human's statement about the room, and it is recorded as a constant so the
statement is reviewable rather than buried in a call site.
"""

DEFAULT_ROBOT_HOST = "192.168.123.161"
DEFAULT_DDS_DOMAIN = 0
DEFAULT_ROBOT_INTERFACE = "enp0s31f6"
"""The wired link to the robot on this workstation.

Named because a multicast group must be joined on a specific wire. This machine
also has Wi-Fi and a Tailscale interface, and both carry a default route, so a
join that lets the kernel choose listens on the wrong cable and hears nothing.
"""
DDS_DISCOVERY_GROUP = "239.255.0.1"
DDS_DISCOVERY_PORT_BASE = 7400
_RTPS_MAGIC = b"RTPS"
_ROUTE_PROBE_PORT = 9
"""Discard port: the route probe connects, transmits nothing, and closes."""

UNOBSERVABLE_OVER_THE_LINK = (
    "end_effector: no telemetry topic reports which hand is mounted",
    "control_authority: what this robot is permitted to be commanded for is a "
    "laboratory decision, not a robot fact",
    "guardian_present: presence of a supervising human is not on the bus",
    "workspace_clear: whether the cell is clear is not on the bus",
    "estop_reachable: physical reach to the stop is not on the bus",
)
"""Facts the link can never settle, listed so nobody expects it to.

This is the hardware twin of ``UNREPRESENTABLE_IN_SIMULATION``. Both exist so
that the boundary of a measurement is written down next to the measurement.
"""


@dataclass(frozen=True)
class LinkAttestation:
    """What one read-only observation of the live robot established.

    It answers exactly one question -- is the thing on the other end of the
    cable the configuration our evidence would be scoped to -- and answers it
    only as far as observation reaches. ``cleared`` names the embodiment fields
    this observation is entitled to confirm; everything in
    ``UNOBSERVABLE_OVER_THE_LINK`` stays outside it by construction.
    """

    robot_host: str
    dds_domain: int
    interface: str
    observed_at: datetime
    reachable: bool
    discovery_packets: Optional[int]
    listened_on: str = ""
    telemetry_hz: Optional[float] = None
    image_service_reachable: Optional[bool] = None
    cleared: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "cleared", tuple(self.cleared))
        object.__setattr__(self, "findings", tuple(self.findings))
        for entry in self.cleared:
            for unobservable in UNOBSERVABLE_OVER_THE_LINK:
                if unobservable.split(":", 1)[0] == entry:
                    raise ValueError(
                        f"the link cannot clear {entry!r}: {unobservable}"
                    )

    @property
    def observed(self) -> bool:
        """Whether the discovery listen actually happened.

        ``discovery_packets is None`` means nobody looked: the socket could not
        join the group, or joined the wrong wire. That is a fact about this
        process, not about the robot, and it must never be reported as one.
        """
        return self.discovery_packets is not None

    @property
    def alive(self) -> bool:
        """Whether the robot was observed publishing, not merely pingable.

        A host that answers ICMP while its control stack is down is the most
        expensive kind of false positive: every later refusal looks like a
        governance bug instead of a robot that is not running.

        An unattempted observation is not alive either, which is the safe
        direction: ``observed`` is what distinguishes the two, and a caller that
        wants to know why must read it rather than infer it from this.
        """
        return self.reachable and bool(self.discovery_packets)


def _route_address(robot_host: str) -> Optional[str]:
    """The local address the kernel would use to reach the robot.

    A connected UDP socket transmits nothing; it only asks the routing table
    which wire owns this destination. That answer is what makes an empty
    ``interface`` argument safe: rather than letting the default route decide
    and then reporting the silence of the wrong cable as a silent robot, the
    listen defaults to the wire the robot is actually on.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((robot_host, _ROUTE_PROBE_PORT))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def _interface_address(interface: str) -> Optional[str]:
    """The IPv4 address of one local interface, or ``None`` if unknown.

    Read from the kernel rather than guessed. A join on the wrong address is
    indistinguishable from a silent robot, so a caller that cannot resolve the
    wire must be told instead of defaulted onto another one.
    """
    if not interface:
        return None
    try:
        import fcntl

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            packed = fcntl.ioctl(
                sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack("256s", interface.encode("utf-8")[:15]),
            )
        finally:
            sock.close()
        return socket.inet_ntoa(packed[20:24])
    except OSError:
        return None


def observe_link(
    robot_host: str = DEFAULT_ROBOT_HOST,
    dds_domain: int = DEFAULT_DDS_DOMAIN,
    interface: str = DEFAULT_ROBOT_INTERFACE,
    listen_s: float = 2.0,
    image_service_port: Optional[int] = 8081,
    now: Optional[Callable[[], datetime]] = None,
) -> LinkAttestation:
    """Watch the robot without addressing it.

    Strictly passive on the control plane: it joins the DDS discovery multicast
    group and counts RTPS traffic. It publishes nothing, subscribes to no data
    topic, and sends no command, so running it against a live robot cannot move
    anything. The image-service check is a TCP connect that is closed
    immediately.

    Passivity here is not politeness. The first thing anyone wants to do with a
    new robot is "just check if it's there", and if that check shares a code
    path with commanding, the check becomes the accident.
    """
    stamp = (now or _utc_now)()
    findings: list[str] = []
    packets: Optional[int] = None
    first: Optional[float] = None
    last: Optional[float] = None

    route = _route_address(robot_host)
    local = _interface_address(interface) if interface else route
    listened_on = f"{interface}:{local}" if interface else (local or "")
    on_robot_wire = local is not None and local == route
    if interface and local is None:
        findings.append(
            f"interface {interface!r} has no IPv4 address on this host, so the "
            "discovery group could not be joined on the wire the robot is on; "
            "this is a fact about this workstation, not about the robot"
        )
    else:
        port = DDS_DISCOVERY_PORT_BASE + 250 * dds_domain + 1
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", port))
            membership = struct.pack(
                "4s4s",
                socket.inet_aton(DDS_DISCOVERY_GROUP),
                socket.inet_aton(local or "0.0.0.0"),
            )
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership
            )
            sock.settimeout(0.25)
            packets = 0
            deadline = time.monotonic() + max(0.0, listen_s)
            while time.monotonic() < deadline:
                try:
                    payload, sender = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError as error:  # pragma: no cover - platform dependent
                    findings.append(f"discovery listen failed: {error}")
                    break
                if sender[0] != robot_host or not payload.startswith(
                    _RTPS_MAGIC
                ):
                    continue
                packets += 1
                moment = time.monotonic()
                first = moment if first is None else first
                last = moment
        except OSError as error:
            packets = None
            findings.append(
                f"could not join the discovery group on {port} via "
                f"{listened_on}: {error}"
            )
        finally:
            sock.close()

    if packets == 0 and not on_robot_wire:
        packets = None
        findings.append(
            f"listened on {listened_on or 'the default route'}, but the route "
            f"to {robot_host} leaves via {route or 'no known interface'}; this "
            "observation was taken on the wrong wire and says nothing about "
            "the robot"
        )
    if packets == 0:
        findings.append(
            f"no RTPS discovery traffic from {robot_host} on domain "
            f"{dds_domain} in {listen_s:g}s via {listened_on}; the robot is "
            "not publishing"
        )
    elif packets is None:
        findings.append(
            "the discovery listen did not run, so whether this robot is "
            "publishing is unknown; nothing here may be read as evidence "
            "about the robot"
        )

    rate: Optional[float] = None
    if first is not None and last is not None and last > first:
        rate = (packets - 1) / (last - first)

    image_reachable: Optional[bool] = None
    if image_service_port is not None:
        image_reachable = _port_open(robot_host, image_service_port)
        if not image_reachable:
            findings.append(
                f"the image service on {robot_host}:{image_service_port} did "
                "not accept a connection, so no policy can be given a "
                "trained-equivalent observation stream"
            )

    return LinkAttestation(
        robot_host=robot_host,
        dds_domain=dds_domain,
        interface=interface,
        observed_at=stamp,
        reachable=bool(packets) or image_reachable is True,
        discovery_packets=packets,
        listened_on=listened_on,
        telemetry_hz=rate,
        image_service_reachable=image_reachable,
        cleared=("onboard_image_service",) if image_reachable else (),
        findings=tuple(findings),
    )


@dataclass(frozen=True)
class MotionAuthority:
    """One named human's grant to command one configuration.

    It is deliberately shaped like ``HumanApproval`` and deliberately separate
    from it. Approval is about evidence -- has this been validated enough. This
    is about the room: is someone standing there right now who said this robot
    may be driven. The two are different questions asked of different people at
    different times, and collapsing them would let accumulated evidence unlock
    hardware with nobody present.
    """

    authorized_by: str
    statement: str
    granted_at: datetime
    skill_version_id: str
    embodiment_digest: str

    def __post_init__(self) -> None:
        if not self.authorized_by.strip():
            raise ValueError("a MotionAuthority must name who authorized it")
        if not self.statement.strip():
            raise ValueError(
                "a MotionAuthority must record what was authorized; an "
                "unstated grant cannot be reviewed"
            )

    def covers(self, skill_version_id: str, embodiment_digest: str) -> bool:
        return (
            self.skill_version_id == skill_version_id
            and self.embodiment_digest == embodiment_digest
        )


class TelemetrySource(Protocol):
    """Whatever delivers raw joint samples from the robot.

    Kept as a seam so the peak accumulator below can be tested without a robot,
    and so the DDS dependency stays at the edge instead of infecting the
    adapter.
    """

    def sample(self) -> Mapping[str, object]:
        """Return the latest raw sample: positions, velocities, force, age."""


class PeakAccumulator:
    """Turns a fast sample stream into the peaks ``RobotState`` requires.

    ``RobotState`` says velocity and force are the largest magnitudes observed
    since the previous read. Telemetry arrives at hundreds of hertz while a
    control loop reads at tens, so the adapter is the only place that can honor
    that contract. It is a separate object because it is the one piece of this
    module with interesting behaviour and no hardware in it.
    """

    def __init__(self, joint_count: int) -> None:
        if joint_count <= 0:
            raise ValueError("joint_count must be positive")
        self._joint_count = joint_count
        self._lock = threading.Lock()
        self._velocity_peaks = [0.0] * joint_count
        self._force_peak = 0.0
        self._samples = 0

    def observe(
        self, joint_velocity_rps: Sequence[float], end_effector_force_n: float
    ) -> None:
        if len(joint_velocity_rps) != self._joint_count:
            raise ValueError(
                f"expected {self._joint_count} joint velocities, got "
                f"{len(joint_velocity_rps)}"
            )
        with self._lock:
            for index, value in enumerate(joint_velocity_rps):
                magnitude = abs(float(value))
                if magnitude > self._velocity_peaks[index]:
                    self._velocity_peaks[index] = magnitude
            magnitude = abs(float(end_effector_force_n))
            if magnitude > self._force_peak:
                self._force_peak = magnitude
            self._samples += 1

    def drain(self) -> tuple[tuple[float, ...], float, int]:
        """Report the peaks since the previous drain, and reset them.

        Draining is destructive on purpose: a peak that survived its read would
        be counted again by the next one, and an envelope violation would then
        abort every subsequent run of a configuration that is in fact fine.
        """
        with self._lock:
            peaks = tuple(self._velocity_peaks)
            force = self._force_peak
            samples = self._samples
            self._velocity_peaks = [0.0] * self._joint_count
            self._force_peak = 0.0
            self._samples = 0
        return peaks, force, samples


class JointCommandWriter(Protocol):
    """Whatever actually puts a setpoint on the wire, and takes it off again.

    Separated from ``RealG1`` because this is the only part of the hardware seam
    that cannot be written honestly without a robot to test it against. Its
    absence is therefore a first-class state rather than a stub: a ``RealG1``
    with no writer can observe a live robot and can be asked to stop, but every
    command refuses. That is the correct shape for this build, and it is what
    stops an untested DDS writer from being the thing between a person and a
    moving arm.
    """

    def write(self, positions_rad: Sequence[float]) -> None:
        """Put one joint-space waypoint on the wire."""

    def stop(self) -> None:
        """Command an immediate stop-and-hold."""


class RealG1:
    """A live Unitree G1 presented as a ``RobotInterface``.

    It carries no governance logic beyond the one refusal it must own: motion
    requires a grant. Everything else -- whether the skill is admissible,
    whether the envelope holds, whether the run proved anything -- is decided
    above this boundary by modules that can be tested without a robot.

    It is deliberately not a ``ResettableRobot``. Real hardware cannot be
    teleported to a chosen initial condition, so the campaign driver and the
    calibration probe structurally cannot drive it, which is exactly the
    property that keeps unattended iteration in simulation.
    """

    def __init__(
        self,
        telemetry: TelemetrySource,
        joint_names: Sequence[str],
        control_frequency_hz: float,
        embodiment: EmbodimentProfile,
        authority: Optional[MotionAuthority] = None,
        writer: Optional[JointCommandWriter] = None,
        skill_version_id: str = "",
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        names = tuple(joint_names)
        if not names:
            raise ValueError("a robot with no named joints cannot be commanded")
        if control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        self._telemetry = telemetry
        self._joint_names = names
        self._control_frequency_hz = float(control_frequency_hz)
        self._embodiment = embodiment
        self._authority = authority
        self._writer = writer
        self._skill_version_id = skill_version_id
        self._clock = clock or time.monotonic
        self._peaks = PeakAccumulator(len(names))
        self._held = False
        self._commands = 0

    @property
    def is_real_robot(self) -> bool:
        return True

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self._joint_names

    @property
    def control_frequency_hz(self) -> float:
        return self._control_frequency_hz

    @property
    def held(self) -> bool:
        return self._held

    @property
    def can_command(self) -> bool:
        """Whether this robot could move at all if it were asked.

        False when no writer is attached. Exposed so a caller can find out by
        asking rather than by commanding and catching, which on hardware is the
        difference between a check and an attempt.
        """
        return self._writer is not None

    @property
    def commands_issued(self) -> int:
        return self._commands

    @property
    def peaks(self) -> PeakAccumulator:
        return self._peaks

    def read_state(self) -> RobotState:
        """Report the measured state. Never commands, never needs a grant."""
        sample = self._telemetry.sample()
        positions = tuple(
            float(value) for value in sample["joint_positions_rad"]  # type: ignore[index]
        )
        if len(positions) != len(self._joint_names):
            raise ValueError(
                f"telemetry reported {len(positions)} joints, but this robot "
                f"declares {len(self._joint_names)}"
            )
        self._peaks.observe(
            sample["joint_velocity_rps"],  # type: ignore[arg-type,index]
            float(sample["end_effector_force_n"]),  # type: ignore[index]
        )
        velocity, force, _ = self._peaks.drain()
        return RobotState(
            joint_positions_rad=positions,
            joint_velocity_rps=velocity,
            end_effector_force_n=force,
            end_effector_position_m=tuple(
                float(value)
                for value in sample["end_effector_position_m"]  # type: ignore[index]
            ),
            guardian_present=bool(sample["guardian_present"]),  # type: ignore[index]
            estop_engaged=bool(sample["estop_engaged"]),  # type: ignore[index]
            estop_reachable=bool(sample["estop_reachable"]),  # type: ignore[index]
            workspace_clear=bool(sample["workspace_clear"]),  # type: ignore[index]
            age_s=float(sample["age_s"]),  # type: ignore[index]
        )

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Command one joint-space waypoint, if someone authorized it."""
        if self._held:
            raise RuntimeError(
                "this robot is holding after a stop; a held robot does not "
                "accept further motion"
            )
        if self._writer is None:
            raise NotImplementedError(
                "this RealG1 has no command writer attached, so it can observe "
                "and stop a real G1 but cannot drive one"
            )
        if self._authority is None:
            raise PermissionError(
                "commanding a real G1 requires a MotionAuthority naming who "
                "authorized it; no grant was supplied"
            )
        if not self._authority.covers(
            self._skill_version_id, self._embodiment.digest()
        ):
            raise PermissionError(
                "the MotionAuthority was granted for a different skill "
                "revision or embodiment than this robot is running"
            )
        if self._embodiment.unverified_fields:
            raise PermissionError(
                "this embodiment still has unverified fields, so no grant can "
                "authorize motion: "
                + ", ".join(sorted(self._embodiment.unverified_fields))
            )
        targets = tuple(float(value) for value in positions_rad)
        if len(targets) != len(self._joint_names):
            raise ValueError(
                f"expected {len(self._joint_names)} joint targets, got "
                f"{len(targets)}"
            )
        self._writer.write(targets)
        self._commands += 1

    def hold(self) -> None:
        """Stop and hold. Always permitted, and latched once used.

        Latching happens first and unconditionally: whatever the wire does, this
        object must never accept another command after a stop was requested.

        With no writer attached there is nothing to stop, and saying so is the
        whole point. This build cannot command motion, so a robot it is driving
        is never in motion; a ``hold`` that quietly returned success while
        having no way to transmit a stop would be indistinguishable from one
        that worked, and that is the single most expensive lie this module could
        tell. It raises instead, after latching.
        """
        self._held = True
        if self._writer is None:
            raise NotImplementedError(
                "this RealG1 has no command writer attached, so it cannot "
                "transmit a stop; the robot is not being driven by this object, "
                "and stopping it is a physical action nobody here can perform"
            )
        self._writer.stop()


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)
