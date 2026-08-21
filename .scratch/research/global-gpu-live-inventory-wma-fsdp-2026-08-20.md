# UnifoLM-WMA-0 Base 全球 GPU 云实时货源收敛报告

- **核验时间**：2026-08-20 16:02:40（Asia/Shanghai）
- **训练目标**：UnifoLM-WMA-0 Base，约 4.18B 参数，16 帧 320×512 视频，26D，单机 4 卡，原生 PyTorch FSDP `FULL_SHARD`
- **硬性筛选**：NVIDIA、每卡显存 ≥80GB、单机 4 卡、CPU ≥48 逻辑核、RAM ≥256GB、本地盘 ≥500GB（1TB 优先）
- **证据边界**：只采用供应商官网、官方控制台、官方 API 与官方文档。库存是瞬时状态，下单时仍可能变化。

---

## 一页结论

### 建议下单顺序

1. **先尝试 RunPod Secure Cloud：4×A100 SXM 80GB**。它是当前最接近“不过度浪费”的正式训练档：官方实时 API 在加入 4 卡、≥48 vCPU、≥256GB RAM 和最低本地盘性能约束后仍返回 `Medium` 库存，整机 **$6.36/小时**。
2. 如果 RunPod 开机后的 `nvidia-smi topo -m` 不能确认足够的卡间高速互联，立即释放，改租 **Vast.ai 日本 4×H100 SXM，Offer 47905643**。该报价的官方实时 API 直接给出 **478.1 GB/s NVLink、224 CPU、约 1TB RAM、约 12TB NVMe、$12.77/小时**，硬件证据最完整。
3. 若 A100 训练吞吐不足但不想进入 H200 过量采购，选择 **RunPod Secure 4×H100 SXM，$13.16/小时**。
4. H200 只作为容量和激活峰值兜底，不作为默认方案。

### 最终候选表

| 排名 | 平台与实例 | 实时状态 | 4 卡总价 | CPU / RAM | 本地盘证据 | 互联证据 | 购买入口 |
|---:|---|---|---:|---|---|---|---|
| 1 | **RunPod Secure 4×A100 SXM 80GB** | **Medium**；US-MO-1、US-MD-1、US-KS-2 为 `AVAILABLE` | **$6.36/h** | API 返回最低匹配资源 **64 vCPU / 1000GB RAM** | RunPod 文档确认 Volume disk 是主机本地盘且可扩容；下单时必须显式设为 ≥500GB | RunPod 公共库存接口未返回拓扑，必须开机验收 | [直接部署 4×A100 SXM](https://console.runpod.io/deploy?gpu=NVIDIA%20A100-SXM4-80GB&count=4) |
| 2 | **Vast.ai 4×H100 SXM，日本，Offer 47905643** | **rentable=true、rented=false、verified** | **$12.7702/h** | **224 cores / 1,031,927MB RAM** | **11,999.7GB Micron NVMe** | **`bw_nvlink=478.116 GB/s`** | [打开 Vast 创建页](https://cloud.vast.ai/create/?offer_id=47905643)（按 Offer ID 47905643 核对） |
| 3 | **RunPod Secure 4×H100 SXM 80GB** | **Medium**；CA-MTL-1、AP-IN-1、AP-IN-2、US-GA-2、US-NE-1 可用 | **$13.16/h** | **96 vCPU / 1004GB RAM** | 下单时将本地 Volume disk 显式设为 ≥500GB | 型号为 SXM，但具体 Pod 拓扑仍需开机验收 | [直接部署 4×H100 SXM](https://console.runpod.io/deploy?gpu=NVIDIA%20H100%2080GB%20HBM3&count=4) |
| 4 | **RunPod Secure 4×H100 NVL 94GB** | **Low**；US-GA-2 可用 | **$12.76/h** | **64 vCPU / 752GB RAM** | 下单时将本地 Volume disk 显式设为 ≥500GB | `NVL` 是产品型号，不等于已公开证明四卡全互联；仍需验收 | [直接部署 4×H100 NVL](https://console.runpod.io/deploy?gpu=NVIDIA%20H100%20NVL&count=4) |
| 5 | **RunPod Secure 4×H200 SXM 141GB** | **Low**；US-GA-2、EUR-IS-2、EUR-IS-4 可用 | **$18.36/h** | **48 vCPU / 1004GB RAM** | 下单时将本地 Volume disk 显式设为 ≥500GB | 具体 Pod 拓扑需开机验收 | [直接部署 4×H200](https://console.runpod.io/deploy?gpu=NVIDIA%20H200&count=4) |
| 6 | **Vast.ai 4×H200，日本，Offer 46355061** | **rentable=true、rented=false、verified** | **$20.7771/h** | **224 cores / 1,031,851MB RAM** | **10,800GB Dell NVMe** | **`bw_nvlink=478.116 GB/s`** | [打开 Vast 创建页](https://cloud.vast.ai/create/?offer_id=46355061)（按 Offer ID 46355061 核对） |

> RunPod 的价格是满足本报告资源过滤条件的四卡整机即时价格，不是单卡价格。Vast 的 `dph_total` 也是整份四卡 Offer 的小时总价。

---

## 1. 为什么首选 RunPod A100 SXM，而不是直接上 H200

本任务是 148 episodes 的下游 post-training，不是从零预训练 4.18B 基础模型。原生 FSDP `FULL_SHARD` 的首要目标是稳定分片参数、梯度和优化器状态；四张 80GB 卡已经提供 320GB 聚合显存。H200 的 564GB 聚合显存当然更宽裕，但当前没有证据证明训练必须支付约三倍于 A100 RunPod 方案的小时费。

RunPod A100 SXM 的风险只有一个：**公共库存 API 证明了卡数、价格、CPU、RAM、最低磁盘性能和数据中心可用性，但没有公开具体机器的 NVLink/NVSwitch 拓扑。** 因此它适合作为首个低成本验收实例，而不是无条件长租。

开机后只做以下两项硬件验收：

```bash
nvidia-smi topo -m
nvidia-smi nvlink -s
```

若四卡之间没有预期的 `NV#` 路径，或 NCCL all-reduce 明显异常，停止实例并切换 Vast H100 Offer 47905643。不要为了已经支付的少量试机费用继续使用不合适的机器。

RunPod 官方来源：

- GPU 类型与显存：[RunPod GPU types](https://docs.runpod.io/references/gpu-types)
- 本地 Container/Volume disk 与网络盘区别：[RunPod storage options](https://docs.runpod.io/pods/storage/types)
- Pod 管理与部署：[RunPod Manage Pods](https://docs.runpod.io/pods/manage-pods)
- 官方实时 GraphQL API：[https://api.runpod.io/graphql](https://api.runpod.io/graphql)
- 官方定价页：[https://www.runpod.io/pricing](https://www.runpod.io/pricing)

---

## 2. Vast.ai 的确定性更高，但平台风险也更高

### 2.1 推荐的确定性备选：Offer 47905643

官方实时 Offer API 在 2026-08-20 16:02:40 返回：

- 4×H100 SXM，每卡约 80GB；
- 224 CPU cores；
- 1,031,927MB 主机 RAM；
- 11,999.7GB Micron NVMe；
- `bw_nvlink=478.1160888671875`；
- `dph_total=$12.770222222222223/h`；
- `rentable=true`、`rented=false`、`verification=verified`；
- `reliability2=0.9982603`；
- 日本机房。

这使它成为本报告中**最容易在购买前证明完整硬件条件**的实例。相比 RunPod，它的主要风险不是容量，而是 Vast 是主机市场：Offer 会瞬时消失，供应商运维一致性弱于标准化云。因此正式训练必须启用高频 sharded checkpoint，并把关键 checkpoint 同步回实验室或对象存储。

### 2.2 不推荐 Vast A100 Offer 39882040

它的表面配置非常合适：4×A100 SXM4、300GB/s NVLink、128 cores、约 961GB RAM、1.95TB NVMe、$6.67/h。但实时 API 同时返回：

- `reliability2=0.9795533`；
- `is_vm_deverified=true`。

因此不应为了每小时节省约 $6 而把首次正式训练交给它。硬件便宜不等于训练总成本低。

Vast 官方来源：

- 官方实时 Offer API：[https://console.vast.ai/api/v0/bundles](https://console.vast.ai/api/v0/bundles)
- 官方搜索 Offer API 文档：[Vast search offers](https://docs.vast.ai/api-reference/search/search-offers)
- 官方创建实例文档：[Vast create instance](https://docs.vast.ai/api-reference/instances/create-instance)
- 购买控制台：[https://cloud.vast.ai/create/](https://cloud.vast.ai/create/)

---

## 3. 已调查但没有进入“实时可直接下单”主榜的平台

### Lambda：配置优秀，但公共接口不能证明当前库存

Lambda 官方定价页明确提供 4×H100 SXM：每卡 $4.09/h，即整机 **$16.36/h**；104 vCPU、900GiB RAM、11TiB SSD。官网称 Instances 是 self-serve、first-come access，但官方 `instance-types`/availability API 需要 API key，本次匿名核验无法证明此刻有货。

- 状态：**有明确规格和价格，但未公开证明实时库存**。
- 登录后可直接尝试：[Lambda Cloud instances](https://cloud.lambda.ai/instances)
- 官方定价：[Lambda pricing](https://lambda.ai/pricing)
- 官方实例类型 API（需要 API key）：[https://cloud.lambda.ai/api/v1/instance-types](https://cloud.lambda.ai/api/v1/instance-types)

### Hyperstack：价格有吸引力，但库存和“本地 SSD”未公开证明

官方定价页列出 A100 NVLink 80GB：$1.40/GPU/h、每 GPU 最多 31 pCPU 和 240GB RAM；理论四卡为 **$5.60/h、124 pCPU、960GB RAM**。但 Flavor API 需要认证，公开页面没有证明四卡即时库存；其 SSV/Cloud-SSD 是附加存储服务，不能在购买前等同于本地 NVMe。

- 状态：**仅标价；登录后才能验证库存与具体 Flavor**。
- 购买入口：[Hyperstack Console](https://console.hyperstack.cloud/)
- 官方定价：[Hyperstack GPU pricing](https://www.hyperstack.cloud/gpu-pricing)
- 官方 Flavor API：[https://infrahub-api.nexgencloud.com/v1/core/flavors](https://infrahub-api.nexgencloud.com/v1/core/flavors)

### Verda / DataCrunch：精确四卡规格存在，但 availability 需要认证

官方公开 `instance-types` API 给出：

- 4×A100 SXM4 80GB；
- 88 CPU、480GB RAM；
- P2P 300GB/s；
- $7.16/h；
- Storage 标记为 `dynamic`。

它的规格与价格都合理，但官方 availability 接口要求 access token，且 `dynamic` 不能证明本地盘容量和介质。因此暂不排在实时主榜。

- 状态：**官方目录有规格和价格，实时库存未证明**。
- 购买入口：[Verda Console](https://console.verda.com/instances)
- 官方类型 API：[https://api.datacrunch.io/v1/instance-types](https://api.datacrunch.io/v1/instance-types)
- 官方定价：[https://verda.com/pricing](https://verda.com/pricing)

### Nebius：没有符合要求的单机四卡 preset

Nebius 官方 VM 类型文档为 H100/H200 提供的是 **1 GPU 或 8 GPU** preset，没有 4 GPU preset。其 8×H100/H200 配置会造成明显过量采购，因此排除。

- 官方 VM 类型与 presets：[Nebius VM types](https://docs.nebius.com/compute/virtual-machines/types)
- 官方价格：[Nebius prices](https://nebius.com/prices)
- 控制台：[Nebius Console](https://console.nebius.com/)

### CoreWeave：相关 H100/H200 是八卡节点

CoreWeave 官方定价页中的 HGX H100/H200 均为 8 GPU 节点；虽然本地盘、RAM 和互联能力充足，但不满足“单机四卡且不过度浪费”的采购边界。四卡规格主要出现在 GB200/GB300 NVL72，价格和能力远超本任务所需。

- 官方价格与节点规格：[CoreWeave pricing](https://www.coreweave.com/pricing)
- 控制台：[CoreWeave Cloud](https://cloud.coreweave.com/)

### AutoDL：中国区购买方便，但当前已知实例不通过磁盘与互联验收

用户此前看到的 AutoDL A800 主机可租四卡后具备 56 核、480GB RAM、约 ¥19.92/h，但只有固定 50GB 数据盘，且型号只标 `A800-80GB` 而非 `A800-80GB-NVLink`。这两个缺口足以将它排除出正式训练候选。AutoDL 的机器搜索和详情 API 需要登录，匿名接口只能证明平台登记了 GPU 类型，不能证明当前四卡库存。

- 官方市场：[AutoDL 算力市场](https://www.autodl.com/market/list)
- 官方 GPU 类型 API：[https://api.autodl.com/api/v1/machine/gpu_type](https://api.autodl.com/api/v1/machine/gpu_type)
- 官方 GPU 文档：[AutoDL GPU 说明](https://www.autodl.com/docs/gpu/)

---

## 4. 下单决策，不再继续横向搜索

### 方案 A：成本与稳妥平衡

直接打开：

> [RunPod 4×A100 SXM 80GB 部署页](https://console.runpod.io/deploy?gpu=NVIDIA%20A100-SXM4-80GB&count=4)

选择 Secure Cloud、4 GPUs、本地 Volume disk ≥500GB。开机后验证拓扑；通过则开始 100～200 steps 的原生 FSDP 验收并继续正式训练。

### 方案 B：购买前硬件证据最完整

直接打开：

> [Vast 创建实例页，目标 Offer 47905643](https://cloud.vast.ai/create/?offer_id=47905643)

核对 Offer ID、4×H100 SXM、日本、$12.77/h、约 12TB NVMe、NVLink 478GB/s 后立即租用。若 Offer 已被抢走，回到 RunPod H100 SXM，不继续寻找更多小平台。

### 方案 C：A100 吞吐不足时升级

> [RunPod 4×H100 SXM 部署页](https://console.runpod.io/deploy?gpu=NVIDIA%20H100%2080GB%20HBM3&count=4)

当前整机 $13.16/h，Medium 库存。它比 H200 更符合本任务规模。

---

## 5. 可复核的实时查询

### RunPod

官方 GraphQL API 查询使用以下约束。其中 `minDisk=500` 是控制台对应的磁盘性能过滤值，不是 500GB 容量；500GB 容量必须在部署页单独设置：

```json
{
  "gpuCount": 4,
  "minDisk": 500,
  "minMemoryInGb": 256,
  "minVcpuCount": 48,
  "secureCloud": true
}
```

查询端点：

```text
POST https://api.runpod.io/graphql
```

读取字段：`uninterruptablePrice`、`minVcpu`、`minMemory`、`stockStatus`、`gpuTypeDatacenters.availability`。该端点在本次核验中无需登录即可返回上述库存摘要，但不返回本地 Volume disk 的最大容量；因此部署页能否设置到 ≥500GB 是 RunPod 候选的最后一道下单条件。

### Vast.ai

官方搜索端点：

```text
POST https://console.vast.ai/api/v0/bundles
```

核心过滤条件：

```json
{
  "limit": 100,
  "type": "on-demand",
  "verified": {"eq": true},
  "rentable": {"eq": true},
  "rented": {"eq": false},
  "num_gpus": {"eq": 4},
  "gpu_ram": {"gte": 80000},
  "cpu_cores": {"gte": 48},
  "cpu_ram": {"gte": 262144},
  "disk_space": {"gte": 500},
  "order": [["dph_total", "asc"]]
}
```

---

## 最终风险提示

1. **库存是瞬时的**：本报告中的 `AVAILABLE`、`Medium`、`rentable=true` 只代表 2026-08-20 16:02:40 的官方返回。
2. **RunPod 有两个下单验收项**：实际主机拓扑，以及部署页是否允许把本地 Volume disk 设置为 ≥500GB；型号名不能替代 `nvidia-smi topo -m`。
3. **Vast 的最大未知项是主机供应商运维质量**：即使硬件数据漂亮，也必须频繁保存可恢复的 sharded checkpoint。
4. **不要使用 Spot/interruptible 进行首次正式训练**：当前所有主榜价格均按 on-demand/uninterruptible 处理。
5. **不要因预算不限而直接上 8 卡或 B200/H200**：先用 4×A100 SXM 做真实 FSDP 测量，再由 step time、峰值显存和总训练时长决定是否升级。
