# AutoDL 上的 UnifoLM-WMA 全量训练算力研究

- **研究日期**：2026-08-20
- **目标**：为 `/home/loongge/unifolm-world-model-action` 的 UnifoLM-WMA 进行真正的联合训练，摆脱本机 RTX 4090 24GB 的资源边界。
- **本报告范围**：仅研究算力、显存、主机内存、存储和现有训练框架限制；未修改任何代码，也未创建 AutoDL 实例。
- **核心结论**：如果 AutoDL 控制台能够提供同一物理主机上的 8×H800 80GB，建议将其作为首选目标；如果没有，优先选择控制台实际可租的 8×A800-80GB-NVLink 或 8×H20-NVLink。8×A100 80GB 的“当前可租性”无法仅凭公开页面确认。

---

## 1. 先厘清“全量训练”到底是多少参数

本地已有训练日志给出：

| 模块 | 参数量 |
|---|---:|
| World Model | 2.51B |
| Action Head | 0.50B |
| State Head | 0.50B |
| **官方训练范围合计** | **2.56B** |
| **模型总参数** | **4.18B** |

这两个数字不能混为一谈。

### 1.1 官方 WMA 训练语义

官方配置中：

- `cond_stage_trainable: false`
- `freeze_embedder: true`
- 第一阶段 AutoEncoder 在源码中被固定为冻结；
- 图像投影器默认可训练；
- 将 `decision_making_only` 设为 `false` 时，动作头和状态头都参与训练。

因此，本项目此前所说的“真正全量联合训练”，按照官方 WMA 训练设计，实际是：

> **训练 World Model + Action Head + State Head，共约 2.56B 可训练参数；CLIP、图像编码器、AutoEncoder 等约 1.62B 参数保持冻结。**

这不是 4.18B 的每一个参数都更新。

### 1.2 字面意义上的 4.18B 全参数训练

如果未来连官方默认冻结的视觉编码器、文本编码器和 AutoEncoder 也全部解冻，则是另一种更重的任务：

> **4.18B 参数全部参与反向传播和优化。**

本报告同时给出这两种规模的预算，但推荐配置以更严格的 4.18B 字面训练为安全上界。

---

## 2. 4.18B 的基础内存预算

以下按十进制 GB 和二进制 GiB 同时给出。实际显存还会受到激活、CUDA workspace、通信 buffer、显存碎片和 batch size 影响。

### 2.1 仅模型权重

```
4.18B × FP16 2 bytes ≈ 8.36 GB ≈ 7.79 GiB
```

这只是加载模型，不是训练预算。

### 2.2 使用 AdamW 进行混合精度训练

一个保守的训练内存估算按每个可训练参数约 16 bytes：

- FP16 模型参数：2 bytes
- 梯度：约 2 bytes
- FP32 master weights：4 bytes
- AdamW 的一阶、二阶状态：8 bytes

因此：

| 训练范围 | 参数/优化器持久内存估算 |
|---|---:|
| 2.56B 官方可训练参数 | 约 40.96 GB / 38.15 GiB |
| 4.18B 全部可训练参数 | 约 66.88 GB / 62.29 GiB |

还要加上：

- 1.62B 冻结参数的权重；
- 中间激活；
- AutoEncoder 和 CLIP 的临时张量；
- 反向传播保存的激活；
- CUDA kernel workspace；
- 多卡通信 buffer；
- 显存碎片。

因此不能把“62 GiB”当作 80GB 显卡上的可用余量。对 4.18B 全参数训练：

> **单张 80GB 卡属于高风险；单张 96GB 卡只能作为未经验证的最低候选，不应称为绝对无 OOM。**

本地实测也支持这一结论：RTX 4090 上仅训练 0.52B action head，显存峰值已经约 23GB/24GB；官方 2.56B 全训练在 FairScale 优化器初始化阶段直接申请约 9.52GiB 额外显存并失败。

---

## 3. AutoDL 当前公开 GPU 信息

### 3.1 公开 GPU 类型接口

AutoDL 官方公开接口在 2026-08-20 返回了以下相关型号：

| 型号 | AutoDL 接口报告显存 | 接口备注 |
|---|---:|---|
| H800 | 80 GiB | 型号列出，但未公开库存 |
| A800-80GB-NVLink | 80 GiB | 型号名明确包含 NVLink |
| H20-NVLink | 96 GiB | 型号名明确包含 NVLink |
| RTX PRO 6000 | 96 GiB | Blackwell，型号列出 |
| A100-PCIE-40GB | 40 GiB | 当前公开接口列出的是 40GB PCIe 版本 |
| RTX 4090 | 24 GiB | 本机同级别 |

注意：

- 该接口证明型号被 AutoDL 平台登记；
- **不证明当前某个地区存在 8 卡空闲库存**；
- 也不证明这些卡一定能组成 8 卡同机实例；
- 价格字段不在该公开 GPU 类型接口中。

### 3.2 A100 80GB 的公开确认边界

NVIDIA 官方 A100 页面明确说明 A100 80GB 存在，且拥有超过 2TB/s 的显存带宽。

但是，AutoDL 当前公开 GPU 类型接口返回的是：

- `A100-PCIE-40GB`
- `A800-80GB-NVLink`
- `H800`

没有返回名为 `A100-80GB` 的当前型号记录。

AutoDL GPU 选型文档仍介绍了 A100 SXM4 的 40/80GB 版本，但这不足以证明当前可以租到 8×A100 80GB。因此：

> **“AutoDL 8×A100 80GB”只能作为控制台现场确认后的候选，不应在未登录控制台前视为已验证配置。**

---

## 4. 三档配置建议

### 4.1 最低可行：2×80/96GB，同一主机

**目标**：官方 2.56B 联合训练；若启用真正的参数分片，也可尝试 4.18B 字面全参数训练。

建议：

- GPU：优先 2×RTX PRO 6000 96GB；其次 2×H20-NVLink 96GB；再其次 2×H800/A800 80GB；
- 主机内存：至少 128GB；
- CPU：至少 16～24 个逻辑核心；
- 本地数据盘：至少 500GB；
- 训练方式：不能使用普通 DDP；需要参数/优化器分片；
- 适用：验证云端训练路径、跑通完整联合训练。

这档不是“绝对无 OOM”。它的意义是最低成本验证；如果代码仍使用当前 FairScale DDPSharded 实现，4.18B 全参数训练不应直接开始。

### 4.2 多余裕推荐：4×A800-80GB-NVLink 或 4×H20-NVLink

**这是更合理的正式训练配置。**

建议优先级：

1. **4×H20-NVLink 96GB**：总显存 384GB；
2. **4×A800-80GB-NVLink**：总显存 320GB；
3. **4×RTX PRO 6000 96GB**：总显存 384GB，但其 NVLink/同机互联能力不能从公开资料确认。

配套资源：

- 主机内存：至少 256GB，最好 512GB；
- CPU：至少 32 个逻辑核心，最好 48～64 个；
- 本地数据盘：1TB；
- 文件存储/网盘：另备 200GB 以上用于备份；
- 训练策略：DeepSpeed ZeRO-3 或成熟的 PyTorch FSDP；
- 训练目标：官方 2.56B 联合训练；也为 4.18B 全解冻留下显存余量。

这档的价值不是单纯“显存相加”，而是让每个 GPU 在参数分片之后仍有足够空间容纳激活、通信和临时张量。

### 4.3 极端稳妥：8×H800 80GB

**如果 AutoDL 控制台实际提供同一物理主机上的 8×H800 80GB，这是本项目最值得优先尝试的配置。**

资源建议：

- GPU：8×H800 80GB；
- 总显存：640GB；
- 主机内存：至少 256GB；为防止多进程加载 checkpoint 和数据预取，建议 512GB；
- CPU：至少 64 个逻辑核心；
- 本地数据盘：1TB～2TB；
- 备份文件存储：200GB～500GB；
- 训练策略：ZeRO-3 或 FSDP FULL_SHARD；
- 单机 8 卡，不建议拆成多台机器。

这档可以同时覆盖：

- 官方 2.56B 可训练参数的联合训练；
- 4.18B 全参数解冻的实验；
- 较大的 micro-batch；
- 梯度检查点关闭或部分关闭后的对照实验；
- 多组超参数复现实验。

### 4.4 A100 80GB 版本

如果控制台确实出现 8×A100 80GB 同机实例，则它的内存预算与 8×H800 80GB 基本同级：

- 总显存：640GB；
- 主机内存：建议 512GB；
- 本地数据盘：1TB～2TB；
- 优先使用同机多卡和 NVLink/高速互联；
- 使用 ZeRO-3/FSDP，而不是普通 DDP。

但当前公开资料无法确认 AutoDL 现阶段是否仍提供 8×A100 80GB，因此不把它作为已确认的采购结论。

---

## 5. 现有 WMA 代码对多卡训练的限制

### 5.1 当前默认策略是 DDPSharded

官方仓库的 `get_trainer_strategy` 默认返回：

```text
pytorch_lightning.strategies.DDPShardedStrategy
```

该策略基于 FairScale。它不是普通 DDP，但也不能直接等同于现代 ZeRO-3：

- 主要解决优化器状态分片；
- 参数和部分运行时数据仍可能在各 rank 保留；
- 单卡时几乎没有分片收益；
- 对 4.18B 全参数训练不能仅凭“用了 Sharded”就认为安全。

当前本机日志已经证明：1×RTX 4090 下，DDPSharded 在优化器初始化时仍然申请约 9.52GiB buffer 并 OOM。

### 5.2 FairScale/Lightning 版本已经过时

本地运行时明确产生了 Lightning 警告：

- FairScale sharded implementation 已弃用；
- Lightning 建议迁移到 native FSDP；
- 当前仓库使用的是 Lightning 1.9.3 体系。

因此，8 卡正式训练前必须先确认：

1. 当前版本的 DDPSharded 是否能在目标 GPU 数量下初始化；
2. checkpoint 是否能从单卡/多卡格式恢复；
3. 每个 rank 的 CPU checkpoint 加载峰值；
4. 训练中断后是否能够恢复 optimizer 和 scheduler 状态。

### 5.3 仓库存在 DeepSpeed 分支，但不等于已完成 ZeRO-3 集成

官方 `scripts/trainer.py` 会在配置中的策略名称以 `deepspeed` 开头时进入 DeepSpeed 分支，否则进入 DDPSharded 分支。

这说明仓库预留了 DeepSpeed 路径，但不能据此断言：

- ZeRO stage 已配置正确；
- 8 卡 H800/A100 已验证；
- 所有 checkpoint 格式都兼容；
- 图像日志、EMA、两个 diffusion head 都能在 ZeRO-3 下正常恢复。

因此：

> **ZeRO-3 是推荐的工程方向，但现有仓库的 DeepSpeed 分支仍需在云实例上做一次最小化验证；不能把“代码识别 deepspeed 字符串”当作完整支持证明。**

### 5.4 当前仓库没有明确的 FSDP 配置

仓库没有提供一个经过项目验证的 `FSDP FULL_SHARD` 配置。

Lightning 1.9 日志提到了 `fsdp_native`，但：

- 没有项目级 FSDP policy；
- 没有明确的 wrapping strategy；
- 没有验证两个 diffusion head、图像投影器和冻结视觉模块的组合；
- 没有验证 checkpoint 和 EMA 的恢复。

所以 FSDP 不是“直接改一个字符串就必然可用”。

---

## 6. 8 卡训练应如何落地

推荐的落地顺序不是直接提交长训练，而是：

### 阶段一：云实例资源验收

确认控制台中：

- 8 张 GPU 是否在同一实例；
- GPU 型号是否完全一致；
- 每 GPU 显存；
- 主机 RAM 是否达到 256GB/512GB；
- 是否支持高速互联；
- 本地数据盘容量和读写性能；
- 价格和库存。

### 阶段二：不训练的初始化测试

只做：

- 加载 9.8GB Base checkpoint；
- 构建 4.18B 模型；
- 构建 optimizer；
- 初始化多卡策略；
- 退出。

必须记录：

- 每个 rank 的显存峰值；
- 主机内存峰值；
- 初始化耗时；
- 是否存在 checkpoint 加载复制；
- 是否存在 NCCL/互联错误。

### 阶段三：极短联合训练

设置极少 steps，仅验证：

- World Model、Action Head、State Head 是否都产生梯度；
- loss 是否正常；
- 无 CUDA OOM；
- 无 CPU OOM；
- checkpoint 是否能保存；
- 从 checkpoint 是否能恢复。

### 阶段四：正式训练

只有阶段三通过后，才进行长时训练。正式训练必须：

- 使用本地 SSD 数据盘；
- 定期将 checkpoint 复制到 AutoDL 文件存储和实验室本地；
- 只保留少量权重 checkpoint；
- 单独保存可恢复训练的 optimizer checkpoint；
- 持续监控显存、主机 RAM、磁盘和 NCCL 状态。

---

## 7. 数据、权重、checkpoint 和环境存储规划

### 7.1 当前已知容量

本地实测：

- WMA Base checkpoint：约 9.8GB；
- 1000-step 训练 checkpoint：约 9.4GB；
- 原始/转换后的实验数据：约 2GB 级别；
- 当前 conda 环境：约 9.2GB；
- WMA 仓库：约 0.3GB。

### 7.2 AutoDL 目录建议

| 内容 | 推荐位置 |
|---|---|
| 操作系统和基础镜像 | 系统盘 |
| Python/Conda 环境 | 系统盘；若空间不足再放数据盘 |
| WMA 代码 | 系统盘或数据盘 |
| Base 权重 | 本地数据盘 |
| 训练数据 | 本地数据盘 |
| 临时缓存 | 本地数据盘 |
| 当前训练 checkpoint | 本地数据盘 |
| 长期备份 checkpoint | 文件存储 + 实验室本地 |

AutoDL 文档说明：

- 系统盘约 30GB；
- 数据盘从 50GB 起，可扩容；
- 数据盘是本地盘，读写快但没有冗余副本；
- 文件存储是网络盘，适合共享和备份，不适合承担全部训练热路径。

因此正式 8 卡训练至少租：

> **1TB 本地数据盘；如计划保存多组 full-res checkpoint，则租 2TB。**

### 7.3 Checkpoint 预算

- 权重-only checkpoint：约 9～10GB/个；
- 可恢复训练 checkpoint：还要包含 optimizer、scheduler 等状态，保守按 40～80GB/个规划；
- 5 个权重 checkpoint + 2 个可恢复 checkpoint，建议预留至少 200～300GB；
- 为避免日志、缓存和临时文件挤占空间，1TB 是更合理的起点。

---

## 8. 价格和可用性

本报告不填猜测价格。

AutoDL 官方价格文档明确要求：

> 各型号 GPU 价格以网站显示的现价为准。

公开未登录接口可以确认 GPU 型号和显存，但不能确认：

- 某个地区当前的按量价格；
- 包年包月价格；
- 8 卡同机库存；
- 8 卡机器的主机内存配置；
- 是否存在 NVLink/IB；
- 当前是否可以立即开机。

因此最终采购动作必须在 AutoDL 登录控制台中确认。当前最可靠的选择顺序是：

1. **8×H800 80GB，同机，RAM≥512GB**；
2. **8×A800-80GB-NVLink，同机，RAM≥512GB**；
3. **8×A100 80GB，同机，仅在控制台明确显示时采用**；
4. 如果只能拿到 4 卡：选择 4×H20-NVLink 96GB 或 4×A800-80GB-NVLink。

---

## 9. 最终建议

### 推荐目标

> **AutoDL 单机 8×H800 80GB；主机内存 512GB；CPU 64～96 逻辑核心；本地 SSD 数据盘 1～2TB；采用 ZeRO-3 或 FSDP FULL_SHARD。**

如果控制台没有 8×H800：

> **优先改为 8×A800-80GB-NVLink。**

如果 AutoDL 只有 8×A100 80GB：

> **可以使用，但必须以控制台实时显示为准；不要依据搜索结果或历史型号列表下单。**

### 关键边界

- 8×GPU 不是自动解决 OOM；训练策略必须真正做参数/优化器分片；
- 当前 DDPSharded 是过时的 FairScale 路径，不能视为现代 ZeRO-3；
- 当前仓库没有经过验证的 FSDP FULL_SHARD 配置；
- DeepSpeed 分支存在，但需要云端最小化验收；
- 主机内存和本地磁盘同样是训练资源，不能只看显存；
- 本报告的配置可以把硬件 OOM 风险压到很低，但在代码策略和 checkpoint 加载路径未验收前，不能承诺“绝对不会 OOM”。

---

## 一手来源

### AutoDL 官方

1. GPU 类型公开接口  
   https://api.autodl.com/api/v1/machine/gpu_type

2. AutoDL GPU 选型与 CPU/内存分配  
   https://www.autodl.com/docs/gpu/

3. AutoDL 多机多卡并行说明  
   https://www.autodl.com/docs/distributed_training/

4. AutoDL 计费说明  
   https://www.autodl.com/docs/price/

5. AutoDL 实例数据、系统盘、数据盘和文件存储  
   https://www.autodl.com/docs/instance_data/

6. AutoDL 网络说明  
   https://www.autodl.com/docs/network/

7. AutoDL 官方数据上传说明  
   https://www.autodl.com/docs/scp/

### NVIDIA 官方

8. NVIDIA A100  
   https://www.nvidia.com/en-us/data-center/a100/

9. NVIDIA RTX PRO 6000 Blackwell（作为 96GB 候选的官方显存参考）  
   https://www.nvidia.com/en-us/products/workstations/professional-desktop-gpus/rtx-pro-6000/

### Unitree / UnifoLM-WMA 官方

10. UnifoLM-WMA 官方仓库  
    https://github.com/unitreerobotics/unifolm-world-model-action

11. 官方训练配置  
    https://raw.githubusercontent.com/unitreerobotics/unifolm-world-model-action/main/configs/train/config.yaml

12. 官方训练入口  
    https://raw.githubusercontent.com/unitreerobotics/unifolm-world-model-action/main/scripts/trainer.py

13. 官方训练策略与 checkpoint 加载代码  
    https://raw.githubusercontent.com/unitreerobotics/unifolm-world-model-action/main/src/unifolm_wma/utils/train.py

---

## 不确定性声明

- AutoDL 的 GPU 型号公开接口不是库存接口；型号列出不等于 8 卡当前可租。
- AutoDL 未登录公开页面不能提供本次采购所需的实时 8 卡价格。
- 8×A100 80GB 在 NVIDIA 官方产品线存在，但 AutoDL 当前公开接口未返回该确切型号。
- H800 在 AutoDL 公开接口列出 80GiB，但其具体主机内存、互联拓扑和实时库存需登录控制台确认。
- 显存预算是工程预算，不是运行前的实测峰值。
- 现有 WMA 仓库的 DeepSpeed/FSDP 组合尚未在 8 卡目标环境验证。

