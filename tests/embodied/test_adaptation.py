"""What an adaptation candidate is allowed to be, and to command.

The load-bearing test in this file is the hostile-candidate one. Everything
else confirms the representation is honest; that one confirms it cannot be
used to buy authority.
"""

from __future__ import annotations

import random
import unittest

from vegapunk.embodied.adaptation import (
    DEFAULT_ADAPTATION_SPACE,
    GENE_BIAS_RAD,
    GENE_DEADBAND_RAD,
    GENE_GAIN_SCALE,
    GENE_LATENCY_COMPENSATION_STEPS,
    GENE_NEUTRAL_VALUES,
    GENE_RATE_LIMIT_SCALE,
    GENE_SETTLE_GAIN,
    GENE_SMOOTHING_ALPHA,
    ORIGIN_MUTATION,
    ORIGIN_PROPOSAL,
    ORIGIN_ROOT,
    AdaptationCandidate,
    AdaptationGene,
    AdaptationSpace,
    AdaptedJointRuntime,
    GoalActionSource,
)
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    DeterministicJointRuntime,
    JointPoseGoal,
    RobotState,
)
from vegapunk.embodied.safety import (
    ABORT_HUMAN_STOP,
    AbortDirective,
    SafetyEnvelope,
)
from vegapunk.embodied.skill import SkillSelection

_ENVELOPE = SafetyEnvelope(
    max_duration_s=20.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
)

# A unit-test double has no servo, so it tracks its setpoints exactly: the
# measured peak equals the commanded rate. Anything with real dynamics is
# measured by ``vegapunk.embodied.calibration``.
_EXACT_TRACKING = CommandRateCalibration(
    commanded_rate_rps=1.5,
    peak_joint_velocity_rps=1.5,
    control_frequency_hz=30.0,
    measured_on="FakeRobot",
)


class FakeRobot:
    """A two-joint robot that tracks commands exactly."""

    def __init__(self, positions=(0.0, 0.0), **state_overrides):
        self.positions = tuple(positions)
        self.commands: list[tuple[float, ...]] = []
        self.holds = 0
        self.state_overrides = dict(state_overrides)

    def read_state(self) -> RobotState:
        fields = dict(
            joint_positions_rad=self.positions,
            joint_velocity_rps=(0.0,) * len(self.positions),
            end_effector_force_n=1.0,
            end_effector_position_m=(0.1, 0.0, 0.8),
            guardian_present=True,
            estop_engaged=False,
            estop_reachable=True,
            workspace_clear=True,
            age_s=0.05,
        )
        fields.update(self.state_overrides)
        return RobotState(**fields)

    def command_joint_positions(self, positions_rad) -> None:
        self.commands.append(tuple(positions_rad))
        self.positions = tuple(positions_rad)

    def hold(self) -> None:
        self.holds += 1


class StuckRobot(FakeRobot):
    """A robot whose joints never answer a command.

    The case the setpoint leash exists for: an integrated ramp against a
    blocked joint is a torque ramp, not a motion.
    """

    def command_joint_positions(self, positions_rad) -> None:
        self.commands.append(tuple(positions_rad))


def _step_until_settled(runtime, limit: int) -> int:
    """Step until the runtime reports completion, or ``limit`` steps.

    The runtime completes when the robot stops making progress, so a test that
    stepped a fixed number of times would be stepping a finished run. The
    governed loop stops on ``complete``; these tests do the same, and assert on
    the settled state the run arrived at.
    """
    for taken in range(limit):
        if runtime.step().complete:
            return taken + 1
    return limit


def _goal(**overrides: object) -> JointPoseGoal:
    fields: dict[str, object] = dict(
        skill_version_id="home_arm@1",
        target_joint_positions_rad=(0.5, -0.5),
        satisfies=("at_home_pose",),
    )
    fields.update(overrides)
    return JointPoseGoal(**fields)  # type: ignore[arg-type]


def _selection(skill_version_id: str = "home_arm@1") -> SkillSelection:
    return SkillSelection(
        skill_version_id=skill_version_id,
        contract_digest="digest",
        arguments={},
    )


def _candidate(**overrides: float) -> AdaptationCandidate:
    """A candidate built directly, bypassing the space's ranges.

    Used for the hostile cases on purpose: the runtime's guarantees must not
    depend on the proposal having come from a well-behaved space.
    """
    values = dict(GENE_NEUTRAL_VALUES)
    values.update(overrides)
    return AdaptationCandidate(values=values, origin=ORIGIN_PROPOSAL)


def _runtime(robot, candidate, goal=None, source=None, clock=None, **kw):
    goal = goal if goal is not None else _goal()
    fields = dict(
        robot=robot,
        source=source if source is not None else GoalActionSource(goal),
        candidate=candidate,
        goal=goal,
        command_rate=_EXACT_TRACKING,
        envelope=_ENVELOPE,
        clock=clock,
    )
    fields.update(kw)
    return AdaptedJointRuntime(**fields)


def _running(robot, candidate, **kw):
    """A runtime that has been started, which is the only state it may step in.

    ``start`` is not ceremony: it seeds the ramp and the low-pass from where
    the robot actually is, so a test that stepped without it would be
    measuring a runtime no caller can construct.
    """
    runtime = _runtime(robot, candidate, **kw)
    runtime.start(_selection(runtime.goal.skill_version_id))
    return runtime


class AdaptationGeneTests(unittest.TestCase):
    def test_a_gene_must_justify_its_range(self) -> None:
        with self.assertRaises(ValueError) as caught:
            AdaptationGene(
                name="gain_scale",
                low=0.5,
                high=1.5,
                unit="dimensionless",
                rationale="",
            )
        self.assertIn("rationale", str(caught.exception))

    def test_a_gene_must_declare_a_unit(self) -> None:
        with self.assertRaises(ValueError) as caught:
            AdaptationGene(
                name="bias_rad",
                low=-1.0,
                high=1.0,
                unit="",
                rationale="stated",
            )
        self.assertIn("unit", str(caught.exception))

    def test_an_inverted_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationGene(
                name="gain_scale",
                low=1.5,
                high=0.5,
                unit="dimensionless",
                rationale="stated",
            )

    def test_clamp_pulls_values_into_the_range(self) -> None:
        self.assertEqual(GENE_GAIN_SCALE.clamp(9.0), GENE_GAIN_SCALE.high)
        self.assertEqual(GENE_GAIN_SCALE.clamp(-9.0), GENE_GAIN_SCALE.low)
        self.assertEqual(GENE_GAIN_SCALE.clamp(1.0), 1.0)

    def test_sampling_stays_inside_the_range(self) -> None:
        generator = random.Random(7)
        for gene in DEFAULT_ADAPTATION_SPACE.genes:
            for _ in range(50):
                value = gene.sample(generator)
                self.assertGreaterEqual(value, gene.low)
                self.assertLessEqual(value, gene.high)

    def test_the_digest_covers_the_range_not_the_prose(self) -> None:
        widened = AdaptationGene(
            name=GENE_GAIN_SCALE.name,
            low=GENE_GAIN_SCALE.low,
            high=GENE_GAIN_SCALE.high + 1.0,
            unit=GENE_GAIN_SCALE.unit,
            rationale=GENE_GAIN_SCALE.rationale,
        )
        reworded = AdaptationGene(
            name=GENE_GAIN_SCALE.name,
            low=GENE_GAIN_SCALE.low,
            high=GENE_GAIN_SCALE.high,
            unit=GENE_GAIN_SCALE.unit,
            rationale="a differently worded but equally defensible range",
        )
        self.assertNotEqual(GENE_GAIN_SCALE.digest(), widened.digest())
        self.assertEqual(GENE_GAIN_SCALE.digest(), reworded.digest())


class AdaptationSpaceTests(unittest.TestCase):
    def test_every_default_gene_range_contains_its_neutral_value(self) -> None:
        for gene in DEFAULT_ADAPTATION_SPACE.genes:
            neutral = GENE_NEUTRAL_VALUES[gene.name]
            self.assertLessEqual(gene.low, neutral)
            self.assertLessEqual(neutral, gene.high)

    def test_a_range_excluding_its_neutral_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            AdaptationSpace(
                (
                    AdaptationGene(
                        name="gain_scale",
                        low=2.0,
                        high=3.0,
                        unit="dimensionless",
                        rationale="excludes the no-op on purpose",
                    ),
                )
            )
        self.assertIn("neutral", str(caught.exception))

    def test_a_gene_with_no_declared_neutral_value_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            AdaptationSpace(
                (
                    AdaptationGene(
                        name="undeclared_knob",
                        low=0.0,
                        high=1.0,
                        unit="dimensionless",
                        rationale="nobody has said what leaving it alone is",
                    ),
                )
            )

    def test_an_empty_space_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationSpace(())

    def test_a_gene_declared_twice_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationSpace((GENE_GAIN_SCALE, GENE_GAIN_SCALE))

    def test_the_identity_is_the_exact_no_op(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        self.assertEqual(identity.origin, ORIGIN_ROOT)
        self.assertIsNone(identity.parent_digest)
        for gene in DEFAULT_ADAPTATION_SPACE.genes:
            self.assertEqual(
                identity.value(gene.name), GENE_NEUTRAL_VALUES[gene.name]
            )

    def test_admit_refuses_an_unrecognised_gene(self) -> None:
        values = dict(GENE_NEUTRAL_VALUES)
        values["turbo"] = 1.0
        with self.assertRaises(KeyError) as caught:
            DEFAULT_ADAPTATION_SPACE.admit(values)
        self.assertIn("turbo", str(caught.exception))

    def test_admit_refuses_a_proposal_missing_a_gene(self) -> None:
        values = dict(GENE_NEUTRAL_VALUES)
        values.pop(GENE_BIAS_RAD.name)
        with self.assertRaises(KeyError) as caught:
            DEFAULT_ADAPTATION_SPACE.admit(values)
        self.assertIn(GENE_BIAS_RAD.name, str(caught.exception))

    def test_admit_clamps_an_out_of_range_value(self) -> None:
        values = dict(GENE_NEUTRAL_VALUES)
        values[GENE_GAIN_SCALE.name] = 99.0
        candidate = DEFAULT_ADAPTATION_SPACE.admit(values)
        self.assertEqual(candidate.origin, ORIGIN_PROPOSAL)
        self.assertEqual(
            candidate.value(GENE_GAIN_SCALE.name), GENE_GAIN_SCALE.high
        )

    def test_mutation_stays_in_range_and_records_its_parent(self) -> None:
        parent = DEFAULT_ADAPTATION_SPACE.identity()
        generator = random.Random(11)
        for _ in range(100):
            child = DEFAULT_ADAPTATION_SPACE.mutate(parent, generator)
            self.assertEqual(child.origin, ORIGIN_MUTATION)
            self.assertEqual(child.parent_digest, parent.digest())
            for gene in DEFAULT_ADAPTATION_SPACE.genes:
                value = child.value(gene.name)
                self.assertGreaterEqual(value, gene.low)
                self.assertLessEqual(value, gene.high)
            parent = child

    def test_mutation_is_reproducible_from_its_seed(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        first = DEFAULT_ADAPTATION_SPACE.mutate(identity, random.Random(3))
        second = DEFAULT_ADAPTATION_SPACE.mutate(identity, random.Random(3))
        self.assertEqual(first.digest(), second.digest())

    def test_a_degenerate_mutation_scale_is_rejected(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        with self.assertRaises(ValueError):
            DEFAULT_ADAPTATION_SPACE.mutate(
                identity, random.Random(0), scale=0.0
            )
        with self.assertRaises(ValueError):
            DEFAULT_ADAPTATION_SPACE.mutate(
                identity, random.Random(0), scale=2.0
            )

    def test_mutating_a_foreign_candidate_is_refused(self) -> None:
        foreign = AdaptationCandidate(
            values={"turbo": 1.0}, origin=ORIGIN_PROPOSAL
        )
        with self.assertRaises(KeyError):
            DEFAULT_ADAPTATION_SPACE.mutate(foreign, random.Random(0))

    def test_the_space_digest_tracks_the_declared_ranges(self) -> None:
        same = AdaptationSpace(DEFAULT_ADAPTATION_SPACE.genes)
        self.assertEqual(
            DEFAULT_ADAPTATION_SPACE.digest(), same.digest()
        )
        widened = AdaptationSpace(
            (
                AdaptationGene(
                    name=GENE_GAIN_SCALE.name,
                    low=GENE_GAIN_SCALE.low,
                    high=GENE_GAIN_SCALE.high + 0.5,
                    unit=GENE_GAIN_SCALE.unit,
                    rationale=GENE_GAIN_SCALE.rationale,
                ),
            )
            + DEFAULT_ADAPTATION_SPACE.genes[1:]
        )
        self.assertNotEqual(
            DEFAULT_ADAPTATION_SPACE.digest(), widened.digest()
        )


class AdaptationCandidateTests(unittest.TestCase):
    def test_the_digest_is_the_values_alone(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        relabelled = AdaptationCandidate(
            values=dict(identity.values),
            origin=ORIGIN_MUTATION,
            parent_digest="somewhere",
        )
        self.assertEqual(identity.digest(), relabelled.digest())

    def test_a_mutation_without_a_parent_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            AdaptationCandidate(
                values=dict(GENE_NEUTRAL_VALUES), origin=ORIGIN_MUTATION
            )
        self.assertIn("lineage", str(caught.exception))

    def test_an_unknown_origin_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationCandidate(
                values=dict(GENE_NEUTRAL_VALUES), origin="vibes"
            )

    def test_a_non_finite_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _candidate(gain_scale=float("inf"))

    def test_reading_an_absent_gene_is_refused(self) -> None:
        candidate = AdaptationCandidate(
            values={"turbo": 1.0}, origin=ORIGIN_PROPOSAL
        )
        with self.assertRaises(KeyError):
            candidate.value(GENE_GAIN_SCALE.name)

    def test_the_contract_records_lineage_and_values(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        child = DEFAULT_ADAPTATION_SPACE.mutate(identity, random.Random(5))
        contract = child.as_contract()
        self.assertEqual(contract["origin"], ORIGIN_MUTATION)
        self.assertEqual(contract["parent_digest"], identity.digest())
        self.assertEqual(contract["digest"], child.digest())
        self.assertEqual(
            set(contract["values"]),  # type: ignore[arg-type]
            {gene.name for gene in DEFAULT_ADAPTATION_SPACE.genes},
        )

    def test_values_cannot_be_mutated_after_construction(self) -> None:
        identity = DEFAULT_ADAPTATION_SPACE.identity()
        with self.assertRaises(TypeError):
            identity.values[GENE_GAIN_SCALE.name] = 9.0  # type: ignore[index]


class HostileCandidateSafetyTests(unittest.TestCase):
    """The candidate may not buy authority it was never granted."""

    def test_a_hostile_rate_scale_cannot_widen_the_step_bound(self) -> None:
        hostile = _candidate(rate_limit_scale=50.0)
        runtime = _runtime(FakeRobot(), hostile)
        self.assertLessEqual(
            runtime.max_step_rad, _EXACT_TRACKING.max_step_rad
        )

    def test_a_hostile_candidate_never_commands_past_the_bound(self) -> None:
        hostile = _candidate(
            rate_limit_scale=1000.0,
            gain_scale=500.0,
            latency_compensation_steps=100.0,
            bias_rad=25.0,
            settle_gain=100.0,
        )
        robot = FakeRobot()
        runtime = _running(robot, hostile)
        for _ in range(40):
            runtime.step()

        previous = (0.0, 0.0)
        for command in robot.commands:
            for before, after in zip(previous, command):
                self.assertLessEqual(
                    abs(after - before),
                    _EXACT_TRACKING.max_step_rad + 1e-12,
                )
            previous = command

    def test_a_hostile_candidate_never_outruns_the_measured_pose(self) -> None:
        hostile = _candidate(
            rate_limit_scale=1000.0,
            gain_scale=500.0,
            latency_compensation_steps=100.0,
        )
        robot = StuckRobot()
        runtime = _running(robot, hostile)
        _step_until_settled(runtime, 30)
        for command in robot.commands:
            for value in command:
                self.assertLessEqual(
                    abs(value), _EXACT_TRACKING.max_lead_rad + 1e-12
                )

    def test_a_hostile_smoothing_weight_cannot_freeze_the_ramp(self) -> None:
        hostile = _candidate(smoothing_alpha=1.0)
        robot = FakeRobot()
        runtime = _running(robot, hostile)
        for _ in range(5):
            runtime.step()
        self.assertGreater(robot.positions[0], 0.0)

    def test_a_hostile_rate_scale_cannot_invert_the_command(self) -> None:
        hostile = _candidate(rate_limit_scale=-5.0)
        robot = FakeRobot()
        runtime = _running(robot, hostile)
        self.assertGreater(runtime.max_step_rad, 0.0)
        runtime.step()
        self.assertGreaterEqual(robot.positions[0], 0.0)

    def test_a_calibration_outside_the_envelope_is_refused(self) -> None:
        too_fast = CommandRateCalibration(
            commanded_rate_rps=1.5,
            peak_joint_velocity_rps=3.0,
            control_frequency_hz=30.0,
            measured_on="FakeRobot",
        )
        with self.assertRaises(ValueError) as caught:
            _runtime(
                FakeRobot(),
                DEFAULT_ADAPTATION_SPACE.identity(),
                command_rate=too_fast,
            )
        self.assertIn("no adaptation", str(caught.exception))

    def test_an_unreachable_goal_tolerance_is_refused(self) -> None:
        drooping = CommandRateCalibration(
            commanded_rate_rps=1.5,
            peak_joint_velocity_rps=1.5,
            control_frequency_hz=30.0,
            measured_on="FakeRobot",
            settled_error_rad=0.02,
        )
        with self.assertRaises(ValueError) as caught:
            _runtime(
                FakeRobot(),
                DEFAULT_ADAPTATION_SPACE.identity(),
                goal=_goal(tolerance_rad=0.005),
                command_rate=drooping,
            )
        self.assertIn("scoring the tolerance", str(caught.exception))


class IdentityEquivalenceTests(unittest.TestCase):
    """The control condition has to be the control, not an approximation."""

    def test_the_identity_commands_what_the_deterministic_runtime_does(
        self,
    ) -> None:
        goal = _goal()
        adapted_robot = FakeRobot()
        adapted = _runtime(
            adapted_robot, DEFAULT_ADAPTATION_SPACE.identity(), goal=goal
        )
        baseline_robot = FakeRobot()
        baseline = DeterministicJointRuntime(
            robot=baseline_robot,
            goals=(goal,),
            command_rate=_EXACT_TRACKING,
            envelope=_ENVELOPE,
        )

        adapted.start(_selection())
        baseline.start(_selection())
        for _ in range(30):
            adapted_step = adapted.step()
            baseline_step = baseline.step()
            if adapted_step.complete or baseline_step.complete:
                break
        self.assertEqual(adapted_robot.commands, baseline_robot.commands)
        self.assertEqual(adapted.postconditions(), baseline.postconditions())

    def test_the_identity_reaches_the_goal(self) -> None:
        robot = FakeRobot()
        runtime = _running(robot, DEFAULT_ADAPTATION_SPACE.identity())
        for _ in range(60):
            if runtime.step().complete:
                break
        self.assertEqual(runtime.postconditions(), {"at_home_pose": True})


class AppliedEffectTests(unittest.TestCase):
    """Every gene has to actually do the thing its rationale claims."""

    def test_bias_shifts_the_pose_the_robot_settles_on(self) -> None:
        robot = FakeRobot()
        runtime = _running(robot, _candidate(bias_rad=0.1))
        _step_until_settled(runtime, 200)
        self.assertAlmostEqual(robot.positions[0], 0.6, places=6)
        self.assertAlmostEqual(robot.positions[1], -0.4, places=6)

    def test_a_tighter_rate_scale_takes_more_steps(self) -> None:
        fast = FakeRobot()
        slow = FakeRobot()
        fast_runtime = _running(fast, DEFAULT_ADAPTATION_SPACE.identity())
        slow_runtime = _running(slow, _candidate(rate_limit_scale=0.25))
        fast_steps = 0
        while fast_steps < 200 and not fast_runtime.step().complete:
            fast_steps += 1
        slow_steps = 0
        while slow_steps < 200 and not slow_runtime.step().complete:
            slow_steps += 1
        self.assertGreater(slow_steps, fast_steps)

    def test_a_deadband_can_suppress_the_final_approach(self) -> None:
        robot = FakeRobot(positions=(0.44, -0.5))
        runtime = _running(
            robot,
            _candidate(deadband_rad=0.02, rate_limit_scale=0.25),
            goal=_goal(tolerance_rad=0.01),
        )
        _step_until_settled(runtime, 50)
        # The deadband forbids the last few milliradians, so the goal is never
        # verified even though nothing failed physically.
        self.assertEqual(runtime.postconditions(), {"at_home_pose": False})

    def test_smoothing_softens_the_first_step(self) -> None:
        sharp = FakeRobot()
        soft = FakeRobot()
        _running(sharp, DEFAULT_ADAPTATION_SPACE.identity()).step()
        _running(soft, _candidate(smoothing_alpha=0.8)).step()
        self.assertLess(soft.commands[0][0], sharp.commands[0][0])

    def test_latency_compensation_leads_the_ramp(self) -> None:
        robot = StuckRobot()
        led = _running(robot, _candidate(latency_compensation_steps=3.0))
        led.step()
        plain_robot = StuckRobot()
        _running(plain_robot, DEFAULT_ADAPTATION_SPACE.identity()).step()
        self.assertEqual(robot.commands[0], plain_robot.commands[0])

    def test_settle_gain_only_acts_inside_the_tolerance_band(self) -> None:
        far = FakeRobot()
        far_settled = FakeRobot()
        _running(far, DEFAULT_ADAPTATION_SPACE.identity()).step()
        _running(far_settled, _candidate(settle_gain=0.25)).step()
        self.assertEqual(far.commands[0], far_settled.commands[0])

        near_goal = _goal(target_joint_positions_rad=(0.005, -0.005))
        near = FakeRobot()
        _running(
            near, _candidate(settle_gain=0.25), goal=near_goal
        ).step()
        self.assertLess(near.commands[0][0], 0.005)

    def test_gain_scale_shapes_the_approach_not_the_bound(self) -> None:
        robot = FakeRobot(positions=(0.49, -0.49))
        runtime = _running(robot, _candidate(gain_scale=0.5))
        runtime.step()
        self.assertLess(robot.commands[0][0], 0.5)


class RuntimeDisciplineTests(unittest.TestCase):
    """Interchangeable with the deterministic runtime means same discipline."""

    def test_starting_twice_is_refused(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        runtime.start(_selection())
        with self.assertRaises(RuntimeError):
            runtime.start(_selection())

    def test_stepping_before_starting_is_refused(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        with self.assertRaises(RuntimeError) as caught:
            runtime.step()
        self.assertIn("before start", str(caught.exception))

    def test_stepping_after_an_abort_is_refused(self) -> None:
        robot = FakeRobot()
        runtime = _runtime(robot, DEFAULT_ADAPTATION_SPACE.identity())
        runtime.start(_selection())
        runtime.step()
        runtime.abort(AbortDirective(cause=ABORT_HUMAN_STOP, detail="stop"))
        self.assertEqual(robot.holds, 1)
        with self.assertRaises(RuntimeError):
            runtime.step()

    def test_stepping_after_completion_is_refused(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        runtime.start(_selection())
        for _ in range(60):
            if runtime.step().complete:
                break
        with self.assertRaises(RuntimeError):
            runtime.step()

    def test_an_abort_falsifies_the_postconditions(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        runtime.start(_selection())
        for _ in range(60):
            if runtime.step().complete:
                break
        runtime.abort(AbortDirective(cause=ABORT_HUMAN_STOP, detail="stop"))
        self.assertEqual(runtime.postconditions(), {"at_home_pose": False})

    def test_postconditions_before_starting_claim_nothing(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        self.assertEqual(runtime.postconditions(), {})

    def test_an_unrecognised_selection_is_refused(self) -> None:
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        with self.assertRaises(KeyError):
            runtime.start(_selection("wave@3"))

    def test_a_width_mismatch_is_refused(self) -> None:
        runtime = _runtime(
            FakeRobot(positions=(0.0, 0.0, 0.0)),
            DEFAULT_ADAPTATION_SPACE.identity(),
        )
        with self.assertRaises(ValueError):
            runtime.start(_selection())

    def test_observing_commands_no_motion(self) -> None:
        robot = FakeRobot()
        runtime = _runtime(robot, DEFAULT_ADAPTATION_SPACE.identity())
        runtime.observe()
        self.assertEqual(robot.commands, [])

    def test_a_source_may_finish_without_the_goal_being_reached(self) -> None:
        class GivesUp:
            def reset(self) -> None:
                pass

            def propose(self, state, elapsed_s):
                return (0.5, -0.5)

            def finished(self, state) -> bool:
                return True

        goal = _goal()
        runtime = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity(),
                           goal=goal, source=GivesUp())
        runtime.start(_selection())
        step = runtime.step()
        self.assertTrue(step.complete)
        self.assertEqual(runtime.postconditions(), {"at_home_pose": False})


class RequiredDurationTests(unittest.TestCase):
    def test_a_reached_goal_needs_no_time(self) -> None:
        runtime = _runtime(
            FakeRobot(positions=(0.5, -0.5)),
            DEFAULT_ADAPTATION_SPACE.identity(),
        )
        self.assertEqual(runtime.required_duration_s(_selection()), 0.0)

    def test_a_throttled_candidate_needs_longer(self) -> None:
        nominal = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        throttled = _runtime(FakeRobot(), _candidate(rate_limit_scale=0.25))
        self.assertGreater(
            throttled.required_duration_s(_selection()),
            nominal.required_duration_s(_selection()),
        )

    def test_a_smoothed_candidate_needs_longer(self) -> None:
        nominal = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        smoothed = _runtime(FakeRobot(), _candidate(smoothing_alpha=0.8))
        self.assertGreater(
            smoothed.required_duration_s(_selection()),
            nominal.required_duration_s(_selection()),
        )

    def test_the_estimate_accounts_for_the_bias(self) -> None:
        nominal = _runtime(FakeRobot(), DEFAULT_ADAPTATION_SPACE.identity())
        biased = _runtime(FakeRobot(), _candidate(bias_rad=0.15))
        self.assertGreater(
            biased.required_duration_s(_selection()),
            nominal.required_duration_s(_selection()),
        )


class GoalActionSourceTests(unittest.TestCase):
    def test_it_proposes_the_goal_pose(self) -> None:
        goal = _goal()
        source = GoalActionSource(goal)
        state = FakeRobot().read_state()
        self.assertEqual(
            tuple(source.propose(state, 0.0)),
            goal.target_joint_positions_rad,
        )
        self.assertFalse(source.finished(state))

    def test_it_reports_finished_once_the_pose_is_reached(self) -> None:
        source = GoalActionSource(_goal())
        state = FakeRobot(positions=(0.5, -0.5)).read_state()
        self.assertTrue(source.finished(state))


if __name__ == "__main__":
    unittest.main()
