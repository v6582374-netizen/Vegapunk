# Prototype Discovery Preparation intake and conversion flow

Type: prototype
Status: closed
Labels: wayfinder:prototype
Parent: ../map.md
Assignee: Codex
Blocked by: none
Blocks: 08-define-native-desktop-acceptance-and-migration-boundary.md

Prototype artifact: [Native Desktop Discovery Preparation prototype](../prototype/README.md)
Run command: `python3 -m http.server 4178 --directory .scratch/native-desktop-discovery-module/prototype`

## Resolution

采用 C 方案的 Stage Canvas 作为 Native Desktop Discovery Preparation 的 V1 原型方向。

四个并列阶段固定为 Gather、Convert、Review、Run，并保持单一 Preparation、独立文件上传、自由文本、显式转换、可编辑保存和显式 Run gate。

混合 A 方案的绿色完成圆圈作为阶段完成点缀。
某个阶段完成后，在该阶段模块的右上角显示绿色勾选圆圈；未完成阶段保持原有中性样式，不增加额外交互含义。

勾选状态按状态模型推进：完成 Gather 后标记第一阶段，完成转换后标记第二阶段，保存 Formatted Discovery Input 后标记第三阶段，显式启动 Launch 后标记第四阶段。

原型已验证初始、转换后、保存后、Launch 后的完成标记，以及拒绝文件阻断转换和 Run 的状态。
完整三种布局和交互证据保留在 [Native Desktop Discovery Preparation prototype](../prototype/README.md)。

## Question

What concrete Native Desktop page and interaction flow best supports one current Preparation containing multiple individually uploaded files and free-form text, followed by explicit conversion, editable review, and Run gating?
The prototype should replace the current new-session task-card assumption with a standalone Sidebar module surface and expose the states that the product contract must support.
