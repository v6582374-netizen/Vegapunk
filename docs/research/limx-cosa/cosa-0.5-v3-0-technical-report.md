---
source: https://www.limxdynamics.com/cosa05v3/#zh
title: "COSA 0.5 发布：人形 VLA V³-0 的全身能力升级"
publisher: LimX Dynamics（逐际动力）
published: 2026-07-15
retrieved: 2026-08-17
note: 技术报告全文（中文在前、英文在后），站点导航已去除，图片与引用链接原样保留。仅作内部参考，版权归原作者。
---

# COSA 0.5 发布：人形 VLA V³-0 的全身能力升级

技术报告

2026 年 7 月 15 日

LimX Team

# Introducing COSA 0.5: A Whole-Body Capability Upgrade for the Humanoid VLA V³-0

Technical Report

July 15, 2026

LimX Team

## 摘要

**V³** （读作 'V-cubed'）是机器人 OS **COSA** 中的 VLA-tools 层。本报告介绍随 **COSA 0.5** 发布的 **V³-0** ，包含两部分工作： 

  1. **支持移动全身操作的人形 VLA 技术栈。** V³-0 运行在 43 自由度的 LimX 人形机器人 Oli 上，多级架构让感知、决策与执行在不同时间尺度协同运行；LimX-WBT 跟踪全身目标并维持动态平衡。系统统一移动与操作，使 Oli 能在真实环境中完成行走、弯腰及单手或双手操作等任务。 
  2. **结合人类在环干预的真机强化学习。** 策略自主运行时，专家可以随时、流畅地接管人形机器人的全身控制，及时纠正关键偏差，避免其演化为不可恢复的失败，也防止策略陷入无效重复。基于真实交互构建的真机强化学习闭环使策略能够持续改进，减少重复失误，并提升从失败状态中恢复、继续完成任务的能力。 

_名称说明：V³（读作 'V-cubed'）取自 veni, vidi, vici，即“我来，我见，我征服”。三个词均以 V 开头，因此取其立方之意。_

完整的整理过程 —— 一镜到底

_整个整理过程一镜到底，没有剪辑或中途复位。Oli 依次把脏衣服放进洗衣篮，把鲨鱼玩偶放上椅子，叠好箱子，收走桌上的玩具，扶正歪斜的椅子，把垃圾扔进桶里，最后将钱包递到主人手上。在此期间，机器人始终保持平衡，并多次弯腰到地面。_

* * *

## 1\. 它能做什么

让 **Oli** 整理一间房间。机器人从角落进入，依次把脏衣服放进洗衣篮，收走箱子上的玩具，叠起地上的箱子，清理桌面玩具，扶正歪斜的椅子，清走桌上的垃圾，再把架子上的钱包递给人。整个过程一镜到底；Oli 全程保持平衡，多次弯腰到地面，并将视觉感知转化为协调的全身动作。 

抓取本身相对简单，复杂的是抓取前后的全身动作协调，这源于机器人的**人形** 形态。整理房间不是若干彼此独立的抓取动作：每项任务都需要走近目标、调整朝向、弯腰、伸手、抓取，再转向下一个位置。因此，系统输出不能局限于双手位姿，还要协调双腿、躯干、头部、手臂和双手共同运动。移动与操作需要作为一个整体求解，并贯穿机器人的每一步动作。 

这些动作还必须满足动态稳定约束。人形机器人在运动学上具有天然的不稳定性：伸手会改变质心位置，迈步会切换承重脚，手臂前摆则需要身体其他部位协同补偿。弯腰把鲨鱼玩偶从一堆箱子上捡起并放到椅子上时，几乎全身都要参与，才能让质心保持在双脚支撑范围内。仅跟踪手部目标点、保持身体其他部位不动并不可行。系统需要在达到操作目标的**同时** ，依靠机器人本机算力实时维持这台 43 自由度人形机器人的平衡，并确保每一步都满足动力学约束。这里的操作始终建立在平衡之上。 

本报告介绍 **V³-0** ，一套运行在 43 自由度 LimX 人形机器人 Oli 上的完整 VLA 技术栈。系统包括理解场景和指令的模型、生成全身运动的快速策略，以及负责全身跟踪和平衡的底层控制器。我们还在真机上建立了人类在环与强化学习闭环：专家可在必要时接管全身控制；机器人通过自主 rollout 采集真实交互数据，人工标注其中的失败片段，用于训练 reward model 并通过 RL 更新上层策略。 

下文将分别介绍三个部分：快慢双系统 VLA、LimX-WBT 的平衡执行机制，以及人类在环与真机强化学习。 

* * *

## 2\. 整个系统

![图 1：三层技术栈。](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-architecture.svg)

_图 1。异步双 GPU VLA 架构。慢系统生成最新的意图表示；快系统结合视觉特征和机器人状态生成全身运动目标；LimX-WBT 随后在 Oli 上实时执行这些目标。各模块按各自频率独立运行。_

系统由三个层级组成，各层以不同频率运行（图 1）： 

  * **V³ 慢系统 —— 理解。** 视觉语言模型读取头部相机、手腕相机和语言指令，生成紧凑的意图表示。该层运行较慢，承担需要充分推理的任务。 
  * **V³ 快系统 —— 行动。** 一个小型快速策略结合相机画面与机器人当前状态，将意图转化为短时运动目标，明确双手、双腿、底盘和头部在接下来零点几秒内的目标位置。 
  * **LimX-WBT —— 在平衡中执行。** 单一的全身跟踪策略把这些目标统一转化为腿、腰、手臂和头部的关节指令，并在机器人移动时维持平衡。策略按控制频率实时运行，不遗漏任何控制节拍。同一个控制器同时驱动移动与操作。 

各层通过精简接口通信，并采用异步运行方式。快速层级始终读取慢速层级最近一次的输出，使耗时较长的推理能够与连续运行的控制回路并行。每一层只承担一类任务，并按相应频率执行。 

三个层级各自处理不同问题。快系统输出全身运动的动作块，将移动与操作统一到同一个全身动作空间中（§3）。LimX-WBT 跟踪这些全身目标，并在执行时维持平衡（§4）。真机强化学习则利用真实交互数据继续更新策略（§5）。 

* * *

## 3\. 理解与行动 —— 快慢双系统 VLA（S1）

VLA 负责将语言和视觉输入转化为运动。我们将 VLA 拆分为两个网络：慢系统负责理解场景和任务，快系统负责生成动作。两个网络观察同一环境，但运行频率不同。对厨房场景的理解无需每秒更新一百次，伸手拿杯子的动作却需要高频调整。因此，两类计算分别按各自所需的频率运行。 

![图 2：快慢双系统 VLA。](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-fast-slow.svg)

_图 2。快慢双系统 VLA。慢系统读取相机画面和指令，生成意图 latent；快系统结合相机画面与机器人状态，将意图转化为动作块。快速回路直接使用最近一次 latent，无需等待慢系统更新，随后将动作块发送给 LimX-WBT（§4）。_

### 慢系统 —— 理解

慢系统是一个视觉语言模型，读取头部和手腕相机的画面及语言指令，将视野中的物体、物体位置、指令要求和下一步任务编码为紧凑的 latent。该过程计算开销较大，但所处理的信息相对控制状态变化较慢，因此慢系统以较低频率运行。 

### 快系统 —— 行动

快系统把慢系统的 latent、头部和手腕相机画面以及机器人当前状态转化为运动目标。由于直接读取相机画面，它既能利用慢系统的 latent，也能响应眼前的环境变化。快系统采用一个由 flow matching 训练的小型策略，只需少量去噪步骤，就能将噪声转化为平滑、连续的未来目标轨迹，从而以足够高的频率跟上机器人的运动。 

快系统每次生成一个动作块（action chunk），描述短时程内双手、双腿、底盘和头部的目标位置，交给下游各层取用和刷新。对人形机器人而言，身体移动本身就是任务的一部分；要够到房间另一端的物体，机器人必须先生成相应的行走目标。头部目标让感知由被动转为主动：相机不必只随躯干朝向转动，机器人可以主动转头，持续观察当前要触达的物体或放置位置，使目光始终跟随当前任务。 

部署时，快系统在当前动作块执行期间生成下一个动作块。为使相邻动作块平滑衔接，我们采用 Training-Time RTC [2]：策略在训练阶段学习沿已有动作生成后续轨迹，推理阶段无需额外修正。异步生成让动作持续输出，Training-Time RTC 则保证动作块切换时运动连续。 

### 两者的耦合

慢系统与快系统以不同频率异步运行，仅通过 latent 连接。慢系统周期性更新对场景和任务的高层理解；快系统持续读取最近一次 latent，并结合实时相机画面与机器人状态生成动作。这样，慢速语义推理不会阻塞快速动作回路；慢系统更新意图期间，快系统仍可响应当前环境。 

**为什么这个拆分重要。** 快慢拆分的主要目的并非节省计算，而是应对动态环境。静态场景中的物体位置不变，没有外部碰撞，单一频率的 VLA 可以等待模型完成推理；真实环境中，物体可能移动，人可能伸手介入，机器人也可能受到碰撞，落脚点随之变化。快系统基于实时相机画面和机器人状态高速运行，在快速回路内处理这些变化，响应当前状态而非此前生成的计划。这使系统能够处理动态场景，而不限于预先布置的静态环境。 

**机器人移动时，这种高频响应尤为重要。** 在移动操作中，机器人以实际速度行走；在两次慢系统决策之间，环境和机器人自身状态已经发生了许多变化。即使型号相同，各台机器人的执行器响应、摩擦和质量也存在差异，针对理想模型规划的运动无法在当前机器人上完全复现。如果重规划过慢，这些失配会在快速运动中不断累积，导致机器人越过预定停止位置，或在到位时抓取姿态不准、偏离目标。快速回路每秒多次依据机器人的实际状态重规划，并在移动过程中补偿**当前这台** 机器人的动力学差异，使其在高速运动后仍能准确停下并对准抓取目标。 

### 推理与训练

VLA 的训练和推理均基于自研的 **FluxVLA Engine** 。本次发布将同步开源 Humanoid FluxVLA Engine 的训练与推理代码：该框架以 GR00T 为参考 VLA 模型，并首次支持端侧推理，使模型直接运行在机器人本机上。开发者可以使用同一套基础设施完成训练和部署，相关开发成果也将用于底座的持续迭代。 

VLA 首先通过专家演示进行模仿学习。专家以全身遥操作控制人形机器人完成伸手、抓取和行走等动作，同时记录机器人观察到的画面及其执行动作。 

**表 1。两个系统一览。**

| **慢系统 —— 理解** | **快系统 —— 行动**  
---|---|---  
角色 | 场景 + 语言理解、规划 | 反应式动作生成  
模型 | 视觉语言模型 | 小型 flow-matching 策略  
输入 | 头部 + 手腕相机 + 语言指令 | 意图 latent + 头部/手腕相机 + 机器人状态  
输出 | 意图 latent | 动作块（末端执行器 / 双手 / 底盘 / 头部）  
频率 | < 5 Hz | 50 Hz  
  
* * *

## 4\. 全身跟踪基础模型（S0）

### LimX-WBT 的角色

V³ 给出末端执行器、双腿、底盘和头部的目标，43-DoF 人形机器人还要平稳到达这些目标并保持平衡。VLA 生成目标与 LimX-WBT 执行目标同等重要。在 V³-0 中，执行这些目标的是 **LimX-WBT** （Whole-Body Tracker，全身跟踪器），也就是我们的**运控基础模型** 。LimX-WBT 本身就是一个单一的全身运动控制器，接收连续的全身运动目标，并在真实机器人上实时执行这些目标，使机器人动作协调、保持平衡并能够移动，从而实现边行走边操作。LimX-WBT 只需训练一次，与具体任务无关，也无需针对任务修改；每项任务和每次专家纠正都复用同一个 LimX-WBT。LimX-WBT 不理解任务语义，V³ 和 §5 中的专家纠正通过它驱动机器人。整套技术栈建立在这一可复用的基础层上。 

LimX-WBT 作为 _基础_ 层，仅提供一个统一接口。无论输入由上游策略生成，还是由人类遥操作员提供，都会先转换为**统一的全身运动目标** ，再由 LimX-WBT 在机器人上执行。在 V³-0 中，这一层承担两项职责： 

  * **V³ 的执行层。** V³ 位于上游，LimX-WBT 作为底层执行器，对应“System 1 → System 0”路径。V³ 将全身意图转换为运动目标，LimX-WBT 驱动电机到达目标位置。 
  * **实时遥操作与数据采集。** 同一个控制器实时跟踪人类操作员的全身运动，并支持机器人同步移动；训练 V³ 所用的演示数据（§3）也通过这一方式采集。 

通过 LimX-WBT 的全身遥操作 —— 一位操作员实时驱动整台人形机器人

_LimX-WBT 全身遥操作。视频为真机实录，以 1× 速度播放。操作员实时控制整台人形机器人在地面上行走、深弯腰搬起收纳箱，并在桌前处理衣物。LimX-WBT 在每个控制步根据连续的全身输入驱动机器人，使动作保持平衡和协调。V³ 也通过同一接口驱动机器人，训练 VLA 的全身演示同样由此采集。_

同时满足目标跟踪和平衡约束，是这一层的主要难点，也是 LimX-WBT 存在的原因。对人形机器人而言，到达目标不能简化为计算并下发关节角：向前伸手会改变质心，迈步会切换承重脚，手臂外摆也需要身体其他部位补偿。弯腰到地面会带来大幅质心转移，几乎全身都要同时运动。这类耦合必须由一个协调的全身控制器统一处理，而不能依赖底盘控制器和手臂控制器在接口处相互协调。LimX-WBT 在每个控制步同时完成两项工作： _准确_ 跟踪接收到的全身目标，并让 43-DoF 人形机器人保持平衡。这项能力只需训练一次，且与具体任务无关，因此可以复用于每项任务和每次专家纠正。 

### 模型

LimX-WBT 是一个紧凑的 Transformer 策略。模型规模经过刻意控制，使其可以完全在机器人本机运行，并满足全身控制回路的实时性要求；平衡回路无需依赖任何外部计算机。 

LimX-WBT 通过一个精简接口接收上游目标。每个控制步，它都会接收一段定长的全身参考序列；参考序列按控制频率流式传入。这个接口划分了清晰的上下游边界：上游只需生成目标，LimX-WBT 负责执行。遥操作和 VLA 等上游模块因此可以与跟踪器独立开发，再通过接口组合，彼此无需了解对方的内部实现。 

### 跟踪质量 —— 与业界最强一较高下

为量化 LimX-WBT 的跟踪质量，我们在内部评测集上将其与当前业界最强的全身跟踪器 SONIC [1] 进行对比。评测采用我们在 Oli 上复现的 SONIC 版本，其训练数据和算力与 LimX-WBT 相同。评测集由一组参考运动构成，覆盖 locomotion、manipulation 等日常人体动作；两个控制器分别跟踪同一组动作，并依据参考运动评分。LimX-WBT 在跟踪精度和平滑度两项指标上均取得更优结果： 

**表 2。LimX-WBT 与 SONIC 在内部全身跟踪评测集上的对比（数值越低越好）。**

指标 | SONIC | LimX-WBT  
---|---|---  
**跟踪精度**  
Mean Per-Joint Position Error (MPJPE) | 13.75 mm | **12.85 mm**  
Mean Per-Joint Angle Error (MPJAE) | 3.3° | **1.5°**  
**平滑度 —— 运动 jerk**  
关节空间 jerk | 129.2 | **115.2**  
底盘朝向 jerk | 113.0 | **90.3**  
  
平均关节角误差（MPJAE）的改善最为明显：LimX-WBT 将该指标相较 SONIC **降低了约 55%** ，同时将平均关节位置误差（MPJPE）**降低了约 7%** ，复现的全身姿态更接近参考运动。跟踪精度提升的同时，平滑度也得到改善；这两项指标通常需要权衡。平滑度以**运动 jerk** 衡量，即运动的三阶时间导数，数值越低，动作的突变和抖动越少。在同一评测集上，LimX-WBT 的关节运动和底盘运动均比 SONIC 更平滑，**关节空间 jerk 约低 11%** ，**底盘朝向 jerk 约低 20%** 。在该基准上，LimX-WBT 相较当前业界最强方法同时取得了更高的跟踪精度和更好的运动平滑度。 

* * *

## 5\. 人类在环与真机强化学习

模仿学习依赖数量有限的专家演示，机器人在真机运行时仍会进入演示数据未覆盖的状态。例如，起始位置变化或执行偏差都可能使策略偏离演示分布，进而导致任务失败。 

为提高策略对真实环境的适应能力和任务成功率，我们以模仿学习得到的基础策略为起点，引入人类在环干预和真机强化学习。如图 3 所示，机器人通过自主 rollout 采集真实交互数据；reward model 从人工标注的失败片段中学习任务反馈，用于支持策略更新；专家则在必要时接管全身控制，纠正关键偏差。 

![人类在环与真机强化学习闭环](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-rl-pipeline.svg)

_图 3。人类在环与真机强化学习闭环。机器人进行自主 rollout，专家在必要时接管全身控制；人工标注的失败片段用于训练 reward model，多源真机数据共同用于策略更新。_

### 全身专家接管

机器人自主 rollout 期间，专家持续监控策略的执行情况。机器人出现抓取失误、动作偏离或重复无效行为时，专家可以随时平稳地接管人形机器人的全身控制，并及时纠正偏差。纠正完成后，专家将控制权交还给策略，机器人继续执行任务。 

专家接管人形机器人时，控制权切换必须兼顾动作连贯性和全身协调性。策略和专家的控制指令共用统一的全身运动链路；在专家接管或将控制权交还给策略时，系统会平滑衔接前后的全身运动目标，减少动作突变，使控制权切换自然融入当前动作。 

全身专家接管 —— 专家在任务过程中接管整台人形机器人

_视频展示专家在任务执行过程中接管人形机器人的全身控制，并针对具体失误进行纠正：搬运箱子时，阻止手部继续移向错误的抓握位置，再调整抓取动作；抓取篮子失败后，引导机器人重新抓取；机器人伸手抓取玩偶却没有抓到时，及时阻止并修正动作。_

### 真机强化学习

专家接管用于纠正当前执行偏差，真机强化学习则将真实交互经验进一步用于策略训练。我们构建了由多源真实数据驱动的训练闭环：专家遥操产生的演示数据用于建立基础行为；自主 rollout 中标注的失误和失败片段用于训练 reward model；人类在环干预提供针对这些状态的纠正数据。这些互补信息共同用于更新基础策略，从而减少重复失误，并提高策略从失败状态中恢复并继续完成任务的能力。 

策略更新阶段，reward model 逐时刻评估任务进展，系统据此计算 action advantage，并将其转换为优劣条件，引导策略学习更有利于完成任务的动作；部署时，策略使用正向条件生成动作。 

Reward model 对真机任务进展的逐时刻预测

_reward model 对三个真机任务逐时刻预测任务进展。画面中的曲线和进度值反映模型在各时刻对任务进展的判断。_

### 实验结果

**经真机强化学习更新的策略在三个任务上均优于 behavior cloning（BC）基线。** 评测任务包括把玩偶放上椅子、叠箱子和把物品收进篮子（basket cleanup）。其中，basket cleanup 的成功率从 **18.01% 提升到 74.00%** ；汇总三个任务后，失败率从 **39.65% 降到 11.33%** （图 4）。 

![图 4：BC 策略对比 real-robot RL 的每任务成功率。](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-rl-success.svg)

_图 4。behavior cloning（BC）基线与真机 RL 策略在三个任务上的成功率对比。_

* * *

## 6\. 它能做的事

这段视频记录一台人形机器人在真实居住环境中连续整理整个房间。Oli 从角落进入，在接近 3 分钟的不间断流程中依次完成多项家务，没有剪辑或复位：移动到目标位置，弯腰接近地面，使用单手或双手操作，再继续下一项任务。机器人始终边移动边完成任务，并反复贴近地面操作。 

这段不间断流程是本报告中难度最高的实验。难点不在任何一项**单独** 家务，而在于任务的**长程（long-horizon）** 属性。整条任务链的可靠性由各环节成功率**相乘** 得到，因此，与完成任何单项任务相比，连续完成整条任务链的容错空间更小。一次未能恢复的抓空、一次失衡，或机器人进入专家演示未覆盖的状态，都会使整段流程中止。从头到尾连续执行且不复位，相当于对整套技术栈进行一次端到端集成测试。 

在同一个居住环境中，系统不在任务之间切换策略，完成的任务覆盖以下类型： 

  * **地面拾取与深弯。** 大多数任务临近结束时都需要机器人深弯腰到地面：把鲨鱼玩偶从一堆箱子上捡起并放到椅子上，把箱子从地面抬起后叠放，以及从地上拎起玩具箱再将其放下。每次深弯都会引起大幅质心转移，需要全身协调才能保持平衡，是整段流程中对平衡要求最高的一类动作。 
  * **可变形的布料。** 处理衣物时，机器人从晾衣架上取下一件脏外套，并与另一件衣物一起放入洗衣篮。这些物体柔软、松垮且形状不固定。 
  * **刚性箱体叠放。** 机器人转身，从地上拿起一个箱子，并将其对齐叠放在另一个箱子上。刚性箱体无法通过形变补偿错位，因此放置精度很重要。 
  * **许多小物体。** 机器人拎起玩具箱，将散落在桌面的玩具逐件放入箱中，再把箱子放回原处，连续完成多次小物体抓取。 
  * **家具。** 机器人识别出桌边歪斜的椅子，将其扶正并向内推回；这把椅子的整体尺寸远大于机器人的手部尺寸。 
  * **清理垃圾。** 在有人读书的圆桌旁，机器人弯腰将用过的水瓶和其他垃圾丢进垃圾桶。 
  * **递给人。** 机器人从书架上取下钱包，直接递到人手中；整段流程以这次物品交接结束。 

连续任务依赖整套系统协同运行。V³ 使用同一全身策略完成移动和操作，LimX-WBT 在每项任务中跟踪全身目标并维持平衡。§5 所述真机回路记录自主 rollout 中的失败状态和恢复状态。整个过程无需在导航策略与操作策略之间切换，也未在子任务之间重置场景。 

### 一个系统，整个空间

图 5 按六条能力轴评估各项任务：移动距离、对全身平衡的依赖、抓取精度、是否需要双手、精细操作与手内灵巧程度，以及泛化范围。移动任务在移动距离和全身平衡两条轴上得分较高，补上了仅在桌面操作的 VLA 在这两项能力上的空白；原地任务则在抓取精度和灵巧性两条轴上得分较高。两类任务共同覆盖六条能力轴。 

![图 5：V³-0 任务映射到能力轴。](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-capability-map.svg)

_图 5。每项任务沿六条能力轴获得 0–4 分；青色越深，表示该任务对相应能力的要求越高。“灵巧”包括精细操作、手指级操作和手到手操作。_

### 同样的任务，重新摆布

为了检验机器人是在执行任务，而不是回放记忆中的固定动作，每段视频开始前都由人员现场临时布置场景：更换物体、改变颜色，并任意放置物体；布置完成后，人员在机器人启动前离开。每段视频的初始布局都由现场临时设置，并非预先为机器人准备。 

洗衣服 —— 黑色外套洗衣服 —— 白色外套

_同一衣物拾取任务的并排对比：左侧为黑色外套（与开篇视频中相同），右侧为白色外套。只有衣物颜色不同，机器人的行为保持一致。_

丢掉鲨鱼挪一个箱子 —— 一个粉色的，在一个新位置

_两项不同家务均从现场布置的场景开始：丢掉鲨鱼玩偶，以及移动一个现场任意摆放的粉色箱子。_

**一次抓空后的重试。** 在这段视频中，Oli 第一次伸手未抓到目标；机器人后退一步，再次弯腰，并在第二次尝试中完成抓取。这次恢复是在真机运行过程中发生并记录的。自主 rollout 会记录此类状态；必要时，专家会及时接管机器人。 

### 同一套流程，原地站立

前述任务都在移动中完成，但同一套流程也适用于原地站立的灵巧操作。机器人仍使用同一套慢系统、快系统和 LimX-WBT，这些组件各自沿用与移动任务相同的训练方式。机器人站在桌前，用双手完成任务；技术栈保持不变，变化的只有任务。 

原地 —— 往篮子里捡原地 —— 从没训练过的物体

_左：基础场景。机器人站在桌前，将桌面上的所有物体依次拾取并放入篮子。右：同一任务中，初始场景随机打乱，并持续加入仅在少量训练数据中出现过的物体，以及模型从未见过的物体；机器人仍能完成抓取与收纳。_

精细操作 —— 糖果精细操作 —— 失败后重试

_左：从托盘中拾取小颗糖果；毫米级位置偏差就可能导致抓取落空。右：抓取失败后，机器人能够及时调整动作并再次尝试，直至完成抓取。_

双手 —— 叠杯子手到手 —— 一个球扔进篮子

_左：双手协同操作，每只手拿起一只杯子，并将其叠到第三只杯子上。右：手到手传递，机器人用一只手捡起球，横向传给另一只手，再将球丢进篮子。_

这些原地任务使用同一个 VLA、同一个全身控制器和同一台机器人，区别仅在任务本身。 

### 从不摆拍

清理桌面 —— 一种布局清理桌面 —— 另一种布局

_同一个桌面清理任务采用两种不同布局。玩具种类和摆放位置每次都会变化；机器人抓取当次桌面上的所有物体，并将其放入袋中。_

每次布置都会改变三项因素：**物体** （黑色外套换为白色外套，玩具和玩偶也各不相同）、**颜色** 和**摆放位置** 。物体由人员现场任意摆放，不依赖预先标记的位置；这些变化均未使任务失效，由此可区分策略学到的是任务本身，还是一套固定的场景布置。 

* * *

## 7\. 结论与展望

年初，我们发布了机器人 OS 的首个版本 **COSA 0** 。**COSA 0.5** 更新了其中的 S1（VLA）和 S0（运控）两层，本报告介绍了这两项更新。V³-0 是一套运行在真实人形机器人上的完整 VLA 技术栈：慢系统理解场景和指令，快系统生成全身运动，S0 负责全身跟踪与平衡。系统还支持真机全身专家接管，并包含 reward model 和 RL 更新回路。在当前评测的三个任务中，更新后策略的成功率均高于 BC 基线。 

后续工作将继续扩展任务、数据和评测范围： 

  * **扩展真机 RL** ：增加任务、场景和自主 rollout 数据，持续评估更新后策略在不同实验设置下的表现。 
  * **用真实数据闭合 S0 的回路** ：使用真机数据缩小长时程、大幅度运动中残余的 sim-to-real 差距，重点处理仿真难以可靠覆盖的部分。 
  * **接触与力** ：在 S1→S0 接口中加入显式的力与阻抗，使机器人能够执行接触密集型任务；在这类任务中，施力大小与目标位置同等重要。 
  * **以任务与物体多样性为基础** ：当前整理流程已在同一居住环境中覆盖可变形布料、刚性箱体叠放、家具、多种小物体和向人递交物品；后续泛化工作将基于这一任务广度展开。 
  * **泛化与跨平台** ：评估策略面对未见过的新物体和新场景时的表现，并扩展到本报告所用机器人之外的其他 LimX 平台。 

后续进展仍将以真机实验结果为依据。 

* * *

## 参考文献

_[1] Luo, Zhengyi, et al. "SONIC: Supersizing motion tracking for natural humanoid whole-body control." arXiv preprint[arXiv:2511.07820](https://arxiv.org/abs/2511.07820) (2025)._

_[2] Black, Kevin, Allen Z. Ren, Michael Equi, and Sergey Levine. "Training-Time Action Conditioning for Efficient Real-Time Chunking." arXiv preprint[arXiv:2512.05964](https://arxiv.org/abs/2512.05964) (2025)._

## 引用本文

如需引用本文，可以使用以下 BibTeX 条目：
    
    
    @online{fu2026cosa05,
    author = {Zhen Fu and Tao Yu and Hongbo Zhu and Haoxiang Luo and Zhiming Chen and Pinxi Shen and Jiaqi Song and Zheyi Zhao and Bozhen He and Jiangtao Hu and Cong Shen and Haolin Ma and Zimo Huang and Ben Liu and Wei Zhang and Hua Chen},
    title = {Introducing {COSA} 0.5: A Whole-Body Capability Upgrade for the Humanoid {VLA} {V³-0}},
    date = {2026-07-15},
    year = {2026},
    url = {https://limxdynamics.com/cosa05v3/#en},
    }

## Summary

**V³** ('V-cubed') is the VLA tooling layer in **COSA** , our robot OS. This report describes **V³-0** , released with **COSA 0.5** , and presents two main developments: 

  1. **A humanoid VLA technology stack for mobile whole-body manipulation.** V³-0 runs on Oli, a 43-DoF LimX humanoid. Its multi-tier architecture lets perception, decision-making, and execution operate at their respective rates; LimX-WBT tracks whole-body targets while maintaining dynamic balance. The stack unifies locomotion and manipulation as coordinated whole-body behavior, allowing Oli to walk, bend, and continuously perform one- or two-handed tasks in the real world. 
  2. **Real-robot reinforcement learning with human-in-the-loop intervention.** During autonomous execution, an expert can smoothly assume whole-body control at any time to correct critical deviations before they become unrecoverable failures or trap the policy in ineffective repetition. A real-robot reinforcement-learning loop built on physical interaction allows the policy to keep improving, repeat fewer mistakes, and recover more reliably from failure states to complete the task. 

_The name V³ ('V-cubed') combines the three V's in veni, vidi, vici ('I came, I saw, I conquered') as V cubed._

The full tidying run — one continuous take

_The complete tidying run, shown from start to finish in one unbroken take without cuts or resets: laundry placed in the hamper, the shark plushie set on the chair, boxes stacked, toys cleared from the desk, a chair straightened, trash put in the bin, and a wallet handed to the owner. Oli remains balanced throughout, repeatedly bending down to the floor._

* * *

## 1\. What it does

Given the instruction to tidy the room, **Oli** walks in from the corner and begins working. It puts laundry in the hamper, clears toys from the boxes, stacks the boxes on the floor, removes toys from the desk, straightens a chair, clears trash from the table, and takes a wallet from the shelf and hands it to the owner. The full sequence runs in one continuous take. Oli remains balanced throughout, including repeated bends to the floor, and converts its visual observations into coordinated whole-body behavior. 

The grasp itself is the easy part; the harder part is the surrounding sequence, and that difficulty arises from the robot's **humanoid** body. "Tidy the room" is not a single action: each task consists of walking to the relevant location, orienting the body, bending, reaching, grasping, and then moving to the next location. The robot must therefore produce more than two hand poses. Its legs, torso, head, arms, and hands must move as one coordinated system. Locomotion and manipulation are coupled throughout the task and must be solved together at every step. 

These motions must also be performed on a body that can fall. A humanoid is kinematically unstable: reaching shifts its center of mass, each step transfers the load between the feet, and forward arm motion must be compensated elsewhere in the body. When Oli bends to take the shark plushie from the boxes and place it on the chair, almost the entire body moves to keep the center of mass over the feet. Tracking a hand target while holding the rest of the body fixed is not sufficient. The onboard system must meet the manipulation target in real time while keeping the 43-DoF humanoid balanced and within its dynamic limits at every step. 

This report presents **V³-0** , a complete VLA stack deployed on Oli, a physical LimX humanoid with 43 degrees of freedom. The stack combines a model for scene and instruction understanding, a fast policy that generates whole-body motion, and a low-level controller for whole-body tracking and balance. We also operate a human-in-the-loop, real-robot RL loop: an expert can smoothly assume whole-body control at any time, while human-annotated failure segments from autonomous rollouts train a reward model that provides feedback for RL policy updates. 

The following sections describe the fast–slow VLA, balanced execution by LimX-WBT, and the expert-takeover and policy-update loop on the real robot. 

* * *

## 2\. The whole system

![Figure 1: the three-tier stack.](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-architecture.svg)

_Figure 1. Asynchronous dual-GPU VLA architecture. The slow system produces an intent latent. The fast system combines the latest latent with visual features and robot state to generate whole-body motion targets, which LimX-WBT executes on Oli in real time. Each component runs independently at its own rate._

The architecture has three tiers, each operating at its own rate (Figure 1): 

  * **V³ slow system — understand.** A vision-language model processes the head and wrist camera streams together with the language instruction, producing a compact representation of intent. This tier handles slower, deliberative computation. 
  * **V³ fast system — act.** A compact, high-rate policy combines that intent with current camera observations and robot state. It generates short motion segments specifying targets for the hands, legs, base, and head over the next fraction of a second. 
  * **LimX-WBT — execute with balance.** A single whole-body tracking policy converts those targets into joint commands for the legs, waist, arms, and head. It moves the robot while maintaining balance, meets the real-time control deadlines, and handles locomotion and manipulation through one controller. 

The tiers communicate through intentionally narrow interfaces and do not run in lockstep. Each lower tier uses the latest output from the tier above, so every tier can operate at the rate appropriate to its function without pausing the control loop. 

Each tier addresses a separate part of the system. The fast system emits a whole-body action chunk that represents locomotion and manipulation in one action space (§3). LimX-WBT tracks these targets while maintaining balance (§4). Real-robot reinforcement learning then uses real interaction data to continue updating the policy (§5). 

* * *

## 3\. Understanding and acting — the fast–slow VLA (S1)

The VLA converts language and vision into motion through two networks that receive the same observations but operate at different rates. The slow network handles scene and task understanding, while the fast network generates actions. These computations have different time scales: the semantic interpretation of a kitchen does not need to change a hundred times per second, whereas a reach toward a cup requires frequent updates. 

![Figure 2: the fast–slow VLA.](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-fast-slow.svg)

_Figure 2. Fast–slow VLA. The slow system processes the cameras and instruction to produce an intent latent. The fast system combines the latest latent with camera observations and robot state to generate an action chunk, without waiting for another slow-system update. LimX-WBT then executes the action chunk (§4)._

### The slow system — understanding

The slow system is a vision-language model that processes the head and wrist cameras and the language instruction. It produces a compact latent representation of the scene and task, including the visible objects, their locations, the requested objective, and the next required step. This computation is relatively expensive and changes slowly compared with control, so it runs at the low end of the frequency hierarchy. 

### The fast system — acting

The fast system converts the slow system's latent, head and wrist camera inputs, and current robot state into whole-body motion. Direct access to the cameras lets it respond to the current scene rather than relying only on the latent. The system uses a small policy trained with flow matching. In a few denoising steps, it transforms noise into a smooth, continuous trajectory of future targets, allowing it to run at the rate required by the moving robot. 

Rather than emitting individual actions, the fast system produces an action chunk: a short-horizon sequence of targets for the hands, legs, base, and head that lower tiers consume and refresh. For a humanoid, controlling the base is necessary because reaching an object elsewhere in the room first requires walking to it. Head control provides active perception: the robot turns its head toward the relevant object or placement location rather than restricting the head-camera view to the torso's facing direction. Its gaze therefore follows the current task. 

During deployment, the fast system generates the next action chunk while the current one executes, maintaining continuous output. Training-Time RTC [2] conditions the policy during training to extend existing actions into a future trajectory without inference-time corrections, producing smooth transitions between adjacent chunks. 

### Coupling the two

The slow and fast systems run asynchronously at different rates, coupled only by the latent representation. The slow system periodically updates its high-level interpretation of the scene and task. The fast system continuously combines the latest latent with live camera inputs and robot state to generate actions. Semantic reasoning therefore does not block the action loop, and the fast system remains responsive while the slow system updates the intent. 

**Why the split matters.** The fast–slow split is not mainly about saving computation; its primary role is to keep pace with a changing world. A single-rate VLA may be sufficient when objects remain fixed, the robot is undisturbed, and computation can proceed against a static scene. In real environments, objects move, people reach into the workspace, the robot is jostled, and its footing changes. The fast system uses live camera observations and robot state to respond to these changes within its own loop, instead of continuing to follow a plan based on an earlier state. That is what allows the system to operate in dynamic scenes rather than only in staged, static ones. 

**The effect is most pronounced while the robot is moving.** During mobile manipulation, the robot walks at real speed and its state can change substantially between slow-system updates. Dynamics also vary between nominally identical units because of differences in actuator response, friction, and mass. A motion planned for an idealized robot will therefore not execute identically on a particular unit. With slow replanning, these discrepancies accumulate during rapid motion, leading to overshoot, grasp misalignment, or drift. The fast loop replans from the robot's measured state many times per second, correcting for the dynamics of the specific unit so that, even during rapid motion, it can stop at the intended location and align for a grasp. 

### Inference and training

Both VLA training and inference run on **FluxVLA Engine** , our internal VLA infrastructure. With this release, we are open-sourcing the Humanoid FluxVLA Engine training and inference code. The framework uses GR00T as its reference VLA model and, for the first time, supports on-device inference on the robot's own computer. Developers can train and deploy on the same infrastructure used by this system, and what they build feeds into subsequent iterations. 

Initial VLA training uses imitation learning from expert demonstrations. An expert teleoperates the whole humanoid through reaching, grasping, and walking motions while the robot records its observations and actions. 

**Table 1. The two systems at a glance.**

| **Slow system — understand** | **Fast system — act**  
---|---|---  
Role | scene + language understanding, planning | reactive action generation  
Model | vision-language model | small flow-matching policy  
Input | head + wrist cameras + language instruction | intent latent + head/wrist cameras + robot state  
Output | intent latent | action chunk (end-effector / hands / base / head)  
Rate | < 5 Hz | 50 Hz  
  
* * *

## 4\. A whole-body tracking foundation model (S0)

### The role of LimX-WBT

V³ specifies targets for the hands, legs, base, and head. The 43-DoF humanoid must then reach those targets smoothly without losing balance. Generating the targets with the VLA and executing them with LimX-WBT are equally important. In V³-0, execution is handled by **LimX-WBT** (Whole-Body Tracker), our **motion-control foundation model**. This single whole-body controller receives a stream of motion targets and reproduces them on the physical robot in real time, coordinating the full body, maintaining balance, and allowing the robot to walk while manipulating. LimX-WBT is trained once, remains task-agnostic, and is reused without modification across tasks and expert corrections. It has no representation of the task itself; V³ and the expert corrections described in §5 command the robot through this shared base layer. 

LimX-WBT serves as a _foundation_ layer rather than a task-specific controller because it exposes a single common interface. Motion from either an upstream policy or a human teleoperator is represented as a **unified whole-body motion target** , which LimX-WBT executes on the robot. In V³-0, this layer has two roles: 

  * **The execution layer for V³.** LimX-WBT is the low-level executor for V³ along the "System 1 → System 0" path. V³ converts whole-body intent into a motion target, and LimX-WBT drives the motors to reach the requested positions. 
  * **Real-time teleoperation for data collection.** The same controller tracks a human operator's live whole-body motion, including mobile full-body behavior. This interface is used to collect the demonstrations for training V³ (§3). 

Full-body teleoperation through LimX-WBT — an operator drives the whole humanoid in real time

_Full-body teleoperation through LimX-WBT on the physical robot at 1× speed. An operator controls the humanoid live while walking across the floor, bending deeply to lift storage boxes, and handling laundry at a table. LimX-WBT converts this input into balanced, coordinated motion at every step. V³ uses the same interface, which is also used to collect the whole-body demonstrations for VLA training._

This tier is required because accurate tracking must be maintained together with balance. For a humanoid, reaching a target involves more than solving joint angles and issuing commands: a forward reach shifts the center of mass, a step transfers the load between feet, and outward arm motion requires compensation elsewhere in the body. Bending to the floor produces a particularly large center-of-mass shift and engages almost the entire body. This motion requires a single coordinated whole-body controller rather than separate base and arm controllers whose outputs must be reconciled. At every step, LimX-WBT tracks the requested whole-body target _accurately_ while keeping the 43-DoF humanoid balanced. Because LimX-WBT learns this capability once in a task-agnostic setting, the same learned balance capability is available to every task and human correction issued through it. 

### The model

LimX-WBT is a compact Transformer policy designed to run entirely on board within the real-time budget of the whole-body control loop. No off-board computer participates in the balance loop; the policy responsible for balance executes on the robot itself. 

The interface is intentionally narrow. At each control step, LimX-WBT consumes a fixed-length whole-body reference streamed at the control rate. The upstream source, whether teleoperation or the VLA, only needs to produce this target, while LimX-WBT only needs to realize it. This contract allows the upstream system and the tracker to be developed independently without either depending on the other's implementation. 

### Tracking quality — versus the state of the art

We evaluate LimX-WBT against SONIC [1], the current state-of-the-art whole-body tracker, using our internal evaluation set. The SONIC baseline is our reproduction on Oli, trained with the same data and compute as LimX-WBT. The evaluation set contains a library of reference motions spanning locomotion, manipulation, and other everyday human movements. Both controllers track the same motions and are scored against the references. LimX-WBT performs better in both tracking _accuracy_ and motion _smoothness_ : 

**Table 2. LimX-WBT vs SONIC on the in-house whole-body tracking eval (lower is better).**

Metric | SONIC | LimX-WBT  
---|---|---  
**Tracking accuracy**  
Mean Per-Joint Position Error (MPJPE) | 13.75 mm | **12.85 mm**  
Mean Per-Joint Angle Error (MPJAE) | 3.3° | **1.5°**  
**Smoothness — motion jerk**  
Joint-space jerk | 129.2 | **115.2**  
Base-orientation jerk | 113.0 | **90.3**  
  
For tracking accuracy, LimX-WBT reduces mean per-joint angle error (MPJAE) by roughly **55%** and mean per-joint position error (MPJPE) by roughly **7%** compared with SONIC, bringing the reproduced whole-body pose substantially closer to the reference. This improvement in precision avoids the usual trade-off with smoothness. We measure smoothness using **motion jerk** , the third time derivative of motion; lower values indicate less abrupt and less jittery movement. On the same evaluation set, LimX-WBT records roughly **11% lower joint-space jerk** and **20% lower base-orientation jerk** than SONIC. Against this state-of-the-art baseline, LimX-WBT is both more precise and smoother. 

* * *

## 5\. Human-in-the-loop and real-robot RL

Imitation learning is limited to the states represented in the expert demonstrations. On the physical robot, the policy will still encounter states outside that set. A different initial position or a small execution error can move the policy outside the demonstration distribution and cause the task to fail. 

To improve real-world robustness and task success, we augment the imitation-trained base policy with human-in-the-loop intervention and real-robot reinforcement learning. Autonomous rollouts collect interaction data on the robot. A reward model learns task feedback from human-annotated failure clips and provides the signal for policy updates, while an expert assumes whole-body control when a rollout requires correction (Fig. 3). 

![Human-in-the-loop and real-robot RL loop](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-rl-pipeline.svg)

_Fig. 3. Human-in-the-loop real-robot reinforcement learning. The robot performs autonomous rollouts, with an expert taking over whole-body control when necessary. Human-annotated failure clips train the reward model, and the combined real-world data sources are used to update the policy._

### Whole-body expert takeover

An expert monitors the policy during autonomous rollouts. If the robot misses a grasp, drifts off course, or settles into an ineffective motion pattern, the expert can smoothly take over whole-body control at any point, correct the motion, and return control to the policy. 

For a humanoid, the transition must preserve both motion continuity and whole-body coordination. The policy and the expert therefore command the robot through the same whole-body motion pathway. At takeover and handback, the system blends their whole-body targets so that control changes without introducing a jolt into the ongoing motion. 

Whole-body expert takeover — the expert takes over the whole humanoid during a task

_Examples of whole-body expert takeover during execution. The expert intercepts and repositions a hand approaching the wrong grasp point while moving a box, guides a regrasp after a failed basket grasp, and stops and corrects an ineffective empty grasp toward the plush._

### Real-robot RL

Expert takeover corrects the current error, while real-robot reinforcement learning turns that experience into a lasting policy update. The update uses several sources of physical-robot data. Teleoperated expert demonstrations establish the base behavior, mistakes and failures identified during autonomous rollouts train the reward model, and human-in-the-loop interventions provide corrections for those specific states. Together, these data allow us to update the base policy so that it repeats the same errors less often and more reliably recovers from a poor state to complete the task. 

For policy updates, the reward model estimates task progress at each moment. The system uses this score to compute an action advantage, converts the advantage into a positive or negative condition, and guides the policy toward actions that advance the task. At deployment, the policy operates under the positive condition. 

The reward model's moment-to-moment prediction of task progress on the real robot

_Reward-model predictions of moment-to-moment task progress for three physical-robot tasks. The on-screen curve and progress value show the model's estimate of task status._

### Results

**After the real-robot reinforcement-learning update, the policy outperforms the behavior-cloning (BC) baseline on all three tasks.** The tasks are placing a plush on a chair, stacking boxes, and clearing items into a basket (basket cleanup). For basket cleanup, the most difficult task, success increases from **18.01% to 74.00%**. Across all three tasks, the failure rate decreases from **39.65% to 11.33%** (Fig. 4). 

![Figure 4: BC policy vs real-robot RL per-task success.](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-rl-success.svg)

_Fig. 4. Success rate for each of the three tasks, comparing the behavior-cloning (BC) baseline with the real-robot reinforcement-learning policy._

* * *

## 6\. What it can do

The room-tidying demonstration uses one humanoid in an occupied home and is recorded as a single continuous take. Oli enters from the corner and completes each chore in sequence during a run of nearly three minutes, without cuts or resets. It walks to each location, bends toward the floor, manipulates with one or both hands, and continues to the next task. The robot stays mobile throughout the run, moving from one workspace to the next, and each chore eventually brings it close to the ground. 

The unbroken run is the most demanding evaluation in this report because it is **long-horizon** , not because any individual chore is unusually difficult. Reliability compounds across the sequence, making completion of the full run less forgiving than completion of any single task. An uncorrected missed grasp, a loss of balance, or drift into a state absent from the demonstrations ends the entire run. Completing the sequence without a reset therefore serves as an integration test for the full stack. 

The run covers the following behaviors in one home without changing policies between tasks: 

  * **Floor pickups and deep bends.** Most tasks end with a bend to the floor: taking the shark plushie from a pile of boxes and setting it on the chair, lifting a box from the ground for stacking, and picking up and replacing a toy bin. Each deep bend produces a large center-of-mass shift that the whole body must absorb, providing the run's strongest test of balance. 
  * **Deformable cloth.** During the laundry task, Oli removes a dirty coat from a drying rack and drops it, together with another garment, into a hamper. These soft, flexible objects do not retain a fixed shape. 
  * **Rigid box-stacking.** Oli turns, picks up a box from the floor, and places it squarely on another box, a rigid-object task that requires precise placement. 
  * **Many small objects.** Oli picks up a toy bin, moves the toys scattered across the desk into it one at a time, and returns the bin to the floor. The task requires a sequence of small grasps rather than a single pick. 
  * **Furniture.** Oli identifies a chair left askew beside the table, straightens it, and pushes it in, manipulating an object substantially larger than its hand. 
  * **Clearing trash.** At the round table where the owner is reading, Oli bends down and drops a used water bottle and other trash into the bin. 
  * **A handover to a person.** Oli takes a wallet from a bookshelf and hands it directly to the owner, ending the run with a human handover rather than an object placement. 

Completing a run of this length requires the full system. V³ controls locomotion and manipulation through one whole-body policy, while LimX-WBT tracks the generated targets and maintains balance for every task. The real-robot loop described in §5 records the failure and recovery states encountered during autonomous runs. The system does not switch policies between navigation and manipulation, and the scene is not reset between subtasks. 

### One system, the whole space

Figure 5 scores each task along six dimensions relevant to humanoid operation: travel distance, dependence on whole-body balance, grasp precision, bimanual operation, fine and in-hand dexterity, and generalization. The tasks form two profiles. Mobile tasks emphasize locomotion and whole-body balance, capabilities not addressed by a table-bound VLA; in-place tasks emphasize precision and dexterity. Together, the evaluated tasks span all six dimensions. 

![Figure 5: V³-0 tasks mapped to capability axes.](https://limx-video.oss-cn-beijing.aliyuncs.com/cosa05v3/limx-vla-capability-map.svg)

_Figure 5. Task scores from 0–4 across six capability axes. Darker teal indicates greater demand on a capability. "Dexterity" includes fine finger-level and hand-to-hand manipulation._

### The same tasks, rearranged

To distinguish task execution from replay of a memorized routine, each run begins with a person manually rearranging the scene. The person swaps objects, changes their colors, and drops them in unconstrained locations, then leaves before the robot starts. Each clip therefore begins from an arrangement that was not predefined for the robot. 

Laundry — black coatLaundry — white coat

_Side-by-side executions of the same laundry pickup with the black coat used in the main run and with a white coat. The garment color changes, while the behavior remains the same._

Throwing out the sharkMoving a box — a pink one, at a fresh spot

_Two tasks performed in scenes arranged immediately before execution: discarding the shark and moving a pink box placed at an unconstrained location._

**A retry after a missed grasp.** In this clip, Oli misses the target on the first reach. It steps back, bends again, and succeeds on the second attempt. This recovery was recorded on the physical robot. Autonomous rollouts log states of this kind, with an expert intervening when necessary. 

### The same pipeline, standing still

The preceding tasks emphasize mobile manipulation, but the same pipeline also supports stationary, dexterous work at a table. The slow system, fast system, and LimX-WBT remain unchanged, and the training procedure for each component is the same as before; only the task differs. 

In-place — picking into a basketIn-place — objects it was never trained on

_Left: Base scenario. The robot stands at a table, picks up each object on the tabletop in sequence, and places it in a basket. Right: The same task with a randomized initial scene and progressively introduced objects, including objects with limited representation in the training data and objects the model has never seen. The robot continues to complete the picking and collection task successfully._

Fine manipulation — candyFine manipulation — retry until the grasp lands

_Left: Fine manipulation. The robot picks up tiny candies from a tray, where a millimeter-scale positioning error can cause a missed grasp. Right: After a failed grasp, the robot promptly adjusts its motion and retries until it picks up the candy._

Two hands — stacking cupsHand-to-hand — a ball into the basket

_Left: Bimanual coordination. The robot picks up one cup in each hand and stacks both on a third cup. Right: Dexterous hand-to-hand transfer. The robot picks up a ball with one hand, passes it laterally to the other, and places it in a basket._

All of these examples use the same VLA and whole-body controller. 

### Nothing is staged

Clearing the table — one layoutClearing the table — another layout

_The same table-clearing task in two layouts. The toys and their positions change on every run; the robot grasps whatever is on the table and drops it into the bag._

Three factors vary across runs without preventing task completion: **the objects** (for example, a white coat instead of a black one, or different toys and plushies), **their colors** , and **their positions**. Objects are dropped by hand rather than placed on marked locations. The policy is therefore executing the task across varied setups rather than reproducing one memorized arrangement. 

* * *

## 7\. Conclusion and outlook

At the beginning of the year, we released **COSA 0** , the first version of our robot OS. **COSA 0.5** updates S1, the VLA layer, and S0, the motion-control layer; this report describes those updates. V³-0 is a complete VLA stack operating on a physical humanoid. Its slow system interprets the scene and instruction, its fast system generates whole-body motion, and S0 provides whole-body tracking and balance. A real-robot training loop combines whole-body expert takeover, a reward model, and reinforcement-learning updates to improve the policy on the robot. Across the three evaluated tasks, the updated policy outperforms the behavior-cloning baseline. 

Next, we are expanding the task set, data, and evaluation in the following areas: 

  * **Scaling real-robot RL** : adding tasks, scenes, and autonomous-rollout data, and evaluating the updated policy across the expanded set. 
  * **Closing S0's loop with real data** : using physical-robot data to reduce the remaining sim-to-real gap for long-horizon, large-amplitude motion, where simulation is least reliable. 
  * **Contact and force** : adding explicit force and impedance terms to the S1→S0 interface for contact-rich tasks in which applied force matters as much as target position. 
  * **Task and object diversity as a foundation** : the tidying run already spans deformable cloth, rigid box-stacking, furniture, many small objects, and a handover to a person, all in one home. That breadth provides the foundation for further generalization. 
  * **Generalization and cross-platform evaluation** : evaluating unseen objects and scenes, as well as additional LimX platforms beyond the robot used in this report. 

We will continue to measure progress on the physical robot. 

* * *

## References

_[1] Luo, Zhengyi, et al. "SONIC: Supersizing motion tracking for natural humanoid whole-body control." arXiv preprint[arXiv:2511.07820](https://arxiv.org/abs/2511.07820) (2025)._

_[2] Black, Kevin, Allen Z. Ren, Michael Equi, and Sergey Levine. "Training-Time Action Conditioning for Efficient Real-Time Chunking." arXiv preprint[arXiv:2512.05964](https://arxiv.org/abs/2512.05964) (2025)._

## Citation

_If you’d like to cite this post, you can use the following BibTeX entry:_
    
    
    @online{fu2026cosa05,
    author = {Zhen Fu and Tao Yu and Hongbo Zhu and Haoxiang Luo and Zhiming Chen and Pinxi Shen and Jiaqi Song and Zheyi Zhao and Bozhen He and Jiangtao Hu and Cong Shen and Haolin Ma and Zimo Huang and Ben Liu and Wei Zhang and Hua Chen},
    title = {Introducing {COSA} 0.5: A Whole-Body Capability Upgrade for the Humanoid {VLA} {V³-0}},
    date = {2026-07-15},
    year = {2026},
    url = {https://limxdynamics.com/cosa05v3/#en},
    }
