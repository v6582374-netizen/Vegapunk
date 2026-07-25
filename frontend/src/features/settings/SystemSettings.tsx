import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Library,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  deleteProviderCredential,
  fetchDefaultConfiguration,
  fetchPrompts,
  fetchProviderConnections,
  saveDefaultConfiguration,
  savePrompt,
  saveProviderConnection,
  verifyProviderConnection,
  type DefaultConfiguration,
  type ParameterField,
  type PromptRecord,
  type ProviderConnection,
} from "../../shared/adminApi";

type SettingsSection = "providers" | "prompts" | "defaults";
type Notice = { kind: "success" | "error"; text: string } | null;

const SECTIONS = [
  { id: "providers" as const, label: "API 配置", icon: KeyRound },
  { id: "prompts" as const, label: "Prompt 库", icon: Library },
  { id: "defaults" as const, label: "默认参数", icon: SlidersHorizontal },
];

const WORKFLOW_LABELS: Record<string, string> = {
  deep_research: "深度研究",
  discovery: "Discovery",
  experiment: "实验执行",
  paper: "论文评审",
  scoring: "结果评分",
};

const STAGE_LABELS: Record<string, string> = {
  citation_review: "引用评审",
  code_understanding: "代码理解",
  debugging: "调试",
  evaluation: "评估",
  evidence_synthesis: "证据综合",
  evolution: "方案演化",
  generation: "想法生成",
  global_planning: "全局规划",
  implementation: "实现",
  iteration: "实验迭代",
  literature_review: "文献评审",
  method_development: "方法开发",
  paper_review: "论文评审",
  ranking: "排序",
  reflection: "反思",
  report_writing: "报告写作",
  safeguards: "安全约束",
  task_execution: "任务执行",
};

const INVOCATION_LABELS: Record<PromptRecord["invocation_type"], string> = {
  single: "单次",
  repeated: "重复调用",
  conditional: "条件调用",
  mutually_exclusive: "互斥调用",
};

const PARAMETER_GROUP_LABELS: Record<string, string> = {
  agents: "Agent 行为",
  experiment: "实验执行",
  memory: "记忆系统",
  sci_task: "论文复现",
  sci_tools: "科学工具",
  system: "系统行为",
  tools: "检索工具",
  workflow: "Discovery 工作流",
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

function LoadingState() {
  return (
    <div className="settings-loading" role="status">
      <LoaderCircle aria-hidden="true" />
      <span>正在读取系统设置</span>
    </div>
  );
}

function NoticeBar({ notice, onClose }: { notice: Notice; onClose: () => void }) {
  if (!notice) return null;
  const Icon = notice.kind === "success" ? CheckCircle2 : AlertCircle;
  return (
    <div
      className={`settings-notice is-${notice.kind}`}
      role={notice.kind === "error" ? "alert" : "status"}
    >
      <Icon aria-hidden="true" />
      <span>{notice.text}</span>
      <button type="button" onClick={onClose} aria-label="关闭通知" title="关闭通知">
        <X aria-hidden="true" />
      </button>
    </div>
  );
}

function ProvidersView({
  connections,
  onChange,
  onNotice,
}: {
  connections: ProviderConnection[];
  onChange: (connection: ProviderConnection) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [urls, setUrls] = useState<Record<string, string>>(() =>
    Object.fromEntries(connections.map((item) => [item.provider, item.base_url])),
  );
  const [busy, setBusy] = useState<Record<string, string | null>>({});

  const run = async (
    provider: string,
    action: string,
    operation: () => Promise<ProviderConnection>,
    success: string,
  ) => {
    setBusy((current) => ({ ...current, [provider]: action }));
    onNotice(null);
    try {
      const connection = await operation();
      onChange(connection);
      onNotice({ kind: "success", text: success });
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      setBusy((current) => ({ ...current, [provider]: null }));
    }
  };

  return (
    <div className="provider-list">
      {connections.map((connection) => {
        const state = busy[connection.provider];
        return (
          <article className="provider-row" key={connection.provider}>
            <header className="provider-heading">
              <div>
                <span className="provider-monogram" aria-hidden="true">
                  {connection.name.slice(0, 1)}
                </span>
                <div>
                  <h2>{connection.name}</h2>
                  <p>{connection.model_count} 个已注册模型</p>
                </div>
              </div>
              <span className={`connection-state is-${connection.verification_status}`}>
                <i aria-hidden="true" />
                {connection.verification_status === "valid"
                  ? "连接有效"
                  : connection.verification_status === "authentication_failed"
                    ? "认证失败"
                    : connection.verification_status === "unreachable"
                      ? "无法连接"
                      : "尚未验证"}
              </span>
            </header>

            <div className="provider-fields">
              <label>
                <span>API Key</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={keys[connection.provider] ?? ""}
                  placeholder={connection.credential_configured ? "已配置，输入可替换" : "输入 API Key"}
                  onChange={(event) =>
                    setKeys((current) => ({
                      ...current,
                      [connection.provider]: event.target.value,
                    }))
                  }
                />
                <small>
                  {connection.credential_source === "vault"
                    ? "系统凭据库"
                    : connection.credential_source === "environment"
                      ? connection.environment_variable
                      : "未配置"}
                </small>
              </label>
              <label>
                <span>Base URL</span>
                <input
                  type="url"
                  value={urls[connection.provider] ?? connection.base_url}
                  disabled={!connection.base_url_configurable}
                  onChange={(event) =>
                    setUrls((current) => ({
                      ...current,
                      [connection.provider]: event.target.value,
                    }))
                  }
                />
                <small>{connection.provider}</small>
              </label>
            </div>

            <footer className="provider-actions">
              <button
                type="button"
                className="button-secondary"
                disabled={Boolean(state) || !connection.credential_configured}
                onClick={() =>
                  run(
                    connection.provider,
                    "verify",
                    () => verifyProviderConnection(connection.provider),
                    `${connection.name} 验证完成`,
                  )
                }
              >
                <RefreshCw className={state === "verify" ? "is-spinning" : ""} aria-hidden="true" />
                验证连接
              </button>
              <div>
                <button
                  type="button"
                  className="icon-button settings-delete"
                  disabled={Boolean(state) || connection.credential_source !== "vault"}
                  onClick={() =>
                    run(
                      connection.provider,
                      "delete",
                      () => deleteProviderCredential(connection.provider),
                      `${connection.name} 凭据已删除`,
                    )
                  }
                  aria-label={`删除 ${connection.name} 凭据`}
                  title="删除凭据"
                >
                  <Trash2 aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="button-primary"
                  disabled={Boolean(state)}
                  onClick={() =>
                    run(
                      connection.provider,
                      "save",
                      async () => {
                        const apiKey = keys[connection.provider]?.trim();
                        const updated = await saveProviderConnection(connection.provider, {
                          ...(apiKey ? { api_key: apiKey } : {}),
                          base_url: urls[connection.provider],
                        });
                        setKeys((current) => ({ ...current, [connection.provider]: "" }));
                        return updated;
                      },
                      `${connection.name} 配置已保存`,
                    )
                  }
                >
                  {state === "save" ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
                  保存
                </button>
              </div>
            </footer>
          </article>
        );
      })}
    </div>
  );
}

function PromptLibraryView({
  prompts,
  onChange,
  onNotice,
}: {
  prompts: PromptRecord[];
  onChange: (prompt: PromptRecord) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<PromptRecord | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [editorNotice, setEditorNotice] = useState<Notice>(null);
  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return term
      ? prompts.filter((prompt) =>
          [prompt.name, prompt.id, prompt.description, prompt.text]
            .join(" ")
            .toLocaleLowerCase()
            .includes(term),
        )
      : prompts;
  }, [prompts, query]);
  const workflows = useMemo(() => {
    const grouped = new Map<string, Map<string, PromptRecord[]>>();
    for (const prompt of filtered) {
      const stages = grouped.get(prompt.workflow) ?? new Map<string, PromptRecord[]>();
      const items = stages.get(prompt.stage) ?? [];
      items.push(prompt);
      stages.set(prompt.stage, items);
      grouped.set(prompt.workflow, stages);
    }
    return grouped;
  }, [filtered]);

  useEffect(() => {
    if (!selected) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) setSelected(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [saving, selected]);

  const open = (prompt: PromptRecord) => {
    setSelected(prompt);
    setDraft(prompt.text);
    setEditorNotice(null);
    onNotice(null);
  };

  const submit = async () => {
    if (!selected) return;
    setSaving(true);
    setEditorNotice(null);
    try {
      const updated = await savePrompt(selected.id, draft);
      onChange(updated);
      setSelected(updated);
      setDraft(updated.text);
      setEditorNotice({ kind: "success", text: `${updated.name} 已保存` });
      onNotice({ kind: "success", text: `${updated.name} 已保存` });
    } catch (error) {
      const notice = { kind: "error" as const, text: errorMessage(error) };
      setEditorNotice(notice);
      onNotice(notice);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="prompt-toolbar">
        <label className="search-field">
          <Search aria-hidden="true" />
          <input
            type="search"
            value={query}
            placeholder="搜索 Prompt"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <span>{filtered.length} / {prompts.length}</span>
      </div>

      <div className="prompt-catalogue">
        {[...workflows].map(([workflow, stages]) => (
          <section className="prompt-workflow" data-particle-identity={workflow} key={workflow}>
            <header>
              <span>{workflow}</span>
              <h2>{WORKFLOW_LABELS[workflow] ?? workflow}</h2>
            </header>
            {[...stages].map(([stage, items]) => (
              <div className="prompt-stage" key={stage}>
                <div className="prompt-stage-heading">
                  <h3>{STAGE_LABELS[stage] ?? stage}</h3>
                  <span>{items.length}</span>
                </div>
                <div className="prompt-grid">
                  {items.map((prompt) => (
                    <button
                      type="button"
                      className="prompt-card"
                      key={prompt.id}
                      onClick={() => open(prompt)}
                    >
                      <span className="prompt-card-topline">
                        <span>{String(prompt.order).padStart(2, "0")}</span>
                        <span>{INVOCATION_LABELS[prompt.invocation_type]}</span>
                      </span>
                      <strong>{prompt.name}</strong>
                      <span className="prompt-description">{prompt.description}</span>
                      <code>{prompt.text.replace(/\s+/g, " ").trim().slice(0, 190)}</code>
                      <span className="prompt-edit"><Pencil aria-hidden="true" />编辑</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
        {filtered.length === 0 ? <p className="settings-empty">没有匹配的 Prompt</p> : null}
      </div>

      {selected ? (
        <div className="prompt-dialog-backdrop" role="presentation" onMouseDown={() => !saving && setSelected(null)}>
          <section
            className="prompt-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="prompt-editor-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>{selected.id}</span>
                <h2 id="prompt-editor-title">{selected.name}</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setSelected(null)}
                disabled={saving}
                aria-label="关闭 Prompt 编辑器"
                title="关闭"
              >
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="prompt-dialog-meta">
              <div className="prompt-contract">
                <span>{WORKFLOW_LABELS[selected.workflow] ?? selected.workflow}</span>
                <span>{STAGE_LABELS[selected.stage] ?? selected.stage}</span>
                <span>{INVOCATION_LABELS[selected.invocation_type]}</span>
                {selected.template_variables.map((variable) => <code key={variable}>{`{${variable}}`}</code>)}
              </div>
              <NoticeBar
                notice={editorNotice}
                onClose={() => setEditorNotice(null)}
              />
            </div>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              spellCheck={false}
              autoFocus
            />
            <footer>
              <span>{draft.length.toLocaleString()} 字符</span>
              <div>
                <button type="button" className="button-secondary" disabled={saving} onClick={() => setDraft(selected.text)}>
                  撤销修改
                </button>
                <button type="button" className="button-primary" disabled={saving || draft === selected.text} onClick={submit}>
                  {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
                  保存 Prompt
                </button>
              </div>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

function getAtPath(values: Record<string, unknown>, path: string): unknown {
  let current: unknown = values;
  for (const part of path.split(".")) {
    current = (current as Record<string, unknown>)[part];
  }
  return current;
}

function setAtPath(
  values: Record<string, unknown>,
  path: string,
  nextValue: unknown,
): Record<string, unknown> {
  const copy = structuredClone(values);
  const parts = path.split(".");
  let current = copy;
  for (const part of parts.slice(0, -1)) {
    current = current[part] as Record<string, unknown>;
  }
  current[parts.at(-1)!] = nextValue;
  return copy;
}

function literalOptions(type: string): string[] {
  if (!type.includes("Literal")) return [];
  return [...type.matchAll(/["']([^"']+)["']/g)].map((match) => match[1]);
}

function ParameterControl({
  field,
  value,
  onChange,
}: {
  field: ParameterField;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const options = literalOptions(field.type);
  if (typeof value === "boolean") {
    return (
      <label className="toggle-control">
        <input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />
        <span aria-hidden="true"><i /></span>
      </label>
    );
  }
  if (options.length) {
    return (
      <select value={String(value)} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    );
  }
  if (typeof value === "number") {
    return (
      <input
        type="number"
        value={value}
        min={field.ge ?? (field.gt === undefined ? undefined : field.gt + Number.EPSILON)}
        max={field.le ?? (field.lt === undefined ? undefined : field.lt - Number.EPSILON)}
        step={Number.isInteger(value) ? 1 : 0.1}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    );
  }
  if (Array.isArray(value)) {
    return (
      <input
        type="text"
        value={value.join(", ")}
        onChange={(event) => onChange(event.target.value.split(",").map((item) => item.trim()).filter(Boolean))}
      />
    );
  }
  if (value && typeof value === "object") {
    return (
      <div className="parameter-map">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <label key={key}>
            <span>{key}</span>
            <input
              type={typeof item === "number" ? "number" : "text"}
              step={typeof item === "number" ? 0.1 : undefined}
              value={String(item)}
              onChange={(event) =>
                onChange({
                  ...(value as Record<string, unknown>),
                  [key]: typeof item === "number" ? Number(event.target.value) : event.target.value,
                })
              }
            />
          </label>
        ))}
      </div>
    );
  }
  return <input type="text" value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />;
}

function DefaultsView({
  configuration,
  onChange,
  onNotice,
}: {
  configuration: DefaultConfiguration;
  onChange: (configuration: DefaultConfiguration) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [bindings, setBindings] = useState(configuration.bindings);
  const [parameters, setParameters] = useState(configuration.parameters);
  const [saving, setSaving] = useState(false);
  const groups = useMemo(() => {
    const result = new Map<string, ParameterField[]>();
    for (const field of configuration.parameter_catalog) {
      const group = field.path.split(".")[0];
      result.set(group, [...(result.get(group) ?? []), field]);
    }
    return result;
  }, [configuration.parameter_catalog]);
  const dirty =
    JSON.stringify(bindings) !== JSON.stringify(configuration.bindings) ||
    JSON.stringify(parameters) !== JSON.stringify(configuration.parameters);
  const textProvider = configuration.models.find((model) => model.id === bindings.active_text_model)?.provider;
  const modelOptions = (capability: string) =>
    configuration.models.filter(
      (model) =>
        model.capabilities.includes(capability) &&
        (capability !== "image_generation" || model.provider === textProvider),
    );

  const save = async () => {
    setSaving(true);
    onNotice(null);
    try {
      const updated = await saveDefaultConfiguration({ bindings, parameters });
      onChange(updated);
      setBindings(updated.bindings);
      setParameters(updated.parameters);
      onNotice({ kind: "success", text: `默认配置 ${updated.revision} 已保存` });
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  const setTextModel = (identity: string) => {
    const provider = configuration.models.find((model) => model.id === identity)?.provider;
    const currentImage = configuration.models.find((model) => model.id === bindings.image_model);
    const compatibleImage = configuration.models.find(
      (model) => model.provider === provider && model.capabilities.includes("image_generation"),
    );
    setBindings((current) => ({
      ...current,
      active_text_model: identity,
      image_model: currentImage?.provider === provider ? current.image_model : compatibleImage?.id ?? "",
    }));
  };

  return (
    <div className="defaults-editor">
      <section className="model-bindings" aria-labelledby="model-bindings-title">
        <header className="settings-section-heading">
          <div>
            <span>MODEL BINDINGS</span>
            <h2 id="model-bindings-title">模型绑定</h2>
          </div>
          <span className={`readiness-state ${configuration.readiness.ready ? "is-ready" : ""}`}>
            <i aria-hidden="true" />
            {configuration.readiness.ready ? "可运行" : "待验证"}
          </span>
        </header>
        <div className="binding-grid">
          <label>
            <span>文本模型</span>
            <select value={bindings.active_text_model} onChange={(event) => setTextModel(event.target.value)}>
              {modelOptions("text").map((model) => <option value={model.id} key={model.id}>{model.id}</option>)}
            </select>
          </label>
          <label>
            <span>图像模型</span>
            <select value={bindings.image_model} onChange={(event) => setBindings((current) => ({ ...current, image_model: event.target.value }))}>
              {modelOptions("image_generation").map((model) => <option value={model.id} key={model.id}>{model.id}</option>)}
            </select>
          </label>
          <label>
            <span>嵌入模型</span>
            <select value={bindings.embedding_model} onChange={(event) => setBindings((current) => ({ ...current, embedding_model: event.target.value }))}>
              {modelOptions("embedding").map((model) => <option value={model.id} key={model.id}>{model.id}</option>)}
            </select>
          </label>
        </div>
      </section>

      {[...groups].map(([group, fields]) => (
        <section className="parameter-group" key={group}>
          <header className="settings-section-heading">
            <div>
              <span>{group.toUpperCase()}</span>
              <h2>{PARAMETER_GROUP_LABELS[group] ?? group}</h2>
            </div>
            <span>{fields.length}</span>
          </header>
          <div className="parameter-list">
            {fields.map((field) => (
              <div className="parameter-row" key={field.path}>
                <label htmlFor={`parameter-${field.path}`}>{field.description}</label>
                <div id={`parameter-${field.path}`}>
                  <ParameterControl
                    field={field}
                    value={getAtPath(parameters, field.path)}
                    onChange={(value) => setParameters((current) => setAtPath(current, field.path, value))}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      <div className="settings-save-dock">
        <span>REV {configuration.revision}</span>
        <button type="button" className="button-primary" disabled={!dirty || saving} onClick={save}>
          {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
          保存默认配置
        </button>
      </div>
    </div>
  );
}

export function SystemSettings() {
  const [section, setSection] = useState<SettingsSection>("providers");
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [prompts, setPrompts] = useState<PromptRecord[]>([]);
  const [configuration, setConfiguration] = useState<DefaultConfiguration | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchProviderConnections(),
      fetchPrompts(),
      fetchDefaultConfiguration(),
    ])
      .then(([providerConnections, registeredPrompts, defaults]) => {
        if (!active) return;
        setConnections(providerConnections);
        setPrompts(registeredPrompts);
        setConfiguration(defaults);
      })
      .catch((error: unknown) => active && setLoadError(errorMessage(error)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const replaceConnection = (updated: ProviderConnection) => {
    setConnections((current) =>
      current.map((connection) =>
        connection.provider === updated.provider ? updated : connection,
      ),
    );
    setConfiguration((current) => {
      if (!current) return current;
      const readinessConnections = current.readiness.connections.map((connection) =>
        connection.provider === updated.provider ? updated : connection,
      );
      return {
        ...current,
        readiness: {
          ready: readinessConnections.every(
            (connection) => connection.verification_status === "valid",
          ),
          connections: readinessConnections,
        },
      };
    });
  };

  return (
    <section className="system-settings" aria-labelledby="settings-title">
      <header className="settings-intro">
        <div>
          <p className="section-label">SYSTEM SETTINGS</p>
          <h1 id="settings-title">系统设置</h1>
        </div>
        <span>{prompts.length} PROMPTS · {connections.length} PROVIDERS</span>
      </header>

      <nav className="settings-tabs" aria-label="系统设置分类">
        {SECTIONS.map((item) => {
          const SectionIcon = item.icon;
          return (
            <button
              type="button"
              key={item.id}
              className={section === item.id ? "is-active" : undefined}
              aria-current={section === item.id ? "page" : undefined}
              onClick={() => {
                setSection(item.id);
                setNotice(null);
              }}
            >
              <SectionIcon aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </nav>

      <NoticeBar notice={notice} onClose={() => setNotice(null)} />
      {loading ? <LoadingState /> : null}
      {loadError ? (
        <div className="settings-error" role="alert">
          <AlertCircle aria-hidden="true" />
          <div><strong>无法读取系统设置</strong><span>{loadError}</span></div>
        </div>
      ) : null}
      {!loading && !loadError ? (
        <div className="settings-body">
          {section === "providers" ? (
            <ProvidersView connections={connections} onChange={replaceConnection} onNotice={setNotice} />
          ) : null}
          {section === "prompts" ? (
            <PromptLibraryView
              prompts={prompts}
              onChange={(updated) => setPrompts((current) => current.map((prompt) => prompt.id === updated.id ? updated : prompt))}
              onNotice={setNotice}
            />
          ) : null}
          {section === "defaults" && configuration ? (
            <DefaultsView configuration={configuration} onChange={setConfiguration} onNotice={setNotice} />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
