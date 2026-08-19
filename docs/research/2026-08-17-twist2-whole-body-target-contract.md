# TWIST2 全身跟踪目标契约（本机 G1 / BrainCo Revo2）

日期：2026-08-17
结论用途：为“具身仪器操作”确定学习策略唯一可越过的策略—执行边界。

## 决策

把 TWIST2 视为一个**低层全身运动跟踪器**，而不是导航器或直接执行器。上游 VLA/任务策略唯一可以发布的是一份有版本、可过期、原子提交的 `TrackerTarget`；目标桥是唯一能把它展开成 TWIST2 的 Redis 输入和 BrainCo 手命令的组件。策略不得直接访问 Unitree 低层命令、手的 DDS 接口或颈部控制器。

当前已接通且与随仓 ONNX 一致的最小目标是：`body[35] + left_hand[6] + right_hand[6]`。颈部 `neck[2]` 是一个**发布了但未接到本机执行器**的预留通道，不能纳入第一阶段闭环成功条件。

```text
VLA / task policy
       │ publishes one atomic, timestamped TrackerTarget
       ▼
Target bridge ── validates freshness, shape, bounds, authority
       │
       ├── body[35] ──► TWIST2 learned tracker ──► G1 29-joint PD target
       └── hand[6]+hand[6] ──────────────────────► BrainCo Revo2 commands

Manual / hardware emergency stop is outside this data plane and has priority.
```

`TrackerTarget` is an architectural contract recommended here; it is not an already-existing TWIST2 class. The current four independent Redis keys are implementation detail to be hidden behind that bridge.

## Exact target accepted by the tracker

The active deployment expects `action_body_unitree_g1_with_hands` to JSON-decode to a 35-element vector. Its element order is exactly:

| Slice | Meaning | Frame / unit |
| --- | --- | --- |
| `0:2` | desired root linear velocity `v_x, v_y` | robot-root local frame; source produces finite-difference position per second |
| `2` | desired root height `z` | source motion/retarget coordinate system (`0.8` in the supplied stand target) |
| `3:5` | desired root roll, pitch | radians |
| `5` | desired root yaw angular velocity | robot-root local frame, rad/s |
| `6:35` | desired positions for the G1's 29 controlled body joints | radians; order is legs (6+6), waist (3), left arm (7), right arm (7) |

The training configuration, online PICO retargeter, offline motion server and real deployment agree on this layout.[^student-layout][^teleop-layout][^offline-layout][^g1-joint-order] It has no global `x,y`, yaw angle, map frame, object pose, end-effector pose, contact force, or navigation-goal field. In particular, it is a local kinodynamic intent plus a full-body reference pose, not a route or navigation API.

The real server puts the target together with 92 proprioceptive values, ten prior 127-value observations, and one duplicate of the current target as the “future” target. That is `127 × 11 + 35 = 1432` floats. The shipped `twist2_1017_20k.onnx` has input `float32[batch_size,1432]` and output `float32[batch_size,29]` (locally inspected; SHA-256 `2d1fb3a31e4e967f70ecfefc3ad1e7b2ac491677068b89f60b565a94e7735061`). The source comment saying “1402” is arithmetic drift, not the value computed or expected.[^real-input][^future-config]

The 29 ONNX outputs are clipped to `[-10,10]`, scaled by `0.5`, offset by the G1 default pose, and sent as G1 position-PD targets with the configured `kp`, `kd`, zero velocity target and zero feed-forward torque.[^real-actuation][^g1-pd][^g1-config] Therefore an upstream policy must publish a *motion reference* in the 35-value form; it must **not** publish the ONNX's 29 residual actions or raw motor torques.

### BrainCo Revo2 hand channels

With `--use_hand` (the supplied real launch script enables it), the real server reads two action keys, truncates each to six values, and sends them through `Brainco_Hand_Controller.ctrl_dual_hand`.[^real-hands][^real-launch] The exact order on both hands is:

```text
[thumb, thumb_aux, index, middle, ring, pinky]
```

They are position targets in the BrainCo hand's joint coordinate, with local source ranges of `0` to `[1.52, 1.05, 1.47, 1.47, 1.47, 1.47]`. The controller also hard-codes velocity targets `[0.2, 1.0, 0.2, 0.2, 0.2, 0.2]`; the policy does not own those velocities.[^brainco]

The existing teleop producer and several historical episodes contain seven-value hand arrays, whereas the current real BrainCo path slices to six. The sole supported policy contract is six values per hand; accepting seven would preserve an obsolete producer ambiguity instead of an embodiment contract.[^teleop-hands][^recorded-episodes]

### Neck channel: present at the publisher, absent at actuation

`action_neck_unitree_g1_with_hands` is a two-value `[yaw, pitch]` target. The PICO teleop source derives it from human head orientation and applies a configurable scale (default `1.5`).[^teleop-neck] The real tracker reads and JSON-decodes this key but does not use the result afterwards; it has no neck wrapper, DDS command, feedback publisher, or onboard service in this checkout.[^real-neck]

The first-party neck document only assigns Dynamixel yaw ID 0 and pitch ID 1, then defers its controller to an unavailable “onboard repo”.[^neck-doc] This makes the neck a dormant integration, not a demonstrated policy-to-hardware channel. Do not expose it to the first policy seam. It can be added later as a separately verified actuator under the same `TrackerTarget` envelope.

## Cadence, feedback, and authority

### Cadence

The real G1 control period is `0.02 s` (50 Hz). The README independently describes expected policy execution at about 50 Hz.[^g1-config][^readme-50hz] The PICO teleop launch asks for 100 Hz, but Redis is last-value storage: the 50 Hz tracker reads only the newest target and does not consume a queue.[^teleop-launch][^real-read]

Thus the policy contract should be:

- Emit target frames at 50 Hz, or faster only if deliberate sample-and-hold is acceptable.
- Include `sequence`, `source_time_ns`, and a bounded `valid_until_ns` in the atomic envelope.
- The target bridge must reject late, malformed, out-of-order, or expired frames before atomically writing the complete actuation target set. The present tracker does none of these checks and does not read `t_action`.[^teleop-write][^real-read]

The demonstration recorder runs at 30 Hz, independently of the 50 Hz control loop; it is for learning data, not a control-clock authority.[^record-launch][^recorder-loop]

### Feedback actually available

At each real tracker cycle the body feedback published to Redis is 34 values:

```text
[imu angular velocity (3), body roll/pitch (2), 29 body joint positions]
```

When hands are enabled, it also publishes six measured positions per Revo2 hand. It reads, but does not publish, neck state. The real path does not publish `t_state` either.[^real-feedback]

This yields the feedback half of the recommended envelope:

```text
TrackerState {
  sequence, state_time_ns,
  body: { angular_velocity[3], roll_pitch[2], joint_position[29] },
  left_hand_position[6], right_hand_position[6],
  applied_target_sequence
}
```

`sequence`, `state_time_ns`, and `applied_target_sequence` must be added by the bridge; they do not exist in the current real tracker. They are the minimum needed to align VLA observations/actions and diagnose target staleness.

### Authority and stop semantics

The real server requires remote `START` to interpolate to its default pose and remote `A` to enter its main loop. Remote `Select` breaks that loop.[^g1-start][^real-stop] The code then calls `env.close()`, whose only visible implementation is `exit()`; no Python-level damping/zero-torque command or target-freshness watchdog is issued.[^g1-close] The documentation's generic damping statement must therefore not be treated as evidence of this check-out's actual stop behavior.[^unitree-doc]

The PICO “emergency stop” kills `sim2real.sh` and a stale filename, `server_low_level_g1_real_future.py`; it does not define an acknowledged stop at the currently launched `server_low_level_g1_real.py` or at the G1/hand transport.[^teleop-estop][^real-launch] Existing Redis values also have no TTL, so a producer failure can leave the last target resident.

Decision: policy authority is **conditional** on an external/manual safety authority. The bridge must provide the automatic dead-man rule (expiry ⇒ safe hold/controlled return) and make any stop observable. It must never rely on Redis persistence, a process kill, or a policy's own “stop” token as the safety mechanism.

## Root motion: what TWIST2 supplies and what it does not

Offline TWIST2 turns a `.pkl` motion's root pose/velocity and 29 joint positions into the 35-value target at `0.02 s`. Online it retargets PICO whole-body data to G1 `qpos`, estimates root linear and angular velocities by finite differences, converts them to the root frame, and emits the same 35-value target.[^offline-root][^teleop-layout] The state machine also calculates joystick velocity commands, but no producer path injects those values into the emitted target.[^joystick-dormant]

Consequently, there is no TWIST2 localization, mapping, obstacle avoidance, waypoint following, or vision-to-navigation path to reuse. For the laboratory scenario, a navigation/perception layer must transform “go to the machine's operation stance” into a continuously refreshed local body target. TWIST2 is then responsible only for tracking that target while maintaining balance.

## Episode-record contract and its evidence

The 30 Hz recorder stores one JSON item per sample with:

```text
idx, rgb, t_img,
state_body, state_hand_left, state_hand_right, state_neck, t_state,
action_body, action_hand_left, action_hand_right, action_neck, t_action
```

The writer stores the full item unchanged alongside episode metadata and a text task description.[^recorder-fields][^episode-writer] The real tracker’s optional separate `--record_proprio` log instead stores timestamp, body joint position, reference joint positions, temperature, torque estimate, voltage, and—when enabled—left/right hand position.[^real-proprio]

This checkout contains six local December-2025 episode JSON files. They demonstrate that the image + body + hand action/state recording path has run against the physical instrument scene: all six have 35-value body actions, 34-value body state, six-value hand state, RGB, `t_img`, and `t_action`; an inspected stereo frame visibly contains the laboratory machine and G1 arms.[^recorded-episodes] They do **not** establish successful autonomous navigation, a learned VLA policy, an end-to-end task success label, or a neck loop. In every inspected stored episode, `state_neck` and `t_state` are `null`, directly corroborating the dormant real feedback paths.

The recorder also uses static generic text (“walk ahead and pick a box”), no camera calibration/extrinsics, target sequence, applied action, safety event, task phase, object state, or success/failure label. It is usable as an observation/action trace, but not yet a sufficient training or evaluation contract for the machine-operation task.

## Connected versus merely present

| Capability | Status on this machine | Why it matters for the first loop |
| --- | --- | --- |
| `body[35] → ONNX tracker → G1 29-joint PD` | Source-connected; first-party documentation says physical G1/PICO control is supported; current-machine physical run was not performed for this research | Reuse as the locomotion + whole-body tracking substrate |
| `hand[6]+hand[6] → BrainCo Revo2` | Source-connected in the machine-local BrainCo migration; historical records corroborate six-value hand feedback but do not prove every current hand command | Include from the outset, behind the same target bridge |
| `neck[2]` | Producer and recorder fields exist; no actuation or real feedback consumer in checkout | Exclude from first closed loop |
| PICO/GMR retargeting | First-party documented and code-complete producer | Use as data-collection reference, not as VLA runtime dependency |
| Navigation / semantic goal execution | Absent | Build above the tracker; do not search TWIST2 for it |
| TTL, sequence, acknowledgment, automatic safe stop | Absent | Add at the sole bridge before policy authority |

The checkout is machine-local `master` at `39a6b6c6e832915eeb0e375f9142199477371e0e` with uncommitted BrainCo-related edits. Findings about Revo2 are intentionally about this installed embodiment, not a claim about an immutable upstream release.

## Sources

All source paths below are relative to `/home/loongge/TWIST2-master`, inspected on 2026-08-17. They are first-party repository source/docs or local data artifacts; no secondary sources were used.

[^student-layout]: `legged_gym/legged_gym/envs/g1/g1_mimic_future.py:244-255`; `legged_gym/legged_gym/envs/g1/g1_mimic_future_config.py:12-35`.
[^teleop-layout]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:82-105`.
[^offline-layout]: `deploy_real/server_motion_lib.py:29-94`.
[^g1-joint-order]: `deploy_real/robot_control/configs/g1.yaml:14-19,44-49`.
[^real-input]: `deploy_real/server_low_level_g1_real.py:123-154,260-273`.
[^future-config]: `legged_gym/legged_gym/envs/g1/g1_mimic_future_config.py:6-35`; `legged_gym/legged_gym/envs/g1/g1_mimic_future.py:321-350`.
[^real-actuation]: `deploy_real/server_low_level_g1_real.py:271-287`.
[^g1-pd]: `deploy_real/robot_control/g1_wrapper.py:135-149`.
[^g1-config]: `deploy_real/robot_control/configs/g1.yaml:1-4,21-31,51-54`.
[^real-hands]: `deploy_real/server_low_level_g1_real.py:249-287`.
[^real-launch]: `sim2real.sh:14-20`.
[^brainco]: `deploy_real/robot_control/brainco_hand_wrapper.py:19-33,82-128,135-149`.
[^teleop-hands]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:297-364,680-704`; `deploy_real/data_utils/params.py:72-154`.
[^recorded-episodes]: `deploy_real/twist2_demonstration/20251227_2028/episode_0004/data.json` and `episode_0007/data.json`; `deploy_real/twist2_demonstration/20251227_2051/episode_0008/data.json`, `episode_0009/data.json`, `episode_0010/data.json`, and `episode_0012/data.json`; `.../20251227_2051/episode_0008/rgb/000000.jpg`.
[^teleop-neck]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:654-704,867-887`.
[^real-neck]: `deploy_real/server_low_level_g1_real.py:233-287`; repository-wide source search of `deploy_real/**/*.py` finds no neck actuator call.
[^neck-doc]: `doc/TWIST2_NECK.md:1-24`.
[^readme-50hz]: `README.md:206-230`.
[^teleop-launch]: `teleop.sh:12-20`.
[^real-read]: `deploy_real/server_low_level_g1_real.py:177-241,260-291`.
[^teleop-write]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:680-704`.
[^record-launch]: `data_record.sh:7-12`.
[^recorder-loop]: `deploy_real/server_data_record.py:76-91,134-213`.
[^real-feedback]: `deploy_real/server_low_level_g1_real.py:199-231`.
[^g1-start]: `deploy_real/robot_control/g1_wrapper.py:84-109`.
[^real-stop]: `deploy_real/server_low_level_g1_real.py:177-197,313-328`.
[^g1-close]: `deploy_real/robot_control/g1_wrapper.py:153-154`.
[^unitree-doc]: `doc/unitree_g1.md:68-86`.
[^teleop-estop]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:397-420`.
[^offline-root]: `deploy_real/server_motion_lib.py:23-94,120-146,206-246`.
[^joystick-dormant]: `deploy_real/xrobot_teleop_to_robot_w_hand.py:139-141,239-252,779-833`.
[^recorder-fields]: `deploy_real/server_data_record.py:134-194`.
[^episode-writer]: `deploy_real/data_utils/episode_writer.py:52-67,125-206`.
[^real-proprio]: `deploy_real/server_low_level_g1_real.py:293-323`.
