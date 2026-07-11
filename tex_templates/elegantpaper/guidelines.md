# Research Narrative 写作约束

本目录的 `template.tex` 是 PaperOrchestra 唯一可重写的 ElegantPaper 入口。上游示例 `elegantpaper-cn.tex` 只用于说明模板能力，不得作为论文原材料。

## 内容约束

- 默认使用中文。模型名、代码标识符、数据集名、原论文标题和必须保真的术语可以保留原语言。
- 论文标题必须逐字使用 Selected Research Candidate 执行方法的 `title`。
- 作者、机构和联系方式保持为空，除非输入材料中存在明确、权威的值。
- 不得推断、补全或润色为不存在的科研事实。
- 只能使用 `citation_map.json` 批准的 citation key，不得创建、搜索或修复引用。
- 只能使用 `figures/info.json` 登记的图片，不得生成或替换实验图片。

## 结构约束

摘要位于正文之前。正文顶层章节及顺序固定为：

1. 引言
2. 相关工作
3. 方法
4. 实验
5. 研究过程
6. 复现指南
7. 局限性与适用边界
8. 结论

可以增加二级及更深层级的小节，但不得重命名、删除或调整顶层章节顺序。

## 过程披露

`研究过程` 必须完整披露 `candidate_selection.json` 中记录的轮次回退、指标排除、模型主观判断、指标并列和随机选择。没有明确记录时，不得编造失败尝试、过程修正或人工判断。

## LaTeX 与版式

- 保留 ElegantPaper 文档类、中文模式、Biber 后端和 `\addbibresource{references.bib}`。
- 不得添加依赖外部网络或未声明字体的宏包。
- 图片路径使用写作工作区内的相对路径。
- 最终文档必须通过 XeLaTeX + Biber 编译。
