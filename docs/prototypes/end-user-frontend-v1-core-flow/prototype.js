// Selected milestone-focused core flow reference. Prototype state lives in the URL.

const app = document.querySelector("#app");

const STATES = [
  "create",
  "queued",
  "running",
  "stopping",
  "cancelled",
  "stopped",
  "interrupted",
  "failed",
  "completed",
];

const WORKFLOWS = {
  deep: {
    key: "deep",
    apiKey: "deep_research",
    area: "深度研究",
    noun: "任务",
    id: "DR-0198",
    nextId: "DR-0199",
    title: "哪些固态电解质体系拥有最有力的室温循环证据？",
    promptLabel: "研究问题",
    progressLabel: "正在评估来源质量",
    percent: 46,
    duration: "已用时 38 分钟",
    milestones: [
      ["界定问题范围", "检索边界已确认"],
      ["检索证据", "已收集 31 个来源"],
      ["评估来源", "31 个来源中已保留 18 个"],
      ["综合证据", "等待已评估来源"],
      ["生成引用报告", "等待综合结果"],
    ],
    activity: [
      ["10:18:42", "已完成 4 个证据索引的检索"],
      ["10:19:06", "已移除 7 条重复记录"],
      ["10:20:14", "正在评估第 17/31 个来源"],
      ["10:20:20", "已保留 DOI 10.1016/j.ensm.2025.103201"],
      ["10:20:31", "正在评估第 18/31 个来源"],
    ],
  },
  discovery: {
    key: "discovery",
    apiKey: "discovery",
    area: "科学发现",
    noun: "任务",
    id: "DS-0248",
    nextId: "DS-0249",
    title: "在不牺牲催化剂选择性的前提下提升低温 CO2 转化率",
    promptLabel: "研究目标",
    progressLabel: "正在评估第 2 轮候选方案",
    percent: 58,
    duration: "已用时 1 小时 12 分钟",
    milestones: [
      ["验证研究简报", "已接受输入材料与任务预算"],
      ["调研文献", "已保留 42 篇参考文献"],
      ["生成候选方案", "第 2 轮生成了 8 个候选方案"],
      ["评估候选方案", "已完成 8 项实验中的 5 项"],
      ["选择结果", "等待评估完成"],
      ["整理论文", "等待选定结果"],
    ],
    activity: [
      ["10:18:42", "实验 IR-12 已完成：产率 79.4%"],
      ["10:19:06", "已为 IR-17 启动独立随机种子 3"],
      ["10:20:14", "IR-17 随机种子 3 已通过验证检查"],
      ["10:20:20", "正在更新第 2 轮证据摘要"],
      ["10:20:31", "正在评估候选方案 IR-18"],
    ],
  },
};

const STATE_LABELS = {
  create: "新建",
  queued: "排队中",
  running: "运行中",
  stopping: "正在停止",
  cancelled: "已取消",
  stopped: "已停止",
  interrupted: "已中断",
  failed: "失败",
  completed: "已完成",
  pending: "待开始",
  active: "进行中",
};

const ACTIONS = {
  queued: ["stop"],
  running: ["stop"],
  stopping: [],
  cancelled: ["run_again"],
  completed: ["run_again"],
  failed: ["run_again"],
  stopped: ["run_again"],
  interrupted: ["run_again"],
};

function readModel() {
  const params = new URLSearchParams(window.location.search);
  const workflow = WORKFLOWS[params.get("workflow")] ? params.get("workflow") : "deep";
  const state = STATES.includes(params.get("state")) ? params.get("state") : "create";
  const defaultView = state === "completed" ? "results" : "progress";
  const view = ["progress", "results"].includes(params.get("view")) ? params.get("view") : defaultView;

  return {
    workflow,
    state,
    view,
    attempt: Number(params.get("attempt")) || 1,
    source: params.get("source") === "1",
    older: params.get("older") === "1",
  };
}

function updateModel(changes) {
  const url = new URL(window.location.href);

  Object.entries(changes).forEach(([key, value]) => {
    if (value === null || value === false || value === undefined) {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, value === true ? "1" : String(value));
    }
  });

  window.history.replaceState({}, "", url);
  render();
}

function allowedActions(model) {
  const actions = [...(ACTIONS[model.state] || [])];
  if (model.workflow === "discovery" && ["stopped", "interrupted"].includes(model.state)) {
    actions.unshift("resume");
  }
  return actions;
}

function assertStateModel() {
  console.assert(!allowedActions({ workflow: "deep", state: "stopped" }).includes("resume"));
  console.assert(allowedActions({ workflow: "discovery", state: "interrupted" }).includes("resume"));
  console.assert(allowedActions({ workflow: "deep", state: "failed" }).includes("run_again"));
  console.assert(allowedActions({ workflow: "discovery", state: "running" }).includes("stop"));
}

function statusBadge(state) {
  return `<span class="work-status status-${state}"><span aria-hidden="true"></span>${STATE_LABELS[state]}</span>`;
}

function productActions(model) {
  return allowedActions(model)
    .map((action) => {
      if (action === "stop") {
        return `<button class="danger-button" type="button" data-action="request-stop"><span class="stop-icon" aria-hidden="true"></span>停止</button>`;
      }
      if (action === "resume") {
        return `<button class="primary-button" type="button" data-action="resume">恢复</button>`;
      }
      return `<button class="${model.state === "completed" ? "quiet-button" : "primary-button"}" type="button" data-action="run-again">再次运行</button>`;
    })
    .join("");
}

function workflowNav(model) {
  return `
    <aside class="a-sidebar">
      <a class="brand" href="./" aria-label="Vegapunk 首页">
        <span class="brand-mark" aria-hidden="true">V</span>
        <span>Vegapunk</span>
      </a>
      <nav class="workflow-nav" aria-label="产品区域">
        <p class="nav-label">工作区</p>
        <button class="${model.workflow === "deep" ? "active" : ""}" type="button" data-action="workflow" data-workflow="deep" ${model.workflow === "deep" ? 'aria-current="page"' : ""}><span aria-hidden="true">DR</span>深度研究</button>
        <button class="${model.workflow === "discovery" ? "active" : ""}" type="button" data-action="workflow" data-workflow="discovery" ${model.workflow === "discovery" ? 'aria-current="page"' : ""}><span aria-hidden="true">DS</span>科学发现</button>
      </nav>
      <div class="recent-work">
        <p class="nav-label">最近任务</p>
        <button class="recent-item selected" type="button"><strong>${WORKFLOWS[model.workflow].title}</strong><small>${model.state === "create" ? "新任务" : STATE_LABELS[model.state]}</small></button>
        <button class="recent-item" type="button"><strong>膜选择性研究</strong><small>昨天已完成</small></button>
      </div>
      <button class="account-button" type="button"><span class="avatar" aria-hidden="true">KR</span><span><strong>研究者</strong><small>本地工作区</small></span><span aria-hidden="true">&#x22EF;</span></button>
    </aside>`;
}

function createFields(model) {
  const workflow = WORKFLOWS[model.workflow];
  const workflowFields = model.workflow === "discovery"
    ? `<div class="field-row two-columns">
        <label>研究领域<input name="domain" value="非均相催化" /></label>
        <label>约束条件<input name="constraints" value="低于 120 C；选择性保持在 88% 以上" /></label>
      </div>
      <label>研究背景<textarea name="background" rows="3">既往试验表明，双金属活性位点可以提高转化率，但可能会降低选择性。</textarea></label>`
    : "";
  const uploadFields = model.workflow === "deep"
    ? `<label>参考文件 <span class="optional">可选</span><input name="reference" type="file" accept=".pdf,.txt,.md" /></label>`
    : `<div class="upload-grid"><label>参考资料<input name="references" type="file" multiple accept=".pdf,.txt,.md" /></label><label>数据集<input name="dataset" type="file" multiple accept=".csv,.json,.zip" /></label><label>基线代码<input name="baseline" type="file" accept=".zip" /></label></div>`;
  const settings = model.workflow === "deep"
    ? `<p class="settings-note">深度研究使用已批准的问答工作流，不提供算法调优。</p>`
    : `<div class="settings-grid"><label>轮数<input name="rounds" type="number" min="1" max="10" value="3" /></label><label>候选数<input name="candidates" type="number" min="1" max="5" value="4" /></label><label>每项实验运行次数<input name="runs" type="number" min="1" max="2" value="2" /></label><label class="check-label"><input name="survey" type="checkbox" checked />文献支撑</label></div>`;

  return `
    <form class="create-form form-a" data-workflow="${model.workflow}">
      <section class="form-section" data-step="1">
        <div class="form-section-heading"><span>01</span><div><p>研究简报</p><small>必填</small></div></div>
        <div class="form-fields">
          <label>${workflow.promptLabel}<textarea name="prompt" rows="5" required>${workflow.title}</textarea></label>
          ${workflowFields}
        </div>
      </section>
      <section class="form-section" data-step="2">
        <div class="form-section-heading"><span>02</span><div><p>输入材料</p><small>创建任务时将被占用</small></div></div>
        <div class="form-fields">${uploadFields}</div>
      </section>
      <section class="form-section" data-step="3">
        <div class="form-section-heading"><span>03</span><div><p>运行设置</p><small>随此${workflow.noun}保存</small></div></div>
        <div class="form-fields">
          <div class="field-row two-columns"><label>模型<select name="model"><option>GPT 5.6</option></select></label><label>凭据<select name="credential"><option>个人 Relay 密钥 / 83af</option></select></label></div>
          ${settings}
        </div>
      </section>
      <div class="create-submit"><p><strong>${model.workflow === "deep" ? "1 个研究问题" : "3 轮 / 最多 24 次实验运行"}</strong><span>创建后输入内容不可更改。</span></p><button class="primary-button launch-button" type="submit">创建${workflow.noun}</button></div>
    </form>`;
}

function progressFor(model) {
  const workflow = WORKFLOWS[model.workflow];
  const activeIndex = model.workflow === "deep" ? 2 : 3;

  return workflow.milestones.map(([label, summary], index) => {
    let state = "pending";
    if (model.state === "completed") state = "completed";
    else if (index < activeIndex && (!["create", "queued", "cancelled"].includes(model.state) || (model.state === "queued" && model.attempt > 1))) state = "completed";
    else if (index === activeIndex && ["running", "stopping"].includes(model.state)) state = "active";
    else if (index === activeIndex && ["stopped", "interrupted", "failed"].includes(model.state)) state = model.state;

    return { label, summary: state === "pending" && !(model.attempt > 1 && index === activeIndex) ? "未开始" : summary, state, index, isCurrent: index === activeIndex };
  });
}

function progressPercent(model) {
  if (model.state === "completed") return 100;
  if (["queued", "cancelled"].includes(model.state)) return model.state === "queued" && model.attempt > 1 ? WORKFLOWS[model.workflow].percent : 0;
  return WORKFLOWS[model.workflow].percent;
}

function progressHeadline(model) {
  const workflow = WORKFLOWS[model.workflow];
  return {
    queued: model.attempt > 1 ? `已排队，将恢复${workflow.milestones[model.workflow === "deep" ? 2 : 3][0]}` : "正在等待可用资源",
    stopping: "正在安全完成当前操作",
    cancelled: "执行前已取消",
    stopped: "任务已停止，进度已保留",
    interrupted: "执行已中断",
    failed: "执行失败",
    completed: "所有里程碑均已完成",
  }[model.state] || workflow.progressLabel;
}

function timeline(model, mode = "ledger") {
  const milestones = progressFor(model);
  return `
    <ol class="timeline timeline-${mode}">
      ${milestones.map((milestone) => `
        <li class="milestone milestone-${milestone.state}">
          <span class="milestone-marker" aria-hidden="true">${milestone.state === "completed" ? "&#x2713;" : milestone.index + 1}</span>
          <div><div class="milestone-title"><strong>${milestone.label}</strong><span>${STATE_LABELS[milestone.state] || milestone.state}</span></div><p>${milestone.summary}</p>${model.attempt > 1 && milestone.isCurrent ? `<small>执行尝试 ${model.attempt}${model.state === "queued" ? " 已排队" : ""}</small>` : ""}</div>
        </li>`).join("")}
    </ol>`;
}

function activity(model) {
  const workflow = WORKFLOWS[model.workflow];
  const older = model.older
    ? [["10:17:08", "执行环境已就绪"], ["10:17:21", "凭据能力检查已通过"]]
    : [];
  const stateMessage = {
    queued: model.attempt > 1 ? `执行尝试 ${model.attempt} 已排队，等待恢复` : "正在等待可用资源",
    running: workflow.progressLabel,
    stopping: "已请求安全停止，正在保留当前工作",
    cancelled: "执行开始前已取消",
    stopped: "当前操作完成后已停止",
    interrupted: "执行进程意外中断",
    failed: "任务结束：provider_authentication_failed",
    completed: "所有里程碑均已完成并保存",
  }[model.state];
  const queuedMessages = [["09:42:11", "已接受提交并保留输入材料"], ["09:42:12", "正在等待可用资源"]];
  const messages = ["queued", "cancelled"].includes(model.state) && model.attempt === 1
    ? queuedMessages
    : [...older, ...workflow.activity];

  return `
    <div class="activity-heading"><div><p class="section-kicker">研究活动</p><h2>实时输出</h2></div><span class="connection ${["queued", "running", "stopping"].includes(model.state) ? "is-live" : ""}">${["queued", "running", "stopping"].includes(model.state) ? "实时" : "已关闭"}</span></div>
    <div class="activity-log" role="log" aria-live="polite" aria-label="经过筛选的研究活动">
      ${messages.map(([time, message]) => `<p><time>${time}</time><span>${message}</span></p>`).join("")}
      ${stateMessage ? `<p class="activity-state"><time>10:20:44</time><strong>${stateMessage}</strong></p>` : ""}
    </div>
    <button class="text-button activity-history" type="button" data-action="toggle-activity">${model.older ? "隐藏早期活动" : "加载早期活动"}</button>`;
}

function stateNotice(model) {
  const workflow = WORKFLOWS[model.workflow];
  const notices = {
    stopping: ["已请求停止", "当前操作正在安全结束。在执行进程停止前，暂无其他可用操作。"],
    cancelled: ["启动前已取消", `此${workflow.noun}未获得执行资源。再次运行会基于相同的不可变提交创建新的任务标识。`],
    stopped: ["任务已安全停止", model.workflow === "discovery" ? "已完成的里程碑和执行尝试均已保留。恢复后将使用同一任务标识继续此任务。" : "已完成的证据仍然可用。深度研究无法可靠恢复，因此再次运行会创建一个新任务。"],
    interrupted: ["执行已中断", model.workflow === "discovery" ? "已核对持久化的完成标记。恢复后将从受影响的里程碑继续。" : "没有可用的可靠检查点。再次运行会基于保留的提交创建一个新任务。"],
    failed: ["提供商身份验证失败", "所选凭据无法授权此次模型调用。请替换或选择有效凭据，然后再次运行此任务。请求 ID：req_01J2F8M9"],
  };
  const notice = notices[model.state];
  return notice ? `<section class="state-notice notice-${model.state}" role="status"><div><strong>${notice[0]}</strong><p>${notice[1]}</p></div></section>` : "";
}

function results(model, compact = false) {
  const workflow = WORKFLOWS[model.workflow];
  if (model.state !== "completed") {
    return `<section class="empty-results"><p class="section-kicker">结果</p><h2>尚无最终结果</h2><p>当前任务处于${STATE_LABELS[model.state]}状态，尚无已完成的报告或选定结果。可用输入材料和里程碑历史仍保留在“进度”中。</p></section>`;
  }

  if (model.workflow === "deep") {
    return `
      <div class="result-evidence ${compact ? "is-compact" : ""}">
        <section class="finding-block"><p class="section-kicker">证据综合</p><h2>硫化物电解质在室温电导率方面领先，而氧化物体系拥有最有力的稳定性证据。</h2><p>在保留的 27 个来源中，没有任何一种体系同时在电导率、界面稳定性和可制造性上占优。报告识别出三个有证据支持的权衡区域，以及五项尚未解决的比较。</p><a class="inline-link" href="#report">打开引用报告</a></section>
        <section class="evidence-table-section"><div class="section-heading"><div><p class="section-kicker">证据基础</p><h2>各体系保留来源数量</h2></div><span class="method-label">27 个来源 / 2019-2026</span></div><div class="family-bars" role="img" aria-label="保留证据：硫化物 11 个来源，氧化物 9 个，聚合物 7 个"><div><span>硫化物</span><i style="--value: 100%"></i><strong>11</strong></div><div><span>氧化物</span><i style="--value: 82%"></i><strong>9</strong></div><div><span>聚合物</span><i style="--value: 64%"></i><strong>7</strong></div></div></section>
        <aside class="result-artifacts"><p class="section-kicker">研究产出</p><a class="artifact-row" href="#report"><span><strong>引用研究报告</strong><small>PDF / 1.4 MB</small></span><span aria-hidden="true">&#x2193;</span></a><a class="artifact-row" href="#sources"><span><strong>来源清单</strong><small>CSV / 18 KB</small></span><span aria-hidden="true">&#x2193;</span></a></aside>
      </div>`;
  }

  return `
    <div class="result-evidence ${compact ? "is-compact" : ""}">
      <section class="finding-block"><p class="section-kicker">选定结果</p><h2>IR-17 在不牺牲选择性的情况下，将验证产率提高了 23.5 个百分点。</h2><p>最佳配置在三个独立随机种子上的产率达到 84.7 ± 1.8%，基线为 61.2%。</p><a class="inline-link" href="#paper">阅读科学发现论文</a></section>
      <section class="evidence-table-section"><div class="section-heading"><div><p class="section-kicker">核心指标</p><h2>各轮验证产率</h2></div><span class="method-label">均值与 95% 置信区间</span></div><svg class="result-chart" viewBox="0 0 640 230" role="img" aria-labelledby="result-chart-title result-chart-desc"><title id="result-chart-title">三轮实验中验证产率持续提高</title><desc id="result-chart-desc">基线为 61.2%。第 1 轮为 69.8%，第 2 轮为 77.6%，第 3 轮为 84.7%。误差线表示 95% 置信区间。</desc><g class="result-grid"><line x1="62" y1="28" x2="610" y2="28"/><line x1="62" y1="75" x2="610" y2="75"/><line x1="62" y1="122" x2="610" y2="122"/><line x1="62" y1="169" x2="610" y2="169"/></g><path class="result-baseline" d="M62 163 H610"/><path class="result-series" d="M104 163 L258 123 L412 87 L566 53"/><g class="result-ci"><path d="M104 156 V170 M98 156 H110 M98 170 H110"/><path d="M258 112 V134 M252 112 H264 M252 134 H264"/><path d="M412 77 V97 M406 77 H418 M406 97 H418"/><path d="M566 45 V61 M560 45 H572 M560 61 H572"/></g><g class="result-dots"><circle cx="104" cy="163" r="5"/><circle cx="258" cy="123" r="5"/><circle cx="412" cy="87" r="5"/><circle cx="566" cy="53" r="6"/></g><g class="result-labels"><text x="20" y="32">90</text><text x="20" y="79">80</text><text x="20" y="126">70</text><text x="20" y="173">60</text><text x="14" y="15">产率 (%)</text><text x="84" y="211">基线</text><text x="234" y="211">第 1 轮</text><text x="388" y="211">第 2 轮</text><text x="542" y="211">第 3 轮</text><text x="520" y="38">84.7%</text><text x="462" y="158">基线 61.2%</text></g></svg></section>
      <aside class="result-artifacts"><p class="section-kicker">研究产出</p><a class="artifact-row" href="#paper"><span><strong>科学发现论文</strong><small>PDF / 2.8 MB</small></span><span aria-hidden="true">&#x2193;</span></a><a class="artifact-row" href="#bundle"><span><strong>可复现性材料包</strong><small>ZIP / 18.4 MB</small></span><span aria-hidden="true">&#x2193;</span></a><a class="artifact-row" href="#metrics"><span><strong>指标表</strong><small>CSV / 12 KB</small></span><span aria-hidden="true">&#x2193;</span></a></aside>
    </div>`;
}

function detailTabs(model) {
  return `<nav class="detail-tabs" aria-label="${WORKFLOWS[model.workflow].noun}视图" role="tablist"><button class="${model.view === "progress" ? "active" : ""}" type="button" role="tab" aria-selected="${model.view === "progress"}" data-action="view" data-view="progress">进度</button><button class="${model.view === "results" ? "active" : ""}" type="button" role="tab" aria-selected="${model.view === "results"}" data-action="view" data-view="results">结果</button></nav>`;
}

function identity(model) {
  const workflow = WORKFLOWS[model.workflow];
  const workId = model.source ? workflow.nextId : workflow.id;
  return `<section class="a-identity work-identity"><div><div class="eyebrow-row">${statusBadge(model.state)}<span>${workflow.area}${workflow.noun}</span>${model.attempt > 1 ? `<span>执行尝试 ${model.attempt}</span>` : ""}</div><h1>${workflow.title}</h1><p>${workId} / 创建于 2026 年 7 月 21 日 09:42${model.source ? ` / 基于 ${workflow.id} 再次运行` : ""}</p></div><div class="identity-actions">${productActions(model)}</div></section>`;
}

function CoreFlowReference(model) {
  const workflow = WORKFLOWS[model.workflow];
  const create = model.state === "create";
  return `
    <div class="variant variant-a core-a">
      ${workflowNav(model)}
      <main class="a-main">
        <header class="a-toolbar"><span>${workflow.area}</span><span aria-hidden="true">/</span><strong>${create ? `新建${workflow.noun}` : model.source ? workflow.nextId : workflow.id}</strong><div class="toolbar-actions">${create ? "" : `<button class="quiet-button" type="button" data-action="history">历史记录</button>`}</div></header>
        ${create ? `<section class="create-heading"><p class="section-kicker">新建${workflow.noun}</p><h1>${model.workflow === "deep" ? "研究一个科学问题" : "启动科学发现任务"}</h1><p>${model.workflow === "deep" ? "定义研究问题，并按需添加参考材料。" : "设置科学目标、不可变输入和有明确上限的任务参数。"}</p></section><div class="a-create-wrap">${createFields(model)}</div>` : `${identity(model)}${detailTabs(model)}${stateNotice(model)}${model.view === "results" ? `<div class="a-flow-results">${results(model)}</div>` : `<div class="a-flow-grid"><section class="timeline-panel"><div class="progress-overview"><div><p class="section-kicker">研究进度</p><h2>${progressHeadline(model)}</h2></div><strong>${progressPercent(model)}%</strong></div><div class="progress-track" aria-label="已完成 ${progressPercent(model)}%"><span style="--progress: ${progressPercent(model)}%"></span></div>${timeline(model)}</section><aside class="activity-panel">${activity(model)}</aside></div>`}`}
      </main>
    </div>`;
}

function PrototypeControls(model) {
  return `
    <aside class="prototype-bar" aria-label="原型控制">
      <strong>核心流程参考</strong>
      <span class="prototype-divider" aria-hidden="true"></span>
      <div class="prototype-workflows" role="group" aria-label="工作流"><button class="${model.workflow === "deep" ? "active" : ""}" type="button" data-action="workflow" data-workflow="deep">DR</button><button class="${model.workflow === "discovery" ? "active" : ""}" type="button" data-action="workflow" data-workflow="discovery">科学发现</button></div>
      <label><span class="sr-only">预览状态</span><select data-action="state" aria-label="预览状态">${STATES.map((state) => `<option value="${state}" ${state === model.state ? "selected" : ""}>${STATE_LABELS[state]}</option>`).join("")}</select></label>
      <button class="advance-button" type="button" data-action="advance">推进状态</button>
    </aside>`;
}

function stopDialog(model) {
  const workflow = WORKFLOWS[model.workflow];
  const message = model.state === "queued"
    ? `此${workflow.noun}尚未开始。停止后会将其移出队列，并标记为“已取消”。`
    : "当前操作会先安全完成，随后执行进程才会释放任务。已完成的里程碑和保留的活动记录仍然可用。";
  return `<dialog id="stop-dialog"><form method="dialog"><p class="section-kicker">安全停止</p><h2>停止此${workflow.noun}？</h2><p>${message}</p><div><button class="quiet-button" value="cancel">继续运行</button><button class="danger-button" value="confirm" data-action="confirm-stop">安全停止</button></div></form></dialog>`;
}

function render() {
  const model = readModel();
  app.innerHTML = `${CoreFlowReference(model)}${PrototypeControls(model)}${stopDialog(model)}`;
}

function advance(model) {
  const happyPath = { create: "queued", queued: "running", running: "completed", stopping: "stopped" };
  updateModel({ state: happyPath[model.state] || "create", view: null });
}

app.addEventListener("submit", (event) => {
  if (!event.target.matches(".create-form")) return;
  event.preventDefault();
  updateModel({ state: "queued", view: "progress", source: null, attempt: null });
});

app.addEventListener("change", (event) => {
  if (event.target.matches('[data-action="state"]')) {
    updateModel({ state: event.target.value, view: null });
  }
});

app.addEventListener("click", (event) => {
  const control = event.target.closest("[data-action]");
  if (!control) return;
  const model = readModel();
  const action = control.dataset.action;

  if (action === "workflow") updateModel({ workflow: control.dataset.workflow, state: "create", view: null, attempt: null, source: null });
  if (action === "view") updateModel({ view: control.dataset.view });
  if (action === "state") updateModel({ state: control.value, view: null });
  if (action === "advance") advance(model);
  if (action === "toggle-activity") updateModel({ older: !model.older });
  if (action === "request-stop") document.querySelector("#stop-dialog").showModal();
  if (action === "confirm-stop") {
    event.preventDefault();
    updateModel({ state: model.state === "queued" ? "cancelled" : "stopping", view: "progress" });
  }
  if (action === "resume") updateModel({ state: "queued", view: "progress", attempt: model.attempt + 1 });
  if (action === "run-again") updateModel({ state: "queued", view: "progress", source: true, attempt: 1 });
});

assertStateModel();
render();
