import {
  Atom,
  FolderKanban,
  MessageCircle,
  Settings,
  Sparkles,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import { SystemSettings } from "./features/settings/SystemSettings";
import { EmbodiedIntelligence } from "./features/embodied/EmbodiedIntelligence";

type ModuleId = "chat" | "embodied" | "skills" | "projects" | "settings";

const MODULES: Array<{
  id: ModuleId;
  label: string;
  caption: string;
  icon: LucideIcon;
}> = [
  { id: "chat", label: "对话", caption: "研究协作", icon: MessageCircle },
  { id: "embodied", label: "具身智能", caption: "实验室实况", icon: Atom },
  { id: "skills", label: "Skill 管理", caption: "能力编排", icon: WandSparkles },
  { id: "projects", label: "课题空间", caption: "研究现场", icon: FolderKanban },
  { id: "settings", label: "系统设置", caption: "工作区配置", icon: Settings },
];

const PLACEHOLDER_COPY: Record<Exclude<ModuleId, "embodied" | "projects" | "settings">, { title: string; body: string }> = {
  chat: {
    title: "把研究变成一段持续的对话。",
    body: "这里将承接课题上下文、追问与阶段性结论。初版先保留模块位置，不连接模型或历史记录。",
  },
  skills: {
    title: "能力应当看得见，也应当可组合。",
    body: "这里将用于浏览、启用与编排研究技能。初版先呈现工作区结构，不修改运行时配置。",
  },
};

function ProjectSpace() {
  return (
    <section className="project-space" aria-labelledby="project-title">
      <div className="project-hero">
        <div className="project-intro reveal" style={{ "--i": 0 } as React.CSSProperties}>
          <div className="project-kicker">
            <span>当前课题</span>
            <span className="project-kicker-rule" aria-hidden="true" />
            <span>研究中</span>
          </div>
          <h1 id="project-title">让长上下文推理的<br />证据可追溯。</h1>
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
          <span className="artifact-count">02</span>
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
        </div>
      </div>
    </section>
  );
}

function PlaceholderModule({ module }: { module: Exclude<ModuleId, "embodied" | "projects" | "settings"> }) {
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

export default function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>("projects");
  const active = MODULES.find((entry) => entry.id === activeModule) ?? MODULES[0];

  const selectModule = (module: ModuleId) => {
    setActiveModule(module);
  };

  return (
    <div className={`workspace workspace--${activeModule}`}>
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
          <span>INTRANET / 01</span>
          <p>研究仍在现场。</p>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="workspace-header">
          <div>
            <p className="workspace-location">工作区 / {active.label}</p>
            <span>{activeModule === "settings" ? "配置与运行控制" : "初版交互演示"}</span>
          </div>
          <div className="header-status"><i className="status-dot" aria-hidden="true" />内网运行</div>
        </header>
        {activeModule === "projects" ? (
          <ProjectSpace />
        ) : activeModule === "settings" ? (
          <SystemSettings />
        ) : activeModule === "embodied" ? (
          <EmbodiedIntelligence />
        ) : (
          <PlaceholderModule module={activeModule} />
        )}
      </main>
    </div>
  );
}
