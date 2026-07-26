import {
  ArrowRight,
  Bolt,
  ExternalLink,
  FileSearch,
  FileText,
  Layers3,
  Quote,
  ShieldCheck,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import {
  getPaperCount,
  getPapersForDomain,
  PAPER_DOMAINS,
  PAPERS_PER_PAGE,
  type PaperDomain,
} from "./paperCatalog";

type PaperToolTab = "search" | "reading" | "citation";
type SearchMode = "quick" | "deep";

const PAPER_TABS: Array<{
  id: PaperToolTab;
  label: string;
  icon: LucideIcon;
}> = [
  {
    id: "search",
    label: "论文检索",
    icon: FileSearch,
  },
  {
    id: "reading",
    label: "论文精读",
    icon: FileText,
  },
  {
    id: "citation",
    label: "引文核验",
    icon: Quote,
  },
];

function SearchComposer({
  mode,
  query,
  onModeChange,
  onQueryChange,
}: {
  mode: SearchMode;
  query: string;
  onModeChange: (mode: SearchMode) => void;
  onQueryChange: (query: string) => void;
}) {
  return (
    <div className="paper-dialog paper-search-dialog">
      <label className="paper-search-field">
        <input
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="输入研究主题或搜索要求……"
          aria-label="输入研究主题或搜索要求"
          autoComplete="off"
        />
      </label>

      <div className="paper-search-toolbar">
        <div className="paper-search-modes" role="radiogroup" aria-label="论文检索模式">
          <button
            type="button"
            role="radio"
            aria-checked={mode === "quick"}
            className={mode === "quick" ? "is-active" : undefined}
            onClick={() => onModeChange("quick")}
          >
            <Bolt aria-hidden="true" />
            <span>快速搜索</span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={mode === "deep"}
            className={mode === "deep" ? "is-active" : undefined}
            onClick={() => onModeChange("deep")}
          >
            <Layers3 aria-hidden="true" />
            <span>深度搜索</span>
          </button>
        </div>
        <button type="button" className="paper-primary-action" disabled title="论文检索服务即将接入">
          <span>开始检索</span>
          <ArrowRight aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function ReadingPlaceholder() {
  return (
    <div className="paper-dialog paper-reading-dialog" aria-label="论文精读即将开放">
      <div className="paper-upload-mark" aria-hidden="true">
        <Upload />
      </div>
      <div className="paper-reading-copy">
        <h2>拖入或点击上传 PDF（≤50MB）</h2>
        <p>仅支持单个 .pdf 文件</p>
      </div>
      <div className="paper-pending-actions">
        <button type="button" className="paper-pending-primary" disabled title="论文精读即将开放">
          上传 PDF
        </button>
        <button type="button" className="paper-pending-secondary" disabled title="论文精读即将开放">
          从课题选择
        </button>
      </div>
      <p className="paper-pending-note">论文精读即将开放</p>
    </div>
  );
}

function CitationPlaceholder() {
  return (
    <div className="paper-dialog paper-citation-dialog">
      <span className="paper-citation-mark" aria-hidden="true">
        <ShieldCheck />
      </span>
      <h2>引文核验即将开放</h2>
      <p>后续将在这里核对论文观点、引文与参考文献，不会读取、修改或保存任何引文。</p>
    </div>
  );
}

function HighInterestPapers({
  activeDomain,
  onDomainChange,
}: {
  activeDomain: PaperDomain;
  onDomainChange: (domain: PaperDomain) => void;
}) {
  const [currentPage, setCurrentPage] = useState(0);
  const papers = getPapersForDomain(activeDomain);
  const totalPages = Math.ceil(papers.length / PAPERS_PER_PAGE);
  const startIndex = currentPage * PAPERS_PER_PAGE;
  const visiblePapers = papers.slice(startIndex, startIndex + PAPERS_PER_PAGE);

  function selectDomain(domain: PaperDomain) {
    setCurrentPage(0);
    onDomainChange(domain);
  }

  return (
    <section className="high-interest-papers" aria-labelledby="high-interest-title">
      <header className="high-interest-heading">
        <div>
          <p className="section-label">SOURCE-VERIFIED LITERATURE</p>
          <h2 id="high-interest-title">高热论文</h2>
          <p>按领域整理的可查论文目录，每篇均保留摘要摘录与 DOI 出版页面链接。</p>
        </div>
        <span aria-live="polite">{getPaperCount(activeDomain)} 篇已核验</span>
      </header>

      <div className="paper-domain-filters" aria-label="高热论文领域筛选">
        {PAPER_DOMAINS.map((domain) => (
          <button
            type="button"
            key={domain}
            className={domain === activeDomain ? "is-active" : undefined}
            aria-pressed={domain === activeDomain}
            onClick={() => selectDomain(domain)}
          >
            {domain}
          </button>
        ))}
      </div>

      <div className="high-interest-grid" aria-label={`${activeDomain} 论文目录`}>
        {visiblePapers.map((paper) => (
          <article className="high-interest-card" key={paper.doi}>
            <div className="high-interest-card-topline">
              <span>{paper.domain}</span>
              <FileText aria-hidden="true" />
            </div>
            <h3>
              <a href={paper.url} target="_blank" rel="noreferrer">
                {paper.title}
              </a>
            </h3>
            <p className="paper-record-meta">
              <span>{paper.authors}</span>
              <span aria-hidden="true">·</span>
              <span>{paper.venue}</span>
              <span aria-hidden="true">·</span>
              <span>{paper.year}</span>
            </p>
            <p className="paper-record-abstract">{paper.abstract}</p>
            <footer className="paper-record-footer">
              <div className="paper-record-tags" aria-label="论文标签">
                {paper.tags.slice(0, 2).map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
                {paper.tags.length > 2 ? <span>+{paper.tags.length - 2}</span> : null}
              </div>
              <a
                className="paper-record-link"
                href={paper.url}
                target="_blank"
                rel="noreferrer"
                aria-label={`${paper.title} 的 DOI 出版页面（新窗口打开）`}
              >
                查看 DOI
                <ExternalLink aria-hidden="true" />
              </a>
            </footer>
          </article>
        ))}
      </div>

      <nav className="paper-pagination" aria-label={`${activeDomain} 论文分页`}>
        <button
          type="button"
          onClick={() => setCurrentPage((page) => Math.max(0, page - 1))}
          disabled={currentPage === 0}
        >
          上一页
        </button>
        <p aria-live="polite">
          第 {currentPage + 1} / {totalPages} 页 · 显示 {startIndex + 1}–{startIndex + visiblePapers.length} 条
        </p>
        <button
          type="button"
          onClick={() => setCurrentPage((page) => Math.min(totalPages - 1, page + 1))}
          disabled={currentPage === totalPages - 1}
        >
          下一页
        </button>
      </nav>
    </section>
  );
}

export function PaperTools() {
  const [activeTab, setActiveTab] = useState<PaperToolTab>("search");
  const [searchMode, setSearchMode] = useState<SearchMode>("quick");
  const [query, setQuery] = useState("");
  const [activeDomain, setActiveDomain] = useState<PaperDomain>(PAPER_DOMAINS[0]);
  const active = PAPER_TABS.find((tab) => tab.id === activeTab) ?? PAPER_TABS[0];

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
              <span>{tab.label}</span>
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
        {active.id === "search" ? (
          <SearchComposer
            mode={searchMode}
            query={query}
            onModeChange={setSearchMode}
            onQueryChange={setQuery}
          />
        ) : active.id === "reading" ? (
          <ReadingPlaceholder />
        ) : (
          <CitationPlaceholder />
        )}
      </section>

      <HighInterestPapers activeDomain={activeDomain} onDomainChange={setActiveDomain} />
    </section>
  );
}
