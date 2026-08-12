# UniFoLM-VLA 应用于实验室 Unitree G1：可行性与落地路径

调研日期：2026-08-11

## 结论

**可以应用，但它不是“把权重装到 G1 上即可运行”的项目。** UniFoLM-VLA 的官方真机路径是一个明确的双端系统：GPU 服务器承载模型推理；G1 侧客户端采集相机和关节状态、执行返回的动作。官方提供的 G1 适配目标是 **`g1_dex1`：双臂 G1 + Dex1-1 两指夹爪 + G1 图像服务**。因此，实验室机器人若不是这一末端执行器和传感器组合，首要工作是建立与该观测/动作契约一致的适配层和本体数据，而不是直接运行预训练权重。

建议把首个目标限定为“桌面、静立、单一已训练相近任务的受控复现”，在离线回放和空载联调均通过后，才进入真机闭环；不要以“通用人形操作”作为第一次部署验收标准。

## 官方支持边界

| 层面 | 官方事实 | 对实验室决策的含义 |
| --- | --- | --- |
| 机器人本体 | UniFoLM-VLA 公开的十二个真机数据集全部标为 Unitree G1；部署仓库注册的 G1 配置为 `g1_dex1`。 | G1 是项目的已验证本体，不是从零移植的对象。 |
| 末端与动作 | `g1_dex1` 配置包含 G1 双臂和两侧 Dex1 夹爪；训练常量中 joint 模式定义 25 步 × 16 维动作/状态，而 `stack_block` 模式为 25 步 × 23 维。 | checkpoint、`unnorm_key`、动作表示与客户端必须严格匹配；Dex1-1 以外的手（例如灵巧手）不能宣称与官方权重即插即用。 |
| 视觉 | G1 配置使用机载 `image_server` 的图像客户端；默认头部相机和双腕相机均以 30 FPS 配置，但示例策略实际选用 `cam_right_high` 作为 `observation.images.top`。 | 真实运行至少需可稳定获得与训练视角/颜色格式一致的相机流；更换相机位置会形成显著域差异。 |
| 推理拓扑 | 官方要求服务器端推理，客户端通过 SSH 本地端口转发访问服务器；并要求设备在同一 LAN。 | 准备一台与 G1 网络连通的 GPU 服务器，且将网络延迟、相机传输和控制节拍作为系统验收项。 |

依据：[UniFoLM-VLA README（数据集、真机部署）](https://github.com/unitreerobotics/unifolm-vla/blob/main/README.md)、[官方 `robot_configs.py`](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/unitree_deploy/robot/robot_configs.py)、[训练常量](https://github.com/unitreerobotics/unifolm-vla/blob/main/src/unifolm_vla/rlds_dataloader/constants.py)。

## 推荐的实施顺序

### 1. 先做兼容性盘点

确认 G1 的具体臂型、末端执行器、机载计算单元访问权限、相机服务是否可用、开发 PC 与机器人网络接口，以及是否具备 Dex1-1。官方部署文档对 G1 的前提写得很具体：G1 板卡运行图像服务，开发 PC2 运行 Dex1-1 服务；各设备处于同一局域网。

若本体为 Dex3 或其他手型，应将项目定义为“基于 UniFoLM-VLA 的再训练集成”，而非“部署 UniFoLM-VLA-Base”。此时须先冻结新的动作空间、相机位置和安全约束，再采集与之配套的数据。

依据：[Unitree Deploy：G1 + Dex1 运行前提](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/README.md)、[xr_teleoperate：支持本体/末端与开发环境](https://github.com/unitreerobotics/xr_teleoperate/blob/main/README.md)。

### 2. 建立两个隔离环境

- **推理服务器**：官方建议 CUDA 12.4、Python 3.10.18；安装指定提交的 LeRobot、项目本身和 FlashAttention2 2.5.6。下载 `UnifoLM-VLM-Base` 与 `UnifoLM-VLA-Base`，以 VLA 权重进行 G1 推理。
- **机器人/开发端**：创建 `unitree_deploy` 的 Python 3.10 环境，安装 Pinocchio、部署包和 `unitree_sdk2_python`。在 G1 板卡启动 `image_server`，在开发 PC2 启动并测试 Dex1 服务。

这两个环境不应混装：前者的职责是 GPU 模型，后者的职责是硬件通信与低层控制。这样可以把模型迭代与机器人可用性解耦。

依据：[UniFoLM-VLA 安装说明](https://github.com/unitreerobotics/unifolm-vla/blob/main/README.md#%EF%B8%8F--installation)、[Unitree Deploy 环境与 G1 服务说明](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/README.md#1-%EF%B8%8F-environment-setup)。

### 3. 以硬件健康检查作为首个门槛

不接模型，依次通过官方部署仓库提供的 Dex1、G1 双臂、图像客户端测试；随后用官方的 G1 数据集回放工具验证状态、相机、动作链路。只有这条硬件链条稳定，才启动模型服务器。

这是关键分界：VLA 服务器无法修复 DDS 网络、夹爪服务或视觉流异常；将其作为独立验收项可避免把硬件故障误判为模型能力不足。

依据：[Unitree Deploy 的 G1 测试与数据回放项](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/README.md#2112-testing)。

### 4. 运行最小闭环

配置服务器脚本中的 VLA checkpoint、VLM 路径、端口与 `unnorm_key`；官方示例给 G1 使用 `g1_stack_block`。客户端以 SSH 隧道连接服务器。

这里存在必须先处理的集成缺口：UniFoLM-VLA 服务器暴露的是 `/act`（默认端口 8777），接受带 `full_image`、`state`、`instruction` 的 `observations` 序列并返回动作块；README 所链接的 `unitree_deploy/scripts/robot_client.py` 却调用其上游项目的 `/predict_action`（默认端口 8000）和另一套观测格式。因此该客户端**不能原样连接 UniFoLM-VLA**。应以其硬件采集与执行部分为参考，单独实现一个小型适配客户端：维护时间窗口，构造 `/act` 请求，验证响应的动作维度/单位/排序，且仅在安全限制内将轨迹发送给 G1。

固定初始姿态、动作块长度、状态/动作归一化是 checkpoint 与真实本体之间不可随意更改的契约。特别是 `constants.py` 的本体选择依赖启动参数中的文字匹配；必须显式核实所选模式对应的常量，而不能接受默认值。

依据：[官方真机服务器脚本](https://github.com/unitreerobotics/unifolm-vla/blob/main/scripts/eval_scripts/run_real_eval_server.sh)、[UniFoLM-VLA `/act` 服务实现](https://github.com/unitreerobotics/unifolm-vla/blob/main/deployment/model_server/run_real_eval_server.py)、[上游硬件客户端](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/scripts/robot_client.py)、[训练常量](https://github.com/unitreerobotics/unifolm-vla/blob/main/src/unifolm_vla/rlds_dataloader/constants.py)。

### 5. 面向实验室任务微调，而非寄望零样本泛化

官方说明的训练入口要求：自有数据先符合 LeRobot v2.1，再转换为 HDF5 和 RLDS；将数据集登记到数据加载器；并在 `G1_CONSTANTS` 中配置动作块、动作维度、状态维度及归一化。训练从 `UnifoLM-VLM-Base` 初始化，而不是从随机参数开始。

对于新场景，数据采集应复用部署时的相机、动作定义、控制频率和起始姿态；训练和部署两侧的这些物理语义必须一致。优先在一个桌面任务上做小规模微调、留出未见物体/位置做评估，再扩展任务集合。

依据：[UniFoLM-VLA 数据转换与训练流程](https://github.com/unitreerobotics/unifolm-vla/blob/main/README.md#-dataset)。

## 首次真机实验的安全边界

官方示例具有固定初始姿态并直接向手臂和夹爪发送动作，仓库没有给出针对实验室场地、人员和载荷的通用安全认证。因此必须由实验室现有的 G1 安全规程覆盖：清空运动空间、配置实体急停和独立监护人、先空载/低风险物体、限制手臂工作空间与速度，并保证操作者能立即终止控制。任何与官方 `g1_dex1` 不同的硬件改动，都应回到离线回放和单执行器验证。

这不是额外的“补丁层”，而是把模型策略限制在机器人能够安全履行的物理契约内。

## 已知限制与许可

- 官方 README 展示了 G1 数据和部署入口，但没有给出 GPU 型号、显存下限、端到端时延阈值或每个 G1 硬件变体的保证；这些需要在实验室环境中实测后定为验收标准。
- `UnifoLM-VLA-Base` 模型卡声明为 **CC BY-NC-SA 4.0**；涉及企业合作、服务交付或其他商业使用前，应先做许可审查。
- 官方示例的 G1 路径是 Dex1 夹爪路径；不能将其扩展解释为支持所有 G1 灵巧手或相机组合。

依据：[UniFoLM-VLA 模型卡许可](https://huggingface.co/unitreerobotics/Unifolm-VLA-Base)、[官方部署配置](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/unitree_deploy/robot/robot_configs.py)。

## 进入实施前需要由实验室确认的事实

1. G1 版本（23/29 DoF）、双臂状态与末端执行器是否为 Dex1-1。
2. 是否能登录机载计算单元并启动官方 `image_server`，以及开发 PC2 的 DDS 网卡名。
3. GPU 服务器的 CUDA 12.4 兼容性、可用显存，以及与机器人网络的稳定可达性。
4. 首个任务是否与公开的 G1 任务相近；若否，是否具备遥操作采集、标注、微调和独立安全审批条件。
