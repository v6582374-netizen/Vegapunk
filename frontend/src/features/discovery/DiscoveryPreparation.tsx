import { FilePlus2, FileText, PackageOpen, Save, Upload, WandSparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import {
  createDiscoveryPreparation,
  convertDiscoveryPreparation,
  fetchDiscoveryPreparations,
  saveFormattedDiscoveryInputRevision,
  type DiscoveryPreparationRecord,
  type DiscoverySource,
  type FormattedDiscoveryInputRevision,
} from "../../shared/workspaceApi";
import "./DiscoveryPreparation.css";

const SUPPORTED_SOURCE_TYPES = ".txt, .md, .pdf, .docx, .csv, .zip";

type Drawer =
  | { kind: "create" }
  | { kind: "details"; preparation: DiscoveryPreparationRecord }
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
  const [drawer, setDrawer] = useState<Drawer>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [isSaving, setIsSaving] = useState(false);
  const [convertingPreparationId, setConvertingPreparationId] = useState<string>();
  const [isSavingRevision, setIsSavingRevision] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

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
    if (!isSaving && !isSavingRevision) {
      setDrawer(undefined);
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

      <p className="discovery-index-future">选择已保存的输入修订版后，Discovery Launch 将从此处进入。</p>
    </aside>
  );

  return (
    <>
      {sidebarHost ? createPortal(preparationIndex, sidebarHost) : null}

      <section className="discovery-console" aria-label="Discovery 控制台">
        <header className="discovery-console-heading">
          <div>
            <p className="section-label">DISCOVERY CONSOLE</p>
            <h1>等待 Discovery Launch</h1>
          </div>
          <span className="discovery-console-status"><i aria-hidden="true" />IDLE</span>
        </header>
        <div className="discovery-console-waiting" role="status">
          <p>当前没有正在运行的 Discovery 流程。</p>
          <p>启动后，原始 stdout 与 stderr 将不经处理地显示在这里。</p>
        </div>
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
            <button type="button" className="discovery-drawer-close" aria-label="关闭 Preparation 详情" disabled={convertingPreparationId === drawer.preparation.id} onClick={closeDrawer}>
              <X aria-hidden="true" />
            </button>
          </header>
          <div className="discovery-drawer-body">
            <section className="discovery-drawer-section" aria-labelledby="saved-research-title">
              <h3 id="saved-research-title">原始课题资料</h3>
              {drawer.preparation.research_text ? <p className="discovery-research-text">{drawer.preparation.research_text}</p> : <p className="discovery-preparation-empty">未提供自由文本资料。</p>}
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
                    <button key={revision.id} type="button" onClick={() => openRevision(drawer.preparation, revision)}>
                      <span>REVISION {String(index + 1).padStart(2, "0")}</span>
                      <strong>{new Date(revision.created_at).toLocaleString()}</strong>
                    </button>
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
            <button type="button" className="button-primary" disabled={convertingPreparationId === drawer.preparation.id} onClick={() => void convertPreparation(drawer.preparation)}>
              <WandSparkles aria-hidden="true" />
              {convertingPreparationId === drawer.preparation.id ? "正在转换…" : "转换为格式化输入"}
            </button>
          </footer>
        </aside>
      ) : null}

      {drawer?.kind === "formatted" ? (
        <aside className="discovery-drawer discovery-input-drawer" role="dialog" aria-labelledby="formatted-discovery-input-title">
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
            <div>
              <button type="button" className="button-secondary" disabled={isSavingRevision} onClick={closeDrawer}>关闭</button>
              <button type="button" className="button-primary" disabled={isSavingRevision || !drawer.draft.trim()} onClick={() => void saveRevision()}>
                <Save aria-hidden="true" />
                {isSavingRevision ? "正在保存…" : "保存为新的输入修订版"}
              </button>
            </div>
          </footer>
        </aside>
      ) : null}
    </>
  );
}
