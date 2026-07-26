export const SKILL_CATEGORIES = [
  "全部",
  "证据与写作",
  "研究方法",
  "生命与药物",
  "计算与实验",
] as const;

export type SkillCategory = (typeof SKILL_CATEGORIES)[number];

export type SkillIconName = "database" | "file-search" | "book-open" | "quote" | "pen" | "flask" | "chart" | "dna" | "molecule" | "boxes" | "bot" | "atom";

export type SkillCatalogEntry = {
  id: string;
  name: string;
  chineseName: string;
  summary: string;
  category: Exclude<SkillCategory, "全部">;
  tags: string[];
  icon: SkillIconName;
  sourceUrl: string;
};

export const CATALOG_SOURCE = {
  name: "K-Dense-AI/scientific-agent-skills",
  repositoryUrl: "https://github.com/K-Dense-AI/scientific-agent-skills",
  license: "MIT",
  stars: "31.8k",
  snapshot: "2026-07-26",
  upstreamTotal: 150,
} as const;

const skillSourceUrl = (skillId: string) =>
  `https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/${skillId}/SKILL.md`;

export const SKILL_CATALOG: SkillCatalogEntry[] = [
  {
    id: "database-lookup",
    name: "Scientific Database Lookup",
    chineseName: "科学数据库检索",
    summary: "面向公共科学数据库完成可复现检索，并保留来源追溯线索。",
    category: "证据与写作",
    tags: ["公共数据库", "来源追溯", "多源检索"],
    icon: "database",
    sourceUrl: skillSourceUrl("database-lookup"),
  },
  {
    id: "paper-lookup",
    name: "Paper Lookup",
    chineseName: "论文与引文检索",
    summary: "在学术 API 中检索论文、引文关系与可获得的开放全文。",
    category: "证据与写作",
    tags: ["论文检索", "引用网络", "开放全文"],
    icon: "file-search",
    sourceUrl: skillSourceUrl("paper-lookup"),
  },
  {
    id: "research-lookup",
    name: "Research Evidence Lookup",
    chineseName: "研究证据定位",
    summary: "为研究简报或论文组织可核验的文献证据包与出处。",
    category: "证据与写作",
    tags: ["证据包", "研究简报", "核验"],
    icon: "book-open",
    sourceUrl: skillSourceUrl("research-lookup"),
  },
  {
    id: "literature-review",
    name: "Literature Review",
    chineseName: "系统文献综述",
    summary: "跨学术数据库开展综述、证据综合与引用核验工作流。",
    category: "证据与写作",
    tags: ["系统综述", "证据综合", "引用核验"],
    icon: "book-open",
    sourceUrl: skillSourceUrl("literature-review"),
  },
  {
    id: "citation-management",
    name: "Citation Management",
    chineseName: "引文管理",
    summary: "检索、校验并生成 DOI、PMID 与 BibTeX 引文记录。",
    category: "证据与写作",
    tags: ["DOI", "PMID", "BibTeX"],
    icon: "quote",
    sourceUrl: skillSourceUrl("citation-management"),
  },
  {
    id: "scientific-writing",
    name: "Scientific Writing",
    chineseName: "科学写作",
    summary: "围绕证据溯源、报告规范和作者责任起草科研文本。",
    category: "证据与写作",
    tags: ["科研写作", "报告规范", "证据溯源"],
    icon: "pen",
    sourceUrl: skillSourceUrl("scientific-writing"),
  },
  {
    id: "hypothesis-generation",
    name: "Hypothesis Generation",
    chineseName: "假设生成",
    summary: "将观察转化为可证伪的假设、对立解释与分析计划。",
    category: "研究方法",
    tags: ["可证伪", "对立解释", "分析计划"],
    icon: "flask",
    sourceUrl: skillSourceUrl("hypothesis-generation"),
  },
  {
    id: "experimental-design",
    name: "Experimental Design",
    chineseName: "实验设计",
    summary: "支持随机化、区组、因子设计，并帮助规避伪重复。",
    category: "研究方法",
    tags: ["随机化", "区组", "因子设计"],
    icon: "flask",
    sourceUrl: skillSourceUrl("experimental-design"),
  },
  {
    id: "statistical-analysis",
    name: "Statistical Analysis",
    chineseName: "统计分析",
    summary: "覆盖检验选择、假设检查、效应量与结果报告。",
    category: "研究方法",
    tags: ["假设检查", "效应量", "结果报告"],
    icon: "chart",
    sourceUrl: skillSourceUrl("statistical-analysis"),
  },
  {
    id: "scientific-visualization",
    name: "Scientific Visualization",
    chineseName: "科学可视化",
    summary: "产出并审查诚实、无障碍、可发表的科学图表。",
    category: "研究方法",
    tags: ["科学图表", "无障碍", "可发表"],
    icon: "chart",
    sourceUrl: skillSourceUrl("scientific-visualization"),
  },
  {
    id: "scanpy",
    name: "Single-cell RNA-seq",
    chineseName: "单细胞 RNA 测序",
    summary: "覆盖单细胞 RNA 测序的质控、降维、聚类与差异分析。",
    category: "生命与药物",
    tags: ["Scanpy", "单细胞", "差异分析"],
    icon: "dna",
    sourceUrl: skillSourceUrl("scanpy"),
  },
  {
    id: "rdkit",
    name: "Cheminformatics Toolkit",
    chineseName: "化学信息学工具箱",
    summary: "用分子描述符、指纹、子结构与反应能力支持化学信息任务。",
    category: "生命与药物",
    tags: ["RDKit", "分子描述符", "药物发现"],
    icon: "molecule",
    sourceUrl: skillSourceUrl("rdkit"),
  },
  {
    id: "pymatgen",
    name: "Materials Structure Analysis",
    chineseName: "材料结构分析",
    summary: "分析晶体结构、相图与计算材料数据。",
    category: "计算与实验",
    tags: ["Pymatgen", "晶体结构", "相图"],
    icon: "boxes",
    sourceUrl: skillSourceUrl("pymatgen"),
  },
  {
    id: "opentrons-integration",
    name: "Laboratory Automation",
    chineseName: "实验室自动化",
    summary: "编写、模拟和排查 Flex 与 OT-2 液体处理协议。",
    category: "计算与实验",
    tags: ["Opentrons", "液体处理", "协议模拟"],
    icon: "bot",
    sourceUrl: skillSourceUrl("opentrons-integration"),
  },
  {
    id: "qiskit",
    name: "Quantum Computing",
    chineseName: "量子计算",
    summary: "构建、模拟、编译和运行量子电路。",
    category: "计算与实验",
    tags: ["Qiskit", "量子电路", "模拟"],
    icon: "atom",
    sourceUrl: skillSourceUrl("qiskit"),
  },
];
