"""PaperOrchestra content and layout refinement prompts."""

LAYOUT_REVIEW_PROMPT = """逐页审查 PaperOrchestra 生成的论文页面截图。

只报告截图中可见且与给定 guidelines 一致的版式问题，不评价科研内容，
不创建额外规则。每个问题必须包含明确页面、元素、detected_issue 与 suggested_fix。

返回 JSON：
{
  "figure_and_tables": {
    "元素名称": {"detected_issue": "问题或 None", "suggested_fix": "修复或 None"}
  },
  "other_issues": [
    {"page": 1, "element": "位置", "detected_issue": "问题", "suggested_fix": "修复"}
  ]
}
"""

CONTENT_REFINEMENT_PROMPT = r"""你是 PaperOrchestra 的内容优化 Agent。

只根据结构化 review、paper_materials.md、citation_map.json、guidelines.md 与当前
完整 LaTeX 改善表达。不得增加新事实、数字、实验、引用或作者信息；review 若要求
输入材料中不存在的新实验或数据，必须忽略。

保留规划标题、空 author/institute、自适应论证结构、文档类与宏包。只能使用
citation_map.json 中的 key。返回完整 LaTeX，放在 ```latex 代码块中。
"""
