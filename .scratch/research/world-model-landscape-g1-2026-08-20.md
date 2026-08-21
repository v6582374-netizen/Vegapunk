# 面向 Unitree G1 + BrainCo Revo2 操作任务的开放世界模型研究

- 日期：2026-08-20
- 范围：固定操作台上的按钮、开盖、抓杯、倾倒（杯中无真实液体）、放杯、关盖；第一版不把行走作为前提。
- 已知条件：G1、BrainCo Revo2 末端、头部与腕部相机、约 148 段 VR 示教数据、已有定点操作链路。
- 证据规则：仅引用论文、模型作者/机构的官方仓库、官方模型页或官方文档。本文将**已由来源明确说明的事实**与**针对本项目的工程判断**分开。
- 结论性质：选型与架构研究；不修改代码、不安装模型、不开始训练。

---

## 0. 先给结论

没有一个公开模型可以被诚实地称为“下载后直接让 **Unitree G1 + BrainCo Revo2** 在本实验台上闭环操作”的现成答案。

原因不是模型不够大，而是三个接口并未自然对齐：

```text
公开模型的动作表示
≠ G1 身体 / Revo2 末端的可执行控制表示
≠ 本操作台上的相机、标定、接触与失败分布
```

因此，第一版应采用**职责分离**，而不是赌一个“万能世界模型”：

```text
观察（头部/腕部图像 + 机器人状态）
          │
          ▼
动作提议器：现有定点技能 / 后续 VLA
          │  产生少量、短时、安全的候选动作片段
          ▼
动作条件世界模型：预测每个候选的后果
          │
          ▼
Harness 评分器：判断预测中是否更接近本步目标
          │
          ▼
选一个候选 → 真机执行短片段 → 真实观察与预测比较
          │
          └────────── 更新下一轮候选与模型评估 ──────────┘
```

其中：

- **世界模型**不是电机控制器；其任务是回答“若执行候选动作，下一小段世界可能怎样变化”。
- **VLA/策略**不是反馈闭环；其任务是提出动作。
- **Harness**才是闭环主体；它负责产生候选、用预测比较候选、让真机给出事实、记录偏差并决定下一轮。
- 真机反馈不可被“模型想象”替代。世界模型只降低试错成本；真机观察才是对预测的校正信号。

### 明确 shortlist

| 角色 | 第一候选 | 为什么进入 shortlist | 不应被误解为 |
|---|---|---|---|
| **最快的 G1 工程基线** | **UnifoLM-WMA-0** | Unitree 官方已公开 G1 数据、训练、交互仿真和 `g1_dex1` 真机部署链路 | 对 Revo2 开箱即用，或已经证明可准确预测本操作台 |
| **最值得先验收的预测器** | **OSCAR-2B** | 以动作骨架而非固定关节编号条件化，明确用于跨 embodiment 的动作条件视频预测和策略评估；公开推理权重，单卡推理门槛明确 | 实时控制器；它目前约一分钟才生成一个示例 rollout |
| **Harness 的结构蓝图** | **Ctrl-World + VLAW** | 公开地实现“VLA 在世界模型内 rollout → 真机失败数据校正世界模型 → 合成 rollout 改进策略”的循环 | 可直接迁移到 G1/Revo2 的模型组件；其官方动作空间为 DROID 7D |
| **后续动作策略候选** | **NVIDIA GR00T N1.7** | 官方含 `REAL_G1`、`NEW_EMBODIMENT`、远程推理和 G1+GEAR-SONIC 全身工作流 | 世界模型或任务结果预测器；Revo2 仍需自定义 embodiment |
| **更强但更重的备选预测器** | **Genie Envisioner GE-Sim / V-JEPA 2-AC** | 前者有多视角动作条件神经模拟器；后者有 latent 预测与 CEM 规划、Franka 真机证据 | 与 Unitree G1/Revo2 已适配 |
| **战略观察，不作为第一版依赖** | **Cosmos 3、DW05、ω-0** | Cosmos 3 已有 forward-dynamics/policy/action 接口；DW05 尝试 video/action/value；ω-0 概念上是 humanoid world-action model | 已具备本项目可验证的 G1+Revo2 部署路径 |

**建议的起步顺序**：先用同一批留出 episode 让 **WMA simulation mode** 与 **OSCAR-2B** 做“真实动作重放 → 预测后续”的离线验收；只有能预测按钮、杯子、盖子和手部局部变化的一方，才有资格接入真机候选选择。不要先租大算力、也不要先全量微调任一大模型。

---

## 1. 三个经常被混淆的东西

| 名称 | 输入 | 输出 | 在本项目中的正确职责 | 代表 |
|---|---|---|---|---|
| **世界模型（world model）** | 当前观察 + 候选动作 | 未来图像、未来 latent、未来状态或其分布 | 预测后果、比较候选、发现预测与真机的偏差 | WMA simulation mode、OSCAR、V-JEPA 2-AC、GE-Sim、Ctrl-World、Cosmos forward dynamics |
| **VLA / 策略（policy）** | 图像 + 语言 + 可选状态 | 动作或动作 chunk | 提出“可以试什么” | GR00T、π0/π0.5、OpenVLA、GE-Act、WMA decision-making |
| **仿真器（simulator）** | 场景物理状态 + 控制 | 物理状态、接触、传感器数据 | 做显式物理训练/安全验证；需要建模 G1、Revo2、操作台和相机 | Isaac Sim / Isaac Lab（物理）；GE-Sim、UniSim、Genie 是神经/生成式模拟范式，不能等同于物理仿真 |

一个模型同时能输出视频和动作，仍不自动成为可信闭环系统。可信闭环至少还需要：

1. **规范动作适配器**：将模型世界中的动作转换为 G1/Revo2 的安全控制命令；
2. **任务状态/成功评分器**：从真实和预测观察中读出按钮是否按到、杯是否被握住、是否完成倾倒姿态、盖子是否到位；
3. **短执行 horizon**：每次只执行足以获得新信息的短片段，不把长动作 chunk 不经观察地全部下发；
4. **真机校正集**：记录“预测成功而真机失败”的反例，避免世界模型只学会乐观想象；
5. **安全闸门**：动作范围、速度、碰撞/力限制和可中止机制全部在模型外。

---

## 2. 判断标准：不是比较宣传片，而是比较能否进入 Harness

对每个候选使用同一组问题：

1. **动作条件性**：是否真的使用候选动作预测后果？
2. **预测对象**：视频、latent 还是明确物理状态？视频好看不代表接触正确。
3. **动作接口距离**：官方动作空间与 G1+Revo2 的距离是多少？
4. **真机证据**：有无真实机器人实验或部署代码？是否就是 Unitree G1？是否就是 Revo2？
5. **开放程度**：权重、训练代码、推理代码、数据接口是否都公开？
6. **闭环可用性**：能否做多步 rollout、候选比较及真机预测误差评估？
7. **计算与时延**：它是离线“想象器”还是可承担在线重规划的组件？

本项目最重要的验收不是 FVD、单张视频质量或训练 loss，而是下面两个量：

```text
A. 反事实排序：模型能否把“较可能完成当前子任务”的候选排在前面？
B. 校准误差：模型说会成功的动作，在真机上到底多常成功？
```

如果 A、B 不能通过，模型只能做演示视频，不能承担 Harness 中的决策职责。

---

## 3. 世界模型 / 世界行动模型候选

### 3.1 UnifoLM-WMA-0（Unitree）——G1 关联最直接，但不是无条件首选

**官方事实**

- 官方定位为 World-Model–Action 架构：世界模型既可作交互式 simulation engine，也可通过 action head 进行 decision-making。
- 官方公开训练、推理、checkpoint 和 Unitree 部署；模型页含 `Base` 与在 Unitree 数据上 post-train 的 `Dual` checkpoint。
- 官方真实机器人示例包括 Unitree G1；部署客户端示例使用 `--robot_type "g1_dex1"`。
- 自有数据需先转为 **LeRobot V2.1**；官方训练说明写明训练只支持**主视角相机**，多视角必须在 CSV 中移除。
- 默认假定最大 DoF 为 16；超过 16 需改 `agent_state_dim` 与 `agent_action_dim`。因此当前 26D Revo2 相关表示不是现成兼容。
- 官方训练序列为：视频世界模型 fine-tune → decision-making post-train → simulation-mode post-train。

**对本项目的判断**

- 它是唯一一个同时拥有**Unitree G1 真实部署链路**和**世界模型交互模式**的现成基线，因此不能简单排除。
- 但它的已公开真机路径是 `G1 + Dex1`，不是 `G1 + BrainCo Revo2`；相机限制也与我们拥有腕部相机的价值冲突。
- WMA 的正确角色应是**对照基线**：验证 Unitree 预训练先验是否能通过动作/观察适配器预测本实验台局部后果，而不是默认全量训练 4B 级模型。
- 先前的 action-head-only 小规模训练不能证明 simulation mode 已训练完成，也不能证明世界模型已学会本任务的物理后果。

**硬件事实与边界**

- 官方 README 没有给出一个可据此承诺的最低训练显存。不要把本机 action-head-only 的峰值推导为完整 WMA 训练预算。
- 26D、双相机、simulation mode 都会改变现有训练成本；需要在数据适配后用实际配置测量。

**一手来源**

- [官方仓库 README](https://github.com/unitreerobotics/unifolm-world-model-action)
- [官方部署说明](https://github.com/unitreerobotics/unifolm-world-model-action/tree/main/unitree_deploy)

---

### 3.2 OSCAR-2B（2026）——当前最适合作为“候选动作后果预测器”的工程候选

**官方事实**

- OSCAR 是 action-conditioned video world model，基于 Cosmos-Predict2.5-2B fine-tune。
- 它不把动作绑定为某个机器人的固定关节编号，而是使用**2D 运动学骨架渲染**：机器人 state → URDF 正运动学 → 相机投影 → skeleton video。
- 官方例子覆盖 AgiBot G1、AIROA 移动操作、DROID/Franka、KUKA 与人手；发布了与 RoboArena 真机策略评估配对的真实/世界模型 rollout。
- 代码、推理 CLI、公开权重和数据入口均已发布；代码为 Apache-2.0。README 写明权重约 5GB、建议推理显存至少 24GB。
- 官方示例在单张 Blackwell GPU 上生成 81 帧 480×640 rollout 的墙钟时间约一分钟（预热后）。

**数据/接口**

```text
首帧 RGB + 文字任务描述 + 由动作序列渲染出的 skeleton video
                         ↓
                    预测未来视频
```

要适配 Revo2，必须提供：Revo2/G1 的运动学链、要被渲染的关键点、相机内外参，以及把候选动作变成可投影的姿态序列的适配器。

**对本项目的判断**

- 它最匹配 Harness 的“候选动作 → 未来视觉结果 → 比较”的接口，尤其适合从固定操作台视角判断按钮、杯子、盖子等可见后果。
- 它没有 G1/Revo2 的电机执行桥，也不输出动作；它只能是**预测器**，不能取代既有定点技能或 VLA。
- 当前示例时延使其更适合**离线规划/低频实验回合**，不适合 30–50Hz 控制回路。
- 手腕相机是移动相机；官方公开范式依赖骨架与相机投影，必须单独测量其在 egocentric 视角的误差，不能从静态相机 demo 外推。

**结论**：将 OSCAR-2B 作为第一个独立预测器的**离线验收对象**是合理的；将它直接接真机当控制器是不合理的。

**一手来源**

- [官方仓库](https://github.com/wuzy2115/oscar-public)
- [官方论文](https://arxiv.org/abs/2606.04463)
- [官方权重](https://huggingface.co/zywu2115/OSCAR-2B)

---

### 3.3 Genie Envisioner / GE-Sim（AgiBot，2025–2026）——多视角神经模拟器备选

**官方事实**

- Genie Envisioner 包含三个角色：GE-Base 视频基础模型、GE-Act 动作策略、GE-Sim 动作条件神经模拟器；论文明确把 policy learning、evaluation 和 simulation 置于统一视频生成框架中。
- 官方仓库已公开训练/推理代码和 GE-Base、GE-Sim 权重入口。
- 对自定义任务，官方推荐先做 task-specific video adaptation，再做 action post-training。
- 数据接口是 LeRobot 风格：Parquet 的 state/action、视频、多相机 key 和统计量；配置可指定 `absolute` / `delta` / `relative` action 及 joint action space。
- GE-Sim 示例输入包含多帧多视角图像、相机内外参、`.npy` action 序列；其公开 Cosmos-based GE-Sim 权重依赖 Cosmos-Predict2-2B 的 tokenizer/VAE 等组件。
- 官方仓库没有在 README 中发布 Unitree G1 + BrainCo Revo2 的 ready-made adapter 或最低显存承诺。仓库部分代码/数据为 CC BY-NC-SA 4.0，使用前须核验许可是否满足比赛与后续用途。

**对本项目的判断**

- 多视角输入与腕部相机的匹配度优于 WMA 的“仅主视角”限制。
- 但 GE-Sim 的演示接口是以末端位姿、相机参数和动作数组为中心；它没有替我们完成 Revo2 action mapping 与相机标定。
- 它是第二个应做离线预测验收的模型，适合在 OSCAR 的单视角骨架表示无法覆盖腕部视角时使用。
- 因依赖栈和组件更多，它不宜作为第一个“只为证明 Loop 可跑通”的依赖。

**一手来源**

- [官方仓库](https://github.com/AgibotTech/Genie-Envisioner-V1)
- [官方论文](https://arxiv.org/abs/2508.05635)
- [官方 GE-Sim v2 项目页](https://ge-sim-v2.github.io/)

---

### 3.4 V-JEPA 2-AC（Meta，2025）——最符合“latent 预测 + 规划”，但需要重做执行接口

**官方事实**

- V-JEPA 2-AC 是从 V-JEPA 2 post-train 得到的**latent action-conditioned world model**：预测的不是未来像素视频，而是未来视觉表征。
- 论文使用少于 62 小时 DROID 无标注机器人视频进行 action-conditioned post-training，并在两个新实验室的 Franka 上以 image goal 规划完成 reach、grasp、pick-and-place；论文声明该实验未收集这些环境中的数据、未做 task-specific training/reward。
- 官方提供代码、V-JEPA 2-AC checkpoint、DROID post-training config 和 energy-landscape/CEM notebook。
- 官方 DROID 配置使用轨迹目录 CSV、`left_mp4_path`、256px、8 帧、4fps；发布的 notebook 使用 7D Franka pose/action 表示并通过 CEM 搜索动作。
- 官方 action-conditioned training config 是一个大规模参考配置（4 节点 × 每节点 8 task、`mem_per_gpu: 220G`）；它是作者的训练配置，**不是**本项目的最低硬件要求。

**对本项目的判断**

- 它在概念上非常干净：世界模型预测 latent 后果，CEM/MPC 从候选动作中找更接近目标的一个。这正是 Harness 可采用的内部机制。
- 但它不是现成 VLA，不直接下发 Revo2 关节动作，也没有 G1 SDK/手部适配。把 Franka 7D 直接扩成 26D 并不等于得到有效全身/灵巧手模型。
- 由于它输出 latent 而非可视视频，Harness 需要一个明确的 goal/energy 定义；这对“按钮/盖子/杯子状态”可更稳健，也更难调试。

**结论**：最值得保留为“低维/latent 预测与 MPC”研究支线；不作为第一版 G1 集成路径。

**一手来源**

- [官方仓库](https://github.com/facebookresearch/vjepa2)
- [官方论文](https://arxiv.org/abs/2506.09985)
- [官方 DROID post-training config](https://github.com/facebookresearch/vjepa2/blob/main/configs/train/vitg16/droid-256px-8f.yaml)
- [官方 CEM notebook](https://github.com/facebookresearch/vjepa2/blob/main/notebooks/energy_landscape_example.ipynb)

---

### 3.5 NVIDIA Cosmos：Cosmos 3 是当前版本；Predict2.5 仍是许多机器人项目的基础

#### Cosmos 3（2026）

**官方事实**

- NVIDIA 将 Cosmos 3 定位为开放的 omnimodal world model 系列；Generator 可输入 text/vision/sound/action，输出 vision/sound/action；Reasoner 输出文字理解与规划结果。
- 官方提供三档：Super 64B、Nano 16B、Edge 4B；官方推荐硬件依次为 H200/B200/GB200、RTX Pro 6000/H100/B200、Jetson AGX Orin/Thor/RTX Pro 6000。
- 官方 forward dynamics 模式为 `image + action chunk → video`；policy/inverse dynamics 为 `image/video + instruction → action chunk`。
- 官方列出的动作条件 domain 包括单臂 10D（DROID/UR/Fractal/Bridge/UMI）、双臂 20D 与 **AgiBot humanoid 29D**。这不是 Unitree G1+Revo2 的现成 domain。
- 推理接口接受图像/MP4 与 JSON action array；代码、模型与 Cosmos Framework 训练/服务入口公开，许可为 OpenMDW-1.1。官方明确警告生成结果仍可能有物体变形、3D/物理不准确和 action-state 不一致，安全/物理任务需额外验证。

**对本项目的判断**

- Cosmos 3 是当前最有能力的“基础设施候选”，并非当前最省风险的任务模型。
- 对我们来说，关键问题不是能否输入 26 个数，而是有没有对应 Unitree+Revo2+本操作台的**已训练 action domain**。官方没有给出这一点。
- `Cosmos3-Edge/Nano-Policy-DROID` 的 policy 也不应被误认为 G1 末端策略。它们仍是 DROID domain 的权重。
- 若要使用，应将其定位为未来的 backbone：先用小规模适配证明 26D/reduced canonical action 的预测校准，再考虑系统性 post-training。

#### Cosmos-Predict2.5（2025）

- Predict2.5 已不再是 NVIDIA 推荐的新主线，但 OSCAR 和 GE-Sim 等公开机器人项目仍在其上构建。
- 官方有 robot/action-conditioned 推理与 post-training 文档；Bridge 风格数据包含视频、EEF pose `[x,y,z,roll,pitch,yaw]`、gripper state/action displacement。
- 该接口再次说明：它解决的是末端动作条件视频预测，不是 G1/Revo2 直接执行。

**一手来源**

- [Cosmos 3 官方仓库](https://github.com/NVIDIA/Cosmos)
- [Cosmos 3 官方技术报告](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf)
- [Predict2.5 官方仓库](https://github.com/nvidia-cosmos/cosmos-predict2.5)
- [Predict2.5 robot/action-conditioned 推理](https://github.com/nvidia-cosmos/cosmos-predict2.5/blob/main/docs/inference_robot_action_cond.md)
- [Predict2.5 action post-training](https://github.com/nvidia-cosmos/cosmos-predict2.5/blob/main/docs/post-training_video2world_action.md)

---

### 3.6 Ctrl-World + VLAW（2025–2026）——不是本项目的直接权重，却是最好的 Loop 参照

**官方事实**

- Ctrl-World 是 action-conditioned、multi-view 的 robot manipulation world model，官方仓库支持 recorded-action replay、键盘交互以及与 π0.5 的 policy-in-the-loop imagination rollout。
- 其公开配置固定 `action_dim = 7`，并以 DROID 为主要数据/动作接口；一次 interaction 在 A100 约 10 秒、H100 约 5 秒。
- 完整 DROID 训练官方使用 1–2 个节点、每节点 8×A100/H100；所以它不是轻量本地基线。
- VLAW 的核心结论不是“世界模型能替代真机”，而是：专家示教缺少失败/接触覆盖时，世界模型会不够可靠；少量真实 rollout 用来校正世界模型，校正后才生成有价值的合成 rollout 来改进 VLA。

**对本项目的判断**

它恰好说明 Harness 的正确闭环：

```text
真实执行的失败/偏差
        ↓
补进校正集，改善世界模型的局部真实性
        ↓
在世界模型内大量比较候选/rollout
        ↓
改善候选策略或选择器
        ↓
下一轮有限、受安全约束的真机执行
```

但 Ctrl-World 的权重、7D DROID adapter 与其 5–10 秒交互时延都不适合直接替换 G1/Revo2 系统。因此它应被采用为**Harness 机制蓝图和评测标准**，不是第一版模型依赖。

**一手来源**

- [官方仓库](https://github.com/Robert-gyj/Ctrl-World)
- [Ctrl-World 论文](https://arxiv.org/abs/2510.10125)
- [VLAW 论文](https://arxiv.org/abs/2602.12063)

---

### 3.7 DW05（2026）——video/action/value 的统一尝试，但 Value Expert 尚未发布

**官方事实**

- DW05 公开说明自己统一 future video prediction、action generation 与 state-value estimation；输入包含语言、图像/视频、robot type、state 和 action。
- 代码、公开权重、训练/推理入口可用；数据格式为 RobotWin 风格 JSONL，可含三相机视频、机器人 state、proprio、action、任务文本和 `robot_task_success`。
- README 明确注明 **Value Expert 将在后续版本更新**。
- 官方 action-conditioned demo 可根据 observation/action 预测 RobotWin future video；README 未给出 G1/Revo2 真机桥或明确最低硬件预算。

**对本项目的判断**

- 若 value head 成熟，它的“预测 + 价值”接口可能很适合 Harness。
- 但当前不能把一个“将来更新”的 Value Expert 作为比赛主闭环的可信决策依据；视频质量也不能代替 value。
- 它值得保存为快速跟踪对象，不应成为第一版唯一依赖。

**一手来源**

- [官方仓库](https://github.com/dexmal/opendw)
- [官方权重](https://huggingface.co/Dexmal/DW05-Base)

---

### 3.8 ω-0（2026-08）——概念最接近 humanoid whole-body WAM，但当前仅是论文线索

**官方论文事实**

- ω-0 将自己定义为 latent predictive whole-body world-action model：语言、视觉、proprio 输入后，直接预测可由 controller 执行的 whole-body action latents，并以未来 observation embedding 作预测目标，而非生成未来视频。
- 论文报告了 humanoid concurrent loco-manipulation 的真机实验和 ω-HOME 数据集。

**本次检索边界内的结论**

- 截至研究日期，在所检索到的论文与官方来源中，未找到可验证的官方代码仓库、公开权重或 Unitree G1+Revo2 接口。
- 因而它是**重要的方向证据**，不是当前可采用的工程依赖。不能因“直接输出全身动作”就把它当作可下载的 WMA。

**一手来源**

- [ω-0 论文](https://arxiv.org/abs/2608.06375)

---

## 4. VLA / 动作策略：它们有用，但不能替代预测器

### 4.1 NVIDIA Isaac GR00T N1.7 ——后续最适合作为 G1 动作提议器

**官方事实**

- GR00T N1.7 是 3B VLA，不是 world model；输入语言/图像/状态，输出 continuous action chunk。
- 公开 base/finetuned weights、训练代码、远程 ZMQ server-client 部署、TensorRT 路径和自定义 `NEW_EMBODIMENT` 流程。
- base checkpoint 有 `REAL_G1` tag；G1 全身流程可使用 `UNITREE_G1_SONIC` + GEAR-SONIC。官方说明该路径可由 VLA 预测 latent action，SONIC 解码成腿、臂、手的全身关节命令。
- 自定义 embodiment 需要 GR00T-flavored **LeRobot v2** 加 `meta/modality.json`，明确记录 state/action/video 的字段划分与归一化。
- 官方推理最低 16GB VRAM；默认 fine-tune 需 40GB+，且默认只调 projector + diffusion action head。若解冻 LLM/视觉层，官方建议 80GB+。
- 官方现成 G1/SONIC 路径并没有声明兼容 BrainCo Revo2。

**对本项目的判断**

- 如果需要把“固定技能”替换为数据驱动候选动作，GR00T 是目前 G1 侧最明确的 VLA 候选。
- 它仍需要 Revo2 modality/action adapter；不要把 `REAL_G1` 当成“所有 G1 末端都零样本可用”。
- 在 Harness 中它的职责是**产生候选**，而不是判断这些候选是否会成功。

**一手来源**

- [官方仓库](https://github.com/NVIDIA/Isaac-GR00T)
- [官方 policy / embodiment 文档](https://github.com/NVIDIA/Isaac-GR00T/blob/main/getting_started/policy.md)
- [官方自定义 embodiment 微调文档](https://github.com/NVIDIA/Isaac-GR00T/blob/main/getting_started/finetune_new_embodiment.md)
- [官方硬件说明](https://github.com/NVIDIA/Isaac-GR00T/blob/main/getting_started/hardware_recommendation.md)
- [GEAR-SONIC 官方仓库](https://github.com/NVlabs/GR00T-WholeBodyControl)

### 4.2 π0 / π0.5（Physical Intelligence）——成熟策略基线，不是世界模型

**官方事实**

- openpi 提供 π0、π0-FAST、π0.5 的代码与 base checkpoint；base 预训练于 10,000+ 小时机器人数据。
- 官方提供 DROID/ALOHA/UR 等真机范例、远程 policy server 以及用 **LeRobot** 格式微调自有数据的教程。
- 官方也明确提醒：其机器人与常见平台不同，迁移到新平台“不一定成功”。
- 官方单卡预算：推理 >8GB、LoRA fine-tune >22.5GB、full fine-tune >70GB；JAX 训练可用 `fsdp_devices`，但官方说明当前训练脚本不支持 multi-node。PyTorch 版仍缺 FSDP/LoRA/mixed precision 等功能。

**对本项目的判断**

- 可作为非 G1 特化的 VLA 对照组；不是世界模型，不能承担“候选后果预测”。
- 没有 Unitree G1 + Revo2 ready-made action bridge；相比 GR00T，它不是当前 G1 路线的第一策略候选。

**一手来源**

- [openpi 官方仓库](https://github.com/Physical-Intelligence/openpi)

### 4.3 OpenVLA ——成熟开源 VLA 对照，但与本项目 embodiment 距离大

**官方事实**

- OpenVLA 是 7B VLA，不是世界模型；其 API 直接预测 7-DoF action，并提供 REST 部署。
- 公开 checkpoint、训练代码和 RLDS 数据接口；自定义数据可转 RLDS 或自写 PyTorch dataset wrapper。
- 官方 LoRA 教程称最小约 27GB 显存；完整 7.5B fine-tune 使用 FSDP，官方建议完整 8×A100 节点。
- 官方真机教程/默认动作示例面向 BridgeData V2/WidowX，不是 Unitree G1/Revo2。

**对本项目的判断**：它是一个可用的 VLA 对照，不进入世界模型 shortlist。

**一手来源**

- [OpenVLA 官方仓库](https://github.com/openvla/openvla)
- [OpenVLA 论文](https://arxiv.org/abs/2406.09246)

---

## 5. UniSim 与 DeepMind Genie：应借鉴思想，不应作为当前依赖

### UniSim

- 2023 的 UniSim 论文分别讨论神经 closed-loop sensor simulator（自动驾驶）与通用交互式真实世界模拟器；后者论文展示过在模拟器中训练策略并零样本部署的研究结果。
- 它们说明“从多源数据学习可交互世界，再在其中训练/评估策略”在研究上成立。
- 但在本次一手资料范围内，没有找到可直接用于 Unitree G1+Revo2 的公开权重、训练代码与真机接口。因此它是**设计参照**，不是工程组件。

来源：

- [UniSim: Neural Closed-Loop Sensor Simulator](https://arxiv.org/abs/2308.01898)
- [Learning Interactive Real-World Simulators](https://arxiv.org/abs/2310.06114)

### DeepMind Genie / Genie 3

- Genie/Genie 3 是生成式交互环境/虚拟世界研究；原始 Genie 使用 latent action，而 Genie 3 面向实时交互生成。
- 它们不公开一个可映射 Unitree G1/Revo2 动作并能在本操作台真机部署的模型/控制桥。
- 因此不要把“能生成可交互视频世界”误读成“能预测并安全控制这台真机”。

来源：

- [Genie 论文](https://arxiv.org/abs/2402.15391)
- [Google DeepMind Genie 官方页](https://deepmind.google/models/genie/)

---

## 6. 统一比较表

> “真机部署”只表示官方是否给出了某种真实机器人实验证据或部署路径；**不表示**对 G1+Revo2 的开箱兼容。`—` 表示官方来源未明确给出，不猜测。

| 项目 | 类型 | 真正动作条件？ | 直接输出动作？ | 官方真机/部署证据 | 权重 / 训练代码 | 主要数据/动作接口 | 公开硬件信息 | 可作 Harness 预测器？ |
|---|---|---:|---:|---|---|---|---|---|
| **UnifoLM-WMA-0** | WMA：WM + action head | 是 | decision mode 是 | Unitree G1/Dex1 部署 | 是 / 是 | LeRobot V2.1；主视角；默认 ≤16 DoF | 未给可承诺的最低完整训练预算 | **是**；G1 基线，但 Revo2/多视角需改造 |
| **OSCAR-2B** | 动作条件视频 WM | 是，2D skeleton | 否 | 真机 policy-evaluation 配对 rollout；无控制桥 | 是 / 是 | 首帧+文本+skeleton video；URDF FK+标定 | ≥24GB 推理；示例单 Blackwell ≈1 分钟 | **是，强**；适合低频候选比较 |
| **GE-Sim** | 多视角神经模拟器 | 是 | GE-Act 另行输出 | 有 server/机器人平台材料；无 Unitree+Revo2 adapter | 是 / 是 | LeRobot 多视角、state/action；相机内外参+action `.npy` | — | **是**；复杂度较高 |
| **V-JEPA 2-AC** | latent action-conditioned WM | 是 | CEM 规划后可给动作 | Franka 真机实验；无 G1 bridge | 是 / 是 | DROID 视频/轨迹；官方示例 7D pose/action | 作者 post-train config 为 32 GPU、220G/GPU；非最低要求 | **是**；需重做目标与执行适配 |
| **Cosmos 3** | omnimodal WAM / WFM | 是 | policy/inverse mode 是 | DROID/AgiBot domains；非 Unitree bridge | 是 / 有框架/部分 recipe | image/MP4 + JSON action；10D/20D/29D domains | Edge 4B / Nano 16B / Super 64B，官方给推荐设备 | **理论上是**；当前 adapter 风险高 |
| **Ctrl-World** | 多视角视频 WM | 是 | 否 | DROID policy-in-WM；无 G1 bridge | 是 / 是 | DROID，官方 config 7D | A100 ≈10s/interaction；全量训练 8×A100/H100 节点 | **是**；做架构/评测参考 |
| **DW05** | video + action + value WM | 是 | 是 | 未见 G1/Revo2 桥 | 是 / 是 | RobotWin JSONL、多视角、state/action | — | **暂不宜承担**；Value Expert 未发布 |
| **ω-0** | latent humanoid WAM | 是 | 是，whole-body latent | 论文真机 | 未找到 / 未找到 | 论文中的视觉+proprio+controller latent | — | **否（暂不可集成）** |
| **GR00T N1.7** | VLA | 不适用 | 是 | `REAL_G1` / GEAR-SONIC | 是 / 是 | GR00T LeRobot v2 + modality.json | 16GB 推理、40GB+默认微调 | **否**；应作动作提议器 |
| **π0 / π0.5** | VLA | 不适用 | 是 | DROID/ALOHA/UR | 是 / 是 | LeRobot | 8/22.5/70GB（推理/LoRA/full） | **否**；策略对照 |
| **OpenVLA** | VLA | 不适用 | 是 | Bridge/WidowX | 是 / 是 | RLDS 或自定义 wrapper | LoRA ~27GB；full 8×A100 建议 | **否**；策略对照 |
| **UniSim / Genie** | 神经生成模拟范式 | 有限/latent | 不面向本机器人 | 无本项目桥 | 无可用本项目栈 | 研究型 | — | **否**；思想参考 |

---

## 7. G1 + Revo2 的最小适配边界

不要为每个模型重写一套机器人控制。应先固定两个与模型无关的深模块：

```text
CanonicalObservation
  = {head_rgb, wrist_rgb, robot_state, camera_calibration, timestamp}

CanonicalActionChunk
  = {arm/EEF intent, Revo2 intent, duration, safety envelope}
```

再分别实现：

```text
Model adapter:
  CanonicalObservation + CanonicalActionChunk
      ↔ 模型所需格式（skeleton / 7D EEF / 26D joint / JSON / latent）

Robot adapter:
  CanonicalActionChunk
      → 现有 G1 低层控制器 + Revo2 驱动 + 安全限制
```

这个分界是决定项目能否持续迭代的关键：

- 换 WMA、OSCAR、GE-Sim、V-JEPA 时，不应重写 G1/Revo2 真机执行层；
- 换现有脚本、GR00T、π0 时，不应重写 Harness 的评分与真机反馈逻辑；
- 世界模型应该看到**规范化动作意图**，而非直接看到未经约束的电机命令。

对于第一版，可进一步做减法：

1. 不建模行走；机器人放在已知操作位；
2. 不要求模型预测“液体”；把倾倒定义为可观测的**杯子位姿/姿态动作完成**；
3. 将长任务分成按钮、抓取、倾倒姿态、放置、关盖五类短片段；
4. 先只比较 2–5 个安全候选，而非在高维 26D 上做无约束搜索；
5. 真实执行后立即重观测，禁止让生成模型连续幻想完整长任务后一次性下发。

---

## 8. 第一版 Harness 的可验证形态

这不是“训练一个新大模型”，而是让已有模型在一个可证伪的科学循环中承担有限职责：

```text
任务目标：完成当前子任务（例如按黄按钮）
  ↓
动作提议：已有定点技能给出 nominal chunk；再构造少量安全扰动候选
  ↓
世界预测：对每个候选预测未来观察 / latent
  ↓
评分：按钮区域变化、手-杯相对位姿、盖子视觉状态、机器人安全代价
  ↓
选择并真机执行很短一段
  ↓
真实观察：提取同一任务状态
  ↓
记录：候选、预测、真实结果、是否成功、预测误差
  ↓
下一轮：更新候选选择、校准评分器，必要时积累 world-model adaptation 数据
```

### 三道必须通过的门

1. **离线重放门**：给定真实起点和真实动作，预测的下一段是否保留关键事件（按钮被按、杯被抓、杯发生倾倒姿态、盖动作）？
2. **反事实排序门**：对真实动作加安全范围内扰动，模型是否能把更接近成功的候选排在前面？
3. **真机校准门**：模型预测排名第一的候选，在真机上是否比 nominal/随机安全候选更常成功？

未通过第一门，不接真机；未通过第三门，不宣称世界模型改善了系统。这样闭环价值来自可量化的**少试错、更早发现失败、更快选择下一轮实验**，而不是生成一段看起来合理的视频。

---

## 9. 不确定性与反营销结论

1. **“公开权重”不等于“开箱适配”**。除 Unitree WMA 的 G1/Dex1 路径和 GR00T 的 G1 tag 外，任何 G1/Revo2 接口都需要我们自己建立；两者也都不等于 Revo2 已支持。
2. **“动作条件视频”不等于物理正确**。Cosmos 3 官方自己列出物体变形、3D/物理不准与 action-state inconsistency；VLAW 的问题正是示教数据使世界模型对失败和接触过度乐观。
3. **“真机实验”不等于可部署**。Franka、DROID、AgiBot G1 与 Unitree G1+Revo2 的关节、末端、控制器、视角完全不同。
4. **“直接输出动作”不等于形成反馈闭环**。ω-0、Cosmos policy、GR00T、π0 和 OpenVLA 可以是动作产生器；没有真机验证、预测对比和下一轮选择，它们仍是开环策略。
5. **148 段数据的角色**应首先是 adapter/后训练的验证与校准集，而不是从零学习接触物理的充分证据。是否够用必须以第 8 节三道门的结果判断，不能按 episode 数量拍脑袋。

---

## 10. 最终决策

### 现在做什么

1. 把 **UnifoLM-WMA-0** 保留为 Unitree G1 对照基线；不把现有 action-head-only 结果误当成完整世界模型。
2. 把 **OSCAR-2B** 作为第一优先的独立预测器验收对象：它的 skeleton action interface 最可能让 Revo2 不被固定关节编号绑死。
3. 用 **Ctrl-World/VLAW** 定义 Harness 的真实回路与评测方法，而不是照搬其 7D 模型。
4. 保留 **GR00T N1.7** 给后续“用 VLA 替换/丰富动作提议器”；它不进入预测器职责。
5. 当单视角/低频 OSCAR 不足时，评估 **GE-Sim**；当需要 latent MPC 时，评估 **V-JEPA 2-AC**。

### 现在不做什么

- 不把 Cosmos 3、ω-0、Genie 3 当作已完成的 G1+Revo2 真机方案；
- 不先为未验收的模型租 8×H800/8×H100 做全量训练；
- 不为了“世界模型”而丢弃已有定点技能；它们正是第一版最安全的 action proposer；
- 不把模拟世界里的成功率当成比赛要求的闭环证据；必须报告真机预测误差与后续迭代收益。


---

## 11. 决策修订：稳定性优先（本节覆盖第 0 节和第 10 节的首选顺序）

### 11.1 不将 OSCAR-2B 放在第一版关键路径

OSCAR 的动作骨架接口有价值，但它是近期研究项目，公开生态、独立复现、故障处理经验以及 Unitree G1 + BrainCo Revo2 的直接验证都不足。社区热度本身不能判定模型能力；但对于尚未跑通的系统，它意味着缺少可借鉴的部署经验，是实际工程风险。

因此，OSCAR 仅保留为**离线研究对照**：它可以参加同一套 action replay 评测，但不能成为第一版真机 Harness 的关键依赖，更不能承担控制职责。

### 11.2 不存在同时满足“成熟、开源、G1+Revo2 已验证”的通用世界模型

本研究范围内：

- WMA 有最直接的 Unitree G1 部署证据，却是 Dex1、主视角、默认 16 DoF 路径，不能宣称已支持 Revo2；
- Cosmos 等大厂基础模型维护更活跃，却没有 Unitree G1 + Revo2 的现成 action domain；
- GR00T 有 G1 的当前策略/全身控制路径，却不是世界模型；
- OSCAR、GE-Sim、V-JEPA 有各自的预测优势，却都没有本项目的真机桥。

把其中任何一个宣传为“开箱即用的稳定答案”都是不诚实的。模型下载量、机构规模或 Hugging Face likes 也不能跨越动作、末端、相机与接触分布的不匹配。

### 11.3 低风险第一版：任务级世界模型，而非通用视频生成器

第一版将世界模型收缩为可验证的任务状态转移：

```text
当前双相机观察 + 机器人状态
        ↓
任务状态（按钮、杯子、盖子、手部、风险）
        + 候选短技能
        ↓
预测下一任务状态 + 成功概率 + 不确定性
```

它仍是世界模型：预测动作施加后的世界状态；但不要求它凭 148 段数据重新学习通用视觉、接触物理和全身运动。现有定点技能继续负责执行，Harness 负责生成少量安全候选、比较预测、执行短片段，并以真机结果校正预测。

这条主线具有三个性质：

1. **对 G1/Revo2 的可应用性来自已有执行链，而非某个论文权重的承诺。**
2. **闭环价值可直接证伪：**是否更常选中成功候选、是否减少无效真机尝试、预测是否随真实反馈变得更准。
3. **前沿模型失败不会阻塞系统。**

### 11.4 外部模型的保守分工

```text
主线：任务级世界模型 + 现有 G1/Revo2 定点技能 + Harness
兼容基线：WMA 仅做数据语义和 G1 对照验证；不沿用 FairScale 训练链
未来基础模型：Cosmos 的受支持版本，待其在规范动作接口上通过离线验收
研究对照：OSCAR / GE-Sim / V-JEPA，仅在离线 action replay 中竞争
未来动作提议器：GR00T，待 Revo2 embodiment adapter 成熟后接入
```

### 11.5 模型进入真机前的三道门

1. **适配门**：能以统一观察和统一短动作表示运行，不绕过 G1/Revo2 的安全控制器；
2. **离线门**：在从未参与适配的真实 episode 上，能正确排序成功与失败候选，并给出可校准的不确定性；
3. **影子门**：先与真实系统并行预测但不控制机器人；只有其候选排序稳定优于现有 nominal 技能，才允许参与真机选择。

### 11.6 FSDP 的位置

PyTorch FSDP 是云端训练基础设施，不是模型可信性的来源。它只在某个候选通过上述前两道门、并确认参数高效微调不足时使用。第一版不为使用 FSDP 而启动全量大模型训练。
