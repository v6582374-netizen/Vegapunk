import { FilePlus2, FileText, PackageOpen, Save, Upload, WandSparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  createDiscoveryPreparation,
  convertDiscoveryPreparation,
  fetchDiscoveryPreparations,
  saveFormattedDiscoveryInputRevision,
  type DiscoveryPreparationRecord,
  type DiscoverySource,
} from "../../shared/workspaceApi";
import "./DiscoveryPreparation.css";

const SUPPORTED_SOURCE_TYPES = ".txt, .md, .pdf, .docx, .csv, .zip";

function sourceKindLabel(source: DiscoverySource) {
  return source.kind === "baseline_code" ? "基线代码包" : "研究资料";
}

function sourceIcon(source: DiscoverySource) {
  return source.kind === "baseline_code" ? <PackageOpen aria-hidden="true" /> : <FileText aria-hidden="true" />;
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

export function DiscoveryPreparation() {
  const [researchText, setResearchText] = useState("");
  const [selectedSources, setSelectedSources] = useState<File[]>([]);
  const [preparations, setPreparations] = useState<DiscoveryPreparationRecord[]>([]);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [isSaving, setIsSaving] = useState(false);
  const [convertingPreparationId, setConvertingPreparationId] = useState<string>();
  const [editor, setEditor] = useState<{
    preparation: DiscoveryPreparationRecord;
    draft: string;
    modelId: string;
  }>();
  const [isSavingRevision, setIsSavingRevision] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDiscoveryPreparations()
      .then((records) => {
        if (!cancelled) {
          setPreparations(records);
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

  const savePreparation = async () => {
    setError(undefined);
    setNotice(undefined);
    setIsSaving(true);
    try {
      const saved = await createDiscoveryPreparation(researchText, selectedSources);
      setPreparations((records) => [saved, ...records.filter((record) => record.id !== saved.id)]);
      setResearchText("");
      setSelectedSources([]);
      if (fileInput.current) {
        fileInput.current.value = "";
      }
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
      setEditor({
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

  const saveRevision = async () => {
    if (!editor || !editor.draft.trim()) return;
    setError(undefined);
    setIsSavingRevision(true);
    try {
      const revision = await saveFormattedDiscoveryInputRevision(
        editor.preparation.id,
        editor.draft,
      );
      setPreparations((records) => records.map((preparation) => (
        preparation.id === editor.preparation.id
          ? { ...preparation, revisions: [...(preparation.revisions ?? []), revision] }
          : preparation
      )));
      setEditor(undefined);
      setNotice("已保存新的输入修订版");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "无法保存输入修订版");
    } finally {
      setIsSavingRevision(false);
    }
  };

  return (
    <section className="discovery-preparation" aria-label="Discovery Preparation">
      <header className="discovery-preparation-intro">
        <p>保留任何尚未整理的课题线索，并把它们保存为后续 Discovery 流程可复用的原始输入。</p>
        <span className="discovery-preparation-status"><i aria-hidden="true" />尚未转换</span>
      </header>

      <div className="discovery-preparation-layout">
        <section className="discovery-preparation-editor" aria-labelledby="raw-material-title">
          <div className="discovery-section-heading">
            <div>
              <p className="section-label">RAW MATERIAL</p>
              <h2 id="raw-material-title">原始课题资料</h2>
            </div>
            <span>可自由输入，不要求结构</span>
          </div>

          <label className="discovery-text-field">
            <span>原始课题资料</span>
            <textarea
              rows={8}
              value={researchText}
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
          {notice ? <p className="discovery-form-message is-success">{notice}</p> : null}

          <button
            type="button"
            className="discovery-save-button"
            disabled={isSaving}
            onClick={() => void savePreparation()}
          >
            <Save aria-hidden="true" />
            {isSaving ? "正在保存…" : "保存为新的 Preparation"}
          </button>
        </section>

        <section className="discovery-saved-preparations" aria-labelledby="saved-preparations-title">
          <div className="discovery-section-heading">
            <div>
              <p className="section-label">SAVED MATERIAL</p>
              <h2 id="saved-preparations-title">已保存的 Preparation</h2>
            </div>
            <span>{preparations.length} 条</span>
          </div>

          {preparations.length ? (
            <div className="discovery-preparation-records">
              {preparations.map((preparation) => (
                <article key={preparation.id} className="discovery-preparation-record">
                  <header>
                    <span>PREPARATION</span>
                    <time dateTime={preparation.created_at}>{new Date(preparation.created_at).toLocaleString()}</time>
                  </header>
                  {preparation.research_text ? <p>{preparation.research_text}</p> : null}
                  <PreparationSources sources={preparation.sources} />
                  <footer className="discovery-preparation-record-footer">
                    <span>{preparation.revisions?.length ?? 0} 个输入修订版</span>
                    <button
                      type="button"
                      className="discovery-convert-button"
                      disabled={convertingPreparationId === preparation.id}
                      onClick={() => void convertPreparation(preparation)}
                    >
                      <WandSparkles aria-hidden="true" />
                      {convertingPreparationId === preparation.id ? "正在转换…" : "转换为格式化输入"}
                    </button>
                  </footer>
                </article>
              ))}
            </div>
          ) : (
            <p className="discovery-preparation-empty">还没有已保存的 Preparation。</p>
          )}
        </section>
      </div>

      {editor ? (
        <aside
          className="discovery-input-drawer"
          role="dialog"
          aria-labelledby="formatted-discovery-input-title"
        >
          <header>
            <div>
              <p className="section-label">FORMATTED DISCOVERY INPUT</p>
              <h2 id="formatted-discovery-input-title">转换草稿</h2>
              <p>由 {editor.modelId} 生成。关闭而不保存会丢弃此草稿。</p>
            </div>
            <button
              type="button"
              className="discovery-drawer-close"
              aria-label="关闭格式化输入编辑器"
              disabled={isSavingRevision}
              onClick={() => setEditor(undefined)}
            >
              <X aria-hidden="true" />
            </button>
          </header>
          <label className="discovery-drawer-field" htmlFor="formatted-discovery-input">
            <span>Formatted Discovery Input</span>
            <textarea
              id="formatted-discovery-input"
              value={editor.draft}
              spellCheck={false}
              autoFocus
              onChange={(event) => setEditor((current) => current && {
                ...current,
                draft: event.target.value,
              })}
            />
          </label>
          <footer>
            <span>{editor.draft.length.toLocaleString()} 字符</span>
            <div>
              <button
                type="button"
                className="button-secondary"
                disabled={isSavingRevision}
                onClick={() => setEditor(undefined)}
              >
                丢弃草稿
              </button>
              <button
                type="button"
                className="button-primary"
                disabled={isSavingRevision || !editor.draft.trim()}
                onClick={() => void saveRevision()}
              >
                <Save aria-hidden="true" />
                {isSavingRevision ? "正在保存…" : "保存为新的输入修订版"}
              </button>
            </div>
          </footer>
        </aside>
      ) : null}
    </section>
  );
}
