import {
  FileSearch,
  FileText,
  Quote,
  Send,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

type PaperToolTab = "search" | "reading" | "citation";

const PAPER_TABS: Array<{
  id: PaperToolTab;
  label: string;
  caption: string;
  icon: LucideIcon;
  title: string;
  body: string;
}> = [
  {
    id: "search",
    label: "论文检索",
    caption: "研究问题",
    icon: FileSearch,
    title: "论文检索对话",
    body: "文献来源与研究报告方案仍在评估中。此处暂时不提交问题，也不会调用外部服务。",
  },
  {
    id: "reading",
    label: "论文精读",
    caption: "近距离阅读",
    icon: FileText,
    title: "论文精读即将开放",
    body: "后续将在选定论文后提供精读、批注与证据回看。当前只保留模块入口。",
  },
  {
    id: "citation",
    label: "引文核验",
    caption: "引用检查",
    icon: Quote,
    title: "引文核验即将开放",
    body: "后续将在这里核对论文观点与参考文献。当前不会读取、修改或保存任何引文。",
  },
];

const PAPER_DOMAINS = ["全部领域", "AI Scientist", "海水淡化", "燃气轮机", "反渗透", "具身智能"];

const PLACEHOLDER_CARDS = [
  { domain: "AI Scientist", index: "01" },
  { domain: "海水淡化", index: "02" },
  { domain: "具身智能", index: "03" },
];

function SearchPlaceholder() {
  return (
    <div className="paper-query-placeholder">
      <div className="paper-placeholder-intro">
        <span className="paper-stage-mark" aria-hidden="true">
          <FileSearch />
        </span>
        <div>
          <h2>论文检索对话</h2>
          <p>文献来源与研究报告方案仍在评估中。此处暂时不提交问题，也不会调用外部服务。</p>
        </div>
      </div>

      <label className="paper-question-field">
        <span>研究问题</span>
        <textarea
          disabled
          rows={3}
          placeholder="例如：反渗透膜污染缓解的最新证据是什么？"
          aria-label="论文检索研究问题，暂未开放"
        />
      </label>

      <div className="paper-composer-footer">
        <span>文献来源待定</span>
        <button type="button" disabled>
          <span>暂未开放</span>
          <Send aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export function PaperTools() {
  const [activeTab, setActiveTab] = useState<PaperToolTab>("search");
  const [activeDomain, setActiveDomain] = useState(PAPER_DOMAINS[0]);
  const active = PAPER_TABS.find((tab) => tab.id === activeTab) ?? PAPER_TABS[0];
  const visibleCards = activeDomain === PAPER_DOMAINS[0]
    ? PLACEHOLDER_CARDS
    : PLACEHOLDER_CARDS.map((card) => ({ ...card, domain: activeDomain }));
  const ActiveIcon = active.icon;

  return (
    <section className="paper-tools" aria-label="论文工具">
      <div className="paper-tool-tabs" role="tablist" aria-label="论文工具子模块">
        {PAPER_TABS.map((tab) => {
          const TabIcon = tab.icon;
          const isActive = tab.id === activeTab;
          return (
            <button
              type="button"
              role="tab"
              key={tab.id}
              id={`paper-tab-${tab.id}`}
              aria-controls={`paper-panel-${tab.id}`}
              aria-selected={isActive}
              className={isActive ? "is-active" : undefined}
              onClick={() => setActiveTab(tab.id)}
            >
              <TabIcon aria-hidden="true" />
              <span>
                <strong>{tab.label}</strong>
                <small>{tab.caption}</small>
              </span>
            </button>
          );
        })}
      </div>

      <section
        className="paper-tool-stage"
        role="tabpanel"
        id={`paper-panel-${active.id}`}
        aria-labelledby={`paper-tab-${active.id}`}
      >
        <div className="paper-stage-heading">
          <span>{active.label} / PLACEHOLDER</span>
          <span>功能暂未开放</span>
        </div>
        {active.id === "search" ? (
          <SearchPlaceholder />
        ) : (
          <div className="paper-tool-empty">
            <span className="paper-stage-mark" aria-hidden="true">
              <ActiveIcon />
            </span>
            <div>
              <h2>{active.title}</h2>
              <p>{active.body}</p>
            </div>
          </div>
        )}
      </section>

      <section className="high-interest-papers" aria-labelledby="high-interest-title">
        <header className="high-interest-heading">
          <div>
            <p className="section-label">HIGH-INTEREST PAPERS / PLACEHOLDER</p>
            <h2 id="high-interest-title">高热论文</h2>
            <p>保留每日推送的展示位置，当前卡片不代表真实论文，也不提供跳转。</p>
          </div>
          <span>推送待接入</span>
        </header>

        <div className="paper-domain-filters" aria-label="高热论文领域筛选">
          {PAPER_DOMAINS.map((domain) => (
            <button
              type="button"
              key={domain}
              className={domain === activeDomain ? "is-active" : undefined}
              aria-pressed={domain === activeDomain}
              onClick={() => setActiveDomain(domain)}
            >
              {domain}
            </button>
          ))}
        </div>

        <div className="high-interest-grid" aria-label={`${activeDomain} 高热论文占位卡片`}>
          {visibleCards.map((card) => (
            <article className="high-interest-card" key={card.index}>
              <div className="high-interest-card-topline">
                <span>{card.domain}</span>
                <span>推送 / {card.index}</span>
              </div>
              <h3>每日论文推送占位</h3>
              <p>等待稳定的论文来源与自动推送策略确定后更新。</p>
              <footer>
                <span>未接入来源</span>
                <Sparkles aria-hidden="true" />
              </footer>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
