# UnifoLM-WMA-0 post-training：GPU 型号硬下限与候选全集

- 日期：2026-08-20（Asia/Shanghai）
- 任务边界：从官方 `UnifoLM-WMA-0-Base` 出发，执行完整 decision + simulation post-training；不是从 Open-X 重训 Base。
- 已确定资源：1 TB 本地 NVMe、256 GB 主机内存；训练时间不再是硬约束。
- 来源边界：Unitree 官方源码、PyTorch/PyPI 官方发布信息、NVIDIA/AMD 官方规格，以及 AutoDL 官方 GPU 类型 API。型号存在不等于实时有库存。

## 一句话结论

**当前软件栈的无迁移下限是 NVIDIA Ampere，当前项目的工程下限是单卡 80 GB；四卡正式档仍是 4×80/96 GB，但它不是数学上的总显存硬下限。**

放宽训练时间后，出现了一条更符合 Minimalism 的路线：

> **优先验证 1×H200 141 GB，micro-batch=1 + 梯度累积，先尝试在单卡上完成全部 decision + simulation。**

它可能用较低的“总显存”换掉 FSDP、NCCL 拓扑、跨 rank checkpoint 和多卡故障面。若实测激活峰值仍超过 141 GB，再退回 4×A100/A800/H100/H800/H20。单卡 H200 是条件路线，不是未经测试即可保证成功的配置。

Blackwell 容量更大，但**不是当前环境即插即用**：Unitree 精确锁定 `torch==2.3.1`、`torchvision==0.18.1`、`xformers==0.0.27`；PyTorch 官方的 2.3.1 二进制只提供 CUDA 11.8/12.1，而官方到 PyTorch 2.7 + CUDA 12.8 才引入 Blackwell 支持；PyPI 的 xformers 0.0.27 元数据又精确要求 `torch==2.3.1`。[S1][S4][S5][S6] 因此 B100/B200/B300/RTX PRO 6000/RTX 6000D 都要先升级 PyTorch、torchvision、xformers、CUDA 和驱动，并做算子、数值与 checkpoint 全回归。

## 1. “下限”必须拆成四层

### 1.1 指令集/软件下限

- **无需迁移的软件代际下限：Ampere。** A100/A800 可直接使用当前 PyTorch 2.3.1 + CUDA 12.1 路线；Hopper 同样处在现有 CUDA 12.x 支持范围内，但仍需匹配足够新的驱动。
- **Blackwell 必须迁移环境。** PyTorch 2.7 官方明确称其首次加入 Blackwell 支持并提供 CUDA 12.8 wheels。[S5]
- V100/Turing 并非每个 CUDA 算子都绝对不能执行，但其显存、混合精度能力和本项目的长训练风险共同使其不再属于合理候选。

### 1.2 单卡显存下限

本项目的**工程下限是 80 GB/卡**，不是 CUDA 的物理下限。原因是 FSDP 的总显存不能合并成一张虚拟大卡；每个 rank 仍需容纳当前 FSDP 单元的 all-gather、视频扩散激活、CUDA/xformers workspace、NCCL buffer 和碎片余量。当前 24 GB 4090 已无法承载完整目标，因此继续用 24/32/40/48 GB 卡堆数量是在扩大系统复杂度，而非解决主要约束。

### 1.3 总显存下限

应区分两条不同架构：

| 路线 | 实验下限 | 正式舒适档 | 含义 |
|---|---:|---:|---|
| 单卡、无参数分片 | **141 GB（1×H200，待实测）** | 180～288 GB（单 B200/B300，需 Blackwell 迁移） | 总显存全部由一个进程直接使用，避免 FSDP；micro-batch 降为 1 后用累积保持有效 batch |
| 多卡、FULL_SHARD | **188～192 GB（2×H100 NVL/H20，仅验证档）** | **320～384 GB（4×80/96 GB）** | 分片能降低持久状态，但每 rank 仍有激活峰值；四卡是首次正式长跑的工程余量 |

因此，先前的 320～384 GB 是**四卡方案的可靠性目标**，不是训练对象本身不可突破的硬容量定律。

### 1.4 互联下限

- 单卡路线没有 GPU 间互联问题。
- 两卡/四卡路线优先 SXM + NVLink/NVSwitch，或 NVIDIA 明确支持的 NVLink Bridge。
- “SXM”“NVL”是产品形态，不等于云实例必然把所租 GPU 放在理想拓扑；必须以目标实例的 `nvidia-smi topo -m` 和 NCCL 测试为准。
- PCIe-only 多卡并非不能训练，而是更慢、更依赖 wrap policy，且故障面更大，所以只列为条件候选。

## 2. 直接推荐：当前环境可走，容量和形态匹配

| 型号/形态 | 显存/卡 | 代际 | 建议卡数 | 总显存 | 互联形态 | 判断与主要风险 |
|---|---:|---|---:|---:|---|---|
| **H200 SXM** | 141 GB HBM3e | Hopper | **1 张先验收**；失败后 2/4 张 | 141 / 282 / 564 GB | SXM；多卡 NVLink 900 GB/s | **首个 Minimalism 候选。** 单卡可能容纳完整训练状态与 micro-batch=1 激活，从而删除 FSDP；141 GB 是否足够必须由完整 forward/backward + optimizer step + save/resume 测量。NVIDIA 官方规格为 141 GB、4.8 TB/s。[S10] |
| **A100 SXM4 80 GB** | 80 GB HBM2e | Ampere | **4 张** | 320 GB | HGX NVLink/NVSwitch；单 GPU NVLink 600 GB/s | **最低代际、最成熟的正式基线。** 性能较 Hopper 慢，但训练时间已放宽；必须确认不是 PCIe 40 GB 版本。NVIDIA 官方同时列出 80 GB SXM 和 PCIe。[S7] |
| **A800-80GB-NVLink** | 80 GiB | Ampere 出口变体 | **4 张** | 320 GiB | AutoDL 型号明确标记 NVLink；仍需实例验收 | **国内租赁直接候选。** 与 A100 同代，吞吐/互联受出口规格影响；AutoDL API 证明平台登记此型号与容量，不证明四卡库存或实际拓扑。[S3] |
| **H100 SXM 80 GB** | 80 GB HBM3 | Hopper | **4 张** | 320 GB | SXM，第四代 NVLink 900 GB/s | **性能型直接候选。** 比 A100 更快，但对于训练时间不限的当前小数据 post-training，是否值得溢价要看每个有效 step 的成本。[S8] |
| **H800 80 GB** | 80 GiB | Hopper 出口变体 | **4 张** | 320 GiB | 只在实例证明 NVLink/NVSwitch 时接受 | **条件通过拓扑后等同直接候选。** AutoDL API 只确认型号和容量，没有证明具体机器互联；不能从“H800”三个字推断拓扑。[S3] |
| **H20-NVLink** | 96 GiB | Hopper 出口变体 | **4 张** | 384 GiB | AutoDL 型号明确标记 NVLink；仍需实例验收 | **显存余量最大的国内常规四卡档。** 单步速度未必高于 H100/H800；应按完成同一有效 step 的总成本选择。[S3] |
| **H200 NVL** | 141 GB HBM3e | Hopper | **2 张或4张** | 282 / 564 GB | NVIDIA 官方 2-way/4-way NVLink bridge，900 GB/s/卡 | 若平台能提供官方形态，这是比四张 80 GB 卡更少 rank 的强候选；两张已提供较大容量与高速互联。风险是租赁形态少、价格可能过量。[S10] |

## 3. 条件可选：能形成方案，但必须先满足附加条件

| 型号/形态 | 显存/卡 | 代际 | 建议卡数 | 总显存 | 条件与风险 |
|---|---:|---|---:|---:|---|
| **H100 NVL** | 94 GB HBM3 | Hopper | **2 张一对**；需要更多容量时用两对 | 188 / 376 GB | 一对三桥 NVLink、600 GB/s；官方硬件指南明确每张卡只能桥接一张相邻 H100 NVL，因此四卡通常是两个高速对，不能视作四卡全互联。[S9] 2×94 GB 是迁移/正式可行性验证档，不是未经实测的保证档。 |
| **A100 PCIe 80 GB** | 80 GB HBM2e | Ampere | 4 张 | 320 GB | 官方 NVLink Bridge 只支持两卡；四卡一般形成两对并通过 PCIe 跨对通信。[S7] 若租价显著低且 NCCL 实测可接受，可以使用；否则选 SXM。 |
| **H100 PCIe 80 GB** | 80 GB HBM2e/HBM3（依官方具体 SKU） | Hopper | 4 张 | 320 GB | PCIe 形态的四卡通信弱于 HGX SXM；仅在机器拓扑和每 step 成本胜出时选择。若两卡配三桥，实质接近 H100 NVL 形态。 |
| **单 H200 141 GB** | 141 GB | Hopper | 1 张 | 141 GB | 虽列为首个推荐验收对象，但在验收前仍属于条件路线：把 batch 降至 1 不改变目标函数，可用梯度累积恢复有效 batch；若单步峰值超过约 125～130 GB 或 checkpoint/optimizer 初始化失败，停止继续压榨，改多卡。 |
| **B100** | 本次未取得可用于采购验收的现行官方单卡规格 | Blackwell | 只有云商能给出真实 NVIDIA SKU 后才讨论 | 不预先承诺 | **当前不应按型号名采购。** NVIDIA 当前 HGX 产品页重点列 B200/B300，缺少同等级的现行 B100 单卡产品规格/标准租赁形态；同时必须升级至 PyTorch 2.7+/CUDA 12.8。只有供应商提供官方 SKU、显存、驱动与拓扑证据后才进入测试。 |
| **B200** | HGX 当前总显存约 1.4 TB/8 GPU，即约 180 GB/卡 | Blackwell | **1 张切片可先验收**；标准 HGX 是8张 | 约180 GB/张；HGX约1.4 TB | 单卡容量比 H200 更可能消除 FSDP，但当前 Unitree 依赖必须整体升级。NVIDIA 当前官方 HGX 页面显示 HGX B200 是 8×Blackwell SXM、总显存约1.4 TB、第五代 NVLink 1.8 TB/s/卡。[S11] 整机8卡对本任务严重过量。 |
| **B300** | 288 GB 级 Blackwell Ultra | Blackwell Ultra | **1 张切片才合理**；标准 HGX 是8张 | 288 GB/张；整机约2.3 TB | 单卡容量几乎肯定优于 FSDP 复杂度，但必须升级软件栈，而且云商通常按 HGX B300 八卡交付。若只能租整机，应排除为性能冗余；官方页面列 8×Blackwell Ultra SXM、第五代 NVLink。[S11] |
| **RTX PRO 6000 Blackwell Workstation/Server Edition** | 96 GB GDDR7 ECC | Blackwell | 2 张验证；4 张正式候选 | 192 / 384 GB | NVIDIA 官方规格确认 96 GB、PCIe 5.0 x16，但规格表没有 NVLink 项。[S12] 因此只能按 PCIe 多卡处理；还必须升级 PyTorch/xformers。优势是大显存和可能较低价格，风险是通信、散热、600 W/卡与工作站平台稳定性。 |
| **RTX 6000D** | AutoDL API：84 GiB | Blackwell（平台登记） | 4 张 | 336 GiB | 截至研究日只有 AutoDL 官方 API 能证实平台名称和 84 GiB 容量，未找到可用于验收 NVLink/带宽的 NVIDIA 公开规格；同时需 Blackwell 软件迁移。仅当实例详情、驱动、拓扑和短程回归全部通过才使用。[S3] |

### Blackwell 的完整迁移门

Blackwell 候选不是“更新一个驱动”即可。至少需要：

1. PyTorch 升至 2.7 或更高，并使用 CUDA 12.8+ 官方 wheel；
2. torchvision 与 PyTorch 配对升级；
3. xformers 从绑定 torch 2.3.1 的 0.0.27 升级到匹配版本，重新验证 memory-efficient attention；
4. 复核 Lightning 1.9.3、FairScale `DDPShardedStrategy` 与新 PyTorch 的兼容性，或直接迁移到受支持的 native FSDP；
5. 对 Base 权重加载、完整 decision + simulation forward/backward、数值有限性、optimizer step、生成评估、checkpoint save/load 做 E2E 回归。

这组迁移成本可能高于 H200 单卡节省的硬件费，所以 **H200 是“减少分布式复杂度”的第一选择，B200/B300 是“容量更大但软件更复杂”的第二选择。**

## 4. 排除：不是物理不能算，而是不构成当前系统级候选

| 类别/代表型号 | 单卡显存 | 为什么排除 |
|---|---:|---|
| **48 GB 数据中心卡**：L40S、L40、L20、A40 | 48 GB | 总量可通过8卡堆到384 GB，但单 rank 激活/all-gather 余量小；L40/L40S/L20通常没有本任务需要的 NVLink，八个 rank 增加通信与失败面。只有80 GB级卡完全无货、并且8卡实测 E2E 通过时才可作为灾备，不属于采购候选。 |
| **48 GB 工作站卡**：RTX A6000、RTX 6000 Ada | 48 GB | A6000最多适合两卡桥接，RTX 6000 Ada为PCIe；要达到总量需更多卡，功耗、拓扑和散热不如四张80/96 GB数据中心卡。 |
| **A100 PCIe/SXM 40 GB** | 40 GB | 8×40 GB + NVSwitch 在技术上可能训练，但每 rank 只有40 GB，卡数翻倍且不比4×80 GB简洁；当前目标是降低系统失败概率，不是证明极限可跑。 |
| **RTX 5090/5090D** | 32 GiB | Blackwell 软件栈还需迁移，又无 NVLink；即使堆卡，总显存和单卡峰值都没有系统优势。AutoDL API确认其为32 GiB。[S3] |
| **V100 32 GB** | 32 GB | Volta代际过老、单卡容量低；需要更多卡和更复杂的通信，没有价格以外的架构价值。 |
| **RTX 4090/4090D** | 24 GiB | 本机实践已经证明完整目标不可承载；无 NVLink，堆8卡仍不解决单 rank 峰值，并增加八倍进程和通信面。 |
| **A30/L4/RTX A5000 等** | 24 GB | 容量低于已失败边界；不是正式 post-training 候选。 |
| **消费卡多机拼接** | 24～32 GB | 公网/普通以太网无法替代单机 NVLink/NVSwitch；跨实例 FSDP 将存储问题变成通信和可靠性问题。 |
| **8×B200 / 8×B300 整机** | 约1.4 / 2.3 TB | 硬件当然能跑，但对当前148 episodes post-training属于性能和成本冗余；只有未来变成 Base 预训练或多实验并行平台才重新进入范围。 |

48/40/32/24 GB 被排除的是**当前系统设计**，不是宣称任何此类 GPU 在任何 batch/wrap policy 下都绝对无法执行一条指令。这个区分很重要：我们是在采购一条长期可恢复的正式训练路径，而不是参加显存压榨竞赛。

## 5. AMD MI300X：容量合格，当前系统排除

MI300X 的 192 GB HBM3 在容量上非常适合单卡或少卡训练；AMD 官方定位也是 ROCm 数据中心加速器。[S13] 它被排除不是硬件性能不足，而是当前项目的软件本体是 CUDA 路线：

- Unitree 锁定的 PyTorch/xformers 组合是 CUDA 11.8/12.1 时代组合；
- 当前分布式、算子、容器、诊断和验收都围绕 CUDA/NCCL；
- ROCm 版 PyTorch 虽存在，但 xformers/自定义 attention、Lightning 1.9.3/FairScale、视频算子和 checkpoint 路径均需逐项移植验证；
- 这会把“选 GPU”升级为一个独立的软件移植项目，违背当前优先完成闭环的目标。

所以 MI300X 的分类是：**未来单独立项的可移植目标，当前采购排除。**

## 6. 最终采购顺序

### 若目标是最小化系统复杂度

1. **1×H200 141 GB**：做 100～200 step 的完整 decision + simulation E2E 验收；micro-batch=1、梯度累积保持有效 batch；必须包含退出进程后的 checkpoint 恢复。
2. 若单 H200 OOM，优先 **2×H200 NVL 141 GB**；它只引入两个 rank，官方支持2/4-way NVLink。
3. 若 H200 不可租或价格不合理，使用 **4×A100 SXM 80 GB** 或国内 **4×A800-80GB-NVLink**。
4. 吞吐成为成本主项时，再升 **4×H100 SXM/H800/H20**。

### 若目标是完全不动当前软件环境

只考虑 Ampere/Hopper：

```text
1×H200（单卡条件验证）
→ 2×H200 NVL
→ 4×A100/A800 80GB
→ 4×H100/H800 80GB 或 H20 96GB
```

### 若供应商只提供 Blackwell

按以下顺序：

```text
独立升级环境并完成E2E回归
→ 单B200/B300切片（若真实可租）
→ 2×RTX PRO 6000验证
→ 4×RTX PRO 6000/RTX 6000D
```

不因显存看起来充足而跳过软件迁移门。

## 7. 下单后的唯一验收门

任何型号只有同时通过以下流程才从“规格候选”升级为“项目可用”：

```text
完整模型初始化
→ decision + simulation forward/backward
→ 至少一次 optimizer step
→ 连续100～200 steps且无NaN/OOM
→ 保存完整训练状态
→ 退出所有进程
→ 新进程恢复 optimizer/scheduler/global_step
→ 再训练若干steps并生成一次评估样本
```

多卡额外验收 `nvidia-smi topo -m`、P2P/NVLink 状态和 NCCL 带宽。显存峰值最好低于物理显存约85%；若单 H200 长期高于约125～130 GB，应视为容错余量不足，而不是继续依赖偶然不 OOM。

## 一手来源

- **[S1] Unitree WMA `pyproject.toml`**：Python 3.10.18；torch 2.3.1、torchvision 0.18.1、xformers 0.0.27、Lightning 1.9.3、FairScale 0.4.13。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/pyproject.toml
- **[S2] Unitree 官方训练配置**：FP16、batch size 8、梯度累积2、decision + simulation 任务范围。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/configs/train/config.yaml
- **[S3] AutoDL 官方 GPU 类型 API**：研究日登记的 A800-80GB-NVLink、H20-NVLink 96 GiB、H800 80 GiB、RTX PRO 6000 96 GiB、RTX 6000D 84 GiB、A100 PCIe 40 GiB、RTX 5090/4090 等。  
  https://api.autodl.com/api/v1/machine/gpu_type
- **[S4] PyTorch 官方历史版本页**：2.3.1 官方 binaries 为 CUDA 11.8/12.1 与 ROCm 6.0。  
  https://pytorch.org/get-started/previous-versions/
- **[S5] PyTorch 2.7 官方发布说明**：首次引入 NVIDIA Blackwell 支持并提供 CUDA 12.8 wheels。  
  https://pytorch.org/blog/pytorch-2-7/
- **[S6] PyPI xformers 0.0.27 官方元数据**：`requires_dist` 包含 `torch==2.3.1`。  
  https://pypi.org/pypi/xformers/0.0.27/json
- **[S7] NVIDIA A100 官方规格**：A100 80 GB PCIe/SXM；SXM NVLink 600 GB/s，PCIe NVLink Bridge最多两卡。  
  https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet-nvidia-us-2188504-web.pdf
- **[S8] NVIDIA H100 官方产品页**：H100 SXM 80 GB、第四代 NVLink 900 GB/s；同时列出 H100 NVL 94 GB。  
  https://www.nvidia.com/en-us/data-center/h100/
- **[S9] NVIDIA H100 NVL 官方硬件指南**：94 GB HBM3/卡，三桥总600 GB/s；每卡桥接一个相邻卡。  
  https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/h100/PB-11773-001_v01.pdf
- **[S10] NVIDIA H200 官方规格**：H200 SXM/NVL均为141 GB、4.8 TB/s；SXM 900 GB/s NVLink；NVL支持2/4-way bridge。  
  https://www.nvidia.com/en-us/data-center/h200/
- **[S11] NVIDIA 当前 HGX 官方产品页**：HGX B200/B300的8卡形态、总显存、第五代NVLink与带宽。  
  https://www.nvidia.com/en-us/data-center/b200/
- **[S12] NVIDIA RTX PRO 6000 Blackwell Workstation Edition 官方规格**：96 GB GDDR7 ECC、PCIe 5.0 x16、600 W。  
  https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-6000-blackwell-workstation-edition/workstation-blackwell-rtx-pro-6000-workstation-edition-nvidia-us-3519208-web.pdf
- **[S13] AMD Instinct MI300X 官方产品页与 ROCm/PyTorch 官方安装文档**。  
  https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html  
  https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/3rd-party/pytorch-install.html

## 证据限制

- A800/H800/H20/RTX 6000D 是区域/出口 SKU；本研究能以 AutoDL 官方 API确认其平台型号与显存，但无法从匿名公开接口证明实时四卡库存和每台机器的实际互联。
- NVIDIA 当前公开产品页已将 HGX B200/B300作为在售主线；B100缺乏同等级的现行、可用于实例验收的公开系统规格。因此本文没有把“B100 192 GB”当成可直接采购事实。
- 单 H200 是否足够是由模型瞬时激活决定的实证问题。本文能证明其容量与软件代际匹配，不能在目标代码尚未跑过完整 step 前宣称必然成功。
