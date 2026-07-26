# Skill 展示模块上游来源调研

调研快照：2026-07-26T12:34:29Z。

## 结论

首期展示目录应以 [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) 为唯一内容主源。
该仓库在快照时有 31,800 stars、3,162 forks，未归档，最后推送于 2026-07-26T03:37:07Z，最新正式发布为 [v2.55.0](https://github.com/K-Dense-AI/scientific-agent-skills/releases/tag/v2.55.0)，发布于 2026-07-24T17:59:25Z。
上游 README 列出 150 个科学和研究技能，覆盖数据库、文献、研究方法、生命科学、化学材料、实验自动化与量子计算，足以支撑高密度的可信展示目录。
展示模块应保存本地的名称、中文摘要、标签、上游链接、来源组织、许可和静态指标，不应自动下载、安装或执行任何上游 skill。

## 许可与呈现边界

K-Dense 仓库根许可证为 [MIT License](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md)。
如果将上游 `SKILL.md` 的实质内容复制到本仓库，必须随副本保留 K-Dense 的版权与 MIT 许可声明。
首期仅使用自行撰写的中文摘要、技能名称和可点击的上游来源链接，仍应在详情页显示“Source: K-Dense-AI/scientific-agent-skills, MIT”。
不要把 README 明确标注为 Anthropic 维护且另附 `LICENSE.txt` 的 `docx`、`pdf`、`pptx`、`xlsx` 四项混入 K-Dense 的统一 MIT 迁移批次。
部分技能面向第三方包时，其包许可证独立存在，例如 RDKit 为 BSD-3-Clause、Scanpy 为 BSD-3-Clause、Qiskit 为 Apache-2.0，但这些限制不影响只展示本地元数据卡片。
上游也明确提醒 skill 可影响代理行为并执行代码，因此所有“安装”入口在本产品当前阶段都应是非执行的外链或禁用状态。

## 建议首批 15 张展示卡

以下名称和能力范围均来自上游 [技能索引](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/docs/skills.md) 与各自 `SKILL.md`。

| 上游 skill | 展示名称 | 分类标签 | 展示摘要 | 上游定义 |
| --- | --- | --- | --- | --- |
| `database-lookup` | Scientific Database Lookup | 数据库 | 面向 78 个公共数据库的可复现检索与来源追溯。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/database-lookup/SKILL.md) |
| `paper-lookup` | Paper Lookup | 文献检索 | 在 10 个学术 API 中检索论文、引用与开放全文。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/paper-lookup/SKILL.md) |
| `research-lookup` | Research Evidence Lookup | 证据研究 | 为研究简报或论文组织可核验的文献证据包。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/research-lookup/SKILL.md) |
| `literature-review` | Literature Review | 文献综述 | 跨学术数据库完成系统综述、证据综合与引用核验。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/literature-review/SKILL.md) |
| `citation-management` | Citation Management | 科学写作 | 检索、校验并生成 DOI、PMID 与 BibTeX 引文。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/citation-management/SKILL.md) |
| `hypothesis-generation` | Hypothesis Generation | 研究方法 | 将观察转化为可证伪的假设、对立解释和分析计划。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/hypothesis-generation/SKILL.md) |
| `experimental-design` | Experimental Design | 实验设计 | 支持随机化、区组、因子设计与避免伪重复。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/experimental-design/SKILL.md) |
| `statistical-analysis` | Statistical Analysis | 数据分析 | 覆盖检验选择、假设检查、效应量与结果报告。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/statistical-analysis/SKILL.md) |
| `scientific-writing` | Scientific Writing | 科学写作 | 围绕证据溯源、报告规范和作者责任起草科研文本。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-writing/SKILL.md) |
| `scientific-visualization` | Scientific Visualization | 数据可视化 | 产出并审查诚实、无障碍、可发表的科学图表。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md) |
| `scanpy` | Single-cell RNA-seq | 生物信息学 | 覆盖单细胞 RNA 测序的质控、降维、聚类与差异分析。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scanpy/SKILL.md) |
| `rdkit` | Cheminformatics Toolkit | 药物发现 | 用分子描述符、指纹、子结构与反应能力支持化学信息学任务。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/rdkit/SKILL.md) |
| `pymatgen` | Materials Structure Analysis | 材料科学 | 分析晶体结构、相图与计算材料数据。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/pymatgen/SKILL.md) |
| `opentrons-integration` | Laboratory Automation | 实验自动化 | 编写、模拟和排查 Flex 与 OT-2 液体处理协议。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/opentrons-integration/SKILL.md) |
| `qiskit` | Quantum Computing | 量子计算 | 构建、模拟、编译和运行量子电路。 | [SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/qiskit/SKILL.md) |

## 备选来源

以下是同一 GitHub 搜索快照中高星、近期活跃且许可证清晰的补充候选。
这些来源适合后续补充“开发者工具”或“官方生态”分区，不建议与首期 K-Dense 科学目录混排。

| 仓库 | 快照 stars | 许可 | 最近推送 | 建议用途 | 来源 |
| --- | ---: | --- | --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | 261,376 | MIT | 2026-07-24T21:21:36Z | 高质量开发流程与工程实践卡片。 | [GitHub API](https://api.github.com/repos/obra/superpowers) |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | 80,423 | MIT | 2026-07-26T02:22:17Z | 生产级编码代理的工程技能。 | [GitHub Search API](https://api.github.com/search/repositories?q=%22agent+skills%22+stars%3A%3E10000%26sort%3Dstars%26order%3Ddesc%26per_page%3D30) |
| [github/awesome-copilot](https://github.com/github/awesome-copilot) | 37,049 | MIT | 2026-07-25T21:02:48Z | 官方社区贡献的 instructions、agents 与 skills 索引。 | [GitHub API](https://api.github.com/repos/github/awesome-copilot) |
| [google/skills](https://github.com/google/skills) | 15,261 | Apache-2.0 | 2026-07-24T22:43:18Z | Google 产品与技术的官方 Agent Skills。 | [GitHub Search API](https://api.github.com/search/repositories?q=%22agent+skills%22+stars%3A%3E10000%26sort%3Dstars%26order%3Ddesc%26per_page%3D30) |

`anthropics/skills`、`openai/skills` 与 `ComposioHQ/awesome-claude-skills` 的 GitHub 仓库 API 快照未声明仓库级许可证，因此不作为可复制内容的首批来源。
若未来只展示外链和仓库事实，可以单独评估它们，但不要复制名称以外的内容，直至逐项确认其许可。

## 实现建议

首批直接内置上表 15 张卡片，并在模块头部声明“Scientific collection · sourced from K-Dense · MIT”。
字段建议为 `id`、`name`、`summary`、`categories`、`sourceUrl`、`sourceRepository`、`license`、`verifiedAt`、`stars`、`downloads`、`views` 与 `official`。
下载量、浏览量和评分属于展示型种子数据，必须与上游 stars 分离，并命名为模拟指标，避免暗示来自 GitHub 的真实统计。
后续真正支持安装前，应固定到发布 tag 或 commit、重做许可证和安全扫描、人工审阅 `SKILL.md` 以及其脚本和依赖项。

## 一手来源

- [K-Dense 仓库元数据](https://api.github.com/repos/K-Dense-AI/scientific-agent-skills)。
- [K-Dense README](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/README.md)。
- [K-Dense 技能索引](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/docs/skills.md)。
- [K-Dense MIT License](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/LICENSE.md)。
- [K-Dense v2.55.0 release](https://github.com/K-Dense-AI/scientific-agent-skills/releases/tag/v2.55.0)。
- [GitHub GitHub API repository schema](https://docs.github.com/rest/repos/repos#get-a-repository)。
