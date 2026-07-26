import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  Eye,
  EyeOff,
  Languages,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import "./PromptMirrors.css";
import { type SettingsSection } from "./settingsNavigation";

import {
  deleteProviderCredential,
  fetchDefaultConfiguration,
  fetchDiscoveryInputConversionPrompt,
  fetchPromptMirrorBatch,
  fetchPromptMirrorBatchAvailability,
  fetchPrompts,
  fetchPromptTranslationInstruction,
  fetchProviderConnections,
  revealProviderCredential,
  saveDefaultConfiguration,
  saveDiscoveryInputConversionPrompt,
  savePrompt,
  savePromptTranslationInstruction,
  saveProviderConnection,
  startPromptMirrorBatch,
  synchronizePrompt,
  retryPromptMirrorBatch,
  verifyProviderConnection,
  type DefaultConfiguration,
  type DiscoveryInputConversionPrompt,
  type ParameterField,
  type ChinesePromptMirror,
  type PromptMirrorBatch,
  type PromptMirrorBatchAvailability,
  type PromptRecord,
  type PromptTranslationInstruction,
  type ProviderConnection,
} from "../../shared/adminApi";

type Notice = { kind: "success" | "error"; text: string } | null;
type PromptLanguage = "en" | "zh";
type SelectedPrompt = { prompt: PromptRecord; language: PromptLanguage };

const MASKED_API_KEY = "******";

const COMING_SOON_PROVIDERS = [
  { provider: "deepseek", name: "DeepSeek" },
  { provider: "kimi", name: "Kimi" },
  { provider: "openai", name: "OpenAI" },
] as const;

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

const MISSING_CHINESE_MIRROR: ChinesePromptMirror = {
  state: "missing",
  file: "",
  text: null,
};

const CHINESE_MIRROR_LABELS: Record<ChinesePromptMirror["state"], string> = {
  ready: "中文镜像已就绪",
  missing: "中文镜像缺失，尚未生成。",
  stale: "中文镜像已过期，需要重新生成。",
};

const BATCH_ITEM_LABELS: Record<PromptMirrorBatch["items"][number]["state"], string> = {
  pending: "等待生成",
  success: "已生成",
  failure: "生成失败",
  skipped: "已跳过",
};

function chineseMirrorFor(prompt: PromptRecord): ChinesePromptMirror {
  return prompt.chinese_mirror ?? MISSING_CHINESE_MIRROR;
}

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

const PARAMETER_HELP: Partial<Record<string, string>> = {
  "system.debug": "打开后会记录更多内部诊断信息，适合排查问题。日常运行建议关闭，避免日志过多。",
  "system.log_level": "决定日志的详细程度。DEBUG 最详细，INFO 适合日常观察，WARNING 只保留警告，ERROR 只保留错误。",
  "memory.task_memory.enabled": "让系统在新一轮实验中参考过去相似任务的经验。关闭后，每轮都不会读取这些短期经验。",
  "memory.task_memory.top_k": "每次检索时取回多少条最相关的历史记录。数值越大，参考范围越广，但内容也可能更杂。",
  "memory.task_memory.alpha": "平衡关键词匹配和语义相似度。接近 1 更看重关键词，接近 0 更看重语义意思。",
  "memory.task_memory.include_details": "控制检索结果是否带上完整实验细节。开启后信息更充分，传给模型的上下文也会更长。",
  "memory.task_memory.embedding_mode": "指定用记录的哪一部分生成检索向量。完整内容最全面，标题最简洁，描述和方法介于两者之间。",
  "memory.online_memory.enabled": "每次实验结束后自动把结果写入经验库，供后续轮次参考。",
  "memory.online_memory.aggregation": "同一实验多次运行时，决定保存哪种汇总结果。best 保存最佳一次，avg 保存平均表现，last 保存最后一次。",
  "memory.long_memory.enabled": "开启跨轮次的长期经验库和 IdeaGraph。它帮助系统识别已探索过的想法方向。",
  "memory.long_memory.idea_graph.similarity_threshold": "两个想法达到这个相似度才会在 IdeaGraph 中连边。值越高，只有更相近的想法才会被归为关联。",
  "memory.long_memory.prompt_evolver.enabled": "允许系统根据积累的经验自动调整 Discovery 阶段使用的提示词。",
  "memory.long_memory.prompt_evolver.evolution_interval": "每完成多少个 Discovery 轮次执行一次提示词演化。设为 1 表示每轮都尝试更新。",
  "sci_tools.local": "启用本机提供的 Sci 工具。仅在本地已经配置这些工具时开启。",
  "tools.web_search.max_results": "限制一次网页搜索最多带回多少条结果。更多结果覆盖更广，但也会增加筛选和上下文负担。",
  "tools.literature_search.timeout": "文献检索请求最多等待多久。网络较慢时可适当调大，过大也会让失败请求占用更久。",
  "agents.generation.generation_count": "每个 Discovery 轮次生成的候选想法数。更多候选带来更广探索，也会增加后续评审成本。",
  "agents.generation.creativity": "控制想法生成的发散程度。低值更稳妥地贴近已有方向，高值会尝试更多新颖组合。",
  "agents.generation.do_survey": "在生成想法前先做文献调研，让候选方案更能避开已有工作。",
  "agents.generation.use_memory": "生成想法时参考历史实验记忆，减少重复尝试并利用已有经验。",
  "agents.generation.filter_failed_ideas": "自动拦截与过去失败尝试过于相似的候选想法。",
  "agents.generation.failed_similarity_threshold": "候选与失败尝试达到这个相似度就会被视为重复。值越低，过滤会更严格。",
  "agents.generation.max_regeneration_attempts": "候选被过滤后，允许系统重新生成的最多次数。设为 0 则不重试。",
  "agents.reflection.count": "每个候选想法会经历多少轮反思和改进。更多轮次通常更细致，但会增加时间和模型调用。",
  "agents.reflection.detail_level": "控制反思输出的篇幅和深入程度。low 简洁，medium 平衡，high 更全面。",
  "agents.evolution.evolution_count": "每轮从已有想法衍生多少个新变体，用于继续探索和比较。",
  "agents.evolution.creativity_level": "控制想法演化时的改动幅度。数值越高，变体与原想法的差异通常越大。",
  "agents.evolution.temperature": "演化模型的采样随机度。较低更稳定和可预测，较高更有探索性但也更不稳定。",
  "agents.evolution.use_memory": "演化已有想法时使用历史经验，帮助保留有效方向并避开已知问题。",
  "agents.evolution.filter_failed_ideas": "过滤掉与失败实验过于相似的演化结果。",
  "agents.evolution.failed_similarity_threshold": "设定演化结果与失败尝试多像时需要过滤。数值越低，过滤范围越大。",
  "agents.evolution.max_regeneration_attempts": "演化结果被过滤后，允许重新生成的最多次数。",
  "agents.ranking.criteria": "为新颖性、可信度、可测试性和任务契合度等排序标准设置权重。权重越大，该标准影响越大。",
  "agents.ranking.strategy": "选择候选想法的排序方式。默认策略会按系统内置的综合规则排序。",
  "agents.scholar.search_depth": "控制学术检索的深入程度。shallow 更快，deep 会搜索和分析更多资料。",
  "agents.scholar.sources": "指定学术检索允许使用的数据来源。留空时按系统默认来源处理。",
  "agents.survey.max_papers": "文献综述最多纳入多少篇论文。数值越大，覆盖更广，但阅读和整理时间也更长。",
  "agents.survey.sources": "指定文献综述可使用的数据来源。留空时按系统默认来源处理。",
  "agents.dr.enabled": "在正式生成前启用 Deep Research 背景调研，帮助系统补充领域信息和证据。",
  "agents.dr.mode": "选择 Deep Research 的执行方式。不同模式会影响调研流程和产出粒度。",
  "agents.exp_analyze.temperature": "控制实验结果分析模型的随机度。较低更稳定，较高更适合探索不同解释。",
  "agents.exp_analyze.timeout": "实验结果分析阶段最多等待模型响应多久，单位为秒。",
  "agents.exp_analyze.use_llm_for_metric_direction": "让模型判断每个指标是越高越好还是越低越好。关闭后需依赖已有规则。",
  "agents.exp_analyze.use_llm_for_primary_metric": "让模型从多个指标中选择最重要的主指标，用于判断实验表现。",
  "workflow.max_iterations": "单个想法在 MAS 中最多经过多少次演化迭代，防止流程无限继续。",
  "workflow.top_ideas_count": "每轮选出多少个最佳想法进入实验阶段。数值越大，实验覆盖更广，资源消耗也更高。",
  "workflow.top_ideas_evo": "让本轮表现最好的想法也参与下一步演化，而不只保留为最终候选。",
  "workflow.max_concurrent_tasks": "MAS 内同时执行的任务数上限。提高它可加快处理，但会占用更多模型和机器资源。",
  "workflow.loop_rounds": "整个 Discovery 流程最多重复多少轮，用于控制总探索范围。",
  "workflow.loop_mode": "fresh 每轮从基线重新开始，incremental 则从上一轮最优结果继续推进。",
  "sci_task.evaluation_mode": "选择论文复现任务如何评估结果。llm_judge 由模型判断，none 则跳过评估。",
  "experiment.model": "指定实验阶段的编码 Agent 使用哪个模型。它会影响代码实现和修复的能力、成本与速度。",
  "experiment.use_mcts": "在实验阶段使用 MCTS 搜索来探索多条路径，而不是常规的运行和修错循环。",
  "experiment.max_runs": "每个候选方案最多运行多少次实验。run_0 是基线运行，后续运行用于改进或重试。",
  "experiment.max_parallel_experiments": "同一时间最多并行运行多少个实验。提高它可缩短总耗时，但会占用更多资源。",
  "experiment.gpu_per_experiment": "分配给每个并行实验的 GPU 配额。支持小数，用于在多个实验间共享 GPU。",
};

function parameterHelpFor(field: ParameterField): string {
  return PARAMETER_HELP[field.path] ?? field.description;
}

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
  const [visibleKeys, setVisibleKeys] = useState<Record<string, boolean>>({});

  const clearKeyDraft = (provider: string) => {
    setKeys((current) => {
      const next = { ...current };
      delete next[provider];
      return next;
    });
    setVisibleKeys((current) => ({ ...current, [provider]: false }));
  };

  const revealKey = async (connection: ProviderConnection) => {
    const provider = connection.provider;
    const hasDraft = Object.hasOwn(keys, provider);
    const keyIsVisible = visibleKeys[provider] ?? false;
    if (!connection.credential_configured || (hasDraft && keys[provider].length > 0)) {
      setVisibleKeys((current) => ({ ...current, [provider]: !keyIsVisible }));
      return;
    }
    if (keyIsVisible) {
      setVisibleKeys((current) => ({ ...current, [provider]: false }));
      return;
    }

    setBusy((current) => ({ ...current, [provider]: "reveal" }));
    onNotice(null);
    try {
      const { api_key } = await revealProviderCredential(provider);
      setKeys((current) => ({ ...current, [provider]: api_key }));
      setVisibleKeys((current) => ({ ...current, [provider]: true }));
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      setBusy((current) => ({ ...current, [provider]: null }));
    }
  };

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
        const hasKeyDraft = Object.hasOwn(keys, connection.provider);
        const keyIsVisible = visibleKeys[connection.provider] ?? false;
        const apiKeyValue = hasKeyDraft
          ? keys[connection.provider]
          : connection.credential_configured
            ? MASKED_API_KEY
            : "";
        const VisibilityIcon = keyIsVisible ? EyeOff : Eye;
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
                <div className="provider-api-key">
                  <input
                    type={keyIsVisible ? "text" : "password"}
                    autoComplete="new-password"
                    value={apiKeyValue}
                    placeholder="输入 API Key"
                    onFocus={() => {
                      if (connection.credential_configured && !hasKeyDraft) {
                        setKeys((current) => ({ ...current, [connection.provider]: "" }));
                      }
                    }}
                    onBlur={() => {
                      if (keys[connection.provider] === "") clearKeyDraft(connection.provider);
                    }}
                    onChange={(event) =>
                      setKeys((current) => ({
                        ...current,
                        [connection.provider]: event.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    className="icon-button"
                    disabled={Boolean(state)}
                    onClick={() => void revealKey(connection)}
                    aria-label={`${keyIsVisible ? "隐藏" : "显示"} ${connection.name} API Key`}
                    title={`${keyIsVisible ? "隐藏" : "显示"} API Key`}
                  >
                    <VisibilityIcon aria-hidden="true" />
                  </button>
                </div>
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
                      async () => {
                        const updated = await deleteProviderCredential(connection.provider);
                        clearKeyDraft(connection.provider);
                        return updated;
                      },
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
                        const apiKey = hasKeyDraft ? keys[connection.provider].trim() : undefined;
                        const updated = await saveProviderConnection(connection.provider, {
                          ...(apiKey ? { api_key: apiKey } : {}),
                          base_url: urls[connection.provider],
                        });
                        clearKeyDraft(connection.provider);
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
      {COMING_SOON_PROVIDERS.map((provider) => (
        <article className="provider-row provider-row--unavailable" key={provider.provider}>
          <header className="provider-heading">
            <div>
              <span className="provider-monogram" aria-hidden="true">
                {provider.name.slice(0, 1)}
              </span>
              <div>
                <h2>{provider.name}</h2>
                <p>服务接入准备中</p>
              </div>
            </div>
            <span className="connection-state is-unavailable">
              <i aria-hidden="true" />
              尚未开放
            </span>
          </header>
          <p className="provider-unavailable-copy">
            API 配置、凭据保存与连通性验证将在服务接入开放后提供。
          </p>
        </article>
      ))}
    </div>
  );
}

function PromptMirrorBatchPanel({
  onRefresh,
  onNotice,
}: {
  onRefresh: (prompts: PromptRecord[]) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [availability, setAvailability] = useState<PromptMirrorBatchAvailability | null>(null);
  const [batch, setBatch] = useState<PromptMirrorBatch | null>(null);
  const [starting, setStarting] = useState(false);

  const refreshPrompts = useCallback(async () => {
    onRefresh(await fetchPrompts());
  }, [onRefresh]);

  useEffect(() => {
    let active = true;
    fetchPromptMirrorBatchAvailability()
      .then((next) => active && setAvailability(next))
      .catch((error: unknown) => active && setAvailability({
        available: false,
        reason: errorMessage(error),
        model_id: null,
      }));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (batch?.state !== "running") return;
    let active = true;
    const update = async () => {
      try {
        const next = await fetchPromptMirrorBatch(batch.id);
        if (!active) return;
        setBatch(next);
        if (next.state === "completed") await refreshPrompts();
      } catch (error) {
        if (active) onNotice({ kind: "error", text: errorMessage(error) });
      }
    };
    void update();
    const interval = window.setInterval(() => void update(), 500);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [batch?.id, batch?.state, onNotice, refreshPrompts]);

  const run = async (operation: () => Promise<PromptMirrorBatch>) => {
    setStarting(true);
    onNotice(null);
    try {
      const next = await operation();
      setBatch(next);
      if (next.state === "completed") await refreshPrompts();
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
      const nextAvailability = await fetchPromptMirrorBatchAvailability().catch(() => null);
      if (nextAvailability) setAvailability(nextAvailability);
    } finally {
      setStarting(false);
    }
  };

  const unavailableReason = availability?.reason ?? "正在检查翻译准备状态。";
  const canStart = availability?.available === true && batch?.state !== "running" && !starting;
  const failures = batch?.progress.failure ?? 0;

  return (
    <section className="prompt-mirror-batch" aria-labelledby="prompt-mirror-batch-title">
      <header className="settings-section-heading">
        <div>
          <span>CHINESE PROMPT MIRRORS</span>
          <h2 id="prompt-mirror-batch-title">批量生成中文镜像</h2>
        </div>
        <span>{availability?.available ? "可用" : "不可用"}</span>
      </header>
      <p>
        仅处理缺失或过期的镜像。生成过程不会修改英文运行时 Prompt。
      </p>
      <div className="prompt-mirror-batch-actions">
        <button
          type="button"
          className="button-primary"
          disabled={!canStart}
          onClick={() => void run(startPromptMirrorBatch)}
        >
          {starting || batch?.state === "running" ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Languages aria-hidden="true" />}
          生成中文镜像
        </button>
        {batch?.state === "completed" && failures > 0 ? (
          <button
            type="button"
            className="button-secondary"
            disabled={!canStart}
            onClick={() => void run(() => retryPromptMirrorBatch(batch.id))}
          >
            <RefreshCw aria-hidden="true" />
            重试失败项
          </button>
        ) : null}
        {availability?.available ? <small>使用 {availability.model_id}</small> : <small>{unavailableReason}</small>}
      </div>
      {batch ? (
        <div className="prompt-mirror-batch-results" role="status" aria-live="polite">
          <p>
            共 {batch.progress.total} 项 · 已完成 {batch.progress.success} 项 · 失败 {batch.progress.failure} 项 · 等待 {batch.progress.pending} 项 · 跳过 {batch.progress.skipped} 项
          </p>
          <ul>
            {batch.items.map((item) => (
              <li key={item.prompt_id} className={`is-${item.state}`}>
                <span>{item.name}</span>
                <strong>{BATCH_ITEM_LABELS[item.state]}</strong>
                {item.error ? <small>{item.error}</small> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function PromptLibraryView({
  prompts,
  onChange,
  onRefresh,
  onNotice,
}: {
  prompts: PromptRecord[];
  onChange: (prompt: PromptRecord) => void;
  onRefresh: (prompts: PromptRecord[]) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<SelectedPrompt | null>(null);
  const [languageByPrompt, setLanguageByPrompt] = useState<Record<string, PromptLanguage>>({});
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
  const workflowDirectory = useMemo(
    () => [...workflows].map(([workflow, stages]) => ({
      workflow,
      count: [...stages.values()].reduce((total, items) => total + items.length, 0),
    })),
    [workflows],
  );

  useEffect(() => {
    if (!selected) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) setSelected(null);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [saving, selected]);

  useEffect(() => {
    if (!selected) return;
    const root = document.documentElement;
    const body = document.body;
    const rootOverflow = root.style.overflow;
    const bodyOverflow = body.style.overflow;

    root.style.overflow = "hidden";
    body.style.overflow = "hidden";
    return () => {
      root.style.overflow = rootOverflow;
      body.style.overflow = bodyOverflow;
    };
  }, [selected]);

  const open = (prompt: PromptRecord, language: PromptLanguage) => {
    const mirror = chineseMirrorFor(prompt);
    setSelected({ prompt, language });
    setDraft(language === "zh" && mirror.state === "ready" ? mirror.text ?? "" : prompt.text);
    setEditorNotice(null);
    onNotice(null);
  };

  const jumpToWorkflow = (workflow: string) => {
    const target = document.getElementById(`prompt-workflow-${workflow}`);
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
    target?.focus({ preventScroll: true });
  };

  const submit = async () => {
    if (!selected || selected.language !== "en") return;
    setSaving(true);
    setEditorNotice(null);
    try {
      const updated = await savePrompt(selected.prompt.id, draft);
      onChange(updated);
      setSelected({ prompt: updated, language: "en" });
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

  const synchronize = async () => {
    if (!selected || selected.language !== "zh") return;
    setSaving(true);
    setEditorNotice(null);
    try {
      const updated = await synchronizePrompt(
        selected.prompt.id,
        draft,
        selected.prompt.source_revision,
      );
      onChange(updated);
      setSelected({ prompt: updated, language: "zh" });
      setDraft(chineseMirrorFor(updated).text ?? "");
      setEditorNotice({ kind: "success", text: `${updated.name} 已同步到英文版本` });
      onNotice({ kind: "success", text: `${updated.name} 已同步到英文版本` });
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
      <PromptMirrorBatchPanel onRefresh={onRefresh} onNotice={onNotice} />
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

      {workflowDirectory.length > 0 ? (
        <nav className="prompt-directory" aria-label="Prompt 目录">
          <span>目录</span>
          <div>
            {workflowDirectory.map(({ workflow, count }) => (
              <button type="button" key={workflow} onClick={() => jumpToWorkflow(workflow)}>
                {WORKFLOW_LABELS[workflow] ?? workflow}
                <small>{count}</small>
              </button>
            ))}
          </div>
        </nav>
      ) : null}

      <div className="prompt-catalogue">
        {[...workflows].map(([workflow, stages]) => (
          <section
            className="prompt-workflow"
            data-particle-identity={workflow}
            key={workflow}
          >
            <header>
              <span>{workflow}</span>
              <h2 className="prompt-workflow-title" id={`prompt-workflow-${workflow}`} tabIndex={-1}>
                {WORKFLOW_LABELS[workflow] ?? workflow}
              </h2>
            </header>
            {[...stages].map(([stage, items]) => (
              <div className="prompt-stage" key={stage}>
                <div className="prompt-stage-heading">
                  <h3>{STAGE_LABELS[stage] ?? stage}</h3>
                  <span>{items.length}</span>
                </div>
                <div className="prompt-grid">
                  {items.map((prompt) => {
                    const language = languageByPrompt[prompt.id] ?? "en";
                    const mirror = chineseMirrorFor(prompt);
                    const chineseView = language === "zh";
                    const preview = chineseView
                      ? mirror.state === "ready"
                        ? mirror.text ?? ""
                        : CHINESE_MIRROR_LABELS[mirror.state]
                      : prompt.text;
                    return (
                      <div className="prompt-card-shell" key={prompt.id}>
                        <article className="prompt-card">
                          <button
                            type="button"
                            className="prompt-card-main"
                            aria-label={`打开 ${prompt.name}`}
                            onClick={() => open(prompt, language)}
                          >
                            <span className="prompt-card-topline">
                              <span>{String(prompt.order).padStart(2, "0")}</span>
                              <span>{INVOCATION_LABELS[prompt.invocation_type]}</span>
                            </span>
                            <strong>{prompt.name}</strong>
                            <span className="prompt-description">{prompt.description}</span>
                            <code>{preview.replace(/\s+/g, " ").trim().slice(0, 190)}</code>
                          </button>
                          <footer className="prompt-card-footer">
                            <span className={`prompt-mirror-state is-${mirror.state}`}>
                              {CHINESE_MIRROR_LABELS[mirror.state]}
                            </span>
                            <button
                              type="button"
                              className="prompt-edit"
                              onClick={() => open(prompt, language)}
                            >
                              <Pencil aria-hidden="true" />{chineseView ? "查看镜像" : "编辑"}
                            </button>
                            <div className="prompt-card-language" role="group" aria-label={`${prompt.name} 语言`}>
                              <button
                                type="button"
                                className={!chineseView ? "is-active" : undefined}
                                aria-pressed={!chineseView}
                                onClick={() => setLanguageByPrompt((current) => ({ ...current, [prompt.id]: "en" }))}
                              >
                                English
                              </button>
                              <button
                                type="button"
                                className={chineseView ? "is-active" : undefined}
                                aria-pressed={chineseView}
                                onClick={() => setLanguageByPrompt((current) => ({ ...current, [prompt.id]: "zh" }))}
                              >
                                中文
                              </button>
                            </div>
                          </footer>
                        </article>
                      </div>
                    );
                  })}
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
                <span>{selected.language === "zh" ? "中文镜像" : selected.prompt.id}</span>
                <h2 id="prompt-editor-title">{selected.prompt.name}</h2>
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
                <span>{WORKFLOW_LABELS[selected.prompt.workflow] ?? selected.prompt.workflow}</span>
                <span>{STAGE_LABELS[selected.prompt.stage] ?? selected.prompt.stage}</span>
                <span>{INVOCATION_LABELS[selected.prompt.invocation_type]}</span>
                <span>{selected.language === "zh" ? "中文镜像" : "英文运行时原文"}</span>
                {selected.prompt.template_variables.map((variable) => <code key={variable}>{`{${variable}}`}</code>)}
              </div>
              <NoticeBar
                notice={editorNotice}
                onClose={() => setEditorNotice(null)}
              />
            </div>
            {selected.language === "zh" && chineseMirrorFor(selected.prompt).state !== "ready" ? (
              <div className="prompt-mirror-unavailable" role="status">
                {CHINESE_MIRROR_LABELS[chineseMirrorFor(selected.prompt).state]}
              </div>
            ) : (
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                spellCheck={false}
                autoFocus
              />
            )}
            <footer>
              <span>{draft.length.toLocaleString()} 字符</span>
              {selected.language === "en" ? (
                <div>
                  <button type="button" className="button-secondary" disabled={saving} onClick={() => setDraft(selected.prompt.text)}>
                    撤销修改
                  </button>
                  <button type="button" className="button-primary" disabled={saving || draft === selected.prompt.text} onClick={submit}>
                    {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    保存 Prompt
                  </button>
                </div>
              ) : chineseMirrorFor(selected.prompt).state === "ready" ? (
                <div>
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={saving}
                    onClick={() => setDraft(chineseMirrorFor(selected.prompt).text ?? "")}
                  >
                    撤销修改
                  </button>
                  <button
                    type="button"
                    className="button-primary"
                    disabled={saving || draft === chineseMirrorFor(selected.prompt).text}
                    onClick={synchronize}
                  >
                    {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
                    同步到英文版本
                  </button>
                </div>
              ) : null}
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}

function PromptTranslationInstructionView({
  translationInstruction,
  configuration,
  onChange,
  onNotice,
}: {
  translationInstruction: PromptTranslationInstruction;
  configuration: DefaultConfiguration;
  onChange: (instruction: PromptTranslationInstruction) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [draft, setDraft] = useState(translationInstruction.instruction);
  const [saving, setSaving] = useState(false);
  const activeTextModel = configuration.models.find(
    (model) => model.id === configuration.bindings.active_text_model,
  );
  const textModelConnection = configuration.readiness.connections.find(
    (connection) => connection.provider === activeTextModel?.provider,
  );
  const defaultTextModelReady = activeTextModel?.provider === "local" ||
    textModelConnection?.verification_status === "valid";
  const dirty = draft !== translationInstruction.instruction;

  const save = async () => {
    setSaving(true);
    onNotice(null);
    try {
      const updated = await savePromptTranslationInstruction(draft);
      onChange(updated);
      setDraft(updated.instruction);
      onNotice({ kind: "success", text: "Prompt 翻译指令已保存" });
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="translation-instruction-editor">
      <section aria-labelledby="translation-instruction-title">
        <header className="settings-section-heading">
          <div>
            <span>TRANSLATION CONFIGURATION</span>
            <h2 id="translation-instruction-title">Prompt 翻译指令</h2>
          </div>
          <span>{translationInstruction.configured ? "已配置" : "未配置"}</span>
        </header>
        <p className="translation-instruction-copy">
          仅供未来的 Prompt 中英同步操作调用。它不是 Prompt 库条目，也不会进入 Discovery 运行时或启动快照。
        </p>
        <label className="translation-instruction-field" htmlFor="prompt-translation-instruction">
          <span>Prompt 翻译指令</span>
          <textarea
            id="prompt-translation-instruction"
            value={draft}
            rows={12}
            spellCheck={false}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
      </section>

      <section className="translation-readiness" aria-labelledby="translation-readiness-title">
        <header className="settings-section-heading">
          <div>
            <span>AVAILABILITY</span>
            <h2 id="translation-readiness-title">同步准备状态</h2>
          </div>
          <span>{translationInstruction.configured && defaultTextModelReady ? "可用" : "不可用"}</span>
        </header>
        <dl>
          <div>
            <dt>翻译指令</dt>
            <dd className={translationInstruction.configured ? "is-ready" : ""}>
              {translationInstruction.configured ? "已配置" : "尚未配置 Prompt 翻译指令"}
            </dd>
          </div>
          <div>
            <dt>默认文本模型</dt>
            <dd className={defaultTextModelReady ? "is-ready" : ""}>
              {defaultTextModelReady
                ? `${activeTextModel?.id} 已验证`
                : "默认文本模型尚不可用"}
            </dd>
          </div>
        </dl>
        <p className={translationInstruction.configured && defaultTextModelReady ? "is-ready" : ""}>
          {translationInstruction.configured && defaultTextModelReady
            ? "翻译操作可用"
            : "完成以上两项配置后，才能执行 Prompt 同步。"}
        </p>
      </section>

      <div className="settings-save-dock">
        <span>{draft.length.toLocaleString()} 字符</span>
        <div>
          <button
            type="button"
            className="button-secondary"
            disabled={!dirty || saving}
            onClick={() => setDraft(translationInstruction.instruction)}
          >
            放弃修改
          </button>
          <button type="button" className="button-primary" disabled={!dirty || saving} onClick={save}>
            {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
            保存翻译指令
          </button>
        </div>
      </div>
    </div>
  );
}

function DiscoveryInputConversionPromptView({
  conversionPrompt,
  configuration,
  onChange,
  onNotice,
}: {
  conversionPrompt: DiscoveryInputConversionPrompt;
  configuration: DefaultConfiguration;
  onChange: (prompt: DiscoveryInputConversionPrompt) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [draft, setDraft] = useState(conversionPrompt.instruction);
  const [saving, setSaving] = useState(false);
  const activeTextModel = configuration.models.find(
    (model) => model.id === configuration.bindings.active_text_model,
  );
  const dirty = draft !== conversionPrompt.instruction;

  const save = async () => {
    setSaving(true);
    onNotice(null);
    try {
      const updated = await saveDiscoveryInputConversionPrompt(draft);
      onChange(updated);
      setDraft(updated.instruction);
      onNotice({ kind: "success", text: "Discovery Input 转换指令已保存" });
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="translation-instruction-editor discovery-input-conversion-prompt-editor">
      <section aria-labelledby="discovery-input-conversion-prompt-title">
        <header className="settings-section-heading">
          <div>
            <span>DISCOVERY INPUT CONFIGURATION</span>
            <h2 id="discovery-input-conversion-prompt-title">Discovery Input 转换指令</h2>
          </div>
          <span>{conversionPrompt.configured ? "已配置" : "未配置"}</span>
        </header>
        <p className="translation-instruction-copy">
          仅供自主发现空间中的显式转换调用。它不是 Prompt 库条目，不会自动保存转换草稿，也不会启动 Discovery 流程。
        </p>
        <label className="translation-instruction-field" htmlFor="discovery-input-conversion-prompt">
          <span>Discovery Input 转换指令</span>
          <textarea
            id="discovery-input-conversion-prompt"
            value={draft}
            rows={12}
            spellCheck={false}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
      </section>

      <section className="translation-readiness" aria-labelledby="discovery-input-conversion-details-title">
        <header className="settings-section-heading">
          <div>
            <span>EXECUTION DETAILS</span>
            <h2 id="discovery-input-conversion-details-title">转换方式</h2>
          </div>
          <span>{conversionPrompt.configured ? "可配置" : "待配置"}</span>
        </header>
        <dl>
          <div>
            <dt>调用方式</dt>
            <dd>在已保存的 Preparation 中手动点击转换</dd>
          </div>
          <div>
            <dt>文本模型</dt>
            <dd className={activeTextModel ? "is-ready" : ""}>
              {activeTextModel?.id ?? "默认文本模型未指定"}
            </dd>
          </div>
        </dl>
        <p className={conversionPrompt.configured ? "is-ready" : ""}>
          {conversionPrompt.configured
            ? "转换结果将作为可编辑草稿打开，只有显式保存才会形成输入修订版。"
            : "先保存转换指令，才能将原始资料转换为 Formatted Discovery Input。"}
        </p>
      </section>

      <div className="settings-save-dock">
        <span>{draft.length.toLocaleString()} 字符</span>
        <div>
          <button
            type="button"
            className="button-secondary"
            disabled={!dirty || saving}
            onClick={() => setDraft(conversionPrompt.instruction)}
          >
            放弃修改
          </button>
          <button type="button" className="button-primary" disabled={!dirty || saving} onClick={save}>
            {saving ? <LoaderCircle className="is-spinning" aria-hidden="true" /> : <Save aria-hidden="true" />}
            保存转换指令
          </button>
        </div>
      </div>
    </div>
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

function ParameterHelp({ field }: { field: ParameterField }) {
  const tooltipId = `parameter-help-${field.path.replaceAll(".", "-")}`;
  return (
    <details className="parameter-help">
      <summary aria-describedby={tooltipId} aria-label={`查看“${field.description}”的说明`}>
        <CircleHelp aria-hidden="true" />
      </summary>
      <span className="parameter-tooltip" id={tooltipId} role="tooltip">
        {parameterHelpFor(field)}
      </span>
    </details>
  );
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
                <div className="parameter-label">
                  <label htmlFor={`parameter-${field.path}`}>{field.description}</label>
                  <ParameterHelp field={field} />
                </div>
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

export function SystemSettings({
  section,
}: {
  section: SettingsSection;
}) {
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [prompts, setPrompts] = useState<PromptRecord[]>([]);
  const [translationInstruction, setTranslationInstruction] = useState<PromptTranslationInstruction | null>(null);
  const [conversionPrompt, setConversionPrompt] = useState<DiscoveryInputConversionPrompt | null>(null);
  const [configuration, setConfiguration] = useState<DefaultConfiguration | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    setNotice(null);
  }, [section]);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchProviderConnections(),
      fetchPrompts(),
      fetchPromptTranslationInstruction(),
      fetchDiscoveryInputConversionPrompt(),
      fetchDefaultConfiguration(),
    ])
      .then(([providerConnections, registeredPrompts, translation, conversion, defaults]) => {
        if (!active) return;
        setConnections(providerConnections);
        setPrompts(registeredPrompts);
        setTranslationInstruction(translation);
        setConversionPrompt(conversion);
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
    <section className="system-settings" aria-label="系统设置">
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
              onRefresh={setPrompts}
              onNotice={setNotice}
            />
          ) : null}
          {section === "translation" && translationInstruction && configuration ? (
            <PromptTranslationInstructionView
              translationInstruction={translationInstruction}
              configuration={configuration}
              onChange={setTranslationInstruction}
              onNotice={setNotice}
            />
          ) : null}
          {section === "conversion" && conversionPrompt && configuration ? (
            <DiscoveryInputConversionPromptView
              conversionPrompt={conversionPrompt}
              configuration={configuration}
              onChange={setConversionPrompt}
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
