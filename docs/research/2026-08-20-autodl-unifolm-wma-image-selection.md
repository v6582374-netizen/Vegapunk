# AutoDL 上 UnifoLM-WMA 的镜像选择

日期：2026-08-20

## 结论

目前没有公开证据可以确认 AutoDL 社区镜像中存在一份可直接用于 Unitree UnifoLM-WMA 的镜像。

这不是说它一定不存在，而是 AutoDL 的社区镜像目录和搜索 API 需要登录：创建实例页面使用的社区镜像接口 `POST /api/v1/image/codewithgpu/list` 在匿名请求下返回 `AuthorizeFailed`。因此无法在不登录的公开环境中核实镜像名称、版本、作者和更新时间，也不能负责任地给出一个社区镜像名。

当前最稳妥的选择是：

> 选择 AutoDL 基础镜像 **PyTorch 2.3.0 / Python 3.12 / CUDA 12.1**，但不直接使用其中的 Python 环境；在镜像内新建 `Python 3.10.18` Conda 环境，安装官方 `torch 2.3.1 + torchvision 0.18.1 + cu121`，再按 Unitree README 安装其余依赖。

这个选择保留了 CUDA 12.1 系统工具链，同时把项目真正依赖的软件栈放进独立、可复现的环境。配置完成并通过训练、保存、恢复验收后，再将实例系统盘保存为自己的镜像。后续使用自己的已验收镜像，而不是持续依赖来源和状态不可控的社区镜像。

## 为什么不能直接套用现有基础环境

Unitree 官方 `pyproject.toml` 锁定了：

| 组件 | 项目要求 |
|---|---:|
| Python | `==3.10.18` |
| torch | `==2.3.1` |
| torchvision | `==0.18.1` |
| xformers | `==0.0.27` |
| pytorch-lightning | `==1.9.3` |
| fairscale | `==0.4.13` |

AutoDL 当前公开基础镜像表中最接近的是：

| AutoDL 基础镜像 | 与项目的关系 | 判断 |
|---|---|---|
| PyTorch 2.3.0 / Python 3.12 / CUDA 12.1 | CUDA 完全匹配；torch 差一个补丁版本；Python 不匹配 | **首选底座，但必须新建环境** |
| Miniconda / Python 3.10 / CUDA 11.8 | Python 主版本接近；PyTorch 官方提供 2.3.1 cu118 | 可用备选；仍应创建精确到 3.10.18 的环境 |
| PyTorch 2.1.0 / Python 3.10 / CUDA 12.1 | Python/CUDA 接近，torch 明显偏旧 | 没有优于 PyTorch 2.3.0 底座的价值 |
| PyTorch 2.5.1、2.7.0、2.8.0 | Python 3.12，torch 过新 | 不应直接使用；会破坏项目锁定栈 |

`xformers 0.0.27` 的官方 PyPI 元数据明确要求 `torch==2.3.1`，并提供 CPython 3.10 Linux wheel。因此这里的 torch 版本不是可随意升级的普通下限。Lightning 1.9.3 的官方元数据要求 Python `>=3.7`、torch `>=1.10.0`；FairScale 0.4.13 要求 Python `>=3.8`，仅发布源码包。二者均能落在 Python 3.10.18 + torch 2.3.1 环境内，但 FairScale 需要在 torch 安装完成后构建。

## H20、驱动 580 与 CUDA 12.1

这组组合不存在驱动版本障碍：

- PyTorch 官方为 `torch 2.3.1 / torchvision 0.18.1` 提供 CUDA 12.1 wheel 和 Conda 包。
- NVIDIA 的兼容性文档指出，CUDA 12.x 的最低驱动为 525；580 及更新驱动继续通过向后兼容运行 CUDA 12.x 应用。
- AutoDL 文档特别说明：`nvidia-smi` 显示的 CUDA 版本只是驱动支持的最高版本，不代表当前 Python 环境使用该版本。因此机器显示“CUDA ≤13.0”不要求把项目升级到 CUDA 13。

换言之，H20 主机上的 580.105.08 驱动可以运行 PyTorch cu121。实际环境应以 `torch.version.cuda` 和一次 CUDA/xFormers 前反向测试为准，而不是以 `nvidia-smi` 标题中的“CUDA Version”为准。

## 社区镜像的证据边界

AutoDL 官方快速开始文档确认，创建实例时可选择“基础镜像”和“社区镜像”。公开前端也将社区镜像标为 `CodeWithGPU`，但目录查询接口要求登录。2026-08-20 的匿名请求结果为：

```json
{"code":"AuthorizeFailed","data":null,"msg":"登录超时，请重新登录"}
```

所以当前能确认的是：

1. AutoDL 确实提供社区镜像机制；
2. 社区镜像目录不能通过匿名公开 API 完整核验；
3. 没有公开证据证明存在 Unitree、UnifoLM 或 WMA 的精确镜像；
4. 在登录后的界面中即使搜到同名镜像，也只能视为候选，不能仅凭名称认为可直接训练。

登录后可搜索 `UnifoLM-WMA`、`UnifoLM`、`Unitree`，但候选镜像必须同时提供或实测以下信息才值得使用：Python 3.10.18、torch 2.3.1、torchvision 0.18.1、xformers 0.0.27、CUDA 12.1，以及可工作的 FairScale/Lightning 多卡训练。如果任意一项不明确，重新配置基础镜像的风险更低。

## 推荐安装策略

### 1. 选基础镜像

首选 AutoDL 页面中的：

```text
PyTorch 2.3.0
Python 3.12
CUDA 12.1
```

这里选择的是它的 Ubuntu、驱动接口和 CUDA 12.1 工具链，不是复用它的 Python 3.12 环境。

### 2. 把缓存和大型制品放到数据盘

AutoDL 系统盘只有 30GB，数据盘位于 `/root/autodl-tmp`。Conda 环境保留在系统盘以便保存为个人镜像，但模型、数据、checkpoint 和下载缓存应放到数据盘：

```bash
mkdir -p /root/autodl-tmp/cache/{huggingface,pip,torch}
export HF_HOME=/root/autodl-tmp/cache/huggingface
export PIP_CACHE_DIR=/root/autodl-tmp/cache/pip
export TORCH_HOME=/root/autodl-tmp/cache/torch
```

### 3. 建立精确环境

```bash
conda create -n unifolm-wma python=3.10.18 pip setuptools=65.6.3 wheel -y
conda activate unifolm-wma

conda install pinocchio=3.2.0 -c conda-forge -y
conda install ffmpeg=7.1.1 -c conda-forge -y

python -m pip install \
  torch==2.3.1 torchvision==0.18.1 \
  --index-url https://download.pytorch.org/whl/cu121

python -m pip install xformers==0.0.27

git clone --recurse-submodules \
  https://github.com/unitreerobotics/unifolm-world-model-action.git \
  /root/autodl-tmp/unifolm-world-model-action
cd /root/autodl-tmp/unifolm-world-model-action
python -m pip install -e .
python -m pip install -e external/dlimp
```

完成后可以清理 Conda/Pip 的无用下载缓存，避免30GB系统盘被安装包副本占满；不要把 Hugging Face 权重和 checkpoint 写进系统盘。

### 4. 验收后保存自己的镜像

AutoDL 官方说明，保存镜像会保存整个系统盘，而数据盘不会进入镜像。因此应在完成以下验收后关机，将系统盘保存为个人镜像；数据与模型权重继续放数据盘或远端存储。

## 环境验收命令

### 版本、驱动和双卡拓扑

```bash
nvidia-smi
nvidia-smi topo -m
nvidia-smi nvlink -s
nvcc --version

conda activate unifolm-wma
python - <<'PY'
import sys
import torch
import torchvision
import xformers
import pytorch_lightning as pl
import fairscale

print("python:", sys.version)
print("torch:", torch.__version__)
print("torchvision:", torchvision.__version__)
print("torch CUDA runtime:", torch.version.cuda)
print("xformers:", xformers.__version__)
print("lightning:", pl.__version__)
print("fairscale:", fairscale.__version__)
print("CUDA available:", torch.cuda.is_available())
print("GPU count:", torch.cuda.device_count())
for i in range(torch.cuda.device_count()):
    print(i, torch.cuda.get_device_name(i), torch.cuda.get_device_capability(i))

assert sys.version_info[:3] == (3, 10, 18)
assert torch.__version__.split("+")[0] == "2.3.1"
assert torchvision.__version__.split("+")[0] == "0.18.1"
assert xformers.__version__ == "0.0.27"
assert pl.__version__ == "1.9.3"
assert torch.version.cuda == "12.1"
assert torch.cuda.device_count() == 2
PY
```

### xFormers CUDA 前向与反向

```bash
python - <<'PY'
import torch
from xformers.ops import memory_efficient_attention

q = torch.randn(1, 1024, 8, 64, device="cuda", dtype=torch.float16,
                requires_grad=True)
k = torch.randn_like(q, requires_grad=True)
v = torch.randn_like(q, requires_grad=True)
y = memory_efficient_attention(q, k, v)
y.float().sum().backward()
print("xformers forward/backward OK:", tuple(y.shape))
PY
```

最终验收不能停留在 import：还应运行项目的完整双卡训练 100–200 step，然后保存完整 checkpoint、退出进程、重新加载并继续训练。只有这条链路通过，环境才应保存为长期使用的个人镜像。

## 不应选择的方案

- 不要把 AutoDL 的 PyTorch 2.3.0 / Python 3.12 环境原样当作项目环境；它同时违反 Python、torch 和 torchvision 锁定版本。
- 不要选择 PyTorch 2.5.1、2.7.0、2.8.0 后强行安装旧 xformers；`xformers 0.0.27` 明确锁定 torch 2.3.1，最终仍会把新环境拆掉重装。
- 不要因为驱动显示 CUDA 13.0 就选择 CUDA 13/PyTorch 最新版；驱动的最高能力不等于项目运行时版本。
- 不要仅凭社区镜像名中出现 Unitree、机器人或 world model 就直接运行训练；社区镜像若没有版本清单和实际 E2E 验收，节省的是几十分钟安装时间，增加的是训练中途失败和环境不可解释的风险。

## 来源

1. Unitree 官方项目依赖与 Python 锁定：<https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/pyproject.toml>
2. Unitree 官方安装步骤：<https://github.com/unitreerobotics/unifolm-world-model-action#%EF%B8%8F-installation>
3. AutoDL 基础镜像版本表与官方推荐选择逻辑：<https://www.autodl.com/docs/base_config/>
4. AutoDL 基础镜像/社区镜像入口说明：<https://www.autodl.com/docs/quick_start/>
5. AutoDL CUDA 版本解释：<https://www.autodl.com/docs/cuda/>
6. AutoDL 镜像保存、加载及数据盘边界：<https://www.autodl.com/docs/image/>、<https://www.autodl.com/docs/env/>
7. AutoDL 社区镜像匿名查询接口（匿名访问返回 `AuthorizeFailed`）：<https://www.autodl.com/api/v1/image/codewithgpu/list>
8. PyTorch 2.3.1 官方 cu118/cu121 安装矩阵：<https://pytorch.org/get-started/previous-versions/#v231>
9. xFormers 0.0.27 官方发布说明：<https://github.com/facebookresearch/xformers/releases/tag/v0.0.27>
10. xFormers 0.0.27 官方 PyPI 元数据：<https://pypi.org/project/xformers/0.0.27/>
11. PyTorch Lightning 1.9.3 官方 PyPI 元数据：<https://pypi.org/project/pytorch-lightning/1.9.3/>
12. FairScale 0.4.13 官方 PyPI 元数据：<https://pypi.org/project/fairscale/0.4.13/>
13. NVIDIA CUDA minor-version/backward compatibility：<https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html>
