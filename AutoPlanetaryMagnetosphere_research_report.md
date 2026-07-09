# AutoPlanetaryMagnetosphere Discovery Research Report

生成时间：2026-07-09

## 1. 执行状态与产物范围

本次 discovery 面向“类地行星感应磁层响应预测”任务，目标是在自包含的合成 benchmark 上提出、实现并评估优于 baseline 的感应磁层 surrogate。当前长跑进程已停止；`kill -TERM` 触发了正常收尾，最后一轮 `session_1783577691` 已写入 launch 目录并标记为 `completed`。

主要产物位于：

- `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/`
- `.codebase-memory/graph.db.zst`

已落盘 discovery 产物：

| 类型 | 数量 | 说明 |
| --- | ---: | --- |
| 完成 session | 4 | `session_1783518612`, `session_1783523223`, `session_1783531396`, `session_1783577691` |
| 候选 idea | 298 | 每轮约 73-75 条 |
| Top idea | 20 | 每轮 top 5 |
| 实验目录 | 16 | 每个目录对应一个被实现或尝试实现的方法 |
| `final_info.json` | 47 | 16 个实验目录中有一个 run 缺少 final result |
| 顶层 `experiment_report.txt` | 16 | 每个实验目录一个汇总报告 |

当前没有 `discovery_summary.json`，因此恢复时应依赖已有 session 目录和 trajectory 文件扫描。

## 2. Benchmark 与 Baseline

系统使用的是一个自包含的合成 benchmark，而不是观测数据、MHD、hybrid 或 PIC 仿真产物。其参考实现位于 `tasks/AutoPlanetaryMagnetosphere/code/experiment.py`。

Baseline 的核心设置：

| 项目 | 内容 |
| --- | --- |
| 数据 | 确定性生成 Mars-like 与 Venus-like 合成样本 |
| 样本数 | 960 |
| 输入 | 16 个太阳风、IMF、太阳活动、pickup-ion 相关原始驱动特征 |
| 输出 | 4 个目标：bow shock standoff、magnetic pileup boundary、ion escape log10 rate、acceleration index |
| 模型 | 标准化输入与目标后的 closed-form ridge regression |
| ridge | 0.35 |
| test split | 0.2 |
| 随机种子 | 20260708 |

原始 baseline 的代表性指标为：

| 指标 | Baseline |
| --- | ---: |
| combined_score | 0.0873459362 |
| boundary_location_mae | 0.0336993621 |
| escape_log_mae | 0.0531940549 |
| acceleration_rmse | 0.0676338791 |
| mean_r2 | 0.9396260830 |

## 3. 系统主要研究了什么

从 4 个 session 的 top ideas 看，系统反复围绕同一条主线收敛：在保持 CPU 可运行、可解释和自包含的条件下，把物理结构显式编码进 surrogate，而不是单纯增加模型复杂度。

主要研究方向包括：

1. **压力平衡与边界压缩。** 多个 top idea 把太阳风动压、磁压、EUV/电离层支撑与 Mars/Venus 差异纳入 bow shock 和 MPB 边界预测。
2. **非线性驱动交互。** 系统反复加入 `log(dynamic_pressure)`、IMF clock angle、southward IMF fraction、convective electric field、EUV、pickup source、ion gyroradius 等非线性和交互特征。
3. **Mars/Venus regime conditioning。** 多个方案把行星类型作为显式条件，试图分离共同响应规律与星体特有 offset。
4. **IMF draping 与 clock-angle 描述符。** 系统认为简单 raw IMF 特征不足以表达 draping、shear 和方位效应。
5. **pickup-ion 与离子动理学尺度。** 候选方法多次引入 pickup source proxy、ion gyroradius、kinetic-scale coupling，以解释加速和逃逸。
6. **多目标一致性。** O-PRISM、PB-Twin、CoP-KR、OMR-MoE 等方案都提出了边界位置、加速、逃逸之间的共享 latent 或一致性约束。
7. **不确定性与 regime mixture。** 最后一轮 top idea `OMR-MoE` 设计了 heteroscedastic mixture-of-experts 和 monotone decoder，但当前实验代码没有真正实现这个深度/概率模型。

## 4. Top Ideas 演化概览

### Session 1

Top ideas 主要是探索压力、湍流、离子动理学与不确定性：

| 方法 | 分数 | 主题 |
| --- | ---: | --- |
| Pressure-Turbulence Coupled Magnetosphere Framework | 8.70 | 压力-湍流耦合 |
| IKC-DPIM | 8.64 | 离子动理学耦合与动态压力不平衡 |
| Constrained Nonlinear Induced Magnetosphere Model | 8.60 | 物理约束非线性 surrogate |
| Stochastic Magnetosphere Response Model | 8.52 | 随机响应与不确定性 |
| PB Uncertainty Coupled Model | 8.32 | 压力平衡与不确定性 |

### Session 2

系统开始把前一轮想法压缩成更可实现的非线性特征工程：

| 方法 | 分数 | 主题 |
| --- | ---: | --- |
| DynamicCoupledMagnetosphereModel | 8.46 | 动态耦合与瞬态 reconnection |
| Turbulence-Aware Coupling Model | 8.20 | 湍流感知的非线性耦合 |
| Pressure-Balance-Conditioned Induced Magnetosphere Model | 8.18 | 压力平衡条件化 |
| Physics-Informed Magnetosphere Surrogate | 8.00 | draping 与 ion kinetics |
| Constrained Nonlinear Magnetosphere Model | 8.00 | 物理正则化 |

### Session 3

系统进一步收敛到“低维物理结构 + ridge 可实现”的方法族：

| 方法 | 分数 | 主题 |
| --- | ---: | --- |
| PB-Twin | 8.77 | Mars/Venus 双行星迁移 surrogate |
| MPC-Kin | 8.72 | 单调压力约束与 kinetic surrogate |
| O-PRISM | 8.60 | 正交物理残差 surrogate |
| CoP-KR | 8.52 | 约束压力-动理学 ridge |
| PB-KIC | 8.50 | 压力平衡 kinetic-induced coupling |

### Session 4

最后一轮提出了更复杂的 mixture-of-experts 和 calibration 思路，但实际实验目录只跑通了与 PB-KIC 类似的特征工程 ridge：

| 方法 | 分数 | 主题 |
| --- | ---: | --- |
| OMR-MoE | 8.51 | 正交单调 regime mixture 与不确定性 |
| PIPER-MC | 8.40 | 行星条件化物理约束 calibration |
| CMR-PB | 8.39 | 单调 regime 压力平衡 surrogate |
| PB-CCS | 8.33 | 压力平衡 calibrated coupling |
| IM-PBMoE | 8.29 | 物理平衡 regime-switching surrogate |

## 5. 实际跑通的实验路线

虽然 idea 层面提出了 mixture-of-experts、heteroscedastic uncertainty、monotone decoder、orthogonal latent decomposition 等更复杂模型，当前实际成功执行的代码主要属于以下两类：

1. **Baseline 修复与复跑。** 多个实验最初失败于缺少 `launcher.sh`，后续通过新增 root-level 或 code-level launcher 解决。修复后跑出的仍是 16 原始特征 ridge baseline。
2. **物理启发非线性特征扩展 + ridge。** 成功提升指标的实验基本都在 baseline 的 ridge pipeline 上增加 13 个左右 deterministic engineered features，使输入从 16 个扩展到约 29 个。

常见新增特征包括：

- `log1p(dynamic_pressure)` 或 pressure log transform
- EUV normalization
- southward IMF fraction
- draping shear fraction
- cycle compression
- clock-angle / planet coupling
- `log1p(convective_e)`
- `sqrt(ion_gyroradius)`
- pickup source proxy
- pressure、IMF、EUV、Venus、clock-angle 的交互项

这些特征与原任务目标一致：保持方法可解释，并显式编码太阳风压力、IMF 几何、太阳活动、pickup ions、Mars/Venus regime 差异。

## 6. 结果汇总

最佳记录来自：

`session_1783523223/20260708_234904_Pressure-Balance-Conditioned Induced Magnetosphere Model/run_2`

| 指标 | Baseline | 最佳结果 | 相对变化 |
| --- | ---: | ---: | ---: |
| combined_score | 0.0873459362 | 0.0209071400 | -76.06% |
| boundary_location_mae | 0.0336993621 | 0.0096904344 | -71.24% |
| escape_log_mae | 0.0531940549 | 0.0148083835 | -72.16% |
| acceleration_rmse | 0.0676338791 | 0.0119487875 | -82.33% |
| mean_r2 | 0.9396260830 | 0.9962914266 | +0.0567 |

代表性成功实验如下：

| 实验 | run | combined_score | mean_r2 | 说明 |
| --- | --- | ---: | ---: | --- |
| Pressure-Balance-Conditioned Induced Magnetosphere Model | run_2 | 0.0209071400 | 0.9962914266 | 最佳结果，29 特征并启用 physics decoder 路径 |
| Constrained Nonlinear Magnetosphere Model | run_0/run_1/run_2 | 0.0209677762 | 0.9962708931 | 稳定复现 29 特征 ridge |
| DynamicCoupledMagnetosphereModel | run_0/run_1/run_2 | 0.0209677762 | 0.9962708931 | 实际同类非线性扩展 ridge |
| PB Uncertainty Coupled Model | run_2 | 0.0216574988 | 0.9959025040 | 物理扩展特征，逃逸误差略高 |
| Pressure-Turbulence Coupled Framework | run_2 | 0.0224098113 | 0.9953561762 | 压力/湍流相关特征 |
| PB-KIC / OMR-MoE 实验目录 | run_2 | 0.0225239409 | 0.9953699840 | 实际实现为 PB-KIC 类特征扩展 |
| O-PRISM | run_2 | 0.0249856427 | 0.9940970970 | 有提升但弱于最佳特征集 |

可以归纳出一个稳定结论：只要加入物理启发的非线性特征，ridge surrogate 就能从 baseline 的 `combined_score ~= 0.0873` 稳定降到 `0.021-0.025` 区间；最佳压力平衡条件化路径进一步降到 `0.02091`。

## 7. 需要谨慎解读的地方

1. **这不是真实物理验证。** 所有指标都来自合成 benchmark，说明模型更好地恢复了 benchmark 内置结构，不能直接声称验证了 Mars/Venus 观测规律或高保真仿真规律。
2. **很多高级 idea 没有真正实现。** OMR-MoE 的 mixture-of-experts、heteroscedastic uncertainty、orthogonal monotone decoder 仍停留在方法设计文本层面；最后的 `OMR-MoE` 实验报告实际写的是 `PB-KIC`，说明执行层复用了较简单的特征扩展 ridge。
3. **实验目录中存在 harness 噪声。** 多个 run 的主要修改是补 `launcher.sh`，并不代表方法本身有科学改进。
4. **部分报告重复或命名不一致。** `session_1783523223` 下有 run 内重复 `experiment_report.txt`；`OMR-MoE` 目录的报告标题为 PB-KIC。
5. **缺少更细粒度评估。** 当前主要看全局 test split 指标，尚未系统评估 high dynamic pressure、Mars/Venus 分组、IMF clock-angle regime、pickup-dominated regime 或 out-of-distribution extrapolation。

## 8. 当前最有价值的研究结论

本轮 discovery 的实际发现不是“复杂模型一定更好”，而是更具体的一点：

> 在这个 AutoPlanetaryMagnetosphere 合成 benchmark 中，性能瓶颈主要来自 raw driver ridge 无法表达非线性物理耦合；加入少量可解释的压力、IMF 几何、EUV、pickup-ion、离子尺度和行星条件交互特征后，简单 ridge 模型就能获得大幅提升。

这个结论有工程和科学两层含义。

工程上，下一步不必直接跳到 MoE 或神经网络。应该先固定最佳 29 特征 ridge 作为 strong baseline，并清理 launcher/report 逻辑，确保每个方法目录真正对应其声称方法。

科学上，最有效的特征族集中在三类：

1. 压力压缩项：dynamic pressure、magnetic pressure、pressure log transform、cycle compression。
2. IMF 几何项：southward IMF fraction、clock-angle coupling、draping shear。
3. 离子源与 kinetic 项：EUV、pickup source、convective electric field、ion gyroradius。

这些项共同解释了边界运动、离子逃逸和加速指标的同步改善。

## 9. 建议后续工作

1. **固化最佳特征工程 baseline。** 将 `Pressure-Balance-Conditioned Induced Magnetosphere Model/run_2` 的实现提取为清晰、单一的 reference method。
2. **补充分组评估。** 至少报告 Mars/Venus、high dynamic pressure、strong southward IMF、pickup-dominated、solar-cycle high/low 几组指标。
3. **做 ablation。** 分别移除 pressure、IMF geometry、EUV/pickup、kinetic、planet coupling 特征，确认每组特征的独立贡献。
4. **实现真正的 OMR-MoE 前先建立强 baseline。** 如果要继续 MoE，应先对当前 ridge baseline 做同样分组评估，否则 MoE 的收益难以解释。
5. **修复 discovery harness。** 统一 `launcher.sh` 生成位置，避免下一轮把大量 agent 步数浪费在 return code 127。
6. **生成正式 summary。** 当前没有 `discovery_summary.json`，建议后续补一个聚合脚本，把 session、top idea、best run、指标和报告索引写成稳定 summary。

## 10. 关键文件索引

| 文件/目录 | 用途 |
| --- | --- |
| `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/session_1783518612/traj.json` | 第一轮 idea 轨迹 |
| `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/session_1783523223/traj.json` | 第二轮 idea 轨迹 |
| `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/session_1783531396/traj.json` | 第三轮 idea 轨迹 |
| `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/session_1783577691/traj.json` | 第四轮 idea 轨迹 |
| `results/AutoPlanetaryMagnetosphere/20260708_215011_launch/session_1783523223/20260708_234904_Pressure-Balance-Conditioned Induced Magnetosphere Model/run_2/final_info.json` | 当前最佳指标 |
| `tasks/AutoPlanetaryMagnetosphere/code/code_summary.json` | baseline benchmark 摘要 |
| `.codebase-memory/graph.db.zst` | codebase-memory 图谱压缩产物 |

