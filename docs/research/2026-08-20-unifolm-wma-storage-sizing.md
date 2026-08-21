# UnifoLM-WMA-0 存储容量：从训练状态而非训练时长推导

日期：2026-08-20  
适用范围：以 `UnifoLM-WMA-0-Base` 为起点，在现有 G1 + BrainCo Revo2 数据上做 decision/simulation post-training。本文不估算从 Open-X 重新预训练 Base 所需的存储。

## 结论

**采购 1 TB 本地热 SSD/NVMe，并配置至少 500 GB、最好 1 TB 的远端文件/对象存储。**

容量档位应这样理解：

| 本地热盘 | 能力边界 | 判断 |
|---:|---|---|
| **200 GB** | 下载环境、Base、当前数据，做预飞和保存少量 weight-only checkpoint | **仅能启动**；一旦保存完整 optimizer resume，空间和崩溃余量都不足，不应承担正式长训练 |
| **500 GB** | 一次正式 post-training；严格保留 2 个 resume、3 个 weight-only，并立即异步备份 | **最低正式档**；可以恢复完成，但容错和对照实验余量很窄 |
| **1 TB** | 3 个近期 resume、best + 5～6 个 milestone weights、一次原子保存临时峰值、日志和下一组实验 | **唯一推荐档**；训练可以无限延长而本地占用保持有界 |
| **2 TB** | 多组实验并存，或把 10k episodes 的多视角原始档案也长期留在训练机 | **研究舒适档，不是当前必要档** |

1 TB 不是“盘越大越安全”的拍脑袋值。按本文留存策略，本地稳定占用约 **550～750 GB**，其余空间是正在写入的新 checkpoint、失败重试、文件系统余量和短期第二实验的缓冲。500 GB 可以工作，但任何一次未清理的完整 resume、视频导出或备份暂存都可能把训练推入磁盘满写；2 TB 对当前 148 episodes 的单实验则没有对应的必要状态。

## 第一性原理：训练时间不决定存储，留存状态决定存储

训练盘的高水位可以写成：

```text
hot_peak = static_runtime
         + hot_dataset
         + N_resume × resume_checkpoint
         + N_weights × weights_checkpoint
         + one_checkpoint_in_flight
         + bounded_logs
         + crash_free_space
```

其中没有“训练小时数”。训练变慢只增加租用时长；只有在以下策略不受控时，存储才随 step 数近似线性增长：

- 每隔固定 steps 永久保留一个 checkpoint；
- TensorBoard/image/video 日志只追加不轮转；
- 每次转换数据都保留新的完整副本；
- 备份先复制到本地 staging，再长期不清理。

Unitree 官方训练配置恰好包含一个线性增长源：`metrics_over_trainsteps_checkpoint` 每 10,000 steps 保存 weight-only，且 `save_top_k: -1`。Lightning 1.9.3 的定义是 `save_top_k=-1` 保留全部；官方配置上限 300,000 steps，若不修改，会留下 30 个永久 milestone。若 checkpoint 达到 Dual 的 16.719 GB，milestone 目录约 **501.6 GB**；再加每 1,000 steps callback 默认保留的最新一个，官方单次完整 run 的权重高水位约 **518.3 GB**。若文件仍接近 Base，则约 322 GB。这不是模型的固有存储需求，而是默认 retention policy 的结果。[S1][S4]

因此，放宽训练时间约束并不要求购买线性更大的盘。正确动作是把 checkpoint 变成固定槽位的环形集合，并把长期历史移出热盘。

## 已核验的真实组成项

### 权重与静态运行时

Hugging Face 官方 API 当前给出的 LFS 文件体积为：

| 项目 | 十进制容量 | 二进制容量 | 角色 |
|---|---:|---:|---|
| Base checkpoint | **10.437 GB** | 9.72 GiB | post-training 起点，必需 |
| Dual checkpoint | **16.719 GB** | 15.57 GiB | 官方五数据集后的 decision + simulation 对照，可选 |
| Base + Dual | **27.157 GB** | 25.29 GiB | 同时保留时的静态权重 |

模型 API 修订分别固定为 Base `f89d6d1c...`、Dual `2c6b6a9e...`。[S6][S7]

当前机器复核值：

| 项目 | 当前实占 | 规划值 |
|---|---:|---:|
| WMA 仓库（含子模块） | 0.295 GB | 1 GB |
| `unifolm-wma` Conda 环境 | 9.555 GB | 12～20 GB |
| open_clip `CLIP-ViT-H-14` 单个 blob | 3.945 GB | 4～8 GB |
| Hugging Face cache 当前总量 | 4.414 GB | 10～30 GB |

HF Hub 使用 blob cache 与 snapshot；同一 blob 通常不会因多个 snapshot 重复，但把缓存文件再复制到工作目录会产生第二份。Conda/pip tarball、失败下载的 `.incomplete`、模型工作副本也必须算入容量。故代码、环境、Base、可选 Dual、open_clip/HF/package cache 的合理静态预算是：

- **最小：35～45 GB**（只保留 Base，主动清缓存）；
- **正式：60～90 GB**（Base + Dual、环境和下载缓冲）。[S8]

### 当前数据与 1k/10k episodes 敏感性

本项目当前 WMA-ready 数据经过复核：148 个 MP4 + 148 个 HDF5，共 **293,437,969 bytes = 0.293 GB**，即 **1.98 MB/episode**。这是单主视角、当前片段长度和当前编码下的实测值，不能直接代表未来连续长 episode。

Unitree 官方五个 LeRobot v2.1 数据 revision 合计 **23.129 GB / 2,189 episodes = 10.57 MB/episode**；其中与本项目相近的四视角 `G1_Dex1_MountCameraRedGripper_Dataset` 为 **5.833 GB / 201 episodes = 29.02 MB/episode**。这些 API 同时表明该 G1 数据是四路 480×640、30 FPS AV1 视频。[S9]

据此给两个边界，而不是用一个虚假的精确数：

| 数据规模 | 当前单主视角实测线性外推 | 四视角 Unitree G1 参照 | 对本地热盘的含义 |
|---:|---:|---:|---|
| 148 episodes | **0.293 GB** converted；原始多视角预计 1～5 GB | 约 4.3 GB | checkpoint 远大于数据 |
| 1,000 episodes | **1.98 GB** converted | 约 **29 GB** raw | 1 TB 仍几乎不敏感；raw + converted 建议按 60～120 GB 封顶 |
| 10,000 episodes | **19.8 GB** converted | 约 **290 GB** raw | 只把主视角训练集放热盘仍可用 1 TB；若 raw 四视角和转换副本都留本地，应转 2 TB 或把 raw 移到对象存储 |

官方转换器会遍历所有 source views，并把 AV1 转为 H.264；原始 LeRobot 数据又不会自动删除。因此若照搬官方转换器，`raw + converted` 可能接近两份多视角视频，且 H.264/AV1 的实际比例取决于画面和编码参数。项目现有 adapter 只输出主视角，符合官方“训练仅支持 main-view camera”的限制，因而可把多视角 raw 归档到远端，只把主视角转换结果留在热盘。[S1][S2]

这组数字只适用于 **Base 之后的下游 post-training**。Unitree 明确说明 Base 来自 Open-X fine-tuning；若目标改成从 Open-X 重新构建 Base，数据、shuffle/cache 和多轮中间权重会成为完全不同的 TB 级乃至更高问题，不能从 148/1k/10k episodes 外推。[S1]

## Checkpoint 的真实尺寸

### Weight-only

当前机器已有的 1,000-step checkpoint 实测为 **9,401,343,679 bytes = 9.401 GB**。其 PyTorch archive 只有 `state_dict`、loop/global-step 等元数据，没有 `optimizer_states`；这是 weight-only，不是可恢复训练 checkpoint。文件内同时存在 `dp_ema_model.*`，所以“含 EMA”也不自动意味着含 optimizer。

结合 Base 10.437 GB、Dual 16.719 GB，规划时应按：

- action/head 适配型 weight-only：**9～11 GB/个**；
- full decision + simulation weight-only：**15～18 GB/个**；
- 统一采购预算：**20 GB/个槽位**。

官方配置两个周期性 callback 都设置了 `save_weights_only: True`。Lightning 的含义是只保存模型权重，不包含 optimizer 和 lr-scheduler；所以官方默认周期性文件本身不能完成精确训练恢复。[S4]

### 完整 resume：为什么不是“显存有多大，文件就有多大”

本模型当前实例化统计为约 **4.18B total parameters、2.56B trainable parameters**。官方优化器是 AdamW，并启用 action-head EMA。完整 Lightning checkpoint 应包含 model state、optimizer、scheduler、precision scaler、epoch/global step、callbacks 和 loops；其中真正占空间的是 model state 与 Adam moments。[S2][S3][S4]

对 2.56B trainable parameters：

```text
Adam first moment  = 2.56B × 4 bytes ≈ 10.24 GB
Adam second moment = 2.56B × 4 bytes ≈ 10.24 GB
optimizer moments subtotal          ≈ 20.48 GB
```

再加 10～17 GB 模型/EMA state，native Lightning/FSDP 的逻辑 resume 下界约 **31～38 GB**。考虑 dtype、param-group、scaler、序列化 storage、26D 配置和实现差异，实际工程区间按 **38～50 GB/个**。

DeepSpeed ZeRO checkpoint 还可能携带用于恢复/导出 fp32 权重的 optimizer shards / fp32 master state；DeepSpeed 官方还专门记录了 ZeRO-1/2 因 tensor flattening 与 `torch.save` storage sharing 产生 checkpoint bloat 的情形。因此在 ZeRO 路线上按 **50～70 GB/个**，统一保守槽位按 **80 GB/个**。这 80 GB 是恢复工程预算，不是从 GPU 显存反推的文件大小。[S11]

还有一个系统完整性前提：官方周期性 callback 全是 weight-only；训练脚本的 SIGUSR1 路径可以调用不带 `weights_only` 的 `trainer.save_checkpoint`，但 `auto_resume` 参数没有接入 `trainer.fit(..., ckpt_path=...)`。也就是说，容量足够不等于官方代码已经完成可靠自动续训。正式 run 前必须用目标分布式策略做一次 **save → 退出进程 → load optimizer/scheduler/global step → 再走若干 steps** 的验收。[S3][S4]

### FSDP/ZeRO sharded 保存的临时峰值

真正 sharded 的 checkpoint 是把同一逻辑状态分散为多文件，不是“每张卡各保存一份完整模型”。PyTorch Distributed Checkpoint 明确由各 rank 保存 local shard，且一个 checkpoint 至少每 rank 一个文件；因此四卡不会天然把 50 GB 变成 200 GB。[S10]

但可靠保存必须写入一个新的、空的 step 目录，所有 shard 与 metadata 完成后再把它标记为可恢复，然后才删除最旧槽位。于是磁盘高水位至少是：

```text
已保留 checkpoint + 正在写的新 checkpoint
```

对统一 80 GB 槽位，保存时至少预留 **80 GB**；考虑失败重试、临时目录和远端同步，实际要求始终保留 **120～160 GB 空闲**。如果实现误用了 `FULL_STATE_DICT` 并让每个 rank 各写一份完整状态，容量会按 rank 数爆炸；这属于配置错误，不能用购买更大磁盘掩盖。

PyTorch DCP 的 async save 默认先把 state 脱敏/拷贝到 CPU staging，再后台写出；这增加的是 RAM 压力，不必增加第二份本地磁盘副本。远端备份也应直接读取已完成的 checkpoint 目录异步上传，不再复制到本地 `backup/`。[S10]

## 日志、视频、崩溃与备份

官方配置表面上把 `ImageLogger.batch_frequency` 设为 20,000、最多 8 个样本、默认写 TensorBoard；但 callback 实现每个 train batch 把内部计数增加 25，因此实际约每 **800 train batches** 触发一次。若 300k optimizer steps 且梯度累积为 2，量级可达约 **750 次**视频采样，而不是 15 次。视频是 16 帧网格，具体 event 大小取决于日志键和值；不能给没有实测的固定总量。TensorBoard event、validation 视频和人工评估导出都是 append-only，因此本地给 **20～50 GB 硬上限**：超过后把旧 event/video 归档远端，只留最近窗口和最终报告。[S2][S5]

崩溃缓冲不能用“盘理论上刚好装下”代替：

- 始终保持 15% 以上文件系统空闲；
- checkpoint 写入前检查可用空间 ≥ 1.5× 目标 resume 槽位；
- 只在新目录存在完整 metadata、可列举所有 shards 且完成一次 load smoke test 后，删除旧 resume；
- 本地 NVMe 没有冗余，不能算备份。

AutoDL 官方说明系统盘/数据盘通常是本地 SSD，性能好但无冗余；文件存储是多副本网络共享存储，但 IO 性能一般。官方建议训练数据先复制到本地盘，重要数据放文件存储；实例连续关机 15 天会释放并清空，本地盘也可能随主机下架而释放。[S12][S13]

因此：

| 层级 | 放什么 | 容量建议 |
|---|---|---:|
| 本地热 SSD/NVMe | 环境、Base、当前主视角数据、当前 resume、近期 weights、活跃日志 | **1 TB** |
| 远端文件/对象存储 | 原始多视角数据、已完成 resume、milestone weights、配置/manifest/metrics | **至少 500 GB；推荐 1 TB 可扩展** |
| 实验室长期副本 | 最终/best weights、数据 manifest、代码 commit、少量关键 resume | 不与云实例生命周期绑定 |

吞吐和 IOPS 不改变容量公式，但决定恢复是否真实可用：训练 dataloader 和多 rank checkpoint 应落本地 NVMe；远端网络存储承担异步备份。原子性依赖“新目录写完再发布”，不能直接覆盖唯一的 `last`。

## 有界留存策略

每个实验固定以下槽位，不因训练持续多久而增加：

1. **最近 3 个 resume**：`resume-A/B/C` 环形覆盖，每个预算 80 GB，共 240 GB。
2. **best weight-only 1 个**：预算 20 GB。
3. **milestone weight-only 5 个**：对数间隔或阶段边界，而非每 10k 永久保留，共 100 GB。
4. **正在写入槽位 1 个**：预算 80 GB；写完、校验、远端确认后才轮转最旧 resume。
5. **TensorBoard/image/video**：本地硬上限 50 GB；若只保留稀疏评估，可收紧到 20 GB。
6. **异步备份**：每个完成的 resume 上传远端；远端保留最近 3 个 + 每阶段 1 个，校验 checksum 后允许本地轮转。
7. **官方无限 milestones callback 必须关闭或改为有界清理**：不得保留 `save_top_k=-1` 的 10k-step 全历史。

按正式静态 90 GB、当前/1k 数据 10～120 GB、3×80 GB resume、6×20 GB weights、80 GB in-flight、20～50 GB logs 与 150 GB crash/free-space 计算：

```text
90 + (10～120) + 240 + 120 + 80 + (20～50) + 150
= 710～850 GB
```

当前 148 episodes 更接近下界；1 TB 有清晰余量。500 GB 若缩成 2 个 resume、3 个 weights、较小数据和 80 GB 写入缓冲，约落在 400～480 GB，故只能称最低正式档。2 TB 只有在 10k 多视角 raw/converted 同机、并行多个实验或拒绝远端归档时才获得实际价值。

## 最终采购判断

**选 1 TB 本地 NVMe，不选 500 GB，也暂不选 2 TB。**

- 不选 500 GB：它能完成一次训练，但必须持续人工清理；完整 resume 保存的瞬时高水位、默认 30 个 milestone weights、TensorBoard/video 或一次失败重试都可能中断训练。它把容量管理变成关键路径。
- 不选 2 TB：当前真正必须常驻的训练状态在有界 retention 后不到 1 TB；多出的 1 TB 不提升模型质量、恢复能力或可解释性。若未来达到 10k 四视角数据，优先把 raw 放对象存储，而不是让昂贵热盘成为档案库。
- 选 1 TB：恰好覆盖 3 个可恢复状态、若干可部署权重、一次安全写入峰值、当前到 1k 数据扩张和下一实验，不要求训练时间有上限。

如果采购界面只能在 500 GB 与 2 TB 二选一，则选 **2 TB**；但在可选 1 TB 时，1 TB 是当前系统的最小充分解。

## 一手来源

- **[S1] Unitree UnifoLM-WMA-0 README（仓库 commit `3e198de68d`）**：Base/Dual、Open-X、五个下游数据集、三阶段训练、自有数据转换、训练仅主视角。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/README.md
- **[S2] Unitree 官方训练配置**：AdamW、EMA、300k steps、1k/10k checkpoint、`save_weights_only`、`save_top_k=-1`、ImageLogger。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/configs/train/config.yaml
- **[S3] Unitree 模型与训练入口源码**：trainable 参数、EMA copy、optimizer/scheduler、SIGUSR1 save 与当前 resume 接线。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/src/unifolm_wma/models/ddpms.py  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/scripts/trainer.py
- **[S4] Lightning 1.9.3 checkpoint 文档与 ModelCheckpoint 源码**：full checkpoint 内容、weights-only 语义、`save_top_k=-1`。  
  https://github.com/Lightning-AI/lightning/blob/1.9.3/docs/source-pytorch/common/checkpointing_basic.rst  
  https://github.com/Lightning-AI/lightning/blob/1.9.3/src/pytorch_lightning/callbacks/model_checkpoint.py
- **[S5] Unitree ImageLogger/save_video 源码**：TensorBoard video、local H.264、追加式日志。  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/src/unifolm_wma/utils/callbacks.py  
  https://github.com/unitreerobotics/unifolm-world-model-action/blob/3e198de68de55f93f24b3ad623dd499390aaee45/src/unifolm_wma/utils/save_video.py
- **[S6] Hugging Face Base 官方 API（`blobs=true`）**：10,437,387,352-byte checkpoint。  
  https://huggingface.co/api/models/unitreerobotics/UnifoLM-WMA-0-Base?blobs=true
- **[S7] Hugging Face Dual 官方 API（`blobs=true`）**：16,719,237,688-byte checkpoint。  
  https://huggingface.co/api/models/unitreerobotics/UnifoLM-WMA-0-Dual?blobs=true
- **[S8] Hugging Face Hub 官方 cache 文档**。  
  https://huggingface.co/docs/huggingface_hub/guides/manage-cache
- **[S9] Unitree 官方五数据集 API 与 G1 `info.json` revision `v2.1`**：文件字节、episode 数、四路 480×640/30FPS/AV1。  
  https://huggingface.co/api/datasets/unitreerobotics/Z1_StackBox_Dataset/revision/v2.1?blobs=true  
  https://huggingface.co/api/datasets/unitreerobotics/Z1_Dual_Dex1_StackBox_Dataset/revision/v2.1?blobs=true  
  https://huggingface.co/api/datasets/unitreerobotics/Z1_Dual_Dex1_StackBox_Dataset_V2/revision/v2.1?blobs=true  
  https://huggingface.co/api/datasets/unitreerobotics/Z1_Dual_Dex1_CleanupPencils_Dataset/revision/v2.1?blobs=true  
  https://huggingface.co/api/datasets/unitreerobotics/G1_Dex1_MountCameraRedGripper_Dataset/revision/v2.1?blobs=true  
  https://huggingface.co/datasets/unitreerobotics/G1_Dex1_MountCameraRedGripper_Dataset/resolve/v2.1/meta/info.json
- **[S10] PyTorch Distributed Checkpoint / FSDP 官方文档**：local shards、多文件 checkpoint、async CPU staging、sharded state。  
  https://docs.pytorch.org/docs/2.8/distributed.checkpoint.html  
  https://docs.pytorch.org/docs/2.8/fsdp.html
- **[S11] DeepSpeed 官方 checkpoint 文档**：ZeRO fp32 recovery 与 checkpoint bloat。  
  https://deepspeed.readthedocs.io/en/latest/model-checkpointing.html
- **[S12] AutoDL 实例数据官方文档**：本地 SSD、无冗余、15 天释放及主机下架风险。  
  https://www.autodl.com/docs/instance_data/
- **[S13] AutoDL 文件存储官方文档**：网络共享、多副本、IO 一般，训练数据应复制到本地盘。  
  https://www.autodl.com/docs/fs/

所有公网 URL 于 2026-08-20 重新访问；容量使用十进制 GB/TB，括号内 GiB 使用二进制换算。
