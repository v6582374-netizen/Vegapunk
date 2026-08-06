# PyFluent 许可证边界与 Vegapunk 仿真反馈机制调研

> 调研日期：**2026-08-05**。本文回答两个问题：PyFluent 是否免费、实际调用 Fluent 是否需要许可证；以及 Fluent 的真实仿真结果如何进入 Vegapunk/LLM 的实验 loop。结论基于 Ansys/PyAnsys 官方资料和当前 Vegapunk 源码。

## 1. 直接结论

### 1.1 PyFluent 包可以免费安装，但 Fluent 求解器不是免费的

需要把“Python 客户端”和“仿真软件”分开看：

| 层 | 典型内容 | 许可证/费用边界 |
| --- | --- | --- |
| Python 客户端 | `ansys-fluent-core`、PyFluent API、gRPC 客户端、settings/field/reduction 封装 | PyFluent 官方仓库声明 **MIT License**，可以按 MIT 条款安装、使用和修改；[官方 LICENSE](https://github.com/ansys/pyfluent/blob/main/LICENSE)、[pyproject.toml](https://github.com/ansys/pyfluent/blob/main/pyproject.toml) |
| Fluent 求解器 | Fluent solver、meshing、solver models、case/data 计算进程 | Ansys 商业软件；官方安装文档明确要求使用 **licensed copy of Ansys Fluent** 才能完整使用 PyFluent；[PyFluent 安装](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html) |
| 远程/容器运行 | Fluent server、Docker/Podman、PIM、Slurm/HPC worker | 仍需有效 Ansys license；容器文档要求 license file 或 license server，并通过 `ANSYSLMD_LICENSE_FILE` 提供；[容器化 Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html) |
| 已有 Fluent session | PyFluent 通过 gRPC 连接别处已启动的 Fluent | Python 客户端可以连接已有 server，但该 server 仍必须由有授权的 Fluent 实例运行；[连接已有 session](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html) |

### 1.2 官方确实存在 Ansys Student 免费版，但它不是无限制 Fluent

Ansys 当前学生版页面把 **Ansys Student** 描述为免费的 Workbench bundle，并明确列出 Ansys CFD/Ansys Fluent。页面同时写明：免费学生下载仅限教育用途，包括自学、学生教学、学生项目和学生演示；页面当前还标注内置 license 有效期至 **2027-03-31**。[Ansys Student 官方页面](https://www.ansys.com/academic/students/ansys-student)

该页面列出的限制包括 Fluid physics 最多 **1 million cells/nodes**，以及 Fluent HPC 最多 **4 个 CPU cores** 和 **40 SMs** GPU 计算能力。它适合作为学习、固定小 case 和 PyFluent smoke test 的合法入口，但不应当当作无限制的商业/生产许可证。Student 版本能否通过 PyFluent 使用，还要用具体 Student/Fluent 版本做一次 `launch_fluent`/`connect_to_fluent` 兼容性验证；PyFluent 文档只保证“有授权且属于支持矩阵的 Fluent 安装”这一前提。

因此准确答案是：**不一定要购买一份个人许可证，但运行真实 Fluent 求解必须有有效授权。**授权可以来自组织的浮动 license、学校/实验室、HPC/云环境或 Ansys 提供的其他合法授权形式；具体 feature、并发数、版本和再分发权取决于合同，不能从 PyFluent 的 MIT 许可证推断。

可以执行：

```bash
pip install ansys-fluent-core
```

但这只安装了 Python 控制层。没有 Fluent 安装、可连接的 Fluent server 和有效 license 时，通常只能导入包、阅读/开发客户端代码或使用有限的离线工具，不能完成真实的网格、迭代求解和物理结果生成。`launch_fluent()` 需要本地/容器中的 Fluent；`connect_to_fluent()` 需要已经运行的 Fluent server。[Launcher API](https://fluent.docs.pyansys.com/version/stable/api/launcher/launcher.html)

类比来说，PyFluent 更像一个免费的 SDK：SDK 可以免费安装，但它调用的商业计算服务仍需要授权；这与云服务 SDK 免费、云端资源按账户授权并不矛盾。

## 2. “Python 调用”实际发生了什么

PyFluent 不是把 Fluent 数值算法重新实现成 Python。典型调用链是：

```text
Vegapunk worker
    -> PyFluent Python client
    -> gRPC connection
    -> Fluent server/solver process
    -> mesh + boundary/model setup
    -> numerical iterations
    -> case/data/monitor/field outputs
```

PyFluent 可以从本机安装、容器、PIM、Slurm/HPC 启动 Fluent，也可以连接一个先前启动的 session；官方文档将这些模式明确区分。[启动和连接 Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)

所以“只写一段 Python”并不意味着计算发生在 Python 解释器里，而是 Python 作为控制面调用了一个真实 Fluent 求解进程。没有 solver、case/data 和 license，就没有真实的 CFD 结果。

## 3. Fluent 的结果不会自动进入 LLM 上下文

用户的第二个担心是正确的：**PyFluent 返回结果 ≠ LLM 自动看到了仿真效果。**中间必须增加一个“反馈投影层”（Observation Projector），把高频、复杂的 Fluent 状态压缩为模型可用的结构化观察和视觉 artifact。

建议将反馈拆成五层：

| 反馈层 | Fluent/PyFluent 来源 | LLM/loop 看到的内容 | 作用 |
| --- | --- | --- | --- |
| 作业状态 | session 生命周期、events | `job_id`、stage、时间、错误、是否可继续 | 控制 loop，不让模型重复提交任务 |
| 收敛过程 | residual/report monitors、iteration callbacks | 最近值、趋势、斜率、稳定性、重复去重后的曲线摘要 | 判断是否收敛、发散或停滞 |
| 物理指标 | reduction、report definitions、force/moment、平均/积分/min/max | 带单位的 primary metric、约束、守恒误差、quality gates | 机器可判定、可比较、可评分 |
| 场数据/视觉 | field data 的 surface/scalar/vector/pathlines 数组，或 Fluent 后处理 | PNG/SVG/VTK/GLTF/HTML artifact 的引用；需要时把图片作为视觉输入 | 诊断流场形态、热点、分离、回流和局部异常 |
| 可复现性 | case/data、journal、plan snapshot、checkpoint、hash | artifact manifest、输入/输出摘要和 provenance | 支持复核、恢复和候选比较 |

官方文档明确说明：

- Events 可以在 `CASE_LOADED`、`ITERATION_ENDED` 等事件发生时回调，用于 solution monitoring 和动态 graphics 更新；[Events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)
- Monitors 可以跟踪 residual 和 solution variables，注册 callback，并将每次迭代的值取回 Python；官方示例使用 `get_monitor_set_data()`，同时提醒 streamed data 可能有重复，需要去重；[Monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)
- Field Data API 可以获取 surface、scalar、vector、pathlines 数据，返回 NumPy 数组；[Field data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_data.html)
- Reduction API 可以对面积/体积范围执行 average、integral、sum、minimum、maximum 等操作，适合作为结构化 primary metric；[Reduction](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/reduction.html)

## 4. Vegapunk 中的反馈闭环

当前 `ModelToolLoop.run()` 已经具备“调用工具 → 得到工具输出 → 将输出作为下一次模型输入”的基本闭环：它执行工具后生成 `FunctionCallOutput`，并用新的 `ModelRunRequest` 继续同一 response chain；工具输入和输出不再写入独立的 research draft。

因此不需要让 LLM 直接操作 PyFluent。推荐增加一个受控 `FluentExecutionService`：

```text
LLM 生成 SimulationPlan
        |
        v
调用策略 / 许可证 / 资源 / schema preflight
        |
        v
submit_job(plan) -> job_id       （立即返回，不同步等待数小时）
        |
        +--> get_status(job_id)   <- events + monitor summary
        +--> read_metrics(job_id) <- reductions + quality gates
        +--> export_artifacts(job_id, selectors)
        |
        v
Observation Projector
        |
        +--> JSON observation -> LLM/tool loop
        +--> PNG/VTK/GLTF -> artifact store/Web/视觉模型
        +--> final_info.json -> scorer/memory/round summary
```

### 4.1 模型看到的 JSON 观察

不要把完整 mesh、全场 NumPy 数组或原始日志直接塞进上下文。默认可返回如下摘要：

```json
{
  "job_id": "fluent-job-042",
  "stage": "solving",
  "iteration": 420,
  "status": "running",
  "converged": false,
  "monitors": {
    "residual-continuity": {"last": 1.2e-5, "trend": "decreasing"},
    "outlet_pressure_drop_pa": {"last": 1834.2, "delta_last_20": 0.8}
  },
  "quality_gates": {
    "mesh_valid": true,
    "residual_ok": false,
    "mass_balance_ok": true,
    "finite_primary_metric": true
  },
  "primary_metric": {
    "name": "outlet_pressure_drop_pa",
    "value": 1834.2,
    "unit": "Pa",
    "direction": "minimize"
  },
  "artifacts": [
    {"id": "artifact:contour:step420", "kind": "contour_png", "mime": "image/png"},
    {"id": "artifact:monitor:residual", "kind": "monitor_json", "mime": "application/json"}
  ],
  "next_allowed_actions": ["poll", "cancel", "request_diagnostic"]
}
```

其中 `converged`、quality gates 和 primary metric 由程序计算；LLM 可以解释趋势、提出下一候选，但不能用自然语言把 `residual_ok=false` 改成成功。

### 4.2 模型看到的真实“画面”

真实视觉反馈至少需要三步：

1. 从 Fluent Field Data 取得受限的 surface/scalar/vector/pathlines 数据；
2. 由 worker 使用 Fluent 后处理能力或 Python 可视化库生成 contour、streamline、vector plot、时间序列图等 artifact；
3. 将 artifact 作为图片/文件引用返回。若使用支持视觉输入的模型，可在工具结果中附加 PNG/JPEG；若当前 runtime 只能接收文本，则返回图像的 artifact ID、元数据和程序生成的摘要，模型本身不会“看到像素”。

所以要区分：

- **数值反馈**是候选选择和质量门的依据；
- **视觉反馈**是诊断和解释的依据；
- **原始 field/mesh**是可复现 artifact，默认不进入模型上下文。

### 4.3 反馈频率

不要每个 Fluent iteration 都触发一次 LLM 调用。建议：

- events/monitor collector 可以高频采集；
- 每隔固定 iteration/时间窗口生成一次摘要；
- `converged`、`diverged`、`stalled`、`timeout` 等重要事件立即生成摘要；
- LLM 只在阶段边界或需要决策时被唤醒；
- 视觉图按需生成，例如初始、周期 checkpoint、异常和最终状态。

这样既保留真实过程，又不会让 Fluent 的高频 callback 把模型 loop、token 成本和 research draft 撑爆。

## 5. 反馈如何驱动下一轮实验

建议采用“程序质量门 + LLM 解释/提出方案”的分工：

```text
Fluent observation
    -> deterministic quality gate
       -> failed: retry/repair/blocked
       -> passed: scorer compares primary metric
                    -> LLM receives summary + selected visual artifact
                       -> proposes next SimulationPlan
```

典型反馈规则：

| 观察结果 | 系统动作 | LLM 能做什么 |
| --- | --- | --- |
| 许可证/版本/case 缺失 | `blocked`，不启动或不重试 | 解释缺失项，不猜安装命令 |
| 网格质量失败 | `quality_failed` | 提议受白名单约束的 mesh profile 修订 |
| residual 发散 | 停止/有限次 retry | 根据摘要提出初始化、边界或 solver profile 修订 |
| residual 收敛但 primary metric 不达标 | `completed` 但候选不通过 | 提出下一组设计变量 |
| metric 接近候选排序阈值 | 进入高保真比较/增加诊断 | 请求指定区域或变量的图像/field artifact |
| 结果已稳定且不影响排序 | 复用缓存，不重复求解 | 解释当前证据并结束本候选 |

LLM 不应在同一个有状态 session 里随意改边界条件并继续计算。更安全的方式是：停止/完成当前 job，生成新的带 digest 的 `SimulationPlan`，经 SIC 再决定是否启动新的 job。这样每个反馈都有明确的输入、输出和 provenance。

## 6. 最小可行 vertical slice

如果当前还没有 Ansys license，不能声称已经完成“真实 Fluent 反馈”集成。可以先做 fake/replay adapter，但结果必须标记为 `simulator=replay` 或 `prediction`，不能伪装成 Fluent validation。

第一版建议：

1. 一个有授权的 Fluent worker；
2. 一个固定 case template；
3. 一个 primary metric，例如压降或出口温度；
4. 一个 residual/质量守恒 monitor；
5. 一个 `submit_job → get_status → read_metrics` 异步链路；
6. 一个最终 contour PNG 和一个 monitor JSON/PNG；
7. 一个 `final_info.json`/artifact manifest，记录 solver、版本、case hash、plan digest、license profile 摘要、quality gates 和指标单位；
8. 用 replay/fake session 先测试模型 loop、恢复、失败和 artifact 投影，再在真实 licensed worker 上做 smoke case。

这条路线能回答“模型是否真的根据仿真反馈调整下一步”，而不仅仅是“Python 是否成功启动 Fluent”。

## 7. 与现有调用决策报告的关系

本报告补充 [外部仿真调用决策机制报告](2026-08-04-ansys-fluent-invocation-policy.md)：

- 许可证检查属于 `inspect_capabilities`/preflight，不属于 LLM 自己的判断；
- Fluent 真实反馈进入 `get_status`、`read_metrics`、`export_artifacts`，再回到 `ModelToolLoop`；
- 没有 license 时可做 API 开发和 replay 测试，但不能生成真实 validation；
- 高保真数值结果必须通过 quality gate，视觉图不能替代收敛和守恒检查。

## 8. 资料索引

- [PyFluent GitHub（MIT）](https://github.com/ansys/pyfluent)
- [PyFluent LICENSE](https://github.com/ansys/pyfluent/blob/main/LICENSE)
- [PyFluent pyproject.toml](https://github.com/ansys/pyfluent/blob/main/pyproject.toml)
- [Ansys Student 免费版、教育用途和 Fluent 限制](https://www.ansys.com/academic/students/ansys-student)
- [PyFluent 安装与 Fluent license 要求](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html)
- [启动/连接 Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/session/launching_ansys_fluent.html)
- [Launcher API](https://fluent.docs.pyansys.com/version/stable/api/launcher/launcher.html)
- [Events](https://fluent.docs.pyansys.com/version/stable/user_guide/events.html)
- [Monitors](https://fluent.docs.pyansys.com/version/stable/user_guide/monitors.html)
- [Field data](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/field_data.html)
- [Reduction](https://fluent.docs.pyansys.com/version/stable/user_guide/fields/reduction.html)
- [Containerization and license](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html)
- [Vegapunk `ModelToolLoop.run`](../../../vegapunk/mas/agents/tool_loop.py#L52-L131)

## 9. 官方免费版、学生版与试用版：不能混为“免费 Fluent”

截至 2026-08-05，官方页面没有把 Fluent 描述成一个不受限制、永久免费的通用版本。Ansys Fluent 产品页的 FAQ 将渠道分为三类：现有客户从 Ansys Customer Portal 下载；非现有客户可申请 30 天试用；学生可下载免费学生软件。[Ansys Fluent 产品页](https://www.ansys.com/products/fluids/ansys-fluent)

### 9.1 Ansys Student：有 Fluent，但仅限教育用途且有硬限制

Ansys Student 是官方免费 Workbench bundle，明确包含 Ansys CFD（Ansys CFX 和 Ansys Fluent）。但其 Terms of Use 明确写着：免费学生下载“仅用于教育用途”，只能用于自学、学生教学、学生项目和学生演示。因此它不是可用于 Vegapunk 商业验证或生产服务的通用 Fluent 授权。[Ansys Student 下载与条款](https://www.ansys.com/academic/students/ansys-student)

页面还列出版本和能力边界，说明学生版不能等同于商业 entitlement：

- Ansys Student 2026 R1 页面显示内置 license 有效至 **2027-03-31**；License Duration 说明为可续期、从发行日起十二个月的 lease（具体到下载版本和页面当前条款）。
- 流体物理问题规模上限为 **1 million cells/nodes**。
- Fluent 的 HPC 支持最多 **4 个 CPU cores**，GPU 计算最多 **40 SMs**。
- 支持平台列为 Windows 10/11 64-bit；这与面向服务器/HPC 的商业安装环境不同。

因此，若用 Student 做 PyFluent/Vegapunk 的学习或 API smoke test，应在 manifest 中标明 `license_profile=student`、`use_scope=educational`、版本和到期日，并把结果标记为 educational/replay evidence；不能把它当作商业或生产 Fluent 结果。PyFluent 文档仍要求安装“licensed copy of Ansys Fluent”，而 Student 的内置 license 是否覆盖某个版本、模式或模块，应以该版本实际启动结果和 Ansys 条款为准，不能从 PyFluent 的 MIT 条款推断。

### 9.2 30 天试用：有期限、需申请，不是永久免费版

Ansys 的专门试用页目前标题为 **Ansys Fluent GPU Solver**，页面写明“Start Your Free 30-Day Trial”，并注明“**No automatic charge. Trial ends unless you contact our sales team to activate a paid license.**”申请表要求公司或学校、是否学生、地区等信息。[Ansys Fluent GPU Solver 30-Day Trial](https://www.ansys.com/products/fluids/ansys-fluent/ansys-fluent-trial)

这意味着试用是 Ansys 授予的、期限和产品范围受控的合法 entitlement；它不是可长期用于实验 loop 的免费运行时，也不自动等于完整 CPU/HPC/商业模块授权。Vegapunk 应记录 `trial_start`、`trial_expiry`、产品 profile（当前页面为 GPU Solver）及允许的 feature，并在到期或 feature 不匹配时 fail closed。

### 9.3 Student 下载通常不需要等待人工 license 审批

Ansys Student 页面直接提供 `DOWNLOAD ANSYS STUDENT 2026 R1` 下载入口；安装说明是下载压缩包、解压、以管理员身份运行 `setup.exe`、接受 clickwrap 并完成安装，随后从 Workbench 启动。页面没有把 Student 描述为“提交 license 申请后等待人工签发”的流程。因此在符合学生/教育用途条件的情况下，通常可以直接下载和安装；网站登录、地区、条款确认或下载服务的临时验证仍可能存在，具体以下载页面为准。[Ansys Student 下载与安装步骤](https://www.ansys.com/academic/students/ansys-student)

这与 30 天 trial 不同：trial 页面明确要求申请表和受控的试用 entitlement。若只是为了学习和验证 PyFluent，优先使用官方 Student 下载；若是商业/生产或非学生用途，应走 Customer Portal、组织 license 或官方 trial/销售流程，不应使用破解版本。

## 10. PyFluent 安装、`launch`、`connect` 与 license 检查位置

官方 PyFluent 文档和 MIT 源码显示，许可证检查不是 `pip` 或 gRPC 客户端单独完成的一次“在线验证”；PyFluent 主要负责定位 Fluent、启动/连接进程和建立 gRPC session。授权的最终判断由 Fluent 可执行程序及 Ansys licensing 运行时在启动或请求相应 solver/feature 时完成。

| 阶段 | PyFluent 做什么 | 许可证判断应归属哪里 | Vegapunk 应如何处理 |
| --- | --- | --- | --- |
| `pip install ansys-fluent-core` | 安装 MIT Python client/API | 不检查 Fluent license；包本身不包含 solver | 可安装和单元测试，但状态只能是 `client_ready`，不能声称可求解 |
| 本地安装发现 | 读取 `AWP_ROOT252` 等环境变量定位 Ansys 安装 | 路径存在性/版本发现不是授权证明 | 记录 `fluent_path`、版本和 client/solver 分离的能力摘要 |
| `launch_fluent()` standalone | 生成启动命令，用 `subprocess.Popen` 启动 Fluent，等待 server-info 文件，再建立 session | Fluent 进程与 Ansys License Manager 在启动阶段检查 entitlement；缺 license 时可能退出、只输出 transcript 错误或无法写出 server-info，随后由 PyFluent 表现为等待超时/`LaunchFluentError` | 启动前做 preflight；启动后读取 transcript、进程状态和 server-info；没有明确授权证据时返回 `license_unavailable`/`blocked` |
| 容器/PIM/HPC launch | 启动远端或容器中的 Fluent，并连接其 gRPC server | 容器中的 Fluent 仍须有效 license；官方示例要求运行时注入 `ANSYSLMD_LICENSE_FILE`（license file 或 server） | 不把镜像存在或 gRPC 可达当成授权；保存 license profile/过期时间等非敏感摘要 |
| `connect_to_fluent()` | 根据 IP/port/address 或 server-info/password 连接已经运行的 Fluent server | 连接器不启动 solver，也没有文档所述的独立 license checkout；授权应已在该 Fluent server 启动时完成 | 仅允许连接到已登记、可审计且由授权 worker 启动的 server；传输层 TLS/密码是安全控制，不等于 license |

PyFluent launcher 的官方 MIT 源码可核对上述行为：`StandaloneLauncher.__call__()` 调用 `subprocess.Popen`，随后 `_await_fluent_launch()` 只等待 server-info 文件更新时间；`connect_to_fluent()` 构造 `FluentConnection` 并读取 server-info。该源码没有客户端许可证绕过或破解逻辑。[launcher.py](https://raw.githubusercontent.com/ansys/pyfluent/main/src/ansys/fluent/core/launcher/launcher.py)、[standalone_launcher.py](https://raw.githubusercontent.com/ansys/pyfluent/main/src/ansys/fluent/core/launcher/standalone_launcher.py)、[launcher_utils.py](https://raw.githubusercontent.com/ansys/pyfluent/main/src/ansys/fluent/core/launcher/launcher_utils.py)

容器路径更明确：PyFluent/Fluent 容器文档在“Run Docker container”前警告需要有效 Ansys license，并要求运行容器时指定 `ANSYSLMD_LICENSE_FILE=<license file or server>`。因此 license 检查发生在容器内的 Fluent/Ansys licensing 运行时，而不是 `pip install` 或 `connect_to_fluent()` 这层。[Containerization of Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html)

### 10.1 建议的 preflight 与证据链

`inspect_capabilities` 可以在不消耗求解 license 的情况下检查：PyFluent 包版本、Fluent 可执行路径、目标版本、运行模式、license profile 是否已登记、到期时间是否满足任务窗口、所需 feature（solver/meshing/GPU/HPC）是否声明。但这些是配置级检查，不应伪装成 Ansys 已授予 lease 的证明。

真正提交任务前，应在授权 worker 上做一次受控启动或 smoke case，并把以下证据写入 manifest（不要写入原始 license 文件、服务器密钥或密码）：

```json
{
  "client_license": "MIT",
  "solver_entitlement": {
    "profile": "commercial|student|trial|organization",
    "product": "fluent|fluent_gpu_solver",
    "valid_until": "2027-03-31",
    "scope": "educational|trial|commercial|internal"
  },
  "evidence": {
    "launch_confirmed": true,
    "server_info_received": true,
    "transcript_license_errors": 0,
    "feature_smoke_test": "passed"
  }
}
```

`launch_confirmed=true` 仅表示 Fluent server 启动并可连接；是否有权使用特定模块、并行规模或 GPU，仍需由 entitlement 和 smoke test 共同确认。license 过期、不可达、feature 不匹配或 transcript 出现授权错误时，实验状态应为 `blocked`，而不是让 LLM 猜测或重试无限次。

## 11. 合法使用与绕过授权的边界

- 合法路径：MIT 条款下使用/分发 PyFluent client；通过 Ansys Customer Portal、组织/学校授权、合规 HPC/云环境、符合条款的 Ansys Student 或官方试用获得 Fluent entitlement；按对应教育、试用或商业范围运行。
- 不应执行：使用破解或修改后的 Fluent 二进制、伪造/篡改 license 文件、连接未经授权的 license server、冒用他人 entitlement、修改主机标识或其他绕过授权的做法。本文不提供任何此类操作方法。
- Vegapunk 的安全策略应 fail closed：授权证据缺失时不启动真实求解或不把结果标记为 Fluent validation；可切换到 `replay`/`fake` adapter 做 loop 测试，但必须在结果中明确 `simulator=replay`。
- 日志只记录 `client_license`、`solver_entitlement` 的 profile/到期时间/非敏感 opaque ID 和校验结果，不记录原始 license 文件、密码或完整 license server secret。

## 12. 本节新增官方来源（访问日期：2026-08-05）

| 来源 | 核实内容 |
| --- | --- |
| [Ansys Fluent 产品页](https://www.ansys.com/products/fluids/ansys-fluent) | FAQ：客户从 Customer Portal 下载；非客户可申请免费 30 天 Fluent trial；学生可下载免费学生软件。 |
| [Ansys Licensing Resources](https://www.ansys.com/it-solutions/licensing) | 官方许可资源页列出 concurrent、named-user 和 elastic 等 entitlement/licensing 方案；运行 Fluent 的商业资格来自 Ansys entitlement，而非 PyFluent MIT client。 |
| [Ansys Student 下载与条款](https://www.ansys.com/academic/students/ansys-student) | 官方免费 bundle 包含 Ansys CFD/Fluent；仅教育用途；2026 R1 内置 license 到 2027-03-31；流体规模、HPC/GPU 和平台限制。 |
| [Ansys Fluent GPU Solver 30-Day Trial](https://www.ansys.com/products/fluids/ansys-fluent/ansys-fluent-trial) | 申请式 30 天 GPU Solver 试用；无自动扣费，试用结束除非联系销售激活付费 license。 |
| [PyFluent Installation](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html) | `pip install ansys-fluent-core` 与 Fluent 安装分离；完整使用需 licensed copy；通过 `AWP_ROOT252` 等变量定位安装。 |
| [PyFluent Launcher API](https://fluent.docs.pyansys.com/version/stable/api/launcher/launcher.html) | `launch_fluent()` 启动本地/容器/调度器模式，`connect_to_fluent()` 连接已有 server；参数和错误边界。 |
| [PyFluent launcher source](https://raw.githubusercontent.com/ansys/pyfluent/main/src/ansys/fluent/core/launcher/standalone_launcher.py) | standalone launch 使用 `subprocess.Popen` 并等待 server-info；未实现客户端独立 license checkout。 |
| [Containerization of Fluent](https://fluent.docs.pyansys.com/version/stable/user_guide/make_container_image.html) | 有效 Ansys license 前置条件；容器运行时通过 `ANSYSLMD_LICENSE_FILE` 指向 license file/server。 |

## 13. Student 与商业 Fluent 的 Linux 支持

### 13.1 Student：当前没有官方 Linux 安装包

截至 2026-08-05，Ansys Student 2026 R1 官方页面的“Supported Platforms and Operating Systems”只列 **Microsoft Windows 10 & 11, 64-bit**。下载入口提供的是 Windows 安装流程（解压后运行 `setup.exe`）；页面没有列出 Linux Student 安装包或 Linux 支持。因此，当前不能把 Ansys Student 视为官方支持的 Linux Fluent 运行时。Wine、未经支持的虚拟机或自行搬运安装目录，即使偶尔能启动，也不应作为 Vegapunk 的受支持部署方案。

这不影响 Linux 上安装 PyFluent Python client：PyFluent 文档明确支持 Windows、macOS 和 Linux，但同一文档要求要完整使用 PyFluent，仍需一份已授权的 Fluent 安装。也就是说，`pip install ansys-fluent-core` 在 Linux 上可行，**Student Fluent solver 在 Linux 上没有官方支持**。

### 13.2 商业 Fluent：有官方 Linux 版本

Ansys 的 [2026 R1 Platform Support by Application](https://www.ansys.com/content/dam/it-solutions/platform-support/2026-r1/ansys-2026-r1-platform-support-by-application.pdf) 第 2 页 Fluids 表中，`Fluent` 在以下 64 位平台均标记为 `P`（supported）：

- Red Hat Enterprise Linux 8（8.8、8.10）和 9（9.4、9.6）；
- SUSE Linux Enterprise Server & Desktop 15（SP5、SP6、SP7）；
- Ubuntu LTS 22.04 和 24.04（Desktop & Server）；
- Rocky Linux 8.10、9.4、9.6。

该 PDF 第 5 页的 Integrated Solutions 表还把 Ansys Fluent 列在 AlmaLinux 8.5+ 和 9.x 的支持项中。实际部署仍应以目标 Fluent 发行版（例如 2025 R2/2026 R1）对应的平台矩阵、所需模块和 HPC/GPU 组合为准，不能将“支持 Linux”扩大解释成“任意 Linux 发行版都支持”。

### 13.3 对 Vegapunk 的落地含义

如果 Vegapunk 的 worker 需要原生 Linux 本地运行 Fluent，建议使用平台矩阵中的 Ubuntu 22.04/24.04、RHEL 8/9 或 Rocky 8/9，并配置组织/商业 Ansys entitlement（或明确允许该用途的其他合法授权）。PyFluent 在该 Linux worker 上负责启动/连接 Fluent，许可证仍由 Fluent/Ansys licensing runtime 检查。

如果只有 Student，可将 Fluent worker 放在受支持的 Windows 10/11 主机上；Linux 侧理论上可以运行 PyFluent client，再通过 gRPC 连接远端 Fluent server，但 Student 的远程连接、并发和教育用途条款必须以该版本官方支持和实际 smoke test 为准，不能据此宣称“Linux Student 已被支持”。

### 13.4 本节新增来源

| 来源 | 核实内容 |
| --- | --- |
| [Ansys Student](https://www.ansys.com/academic/students/ansys-student) | Supported Platforms 只列 Windows 10/11 64-bit；2026 R1 下载入口和 Windows 安装步骤。 |
| [Ansys 2026 R1 Platform Support by Application](https://www.ansys.com/content/dam/it-solutions/platform-support/2026-r1/ansys-2026-r1-platform-support-by-application.pdf) | 第 2 页 Fluids 表列出 Fluent 的 Windows/Linux 支持矩阵；第 5 页列出 AlmaLinux 集成平台项。 |
| [PyFluent Installation](https://fluent.docs.pyansys.com/version/stable/getting_started/installation.html) | PyFluent client 支持 Windows、macOS、Linux；完整使用需要 licensed Fluent，并说明 Linux 上设置 `AWP_ROOT252`。 |
