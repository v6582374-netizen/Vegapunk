import {
  ArrowRight,
  Atom,
  FileText,
  FolderKanban,
  MessageCircle,
  Settings,
  Sparkles,
  WandSparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { SystemSettings } from "./features/settings/SystemSettings";

type ModuleId = "chat" | "skills" | "projects" | "settings";

const MODULES: Array<{
  id: ModuleId;
  label: string;
  caption: string;
  icon: LucideIcon;
}> = [
  { id: "chat", label: "对话", caption: "研究协作", icon: MessageCircle },
  { id: "skills", label: "Skill 管理", caption: "能力编排", icon: WandSparkles },
  { id: "projects", label: "课题空间", caption: "研究现场", icon: FolderKanban },
  { id: "settings", label: "系统设置", caption: "工作区配置", icon: Settings },
];

const PLACEHOLDER_COPY: Record<Exclude<ModuleId, "projects" | "settings">, { title: string; body: string }> = {
  chat: {
    title: "把研究变成一段持续的对话。",
    body: "这里将承接课题上下文、追问与阶段性结论。初版先保留模块位置，不连接模型或历史记录。",
  },
  skills: {
    title: "能力应当看得见，也应当可组合。",
    body: "这里将用于浏览、启用与编排研究技能。初版先呈现工作区结构，不修改运行时配置。",
  },
};

function ProjectSpace({
  previewOpen,
  onOpenPreview,
}: {
  previewOpen: boolean;
  onOpenPreview: () => void;
}) {
  return (
    <section className="project-space" aria-labelledby="project-title">
      <div className="project-intro reveal" style={{ "--i": 0 } as React.CSSProperties}>
        <div className="project-kicker">
          <span>当前课题</span>
          <span className="project-kicker-rule" aria-hidden="true" />
          <span>研究中</span>
        </div>
        <h1 id="project-title">让长上下文推理的<br className="preview-title-break" />证据可追溯。</h1>
        <p>
          这是一个用于讨论证据链、检验路径和论文产物的课题空间示例。
          初版只呈现工作台结构，不连接真实研究任务。
        </p>
        <div className="project-meta" aria-label="课题状态">
          <span><i className="status-dot" aria-hidden="true" />探索阶段</span>
          <span>第 03 轮</span>
          <span>本地工作区</span>
        </div>
      </div>

      <div className="project-ledger reveal" style={{ "--i": 1 } as React.CSSProperties}>
        <div className="ledger-heading">
          <div>
            <p className="section-label">研究脉络</p>
            <h2>从问题到可读的产物。</h2>
          </div>
          <span className="ledger-note">演示状态</span>
        </div>
        <ol className="research-path">
          <li className="is-complete">
            <span className="path-index">01</span>
            <div>
              <strong>研究问题</strong>
              <p>梳理长上下文推理中可验证性不足的来源。</p>
            </div>
          </li>
          <li className="is-active">
            <span className="path-index">02</span>
            <div>
              <strong>证据设计</strong>
              <p>将来源、推理步骤与评估信号放入同一条证据链。</p>
            </div>
          </li>
          <li>
            <span className="path-index">03</span>
            <div>
              <strong>论文产出</strong>
              <p>整理为可预览、可复查的研究论文。</p>
            </div>
          </li>
        </ol>
      </div>

      <div className="artifact-section reveal" style={{ "--i": 2 } as React.CSSProperties}>
        <div className="section-heading">
          <div>
            <p className="section-label">课题产物</p>
            <h2>正在形成的材料。</h2>
          </div>
          <span className="artifact-count">03</span>
        </div>
        <div className="artifact-list">
          <div className="artifact-row">
            <span className="artifact-kind">MD</span>
            <div className="artifact-copy">
              <strong>Evidence map</strong>
              <span>研究证据图谱</span>
            </div>
            <span className="artifact-state">已整理</span>
          </div>
          <div className="artifact-row">
            <span className="artifact-kind">NB</span>
            <div className="artifact-copy">
              <strong>Evaluation notebook</strong>
              <span>评估记录与方法草稿</span>
            </div>
            <span className="artifact-state">进行中</span>
          </div>
          <button
            type="button"
            className={`artifact-row artifact-row-button ${previewOpen ? "is-selected" : ""}`}
            onClick={onOpenPreview}
            aria-pressed={previewOpen}
          >
            <span className="artifact-icon"><FileText aria-hidden="true" /></span>
            <span className="artifact-copy">
              <strong>Traceable Context Reasoning</strong>
              <span>论文草稿 · PDF · 18 页</span>
            </span>
            <span className="artifact-open">预览 <ArrowRight aria-hidden="true" /></span>
          </button>
        </div>
      </div>
    </section>
  );
}

function PlaceholderModule({ module }: { module: Exclude<ModuleId, "projects" | "settings"> }) {
  const copy = PLACEHOLDER_COPY[module];
  const item = MODULES.find((entry) => entry.id === module);
  const PlaceholderIcon = item?.icon ?? Sparkles;

  return (
    <section className="module-placeholder" aria-labelledby="placeholder-title">
      <div className="placeholder-mark reveal" style={{ "--i": 0 } as React.CSSProperties}>
        <PlaceholderIcon aria-hidden="true" />
      </div>
      <p className="section-label reveal" style={{ "--i": 1 } as React.CSSProperties}>{item?.label} / 初版演示</p>
      <h1 id="placeholder-title" className="reveal" style={{ "--i": 2 } as React.CSSProperties}>{copy.title}</h1>
      <p className="placeholder-copy reveal" style={{ "--i": 3 } as React.CSSProperties}>{copy.body}</p>
      <div className="placeholder-note reveal" style={{ "--i": 4 } as React.CSSProperties}>
        <Sparkles aria-hidden="true" />
        <span>模块结构已就位，具体能力将在后续阶段接入。</span>
      </div>
    </section>
  );
}

function ArtifactPreview({ onClose }: { onClose: () => void }) {
  return (
    <aside className="artifact-preview" aria-label="论文 PDF 预览">
      <div className="preview-toolbar">
        <div>
          <p className="section-label">产物预览</p>
          <strong>Paper draft.pdf</strong>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="关闭论文预览">
          <X aria-hidden="true" />
        </button>
      </div>
      <div className="pdf-stage">
        <article className="pdf-sheet" aria-label="论文第一页示意">
          <div className="pdf-running-head">
            <span>VEGAPUNK / RESEARCH NOTE</span>
            <span>01</span>
          </div>
          <h2>Traceable Context Reasoning</h2>
          <p className="pdf-subtitle">A working paper on evidence-preserving long-context inference</p>
          <div className="pdf-authors">
            <span>Vegapunk Research Workspace</span>
            <span>Draft · Local edition</span>
          </div>
          <div className="pdf-rule" />
          <section>
            <h3>Abstract</h3>
            <p>
              Long-context systems often provide an answer without making the path to that answer inspectable.
              This draft frames the missing path as a research object: evidence, transformations, and evaluation signals remain connected.
            </p>
          </section>
          <section>
            <h3>Working proposition</h3>
            <p>
              A useful research interface should keep the question, its supporting material, and its resulting paper in view without treating them as separate systems.
            </p>
          </section>
          <div className="pdf-diagram" aria-hidden="true">
            <span>Context</span>
            <i />
            <span>Evidence</span>
            <i />
            <span>Claim</span>
          </div>
          <p className="pdf-footnote">Preview surface for the initial workspace demo.</p>
        </article>
      </div>
      <div className="preview-footer">
        <span>第 1 / 18 页</span>
        <span>PDF 预览占位</span>
      </div>
    </aside>
  );
}

export default function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>("projects");
  const [previewOpen, setPreviewOpen] = useState(false);
  const active = MODULES.find((entry) => entry.id === activeModule) ?? MODULES[0];

  const selectModule = (module: ModuleId) => {
    setActiveModule(module);
    if (module !== "projects") setPreviewOpen(false);
  };

  return (
    <div className={`workspace ${previewOpen ? "has-preview" : ""}`}>
      <aside className="workspace-sidebar">
        <div className="brand-lockup">
          <span className="brand-mark"><Atom aria-hidden="true" /></span>
          <span>
            <strong>Vegapunk</strong>
            <small>RESEARCH STUDIO</small>
          </span>
        </div>

        <nav className="module-nav" aria-label="工作区模块">
          {MODULES.map((module) => {
            const isActive = activeModule === module.id;
            const ModuleIcon = module.icon;
            return (
              <button
                type="button"
                key={module.id}
                className={isActive ? "is-active" : undefined}
                onClick={() => selectModule(module.id)}
                aria-current={isActive ? "page" : undefined}
                aria-label={module.label}
                title={module.label}
              >
                <span className="module-icon"><ModuleIcon aria-hidden="true" /></span>
                <span className="module-label">
                  <strong>{module.label}</strong>
                  <small>{module.caption}</small>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footnote">
          <span>LOCAL / 01</span>
          <p>研究仍在现场。</p>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="workspace-location">工作区 / {active.label}</p>
            <span>{activeModule === "settings" ? "配置与运行控制" : "初版交互演示"}</span>
          </div>
          <div className="header-status"><i className="status-dot" aria-hidden="true" />本地运行</div>
        </header>
        {activeModule === "projects" ? (
          <ProjectSpace previewOpen={previewOpen} onOpenPreview={() => setPreviewOpen(true)} />
        ) : activeModule === "settings" ? (
          <SystemSettings />
        ) : (
          <PlaceholderModule module={activeModule} />
        )}
      </main>

      {previewOpen ? <ArtifactPreview onClose={() => setPreviewOpen(false)} /> : null}
    </div>
  );
}
