import {
  Atom,
  Bot,
  BookOpenCheck,
  Boxes,
  ChartNoAxesCombined,
  Database,
  Dna,
  ExternalLink,
  FileSearch,
  FlaskConical,
  PenLine,
  Quote,
  Search,
  TestTubeDiagonal,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import {
  CATALOG_SOURCE,
  SKILL_CATALOG,
  SKILL_CATEGORIES,
  type SkillCategory,
  type SkillIconName,
} from "./skillCatalogData";

const SKILL_ICONS: Record<SkillIconName, LucideIcon> = {
  database: Database,
  "file-search": FileSearch,
  "book-open": BookOpenCheck,
  quote: Quote,
  pen: PenLine,
  flask: FlaskConical,
  chart: ChartNoAxesCombined,
  dna: Dna,
  molecule: TestTubeDiagonal,
  boxes: Boxes,
  bot: Bot,
  atom: Atom,
};

function matchesQuery(value: string, query: string) {
  return value.toLocaleLowerCase().includes(query.toLocaleLowerCase());
}

export function SkillCatalog() {
  const [activeCategory, setActiveCategory] = useState<SkillCategory>("全部");
  const [query, setQuery] = useState("");

  const visibleSkills = useMemo(() => SKILL_CATALOG.filter((skill) => {
    const isInCategory = activeCategory === "全部" || skill.category === activeCategory;
    const searchable = [skill.name, skill.chineseName, skill.summary, skill.tags.join(" ")].join(" ");

    return isInCategory && matchesQuery(searchable, query.trim());
  }), [activeCategory, query]);

  return (
    <section className="skill-catalog" aria-labelledby="skill-catalog-title">
      <header className="skill-catalog-heading">
        <div>
          <p className="section-label">CURATED GITHUB SKILLS</p>
          <h1 id="skill-catalog-title">研究 Skill 目录</h1>
          <p>
            从公开上游筛选的研究能力索引，用于工作区展示与能力发现。
            每张卡保留原始定义入口，当前不会写入、安装或运行任何外部 skill。
          </p>
        </div>
        <aside className="skill-catalog-disclosure" aria-label="目录来源与状态">
          <span>展示目录</span>
          <strong>仅供发现，不改变运行时</strong>
          <a href={CATALOG_SOURCE.repositoryUrl} target="_blank" rel="noreferrer">
            {CATALOG_SOURCE.name}
            <ExternalLink aria-hidden="true" />
          </a>
        </aside>
      </header>

      <div className="skill-catalog-controls">
        <label className="skill-search-field">
          <Search aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索技能、领域或方法……"
            aria-label="搜索技能、领域或方法"
            autoComplete="off"
          />
        </label>

        <div className="skill-category-filters" aria-label="Skill 领域筛选">
          {SKILL_CATEGORIES.map((category) => (
            <button
              type="button"
              key={category}
              className={activeCategory === category ? "is-active" : undefined}
              aria-pressed={activeCategory === category}
              onClick={() => setActiveCategory(category)}
            >
              {category}
            </button>
          ))}
        </div>
      </div>

      <div className="skill-catalog-status" aria-live="polite">
        <p>显示 <strong>{visibleSkills.length}</strong> / {SKILL_CATALOG.length} 个精选条目</p>
        <p>
          上游 {CATALOG_SOURCE.upstreamTotal} 个 skills · {CATALOG_SOURCE.license} · {CATALOG_SOURCE.stars} stars 快照于 {CATALOG_SOURCE.snapshot}
        </p>
      </div>

      {visibleSkills.length > 0 ? (
        <div className="skill-grid" aria-label="研究 Skill 目录条目">
          {visibleSkills.map((skill) => {
            const SkillIcon = SKILL_ICONS[skill.icon];

            return (
              <article className="skill-card" key={skill.id}>
                <header className="skill-card-header">
                  <span className="skill-card-icon" aria-hidden="true"><SkillIcon /></span>
                  <div>
                    <p>{skill.category}</p>
                    <h2>{skill.name}</h2>
                    <span>{skill.chineseName}</span>
                  </div>
                </header>

                <p className="skill-card-summary">{skill.summary}</p>

                <footer className="skill-card-footer">
                  <div className="skill-card-tags" aria-label={`${skill.name} 标签`}>
                    {skill.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                  <div className="skill-card-source">
                    <span>{CATALOG_SOURCE.license} · 上游定义</span>
                    <a href={skill.sourceUrl} target="_blank" rel="noreferrer" aria-label={`在 GitHub 查看 ${skill.name} 的 SKILL.md`}>查看 SKILL.md <ExternalLink aria-hidden="true" /></a>
                  </div>
                </footer>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="skill-catalog-empty" role="status">
          <Search aria-hidden="true" />
          <p>没有匹配的 Skill。请调整关键词或领域筛选。</p>
        </div>
      )}
    </section>
  );
}
