"""The hardware seam refuses in the directions that cost a person something."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.hardware import (
    END_EFFECTOR_BRAINCO_REVO2,
    UNOBSERVABLE_OVER_THE_LINK,
    LinkAttestation,
    MotionAuthority,
    PeakAccumulator,
    RealG1,
    observe_link,
)

SKILL = "reach-left@1"


def _embodiment(**overrides: object) -> EmbodimentProfile:
    fields: dict[str, object] = {
        "robot_model": "unitree_g1_29dof",
        "arm_dof": 2,
        "end_effector": END_EFFECTOR_BRAINCO_REVO2,
        "camera_map": {"observation.images.head": "head"},
        "control_frequency_hz": 50.0,
        "control_authority": "arm_sdk",
        "state_dim": 2,
        "action_dim": 2,
        "onboard_image_service": True,
        "unverified_fields": (),
    }
    fields.update(overrides)
    return EmbodimentProfile(**fields)  # type: ignore[arg-type]


class _Telemetry:
    """A stand-in for the bus, so the adapter is testable without a robot."""

    def __init__(self, joints: int = 2) -> None:
        self.joints = joints
        self.velocity = (0.0,) * joints
        self.force = 0.0
        self.guardian_present = True
        self.estop_engaged = False

    def sample(self) -> dict[str, object]:
        return {
            "joint_positions_rad": (0.1,) * self.joints,
            "joint_velocity_rps": self.velocity,
            "end_effector_force_n": self.force,
            "end_effector_position_m": (0.3, 0.1, 0.9),
            "guardian_present": self.guardian_present,
            "estop_engaged": self.estop_engaged,
            "estop_reachable": True,
            "workspace_clear": True,
            "age_s": 0.01,
        }


class _Writer:
    def __init__(self) -> None:
        self.written: list[tuple[float, ...]] = []
        self.stops = 0

    def write(self, positions_rad) -> None:
        self.written.append(tuple(float(v) for v in positions_rad))

    def stop(self) -> None:
        self.stops += 1


def _authority(digest: str, skill: str = SKILL) -> MotionAuthority:
    return MotionAuthority(
        authorized_by="lab-lead",
        statement="cleared one supervised reach at reduced rate",
        granted_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        skill_version_id=skill,
        embodiment_digest=digest,
    )


def _robot(
    *,
    embodiment: EmbodimentProfile | None = None,
    authority: MotionAuthority | None = None,
    writer: _Writer | None = None,
    skill: str = SKILL,
) -> RealG1:
    profile = embodiment or _embodiment()
    return RealG1(
        telemetry=_Telemetry(),
        joint_names=("left_elbow", "left_wrist_roll"),
        control_frequency_hz=50.0,
        embodiment=profile,
        authority=authority,
        writer=writer,
        skill_version_id=skill,
    )


# --- the peaks the envelope is checked against -------------------------------


def test_accumulator_reports_the_largest_magnitude_between_reads() -> None:
    peaks = PeakAccumulator(2)
    peaks.observe((0.1, -0.2), 1.0)
    peaks.observe((-1.4, 0.3), 8.0)
    peaks.observe((0.0, 0.0), 0.0)

    velocity, force, samples = peaks.drain()

    assert velocity == (1.4, 0.3)
    assert force == 8.0
    assert samples == 3


def test_draining_resets_so_one_peak_is_not_counted_twice() -> None:
    peaks = PeakAccumulator(1)
    peaks.observe((2.0,), 5.0)
    peaks.drain()

    peaks.observe((0.1,), 0.5)
    velocity, force, _ = peaks.drain()

    assert velocity == (0.1,)
    assert force == 0.5


def test_accumulator_rejects_a_sample_of_the_wrong_width() -> None:
    peaks = PeakAccumulator(2)
    with pytest.raises(ValueError, match="expected 2 joint velocities"):
        peaks.observe((0.1,), 0.0)


# --- what the link may and may not claim ------------------------------------


def test_the_link_cannot_clear_a_fact_it_cannot_observe() -> None:
    for unobservable in UNOBSERVABLE_OVER_THE_LINK:
        field = unobservable.split(":", 1)[0]
        with pytest.raises(ValueError, match=f"cannot clear '{field}'"):
            LinkAttestation(
                robot_host="192.168.123.161",
                dds_domain=0,
                interface="enp0s31f6",
                observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
                reachable=True,
                discovery_packets=10,
                cleared=(field,),
            )


def test_an_unattempted_observation_is_unknown_not_dead() -> None:
    attestation = LinkAttestation(
        robot_host="192.168.123.161",
        dds_domain=0,
        interface="wlan0",
        observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        reachable=False,
        discovery_packets=None,
    )

    assert attestation.observed is False
    assert attestation.alive is False


def test_a_silent_robot_is_observed_but_not_alive() -> None:
    attestation = LinkAttestation(
        robot_host="192.168.123.161",
        dds_domain=0,
        interface="enp0s31f6",
        observed_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        reachable=True,
        discovery_packets=0,
    )

    assert attestation.observed is True
    assert attestation.alive is False


def test_an_unresolvable_interface_is_a_fact_about_this_workstation() -> None:
    attestation = observe_link(
        interface="vegapunk_not_an_interface",
        listen_s=0.0,
        image_service_port=None,
    )

    assert attestation.observed is False
    assert attestation.alive is False
    assert any("this workstation" in f for f in attestation.findings)


# --- the grant --------------------------------------------------------------


def test_a_grant_must_name_a_person_and_what_was_authorized() -> None:
    with pytest.raises(ValueError, match="must name who authorized"):
        MotionAuthority(
            authorized_by="  ",
            statement="anything",
            granted_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            skill_version_id=SKILL,
            embodiment_digest="abc",
        )
    with pytest.raises(ValueError, match="must record what was authorized"):
        MotionAuthority(
            authorized_by="lab-lead",
            statement="   ",
            granted_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
            skill_version_id=SKILL,
            embodiment_digest="abc",
        )


# --- reading and stopping never need a grant --------------------------------


def test_reading_needs_no_grant_and_drains_the_peaks() -> None:
    telemetry = _Telemetry()
    robot = RealG1(
        telemetry=telemetry,
        joint_names=("a", "b"),
        control_frequency_hz=50.0,
        embodiment=_embodiment(),
    )
    telemetry.velocity = (0.4, -1.1)
    telemetry.force = 3.0

    state = robot.read_state()

    assert state.joint_velocity_rps == (0.4, 1.1)
    assert state.end_effector_force_n == 3.0
    assert robot.is_real_robot is True


def test_telemetry_of_the_wrong_width_is_refused_not_padded() -> None:
    robot = RealG1(
        telemetry=_Telemetry(joints=3),
        joint_names=("a", "b"),
        control_frequency_hz=50.0,
        embodiment=_embodiment(),
    )
    with pytest.raises(ValueError, match="telemetry reported 3 joints"):
        robot.read_state()


# --- commanding is the guarded direction ------------------------------------


def test_a_robot_with_no_writer_cannot_command_and_says_so() -> None:
    robot = _robot()
    assert robot.can_command is False
    with pytest.raises(NotImplementedError, match="no command writer"):
        robot.command_joint_positions((0.1, 0.1))


def test_a_missing_grant_refuses_motion() -> None:
    robot = _robot(writer=_Writer())
    with pytest.raises(PermissionError, match="requires a MotionAuthority"):
        robot.command_joint_positions((0.1, 0.1))


def test_a_grant_for_another_configuration_does_not_transfer() -> None:
    profile = _embodiment()
    robot = _robot(
        embodiment=profile,
        writer=_Writer(),
        authority=_authority("some-other-digest"),
    )
    with pytest.raises(PermissionError, match="different skill"):
        robot.command_joint_positions((0.1, 0.1))


def test_a_grant_for_another_skill_does_not_transfer() -> None:
    profile = _embodiment()
    robot = _robot(
        embodiment=profile,
        writer=_Writer(),
        authority=_authority(profile.digest(), skill="other-skill@1"),
    )
    with pytest.raises(PermissionError, match="different skill"):
        robot.command_joint_positions((0.1, 0.1))


def test_no_grant_can_authorize_an_unverified_embodiment() -> None:
    profile = _embodiment(unverified_fields=("end_effector",))
    robot = _robot(
        embodiment=profile,
        writer=_Writer(),
        authority=_authority(profile.digest()),
    )
    with pytest.raises(PermissionError, match="unverified fields"):
        robot.command_joint_positions((0.1, 0.1))


def test_a_granted_command_reaches_the_wire_once() -> None:
    profile = _embodiment()
    writer = _Writer()
    robot = _robot(
        embodiment=profile, writer=writer, authority=_authority(profile.digest())
    )

    robot.command_joint_positions((0.2, -0.3))

    assert writer.written == [(0.2, -0.3)]
    assert robot.commands_issued == 1


def test_a_command_of_the_wrong_width_never_reaches_the_wire() -> None:
    profile = _embodiment()
    writer = _Writer()
    robot = _robot(
        embodiment=profile, writer=writer, authority=_authority(profile.digest())
    )

    with pytest.raises(ValueError, match="expected 2 joint targets"):
        robot.command_joint_positions((0.2,))

    assert writer.written == []
    assert robot.commands_issued == 0


# --- stopping is latched ----------------------------------------------------


def test_hold_transmits_a_stop_and_latches_against_later_motion() -> None:
    profile = _embodiment()
    writer = _Writer()
    robot = _robot(
        embodiment=profile, writer=writer, authority=_authority(profile.digest())
    )

    robot.hold()

    assert writer.stops == 1
    assert robot.held is True
    with pytest.raises(RuntimeError, match="holding after a stop"):
        robot.command_joint_positions((0.1, 0.1))
    assert writer.written == []


def test_hold_without_a_writer_latches_before_it_admits_it_cannot_stop() -> None:
    robot = _robot()

    with pytest.raises(NotImplementedError, match="cannot transmit a stop"):
        robot.hold()

    assert robot.held is True
    with pytest.raises(RuntimeError, match="holding after a stop"):
        robot.command_joint_positions((0.1, 0.1))


# --- the structural guarantee ----------------------------------------------


def test_a_real_g1_is_not_resettable_so_campaigns_cannot_drive_it() -> None:
    assert not hasattr(_robot(), "reset")
