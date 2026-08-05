# CFD 与 LLM 实验 loop 集成调研报告（外部资料与可调用性评估）

> 本文档先记录外部一手资料和可调用性结论，供后续补充 Vegapunk 的项目内架构映射与实施计划。
> 资料访问日期：**2026-08-03**。除特别说明外，源码链接均固定到本次检查的 commit，避免随主分支变化而失去可复核性。

## 1. 先给结论

1. **Antmicro `cfd-simulation-scripts` 可以作为 OpenFOAM 的批处理包装器，但还不是面向 LLM/服务编排的 CFD 引擎。**它提供 `cfd-pre`、`cfd-post`、`cfd-utils` 三组 Typer CLI，能串起网格生成、并行 `chtMultiRegionSimpleFoam`、重构、温度曲线、ParaView/Blender 后处理和缩减输出；输入仍然是人工准备的完整 OpenFOAM case，输出主要是日志、目录树、图片/GLTF/Blend/Markdown，而不是稳定的结构化任务 API。
2. **它适合先包在受控 worker 中，而不适合让 LLM 直接拼 shell 命令。**调用方必须管理当前工作目录、OpenFOAM shell、MPI/CPU/GPU（该仓库的求解路径本身使用 CPU `mpirun`）、外部工具、超时、取消、重试和结果校验。源码没有任务 ID、状态查询、断点恢复、资源配额、结构化事件/JSON 结果或输入 schema 校验。
3. **NVIDIA 的方向是“高保真 CFD + AI surrogate + 交互式可视化”的组合，而不是把 LLM 直接当数值求解器。**NVIDIA 官方 CFD 页面把传统 CFD 描述为批处理，并建议用 PhysicsNeMo 等 AI-physics surrogate 做快速设计迭代，再用传统高保真求解器验证；OpenUSD/Omniverse 是可替换的可视化/数据互操作层。
4. **如果目标是让实验 loop 先获得可交互的流场反馈，PhysicsNeMo-CFD/DoMINO NIM 比直接驱动 OpenFOAM 更容易被程序化调用。**PhysicsNeMo-CFD 提供 Python API、Hydra 配置 benchmark、模型/数据集/指标注册机制和 NIM HTTP 客户端；DoMINO NIM 有 OpenAPI、健康检查、显式参数和二进制结构化响应。但它是特定训练分布的 surrogate，不应替代最终的高保真验证。
5. **许可证需要在集成前单独清理。**Antmicro 仓库当前没有 LICENSE 文件，GitHub API 的 `license` 字段也是 `None`；不能假定可以复制、再分发或修改其代码。PhysicsNeMo 和 PhysicsNeMo-CFD 声明 Apache-2.0；DoMINO NIM 容器/API 的 OpenAPI 声明为 NVIDIA Software License Agreement，且需要 NGC API key，不能按 Apache 项目处理。

## 2. 资料与版本基线

| 资料 | 本次核对的版本/页面 | 主要用途 |
| --- | --- | --- |
| Antmicro `cfd-simulation-scripts` | [`6435257a59e1468ee4fd2812ef82d6a7e2838c93`](https://github.com/antmicro/cfd-simulation-scripts/tree/6435257a59e1468ee4fd2812ef82d6a7e2838c93)，`main` 最新 commit 日期 2026-04-13 | OpenFOAM case 要求、CLI、输入输出、依赖和许可证状态 |
| Antmicro README | [README.md](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/README.md) | 官方安装/使用说明 |
| Antmicro OpenFOAM 说明 | [openfoam.md](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/openfoam.md) | case 目录、网格、边界条件和热源要求 |
| NVIDIA CFD 官方使用案例 | [Computational Fluid Dynamics (CFD) Simulation（en-US）](https://www.nvidia.com/en-us/use-cases/computational-fluid-dynamics-simulation/)；用户提供的[繁中页面](https://www.nvidia.com/zh-tw/use-cases/computational-fluid-dynamics-simulation/)（页面版权/更新信息为 2026） | NVIDIA 对 CUDA-X、PhysicsNeMo、surrogate、Blueprint 和端到端 loop 的官方定位 |
| PhysicsNeMo 核心 | [`NVIDIA/physicsnemo` main @ `840bb02e7e4400b591b9274bd11ea8dee99b8b91`](https://github.com/NVIDIA/physicsnemo/tree/840bb02e7e4400b591b9274bd11ea8dee99b8b91)；[README](https://github.com/NVIDIA/physicsnemo/blob/840bb02e7e4400b591b9274bd11ea8dee99b8b91/README.md) | Python 物理机器学习框架、部署/训练边界、许可证 |
| PhysicsNeMo-CFD | [`NVIDIA/physicsnemo-cfd` main @ `0d2305e1777351569b1795ce38884ee945491d28`](https://github.com/NVIDIA/physicsnemo-cfd/tree/0d2305e1777351569b1795ce38884ee945491d28)；[README](https://github.com/NVIDIA/physicsnemo-cfd/blob/0d2305e1777351569b1795ce38884ee945491d28/README.md) | CFD surrogate 推理、benchmark、混合初始化和 API 稳定性 |
| DoMINO NIM 快速入门 | [Quickstart Guide](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/quickstart-guide.html) | 容器、GPU、健康检查、STL 输入和请求示例 |
| DoMINO NIM API | [API Reference](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/api-reference.html) 与官方 [OpenAPI YAML](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/_static/_static/yaml/domino-automotive-aero.openapi.yaml) | 可编程接口、输入约束、响应格式、错误/健康端点、许可证 |
| DoMINO NIM 适用性 | [Usability Guide](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/usability-guide.html)、[Support Matrix](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/support-matrix.html)、[Performance](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/performance.html) | 训练分布、几何/速度约束、GPU 和性能边界 |

## 3. Antmicro `cfd-simulation-scripts`：真实能力

### 3.1 它是什么

仓库 README 将项目定义为“用于多区域稳态共轭传热（conjugate heat transfer）模拟收敛和自动结果可视化的开源工具”。它明确依赖外部 OpenFOAM 和 ParaView，并把自身安装成 Python 3.11 的 `cfd-scripts` 包；README 的安装示例默认安装 `openfoam2512-default`、ParaView 6.0、`cfd-scripts` 和 PCBooth。仓库的 `pyproject.toml` 公开了 Python 约束 `>=3.11,<3.12`、依赖（Typer、pandas、NumPy、matplotlib、bpy、PyYAML、psutil 等）以及三个入口点：

- `cfd-pre = preprocessing.pre_api:main`
- `cfd-post = postprocessing.post_api:main`
- `cfd-utils = utils.utils_api:main`

依据：[`README.md#installation`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/README.md#installation)、[`pyproject.toml`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/pyproject.toml)。

这里的 `openfoam2512` 是 OpenCFD 官方预编译包提供的 shell-session wrapper，而不是 Python 库。OpenCFD 的[预编译包说明](https://gitlab.com/openfoam/core/openfoam/-/wikis/precompiled)写明：包提供 OpenFOAM runtime/solver/utils 和版本化 shell wrapper，可并行安装多个版本；可视化（例如 ParaView）及外部 solver 模块不一定随包提供。因此 Antmicro README 另外要求安装 ParaView 和 PCBooth，worker 不能只安装 `cfd-scripts` 就宣称环境就绪。

它不是 OpenFOAM 求解器，也没有 CAD-to-case 建模器或 LLM/HTTP 服务；它只是把 OpenFOAM 工具链和若干后处理工具串起来。求解器、网格质量、物性、边界条件和热源仍由 case 文件决定。

### 3.2 输入：人工准备的 OpenFOAM case

官方 `openfoam.md` 要求 case 至少包含 `0/`、`constant/`、`system/`。关键输入包括：

- `constant/regionProperties` 和各区域的 `thermophysicalProperties`；流体区域还需要 `turbulenceProperties`。
- `0/{region_name}/` 下的温度、流动、压力、湍流等边界条件。
- `system/domain0/fvOptions` 中的风扇源（自适应风扇曲线或常量流量）和 `system/{heater_region}/fvOptions` 中均匀分布的热源。
- `constant/triSurface` 中、以米为 SI 单位的 `.stl` 几何；`blockMeshDict`、`surfaceFeatureExtractDict`、`snappyHexMeshDict`、区域检测配置等网格文件。
- `system/controlDict` 中的迭代次数、写出间隔和每个区域的 `fieldMinMax` 监控函数。后处理读取的文件路径固定为 `postProcessing/{region}/minMaxT_{region}/0/fieldMinMax.dat`。

依据：[OpenFOAM case setup](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/openfoam.md)、[README 的 case/config 章节](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/README.md#openfoam-case-preparation)。

后处理另需 case 根目录的 `config.json`，至少描述区域名及 `fluid`/`solid` 类型；可选 `vis_planes` 和 `temperature_range`。官方示例：[basic-cube/config.json](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/examples/basic-cube/config.json)。这个 JSON 没有随包提供的 JSON Schema，代码通过 `json.load` 直接读取。

### 3.3 可执行阶段和输出

| 命令 | 代码实际执行的阶段 | 主要输入/输出 |
| --- | --- | --- |
| `cfd-pre mesh` | `blockMesh` → `surfaceFeatureExtract` → `snappyHexMesh -overwrite` → `checkMesh -allGeometry -allTopology` → `splitMeshRegions -cellZones -overwrite` | 在当前目录读写 OpenFOAM case；每个阶段产生同名 `HH_MM_SS.log`；网格保留在当前 case |
| `cfd-pre simulate` | 重写 `system/decomposeParDict` 的 `numberOfSubdomains` 为物理 CPU 核数；`topoSet -region domain0` → `decomposePar -allRegions` → MPI `chtMultiRegionSimpleFoam` → `reconstructPar -allRegions` | 读取/写入各区域时间步、`processor*`、`postProcessing`；日志同样是文本文件 |
| `cfd-post plot` | 读取 `fieldMinMax.dat`，输出温度-迭代次数图 | `plots/` 下的图片 |
| `cfd-post visualize` | 调用 `pvpython` 生成 ParaView 预览、GLTF 和流线 | `previews/`、`gltf/` |
| `cfd-post generate-blend` | 用内置 Blender 模板导入 GLTF 和材料/几何节点 | `auto.blend`、`manual.blend` |
| `cfd-post render-frames` / `combine-frames` | PCBooth 渲染和 FFmpeg 合成 | `renders/` 下帧和 WebM |
| `cfd-utils reduce-sim-output` | 找最大数字时间步，只复制最后步、`0/`、`constant/`、`system/`、必要 `postProcessing`/VTK | 默认 `reduced/` |
| `cfd-utils generate-report` | 读取温度数据和工具版本，写 Markdown | 默认 `README.md` |

依据：[`pre_api.py`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/preprocessing/pre_api.py)、[`post_api.py`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/postprocessing/post_api.py)、[`utils_api.py`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/utils/utils_api.py)、[`common.py`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/utils/common.py)。

### 3.4 对自动编排最重要的源码事实

以下不是推测，而是对固定 commit 的源码行为进行的审阅：

1. `_run_command()` 通过 `subprocess.Popen` 启动 `openfoam2512 <command...>`，将 stdout/stderr 合并到文本日志；失败只根据非零返回码抛出通用 `RuntimeError("<command> failed")`。没有 JSON 事件、阶段状态、错误分类或取消/超时参数。[`pre_api.py#L14-L55`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/preprocessing/pre_api.py#L14-L55)
2. `mesh()` 没有 case-path 参数，所有 OpenFOAM 子进程继承调用者当前工作目录。[`pre_api.py#L57-L69`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/preprocessing/pre_api.py#L57-L69)
3. `simulate(simulation=...)` 只使用该参数定位 `system/decomposeParDict`；后续 `topoSet`、`decomposePar`、`mpirun`、`reconstructPar` 仍通过没有 `cwd=` 的 `_run_command()` 启动，因此 worker 必须显式把 cwd 设为 case 目录（或在更高层封装这一点）。源码还会无条件用 `psutil.cpu_count(logical=False)` 覆盖 `numberOfSubdomains`，没有 CPU 额度/并发参数。[`pre_api.py#L72-L107`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/preprocessing/pre_api.py#L72-L107)
4. `reduce_sim_output` 若输出目录已存在会直接 `shutil.rmtree()` 后重建，并假设至少存在一个数字时间步；这不是幂等、原子或可回滚的 artifact 操作。[`utils_api.py#L13-L70`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/utils/utils_api.py#L13-L70)
5. 多个后处理命令使用 `subprocess.run(...)` 但不设置 `check=True`，函数随后仍打印“finished/generated”；因此外层不能只看进程退出码就认为所有可视化产物有效，必须检查目标文件和日志。[`post_api.py#L44-L59`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/postprocessing/post_api.py#L44-L59)、[`post_api.py#L93-L173`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/postprocessing/post_api.py#L93-L173)
6. `SimulationTemperatureData` 直接用 pandas 读取固定列数的 `fieldMinMax.dat`，读取不到、列数不符或文件为空会抛出普通 Python 异常；没有面向调用者的结果 schema。[`common.py#L44-L78`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/utils/common.py#L44-L78)
7. CLI 模块底部直接调用 `app()`，设计中心是终端命令而非可复用服务对象。它没有任务队列、服务端状态、心跳、断点/恢复、幂等 run key、资源限额、沙箱或权限边界。[`pre_api.py#L110`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/preprocessing/pre_api.py#L110)、[`post_api.py#L175`](https://github.com/antmicro/cfd-simulation-scripts/blob/6435257a59e1468ee4fd2812ef82d6a7e2838c93/src/postprocessing/post_api.py#L175)。

**可调用性判定（Antmicro）：**“可由 worker 包装后自动化”，而非“LLM 可直接丝滑调用”。最低限度的 adapter 需要把输入 manifest 转成受控 case 目录，固定 cwd，执行白名单命令，采集每阶段日志和返回码，检查产物，设置超时/取消/CPU 配额，并将结果归一化为 JSON；LLM 只应调用这个 adapter 的窄接口。

## 4. NVIDIA CFD / PhysicsNeMo：官方定位和边界

### 4.1 NVIDIA 官方 CFD 页面给出的架构方向

NVIDIA 官方页面明确将以下组合描述为构建实时互动流体数字孪生的参考架构：

- CUDA-X 加速求解器/数值密集部分；
- PhysicsNeMo 等 AI-physics 框架训练 surrogate；
- Omniverse libraries / OpenUSD 做交互式、高保真可视化与数据连接。

页面明确写出：传统 CFD solver 是批处理；AI-physics surrogate 可以近乎实时预测流场，之后再由高保真 CFD 验证。Blueprint 允许把 PhysicsNeMo 换成自定义 AI 模型，并把 CFD solver 或 surrogate 通过 OpenUSD 接到 Omniverse。页面列出的端到端例子为 `CAD → meshing → GPU-accelerated CFD solve → AI surrogate → Omniverse visualization`。

依据：[NVIDIA CFD use case（正文及 FAQ）](https://www.nvidia.com/en-us/use-cases/computational-fluid-dynamics-simulation/)。这些是官方参考架构和厂商用例，不是 Vegapunk 硬件上的性能保证；页面中的“orders of magnitude”“48x”等数字应视为 NVIDIA/合作伙伴特定硬件与工作负载的宣传/案例结果，不能直接外推。

### 4.2 PhysicsNeMo 核心框架

PhysicsNeMo README 将其定义为用于构建、训练、微调和推理 Physics AI 模型的开源深度学习框架，支持 neural operators、GNN、transformers、PINNs 等，并提供 `physicsnemo.models`、datapipes、distributed、symbolic PDE 和 checkpoint/ONNX/deployment 相关模块。它是 PyTorch 之上的 Python 组件库，不是一个可替代 OpenFOAM 的通用 CFD 求解器，也不是 LLM agent runtime。

依据：[PhysicsNeMo README 的 What is PhysicsNeMo / Components / Extensibility](https://github.com/NVIDIA/physicsnemo/blob/840bb02e7e4400b591b9274bd11ea8dee99b8b91/README.md#what-is-physicsnemo)。

### 4.3 PhysicsNeMo-CFD 的真实接口

PhysicsNeMo-CFD README 将其定义为 PhysicsNeMo 的 CFD 子模块，提供：

- **NIM inference**：`physicsnemo.cfd.evaluation.nims.call_domino_nim`，从 Python 调用已部署的 DoMINO NIM；
- **benchmark/evaluation**：Hydra/OmegaConf 配置驱动模型×数据集推理、指标、JSON/CSV/HTML、可选 PNG/VTK；支持注册自定义 `CFDModel`、dataset adapter、metric 和 visual；
- **hybrid initialization**：将 DoMINO 预测与 potential-flow/OpenFOAM 工作流结合，为后续高保真瞬态 CFD 提供初始条件。

该 README 也明确标注 PhysicsNeMo-CFD 为 **experimental library、currently v0**，面向演示 workflow，**不是 production-level stable API**，预期存在 breaking changes。[README 安装说明](https://github.com/NVIDIA/physicsnemo-cfd/blob/0d2305e1777351569b1795ce38884ee945491d28/README.md#installation)

可编排性明显好于纯 shell CLI：benchmark 有 YAML schema、设备/seed/output_dir、case_id、metrics cache、失败策略、多 GPU case sharding，输出文件名和字段也写在 README 中。但仍需把它放在隔离 worker/容器中管理 GPU、模型缓存、数据体积和版本锁定；“实验 loop 可调用”不等于“模型结果天然可信”。

## 5. DoMINO NIM：LLM/程序化调用面和限制

### 5.1 部署/运行前提

官方 Quickstart 要求拉取 NVIDIA NGC 容器（文档示例镜像约 31 GB 未压缩），设置 `NGC_API_KEY`，以 NVIDIA runtime 和 GPU 启动容器并暴露 HTTP 8000；模型下载约 91 MB。`/v1/health/ready` 返回 `{"status":"ready"}` 后才能发推理请求。Support Matrix 给出优化配置（H100 80 GB、A100 40/80 GB、L40S 48 GB、RTX PRO 6000 Blackwell 96 GB）以及非优化配置最低约 40 GB GPU memory、compute capability ≥ 7.5、x86（ARM 尚不支持）。

依据：[Quickstart](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/quickstart-guide.html)、[Support Matrix](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/support-matrix.html)、[Runtime configuration](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/configuring-the-nim-at-runtime.html)。

### 5.2 明确的 HTTP/OpenAPI 接口

官方 OpenAPI 3.0.1 规范给出：

- `POST /v1/infer`：同时返回 volume + surface；`/v1/infer/volume` 和 `/v1/infer/surface` 可只跑一个域；
- multipart/form-data 必填 `design_stl`（当前只支持 batch size 1）；可选字符串参数 `stream_velocity`、`stencil_size`、`batch_size`、`point_cloud_size`，或 `.npy` 的 `point_cloud`（不能同时使用 `point_cloud_size`）；
- 200 响应为 `application/octet-stream`，内容是结构化数值数组；400 是输入校验错误，500 是内部 Triton 错误；
- `GET /v1/health/live`、`GET /v1/health/ready`、`GET /v1/model/config`、`GET /v1/openapi`、`GET /v1/metrics`、`GET /v1/license` 提供服务可观测性和模型配置。

官方 Quickstart/API 描述的输出字段包括 volume `coordinates`、`velocity`、`pressure`、`turbulent-kinetic-energy`、`turbulent-viscosity`、`sdf`、`bounding_box_dims`，surface `surface_coordinates`、`pressure_surface`、`wall-shear-stress`，以及全局 `drag_force`、`lift_force`。因此它适合写成带类型校验的 HTTP tool；不应让 LLM 自己解析任意文本日志。

依据：[DoMINO API Reference](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/api-reference.html)、[OpenAPI YAML](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/_static/_static/yaml/domino-automotive-aero.openapi.yaml)、[官方 Python 调用示例](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/quickstart-guide.html#inference-request)。

PhysicsNeMo-CFD 自己的 `call_domino_nim` 对此接口做了一个窄 Python 封装：先用 trimesh 把输入 STL 合并为单一 solid，使用 httpx multipart POST，处理 ConnectError/Timeout/status code，然后用 `numpy.load(BytesIO(response.content))` 返回数组字典。[固定源码](https://github.com/NVIDIA/physicsnemo-cfd/blob/0d2305e1777351569b1795ce38884ee945491d28/physicsnemo/cfd/evaluation/nims/domino_nim.py#L23-L175)

### 5.3 模型适用性边界

DoMINO NIM 官方 Usability Guide 给出硬约束/可信边界：

- 模型训练于 **RANS** 数据，面向 RANS-like prediction；不能直接把它和基于 LES 的数据集（文档举 DrivAerML）作无条件比较；
- STL 需单一、watertight、米制、规定轴向/姿态，建议分辨率大于 300k 点；
- 速度入口沿 x 轴，不支持 cross flow；20–50 m/s 是文档给出的最高准确度范围；
- `stencil_size` 越大通常精度越高但推理越慢，volume fidelity 随采样点数增加；
- 官方性能页的一个基准是 point cloud 50,000 时 L40S/A100/H100 约 7.17/8.02/7.20 秒；该数字只代表文档中的单样本、同机 client/NIM、三次平均实验，不能当作通用 SLA。

依据：[Usability Guide](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/usability-guide.html)、[Performance](https://docs.nvidia.com/nim/physicsnemo/domino-automotive-aero/latest/performance.html)。

**判定：**DoMINO NIM 的“服务调用面”已经足够明确，适合放在实验 loop 的快速 surrogate 分支；但 geometry/速度/训练分布检查、误差指标和最终 OpenFOAM/高保真复核必须由平台代码负责。LLM 只能提出参数/设计候选，不能把 surrogate 的单次响应当作经验证的物理事实。

## 6. 可调用性比较（面向实验 loop）

| 能力 | Antmicro cfd-scripts | PhysicsNeMo-CFD / DoMINO NIM | 对 LLM tool 的含义 |
| --- | --- | --- | --- |
| 调用协议 | 终端 CLI；OpenFOAM 子进程 | Python 函数 + Hydra CLI + HTTP/OpenAPI | NIM 可直接包成 typed tool；cfd-scripts 需 worker adapter |
| 输入契约 | 完整 OpenFOAM case + `config.json`，无统一 schema | STL + 明确参数；benchmark YAML/数据集 adapter | 先 schema/validator，再允许模型提出候选 |
| 结果契约 | 日志、OpenFOAM 时间步、VTK/GLTF/图片/Markdown | NumPy 字段、drag/lift、JSON/CSV/HTML/VTK | 可直接做结构化 observation，但仍需物理校验 |
| 状态/恢复 | 无任务状态、心跳、恢复/取消 API | NIM 有 live/ready/metrics；benchmark 有缓存/分布式配置，但不是通用 job scheduler | 平台层必须补 run manifest、状态机、超时和 artifact index |
| 资源边界 | 脚本按物理 CPU 核数自动并行；外部 OpenFOAM/MPI/ParaView/Blender | GPU/容器/NGC key；NIM GPU memory 和输入点数可调 | 不能让 LLM 直接决定任意 `mpirun` 或 Docker 参数 |
| 可信性 | 可作为高保真验证路径，但网格/边界条件质量决定结果 | 特定 RANS 训练分布的 surrogate，需高保真复核 | 使用“两阶段”：surrogate 探索 → CFD 验证 |
| 许可证 | 当前仓库无 LICENSE/无 API license 信息 | PhysicsNeMo Apache-2.0；NIM NVIDIA Software License | 依赖/模型/数据分别做 license gate |

## 7. 集成前必须保留的工程护栏

以下结论直接由上述接口与源码边界推导，后续项目内设计应实现，而不是交给 LLM 自行决定：

1. **统一 run manifest**：固定 case 输入、几何哈希、OpenFOAM/脚本/NIM 镜像 digest、参数、随机 seed、GPU/CPU 资源、开始/结束时间和父实验 ID。
2. **白名单 adapter**：LLM 只调用 `prepare_case`、`run_surrogate`、`run_high_fidelity`、`collect_metrics` 这类窄工具；adapter 才能决定 cwd、容器挂载、命令 argv、环境变量、超时、取消和产物路径。
3. **先 schema 再运行**：对 STL 单 solid/watertight/单位/方向、OpenFOAM 必备文件、区域/边界/监控函数、参数范围和 license/模型可用性做预检；预检失败不启动昂贵求解。
4. **分层结果**：surrogate 结果标为“预测”，高保真 OpenFOAM 结果标为“验证”；保留两者及误差/收敛证据，不要覆盖。
5. **可恢复 artifact**：阶段输出写入不可变 run 目录；每阶段写结构化 `status.json`、日志索引和 checksum；失败时按阶段重试，避免使用 `reduce-sim-output` 这类会删除既有目录的操作作为默认路径。
6. **可信性与安全**：禁止把完整 shell、路径、Docker 或 arbitrary Python 暴露给 LLM；对许可证、NGC 密钥、环境变量和上传 STL 做隔离；NIM 官方文档明确需要 NGC key，PhysicsNeMo benchmark 还提醒环境日志可能包含 secrets。

## 8. 许可证和再分发核验清单

- **Antmicro `cfd-simulation-scripts`**：仓库根目录在本次 commit 只有 `.ci.yml`、`.gitignore`、README、examples、img、openfoam.md、pyproject、src 等，没有 `LICENSE`/`COPYING`；GitHub API `GET /repos/antmicro/cfd-simulation-scripts/license` 返回 404，仓库 metadata `license` 为 `null`。在版权所有者明确授权前，建议只把它作为外部依赖/参考流程，避免复制代码进 Vegapunk 或再发布二进制。
- **PhysicsNeMo**：README 明确声明 Apache License 2.0，仓库有 `LICENSE.txt`；固定源码头部也带 SPDX Apache-2.0。[README License](https://github.com/NVIDIA/physicsnemo/blob/840bb02e7e4400b591b9274bd11ea8dee99b8b91/README.md#license)
- **PhysicsNeMo-CFD**：`README` 和 `pyproject.toml` 声明 Apache-2.0，仓库含 `LICENSE.txt`；但 README 将其标为 experimental/v0，生产使用仍需锁版本和自测。[README](https://github.com/NVIDIA/physicsnemo-cfd/blob/0d2305e1777351569b1795ce38884ee945491d28/README.md#license)
- **DoMINO NIM**：官方 OpenAPI `info.license` 是 NVIDIA Software License Agreement；部署需要 NGC API key。NIM 容器、模型权利及模型输出限制应按 NVIDIA NGC/EULA 单独审核，不能由 PhysicsNeMo 的 Apache-2.0 传递。
- **数据集**：PhysicsNeMo-CFD benchmark README 对 DrivAerML 数据集标注 CC BY-SA 4.0；若使用该数据训练/验证，需遵守数据集 attribution/share-alike 要求，且不能把数据许可误认为模型或 NIM 许可。[benchmark README](https://github.com/NVIDIA/physicsnemo-cfd/blob/0d2305e1777351569b1795ce38884ee945491d28/workflows/benchmarking/README.md#drivaerml-dataset-download-and-directory-layout)

---

*本节到此为外部资料与可调用性评估；Vegapunk 内部 loop、后端入口和具体 adapter seam 由后续章节补充。*

## 9. Vegapunk 当前后端：已有的可复用 seam

本节是对当前分支（检查日期 2026-08-03）的代码映射。它描述现有事实，并把“适合放置 CFD 的位置”和“暂时不要改动的位置”分开。

### 9.1 外层实验 loop

`launch_discovery._main()` 已经是一个多轮实验编排器，而不只是一次性脚本：

1. `--resume` 会读取已有 launch 的 `discovery_summary.json`，把 `completed_rounds` 恢复为下一轮起点；恢复粒度是“已完成轮次”，不是求解器进程或单个阶段。
2. 它为每次 launch 建立 `results/<task>/<timestamp>_launch/`，每轮建立 `session_*`，保存 prompt、ideas、trajectory 和实验结果。
3. 每一轮先由 `IdeaGenerator.generate_ideas()` 生成/整理候选，再由 `ExperimentRunner.run_experiments()` 执行；增量模式会从上一轮最佳目录更新下一轮 baseline。
4. 轮次结束后写 `discovery_summary.json`，最后交给 PaperOrchestra 做一次 handoff。

证据：`launch_discovery.py:641-653`（resume 起点）、`launch_discovery.py:704-737`（launch 与 prompt 快照）、`launch_discovery.py:871-889`（轮次和 incremental baseline）、`launch_discovery.py:923-1060`（idea/experiment 阶段）、`launch_discovery.py:1137-1170`（summary 与 handoff）。

这意味着 CFD 最自然的第一接入点不是重新设计 MAS 状态机，而是作为一种新的、可观测的 Experiment backend；CFD 自己的阶段状态需要嵌入每个 candidate 的 run artifact 中，不能只依赖外层 round 状态。

### 9.2 ExperimentRunner 与现有外部执行边界

`ExperimentRunner` 已经承担了四类通用职责：

- 初始化资源分配器和并行上限（`stage.py:466-557`）；
- 为每个 idea 建立隔离工作目录（`stage.py:715-848`）；
- 通过 `exp_backend` 分派 Codex、iFlow、OpenHands（`stage.py:899-1059`）；
- 收集性能并把成功结果写入在线记忆（`stage.py:1061-1171`）。

其中 `_run_single_experiment()` 用 semaphore 包住单个 candidate，说明“一个 candidate 的资源 lease”已经有现成概念；但现有 lease 主要表达 GPU 数量，不能表达 OpenFOAM/MPI 的 CPU 核、内存、临时磁盘和独占 case 目录。

### 9.3 `run_experiment` 已有的过程契约

Codex backend 的 `run_experiment()` 把一个 candidate 变成如下过程：

1. 复制主工作区到 `run_N/`；
2. 在 `run_N/` 启动固定的 `bash launcher.sh`；
3. 用 `Popen` 合并并实时记录 stdout/stderr；
4. 支持 wall-clock timeout，失败时读取 `traceback.log`；
5. 成功时读取 `run_N/final_info.json`，把它作为下一轮提示和性能比较的依据。

证据：`vegapunk/experiments_utils_codex.py:218-375`、`vegapunk/experiments_utils_codex.py:449-587`。

这个契约与 Antmicro 的“当前目录 + CLI + 日志 + 结果目录”边界相容，因此可以做一个 CFD adapter，而不必把 OpenFOAM Python/C++ 代码嵌进 Vegapunk。需要注意的是，CFD case 可能包含很大的 STL、网格和时间步，盲目沿用 `copytree` 会产生很高的复制成本；应把不可变几何/模板与可写的 solver workspace 分开。

### 9.4 LLM tool loop 与 MCP

Vegapunk 已有两个可以复用、但不能单独承担 CFD 安全职责的工具 seam：

- `ModelToolLoop.run()` 将模型请求、工具调用、工具输出、错误和下一轮 response 串成有限循环，并限制 `max_iterations`/`max_tool_calls`；错误会作为模型可见证据而不是静默吞掉。证据：`vegapunk/mas/agents/tool_loop.py:45-131`。
- `MCPToolkit`/`_MCPServer` 支持本地 stdio 或 HTTP/SSE MCP server，读取工具的 JSON Schema，动态生成 `FunctionTool` 并调用 `call_tool`。证据：`vegapunk/mas/agents/dr_agents/camel/toolkits/mcp_toolkit.py:82-126`、`:164-321`、`:324-509`。

因此可以把 CFD 包装成一个本地 stdio MCP server，或者把 MCP 作为 Web sidecar 的窄 facade；但真实的 cwd、命令 allowlist、资源 lease、状态机和 artifact 逻辑必须留在共享的 `CfdExecutionService`，不能藏在 prompt 或动态生成的 shell 中。

### 9.5 当前指标契约的限制

现有 `ExperimentRunner._calculate_experiment_performance()` 从 `run_0/final_info.json` 和最新 `run_N/final_info.json` 读取 `means`，随后对同名指标计算变化并求平均（`vegapunk/stage.py:597-658`）。这对单一 accuracy 类任务尚可，但对 CFD 不安全：

- 最大温度、压力降、残差、能耗、流量偏差可能有不同优化方向；
- 不同区域/不同单位的指标不能无权平均；
- 一个数值变好不能抵消 mesh quality、收敛性或物理约束失败；
- 缺少显式 `converged`、`residual_threshold`、`primary_metric` 和 `optimization_direction`。

PaperOrchestra 的 candidate selection 已经有更严格的 `primary_metric` 和数值有效性检查（`vegapunk/paper_orchestra/candidate_selection.py:790-855`），CFD 应沿用“显式 primary metric + direction + provenance”的思路，而不是扩展当前的无方向平均。

### 9.6 本机运行时基线

2026-08-03 在本机做了只读可用性检查：

| 检查项 | 结果 | 含义 |
| --- | --- | --- |
| `python3 --version` | `Python 3.14.4` | Antmicro `pyproject.toml` 要求 `>=3.11,<3.12`，不能直接使用当前解释器安装 |
| `openfoam2512` | 未找到 | OpenFOAM shell 尚未安装/不在 PATH |
| `cfd-pre`、`cfd-post`、`cfd-utils` | 未找到 | Antmicro wrapper 尚未安装 |
| `chtMultiRegionSimpleFoam`、`mpirun` | 未找到 | CFD 求解器和 MPI 运行时尚未就绪 |
| `paraview`、`pvpython` | 未找到 | 可视化链尚未就绪 |
| GPU | NVIDIA GeForce RTX 4060，8,188 MiB | 有 GPU，但 Antmicro 求解路径是 CPU `mpirun`；不能把“有 GPU”当作 OpenFOAM GPU 加速已具备 |

这说明当前是架构设计阶段，不是已经可以提交 CFD job 的运行环境。第一阶段应先建立可重复的环境检查和 smoke case，不应把安装失败留给 LLM 在实验过程中猜测。

## 10. 适配度结论

| 维度 | Antmicro 脚本现状 | Vegapunk 可复用能力 | 结论 |
| --- | --- | --- | --- |
| 执行协议 | CLI，依赖当前 cwd | `run_experiment` 已有隔离 cwd、Popen、日志 | **强**：适合 worker adapter |
| 输入契约 | 完整 OpenFOAM case，只有约定没有统一 schema | task 目录、prompt 和 launcher 约定 | **中**：必须新增 manifest/validator |
| 结果契约 | 日志、时间步、VTK/GLTF/图片/Markdown | `final_info.json` 和 artifact 目录 | **中**：需归一化 metrics/status/manifest |
| LLM 原生工具 | 没有 HTTP/MCP/JSON-RPC | 已有 MCP schema 和 ModelToolLoop | **中**：应加窄 MCP facade，禁止 raw shell |
| 长任务 | 无 job id、心跳、取消、超时、状态查询 | 外层 launch 有日志/timeline，但 solver 阶段不持久化 | **弱**：CfdJob 状态机是必需品 |
| 断点恢复 | 无 solver checkpoint/resume API | 仅恢复完成轮次 | **弱**：至少恢复到最后成功 stage |
| 资源控制 | 按物理 CPU 核自动改 `decomposeParDict` | 现有 GPU semaphore | **弱**：需要 CPU/MPI lease 和独占目录 |
| 指标比较 | 主要是 `fieldMinMax.dat` 温度数据 | 当前 scorer 默认平均变化 | **弱**：需要 primary metric/direction/约束 |
| 可视化 | ParaView/Blender/PCBooth 产物丰富 | launch artifact 可投影到 Web | **中**：只暴露 curated manifest |
| 依赖/授权 | 外部 OpenFOAM、ParaView、PCBooth；Antmicro 无许可证文件 | 仓库可运行外部命令 | **需 gate**：法律和环境检查先于集成 |

**总体判定：**它已经具备“被一个受控 worker 自动运行”的基础，但尚不具备“被 LLM 丝滑调用”的基础。缺口不是模型 prompt，而是 typed input、作业状态、资源隔离、结构化结果、可恢复性和授权边界。

## 11. 推荐的目标架构

### 11.1 一条共享执行服务，两个 CFD lane

建议先设计一个共享的 `CfdExecutionService`，让不同调用面复用同一套状态、资源、日志和 artifact 逻辑：

```text
LLM / Web request
        |
        v
SimulationPlan (versioned JSON)
        |
validate -> preview/diff -> policy/approval
        |
        v
CfdExecutionService (job state, lease, cwd, timeout, events)
        |------------------------------|
        v                              v
high-fidelity lane                surrogate lane
Antmicro/OpenFOAM worker          PhysicsNeMo/DoMINO NIM worker
        |                              |
        v                              v
metrics + convergence + artifacts + prediction metadata
        \______________________________/
                       |
                       v
round scorer / memory / PaperOrchestra / Web projection
```

两个 lane 必须在结果中明确标记：

- `prediction`：PhysicsNeMo/DoMINO surrogate 的快速估计，只用于筛选或初始化；
- `validation`：OpenFOAM 等高保真求解器的结果，必须附 mesh、边界、收敛和版本证据。

不能把 surrogate 的一次推理伪装成已验证的 CFD 结果，也不能把 NVIDIA 页面中的硬件性能数字当作本机 SLA。

### 11.2 第一选择：外部 adapter，不 vendor Antmicro 代码

第一阶段不应把 Antmicro 源码复制进 Vegapunk：

1. 仓库没有 LICENSE 文件，GitHub metadata 的 `license` 也为 `null`；在获得明确授权前，复制和再分发存在风险。
2. CLI 模块底部直接 `app()`，设计中心是进程边界而不是稳定 library API；直接 import 会把 Typer 应用生命周期带入后端。
3. 外部命令本来就是 OpenFOAM 的自然接口；Vegapunk 需要的是围绕它的作业服务，而不是重写求解器。

因此建议在本地 worker/container 中安装固定版本的 `cfd-scripts`，由 Vegapunk adapter 通过显式 argv 和固定 cwd 调用。许可证清理完成、需要长期维护时，再评估 fork 或重新实现最小的命令编排层。

### 11.3 建议新增的内部模块（提案）

以下路径是建议的新增 seam，不代表本次已实现：

| 模块 | 责任 |
| --- | --- |
| `vegapunk/cfd/models.py` | `SimulationPlan`、`CfdJob`、`CfdStage`、`CfdMetrics`、`CfdArtifact`、状态事件的 typed model |
| `vegapunk/cfd/capabilities.py` | 检查 Python/OpenFOAM/cfd-scripts/ParaView/MPI 版本、solver 能力、CPU/GPU/内存和 license gate |
| `vegapunk/cfd/validation.py` | manifest、单位、维度、区域、边界、STL、`controlDict` 监控函数和资源上限预检 |
| `vegapunk/cfd/runner.py` | 异步 job、固定 cwd、argv、环境白名单、timeout/cancel、阶段重试、进程组清理和资源 lease |
| `vegapunk/cfd/antmicro_adapter.py` | 将 plan 编译为 mesh/simulate/postprocess/report 的白名单命令；对 Antmicro cwd/参数缺陷做上层补偿 |
| `vegapunk/cfd/surrogate_adapter.py` | 对 PhysicsNeMo/DoMINO NIM 做 typed HTTP/Python 调用、健康检查和 prediction provenance |
| `vegapunk/cfd/metrics.py` | 解析 `fieldMinMax.dat`/OpenFOAM logs/solver report，产出带单位、区域、方向和收敛证据的 JSON |
| `vegapunk/cfd/artifacts.py` | 生成不可变 artifact manifest、大小/hash/MIME/来源 stage，过滤敏感路径和大文件默认展示 |
| `vegapunk/cfd/mcp_server.py` | 可选本地 stdio MCP facade；只暴露窄工具，内部调用同一个 `CfdExecutionService` |

对现有代码的最小改动建议：

- `vegapunk/stage.py`：把 `if self.backend == ...` 逐步抽成 backend registry/protocol，新增 `cfd` adapter；不要把 OpenFOAM 细节散落到 `ExperimentRunner` 的每个分支。
- `launch_discovery.py`：为 CFD 引入显式任务类型/manifest（而不是继续靠“有无 `prompt.json`”猜测），在 summary 中保存 `job_id`、stage 状态和 primary metric；保留当前 round-level resume 作为外层恢复。
- `config/default_config.yaml`：增加 `cfd` profile（CPU cores、MPI ranks、memory、wall time、case size、parallelism=1、adapter version），不要复用默认 GPU 数值。
- `tests/`：先用 fake `openfoam2512`/`cfd-pre`/`mpirun` 可执行文件做契约测试，再做真实 basic-cube smoke；不要在普通单元测试中依赖本机 OpenFOAM。
- `desktop/openworker/upstream/coworker/server/`：等核心 service 稳定后再加 HTTP job/status/cancel/artifact projection；浏览器只看到 launch 内部的 curated CFD artifacts，不获得任意路径读取权。

## 12. `SimulationPlan` 与结果契约

### 12.1 LLM 只生成受限计划

LLM 的输出应是可校验 JSON，而不是 Python、Scheme、Java 或 shell。OpenFOAM 版本的最小计划可以是：

```json
{
  "schema_version": "vegapunk.cfd.plan.v1",
  "engine": "openfoam-antmicro",
  "case_template": "cfd/basic-cube-v1",
  "geometry_artifact_ids": ["stl:sha256:..."],
  "design_variables": {
    "heater_power_w": 120.0,
    "fan_flow_rate_m3_s": 0.004
  },
  "solver": {
    "mode": "steady_cht",
    "max_iterations": 800,
    "write_interval": 20
  },
  "resources": {
    "cpu_cores": 8,
    "memory_mb": 16384,
    "wall_time_s": 7200
  },
  "objective": {
    "primary_metric": "heater.max_temperature_c",
    "direction": "minimize",
    "constraints": [{"metric": "mesh.max_non_orthogonality", "lte": 70}]
  },
  "outputs": ["metrics", "temperature_plot", "reduced_case", "report"]
}
```

计划 validator 必须拒绝任意路径、任意环境变量、管道/重定向、任意 `mpirun` 参数、越过资源上限的 core 数、未知区域和没有单位的物理量。几何、模板和上传文件用 artifact ID/hash 引用，而不是由模型提供绝对路径。

### 12.2 Job 是异步的、分阶段的

建议状态为：

```text
created -> validating -> previewed -> approved -> queued
  -> preparing -> meshing -> mesh_validated -> solving
  -> postprocessing -> scoring -> completed
```

终态包括 `failed`、`cancel_requested`、`cancelled`、`interrupted`。每个 stage 记录 `started_at`、`ended_at`、`attempt`、`argv_digest`、`input_hash`、`exit_code`、日志引用和产物引用。

恢复规则：

- 只有在输入 hash、adapter 版本和前置 artifact 都匹配时，才能跳过已完成 stage；
- 进程被杀掉后必须标成 `interrupted`，不能仅凭目录存在就当作成功；
- `simulate` 产生的时间步、processor 目录和日志都应作为 stage 输出登记；
- 不把 Antmicro 的 `reduce_sim_output` 作为 canonical artifact 的覆盖操作，因为它在输出目录存在时会先 `rmtree`；只在独立的派生目录执行，并使用临时目录 + 原子 rename。

### 12.3 `final_info.json` 不能只是一组裸均值

为了兼容现有 loop，可继续写 `run_N/final_info.json`，但 CFD 内容应至少包含：

```json
{
  "cfd": {
    "means": {
      "heater.max_temperature_c": 73.4,
      "domain0.outlet_pressure_pa": 100842.0
    },
    "primary_metric": "heater.max_temperature_c",
    "optimization_direction": "minimize",
    "converged": true,
    "mesh_valid": true,
    "solver": "chtMultiRegionSimpleFoam",
    "solver_version": "openfoam2512",
    "metric_provenance": [
      "postProcessing/heater/minMaxT_heater/0/fieldMinMax.dat"
    ]
  }
}
```

外层 scorer 应使用 `primary_metric` 和 `optimization_direction`，并在 `converged=false`、mesh invalid、指标缺失或非有限时拒绝 candidate。多目标优化应显式使用约束/权重/帕累托规则，而不是把所有区域和单位直接取平均。

## 13. 面向 LLM 的工具面

第一版工具保持小而稳定，建议如下：

| 工具 | 作用 | 默认策略 |
| --- | --- | --- |
| `cfd.inspect_capabilities` | 返回 adapter、solver、版本、CPU/GPU、license 和可用 stage | 只读 |
| `cfd.inspect_case` | 返回区域、边界、几何 hash、已有 stage/artifact 和缺失文件 | 只读 |
| `cfd.validate_plan` | 校验 schema、单位、枚举、依赖、资源和安全策略 | 只读 |
| `cfd.preview_changes` | 返回将改动的字典、资源估算、覆盖风险和预计产物 | 只读 |
| `cfd.submit_job` | 创建异步 job，固定 plan snapshot | 需 approval/policy |
| `cfd.get_status` | 获取状态、当前 stage、进度、警告和短错误摘要 | 只读 |
| `cfd.cancel_job` | 请求进程组安全停止并登记原因 | 需 policy |
| `cfd.read_metrics` | 读取白名单标量、收敛曲线摘要和单位 | 只读 |
| `cfd.export_artifacts` | 生成 curated artifact manifest 或派生 reduced output | 只读/需 policy |

不要把 `openfoam2512`、`bash -c`、任意 `mpirun`、任意 Python 或完整文件系统浏览暴露给模型。MCP server 只负责把这些工具的 JSON Schema 暴露给 `ModelToolLoop`；长时间计算通过 job ID 返回，LLM 后续调用 `get_status`/`read_metrics`，不应占住一个同步 HTTP 请求。

## 14. 关键工程护栏

### 14.1 资源和并发

- Antmicro `simulate` 会把 `numberOfSubdomains` 改成所有物理 CPU 核，并启动 MPI；Vegapunk 配置默认允许最多 4 个 candidate，GPU allocator 在本机单卡时可能把实际并发降到 1，但它并不会替 CFD 过程分配 CPU 核。任何允许多个 CFD candidate 的配置都会有严重 oversubscribe 风险。
- CFD profile 初期应强制 `parallelism=1`，由 scheduler 分配明确 `cpu_cores`/MPI ranks；一个 case 的 `system/`、`processor*`、时间步和 postProcessing 必须独占。
- 为每个 job 建立 CPU、内存、临时磁盘和 wall-time lease；若将来运行 PhysicsNeMo/DoMINO，再单独增加 GPU memory lease。
- 不把 RTX 4060 的存在理解为可运行 DoMINO NIM：官方 support matrix 和显存约束需要单独满足，且 NIM/模型版本、NGC key 和容器 digest 必须记录。

### 14.2 安全、路径和敏感信息

- worker 只允许在 launch-local root 下读写；解析 STL、case manifest 和 symlink 时拒绝路径逃逸。
- 不允许 `sudo`、任意网络、任意挂载、shell 插值和未审计环境变量；NGC/API/license secret 不能写入 `record_research_event`、日志或 artifact manifest。
- LLM 可以修改白名单设计变量或受控字典模板，不能直接改 launcher、执行脚本、容器参数和宿主机路径。
- 用户上传的 STL 必须有大小、面数、watertight、单位/姿态和格式上限；失败在 `validate_plan` 阶段返回，不启动求解器。

### 14.3 物理可信性

- mesh quality、边界映射、单位、区域类型、残差阈值、守恒误差和收敛状态要由程序检查；模型的自然语言解释不能替代这些证据。
- surrogate 输出永远标为 prediction，OpenFOAM/高保真 solver 输出标为 validation；保存两者和误差，不覆盖。
- 设计变量、case hash、solver/adaptor digest、输入参数、资源和随机 seed 都写入 run manifest，保证后续 PaperOrchestra/记忆层能复盘。

## 15. 分阶段实施路线

### P0：环境和授权 smoke（先于核心代码）

1. 建立独立 Python 3.11 环境，锁定 Antmicro commit、OpenFOAM 2512、ParaView、MPI 和 PCBooth 版本。
2. 通过 `cfd-pre mesh`、`cfd-pre simulate`、`cfd-post plot`、`cfd-utils generate-report` 跑通 `examples/basic-cube`，记录每阶段日志和输出 hash。
3. 核对 Antmicro 代码授权、OpenFOAM/ParaView/PCBooth/NVIDIA NIM 的许可证和部署条款；未清理前只使用外部依赖，不 vendor。

### P1：固定 case 的 deterministic adapter

1. 实现 `CfdExecutionService` 的 `inspect_case`、`validate_plan`、`submit_job`、`get_status`、`read_metrics`。
2. 只支持一个固定 basic-cube case、串行/受控 CPU 数、一个 primary metric；先不用 LLM。
3. 通过 fake binaries 测试 argv、cwd、timeout、退出码、日志、artifact hash 和 `final_info.json`，再做真实 smoke。

### P2：接入 Vegapunk ExperimentRunner

1. 引入显式 `cfd` task manifest 和 backend registry，避免继续靠 `prompt.json`/`task_info.json` 猜任务类型。
2. 将 CFD job 结果映射为现有 `run_N`/`final_info.json`/`discovery_summary.json`，但 scorer 改为 primary metric + direction + convergence gate。
3. 先强制一 job 一 case、一轮串行，完成 round-level resume；随后增加 stage-level resume。

### P3：MCP 与 Web 观察面

1. 用同一个 `CfdExecutionService` 提供本地 stdio MCP facade；模型只见窄工具和结构化结果。
2. 在已有 launch timeline/artifact 投影上增加 CFD stage、job status、短日志和 curated plots；Web API 只暴露 job ID 和 artifact manifest。
3. 加入 approval policy、cancel、retry、进程组清理和事件序列号，验证网络中断/浏览器刷新后仍能观察同一个 job。

### P4：surrogate branch

1. 在独立 worker 中接入 PhysicsNeMo-CFD/DoMINO NIM，先做 health/schema/输入边界验证。
2. 将 surrogate 用作 candidate screening 或高保真 solver 初始化，不直接替换 validation lane。
3. 记录 prediction/validation 差异，只有经过高保真复核的结果才进入“验证成功”记忆。

### P5：多轮优化和并行调度

在单 case、单 primary metric 稳定后，再引入受资源 lease 约束的并行 candidate、显式多目标/帕累托选择、parameter sweep、mesh refinement policy 和长期 checkpoint。不要在 P1 之前打开当前默认的四路并行。

## 16. 验收标准

至少满足以下条件，才称为“CFD 已嵌入实验 loop”，而不是“LLM 能启动一个脚本”：

- 不完整 case、非法单位/区域/几何和超资源计划在 solver 启动前被拒绝；
- 相同 plan/case/adapter digest 生成可比较的 run manifest；
- worker 不接受任意 shell、绝对路径、网络或 secret 参数；
- mesh、solve、postprocess、score 每一阶段都有持久化状态、短日志摘要、退出码和 artifact 引用；
- 超时、取消、SIGTERM、MPI 子进程残留和浏览器断线都有可测试行为；
- 进程中断后可从最后一个输入 hash 匹配的成功 stage 恢复，不能把半成品判为成功；
- `final_info.json` 的 primary metric、direction、单位、converged 和 provenance 可被 scorer 机器读取；
- 两个 candidate 并行时不会共享可写 case、processor 目录、MPI ranks 或临时磁盘；
- Web/LLM 只获得 curated metrics/artifacts，原始网格和大日志按需取；
- surrogate 与高保真结果的 provenance、误差和可信等级清楚区分；
- 没有许可证或运行时依赖时，任务进入 `blocked/preflight_failed`，而不是让 LLM 猜安装命令。

## 17. 最终建议

回答“这个软件现在是否已经具备被 LLM 丝滑调用的基础”：**具备批处理 worker 的基础，不具备直接 LLM 调用的基础**。

回答“应该把它集成在哪里”：**先放在 `ExperimentRunner` 与外部 solver 之间的 `CfdExecutionService`/adapter seam；再用 MCP 和 Web API 做窄 facade；不要把 CFD 细节塞进 `UnifiedModelRuntime`，也不要让模型直接执行 OpenFOAM shell**。

回答“如何结合 NVIDIA 路线”：**把 PhysicsNeMo/DoMINO 作为后续的 surrogate lane，用来快速筛选或初始化；把 Antmicro/OpenFOAM 作为高保真 validation lane；两个结果都进入同一份 run manifest、状态机和 artifact projection**。

这条路线能最大限度复用 Vegapunk 已有的 round loop、workspace、MCP tool loop、日志和 PaperOrchestra，同时把 CFD 真正缺失的 schema、资源、可观测性、恢复、安全和物理可信性补在正确的后端边界上。

## 18. 项目内证据索引

- [launch_discovery.py](../../../launch_discovery.py)：resume、round loop、incremental baseline、summary 和 Paper Handoff。
- [vegapunk/stage.py](../../../vegapunk/stage.py)：`IdeaGenerator`、`ExperimentRunner`、资源 lease、workspace 和性能计算。
- [vegapunk/experiments_utils_codex.py](../../../vegapunk/experiments_utils_codex.py)：`run_experiment`、`launcher.sh`、超时、日志和 `final_info.json` 契约。
- [vegapunk/mas/agents/tool_loop.py](../../../vegapunk/mas/agents/tool_loop.py)：模型工具循环、调用上限、错误可见性和 research event。
- [vegapunk/mas/agents/dr_agents/camel/toolkits/mcp_toolkit.py](../../../vegapunk/mas/agents/dr_agents/camel/toolkits/mcp_toolkit.py)：stdio/SSE MCP、工具 JSON Schema 和动态 function wrapper。
- [vegapunk/paper_orchestra/candidate_selection.py](../../../vegapunk/paper_orchestra/candidate_selection.py)：primary metric、finite number 和 candidate selection。
- [2026-07-28-cfd-ai-integration.md](2026-07-28-cfd-ai-integration.md)：已有 Fluent/PyFluent、COMSOL、OpenFOAM 官方自动化路线调研；本报告在其基础上补充 Antmicro/NVIDIA 与当前分支映射。

---

报告结论：**先做受控异步 CFD adapter，再做 MCP facade，最后接入 surrogate；不要从“让 LLM 直接写 shell 并跑 CFD”开始。**
