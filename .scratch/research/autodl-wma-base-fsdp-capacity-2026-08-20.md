# AutoDL 上 UnifoLM-WMA-0 Base 原生 FSDP 训练容量方案

- **研究日期**：2026-08-20（Asia/Shanghai）
- **任务**：以 UnifoLM-WMA-0 Base 为起点，在 G1 + BrainCo Revo2 的 148 episodes 上进行官方语义下的 **decision + simulation post-training**。
- **分布式方式**：单机多卡、原生 PyTorch FSDP `FULL_SHARD`。
- **目标**：不靠小显存勉强挤入，也不默认采购 8 张高端卡造成浪费。
- **外部取证边界**：AutoDL 官方网站、帮助文档、官方 API 和官方可验证实例信息。未采用第三方报价、云 GPU 聚合站或搜索摘要。

---

## 结论

### 推荐：单机 4×A800-80GB-NVLink；H20-NVLink 作为同级竞价候选

正式训练的目标规格应为：

| 项目 | 验收规格 |
|---|---:|
| GPU | **单机 4×A800-80GB-NVLink**；若 4×H20-NVLink 96GB 的实时总价和实测每 step 成本更优，则改选 H20 |
| 单卡显存 | A800 80 GiB；H20 96 GiB |
| 总显存 | 320 GiB；H20 方案为 384 GiB |
| GPU 互联 | 型号名由 AutoDL 明确标注 `NVLink`；下单后仍应运行 `nvidia-smi topo -m` 验收 |
| CPU | **至少 32 个逻辑核心，建议 48～64 个** |
| 主机内存 | **至少 256GB**；不是默认追求 512GB |
| 系统盘 | 只容纳系统、代码和轻量环境；有效可用空间不足 60～80GB 时，将 Conda、HF 缓存迁到数据盘 |
| 本地数据盘 | **1TB 本地 SSD 推荐；500GB 是最低验收线** |
| 远端备份 | 200GB 起的文件存储；更多容量需按 checkpoint 保留策略决定 |
| 网络 | AutoDL 官方称同地区共享约 3～10Gbps、上下行相等；仅用于下载和备份，不承担 FSDP rank 间通信 |

这是一档“有余量但不过量”的配置。148 episodes 很小，本次是下游 post-training，而不是从零预训练 4.18B 模型；只要 FSDP 确实执行参数、梯度和优化器状态分片，默认上 8×80/96GB 没有充分理由。

### 为什么不是 2 卡

2×H20-NVLink 96GB 或 2×A800 80GB 很可能可以完成初始化甚至训练，但它仍属于**云端迁移验证档**，不属于本报告的正式稳妥档：

1. 当前任务第一次迁移到原生 FSDP，模型 auto-wrap、冻结模块、激活峰值和 checkpoint 聚合峰值尚未在云端测量；
2. WMA 同时训练 simulation/world-model 路径和 decision/action-state 路径，显存压力不能只用参数量推断；
3. 省下两张卡，却把正式训练变成反复处理 OOM 和低吞吐，并不是真正省钱。

### 为什么不默认 8 卡

8×A800/H800/H20 是容量兜底，不是默认采购：

- 148 episodes 不构成基础模型预训练的数据规模；
- 4×80/96GB 在 `FULL_SHARD` 下已经有 320～384GiB 聚合显存；
- 只有 4 卡短程验收出现**不可通过合理 batch、activation checkpointing 和 wrap policy 解决的实测 OOM**，或 8 卡的实测单 step 成本反而更低，才升级 8 卡。

---

## 1. 训练对象与容量边界

### 1.1 这里不是“4.18B 全部解冻”

当前工作区已经核验：

| 项目 | 数值 |
|---|---:|
| 模型总参数 | 约 4.18B |
| 官方 decision + simulation 配置下可训练参数 | 约 2.56B |
| 冻结参数 | 约 1.62B |
| 数据 | 148 episodes，约数 GB 量级 |
| Base checkpoint | 约 9.8GB |
| 已生成的 1000-step checkpoint | 约 8.8～9.4GB |

因此，本报告中的“官方 decision + simulation post-training”是：更新 world/simulation 与 action/state 决策相关参数，同时保留官方配置中的冻结视觉、文本或 AE 模块；它不是把 4.18B 全部参数解冻后重新预训练。

### 1.2 FSDP 的作用

原生 FSDP `FULL_SHARD` 要分片的是：

- 可训练参数；
- 梯度；
- AdamW 优化器状态。

按混合精度 AdamW 的常见持久训练状态粗略预算，可训练参数约需 `16 bytes/parameter`：

```text
2.56B × 16 bytes ≈ 40.96GB（全局持久训练状态）
```

四卡理想分片后约为每 rank 10.24GB，再叠加：

- 冻结权重；
- 当前 FSDP 单元 all-gather 的完整参数；
- 视频/图像扩散网络的激活；
- CUDA kernel workspace；
- NCCL buffer；
- 日志、EMA 或 checkpoint 临时副本；
- 显存碎片。

这解释了两个结论：

1. **4×80GB 并不是因为静态参数本身需要 320GB，而是给未知激活峰值和首次 FSDP 迁移留出工程余量。**
2. **GPU 总显存不能当成一张大显卡使用。** 如果 wrap policy 错误、某个巨型模块未分片或 checkpoint 路径在单 rank 聚合，仍然可能 OOM。

### 1.3 质量边界

本方案不通过以下方式换取“能跑”：

- 不关闭 simulation/world-model loss；
- 不退回 action-head-only；
- 不降低输入语义或删除相机流来规避显存；
- 不以 CPU offload 作为默认长期方案；
- 不用 24GB 消费卡堆数量替代单卡显存和互联。

可以采用的内存优化只有不改变训练目标的工程手段：混合精度、activation checkpointing、合理 micro-batch、梯度累积、FSDP `FULL_SHARD` 和 sharded checkpoint。

---

## 2. AutoDL 当前能够被官方公开信息确认的 GPU

AutoDL 官方 GPU 类型 API 在研究日列出了：

| AutoDL 型号名 | 官方 API 显存 | 多卡/NVLink 的公开证据 | 本任务判断 |
|---|---:|---|---|
| `A800-80GB-NVLink` | 80 GiB | 型号名明确写明 NVLink；AutoDL 支持同实例租多卡 | **首选候选** |
| `H20-NVLink` | 96 GiB | 型号名明确写明 NVLink；GPU 文档还列出北京 A 区和 L20 专区对应 CPU | **首选候选** |
| `H800` | 80 GiB | API 确认型号和显存，但公开文档未确认具体出租主机的 NVLink 拓扑 | **条件候选** |
| `A800-80GB` | 80 GiB | 型号名没有 NVLink 标识 | 只有实例详情和拓扑验收通过才考虑 |
| `RTX PRO 6000` | 96 GiB | API 确认显存；公开资料不能确认 AutoDL 出租实例的 NVLink/多卡拓扑 | 不作为正式首选 |
| `PRO 6000 Max-Q` | 96 GiB | 同上 | 不作为正式首选 |
| `RTX 6000D` | 84 GiB | 无公开 NVLink 证据 | 不作为正式首选 |
| `A100-PCIE-40GB` | 40 GiB | API 当前列出的是 PCIe 40GB | 不选 |
| `RTX 5090/5090D` | 32 GiB | 无本任务所需互联与单卡显存余量 | 不选 |
| `RTX 4090/4090D` | 24 GiB | 单卡显存不足；AutoDL 文档也指出 4090 多机多卡效率低 | 不选 |

必须区分：**GPU 类型 API 只证明平台登记了这种型号，不证明研究时刻存在四张同机空闲卡，也不提供该主机的 RAM、CPU、数据盘和价格。**

AutoDL 算力市场的机器搜索、机器详情和地区 GPU 接口在未登录时返回 `AuthorizeFailed`。因此，本次无法从公开一手接口验证四卡实例的实时库存与 GPU 小时价。

---

## 3. 推荐配置

### 3.1 首选采购规格：4×A800-80GB-NVLink，同一实例

| 资源 | 目标 |
|---|---:|
| GPU | 4×A800-80GB-NVLink |
| 单卡/总显存 | 80 / 320 GiB |
| CPU | 32 逻辑核心最低，48～64 更合适 |
| RAM | 256GB 最低验收线 |
| 系统盘 | 环境和代码可用空间 60～80GB；不足则环境迁数据盘 |
| 数据盘 | 1TB 本地 SSD |
| 文件存储 | 200GB 起，保存少量关键 checkpoint |
| 训练网络 | 单机 GPU 互联；不使用多机公网拼卡 |

选择它的依据不是“最高端”，而是三个边界同时满足：

1. 80GiB 单卡显存足够容纳 FSDP 临时全量单元、激活和通信余量；
2. 型号名明确带 NVLink，适合 FSDP 高频 all-gather/reduce-scatter；
3. 四卡比八卡更匹配 148 episodes 的 post-training 规模。

### 3.2 同级动态候选：4×H20-NVLink 96GB

H20 方案总显存为 384GiB，比 A800 方案每卡多 16GiB。AutoDL GPU 文档明确提到：

- 北京 A 区 H20-NVLink 使用 AMD EPYC 9K84；
- L20 专区的 H20-NVLink 使用 Xeon Platinum 8457C。

它不是无条件高于 A800。下单决策应使用**通过相同 100～200 step 验收后的每有效 step 成本**：

```text
每 step 成本 = 实例总小时价 ÷ 每小时完成的有效 steps
```

若 H20 的实时总价更高但没有带来对应的吞吐或稳定性收益，选 A800；若 A800 库存不足、RAM 配置较低，或显存峰值过于贴线，则选 H20。

### 3.3 推荐配置的验收条件

控制台下单前必须同时满足：

- 四张相同 GPU 位于**同一个实例/同一物理主机**；
- 空闲 GPU 数不少于 4；
- 控制台每 GPU RAM × 4 后达到 256GB；
- 控制台每 GPU CPU × 4 后达到至少 32 逻辑核心；
- 本地数据盘可扩至至少 500GB，建议 1TB；
- 实例开机后 `nvidia-smi topo -m` 显示 GPU 间存在预期高速互联；
- 100～200 steps 中，单卡峰值显存最好不超过物理显存的约 85%，主机 RAM 峰值最好不超过配额的约 75%；
- sharded checkpoint 能保存，并能在新进程中恢复至少一次。

最后三项是项目验收阈值，不是 AutoDL 对硬件的保证。

---

## 4. 保守备选

### 4.1 4×H20-NVLink 96GB

当 4×A800 的任一条件不满足时，H20 是最自然的保守备选：总显存增加到 384GiB，同时保留明确的 NVLink 标识。主机内存仍以 256GB 为最低线，不因为显存更大就自动放宽 RAM 要求。

### 4.2 8×A800-80GB-NVLink

只在以下任一条件成立后采用：

- 4 卡验收中，正确的 `FULL_SHARD`、activation checkpointing 和 micro-batch=1 仍出现不可接受的 OOM；
- 4 卡单次正式训练耗时超过实验迭代周期，而 8 卡实测扩展效率足以降低每次训练的总占用成本；
- 8 卡包日/包周总价与 4 卡实际完成同一训练的总成本接近，且库存更稳定。

规格：

| 资源 | 目标 |
|---|---:|
| GPU | 8×A800-80GB-NVLink |
| 总显存 | 640 GiB |
| CPU | 至少 64 逻辑核心 |
| RAM | 512GB 建议；256GB 只有在 sharded checkpoint 实测无 CPU 聚合峰值时才接受 |
| 数据盘 | 1TB；多组实验可用 2TB |

### 4.3 8×H800 80GB：必须先证明拓扑

AutoDL API 确认 H800 80GiB 型号存在，但公开资料没有给出当前可租 H800 主机的互联拓扑。它只有在控制台和开机验收同时证明以下内容时才进入备选：

- 八卡同机；
- 高速 GPU 互联满足 FSDP；
- RAM 至少 512GB；
- 实时价格相对 4 卡方案有训练时长或稳定性的合理回报。

不能因为型号叫 H800 就自行推断当前出租实例一定具备完整 NVLink/NVSwitch 拓扑。

### 4.4 2×H20/A800：仅用于迁移验证

可用于：

- 安装环境；
- 验证 native FSDP 初始化；
- 跑 10～50 steps；
- 验证 sharded checkpoint 保存/恢复。

它不应在没有四卡实测前直接承担长时间正式训练。调试结束后可利用 AutoDL 的升降配置能力改为 4 卡；但按量实例关机后 GPU 不预留，正式训练若要求不中断，应在控制台比较包日/包周。

---

## 5. 不可选

### 5.1 24GB、32GB、40GB 单卡

包括：

- RTX 4090/4090D 24GB；
- RTX 5090/5090D 32GB；
- A100-PCIE-40GB；
- 任何由这些卡组成、但仍让单 rank 只有 24～40GB 的正式训练实例。

原因不是“总显存相加不够”，而是 FSDP 的临时 all-gather、激活和 CUDA workspace 都受单卡物理显存约束。当前本机 4090 上仅 action-head-only 就已接近 24GB 峰值，回到 decision + simulation 不应继续围绕小显存做妥协。

### 5.2 8×4090/4090D

AutoDL 官方可验证的 8×4090D 整机实例采用 PCIe 4.0 x16，并配 512GB RAM 和双口 25G 网卡；该页面是整机售卖信息，不是云租赁报价，也没有给出 NVLink。它能证明 AutoDL 存在八卡消费 GPU 服务器形态，但不能证明它适合本次 FSDP。

本任务不选择它：

- 每卡仍只有 24GB；
- FSDP 通信频繁，PCIe 多卡不能替代 NVLink；
- 八卡进程、通信和故障面更大，却没有解决单卡峰值边界。

### 5.3 多机拼卡

AutoDL 官方多机多卡文档明确表示：已不再支持通过开通内网 IP 进行多机多卡并行，并首推同一实例内的单机多卡。故本任务只接受单机 4 卡或单机 8 卡，不设计跨实例 FSDP。

### 5.4 无法确认同机拓扑的 96GB 卡

RTX PRO 6000、PRO 6000 Max-Q 虽有 96GiB，但 AutoDL 公开信息不足以证明多卡出租实例的 NVLink 拓扑。除非控制台实例详情和开机后的 `nvidia-smi topo -m` 同时通过，否则不能只看显存购买。

### 5.5 vGPU

不选 vGPU-32GB/48GB。模型训练需要稳定、独占和可验证的多卡拓扑；AutoDL 文档确认普通 GPU 实例为 GPU 独占，本任务没有使用 vGPU 换成本的必要。

---

## 6. CPU 与主机内存

AutoDL 官方说明：算力市场展示的是**每 GPU** 分配的 CPU 和内存，租用多张 GPU 时按卡数同比增加；并建议每 GPU 至少配 4～8 个 CPU 逻辑核心。

本任务的控制台筛选规则应为：

| 四卡实例每 GPU 展示值 | 四卡总量 | 判断 |
|---|---:|---|
| 4 CPU 逻辑核心/GPU | 16 | 不选，视频解码与四个 rank 容易抢 CPU |
| 8 CPU 逻辑核心/GPU | 32 | 最低可接受 |
| 12～16 CPU 逻辑核心/GPU | 48～64 | 推荐 |
| 32GB RAM/GPU | 128GB | 不选 |
| 64GB RAM/GPU | 256GB | 推荐最低线 |
| 128GB RAM/GPU | 512GB | 极稳，但只有价格合理或 checkpoint 路径仍会聚合时才购买 |

主机内存必须留余量。AutoDL 文档明确说明：实例超过内存配额会直接被系统 Kill，不能把本地电脑依赖 swap 的经验带到云实例。

---

## 7. 系统盘、数据盘与 checkpoint

### 7.1 热路径

AutoDL 官方说明系统盘和数据盘通常是本地 SSD，少数为云盘；本地数据盘性能好但没有冗余可靠性承诺。因此：

| 内容 | 位置 |
|---|---|
| 系统、驱动、最小运行环境 | 系统盘 |
| Conda 环境（系统盘不足时） | 本地数据盘 |
| Base checkpoint | 本地数据盘 |
| 148 episodes 及转换缓存 | 本地数据盘 |
| Hugging Face / open_clip 缓存 | 本地数据盘 |
| 当前训练的 sharded checkpoint | 本地数据盘 |
| 关键 checkpoint 副本 | AutoDL 文件存储 + 实验室本地 |

### 7.2 容量预算

已知静态内容只有约几十 GB，真正占空间的是可恢复 checkpoint：

- 代码、环境、Base 权重、数据、open_clip 和缓存：建议按 40～80GB 规划；
- 一个权重型 checkpoint：约 9～10GB；
- 一个包含 optimizer/scheduler 的 FSDP 可恢复 checkpoint：保守按 50～80GB 规划；
- 保留 3 个可恢复 checkpoint、5 个权重 checkpoint，再加临时文件和下一轮实验，约需 250～400GB。

所以：

- **500GB 是最低线**：只允许严格轮转 checkpoint；
- **1TB 是推荐值**：足够保留训练、转换缓存和一组对照实验；
- **2TB 默认浪费**：只有 8 卡、多组并行实验或大量生成视频时再扩。

### 7.3 数据保留风险

AutoDL 官方说明：实例连续关机 15 天后会被释放，实例数据清空；主机下架也可能释放实例。故本地数据盘不构成备份。

推荐保留策略：

- 数据集与 Base 权重在实验室保留原始副本；
- 云端只保留最近 2～3 个可恢复 checkpoint；
- 每个里程碑保存一个权重 checkpoint；
- 每次保存后异步复制到文件存储；
- 正式训练结束立刻下载最终权重、配置、指标和版本信息。

---

## 8. 网络

AutoDL 官方网络文档给出的平台级事实是：

- 同地区实例共享带宽；
- 一个地区约 3～10Gbps；
- 上下行带宽相等；
- 网络带宽和流量不单独计费。

这只适用于数据上传、模型下载和 checkpoint 备份。FSDP 的 rank 间通信必须在单台主机内部完成，不能把 3～10Gbps 公网带宽当作 GPU 互联带宽。

148 episodes 数据本身不大，网络不是主要训练瓶颈；10GB 级 Base 权重、约 4GB open_clip 和数十 GB checkpoint 的稳定传输才是重点。正式训练前应先把全部依赖下载到本地 SSD，避免训练进程启动时临时访问外网。

---

## 9. 价格、库存与“价格区间”的可信边界

### 9.1 GPU 租价：公开一手来源无法给出数值区间

AutoDL 官方价格文档对“各型号 GPU 价格”的表述是：**以网站显示的现价为准**。机器搜索与详情 API 需要登录；未登录请求返回授权失败。因此，在不使用第三方报价、不读取用户账户凭据的前提下，本报告无法可靠给出 2026-08-20 的 H20/A800/H800 每小时数字区间与四卡库存。

这不是遗漏，而是当前官方公开面的事实边界。任何具体的“¥X～¥Y/卡/小时”都会是猜测，违反本任务的一手来源要求。

控制台现场需要记录：

| 方案 | 总小时价公式 | 总日价公式 |
|---|---:|---:|
| 4×A800 | 控制台单卡小时价 × 4 | 总小时价 × 24，或直接使用控制台包日价 |
| 4×H20 | 控制台单卡小时价 × 4 | 同上 |
| 8×A800/H800 | 控制台单卡小时价 × 8 | 同上 |

若同一型号存在多台主机，则该时刻的**可验证价格区间**就是控制台中过滤“同型号、空闲卡数≥目标卡数、RAM/CPU/数据盘均达标”后，合格实例的最低价到最高价。不能先按价格排序，再忽略 RAM 和拓扑。

### 9.2 可公开核实的固定费用

AutoDL 官方价格文档当前可核实：

| 项目 | 官方价格 |
|---|---:|
| 文件存储 | 20GB 以下免费；超出部分 **¥0.01/GB/日** |
| 网盘 | 20GB 免费；扩容 **¥0.30/GB/月** |
| 镜像 | 30GB 以下免费；超出部分 **¥0.01/GB/日** |
| 无卡模式 | 0.5 核、2GB RAM、无 GPU，**¥0.1/小时** |
| 付费数据盘 | 以每台主机显示的实时单价为准 |
| 高速文件存储 | 以购买页面实时价格为准 |

例如文件存储实际占用 200GB 时，超出免费 20GB 的部分为 180GB，对应约 **¥1.8/日**。这一数字仅是官方存储公式的代入，不包含 GPU、数据盘和网络加速费用。

### 9.3 计费方式

AutoDL 官方说明：

- 按量实例开机开始计费、关机结束 GPU 计费；
- 按量关机后不预留 GPU，重新开机可能没有足够空闲卡；
- 包日/包周/包月会预留 GPU，价格通常相对便宜，但租期内开关机都计时；
- 付费数据盘即使实例关机仍会计费。

本任务应采用：

1. **按量 2 卡或 4 卡**完成环境、FSDP 和 100～200 step 验收；
2. 验收通过且预计连续运行超过一天后，再根据控制台实时价格转包日/包周；
3. 不在 FSDP 尚未通过 checkpoint 恢复前预付长周期。

---

## 10. 云端实施顺序

### 阶段 A：控制台筛选

只保留以下实例：

- 4×A800-80GB-NVLink 或 4×H20-NVLink；
- 同机空闲卡数 ≥4；
- RAM ≥256GB；
- CPU ≥32 逻辑核心；
- 本地 SSD 数据盘可到 500GB～1TB。

记录每台合格实例的：地区、GPU、每 GPU CPU/RAM、可租卡数、数据盘类型与单价、按量/包日/包周价格。

### 阶段 B：资源与拓扑验收

开机后确认：

- 四张卡型号、显存完全一致；
- `nvidia-smi topo -m` 的 GPU 间拓扑；
- 主机 RAM 和 CPU 配额与控制台一致；
- 数据盘确实为本地热路径；
- Base 权重、open_clip 和数据已完整落盘。

### 阶段 C：FSDP 短程验收

依次通过：

1. 模型与 Base checkpoint 加载；
2. optimizer 初始化；
3. 10 steps 前向/反向；
4. 100～200 steps 稳定运行；
5. 保存 sharded checkpoint；
6. 终止进程后恢复并继续训练；
7. 确认 simulation、action、state 三类 loss 都在工作。

只有这七项全部通过，才定义为“官方 decision + simulation 的云端训练链路已跑通”。

### 阶段 D：是否扩到 8 卡

以测量结果决定，不靠想象：

- 4 卡显存和 RAM 有健康余量、训练时长可接受：保持 4 卡；
- 4 卡稳定但太慢：租同型号 8 卡做 100～200 steps，比较扩展效率与每 step 成本；
- 4 卡 OOM：先证明 FSDP 分片和 wrap 正确，再决定是否 8 卡；不能用加卡掩盖实现错误。

---

## 11. 最终采购判断表

### 推荐

1. **单机 4×A800-80GB-NVLink，RAM≥256GB，CPU≥32 逻辑核心，1TB 本地 SSD。**
2. **单机 4×H20-NVLink 96GB** 与其竞价；用短程实测的每有效 step 成本决胜。

### 保守备选

1. 4×H20-NVLink：A800 不可租、RAM 不足或显存峰值贴线时。
2. 8×A800-80GB-NVLink：四卡已证明不足或八卡总训练成本更低时。
3. 8×H800 80GB：仅在控制台和拓扑验收明确证明同机高速互联后。
4. 2×H20/A800：只做 FSDP 迁移与短程验证，不直接定义为正式方案。

### 不可选

- 1～2×24/32/40GB 作为正式 decision + simulation 训练；
- 8×4090/4090D；
- 多机拼卡；
- vGPU；
- 无法确认 NVLink/同机拓扑的 RTX PRO 6000 多卡；
- 仅因型号高端而默认购买 8 卡。

---

## 官方来源

1. AutoDL GPU 类型 API（型号与显存）  
   https://api.autodl.com/api/v1/machine/gpu_type

2. AutoDL 地区 API  
   https://api.autodl.com/api/v1/region/list

3. AutoDL GPU 选型、CPU/RAM 按 GPU 数量分配、CPU 建议及 A100 NVLink 说明  
   https://www.autodl.com/docs/gpu/

4. AutoDL 单机/多机多卡说明  
   https://www.autodl.com/docs/distributed_training/

5. AutoDL 网络与共享带宽说明  
   https://www.autodl.com/docs/network/

6. AutoDL 实例数据保留与本地 SSD 风险  
   https://www.autodl.com/docs/instance_data/

7. AutoDL 计费方式、GPU 实时价格边界、文件存储/网盘/镜像价格  
   https://www.autodl.com/docs/price/

8. AutoDL 无卡模式与升降配置建议  
   https://www.autodl.com/docs/save_money/

9. AutoDL 官方 AI 服务器实例 API（8×4090D、512GB RAM、PCIe 4.0 x16、25G 网卡；整机售卖信息，不是云租价）  
   https://fe-config-backend.autodl.com/api/v1/autodl/aiserver

10. AutoDL 官方前端调用的算力市场接口（未登录返回授权失败）  
    https://api.autodl.com/api/v1/machine/search  
    https://api.autodl.com/api/v1/machine/detail  
    https://api.autodl.com/api/v1/machine/region/gpu_type

---

## 不确定性声明

- GPU 价格和库存会实时变化；本报告研究时，公开官方接口无法读取高端四卡实例的实时租价和库存。
- GPU 类型 API 中出现某型号，不等于该型号此刻存在四张或八张同机空闲卡。
- AutoDL 的 CPU/RAM 是按具体主机、按每 GPU 展示；报告给出的是采购验收线，不是对所有同型号实例的统一声明。
- `A800-80GB-NVLink` 和 `H20-NVLink` 的型号名提供了 NVLink 证据，但最终实例拓扑仍应开机实测。
- H800、RTX PRO 6000 的多卡互联不能由公开 AutoDL 信息充分确认。
- FSDP 显存预算是工程估算；真实峰值取决于 wrap policy、输入帧数、分辨率、激活检查点、micro-batch、精度和 checkpoint 实现。
- 4 卡是当前“不勉强、不浪费”的采购结论，不是对未经验收代码作出的绝对无 OOM 承诺。

---

## 12. 具体实例核验：A800专区 / 003机 `98fc43be4e`

用户控制台显示该机 GPU 名称为 `A800-80GB`，而 AutoDL 官方 GPU 类型 API 同时、分别登记了：

- `A800-80GB-NVLink`
- `A800-80GB`

因此 AutoDL 并未把 A800 默认等同为 NVLink；该实例在没有拓扑实测前必须按“NVLink 未证实”处理。炼丹平台、同机多卡和 GPU 独占都不能替代 NVLink 证据。

四卡资源换算为：56 个 CPU 逻辑核心、480GB 主机内存，二者都充分满足本任务。真正的阻塞是：数据盘只有 50GB 且不可扩容，无法安全容纳环境、Base/open_clip、数据缓存和 FSDP 可恢复 checkpoint；即使使用公网文件存储备份，训练热路径仍需要数百 GB 本地 SSD。

该机只有在以下两项同时解决后才可用于正式训练：

1. 按量开四卡后，`nvidia-smi topo -m` 显示目标 GPU 之间为 `NV#`，且 `nvidia-smi nvlink -s` 显示链路激活；
2. 能挂载/购买至少 500GB、建议 1TB 的高性能本地或官方高性能文件存储，并完成 checkpoint 写入/恢复吞吐测试。

否则不建议为正式训练购买该实例。
