# Unitree SDK2 Python for G1：安装前提与权威来源核对

调研日期：2026-08-11

## 当前结论

G1 的 Python 开发接口应采用 Unitree 的 **`unitree_sdk2_python`**，其通信基础是 DDS（Cyclone DDS），而不是 ROS 1。单纯使用该 SDK 读取状态或运行官方 G1 示例，**不以安装 ROS 为前提**。机器人 SSH 登录时出现的 Foxy/Noetic 选择，是机器人板载系统为终端准备 ROS 环境，不能据此推导开发电脑必须安装某一 ROS 发行版。

开发电脑应把 SDK 放在一个独立 Python 虚拟环境中，并在首次运行任何示例前，显式将 Cyclone DDS 绑定到连接 G1 的物理网卡。对当前机器，这个接口是 `eno1`。这解决的是“SDK 在正确的网线上发现 G1”，不涉及任何运动指令。

## 官方来源与应以其 HEAD 为准的事项

| 事项 | 官方来源 | 安装决策 |
| --- | --- | --- |
| Python SDK 与 G1 示例 | [Unitree `unitree_sdk2_python`](https://github.com/unitreerobotics/unitree_sdk2_python) | 以仓库根目录 README、`examples/g1/` 与其依赖声明为唯一安装依据。 |
| DDS/C++ SDK 与网络配置背景 | [Unitree `unitree_sdk2`](https://github.com/unitreerobotics/unitree_sdk2) | 核对 Cyclone DDS、系统依赖和网卡配置的当前写法。 |
| 本项目的 G1 部署环境 | [Unitree Deploy README](https://github.com/unitreerobotics/unifolm-world-model-action/blob/main/unitree_deploy/README.md) | UniFoLM 的机器人端使用独立 Python 3.10 环境，并安装 `unitree_sdk2_python`；模型推理环境另行隔离。 |

官方 SDK README 历来列出的最小系统构建依赖至少包括 `libboost-all-dev`，并采用“克隆仓库后以 `pip install -e .` 安装”的方式。具体 Python 版本、额外依赖与最新命令应在联网后直接读取以上 README 后执行；不要凭旧教程安装 ROS 1 或拷贝未知来源的 DDS 配置。

## 给本机的最小实施顺序

1. 确认本机 Ubuntu 版本与 Python 版本；不要混用系统 Python、conda `tv`（它属于 G1 相机服务）和模型环境。
2. 在线读取 SDK 官方 README 的当前提交内容，确认依赖与支持矩阵。
3. 安装系统构建依赖，创建专用 Python 虚拟环境，克隆并以 editable 方式安装 `unitree_sdk2_python`。
4. 配置 Cyclone DDS 只使用 `eno1`；不要依靠 Wi-Fi 自动发现机器人。
5. 先运行 SDK 的只读 G1 状态订阅示例，确认能发现 DDS 数据；在此之前不运行 hand/arm 控制示例。

## 网络绑定的概念示例（尚不可直接视为最终命令）

Cyclone DDS 需要指定 `eno1`，避免它把 Wi-Fi 当作机器人通信接口。官方示例/版本之间 XML 字段有新旧差异，例如新形式常以 `NetworkInterface name="eno1"` 表达，旧形式可见 `NetworkInterfaceAddress`。应以当前 SDK README 的范例为准，**不要混合两种格式**。

## 调研限制

本次尝试直接访问 GitHub 的原始 README 时，当前机器的 DNS 无法解析 `raw.githubusercontent.com`。因此此笔记只记录权威来源和不随版本变化的架构结论；它不能声称已验证 2026-08-11 的 README HEAD。恢复外网/DNS 后，首项操作应是读取上列两个官方 README，再开始安装。
