# 具身智能实验室监控素材来源

> 调研日期：2026-07-26

## 推荐结论

优先采用同一真实自主材料实验室的 Wikimedia Commons 机械臂 WebM 作为三个工作机位，再以 NASA JPL 的真实实验室广角补足第四机位。
这组素材比通用 GIF 更接近真实具身智能实验室，并且每个来源都有可核验的授权信息和原始媒体直链。
这些并不是同一次实验的同步四路摄像机，所以产品保留“演示模式”和“非实时摄像头输入”标识，不暗示它们来自同一台机器人或同一时刻。
当前版本遵循演示需求，使用本地 GIF 而不是运行时加载外链视频。

## 当前应用内的派生 GIF

这些素材原先作为已退休根 Web 工作台的演示资源。根 Web 前端已移除；本记录保留来源、授权和改动说明，供未来 Desktop App 重新接入时复用。

四段 GIF 均由下列原始媒体中截取可循环的 5 秒片段，缩放为 800 × 450、10 fps、50 帧，并以静音循环方式嵌入。
派生处理仅包括片段裁切、尺寸缩放、帧率调整和 GIF 转码，不改变原始画面内容或表达含义。

| 已退役 Web 应用文件（历史路径） | 界面机位 | 原始来源 | 授权与署名 |
| --- | --- | --- | --- |
| `frontend/public/embodied/lab-main.gif`（已退役） | C-01 主机位 / 样本制备站 | [R1 样品制备机械臂 WebM](https://upload.wikimedia.org/wikipedia/commons/0/0f/Robot_arm_R1_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_%28handling_powders_and_slurries_in_the_sample_preparation_station%29.webm) | Nathan J. Szymanski 等，CC BY 4.0，via Wikimedia Commons，已裁切与循环转码。 |
| `frontend/public/embodied/lab-overhead.gif`（已退役） | C-02 高位总览 / 样品转移台 | [R2 坩埚转移机械臂 WebM](https://upload.wikimedia.org/wikipedia/commons/1/18/Robot_arm_R2_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_%28moving_crucibles%29.webm) | Nathan J. Szymanski 等，CC BY 4.0，via Wikimedia Commons，已裁切与循环转码。 |
| `frontend/public/embodied/lab-close.gif`（已退役） | C-03 操作近景 / 精密处理单元 | [R3 UR5e 与 X 射线衍射仪 WebM](https://upload.wikimedia.org/wikipedia/commons/e/ef/Robot_arm_R3_%28UR5e%29_retrieving_powder_samples_%28post-annealing%29_and_cooperating_with_an_Aeris_X-ray_diffractometer_for_their_characterization_%28autonomous_lab%29.webm) | Nathan J. Szymanski 等，CC BY 4.0，via Wikimedia Commons，已裁切与循环转码。 |
| `frontend/public/embodied/lab-wide.gif`（已退役） | C-04 环境广角 / 工程测试场 | [NASA JPL Perseverance 测试车库 MP4](https://images-assets.nasa.gov/video/JPL-20201006-M2020f-0001-Twin%20Rover%20Gets%20to%20Work/JPL-20201006-M2020f-0001-Twin%20Rover%20Gets%20to%20Work~mobile.mp4) | NASA/JPL-Caltech，已裁切与循环转码，仅作展示用途，不暗示 NASA 背书。 |

## 授权与使用边界

前三项采用 [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) 授权，发布时必须给出作者、作品标题或描述、Wikimedia Commons 来源、CC BY 4.0 链接，并说明为适配循环播放所作的裁切或转码。
R1、R2 和 R3 的 Commons 元数据作者行是 Nathan J. Szymanski、Bernardus Rendy、Yuxing Fei、Rishi E. Kumar、Tanjin He、David Milsted、Matthew J. McDermott、Max Gallant、Ekin Dogus Cubuk、Amil Merchant、Haegyeom Kim、Anubhav Jain、Christopher J. Bartel、Kristin Persson、Yan Zeng 和 Gerbrand Ceder。
NASA 的官方[图像与媒体使用政策](https://www.nasa.gov/nasa-brand-center/images-and-media/)说明其图像、音频和视频通常不受美国版权保护，可用于信息性网页，但必须署名 NASA、不得将 NASA 徽标另作本项目的品牌元素、不得暗示 NASA 为本项目背书，并应避开任何标注为第三方受版权保护的材料。
所有下列直链都已对小范围 Range 请求返回可播放的媒体响应，其中 Commons 条目为 `206 video/webm`，NASA 条目为 `206 video/mp4`。

## 推荐的四机位素材组

### 1. 主机位 - R1 样品制备机械臂

- [来源页面：Robot arm R1 operation of the autonomous laboratory](https://commons.wikimedia.org/wiki/File:Robot_arm_R1_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_(handling_powders_and_slurries_in_the_sample_preparation_station).webm) 记录了自主材料合成实验室中 R1 机械臂处理粉末和浆料的真实操作。
- [原始 WebM](https://upload.wikimedia.org/wikipedia/commons/0/0f/Robot_arm_R1_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_%28handling_powders_and_slurries_in_the_sample_preparation_station%29.webm) 为 1920 × 1080、48.415 秒、12,543,764 字节的 CC BY 4.0 视频文件。
- 该画面最适合作为“主工作台 / 样品制备”主视图，因为机械臂、容器和实验设备同时清晰可见。
- 建议署名为“Robot arm R1 operation of the autonomous laboratory, Nathan J. Szymanski et al., CC BY 4.0, via Wikimedia Commons, cropped and looped for the demo”。

### 2. 俯视或台面辅助机位 - R2 坩埚转移机械臂

- [来源页面：Robot arm R2 operation of the autonomous laboratory](https://commons.wikimedia.org/wiki/File:Robot_arm_R2_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_(moving_crucibles).webm) 记录了同一自主材料实验室中 R2 机械臂转移坩埚的真实操作。
- [原始 WebM](https://upload.wikimedia.org/wikipedia/commons/1/18/Robot_arm_R2_operation_of_the_autonomous_laboratory_for_the_accelerated_synthesis_of_novel_materials_%28moving_crucibles%29.webm) 为 640 × 360、87.426 秒、5,764,978 字节的 CC BY 4.0 视频文件。
- 该画面适合裁成第二机位的工作区局部，并标为“坩埚转移台”而不是将外部拍摄画面误称为真实机载俯视相机。
- 建议署名为“Robot arm R2 operation of the autonomous laboratory, Nathan J. Szymanski et al., CC BY 4.0, via Wikimedia Commons, cropped and looped for the demo”。

### 3. 近景工作单元 - R3 UR5e 与 X 射线衍射仪

- [来源页面：Robot arm R3 (UR5e) retrieving powder samples](https://commons.wikimedia.org/wiki/File:Robot_arm_R3_(UR5e)_retrieving_powder_samples_(post-annealing)_and_cooperating_with_an_Aeris_X-ray_diffractometer_for_their_characterization_(autonomous_lab).webm) 展示了 R3 UR5e 机械臂取回退火后的粉末样品并与 Aeris X 射线衍射仪协作的真实工作单元。
- [原始 WebM](https://upload.wikimedia.org/wikipedia/commons/e/ef/Robot_arm_R3_%28UR5e%29_retrieving_powder_samples_%28post-annealing%29_and_cooperating_with_an_Aeris_X-ray_diffractometer_for_their_characterization_%28autonomous_lab%29.webm) 为 1920 × 1080、295.995 秒、105,423,552 字节的 CC BY 4.0 视频文件。
- 该条目作为近景“精密操作单元”接入，原文件较大，因此当前版本只保留一个无转场的短片段并转为 GIF。
- 建议署名为“Robot arm R3 (UR5e) autonomous laboratory operation, Nathan J. Szymanski et al., CC BY 4.0, via Wikimedia Commons, cropped and looped for the demo”。

### 4. 环境广角 - JPL 的 Perseverance 工程测试车库

- [来源页面：Twin of NASA’s Perseverance Mars Rover Now on the Move](https://images.nasa.gov/details/JPL-20201006-M2020f-0001-Twin%20Rover%20Gets%20to%20Work) 展示 JPL 的全尺寸 Perseverance 工程测试车在室内首次行驶和实验车库环境。
- [原始移动版 MP4](https://images-assets.nasa.gov/video/JPL-20201006-M2020f-0001-Twin%20Rover%20Gets%20to%20Work/JPL-20201006-M2020f-0001-Twin%20Rover%20Gets%20to%20Work~mobile.mp4) 为 5,825,223 字节，来源元数据显示可取得最高 3840 × 2160 的母版变体。
- 该画面最适合作为“环境广角 / 试验场”辅助视图，因为来源说明明确测试车在 JPL 车库内工作。
- 建议以“NASA/JPL-Caltech footage, edited and looped for demonstration”署名，并且不将 NASA 标识另作本项目品牌元素或使用任何暗示 NASA 支持本项目的表述。

## 已核验的替代素材

- [RASSOR Testing - June 2019 的来源页面](https://images.nasa.gov/details/KSC-20190605-MH-GEB01_0001-RASSOR_testing_B-roll_and_photos-3222817) 和 [8,470,542 字节移动版 MP4](https://images-assets.nasa.gov/video/KSC-20190605-MH-GEB01_0001-RASSOR_testing_B-roll_and_photos-3222817/KSC-20190605-MH-GEB01_0001-RASSOR_testing_B-roll_and_photos-3222817~mobile.mp4) 是 3 分 12 秒、母版 3840 × 2160 的 NASA Swamp Works 机器人测试素材，适合需要更强机械运动的主机位备选。
- [How NASA’s Perseverance Rover Takes a Selfie 的来源页面](https://images.nasa.gov/details/JPL-20210625-M2020f-0001-Taking%20a%20Selfie%20on%20Mars%20UHD) 和 [6,042,808 字节移动版 MP4](https://images-assets.nasa.gov/video/JPL-20210625-M2020f-0001-Taking%20a%20Selfie%20on%20Mars%20UHD/JPL-20210625-M2020f-0001-Taking%20a%20Selfie%20on%20Mars%20UHD~mobile.mp4) 直接包含由机器人导航相机拍到的机械臂运动，母版为 1920 × 1080，适合真正的机器人视角备选。
- [Robonaut 2 的来源页面](https://images.nasa.gov/details/ksc_082710_robonaut) 和 [11,310,521 字节移动版 MP4](https://images-assets.nasa.gov/video/ksc_082710_robonaut/ksc_082710_robonaut~mobile.mp4) 展示了 NASA 实验室中具备手指、传感器和相机的 Robonaut 2，可在需要人形机器人近景时替换第四机位。
- [手作 Arduino 机械臂的来源页面](https://commons.wikimedia.org/wiki/File:Hand-made_robotic_arm_with_Arduino.webm) 和 [5,983,488 字节、1920 × 1080、22.386 秒的原始 WebM](https://upload.wikimedia.org/wikipedia/commons/9/9c/Hand-made_robotic_arm_with_Arduino.webm) 采用 CC BY-SA 4.0 授权，因其需要以相同授权条件传播改编内容且视觉质感较弱，只应作为非主推桌面机械臂备选。

## 不推荐直接采用的素材

- [Mixkit 的 Robotic arm in a factory](https://mixkit.co/free-stock-video/robotic-arm-in-a-factory-20970/) 虽有 [2,112,672 字节的 720p MP4](https://assets.mixkit.co/videos/20970/20970-720.mp4)，但该页面将免费 720p 下载标为 Personal Use，不能安全地放入公开仓库或后续公开部署。

## 已采用的接入处理

- 每条原始视频均已裁成可循环的 5 秒动图，并作为受版本控制的本地派生媒体文件随应用分发。
- 派生后的 CC BY 4.0 素材在本文件和模块内保留来源及改动说明，而 NASA 素材以来源署名和无背书方式处理。
- 应用不在运行时请求外部媒体源，因此本机演示不依赖网络连接。

## 来源关联

- R1、R2 和 R3 条目都对应 [Nature 论文 s41586-023-06734-w](https://doi.org/10.1038/s41586-023-06734-w) 所述的自主材料合成实验室，并由 Commons 条目以 CC BY 4.0 提供。
