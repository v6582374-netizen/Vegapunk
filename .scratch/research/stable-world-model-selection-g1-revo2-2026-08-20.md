# 稳定性优先：G1 + BrainCo Revo2 的现成世界模型第二轮选型

- 日期：2026-08-20
- 任务：Unitree G1 在固定操作位完成按钮、开盖、抓杯、倾倒姿态、放杯、关盖；第一阶段不要求行走。
- 非协商约束：**必须使用已公开、可下载的世界模型；不自建任务级预测模型；不把 VLA 当作世界模型。**
- 允许的适配：机器人驱动、相机接入、时间同步、动作/状态字段映射，以及对**官方现成世界模型**使用其官方训练或 post-training 流程。它们不构成新建预测模型。
- 证据范围：仅使用论文、官方仓库、官方模型页、官方文档；维护指标来自相应官方 GitHub 仓库/API，观察日期为 2026-08-20。
- 本文不修改已有研究文档，也不修改代码。

---

## 执行结论

### 没有完全匹配者

在所核验的现成世界模型中，**没有任何一个**同时满足：

```text
公开权重 + 官方训练/推理 + 持续维护
+ Unitree G1 真机部署
+ BrainCo Revo2 直接支持
+ 多相机原生训练
+ 26D / 高 DoF 现成动作域
+ 原生 PyTorch FSDP
```

尤其是：在各候选的官方仓库、论文、模型页和部署文档中，**未找到 BrainCo Revo2 的直接支持证据**。这是一条范围明确的负结论，不是说 Revo2 无法接入；而是说任何“开箱支持 Revo2”的承诺都没有一手依据。

### 最保守的现成模型选择

1. **运行时主世界模型：UnifoLM-WMA-0 Dual**
   - 原因：唯一同时具备 Unitree 官方 G1 数据、G1 实机部署路径、world-model interaction mode、完整训练/推理/部署代码的候选。
   - 代价：官方现成路径是 `G1 + Dex1`，训练仅主视角，默认最多 16 DoF；Revo2 和 26D 不属于现成 checkpoint 的已证实动作域。

2. **高 DoF / FSDP 的保守备选：Cosmos 3（优先 Edge/Nano，而非 Super）**
   - 原因：当前维护最活跃、训练基础设施最成熟的开放世界模型平台；官方支持 action-conditioned forward dynamics、LeRobot 数据、29D humanoid（AgiBot）动作域、原生 PyTorch FSDP/HSDP/DCP。
   - 代价：没有 Unitree G1 或 Revo2 直接部署证据；29D AgiBot 不是 26D Revo2 语义的同义词。它是**可用官方流程做适配的备选**，不是 frozen zero-shot 的 G1 方案。

3. **多相机的唯一严肃备选：Genie Envisioner GE-Sim**
   - 原因：官方代码/配置明确使用头部、左手、右手三视角和 LeRobot 风格数据，也公开 action-conditioned neural simulator。
   - 代价：维护/发布成熟度显著低于 NVIDIA Cosmos；无 Unitree G1/Revo2 直接证据；训练栈是 Accelerate + DeepSpeed ZeRO，而非原生 PyTorch FSDP；官方没有可验证的硬件下限。

### 不应组成“投票 ensemble”

最保守的组合不是让几个语义不同的世界模型投票。WMA 的 `G1/Dex1` 动作、Cosmos 的 `AgiBot 29D` 动作和 GE-Sim 的姿态/相机参数动作若没有经过验证就混在一起，会制造**虚假的多模型一致性**。

保守组合应是职责组合：

```text
主世界模型：WMA-0 Dual
    + 现有 G1 / Revo2 低层执行器
    + 非学习的动作/观察字段适配
    + 确定性的真机安全闸门

离线备选资格验证：Cosmos 3 Edge/Nano
    （只在相同真实起点、相同动作片段上做预测对比）

多相机资格验证：GE-Sim
    （仅当头部单视角确实不足以判断关键状态时引入）
```

不会让一个新自建预测器填补这些模型的缺口。

---

## 1. 筛选门槛

世界模型在本项目中必须能够表达：

```text
当前真机观察 + 已定义的候选动作片段
                    ↓
          动作之后的未来观察 / latent / 状态
```

因此，以下项目一律不因“能输出动作”而入选世界模型：GR00T、π0/π0.5、OpenVLA 等 VLA。它们可作为未来动作提议器，但不回答“该动作会在当前实验台产生什么后果”。

### 强制通过项

| 门槛 | 含义 |
|---|---|
| 权重与推理 | 能下载公开 checkpoint，且有官方可运行推理入口 |
| 训练可复现 | 官方仓库存在训练/post-training 代码，而不只是论文或 demo |
| 真动作条件 | 输入中有 robot action / state-action，而不是纯图像或纯文字续写 |
| 真实机器人关联 | 至少有官方真机证据；Unitree G1 优先，humanoid 次之，Franka 等仅作弱相关 |
| 动作/相机可适配 | 对 26D/高 DoF、多相机的支持必须区分“已验证”“配置可改”“完全无证据” |
| 基础设施 | 核验单卡/多卡与原生 PyTorch FSDP；不把“用了 PyTorch”误写为“支持 FSDP” |
| 维护 | 核验 release、源码最近提交、issue/fork 等；star/fork 只作弱信号，不作为结论 |

---

## 2. 结论总表

> `直接`：官方已有同一硬件/接口证据。`可配置`：源码或配置明确允许修改，但未证明目标组合。`无证据`：本次一手资料中未找到。`—`：官方未发布可验证信息，不猜测。

| 候选 | 现成权重 + 训练 + 推理 | 真 action-conditioned | G1 / humanoid / 灵巧手证据 | 多相机 | 26D / 高 DoF | 原生 PyTorch FSDP | 维护成熟度 | 结论 |
|---|---|---|---|---|---|---|---|---|
| **UnifoLM-WMA-0** | **是**：训练、interaction inference、decision deployment | **是**：world model + action head | **直接 G1**，但为 G1+Dex1；无 Revo2 | 训练**否**：仅主视角；硬件相机接入可配置 | 配置可改；默认 ≤16，26D 未证实 | **否（官方路径）**：Lightning DDPSharded / 可选 DeepSpeed | 中等：官方 G1 路径强，但无 GitHub release、最后源码提交较早 | **主选** |
| **Cosmos 3** | **是**：模型、Framework、SFT、推理、服务 | **是**：forward dynamics | 29D AgiBot humanoid domain；无 Unitree/Revo2 | 视频输入与 LeRobot；目标 humanoid 多相机 recipe **无证据** | **有 29D humanoid 官方域**；26D Revo2 仍无证据 | **是**：官方 FSDP/HSDP/DCP | **高**：正式 Cosmos3 release，主仓/Framework 持续更新 | **高 DoF / FSDP 备选** |
| **GE-Sim** | **部分**：公开权重与 GE-Sim inference；平台级 train/infer 代码公开，但 GE-Sim 专用训练 recipe 未单列 | **是** | 无 Unitree/Revo2 直接证据 | **直接三视角** | joint action 可配置；26D 未验证 | **否**：Accelerate + DeepSpeed ZeRO-2 | 中低：无 GitHub release、研究仓库节奏 | **多相机备选** |
| **V-JEPA 2-AC** | **是**：checkpoint、DROID post-train、CEM 示例 | **是**，latent prediction | Franka 真机；无 humanoid/G1 | **否**：官方 recipe 单 `left_mp4_path` | **否**：官方示例 7D | **否**：官方训练为 PyTorch DDP | 中等：Meta 官方、近期版本；无 release | 不进主路径 |
| **Cosmos-Predict2.5** | 是，且发布版本多 | 是 | robot action models；无 Revo2 | 有 robot multiview 路线 | EEF 7D 等；非现成 Revo2 | 旧栈，不作为新 FSDP 路径 | 维护已转移至 Cosmos 3 | 排除新建设 |
| **Ctrl-World / VLAW** | 是：checkpoint、训练、rollout | 是 | DROID/Franka；无 humanoid/G1 | multi-view | **否**：官方 `action_dim=7` | **否**：无官方 FSDP | 中低：无 release、源码节奏慢 | 仅借鉴评测机制 |
| **OSCAR-2B** | 权重 + 推理是；**训练代码未公开** | 是，skeleton-conditioned | AgiBot G1 demo；无 Revo2 | 不构成多相机现成方案 | 骨架可泛化，但 Revo2 未验证 | 无训练代码，不能评估 | 低：新仓库、无 release | 排除主选 |
| **DW05** | 权重/训练/推理称已公开 | 是 | 无 G1/Revo2 bridge | 多相机 JSONL | 未验证 | 无原生 FSDP 证据 | 低：2026-07 初发，Value Expert 尚待发布 | 排除主选 |
| **ω-0** | 未找到公开 repo/weight | 论文中是 | humanoid 真机论文 | 论文多视角 | whole-body latent | — | 论文线索，非生态 | 排除 |

---

## 3. 逐项核验

## 3.1 UnifoLM-WMA-0：唯一应先上真机资格验证的模型

### 已核实的现成能力

Unitree 官方 README 明确公开：

- Training、Inference、Checkpoints、Deployment；
- `G1_Pack_Camera` 数据集与 Unitree G1 实机 demo；
- world-model interaction mode（用于交互式 simulation）；
- decision-making server/client，客户端示例为 `--robot_type "g1_dex1"`；
- 自有数据转换至 **LeRobot V2.1** 的官方脚本。

其部署仓库还提供“新增自定义末端”和“新增相机”的正式接口文档：需要实现末端状态读写、控制写入、IK 等协议，或实现相机 `read/async_read`。这意味着 Revo2 的**设备驱动层**不是被硬编码封死的。

### 关键限制

这不等于 Revo2 已被模型理解：

1. 官方训练说明明说**模型训练只支持主视角相机**；多视角记录需要在训练 CSV 中移除。部署层能接腕部相机，不等于 world model 可以将其作为第二视觉条件。
2. 官方默认最大 DoF 为 16；虽然 README 允许修改 `agent_state_dim`、`agent_action_dim`，但当前可下载 checkpoint 并没有官方证据表明已在 26D Revo2 语义上训练/验证。
3. 官方预训练/真机链是 G1+Dex1，不是 G1+BrainCo Revo2。Revo2 的关节含义、动作范围和接触行为必须在 official WMA 的数据/配置中重新映射。
4. 现有训练主策略默认是 PyTorch Lightning `DDPShardedStrategy`；训练脚本支持 DeepSpeed 配置。仓库虽有 FSDP wrapping helper，但没有官方可直接复现的 `FSDPStrategy` 训练入口。因此不能称其“原生 PyTorch FSDP 已支持”。

### 多卡与硬件判断

- 官方 `scripts/train.sh` 示例使用 8 GPU 的 `torch.distributed.launch`。
- 官方没有发布完整 WMA post-training 的最低显存/主机内存预算；因此不对单卡全量训练作保证。
- 本项目已观察到 4090/32GB 只能勉强运行 action-head-only；这不应外推为 full WMA 的可行性。

### 稳定性/维护信号（弱到强分层）

- 强信号：供应商官方、完整 G1 部署链、训练/推理/数据转换文档齐备。
- 中信号：GitHub 约 1.1k star、140 fork、18 open issues（仅为 2026-08-20 快照，社区量级不是质量证明）。
- 负信号：无 GitHub release；仓库默认分支最近源码提交为 2026-03-18。仓库页面在 8 月仍有活动记录，但这不等同于版本化维护承诺。

### 判定

**主选，但只以“冻结现成 WMA + 官方适配路径”的方式启动。**

第一阶段不把腕部相机和 26D 同时塞进模型。先用头部主视角、现有可执行短动作，验证 WMA-0 Dual 是否对关键状态变化有预测能力。只有主视角通过后，才用官方 data conversion/train path 做 Revo2 action dimension 的 post-training；这仍是使用现成 WMA，而非自建世界模型。

**官方来源**

- [UnifoLM-WMA 官方仓库](https://github.com/unitreerobotics/unifolm-world-model-action)
- [WMA 官方自定义末端文档](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/docs/add_robot_endeffector.md)
- [WMA 官方自定义相机文档](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/docs/add_robot_camera.md)
- [仓库 commits](https://github.com/unitreerobotics/unifolm-world-model-action/commits/main)
- [仓库 releases](https://github.com/unitreerobotics/unifolm-world-model-action/releases)

---

## 3.2 Cosmos 3：维护和 FSDP 最成熟，但 G1 适配不是现成事实

### 已核实的现成能力

NVIDIA 的当前主线是 Cosmos 3，而不是已进入有限维护状态的 Predict2.5。Cosmos 3 官方仓库/Framework 明确提供：

- action-conditioned `forward_dynamics`：`image + action chunk → future video`；
- policy/inverse dynamics（这些是动作模型能力，不在本报告的世界模型结论中使用）；
- 公共模型系列：Edge 4B、Nano 16B、Super 64B；
- action domain 文档：单臂 10D、双臂 20D、**AgiBot humanoid 29D**；
- 模型输入支持 text/image/video/action，action 为 JSON 数组；
- Cosmos Framework：JSONL / WebDataset / **LeRobot** adapter、原生 PyTorch Distributed Checkpoint（DCP）、FSDP/TP/CP/PP；
- SFT 文档、checkpoint 导入导出、恢复、单 GPU inference，以及 8×H100 80GB 已测试训练 recipes。

训练文档写明：`distributed_parallelism="fsdp"` 是官方支持的训练并行模式；`data_parallel_shard_degree` 与 HSDP/context parallel 都有正式配置字段。这是本轮唯一明确满足“原生 PyTorch FSDP”要求的世界模型平台。

### 对本项目的关键限制

1. 官方 29D humanoid domain 是 **AgiBot**，没有声明 Unitree G1、Dex1 或 BrainCo Revo2 的动作语义兼容。
2. Cosmos 3 接受 video，但官方 DROID action policy recipe 的已验证数据是 LeRobot v3、8D joint position、`concat_view`；没有公开“G1+Revo2、头部+腕部、多视角、26D forward dynamics”的现成 recipe。
3. `raw_action_dim=26` 一类接口参数不能证明动作有正确语义。动作维数一致与关节/末端含义一致是两件事。
4. Edge/Nano 都不是“本机 4090 可无压力全量训练”的模型。官方推荐的硬件分别为 Jetson/Thor/RTX Pro 6000 与 RTX Pro 6000/H100/B200；官方 SFT recipes 在 8×H100 80GB 验证。
5. 官方也明确列出 action-state inconsistency、物体变形、3D/物理不准确等限制。它不应直接越过低层安全器下发控制。

### 稳定性/维护信号

- 强信号：NVIDIA 正式 `Cosmos3` release；独立 `cosmos-framework` 训练/服务仓；正式 SFT、DCP、FSDP、FAQ 与部署文档。
- 强信号：主仓最近源码提交 2026-08-18，Framework 最近源码提交 2026-08-19（研究日快照）。
- 弱信号：主仓约 11.6k star / 837 fork、Framework 约 476 star / 123 fork；这些只表示可见社区规模，不证明适配本任务。

### 判定

**作为高 DoF/FSDP 的保守备选，不作为首个真机主模型。**

当且仅当 WMA 在“主视角 + 既有短动作”上无法通过离线预测验收，才启动 Cosmos 3 Edge/Nano 的官方 forward-dynamics 路线。其优势是官方训练基础设施而不是对 Revo2 的零样本承诺。

**官方来源**

- [Cosmos 3 官方仓库](https://github.com/NVIDIA/Cosmos)
- [Cosmos Framework 官方仓库](https://github.com/NVIDIA/cosmos-framework)
- [Cosmos Framework 训练文档](https://github.com/NVIDIA/cosmos-framework/blob/main/docs/training.md)
- [Cosmos3 DROID action-policy 官方文档](https://github.com/NVIDIA/cosmos-framework/blob/main/docs/action_policy_droid_posttrain.md)
- [Cosmos 3 技术报告](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf)
- [Cosmos 主仓 commits](https://github.com/NVIDIA/Cosmos/commits/main)
- [Cosmos Framework commits](https://github.com/NVIDIA/cosmos-framework/commits/main)

---

## 3.3 Genie Envisioner GE-Sim：多相机能力最贴近，工程成熟度不够主选

### 已核实的现成能力

GE-Sim 是 Genie Envisioner 中 action-conditioned neural simulator 的组件。官方仓库提供：

- 平台级 GE-Base/GE-Act 的训练/推理入口与权重下载入口，以及 GE-Sim 的公开权重和专用 inference 入口；
- LeRobot 风格数据结构：Parquet state/action、视频、统计量；
- video adaptation 与 action post-training 的官方步骤（这些步骤主要面向 GE-Base/GE-Act，不能自动等同为 GE-Sim 专用训练 recipe）；
- 明确三视角配置：`head`、`hand_left`、`hand_right`；
- GE-Sim 输入为多帧多视角图像、相机内外参和 action `.npy`；
- Accelerate 分布式训练及可选 DeepSpeed ZeRO-2。

这使它成为唯一一个在公开配置层面已经接近“头部 + 腕部相机”形式的世界模型候选。

### 限制

- 没有独立、明确的 GE-Sim 专用 post-training recipe；因此它没有完整通过本轮“每个候选必须有可复现训练路径”的硬门槛。
- 没有 Unitree G1、BrainCo Revo2 的官方部署或动作接口证据。
- README 虽允许 `action_space: joint`、`absolute/delta/relative`，但没有证明 26D Revo2 数据或灵巧手动作已验证。
- 没有原生 PyTorch FSDP：公开栈是 Accelerate + DeepSpeed ZeRO-2。
- README 没有公布最低 VRAM、单卡训练的可重复基线或完整多卡容量预算。
- 仓库代码/数据许可并非统一宽松：部分是 Apache-2.0，其他部分为 CC BY-NC-SA 4.0，必须先核验比赛/后续使用合规性。

### 稳定性/维护信号

- 有持续功能发布记录（GE-Sim Cosmos 版、GE-Sim v2 项目页），但 GitHub 无版本化 release。
- 默认分支最近源码提交为 2026-06-24；约 574 star、27 fork、19 open issues 为弱信号。
- 这是有可运行实现的研究仓库，不能与 Cosmos 的平台化基础设施等同。

### 判定

**只有在“腕部相机是任务成败不可替代观测”且 WMA 单主视角失败时，才作为现成模型的第二阶段选择。**

它不要求新建预测模型，但在开始任何任务适配前，还必须先确认官方代码中 GE-Sim 的专用训练入口；否则它只能作冻结推理比较器。即使该入口成立，仍会带来相机标定、时间同步、Revo2 action adapter 与 DeepSpeed 环境维护风险。

**官方来源**

- [Genie Envisioner 官方仓库](https://github.com/AgibotTech/Genie-Envisioner-V1)
- [Genie Envisioner 论文](https://arxiv.org/abs/2508.05635)
- [官方 GE-Sim v2 项目页](https://ge-sim-v2.github.io/)
- [仓库 commits](https://github.com/AgibotTech/Genie-Envisioner-V1/commits/master)
- [仓库 releases](https://github.com/AgibotTech/Genie-Envisioner-V1/releases)

---

## 3.4 V-JEPA 2-AC：高质量研究基线，但不适合本轮“稳定落地”目标

### 已核实的现成能力

- 公开 Meta 官方代码、V-JEPA 2-AC checkpoint、DROID post-training config 和 CEM/energy-landscape 示例。
- 是真正的 action-conditioned **latent** world model；论文在 Franka 新环境上展示 image-goal planning 的真机结果。
- 训练源码将 encoder、predictor、target encoder 包装为 PyTorch `DistributedDataParallel`。

### 不满足处

- 官方 DROID config 使用单一 `left_mp4_path`、7D pose/action 示例；无 humanoid、G1、Revo2 或多相机官方路径。
- 没有官方 FSDP。作者的 action-conditioned config 是 4 节点 × 8 task、每 GPU 220GB 内存的参考训练配置，远超小规模落地；它也不是最低要求。
- 输出为 latent，不是可视 future video；将“按钮/盖子/杯子是否成功”转为 latent goal 会增加系统风险，而不是降低它。

### 判定

不作为稳定性优先的主选；保留为未来 research baseline。

**官方来源**

- [V-JEPA 2 官方仓库](https://github.com/facebookresearch/vjepa2)
- [V-JEPA 2 论文](https://arxiv.org/abs/2506.09985)
- [官方 DROID config](https://github.com/facebookresearch/vjepa2/blob/main/configs/train/vitg16/droid-256px-8f.yaml)
- [官方 CEM notebook](https://github.com/facebookresearch/vjepa2/blob/main/notebooks/energy_landscape_example.ipynb)
- [仓库 commits](https://github.com/facebookresearch/vjepa2/commits/main)

---

## 4. 明确排除项

| 项目 | 排除原因 |
|---|---|
| **Cosmos-Predict2.5** | 官方 README 已说明未来模型/文档/支持将聚焦 Cosmos 3。尽管它有 11 个 GitHub release、并被 OSCAR/GE-Sim 使用，但新项目不应把有限维护分支作为长期主依赖。 |
| **OSCAR-2B** | 有权重和漂亮的 skeleton action interface，也有 AgiBot G1 demo；但公开仓库仅含 inference/demo，没有训练/post-training 代码；无 release，最近提交 2026-06-16。未通过本轮硬门槛。 |
| **Ctrl-World/VLAW** | 机制非常有价值，但官方 config 固定 `action_dim=7`、主数据为 DROID；无 Unitree/humanoid 适配和原生 FSDP。应借鉴验收方法，不把它当部署组件。 |
| **DW05** | 2026-07 才初次公开，README 明说 Value Expert 未来才更新；维护和长期复现尚不足以承担主路径。 |
| **ω-0** | 论文很相关，但在本次一手来源范围内未找到公开代码、权重或部署接口。 |
| **UniSim / DeepMind Genie** | 是重要的神经模拟/交互世界研究，但没有可下载、可适配 G1+Revo2 的完整官方世界模型工程栈。 |
| **GR00T、π0/π0.5、OpenVLA** | 它们是 VLA/policy，不是世界模型；即使能输出动作，也不能承担当前闭环中的动作后果预测。 |

**官方来源**

- [Cosmos-Predict2.5 官方仓库](https://github.com/nvidia-cosmos/cosmos-predict2.5)
- [OSCAR 官方仓库](https://github.com/wuzy2115/oscar-public)
- [Ctrl-World 官方仓库](https://github.com/Robert-gyj/Ctrl-World)
- [DW05 官方仓库](https://github.com/dexmal/opendw)
- [ω-0 论文](https://arxiv.org/abs/2608.06375)
- [UniSim 论文](https://arxiv.org/abs/2310.06114)
- [Genie 论文](https://arxiv.org/abs/2402.15391)

---

## 5. 分阶段验收：不训练新模型，也不假装零样本

### Phase 0：接口事实核对，不调用模型

目标：证明现有 G1/Revo2 执行器可把一段已记录动作表示为 WMA 所需的 state/action，同时保存同步头部主视角。

验收：

- 使用官方 WMA 的 LeRobot V2.1 conversion path；
- 不改网络结构；
- 明确记录 Revo2 的 26D 表示与 WMA 默认 16D 的差异；
- 证明每个字段的单位、关节顺序、时钟一致；
- 无法采用非学习的安全映射时，停止，不把错误的 26D 数据硬塞进 checkpoint。

通过 Phase 0 并不表示模型有效，只表示可以开始测量。

### Phase 1：冻结 WMA-0 Dual 的离线预测验收

目标：只用现成、已下载 WMA 权重，测试它是否对本实验台有任何可用预测能力。

做法：

```text
真实 episode 的当前头部帧 + 真实短动作片段
                      ↓
              WMA interaction prediction
                      ↓
         与真实后续帧的关键状态变化比较
```

只评估五个外部可见事件：

1. 黄按钮是否被按到；
2. 杯是否被抓住；
3. 杯是否达到“倾倒姿态”；
4. 杯是否放回；
5. 绿按钮是否被按到。

通过标准不是视频是否好看，而是对**真实动作片段**能否稳定保留这些事件的时间顺序。

- 通过：WMA 可以进入小范围候选比较；
- 失败：不对 WMA 作“全量大训”承诺，转 Phase 2。

### Phase 2：二选一的官方模型适配

| 触发事实 | 采用的现成模型 | 使用的官方路径 | 不能声称的事 |
|---|---|---|---|
| WMA 的问题是 26D/Revo2 语义，而头部图像足够 | **WMA-0 Base/Dual** | 官方改 `agent_state_dim`/`agent_action_dim` 后的训练与 simulation-mode post-training | 不是自建世界模型；但也不是冻结权重零样本成功 |
| WMA 的问题是多相机缺失，腕部视角确实是关键 | **GE-Sim** | 官方 LeRobot 多相机 + GE video adaptation + GE-Sim inference；先核验 GE-Sim 专用训练入口 | 不是 G1/Revo2 已支持；不把平台级训练代码误称为 GE-Sim 已验证 post-training，也不把 DeepSpeed 当原生 FSDP |
| 需要可维护的高 DoF + FSDP 训练平台 | **Cosmos 3 Edge/Nano** | 官方 LeRobot/FSDP/DCP + forward dynamics 路线 | 29D AgiBot ≠ 26D Revo2；无 Unitree 直接部署保证 |

所有分支仍然使用公开基础 checkpoint、官方训练代码和官方模型结构；不添加新的任务级预测网络。

### Phase 3：有限真机闭环资格

仅在 Phase 1/2 的离线预测合格后：

```text
现成世界模型预测 2–3 个短候选
          ↓
安全器过滤
          ↓
执行一个短候选
          ↓
真机观察与预测比较
          ↓
下一轮
```

真机结果用于**校验现成世界模型是否可信**，而不是训练一个新预测器。若模型对当前操作台持续不校准，就应停止其作为选择依据的权限，而不是用更漂亮的视频掩盖失败。

---

## 6. 硬件决策

| 路径 | 可确认的硬件事实 | 当前硬障碍 | 建议 |
|---|---|---|---|
| WMA | 官方示例 8 GPU 分布式训练；无完整最低预算 | 26D full simulation post-train 显存未知；本机已经证明 full run 不适合 24GB/32GB | 仅做已下载权重的离线推理验收；任何 full post-train 迁到云端 |
| Cosmos 3 Edge/Nano | Edge 4B、Nano 16B；官方 SFT 已测试 8×H100 80GB；原生 FSDP/HSDP | 预训练/适配成本、模型文件和环境复杂度；没有 Revo2 recipe | 只有通过 WMA 失败门后，才租多卡做官方适配 |
| GE-Sim | 官方未承诺最低训练显存；依赖 LTX/Cosmos/DeepSpeed | 依赖与显存预算不确定，多相机增加显存与吞吐压力 | 先跑官方推理样例，再决定训练资源，不能先拍脑袋租卡 |
| V-JEPA 2-AC | 作者 config 为 32 GPU / 220GB-per-GPU 参考 | 单视角 7D 与高训练成本 | 不进入本轮算力计划 |

**不能因有 8×H100 就忽略接口错误。** FSDP 解决存储与参数分片，不会自动让 AgiBot 29D、Dex1 16D 或 Franka 7D 变成 Revo2 26D。

---

## 7. 最终决策记录

### 选定

```text
当前主路线：UnifoLM-WMA-0 Dual
角色：唯一首个进入 G1 真机资格验证的现成世界模型
视觉：第一阶段仅官方支持的主视角
动作：先核验、后映射；绝不假设 Revo2 已被预训练覆盖
训练：仅在冻结权重通过基础预测验收后，使用官方 WMA post-training
```

### 有条件备选

```text
高 DoF / FSDP：Cosmos 3 Edge/Nano
多相机：GE-Sim
```

### 明确不做

```text
不自建任务级预测模型
不将 VLA 写成“世界模型”
不让多个不兼容模型对动作投票
不在离线预测失败前租大规模训练算力
不把 Revo2 的设备驱动可接入误称为世界模型已适配
```

这条路线是“稳定性优先”的真实含义：先选择维护与部署证据最强的现成模型，再用可证伪的阶段门决定是否迁移；而不是因为某篇新论文更像愿景，就让它成为真机闭环的单点依赖。

---

## 8. 架构决策澄清：WMA 是兼容性基线，不是长期训练锁定

“首先用 WMA-0 Dual 验收”与“后续云端训练坚持原生 PyTorch FSDP”是两件不同的事：

```text
第一道兼容性门：冻结 WMA-0 Dual
  目的：用唯一具有 Unitree G1 官方部署证据的现成世界模型，验证
       当前主视角、动作字段与短操作片段是否可以进入世界模型链路。
  不做：不把旧 FairScale/DDPSharded 训练链作为长期基础设施。

长期可训练主线：Cosmos 3 Edge/Nano + 官方 FSDP
  触发：WMA 需要针对 Revo2/26D/多相机作有意义的训练适配，或者其冻结预测无法通过离线门。
  目的：在仍使用现成、维护活跃的基础世界模型前提下，走官方 FSDP/DCP 训练路径。
```

因此，WMA 不会因“G1 关联最直接”而把整个 Harness 锁定在过时训练框架；它的角色是把硬件兼容风险尽早暴露。Cosmos 也不会因“基础设施更新”而被误称为已经兼容 Revo2；它只有在规范动作适配和离线预测验证通过后，才是后续云端 FSDP 微调的正式平台。

---

## 9. BrainCo Revo2 官方是否提供可复用的预训练模型

截至 2026-08-20，在 BrainCoTech 官方公开仓库中，未找到面向 Revo2 的通用操作策略、VLA 或世界模型预训练 checkpoint。官方公开的 Revo2 资产主要是：SDK、ROS2/串口控制、URDF/mesh、G1 联合控制教程、遥操作重定向，以及触觉抓握示例。

`brainco-hand-sdk` 的 Revo2 触觉抓握示例包含很小的滑移/刚度识别模型，但它们只服务于触觉接触与自适应抓握，不是能够预测操作台后果或产生整套操作动作的世界模型/策略权重。

BrainCo 官方 `RevoLab` 确实发布了 Isaac Lab 强化学习 checkpoint 与 sim-to-real 部署代码，但当前公开任务面向 **Revo3 / RevoTron**，包括手内重定位、旋转、抬起和动态交接；不能直接作为 Revo2 权重使用。

因此，当前不存在可与 Unitree WMA Base 直接拼接的“BrainCo Revo2 预训练世界模型权重”。Revo2 的动作语义仍需通过现有示教数据或兼容的公开 G1+BrainCo 数据对所选现成世界模型进行 post-training。

官方来源：

- https://github.com/BrainCoTech/unitree-g1-brainco-hand
- https://github.com/BrainCoTech/brainco-hand-sdk
- https://github.com/BrainCoTech/revo2_description
- https://github.com/BrainCoTech/Revo-Retargeting
- https://github.com/BrainCoTech/RevoLab
