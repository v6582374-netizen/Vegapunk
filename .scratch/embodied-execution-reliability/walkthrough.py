"""最短上手路径：不接真机，走完整个治理循环，看它在哪里拒绝你。"""
from datetime import datetime, timedelta, timezone

from vegapunk.embodied.admission import (
    STAGE_HARDWARE_SUPERVISED, STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION, STAGE_SHADOW_MODE,
    AdmissionLedger, EvidenceRecord, HumanApproval,
)
from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.loop import ExecutionLoop, RuntimeStep
from vegapunk.embodied.safety import (
    Observation, SafetyEnvelope, SafetySupervisor,
)
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC, PhysicalSkill, SkillRegistry,
)
from vegapunk.embodied.trajectory import TrajectoryLedger

NOW = datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)

# 1) 声明一个技能：确定性的，不需要 VLA checkpoint
skill = PhysicalSkill(
    skill_id="home_arm", revision=1, kind=SKILL_KIND_DETERMINISTIC,
    summary="把手臂收回 home 位姿。",
    parameters=(),
    preconditions=("workspace_clear", "guardian_present"),
    postconditions=("at_home_pose",),
    abort_conditions=("force_exceeded",),
    max_duration_s=5.0, reviewed_by="loongge",
)
registry = SkillRegistry()
registry.register(skill)
print("catalog:", registry.catalog())

# 2) 声明本体。故意留一个未验证字段，看它是否拒绝
embodiment = EmbodimentProfile(
    robot_model="unitree_g1", arm_dof=7, end_effector="dex1_1",
    camera_map={"observation.images.top": "head_rgb"},
    control_frequency_hz=30.0, control_authority="arm_and_gripper",
    state_dim=16, action_dim=16, onboard_image_service=True,
    unverified_fields=("end_effector",),
)

# 3) 一个假 runtime，代替真机
def obs(**kw):
    f = dict(elapsed_s=0.0, age_s=0.05, joint_velocity_rps=(0.0, 0.0),
             end_effector_force_n=1.0, end_effector_position_m=(0.1, 0.0, 0.8),
             guardian_present=True, estop_engaged=False,
             estop_reachable=True, workspace_clear=True)
    f.update(kw)
    return Observation(**f)

class PrintingRuntime:
    def observe(self): return obs()
    def start(self, selection): print("  runtime: 开始运动", selection.skill_version_id)
    def step(self): return RuntimeStep(observation=obs(elapsed_s=1.0), complete=True)
    def abort(self, d): print("  runtime: 被要求停止 ->", d.cause, d.detail)
    def postconditions(self): return {"at_home_pose": True}

loop = ExecutionLoop(
    registry=registry, embodiment=embodiment,
    supervisor=SafetySupervisor(SafetyEnvelope(
        max_duration_s=20.0, max_joint_velocity_rps=1.5,
        max_end_effector_force_n=20.0,
        workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
    )),
    admission=AdmissionLedger(), trajectories=TrajectoryLedger(),
)

selection = registry.select("home_arm", {})
print("\n[第一次尝试：什么证据都没有]")
r = loop.run(selection=selection, runtime=PrintingRuntime(), run_id="r1",
             stage=STAGE_HARDWARE_SUPERVISED, now=NOW, approval=None)
print(" outcome:", r.outcome)
for f in r.trajectory.findings:
    print("  拒绝理由:", f)

# 4) 补齐：验证本体 + 逐级录入证据 + 人类批准
embodiment = EmbodimentProfile(
    robot_model="unitree_g1", arm_dof=7, end_effector="dex1_1",
    camera_map={"observation.images.top": "head_rgb"},
    control_frequency_hz=30.0, control_authority="arm_and_gripper",
    state_dim=16, action_dim=16, onboard_image_service=True,
)
admission = AdmissionLedger()
for stage in (STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY, STAGE_SHADOW_MODE):
    admission.record(EvidenceRecord(
        stage=stage, skill_version_id=skill.version_id,
        embodiment_digest=embodiment.digest(), policy_digest=None,
        attempts=20, successes=20, safety_violations=0,
        recorded_at=NOW - timedelta(days=1),
    ))

trajectories = TrajectoryLedger()
loop = ExecutionLoop(
    registry=registry, embodiment=embodiment,
    supervisor=SafetySupervisor(SafetyEnvelope(
        max_duration_s=20.0, max_joint_velocity_rps=1.5,
        max_end_effector_force_n=20.0,
        workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
    )),
    admission=admission, trajectories=trajectories,
)
approval = HumanApproval(
    skill_version_id=skill.version_id,
    embodiment_digest=embodiment.digest(), policy_digest=None,
    approver="loongge", approved_at=NOW - timedelta(minutes=10),
    statement="工作区已清空，我在旁边，急停已测试。",
    evidence_digest=admission.evidence_digest(
        skill.version_id, embodiment.digest(), None),
)

print("\n[第二次尝试：证据齐备 + 已批准]")
r = loop.run(selection=selection, runtime=PrintingRuntime(), run_id="r2",
             stage=STAGE_HARDWARE_SUPERVISED, now=NOW, approval=approval)
print(" outcome:", r.outcome, "| succeeded:", r.succeeded)

print("\n[运行中有人按下急停]")
class EstopRuntime(PrintingRuntime):
    def step(self): return RuntimeStep(observation=obs(elapsed_s=1.0, estop_engaged=True))
r = loop.run(selection=selection, runtime=EstopRuntime(), run_id="r3",
             stage=STAGE_HARDWARE_SUPERVISED, now=NOW, approval=approval)
print(" outcome:", r.outcome, "| cause:", r.trajectory.abort_cause)

print("\n[中止之后立刻重试同一配置]")
r = loop.run(selection=selection, runtime=PrintingRuntime(), run_id="r4",
             stage=STAGE_HARDWARE_SUPERVISED, now=NOW, approval=approval)
print(" outcome:", r.outcome)
for f in r.trajectory.findings:
    print("  拒绝理由:", f)
