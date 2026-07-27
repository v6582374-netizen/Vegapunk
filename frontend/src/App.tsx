import {
  Archive,
  Atom,
  Award,
  Box,
  BookOpenText,
  FileText,
  Settings,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useCallback, useState } from "react";

import { EmbodiedIntelligence } from "./features/embodied/EmbodiedIntelligence";
import { AchievementShowcase } from "./features/achievements/AchievementShowcase";
import { DiscoveryPreparation } from "./features/discovery/DiscoveryPreparation";
import {
  OccludedPointCloudSubstrate,
  type MaterialExpressionProfile,
} from "./features/identity/OccludedPointCloudSubstrate";
import { PaperTools } from "./features/papers/PaperTools";
import { SystemSettings } from "./features/settings/SystemSettings";
import { SkillCatalog } from "./features/skills/SkillCatalog";
import {
  SETTINGS_SECTIONS,
  type SettingsSection,
} from "./features/settings/settingsNavigation";

type WorkspaceSpaceId = "collaboration" | "autonomous-discovery";
type ModuleId = "papers" | "embodied" | "simulation" | "skills" | "achievement-upir" | "achievement-pbtwin" | "settings" | "discovery-preparation" | "discovery-launch-archive";

type WorkspaceSubmodule = {
  id: ModuleId;
  label: string;
  icon: LucideIcon;
};

type WorkspaceModule = {
  id: ModuleId;
  label: string;
  caption: string;
  icon: LucideIcon;
  materialProfile: MaterialExpressionProfile;
  submodules?: WorkspaceSubmodule[];
};

type WorkspaceSpace = {
  id: WorkspaceSpaceId;
  label: string;
  modules: WorkspaceModule[];
};

const SPACES: Record<WorkspaceSpaceId, WorkspaceSpace> = {
  collaboration: {
    id: "collaboration",
    label: "协作空间",
    modules: [
      { id: "papers", label: "论文工具", caption: "文献工作台", icon: BookOpenText, materialProfile: "quiet" },
      {
        id: "embodied",
        label: "干湿结合",
        caption: "实验室实况",
        icon: Atom,
        materialProfile: "quiet",
        submodules: [
          { id: "embodied", label: "具身智能", icon: Atom },
          { id: "simulation", label: "物理仿真", icon: Box },
        ],
      },
      { id: "skills", label: "Skill 管理", caption: "能力编排", icon: WandSparkles, materialProfile: "quiet" },
      {
        id: "achievement-upir",
        label: "成果展示",
        caption: "论文陈列",
        icon: Award,
        materialProfile: "exhibition",
        submodules: [
          { id: "achievement-upir", label: "疲劳代理建模", icon: Atom },
          { id: "achievement-pbtwin", label: "双行星预测", icon: BookOpenText },
        ],
      },
      { id: "settings", label: "系统设置", caption: "工作区配置", icon: Settings, materialProfile: "none" },
    ],
  },
  "autonomous-discovery": {
    id: "autonomous-discovery",
    label: "自主发现空间",
    modules: [
      { id: "discovery-preparation", label: "Discovery Preparation", caption: "研究资料准备", icon: FileText, materialProfile: "exhibition" },
      { id: "discovery-launch-archive", label: "Discovery Launch Archive", caption: "运行档案", icon: Archive, materialProfile: "quiet" },
    ],
  },
};

const INITIAL_MODULES: Record<WorkspaceSpaceId, ModuleId> = {
  collaboration: "papers",
  "autonomous-discovery": "discovery-preparation",
};

const PLACEHOLDER_COPY: Record<"skills" | "discovery-launch-archive", { title: string; body: string }> = {
  skills: {
    title: "研究能力的启用与编排",
    body: "在这里浏览、启用与编排研究技能。初版先呈现工作区结构，不修改运行时配置。",
  },
  "discovery-launch-archive": {
    title: "运行记录与原始产物",
    body: "在这里回看正在运行或已完成的 Discovery Launch，并在后续流程中进入对应的原始控制台与运行产物。",
  },
};

function PlaceholderModule({ module }: { module: "skills" | "discovery-launch-archive" }) {
  const copy = PLACEHOLDER_COPY[module];
  const label = module === "skills" ? "Skill 管理" : "Discovery Launch Archive";

  return (
    <section className="module-placeholder" aria-label={label}>
      <h1 id="placeholder-title" className="reveal" style={{ "--i": 0 } as React.CSSProperties}>{copy.title}</h1>
      <p className="placeholder-copy reveal" style={{ "--i": 1 } as React.CSSProperties}>{copy.body}</p>
      <p className="placeholder-note reveal" style={{ "--i": 2 } as React.CSSProperties}>
        模块结构已就位，具体能力将在后续阶段接入。
      </p>
    </section>
  );
}

function SimulationPlaceholder() {
  return (
    <section className="module-placeholder" aria-label="物理仿真">
      <h1>敬请期待</h1>
    </section>
  );
}

export default function App() {
  const [activeSpaceId, setActiveSpaceId] = useState<WorkspaceSpaceId>("collaboration");
  const [selectedModules, setSelectedModules] = useState<Record<WorkspaceSpaceId, ModuleId>>(INITIAL_MODULES);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("providers");
  const [substrateEpoch, setSubstrateEpoch] = useState(0);
  const [discoverySidebarHost, setDiscoverySidebarHost] = useState<HTMLDivElement | null>(null);
  const activeSpace = SPACES[activeSpaceId];
  const activeModuleId = selectedModules[activeSpaceId];
  const activeModule = activeSpace.modules.find((module) => (
    module.id === activeModuleId
    || module.submodules?.some((submodule) => submodule.id === activeModuleId)
  )) ?? activeSpace.modules[0];

  const selectSpace = (spaceId: WorkspaceSpaceId) => {
    if (spaceId === activeSpaceId) {
      return;
    }

    setActiveSpaceId(spaceId);
    setSubstrateEpoch((epoch) => epoch + 1);
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  const selectModule = (module: ModuleId) => {
    if (module === selectedModules[activeSpaceId]) {
      return;
    }

    setSelectedModules((modules) => ({ ...modules, [activeSpaceId]: module }));
    setSubstrateEpoch((epoch) => epoch + 1);
    window.scrollTo({ top: 0, behavior: "auto" });
  };

  const setDiscoverySidebarHostRef = useCallback((element: HTMLDivElement | null) => {
    setDiscoverySidebarHost(element);
  }, []);

  const showsDiscoveryIndex = activeSpaceId === "autonomous-discovery";

  return (
    <div
      className={`workspace workspace--${activeSpaceId} workspace--${activeModuleId}`}
      data-material-profile={activeModule.materialProfile}
    >
      <aside className={`workspace-sidebar${showsDiscoveryIndex ? " workspace-sidebar--with-discovery-index" : ""}`}>
        <div className="brand-lockup">
          <span className="brand-mark"><img src="/vegapunk-icon.png" alt="" /></span>
          <span>
            <strong>Vegapunk</strong>
            <small>RESEARCH STUDIO</small>
          </span>
        </div>

        <nav className="module-nav" aria-label={`${activeSpace.label}模块`}>
          {activeSpace.modules.map((module) => {
            const isActive = activeModule.id === module.id;
            const ModuleIcon = module.icon;
            return (
              <Fragment key={module.id}>
                <button
                  type="button"
                  className={isActive ? "is-active" : undefined}
                  onClick={() => selectModule(module.id)}
                  aria-current={isActive && !module.submodules ? "page" : undefined}
                  aria-label={module.label}
                  title={module.label}
                >
                  <span className="module-icon"><ModuleIcon aria-hidden="true" /></span>
                  <span className="module-label">
                    <strong>{module.label}</strong>
                    <small>{module.caption}</small>
                  </span>
                </button>
                {module.submodules ? (
                  <div className="module-subnav" role="group" aria-label={`${module.label}子菜单`}>
                    {module.submodules.map((submodule) => {
                      const SubmoduleIcon = submodule.icon;
                      const isSubmoduleActive = activeModuleId === submodule.id;
                      return (
                        <button
                          type="button"
                          key={submodule.id}
                          className={isSubmoduleActive ? "is-active" : undefined}
                          aria-current={isSubmoduleActive ? "page" : undefined}
                          onClick={() => selectModule(submodule.id)}
                        >
                          <SubmoduleIcon aria-hidden="true" />
                          <span>{submodule.label}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {module.id === "settings" ? (
                  <div className="module-subnav" role="group" aria-label="系统设置子模块">
                    {SETTINGS_SECTIONS.map((item) => {
                      const SectionIcon = item.icon;
                      const isSectionActive = settingsSection === item.id;
                      return (
                        <button
                          type="button"
                          key={item.id}
                          className={isSectionActive ? "is-active" : undefined}
                          aria-current={isActive && isSectionActive ? "page" : undefined}
                          onClick={() => {
                            setSettingsSection(item.id);
                            selectModule("settings");
                          }}
                        >
                          <SectionIcon aria-hidden="true" />
                          <span>{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </Fragment>
            );
          })}
        </nav>

        <div
          ref={setDiscoverySidebarHostRef}
          className="workspace-discovery-index-host"
          hidden={!showsDiscoveryIndex}
        />

        <div className="space-switcher" role="radiogroup" aria-label="工作空间">
          <p className="space-switcher-label">工作空间</p>
          <div className={`space-switcher-track space-switcher-track--${activeSpaceId}`}>
            <span className="space-switcher-indicator" aria-hidden="true" />
            {Object.values(SPACES).map((space) => {
              const isActive = space.id === activeSpaceId;
              return (
                <button
                  type="button"
                  key={space.id}
                  role="radio"
                  aria-checked={isActive}
                  aria-label={space.label}
                  className={isActive ? "is-active" : undefined}
                  onClick={() => selectSpace(space.id)}
                >
                  {space.id === "collaboration" ? "协作" : "自主发现"}
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      <main className="workspace-main" data-material-profile={activeModule.materialProfile}>
        <OccludedPointCloudSubstrate
          key={substrateEpoch}
          profile={activeModule.materialProfile}
          respondsToModuleChange={substrateEpoch > 0}
        />
        {activeModuleId === "settings" ? (
          <SystemSettings section={settingsSection} />
        ) : activeModuleId === "papers" ? (
          <PaperTools />
        ) : activeModuleId === "embodied" ? (
          <EmbodiedIntelligence />
        ) : activeModuleId === "simulation" ? (
          <SimulationPlaceholder />
        ) : activeModuleId === "skills" ? (
          <SkillCatalog />
        ) : activeModuleId === "achievement-upir" ? (
          <AchievementShowcase paper="upir" />
        ) : activeModuleId === "achievement-pbtwin" ? (
          <AchievementShowcase paper="planetary" />
        ) : activeSpaceId === "autonomous-discovery" ? null : (
          <PlaceholderModule module={activeModuleId as "skills" | "discovery-launch-archive"} />
        )}
        <div hidden={activeSpaceId !== "autonomous-discovery"}>
          <DiscoveryPreparation sidebarHost={discoverySidebarHost} />
        </div>
      </main>
    </div>
  );
}
