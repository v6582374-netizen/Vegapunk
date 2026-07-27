import { ChevronLeft, ChevronRight, FilePlus2, FileText, PackageOpen, Rocket, Save, Upload, WandSparkles, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  createDiscoveryPreparation,
  convertDiscoveryPreparation,
  discoveryArtifactFileUrl,
  discoveryLogStreamUrl,
  fetchDiscoveryArtifactText,
  fetchDiscoveryArtifactTree,
  fetchDiscoveryLaunchStatus,
  fetchDiscoveryLaunches,
  fetchDiscoveryPreparations,
  saveFormattedDiscoveryInputRevision,
  submitDiscoveryLaunch,
  updateDiscoveryPreparation,
  type DiscoveryArtifactNode,
  type DiscoveryLaunchStatus,
  type DiscoveryLaunchSummary,
  type DiscoveryPreparationRecord,
  type DiscoverySource,
  type FormattedDiscoveryInputRevision,
} from "../../shared/workspaceApi";
import "./DiscoveryPreparation.css";

const SUPPORTED_SOURCE_TYPES = ".txt, .md, .pdf, .docx, .csv, .zip";

const STATUS_STAGES = [
  { id: "preparation", label: "Discovery Preparation", short: "准备" },
  { id: "launch", label: "Discovery Launch", short: "启动" },
  { id: "round", label: "Discovery Round", short: "轮次" },
  { id: "paper", label: "论文交接", short: "交接" },
  { id: "completed", label: "已完成", short: "完成" },
];

const TEXT_EXTENSIONS = new Set([
  "txt", "log", "json", "yaml", "yml", "py", "ts", "tsx", "js", "jsx", "sh",
  "tex", "bib", "csv", "toml", "ini", "cfg", "html", "css", "xml", "jsonl",
  "sql", "diff", "patch", "rs", "go", "java", "c", "cc", "cpp", "h", "hpp",
  "swift", "m", "mm", "r", "jl", "vue", "svelte", "lock", "properties", "rst", "adoc",
]);
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

type Drawer =
  | { kind: "create" }
  | {
    kind: "details";
    preparation: DiscoveryPreparationRecord;
    editingResearch?: boolean;
    researchDraft?: string;
  }
  | {
    kind: "formatted";
    preparation: DiscoveryPreparationRecord;
    draft: string;
    modelId?: string;
    revision?: FormattedDiscoveryInputRevision;
  };

function sourceKindLabel(source: DiscoverySource) {
  return source.kind === "baseline_code" ? "基线代码包" : "研究资料";
}

function sourceIcon(source: DiscoverySource) {
  return source.kind === "baseline_code" ? <PackageOpen aria-hidden="true" /> : <FileText aria-hidden="true" />;
}

function preparationTitle(preparation: DiscoveryPreparationRecord) {
  const firstLine = preparation.research_text.trim().split(/\r?\n/).find(Boolean)?.trim();
  if (firstLine) {
    return firstLine.slice(0, 54);
  }
  return preparation.sources.length ? `${preparation.sources.length} 份上传资料` : "未命名研究资料";
}

function extensionOf(path: string) {
  const dot = path.lastIndexOf(".");
  return dot === -1 ? "" : path.slice(dot + 1).toLowerCase();
}

function launchStageIndex(status: DiscoveryLaunchStatus | null) {
  if (status === null) return 0;
  if (status.state === "completed") return STATUS_STAGES.length - 1;
  if (status.stage === "paper") return 3;
  if (status.stage === "discovery" || status.stage === "experiment") return 2;
  if (status.stage === "starting") return 1;
  return 0;
}

function terminalOutcomeLabel(status: DiscoveryLaunchStatus | null) {
  if (!status) return undefined;
  switch (status.state) {
    case "cancelled": return "已取消";
    case "aborted": return "已停止";
    case "failed": return "运行失败";
    case "interrupted": return "执行中断";
    default: return undefined;
  }
}

function launchStateLabel(state: string) {
  switch (state) {
    case "running": return "运行中";
    case "starting": return "启动中";
    case "completed": return "已完成";
    case "failed": return "运行失败";
    case "aborted": return "已停止";
    case "interrupted": return "已中断";
    case "cancelled": return "已取消";
    default: return state || "未知";
  }
}

function flattenArtifactNodes(nodes: DiscoveryArtifactNode[]): DiscoveryArtifactNode[] {
  return nodes.flatMap((node) => [
    node,
    ...(node.children ? flattenArtifactNodes(node.children) : []),
  ]);
}

function PreparationSources({ sources }: { sources: DiscoverySource[] }) {
  if (!sources.length) {
    return <p className="discovery-preparation-empty">仅保存了自由文本资料。</p>;
  }

  return (
    <ul className="discovery-source-list">
      {sources.map((source) => (
        <li key={`${source.name}-${source.kind}`}>
          <span className="discovery-source-icon">{sourceIcon(source)}</span>
          <span>
            <strong>{source.name}</strong>
            <small>{sourceKindLabel(source)} · {source.extension}</small>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function DiscoveryPreparation({ sidebarHost }: { sidebarHost: HTMLDivElement | null }) {
  const [researchText, setResearchText] = useState("");
  const [selectedSources, setSelectedSources] = useState<File[]>([]);
  const [preparations, setPreparations] = useState<DiscoveryPreparationRecord[]>([]);
  const [selectedPreparationId, setSelectedPreparationId] = useState<string>();
  const [launches, setLaunches] = useState<DiscoveryLaunchSummary[]>([]);
  const [selectedLaunchId, setSelectedLaunchId] = useState<string>();
  const [launchStatus, setLaunchStatus] = useState<DiscoveryLaunchStatus | null>(null);
  const [artifactTree, setArtifactTree] = useState<DiscoveryArtifactNode[]>([]);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState<string>();
  const [artifactText, setArtifactText] = useState<string>();
  const [artifactError, setArtifactError] = useState<string>();
  const [logLines, setLogLines] = useState<string[]>([]);
  const [wheelFocus, setWheelFocus] = useState(0);
  const [drawer, setDrawer] = useState<Drawer>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [isSaving, setIsSaving] = useState(false);
  const [convertingPreparationId, setConvertingPreparationId] = useState<string>();
  const [isSavingRevision, setIsSavingRevision] = useState(false);
  const [isUpdatingPreparation, setIsUpdatingPreparation] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const launchRunningRef = useRef(false);
  const initializedWheelLaunchRef = useRef<string | undefined>(undefined);
  const wheelPointerStart = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDiscoveryPreparations()
      .then((records) => {
        if (!cancelled) {
          setPreparations(records);
          setSelectedPreparationId((current) => current ?? records[0]?.id);
        }
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "无法读取已保存的 Preparation");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadLaunches = () => {
      fetchDiscoveryLaunches()
        .then((records) => {
          if (!cancelled) {
            setLaunches(records);
            setSelectedLaunchId((current) => current ?? records[0]?.id);
          }
        })
        .catch((loadError: unknown) => {
          if (!cancelled) {
            setError(loadError instanceof Error ? loadError.message : "无法读取 Discovery Launch Archive");
          }
        });
    };
    loadLaunches();
    const timer = window.setInterval(loadLaunches, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedLaunchId) {
      launchRunningRef.current = false;
      initializedWheelLaunchRef.current = undefined;
      setLaunchStatus(null);
      setArtifactTree([]);
      setLogLines([]);
      return;
    }

    let cancelled = false;
    let source: EventSource | null = null;
    let retryTimer: number | undefined;
    const loadLaunch = () => {
      void fetchDiscoveryLaunchStatus(selectedLaunchId).then((status) => {
        if (!cancelled) {
          setLaunchStatus(status);
          launchRunningRef.current = status.state === "running" || status.state === "starting";
          if (initializedWheelLaunchRef.current !== selectedLaunchId) {
            initializedWheelLaunchRef.current = selectedLaunchId;
            setWheelFocus(launchStageIndex(status));
          }
        }
      }).catch(() => undefined);
      void fetchDiscoveryArtifactTree(selectedLaunchId)
        .then((tree) => { if (!cancelled) setArtifactTree(tree); })
        .catch(() => undefined);
    };
    loadLaunch();
    const statusTimer = window.setInterval(loadLaunch, 1500);

    const connect = () => {
      if (cancelled) return;
      setLogLines([]);
      source = new EventSource(discoveryLogStreamUrl(selectedLaunchId));
      source.onmessage = (event) => {
        if (!cancelled) setLogLines((lines) => [...lines, event.data]);
      };
      source.onerror = () => {
        source?.close();
        if (!cancelled && launchRunningRef.current) {
          retryTimer = window.setTimeout(connect, 1200);
        }
      };
    };
    connect();
    return () => {
      cancelled = true;
      source?.close();
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      window.clearInterval(statusTimer);
    };
  }, [selectedLaunchId]);

  const openCreateDrawer = () => {
    setError(undefined);
    setNotice(undefined);
    setDrawer({ kind: "create" });
  };

  const openDetailsDrawer = (preparation: DiscoveryPreparationRecord) => {
    setError(undefined);
    setNotice(undefined);
    setSelectedPreparationId(preparation.id);
    setDrawer({ kind: "details", preparation });
  };

  const closeDrawer = () => {
    if (!isSaving && !isSavingRevision && !isUpdatingPreparation) {
      setDrawer(undefined);
    }
  };

  const savePreparationResearch = async () => {
    if (!drawer || drawer.kind !== "details" || drawer.researchDraft === undefined) return;
    setError(undefined);
    setNotice(undefined);
    setIsUpdatingPreparation(true);
    try {
      const updated = await updateDiscoveryPreparation(
        drawer.preparation.id,
        drawer.researchDraft,
      );
      setPreparations((records) => records.map((preparation) => (
        preparation.id === updated.id ? updated : preparation
      )));
      setDrawer({ kind: "details", preparation: updated });
      setNotice("原始课题资料已更新；已有 Launch 不会被修改");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "无法更新原始课题资料");
    } finally {
      setIsUpdatingPreparation(false);
    }
  };

  const savePreparation = async () => {
    setError(undefined);
    setNotice(undefined);
    setIsSaving(true);
    try {
      const saved = await createDiscoveryPreparation(researchText, selectedSources);
      setPreparations((records) => [saved, ...records.filter((record) => record.id !== saved.id)]);
      setSelectedPreparationId(saved.id);
      setResearchText("");
      setSelectedSources([]);
      if (fileInput.current) {
        fileInput.current.value = "";
      }
      setDrawer(undefined);
      setNotice("Preparation 已保存");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "无法保存 Preparation");
    } finally {
      setIsSaving(false);
    }
  };

  const convertPreparation = async (preparation: DiscoveryPreparationRecord) => {
    setError(undefined);
    setNotice(undefined);
    setConvertingPreparationId(preparation.id);
    try {
      const converted = await convertDiscoveryPreparation(preparation.id);
      setDrawer({
        kind: "formatted",
        preparation,
        draft: converted.formatted_input,
        modelId: converted.model_id,
      });
    } catch (conversionError) {
      setError(conversionError instanceof Error ? conversionError.message : "无法转换 Preparation");
    } finally {
      setConvertingPreparationId(undefined);
    }
  };

  const openRevision = (
    preparation: DiscoveryPreparationRecord,
    revision: FormattedDiscoveryInputRevision,
  ) => {
    setError(undefined);
    setNotice(undefined);
    setDrawer({
      kind: "formatted",
      preparation,
      draft: revision.formatted_input,
      revision,
    });
  };

  const saveRevision = async () => {
    if (!drawer || drawer.kind !== "formatted" || !drawer.draft.trim()) {
      return;
    }

    setError(undefined);
    setNotice(undefined);
    setIsSavingRevision(true);
    try {
      const revision = await saveFormattedDiscoveryInputRevision(
        drawer.preparation.id,
        drawer.draft,
      );
      const updatedPreparation = {
        ...drawer.preparation,
        revisions: [...(drawer.preparation.revisions ?? []), revision],
      };
      setPreparations((records) => records.map((preparation) => (
        preparation.id === updatedPreparation.id ? updatedPreparation : preparation
      )));
      setDrawer({ kind: "details", preparation: updatedPreparation });
      setNotice("已保存新的输入修订版");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "无法保存输入修订版");
    } finally {
      setIsSavingRevision(false);
    }
  };

  const launchPreparation = async (
    preparation: DiscoveryPreparationRecord,
    revision: FormattedDiscoveryInputRevision,
  ) => {
    setError(undefined);
    setNotice(undefined);
    setIsLaunching(true);
    try {
      const submitted = await submitDiscoveryLaunch(preparation.id, revision.id);
      const records = await fetchDiscoveryLaunches();
      setLaunches(records);
      setSelectedLaunchId(submitted.launch_id);
      setDrawer(undefined);
      setNotice("Moonshot 已提交，已切换到新的 Discovery Launch");
    } catch (launchError) {
      setError(launchError instanceof Error ? launchError.message : "无法发起 Discovery Launch");
    } finally {
      setIsLaunching(false);
    }
  };

  const openArtifact = async (path: string) => {
    if (!selectedLaunchId) return;
    if (extensionOf(path) === "pdf") {
      window.open(discoveryArtifactFileUrl(selectedLaunchId, path), "_blank", "noopener,noreferrer");
      return;
    }
    setSelectedArtifactPath(path);
    setArtifactText(undefined);
    setArtifactError(undefined);
    const extension = extensionOf(path);
    if (TEXT_EXTENSIONS.has(extension) || extension === "md") {
      try {
        setArtifactText(await fetchDiscoveryArtifactText(selectedLaunchId, path));
      } catch (loadError) {
        setArtifactError(loadError instanceof Error ? loadError.message : "无法读取产物");
      }
    }
  };

  const selectedArtifact = selectedArtifactPath
    ? flattenArtifactNodes(artifactTree).find((node) => node.kind === "file" && node.path === selectedArtifactPath)
    : undefined;
  const currentStageIndex = launchStageIndex(launchStatus);
  const focusedStageIndex = Math.max(0, Math.min(STATUS_STAGES.length - 1, wheelFocus));
  const focusedStage = STATUS_STAGES[focusedStageIndex];
  const outcomeLabel = terminalOutcomeLabel(launchStatus);
  const focusedStageLabel = (
    outcomeLabel && focusedStageIndex === currentStageIndex
      ? outcomeLabel
      : focusedStage.label
  );

  const preparationIndex = (
    <aside className="discovery-preparation-index" aria-label="Preparation 索引">
      <div className="discovery-index-heading">
        <div>
          <p className="section-label">DISCOVERY PREPARATIONS</p>
          <h2>资料索引</h2>
        </div>
        <button type="button" className="discovery-new-preparation" onClick={openCreateDrawer}>
          <FilePlus2 aria-hidden="true" />
          <span>新建资料</span>
        </button>
      </div>
      <p className="discovery-index-copy">保存原始课题资料，并在右侧完成转换、修订与确认。</p>

      {error || notice ? (
        <p className={`discovery-index-message${error ? " is-error" : " is-success"}`} role={error ? "alert" : "status"}>
          {error ?? notice}
        </p>
      ) : null}

      <div className="discovery-index-records" aria-label="已保存的 Preparation">
        {preparations.length ? preparations.map((preparation, index) => {
          const isSelected = preparation.id === selectedPreparationId;
          return (
            <button
              key={preparation.id}
              type="button"
              className={`discovery-index-record${isSelected ? " is-selected" : ""}`}
              aria-pressed={isSelected}
              onClick={() => openDetailsDrawer(preparation)}
            >
              <span>PREPARATION {String(index + 1).padStart(2, "0")}</span>
              <strong>{preparationTitle(preparation)}</strong>
              <small>{preparation.sources.length} 份来源 · {preparation.revisions?.length ?? 0} 个输入修订版</small>
            </button>
          );
        }) : (
          <p className="discovery-preparation-empty">还没有已保存的 Preparation。</p>
        )}
      </div>

      {drawer?.kind === "formatted" ? (
        <section className="discovery-inline-formatted" aria-labelledby="formatted-discovery-input-title">
          <header>
            <div>
              <p className="section-label">FORMATTED DISCOVERY INPUT</p>
              <h2 id="formatted-discovery-input-title">{drawer.revision ? "格式化输入修订版" : "转换草稿"}</h2>
              <p>{drawer.modelId ? `由 ${drawer.modelId} 生成。` : "已保存的修订版可继续编辑并另存为新版本。"}</p>
            </div>
            <button type="button" className="discovery-drawer-close" aria-label="关闭格式化输入编辑器" disabled={isSavingRevision} onClick={closeDrawer}>
              <X aria-hidden="true" />
            </button>
          </header>
          <section className="discovery-inline-formatted-context" aria-labelledby="formatted-discovery-context-title">
            <h3 id="formatted-discovery-context-title">来源上下文</h3>
            {drawer.preparation.research_text ? <p className="discovery-research-text">{drawer.preparation.research_text}</p> : null}
            <PreparationSources sources={drawer.preparation.sources} />
          </section>
          <label className="discovery-drawer-field" htmlFor="formatted-discovery-input">
            <span>Formatted Discovery Input</span>
            <textarea
              id="formatted-discovery-input"
              value={drawer.draft}
              spellCheck={false}
              autoFocus
              onChange={(event) => setDrawer((current) => current?.kind === "formatted" ? {
                ...current,
                draft: event.target.value,
              } : current)}
            />
          </label>
          <footer>
            <span>{drawer.draft.length.toLocaleString()} 字符</span>
            <button type="button" className="button-primary" disabled={isSavingRevision || !drawer.draft.trim()} onClick={() => void saveRevision()}>
              <Save aria-hidden="true" />
              {isSavingRevision ? "正在保存…" : "保存为新的输入修订版"}
            </button>
          </footer>
        </section>
      ) : null}

      <p className="discovery-index-future">选择已保存的输入修订版后，Discovery Launch 将从此处进入。</p>
    </aside>
  );

  return (
    <>
      {sidebarHost ? createPortal(preparationIndex, sidebarHost) : null}

      <section className="discovery-workbench" aria-label="Discovery 控制台">
        <aside className="discovery-launch-archive" role="region" aria-label="Discovery Launch Archive">
          <header className="discovery-archive-heading">
            <div>
              <p className="section-label">DISCOVERY LAUNCH ARCHIVE</p>
              <h2>运行档案</h2>
            </div>
            <span>{launches.length} 个 Launch</span>
          </header>
          <p className="discovery-archive-copy">选择一个 Launch，中央终端和可读产物会跟随切换。</p>
          <div className="discovery-archive-list">
            {launches.length ? launches.map((launch) => (
              <button
                type="button"
                key={launch.id}
                className={`discovery-launch-record${selectedLaunchId === launch.id ? " is-selected" : ""}`}
                aria-pressed={selectedLaunchId === launch.id}
                onClick={() => {
                  setSelectedLaunchId(launch.id);
                  setSelectedArtifactPath(undefined);
                  setArtifactText(undefined);
                }}
              >
                <span className={`discovery-launch-dot is-${launch.state}`} aria-hidden="true" />
                <span className="discovery-launch-record-copy">
                  <strong>{launch.task === "Discovery" ? "Autonomous Discovery" : launch.task}</strong>
                  <small>{new Date(launch.started_at).toLocaleString()} · {launchStateLabel(launch.state)}</small>
                  <code>{launch.id}</code>
                </span>
              </button>
            )) : (
              <p className="discovery-preparation-empty">尚无 Discovery Launch。</p>
            )}
          </div>
          {selectedLaunchId && artifactTree.length ? (
            <section className="discovery-archive-files" aria-labelledby="discovery-archive-files-title">
              <div className="discovery-archive-files-heading">
                <h3 id="discovery-archive-files-title">可读产物</h3>
                <small>PDF 在新标签页打开</small>
              </div>
              <div className="discovery-archive-file-list">
                {flattenArtifactNodes(artifactTree).filter((node) => node.kind === "file").map((node) => (
                  <button
                    key={node.path}
                    type="button"
                    className={selectedArtifactPath === node.path ? "is-selected" : undefined}
                    onClick={() => void openArtifact(node.path)}
                  >
                    <FileText aria-hidden="true" />
                    <span>{node.path}</span>
                    {extensionOf(node.path) === "pdf" ? <small>PDF ↗</small> : null}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </aside>

        <div className="discovery-center-stage">
          <header className="discovery-console-heading">
            <div>
              <p className="section-label">SELECTED LAUNCH STATUS</p>
              <h1>{selectedLaunchId ? "Discovery Launch" : "等待 Discovery Launch"}</h1>
              {selectedLaunchId ? (
                <code className="discovery-selected-launch-id" aria-label={`选中 Launch ${selectedLaunchId}`}>
                  {selectedLaunchId}
                </code>
              ) : null}
            </div>
            <span
              className={`discovery-console-status is-${launchStatus?.state ?? "idle"}`}
              role="status"
              aria-label={`Launch 状态：${launchStatus ? launchStateLabel(launchStatus.state) : "空闲"}`}
            >
              <i aria-hidden="true" />{launchStatus ? launchStateLabel(launchStatus.state) : "IDLE"}
            </span>
          </header>

          <section className="discovery-status-wheel" aria-label="Selected Launch 状态轮盘">
            <div className="discovery-wheel-heading">
              <div>
                <p className="section-label">STATUS WHEEL</p>
                <h2>{launchStatus ? focusedStageLabel : "等待 Discovery Launch"}</h2>
              </div>
              <span>{launchStatus ? "状态来自持久运行事实" : "选择左侧 Launch 查看状态"}</span>
            </div>
            <div
              className="discovery-wheel-stages"
              tabIndex={0}
              role="listbox"
              aria-label="浏览 Discovery 生命周期状态"
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  setWheelFocus((focus) => Math.max(0, focus - 1));
                }
                if (event.key === "ArrowRight") {
                  event.preventDefault();
                  setWheelFocus((focus) => Math.min(STATUS_STAGES.length - 1, focus + 1));
                }
              }}
              onPointerDown={(event) => {
                wheelPointerStart.current = event.clientX;
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerUp={(event) => {
                if (wheelPointerStart.current === null) return;
                const distance = event.clientX - wheelPointerStart.current;
                wheelPointerStart.current = null;
                if (Math.abs(distance) < 24) return;
                setWheelFocus((focus) => Math.max(
                  0,
                  Math.min(STATUS_STAGES.length - 1, focus + (distance < 0 ? 1 : -1)),
                ));
              }}
              onPointerCancel={() => { wheelPointerStart.current = null; }}
            >
              {STATUS_STAGES.map((stage, index) => {
                const isFocused = index === focusedStageIndex;
                const isDone = index < currentStageIndex;
                const isCurrent = index === currentStageIndex;
                return (
                  <button
                    type="button"
                    role="option"
                    aria-selected={isFocused}
                    key={stage.id}
                    className={`discovery-wheel-stage${isFocused ? " is-focused" : ""}${isDone ? " is-done" : ""}${isCurrent ? " is-current" : ""}${isCurrent && outcomeLabel ? " is-terminal" : ""}`}
                    onClick={() => setWheelFocus(index)}
                  >
                    <small>{isCurrent && outcomeLabel ? "结果" : stage.short}</small>
                    <strong>{isCurrent && outcomeLabel ? outcomeLabel : stage.label}</strong>
                  </button>
                );
              })}
            </div>
            <div className="discovery-wheel-meta">
              <span>{launchStatus ? `当前事实：${outcomeLabel ?? STATUS_STAGES[currentStageIndex].label}${launchStatus.rounds ? ` · Round ${launchStatus.rounds}` : ""}` : "轮盘只浏览状态，不改变运行流程"}</span>
              <div>
                <button type="button" aria-label="上一个状态" onClick={() => setWheelFocus((focus) => Math.max(0, focus - 1))}><ChevronLeft aria-hidden="true" /></button>
                <button type="button" aria-label="下一个状态" onClick={() => setWheelFocus((focus) => Math.min(STATUS_STAGES.length - 1, focus + 1))}><ChevronRight aria-hidden="true" /></button>
                <button type="button" onClick={() => setWheelFocus(currentStageIndex)}>回到当前状态</button>
              </div>
            </div>
          </section>

          <section className="discovery-raw-console" aria-label="Raw Discovery Console">
            <header>
              <div>
                <span className="discovery-live-dot" aria-hidden="true" />
                <h2>Raw Discovery Console</h2>
              </div>
              <small>完整持久日志 · 未处理</small>
            </header>
            {selectedLaunchId ? (
              <pre>{logLines.length ? logLines.join("\n") : "等待 runner.log 输出…"}</pre>
            ) : (
              <div className="discovery-console-waiting" role="status">
                <p>当前没有已选择的 Discovery Launch。</p>
                <p>启动后，原始 stdout 与 stderr 将不经处理地显示在这里。</p>
              </div>
            )}
          </section>
        </div>

        {selectedArtifactPath && selectedArtifact ? (
          <aside className="discovery-artifact-preview" aria-label="Artifact Preview">
            <header>
              <div>
                <p className="section-label">ARTIFACT PREVIEW</p>
                <h2>{selectedArtifact.name}</h2>
              </div>
              <button type="button" className="discovery-drawer-close" aria-label="关闭产物预览" onClick={() => setSelectedArtifactPath(undefined)}><X aria-hidden="true" /></button>
            </header>
            <div className="discovery-artifact-preview-body">
              <small>{selectedArtifact.path}</small>
              {artifactError ? <p className="discovery-form-message is-error" role="alert">{artifactError}</p> : null}
              {IMAGE_EXTENSIONS.has(extensionOf(selectedArtifact.path)) && selectedLaunchId ? (
                <img src={discoveryArtifactFileUrl(selectedLaunchId, selectedArtifact.path)} alt={selectedArtifact.name} />
              ) : extensionOf(selectedArtifact.path) === "md" && artifactText !== undefined ? (
                <article className="discovery-markdown-preview"><ReactMarkdown>{artifactText}</ReactMarkdown></article>
              ) : TEXT_EXTENSIONS.has(extensionOf(selectedArtifact.path)) && artifactText !== undefined ? (
                <pre className="discovery-text-preview">{artifactText}</pre>
              ) : !artifactError ? (
                <p className="discovery-preparation-empty">该文件没有内置预览。</p>
              ) : null}
            </div>
          </aside>
        ) : null}
      </section>

      {drawer?.kind === "create" ? (
        <aside className="discovery-drawer" role="dialog" aria-labelledby="new-preparation-title">
          <header>
            <div>
              <p className="section-label">RAW MATERIAL</p>
              <h2 id="new-preparation-title">新建 Preparation</h2>
              <p>可粘贴任何原始想法或问题，也可附加研究资料与基线代码包。</p>
            </div>
            <button type="button" className="discovery-drawer-close" aria-label="关闭新建 Preparation" disabled={isSaving} onClick={closeDrawer}>
              <X aria-hidden="true" />
            </button>
          </header>
          <div className="discovery-drawer-body">
            <label className="discovery-text-field">
              <span>原始课题资料</span>
              <textarea
                rows={9}
                value={researchText}
                autoFocus
                onChange={(event) => setResearchText(event.target.value)}
                placeholder="粘贴研究问题、观察、假设或任何未整理的课题资料…"
              />
            </label>

            <div className="discovery-upload-field">
              <div>
                <strong>补充来源</strong>
                <p>支持 {SUPPORTED_SOURCE_TYPES}，其中 .zip 将作为基线代码包保存。</p>
              </div>
              <label className="discovery-upload-button">
                <Upload aria-hidden="true" />
                <span>上传研究资料</span>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept={SUPPORTED_SOURCE_TYPES}
                  aria-label="上传研究资料"
                  onChange={(event) => {
                    setSelectedSources(Array.from(event.currentTarget.files ?? []));
                    setError(undefined);
                  }}
                />
              </label>
            </div>

            {selectedSources.length > 0 ? (
              <section className="discovery-pending-sources" aria-labelledby="pending-sources-title">
                <h3 id="pending-sources-title">待保存来源</h3>
                <ul className="discovery-source-list">
                  {selectedSources.map((source) => (
                    <li key={`${source.name}-${source.lastModified}`}>
                      <span className="discovery-source-icon"><FilePlus2 aria-hidden="true" /></span>
                      <span>
                        <strong>{source.name}</strong>
                        <small>{source.type || "等待服务端确认类型"}</small>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {error ? <p className="discovery-form-message is-error" role="alert">{error}</p> : null}
          </div>
          <footer>
            <span>保存后可在此资料索引中查看与转换。</span>
            <button type="button" className="button-primary" disabled={isSaving} onClick={() => void savePreparation()}>
              <Save aria-hidden="true" />
              {isSaving ? "正在保存…" : "保存为新的 Preparation"}
            </button>
          </footer>
        </aside>
      ) : null}

      {drawer?.kind === "details" ? (
        <aside className="discovery-drawer" role="dialog" aria-labelledby="preparation-details-title">
          <header>
            <div>
              <p className="section-label">PREPARATION</p>
              <h2 id="preparation-details-title">已保存的研究资料</h2>
              <p>{new Date(drawer.preparation.created_at).toLocaleString()}</p>
            </div>
            <button type="button" className="discovery-drawer-close" aria-label="关闭 Preparation 详情" disabled={convertingPreparationId === drawer.preparation.id || isUpdatingPreparation} onClick={closeDrawer}>
              <X aria-hidden="true" />
            </button>
          </header>
          <div className="discovery-drawer-body">
            <section className="discovery-drawer-section" aria-labelledby="saved-research-title">
              <h3 id="saved-research-title">原始课题资料</h3>
              {drawer.editingResearch ? (
                <textarea
                  className="discovery-research-editor"
                  aria-label="编辑原始课题资料"
                  value={drawer.researchDraft ?? ""}
                  autoFocus
                  onChange={(event) => setDrawer((current) => current?.kind === "details" ? {
                    ...current,
                    researchDraft: event.target.value,
                  } : current)}
                />
              ) : drawer.preparation.research_text ? (
                <p className="discovery-research-text">{drawer.preparation.research_text}</p>
              ) : (
                <p className="discovery-preparation-empty">未提供自由文本资料。</p>
              )}
              <div className="discovery-drawer-inline-actions">
                {drawer.editingResearch ? (
                  <>
                    <button type="button" className="button-secondary" disabled={isUpdatingPreparation} onClick={() => setDrawer({ kind: "details", preparation: drawer.preparation })}>取消</button>
                    <button type="button" className="button-primary" disabled={isUpdatingPreparation || !(drawer.researchDraft ?? "").trim() && !drawer.preparation.sources.length} onClick={() => void savePreparationResearch()}>
                      {isUpdatingPreparation ? "正在保存…" : "保存原始资料"}
                    </button>
                  </>
                ) : (
                  <button type="button" className="button-secondary" onClick={() => setDrawer({
                    kind: "details",
                    preparation: drawer.preparation,
                    editingResearch: true,
                    researchDraft: drawer.preparation.research_text,
                  })}>编辑原始资料</button>
                )}
              </div>
            </section>
            <section className="discovery-drawer-section" aria-labelledby="saved-sources-title">
              <h3 id="saved-sources-title">来源</h3>
              <PreparationSources sources={drawer.preparation.sources} />
            </section>
            <section className="discovery-drawer-section" aria-labelledby="saved-revisions-title">
              <h3 id="saved-revisions-title">输入修订版</h3>
              {drawer.preparation.revisions?.length ? (
                <div className="discovery-revision-list">
                  {drawer.preparation.revisions.map((revision, index) => (
                    <div className="discovery-revision-row" key={revision.id}>
                      <button type="button" onClick={() => openRevision(drawer.preparation, revision)}>
                        <span>REVISION {String(index + 1).padStart(2, "0")}</span>
                        <strong>{new Date(revision.created_at).toLocaleString()}</strong>
                      </button>
                      <button
                        type="button"
                        className="discovery-revision-launch"
                        disabled={isLaunching}
                        onClick={() => void launchPreparation(drawer.preparation, revision)}
                      >
                        <Rocket aria-hidden="true" />
                        Moonshot
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="discovery-preparation-empty">尚无已保存的格式化输入。</p>
              )}
            </section>
            {error ? <p className="discovery-form-message is-error" role="alert">{error}</p> : null}
          </div>
          <footer>
            <span>{drawer.preparation.revisions?.length ?? 0} 个输入修订版</span>
            <button type="button" className="button-primary" disabled={convertingPreparationId === drawer.preparation.id || isLaunching} onClick={() => void convertPreparation(drawer.preparation)}>
              <WandSparkles aria-hidden="true" />
              {convertingPreparationId === drawer.preparation.id ? "正在转换…" : "转换为格式化输入"}
            </button>
          </footer>
        </aside>
      ) : null}

    </>
  );
}
