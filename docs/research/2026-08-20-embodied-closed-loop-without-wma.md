# 无法训练 WMA 时，如何优先完成具身实验闭环

调研日期：2026-08-20  
证据口径：只采用论文、项目官网、官方文档、官方仓库、官方模型卡与本仓库权威规格。所有公网来源的访问日期均为 2026-08-20。

## 结论

下一步不应寻找一个“缩水版 WMA”继续占据关键路径，而应删除“世界模型先训练好，闭环才能开始”这一系统依赖。

推荐唯一主线是：

> **完整连续真实示教 → 冻结 replay 基线 → live shadow → 受监督真机 → 独立见证与真实锚点 → 端到端 ACT → 自转批次。**

这条路线首先证明系统完整性，然后才证明策略能力。它不依赖大集群，也不依赖仿真能够复刻实验室全部细节；单机 RTX 4090 足以承担 ACT、一次受控的 Diffusion Policy 对照，以及后续可选的 SmolVLA 小规模实验。[S1][S2][S3]

仿真不再是闭环的地基。真实连续 replay、真实 observation 上的 shadow、受监督硬件回合和每批真实锚点共同构成 **simulation-lite** 主线。Unitree Isaac Lab 只在真实 operator、witness 和 replay 已经成立后，作为仿真适配/准入或 `PredictiveNode` 的一个实现接入。[S8][S9]

**明确排除项：当前路线不采用 MuJoCo 或 MJX。**

WMA 保留，但改为后置的 **shadow predictive auditor**：先预测已经封存回合本应出现的 witness 轨迹并接受评分；它只有在真实校准中持续胜过简单预测器后，才逐级获得候选排序权，永远不获得真实执行权或裁决权。[S15][S16]

## 1. 不可改变的系统边界

本建议继承以下仓库契约：

- [权威规格](../../.scratch/embodied-instrument-operation/spec.md)：任务是无液体、可逆的开盖—取杯—倾斜—放回—关盖完整轨迹；研究对象是固定策略的可靠工作包络。
- [问题 06](../../.scratch/embodied-instrument-operation/issues/06-choose-the-minimal-policy-learning-and-serving-shape.md)：策略输出动作块，tracker 是唯一运动执行器，学习输出必须投影到可行域且记录投影幅度。
- [问题 09](../../.scratch/embodied-instrument-operation/issues/09-define-the-pilot-go-no-go-decision.md)：20 回合试点必须把失败路由到“补数据、修契约或停止 formulation”，不能用扩大数据集代替诊断。
- [问题 20](../../.scratch/embodied-instrument-operation/issues/20-define-the-predictive-node-contract.md)：预测节点生成未来 witness view 或 predicates，接受真实结果评分，但不裁决、不授权真机动作。
- [问题 22](../../.scratch/embodied-instrument-operation/issues/22-define-what-the-loop-may-change.md)：闭环优化条件、调用方式、环境工单和最小新增数据，而不是在线改写受试策略。

由此得到六个不变量：

1. 控制环、策略训练环、批次实验环分离。
2. 唯一运动路径保持为 `Policy/Replay → WholeBodyTarget → Target Bridge → tracker`。
3. 成功必须由独立于策略的外部 witness 对完整有序轨迹归约；终态、仿真结果、策略自评和人工主观判断均不能成为成功。
4. reset、hold、intervention、failed、indeterminate 和 completed 是不同事实，全部追加记录。
5. 每批预注册、每批永久保留真实锚点；generation、policy、witness 标定或 action protocol 任一变化，旧校准权限归零。
6. 仿真证据、shadow 证据和真实证据不得通过改名或聚合互相转换。

## 2. 两个闭环必须分权，而不是合并

仓库已经存在两个看似相近、实际权力不同的闭环。

### 2.1 `vegapunk.embodied.harness.CampaignEvaluator`

它属于 **simulation / adaptation / admission** 平面：评估候选适配、扰动条件和仿真准入。实现会在 `robot.is_real_robot` 时直接拒绝构造 evaluator，因此不能被扩展为无人值守真机搜索器。

Unitree Isaac Lab 若接入，应放在这一平面，或封装成只读的 `PredictiveNode`。它的输出只能是候选、分数、仿真轨迹和准入证据。

### 2.2 `vegapunk.operation.ExperimentLoop`

它属于 **SOURCE_REAL generation / batch / reliability** 平面：预注册真实批次、调用受监督真机 episode、接收独立 witness/reset、封存结果、生成可靠性包络和下一批。

只有这一平面可以产生真实成功、真实失败和当前 generation 的可靠性证据。

### 2.3 唯一合法交接

两个闭环只通过不可变摘要交接：

```text
policy digest
configuration digest
embodiment digest
evidence digest
```

仿真 ledger 不导入真实 ledger；仿真 campaign 不创建或改写 SOURCE_REAL generation；真实反例不能被仿真多数票覆盖。这样既保留仿真价值，也避免出现两个都声称拥有“实验真相”的系统。

## 3. 单一路线：simulation-lite 真实证据阶梯

```text
5–10 条完整连续遥操作
          │
          ▼
冻结 end-to-end replay artifact
          │
   ┌──────┴────────┐
   ▼               ▼
offline replay   live shadow
不发命令          读真实观测、不发命令
   └──────┬────────┘
          ▼
supervised hardware
同一 artifact → 唯一 motor path
          │
          ▼
独立 trace/reset witness + human intervention record
          │
          ▼
每批 real anchor → sealed result → 下一批/工单
          │
          ▼
20 条完整连续 pilot → end-to-end ACT
```

### 3.1 为什么先补 5–10 条完整连续示教

现有 148 条是四类分段数据，不包含自然的段间过渡，也没有完整任务的端到端结果。它们可以用于局部动作范围、视觉质量、手部动作和 segment shadow 诊断，但不能通过 FSM、四个 segment policy 或离线拼接被转换为完整闭环策略。

最小的诚实补充不是继续扩大四类分段，而是先采集 5–10 条从 reset 初态开始、连续完成全部可逆轨迹的遥操作：

- 用于校准 observation/action 时间、相机、BrainCo、WholeBodyTarget 和 witness 的端到端语义；
- 冻结为 deterministic replay artifact，验证系统接线和安全边界；
- 不用于宣称泛化，也不用于得出可靠成功率；
- 失败或人工干预不删除，只带明确 outcome/intervention 标签封存。

这里的 replay 必须是 **qualified replay**：绑定 generation、初态容差、控制频率和 artifact digest；每帧仍经过目标有效性、序号/时效、可行域与 Safe Hold。初态超出预注册包络、轨迹偏差扩大或任一证据通道失效时立即停止，绝不以“把录制命令原样发完”为目标。

### 3.2 四条证据通道

| 通道 | 机器人是否动作 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| Offline replay | 否 | 数据解码、预处理一致、动作维度、时序、投影、chunk continuity | 真机稳定或任务成功 |
| Live shadow | 否 | 策略能在真实 observation、真实时延和真实状态分布上持续输出合规动作 | 输出被执行后会成功 |
| Supervised hardware | 是，具名监督、急停、单回合 | 唯一 motor path、安全保持、真实 witness/reset、真实任务结果 | 无人值守批量安全 |
| Real anchor | 是，每批至少一个 | 将预测和仿真持续校准到当前 generation | 允许预测器代替真实实验 |

Unitree 官方 LeRobot 工具已经把 `--send_real_robot` 暴露为显式部署开关，并提供数据集 replay、模型评估、BrainCo 数据转换和 `--ee=brainco` 路径；这为 offline/shadow/real 三态共用一个 adapter 提供了现实基础。[S6] 但其直接真机示例只可作为数据和模型适配参考，本项目不得绕过 WholeBodyTarget 与 Target Bridge。

Unitree 的 `G1_BRAINCO_CONFIG` 定义了 26 个双臂/双手 motor 与四路相机（左右高位、左右腕部），与现有分段档案很接近。[S6] 这只证明 source-side 数据转换接缝接近，不证明 26D 档案可以直接满足项目完整 47D `WholeBodyTarget`；固定站立的 root/legs、时效、序号、投影和安全 envelope 仍必须由项目 adapter 补全和验证。新连续 pilot 必须记录完整目标契约，不能把旧 26D 档案冒充可直接部署权重。

### 3.3 Independent witness 与 human intervention

- policy observation 与 witness observation 至少在裁决逻辑上独立；策略不得读到 witness verdict。
- witness 输出有时间、通道身份、新鲜度和 definite/indeterminate；只对完整有序轨迹做纯归约。
- 人工可以急停、进入 Safe Hold、确认工单和恢复物理台面；人工不能把失败口头改判为成功。
- 每次 intervention 结束当前 episode。之后若重启，必须新建 episode record 并重新通过 reset witness，不能把“人工救回来的回合”计为自主成功。
- reset 无法确认、witness 丢失或安全状态未知时，批次停止等待人工，而不是自动重试。

Unitree SDK2 官方要求低层控制前释放高层 motion service，避免冲突命令；官方 G1 示例以 2 ms 周期发布低层命令。[S7] 这进一步说明策略推理、实验设计和网络通信都不能取代本地确定性 tracker/dead-man。

## 4. 4090 上的策略决策

### 4.1 候选矩阵

| 候选 | 官方一手事实 | 对 4090 + 少量真实数据的判断 | 在本项目中的位置 |
| --- | --- | --- | --- |
| **ACT** | LeRobot 定位为约 80M、单 GPU 数小时、可接多相机与关节状态并输出 action chunk；官方硬件指南给出约 2–6 GB 峰值区间。[S1][S2] | 明确可行；算力余量可用于多视角、数据审计和多次复现 | **第一个且唯一默认 learned subject** |
| **Diffusion Policy** | 官方方法面向多峰动作分布，以条件扩散生成 receding-horizon action sequence；LeRobot 指南给出约 8–14 GB 区间。[S2][S3] | 可行，但训练/推理和调参复杂度高于 ACT | ACT 被证实出现动作平均化或多峰冲突时，做一次受控替代 |
| **SmolVLA** | 450M，多相机+状态+语言+action expert；官方示例任务使用 50 episodes，并报告同任务 25 episodes 不足，但这不是通用样本下限；20k steps 单 A100 约 4 小时，LeRobot 指南给出约 10–16 GB 区间。[S2][S4][S5] | 显存可行，数据与任务形态当前不匹配 | 暂不进入主线；多任务/语言变化成为真实变量后再试 |
| **OpenVLA-OFT** | 官方仓库给出推理约 16–18 GB，但训练需要 1–8 张、每张约 27–80 GB；输入支持主视角、腕部视角、状态和语言并输出动作块。[S17][S18] | 4090 可做部分推理，不在官方训练显存包络内 | 不作为本机训练候选；未来只可作为外部 checkpoint 的 shadow challenger |

### 4.2 为什么 ACT 是主线

ACT 的系统优势不是“最先进”，而是最容易被完整验证：

- 与现有动作块和多相机契约直接对齐；
- 单机 4090 可反复训练、回滚和做数据消融，而不是只够一次昂贵实验；
- Unitree 官方 LeRobot 仓库已经给出 G1+BrainCo 的数据转换、ACT/Diffusion 训练与真机评估接缝。[S6]
- 失败更容易被分解为数据、过渡、感知、投影、延迟或条件包络问题。

但 ACT 必须训练在 **完整连续 episode** 上。148 条 segment 数据只能辅助预训练局部 encoder、局部诊断或 segment shadow；禁止把四个模型用 FSM 串起来冒充端到端 learned subject。

### 4.3 20 条 pilot 的正确含义

先补 5–10 条连续示教是接线样本；随后正式收集 20 条端到端 pilot，按完整 episode 划分 train/validation/test，再训练第一版 end-to-end ACT。

20 条是一个 go/no-go 诊断门，不是“数据已经足够”的保证。若 held-out learning curve 仍明显随数据增长，才定向扩展到 30、40、约 50 条；若失败来自 witness、时序、动作语义或过渡方式，则先修契约，继续堆数据无效。SmolVLA 官方对 25/50 episodes 的观察也说明，episode 数量不能脱离任务变化覆盖来解释。[S4]

### 4.4 Diffusion、SmolVLA、OpenVLA-OFT 的启动条件

- **Diffusion**：ACT 在同一 held-out episodes 和真实 shadow 上重复出现“相同观察对应多种有效动作，回归结果落在无效平均值”的证据；只能更换 policy，不得同时更换数据划分、动作定义和 witness。
- **SmolVLA**：语言指令变化或多个任务确实成为实验变量，且完整连续数据已通过学习曲线证明足够；否则语言骨干只增加不可解释性。官方 25/50 episodes 结果只用于提示数据风险，不移植为本任务阈值。[S4]
- **OpenVLA-OFT**：出现可复现的外部训练资源或合格 checkpoint，并先在 4090 上完成离线推理、延迟和 action-contract shadow；本机不承担其官方训练形态。

## 5. 仿真与场景替代方案：只保留一个升级方向

| 方案 | G1/场景/传感/真实接口一手证据 | 对当前系统的缺口 | 决策 |
| --- | --- | --- | --- |
| **Unitree Isaac Lab** | Unitree 官方提供 G1 29 DoF、Dex1/Dex3/Inspire、任务场景、相机、数据 replay、光照/相机增广，并采用与真机相同 DDS；官方声明测试过 RTX 4090。[S8] Isaac Lab 提供 RGB/depth/segmentation、IMU、contact 等传感接口。[S9] | 没有 BrainCo Revo2 官方资产；同 DDS 反而要求仿真与真机严格网络隔离；场景仍需按实验台重建和真实标定 | **唯一计划接入的仿真器**，但必须排在真实 replay/operator 之后 |
| **ManiSkill 3** | 官方含 Unitree G1 37 DoF、位置控制器、GPU 视觉/并行仿真、real2sim 和 IL/Diffusion/VLA 基线。[S10][S11] | G1 资产质量标为 B，官方说明部分数值不现实；无 BrainCo、Unitree DDS 和本项目真实控制契约 | 降级为快速几何/任务 API 原型，不进入准入和真实可靠性主线 |
| **Genesis World** | 官方支持 URDF/USD 等资产、刚体/多物理、相机、深度、IMU、接触、触觉和并行异构环境。[S12] | 官方树没有可直接采用的 G1+BrainCo 任务资产或 Unitree 真实接口；需要从模型、控制、传感、场景到标定全部自建 | 暂缓；工程面过大，会推迟闭环而不增加当前证据权威 |
| **Webots** | 官方有通用 Camera/LiDAR 等设备和 `webots_ros2` messages/services/actions 接口。[S13] | 官方发行树没有可直接采用的 Unitree G1；G1+BrainCo、WholeBodyTarget 和实验台均需自建 | 暂缓；只适合低成本场景可视化或 ROS 接口原型 |
| **Gazebo** | Unitree 官方 ROS 仓库已有 G1 URDF/mesh，同时提供通用 Gazebo joint controller；仓库说明的现成 Gazebo launch 仍面向列出的四足型号，并基于 ROS Kinetic/Melodic 与 Gazebo 8。[S14] | “有 G1 描述文件”不等于“有 G1 操作仿真”；缺少现成 G1 task/controller/BrainCo/当前 ROS 2 真实链 | 暂缓；不把模型可加载误判为系统可用 |

### 5.1 Isaac Lab 的最小接法

Isaac Lab 不建立第二套 experiment loop，只提供一个 adapter：

```text
相同 policy/config/embodiment digest
              │
              ▼
Isaac adapter
   ├─ CampaignEvaluator：simulation/adaptation/admission
   └─ PredictiveNode：预测 witness predicates + uncertainty
              │
              ▼
仿真 evidence digest
              │
              ▼
ExperimentLoop 仅把它当候选排序输入
```

第一版只对齐动作语义、关节/手范围、控制周期、相机位姿、桌面几何、关键接触和 witness 可见性。未经真实标定的摩擦、材质、光照和接触参数只能是扰动轴，不能写成台面事实。

SimFoundry 的公开结果显示仿真排名与真实表现可以高度相关，但其论文仍把真实表现作为外部比较对象，而不是由仿真替代。[S19] 因此仿真的最佳权力是“哪里更值得买真实回合”，不是“这里已经真实成功”。

## 6. WMA 后置为 shadow predictive auditor

Unitree 官方 WMA 同时提供 simulation engine 与 decision-making 两种形态；官方训练入口默认启动 8 个 GPU 进程，训练数据目前只支持主视角输入，默认状态/动作维度为 16，公开 G1 路径主要是 Dex1。[S15][S16]

这些事实意味着算力只是第一层不匹配。当前项目还需要头部/双腕视角、BrainCo、WholeBodyTarget、独立 witness 和 50 Hz tracker。为了适配 WMA 而扩张核心接口，会让外部模型反过来定义系统。

### 6.1 后置审计流程

1. 在 batch seal 前预注册 WMA 版本、输入摘要、预测目标和评分规则。
2. 对已计划但尚未向 WMA 泄露结果的真实 episode，输入起始 witness view、状态和冻结 action sequence。
3. WMA 生成未来 witness view 或 predicates；不生成真机目标。
4. 真实 episode 完成后，用同一个 witness reducer 比较预测与真实轨迹。
5. 记录有序轨迹匹配、危险/不确定事件漏报、Brier score、校准图和条件排序质量。
6. generation、policy、witness 标定或 action protocol 任一变化，WMA 权限归零并重新 shadow。

### 6.2 权限阶梯

| 等级 | WMA 权力 | 晋级条件 | 永久禁止 |
| --- | --- | --- | --- |
| W0 score-only | 只对封存样本出分 | 能稳定运行且输入/输出可复现 | 影响下一真实回合 |
| W1 prospective ranking | 批次前排序候选条件 | 连续多个预注册批次优于 tabular/calibrated baseline，且危险事件漏报不恶化 | 声称真实成功率 |
| W2 reduce duplicates | 可建议减少部分重复的低信息点 | 排序和校准持续稳定；每批仍有真实边界点和真实锚点 | 取消真实锚点、执行动作、裁决结果 |

首版采用以下保守的**治理阈值**；它们是项目的授权门，不是世界模型能力的通用科学常数：

- **W0 → W1**：在同一 `generation/policy/witness/action-protocol` 下至少完成 3 个封存批次、累计至少 30 个真实锚点，且 succeeded 与 non-succeeded 各至少 10 个；全部预测必须在真实执行前封存。锁定 holdout 上，相对“经验先验”和 `TabularPredictiveNode` 两者中更强的基线，Brier skill 的 95% bootstrap 置信区间下界必须大于 0；条件排序相关性的 95% 区间下界也必须大于 0；对 hold、reset failure、indeterminate 的漏报不得高于基线，任何安全相关漏报都阻止晋级。[S20][S21]
- **W1 → W2**：再完成 2 个前瞻批次、每批至少 10 个真实锚点，以上条件继续成立。初次最多减少 25% 的**重复低信息点**，不得减少边界点、不确定点、校准点或每批真实锚点。
- **立即降级**：任一关键 digest 改变、出现安全相关漏报、连续两个批次不再优于基线，或校准漂移越过预注册阈值，权限立即回到 W0。

单独的 Brier score 会混合校准与区分能力，因此授权同时看 reliability diagram、前瞻排序和危险事件漏报，不能靠一个汇总分数晋级。[S20]

世界模型的终极 Gate 不是“终于租到卡”，而是：它在相同真实 held-out batches 上，比简单预测器更早、更准地发现可靠性边界，并且没有隐藏危险反例。

## 7. 阶段 Gate、停止条件与失败路由

### Gate 0：软件分权成立

通过条件：

- `CampaignEvaluator` 明确拒绝 real robot；
- SOURCE_REAL generation 只能由 `ExperimentLoop` 产生；
- 两边只交换四类 digest，不交换可改写 ledger；
- no-op、stale/indeterminate witness、reset failure 均不能成为成功。

停止条件：任何 adapter 能直接把仿真结果写成真实 result，或存在第二 motor path。

### Gate 1：5–10 条完整连续数据与冻结 replay

通过条件：

- 每条从 reset 初态开始，包含完整有序任务轨迹和结束状态；
- 多相机、状态、动作和 witness 时间可对齐；
- frozen replay 通过 offline pipeline，无持续大投影或动作语义歧义；
- 148 条 segment 数据被保留为 segment-local evidence，不被拼接。

停止条件：时间同步不可信、动作单位不明、相机 provenance 缺失或输出主要依靠可行域投影修正。此时修数据契约，不训练。

### Gate 2：确定性 end-to-end 受监督真机闭环

交付：同一个冻结连续 replay artifact 通过唯一 motor path 完成受监督单回合；独立 trace/reset witness、hold、intervention 和 append-only record 全链工作。

通过不是要求高成功率，而是要求每次成功、失败、保持和人工干预都被正确裁决且不可洗白。

停止条件：安全违规、控制饥饿、reset 不可确认、witness 丢失或 intervention 未结束 episode。未通过前不得训练后直接上真机。

### Gate 3：20 条端到端 pilot 与 ACT

交付：20 条连续示教的 whole-episode split、end-to-end ACT checkpoint、held-out offline replay、真实 live shadow 和投影/延迟报告。

失败路由：

| 观察 | 唯一下一步 |
| --- | --- |
| 同步、witness、动作契约缺口 | 修基础设施；该批不进入策略能力结论 |
| 安全违规、持续大投影、chunk starvation | 停止该 action formulation，不补同类数据 |
| 训练片段好、完整过渡差 | 只补完整过渡附近的连续示教 |
| 失败集中在杯位、光照、起姿 | 条件搜索或夹具工单，先不换模型 |
| 证实为多峰动作平均化 | 同一数据/划分/契约下试一次 Diffusion Policy |
| 学习曲线继续明显上升 | 定向增加完整 episodes，逐步向约 50 条验证 |
| held-out 与 shadow 均无改善 | 停止当前 observation/action formulation，重新定义问题 |

### Gate 4：ACT 受监督硬件 pilot

通过条件：

- 具名监督者、物理急停、固定站立、轻质道具、清空周边；
- 每回合独立 reset，intervention 立即终止；
- 每个 outcome 由 witness 归约；
- checkpoint、generation 和调用协议全程冻结。

停止条件：一次安全违规，或配置的重复等价失败/circuit breaker 触发。不得自动重试到成功。

### Gate 5：真实自转批次

通过条件：至少两个封存批次，第二批的条件、调用方式、最小新增数据或环境工单必须由第一批真实结果改变；每批都有真实锚点，错误预测被保留。

评价输出不是一个总成功率，而是：

- 当前 generation 的可靠性包络；
- 不确定区间和样本量；
- 失败边界；
- 下一批为何改变；
- 夹具/协议工单的预期收益。

### Gate 6：Isaac Lab 或 WMA 进入预测竞争

只有 Gate 5 成立后接入。通过条件是对真实批次的 prospective ranking 有增益；不是画面逼真、仿真吞吐高或单次预测漂亮。

## 8. 2–6 周实施计划

### 第 1 周：清除双闭环歧义，补齐真实 operator

- 固化 `CampaignEvaluator = simulation/adaptation/admission`、`ExperimentLoop = SOURCE_REAL` 的分权测试。
- 暴露唯一 campaign operator：generation、预注册、episode factory、trace/reset witness、sealed result、next design。
- 删除或隔离旧的液体 outcome、人工成功判断和分段拼接叙事。
- 把 policy/config/embodiment/evidence digest 作为两平面的唯一交接。

### 第 2 周：完整连续 replay 基线

- 补采 5–10 条完整连续遥操作；保留失败与 intervention。
- 审计 148 条 segment 数据，但只用于局部诊断。
- 建立 frozen replay artifact，完成 offline replay、动作投影、chunk continuity 和 witness 时间对齐。
- 在安全 envelope 内做确定性受监督真机回合，证明整个闭环能失败、停止、复位和封存。

**两周最低完成定义**：即使尚未训练 ACT，也已有一个真实可转动、可裁决、可停止、能改变下一批的闭环。

### 第 3 周：正式 20 条端到端 pilot

- 以完整 episode 为单位收集和划分数据，覆盖有限但预注册的杯位/起姿/光照变化。
- 固定 BrainCo 与 WholeBodyTarget 语义；使用 Unitree 官方 BrainCo→LeRobot 接缝核对转换。[S6]
- 产生 learning curve 和数据 shopping list，不把 episode 数当作成功代理。

### 第 4 周：训练 end-to-end ACT 与 live shadow

- 单机 4090 训练至少两个可复现 seed/checkpoint。
- held-out whole-episode offline evaluation。
- 真实 observation 上 live shadow；记录延迟、投影、chunk starvation 和与 replay/人类动作的偏差。
- 只有 Gate 3 全部通过才申请真机回合。

### 第 5 周：ACT 受监督硬件与第一真实批次

- 运行预注册硬件 pilot；严格 circuit breaker。
- 形成 failure taxonomy、可靠性初始包络和第一批 sealed result。
- 由结果决定：补过渡数据、做夹具工单、停止 formulation，或触发一次 Diffusion 对照。

### 第 6 周：第二批自转与可选 Isaac adapter

- 第二批必须由第一批真实证据改变，证明闭环不是固定脚本。
- 若真实 operator/replay/witness 已稳定，再把 Unitree Isaac Lab 接到 `CampaignEvaluator` 或 `PredictiveNode`，只比较少量相同条件。
- WMA 若有可用 checkpoint，只以 W0 score-only 身份进入；不因已有权重而跳级。

## 9. 近期明确不做

- 不等待 WMA 训练资源。
- 不把四类 segment policy 用 FSM 串成完整 learned policy。
- 不让 behavior tree、LLM、仿真器、WMA 或 witness 进入 50 Hz 控制。
- 不采用第三方 direct joint/LowCmd 示例绕过 WholeBodyTarget、Target Bridge 和 tracker。
- 不让仿真 campaign 创建真实 generation、真实 batch 或真实 reliability。
- 不把仿真 replay、shadow 输出或人工救回的回合计为 autonomous success。
- 不同时更换模型、数据划分、动作语义、witness 和仿真器；一次实验只改变能被归因的一类变量。
- 不追逐宣传吞吐数字；只测本任务的 step time、显存、传感器组合和 evidence quality。
- 不做真实液体、流体结论、新平衡模型、无人值守在线强化学习或自动在线改权重。

## 10. 最终判断

项目现在缺的不是另一个“大模型替代品”，而是把真实证据链变成系统主干。

**最小而完整的方案**是：

```text
完整连续真实数据
  + frozen replay
  + end-to-end ACT
  + WholeBodyTarget 唯一运动通路
  + live shadow / supervised hardware
  + independent trace/reset witness
  + real anchor
  + ExperimentLoop 批次反馈
```

这套系统即使 ACT 失败也有实际价值：它能指出失败究竟来自数据过渡、观察、动作契约、条件边界还是物理台面，并生成下一批和环境工单。相反，即使一个世界模型生成了漂亮视频，只要没有独立见证、真实锚点和能被真实结果改变的下一批，它仍没有形成闭环。

仿真和 WMA 都不被删除，只被放回正确的位置：**它们负责压缩真实试验搜索空间；真实台面负责定义事实。**

## 一手来源

- **[S1] LeRobot ACT 官方文档**：ACT 的规模、输入、action chunk、单 GPU 与少量示教定位。  
  https://github.com/huggingface/lerobot/blob/main/docs/source/act.mdx （访问日期：2026-08-20）
- **[S2] LeRobot Compute HW Guide**：ACT、Diffusion、SmolVLA 的指示性显存与 4090 训练量级；官方明确提醒数值依赖图像、batch 和 I/O，非 SLA。  
  https://github.com/huggingface/lerobot/blob/main/docs/source/hardware_guide.mdx （访问日期：2026-08-20）
- **[S3] Diffusion Policy 官方项目与论文入口**：条件动作扩散、多峰行为与 receding-horizon action sequence。  
  https://diffusion-policy.cs.columbia.edu/ （访问日期：2026-08-20）  
  https://arxiv.org/abs/2303.04137 （访问日期：2026-08-20）
- **[S4] LeRobot SmolVLA 官方文档**：450M；其特定示例任务使用 50 episodes，并报告 25 episodes 不足；另含单 A100 训练参考。该结果不是通用样本下限。  
  https://github.com/huggingface/lerobot/blob/main/docs/source/smolvla.mdx （访问日期：2026-08-20）
- **[S5] SmolVLA 官方模型卡**。  
  https://huggingface.co/lerobot/smolvla_base （访问日期：2026-08-20）
- **[S6] Unitree LeRobot 官方仓库与 BrainCo 配置**：G1+BrainCo 的 26 motor/四视角数据转换、model deployment、replay、ACT/Diffusion 训练和 real-eval 开关。  
  https://github.com/unitreerobotics/unitree_lerobot/blob/main/README.md （访问日期：2026-08-20）  
  https://github.com/unitreerobotics/unitree_lerobot/blob/main/unitree_lerobot/utils/constants.py （访问日期：2026-08-20）
- **[S7] Unitree SDK2 Python 官方仓库与 G1 低层示例**：DDS、高低层控制冲突边界、G1 2 ms 本地控制示例。  
  https://github.com/unitreerobotics/unitree_sdk2_python （访问日期：2026-08-20）  
  https://github.com/unitreerobotics/unitree_sdk2_python/blob/master/example/g1/low_level/g1_low_level_example.py （访问日期：2026-08-20）
- **[S8] Unitree Isaac Lab 官方仓库**：G1 多末端、任务场景、DDS、相机、replay、数据增广与 RTX 4090 测试声明。  
  https://github.com/unitreerobotics/unitree_sim_isaaclab （访问日期：2026-08-20）  
  https://api.github.com/repos/unitreerobotics/unitree_sim_isaaclab/git/trees/main?recursive=1 （访问日期：2026-08-20；用于核验当前官方树中没有 BrainCo/Revo 命名资产或 DDS 实现）
- **[S9] Isaac Lab 官方仓库**：传感器、仿真和学习框架边界。  
  https://github.com/isaac-sim/IsaacLab （访问日期：2026-08-20）
- **[S10] ManiSkill 3 官方仓库**：GPU 并行、real2sim、学习基线与任务构建能力。  
  https://github.com/haosulab/ManiSkill （访问日期：2026-08-20）
- **[S11] ManiSkill Unitree G1 官方页面**：37 DoF、控制器和 Quality B 限制。  
  https://github.com/haosulab/ManiSkill/blob/main/docs/source/robots/unitree_g1/index.md （访问日期：2026-08-20）
- **[S12] Genesis World 官方仓库与完整树 API**：资产格式、传感器、多物理和并行环境；树用于核验当前官方发行中没有可直接采用的 G1+BrainCo 任务资产。  
  https://github.com/Genesis-Embodied-AI/genesis-world （访问日期：2026-08-20）  
  https://api.github.com/repos/Genesis-Embodied-AI/genesis-world/git/trees/main?recursive=1 （访问日期：2026-08-20）
- **[S13] Webots、官方树 API 与 Webots ROS 2 官方仓库**：通用传感设备及 ROS 2 messages/services/actions 接口；树用于核验当前官方发行没有可直接采用的 Unitree G1。  
  https://github.com/cyberbotics/webots （访问日期：2026-08-20）  
  https://api.github.com/repos/cyberbotics/webots/git/trees/master?recursive=1 （访问日期：2026-08-20）  
  https://github.com/cyberbotics/webots_ros2 （访问日期：2026-08-20）
- **[S14] Unitree ROS 官方仓库**：G1 描述资产、Gazebo joint controller、现有 launch 型号与旧版 ROS/Gazebo 依赖。  
  https://github.com/unitreerobotics/unitree_ros （访问日期：2026-08-20）
- **[S15] Unitree UnifoLM-WMA-0 官方仓库**：simulation/decision 两种模式、主视角限制、默认 16 维、G1 Dex1 路径。  
  https://github.com/unitreerobotics/unifolm-world-model-action （访问日期：2026-08-20）
- **[S16] Unitree WMA 官方训练入口与配置**：默认 8 GPU 进程及模型/时序配置。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/scripts/train.sh （访问日期：2026-08-20）  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/configs/train/config.yaml （访问日期：2026-08-20）
- **[S17] OpenVLA-OFT 官方仓库**：推理与训练显存范围、动作块输入输出示例。  
  https://github.com/moojink/openvla-oft （访问日期：2026-08-20）
- **[S18] OpenVLA-OFT 官方论文与项目页**。  
  https://openvla-oft.github.io/ （访问日期：2026-08-20）  
  https://arxiv.org/abs/2502.19645 （访问日期：2026-08-20）
- **[S19] SimFoundry 官方论文与 NVIDIA Research 项目页**：仿真排序与真实表现相关，但真实回合作为独立比较锚点。  
  https://arxiv.org/abs/2606.28276 （访问日期：2026-08-20）  
  https://research.nvidia.com/labs/gear/simfoundry/ （访问日期：2026-08-20）
- **[S20] scikit-learn Probability Calibration 官方文档**：reliability diagram、Brier score 的解释边界，以及校准不能只看单一汇总分数。  
  https://scikit-learn.org/stable/modules/calibration.html （访问日期：2026-08-20）
- **[S21] SciPy Bootstrap 官方文档**：bootstrap 置信区间的计算接口与方法边界。  
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html （访问日期：2026-08-20）
