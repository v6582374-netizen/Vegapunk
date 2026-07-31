const variantList = [
  { key: "A", name: "Runtime Desk", description: "Central runtime view with persistent right-side adapters." },
  { key: "B", name: "Launch Index", description: "History-first master/detail with one selected Launch." },
  { key: "C", name: "Observatory", description: "Stage strip and raw console with a contextual rail." },
];

const initialState = {
  variant: new URLSearchParams(window.location.search).get("variant")?.toUpperCase() || "A",
  route: "active",
  connection: "connected",
  selectedRun: "launch-042",
  rail: { progress: true, artifacts: true, access: false },
  launch: {
    id: "launch-042",
    title: "Catalyst membrane screening",
    status: "running",
    stage: "Experiment runner",
    progress: 62,
    started: "Today, 09:42",
    updated: "2 min ago",
    completed: "3 / 5",
  },
  history: [
    { id: "launch-041", title: "Electrolyte stability sweep", status: "completed", meta: "Yesterday · 41 min", progress: 100 },
    { id: "launch-040", title: "Membrane literature pass", status: "failed", meta: "Jul 29 · stopped", progress: 48 },
    { id: "launch-039", title: "Solvent candidate scan", status: "completed", meta: "Jul 28 · 1 h 08 min", progress: 100 },
  ],
  log: [
    { time: "09:42:06", text: "Launch snapshot accepted from formatted input revision 7.", tone: "success" },
    { time: "09:42:12", text: "Background and literature stage completed.", tone: "success" },
    { time: "09:54:30", text: "Idea generation produced 18 candidate hypotheses.", tone: "success" },
    { time: "10:11:04", text: "Experiment runner is evaluating candidate set 3 of 8.", tone: "normal" },
  ],
  lastAction: "Live updates are connected to the native sidecar.",
};

let state = structuredClone(initialState);

function currentVariant() {
  return variantList.find((item) => item.key === state.variant) || variantList[0];
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusLabel(status) {
  return { running: "Running", stopped: "Stopped", completed: "Completed", failed: "Failed", queued: "Queued" }[status] || status;
}

function statusChip(status) {
  return `<span class="status-chip status-${status}">${statusLabel(status)}</span>`;
}

function setVariant(key) {
  const next = variantList.find((item) => item.key === key) || variantList[0];
  state.variant = next.key;
  const url = new URL(window.location.href);
  url.searchParams.set("variant", next.key);
  window.history.replaceState({}, "", url);
  render();
}

function addLog(text, tone = "normal") {
  const now = new Date();
  const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  state.log.push({ time, text, tone });
  state.log = state.log.slice(-6);
}

function stopLaunch() {
  if (state.launch.status !== "running") return;
  state.launch.status = "stopped";
  state.launch.updated = "just now";
  state.lastAction = "Launch stopped. The durable state is available for Resume.";
  addLog("Stop requested by the researcher; the active Launch is now resumable.", "warn");
  render();
}

function resumeLaunch() {
  if (state.launch.status !== "stopped") return;
  state.launch.status = "running";
  state.launch.updated = "just now";
  state.lastAction = "Launch resumed and live updates are flowing again.";
  addLog("Resume accepted; the experiment runner continued from its durable checkpoint.", "success");
  render();
}

function selectRun(id) {
  state.selectedRun = id;
  state.route = id === state.launch.id ? "active" : "history";
  state.lastAction = id === state.launch.id ? "Viewing the active Launch." : "History is read-only; controls for the active Launch remain separate.";
  render();
}

function toggleRail(section) {
  state.rail[section] = !state.rail[section];
  render();
}

function shellSidebar() {
  const active = state.route === "history" ? "history" : "active";
  return `
    <aside class="shell-sidebar">
      <div class="brand"><span>OpenWorker</span><small>DESKTOP</small></div>
      <div>
        <div class="side-section-label">Modules</div>
        <button class="side-link active" data-action="route" data-route="active"><span class="glyph">✦</span><span>Discovery</span></button>
        <div class="side-subnav">
          <button class="${active === "active" ? "active" : ""}" data-action="route" data-route="active">Active Launch</button>
          <button class="${active === "history" ? "active" : ""}" data-action="route" data-route="history">Launch history</button>
          <button data-action="route" data-route="preparation">Preparation</button>
        </div>
      </div>
      <div>
        <div class="side-section-label">Other</div>
        <button class="side-link" data-action="noop"><span class="glyph">⌘</span><span>New Session</span></button>
        <button class="side-link" data-action="noop"><span class="glyph">⚙</span><span>Settings</span></button>
      </div>
      <div class="side-footer">
        <span class="prototype-stamp">Prototype only</span>
        <div>Discovery is a top-level module.<br />One active Launch at a time.</div>
      </div>
    </aside>`;
}

function topbar() {
  const action = state.launch.status === "running"
    ? `<button class="button stop" data-action="stop">Stop Launch</button>`
    : state.launch.status === "stopped"
      ? `<button class="button primary" data-action="resume">Resume Launch</button>`
      : `<button class="button" disabled>Read-only history</button>`;
  return `
    <header class="topbar">
      <div class="topbar-title">
        <h1>Discovery <span style="color:var(--faint);font-weight:400">/</span> ${state.route === "history" ? "Launch history" : "Active Launch"}</h1>
        <p>One current Preparation · one active Launch · native sidecar transport</p>
      </div>
      <div class="topbar-actions">
        <span class="connection">${state.connection === "connected" ? "Sidecar connected" : "Reconnecting"}</span>
        ${action}
      </div>
    </header>`;
}

function variantKicker() {
  const variant = currentVariant();
  return `<div class="variant-kicker"><div><h2>${variant.key} / ${variant.name}</h2><p>${variant.description}</p></div><span class="read-only-badge">UI prototype · in-memory state</span></div>`;
}

function heroPanel(compact = false) {
  const launch = state.launch;
  return `
    <section class="panel hero-panel">
      <div class="hero-row">
        <div>
          <h3 class="launch-title">${escapeHtml(launch.title)}</h3>
          <div class="launch-meta">${launch.id} · started ${launch.started} · updated ${launch.updated}</div>
        </div>
        <div class="hero-actions">
          ${statusChip(launch.status)}
          ${launch.status === "running" ? `<button class="button stop" data-action="stop">Stop</button>` : launch.status === "stopped" ? `<button class="button primary" data-action="resume">Resume</button>` : ""}
        </div>
      </div>
      ${compact ? "" : `<div class="hero-facts"><div class="fact"><div class="fact-label">Stage</div><div class="fact-value">${launch.stage}</div></div><div class="fact"><div class="fact-label">Progress</div><div class="fact-value">${launch.progress}%</div></div><div class="fact"><div class="fact-label">Completed</div><div class="fact-value">${launch.completed}</div></div><div class="fact"><div class="fact-label">Access</div><div class="fact-value">3 sources · 1 folder</div></div></div>`}
    </section>`;
}

function timelineRows() {
  const stages = [
    ["01", "Source intake", "Preparation snapshot verified", "done"],
    ["02", "Conversion", "Formatted input revision 7", "done"],
    ["03", "Idea generation", "18 candidate hypotheses", "done"],
    ["04", "Experiment runner", "Candidate set 3 of 8", state.launch.status === "running" ? "active" : "pending"],
    ["05", "Paper handoff", "Awaiting experiment metrics", "pending"],
  ];
  return stages.map(([index, title, detail, stateName]) => `
    <div class="timeline-row ${stateName}">
      <span class="timeline-node"></span><span class="timeline-step">${index}</span>
      <div class="timeline-detail"><strong>${title}</strong><span>${detail}</span></div>
      <span class="timeline-state">${stateName === "done" ? "Done" : stateName === "active" ? "Live" : "Next"}</span>
    </div>`).join("");
}

function stageStrip() {
  const stages = [
    ["01", "Intake", "Verified", "done"],
    ["02", "Convert", "Revision 7", "done"],
    ["03", "Ideas", "18 found", "done"],
    ["04", "Runner", "Set 3 / 8", state.launch.status === "running" ? "active" : "pending"],
    ["05", "Handoff", "Waiting", "pending"],
  ];
  return stages.map(([index, title, detail, stateName]) => `<div class="stage-cell ${stateName}"><span class="stage-index">${index}</span><strong>${title}</strong><span>${detail}</span></div>`).join("");
}

function logList(consoleMode = false) {
  return state.log.map((entry) => `<div class="log-row ${entry.tone}"><span class="log-time">${entry.time}</span><i class="log-dot"></i><span>${escapeHtml(entry.text)}</span></div>`).join("");
}

function railSection(name, label, summary, body) {
  const open = state.rail[name];
  return `<section class="panel rail-section"><button class="rail-toggle" data-action="rail" data-section="${name}"><span class="chevron">${open ? "⌄" : "›"}</span><strong>${label}</strong><span class="rail-summary">${summary}</span></button>${open ? `<div class="rail-body">${body}</div>` : ""}</section>`;
}

function rightRail(compact = false) {
  const launch = state.launch;
  const progressBody = `<div class="progress-bar"><i style="width:${launch.progress}%"></i></div><div class="progress-caption"><span>${launch.stage}</span><strong>${launch.progress}%</strong></div><div class="rail-stat"><span>Completed stages</span><strong>${launch.completed}</strong></div><div class="rail-stat"><span>Live output</span><strong>${state.log.length} events</strong></div>`;
  const artifactsBody = `<div class="artifact-list"><div class="artifact-row"><span class="artifact-icon">MD</span><span>formatted-input.md</span><small>42 KB</small></div><div class="artifact-row"><span class="artifact-icon">CSV</span><span>runner-metrics.csv</span><small>18 KB</small></div><div class="artifact-row"><span class="artifact-icon">LOG</span><span>runner.log</span><small>live</small></div></div>`;
  const accessBody = `<div class="rail-stat"><span>Sources</span><strong>3 enabled</strong></div><div class="rail-stat"><span>Working folder</span><strong>discovery-042</strong></div><p class="access-note">Access is shown as an adapter for this Launch. It does not grant folder upload or create a second Preparation.</p>`;
  return `<aside class="rail ${compact ? "compact-rail" : ""}">${railSection("progress", "Progress", `${launch.progress}% · ${launch.stage}`, progressBody)}${railSection("artifacts", "Artifacts", "3 available", artifactsBody)}${railSection("access", "Access", "3 sources · 1 folder", accessBody)}</aside>`;
}

function historyItems() {
  const active = state.launch;
  const all = [active, ...state.history];
  return all.map((run) => `<button class="run-item ${state.selectedRun === run.id ? "selected" : ""}" data-action="select-run" data-id="${run.id}"><span class="run-item-top"><span class="run-item-title">${escapeHtml(run.title)}</span>${statusChip(run.status)}</span><span class="run-item-meta">${run.id} · ${run.meta || run.updated}</span></button>`).join("");
}

function runtimeDesk() {
  return `<div class="runtime-grid"><main class="runtime-main">${heroPanel()}<section class="panel"><div class="panel-head"><h3>Launch timeline</h3><span>Start-time snapshot · immutable for this Launch</span></div><div class="panel-body timeline">${timelineRows()}</div></section><section class="panel"><div class="panel-head"><h3>Runtime output</h3><span>${state.lastAction}</span></div><div class="panel-body log-list">${logList()}</div></section></main>${rightRail()}</div>`;
}

function launchIndex() {
  const selected = state.selectedRun === state.launch.id ? state.launch : state.history.find((item) => item.id === state.selectedRun) || state.launch;
  const readOnly = selected.id !== state.launch.id;
  return `<div class="master-detail"><section class="panel run-index"><div class="run-index-head"><strong>Launches</strong><span>${state.history.length + 1} total</span></div>${historyItems()}</section><main class="detail">${readOnly ? `<p class="history-note">Completed and failed Launches are retained as read-only history. Select the active Launch to use Stop or Resume.</p>` : ""}<section class="panel detail-header"><div><h3 class="launch-title">${escapeHtml(selected.title)}</h3><div class="launch-meta">${selected.id} · ${readOnly ? selected.meta : `${selected.stage} · ${selected.updated}`}</div></div><div class="detail-header-actions">${statusChip(selected.status)}${!readOnly && selected.status === "running" ? `<button class="button stop" data-action="stop">Stop</button>` : ""}${!readOnly && selected.status === "stopped" ? `<button class="button primary" data-action="resume">Resume</button>` : ""}</div></section><section class="panel"><div class="panel-head"><h3>Lifecycle</h3><span>${readOnly ? "Archived observation" : "Live observation"}</span></div><div class="detail-timeline timeline">${timelineRows()}</div></section><section class="panel"><div class="panel-head"><h3>Raw runtime output</h3><span>${readOnly ? "Read-only" : "Streaming"}</span></div><div class="detail-log log-list">${logList()}</div></section></main>${rightRail(true)}</div>`;
}

function observatory() {
  return `<div class="observatory"><main class="observatory-main"><section class="panel observatory-header"><div><h3 class="launch-title">${escapeHtml(state.launch.title)}</h3><div class="launch-meta">${state.launch.id} · ${state.launch.stage} · ${state.lastAction}</div></div><div class="observatory-header-actions">${statusChip(state.launch.status)}${state.launch.status === "running" ? `<button class="button stop" data-action="stop">Stop</button>` : state.launch.status === "stopped" ? `<button class="button primary" data-action="resume">Resume</button>` : ""}</div></section><section class="panel"><div class="panel-head"><h3>Discovery lifecycle</h3><span>One Launch snapshot</span></div><div class="stage-strip">${stageStrip()}</div></section><div class="facts-grid"><section class="panel fact-card"><div class="fact-label">Current stage</div><strong>${state.launch.stage}</strong><p>The central stage strip stays stable while the live console grows below it.</p></section><section class="panel fact-card"><div class="fact-label">Progress</div><strong>${state.launch.progress}%</strong><p>${state.launch.completed} lifecycle stages have durable completion state.</p></section><section class="panel fact-card"><div class="fact-label">History</div><strong>${state.history.length}</strong><p>Finished Launches remain visible without competing with the active run.</p></section></div><section class="panel console"><div class="panel-head"><h3>Raw console</h3><span>merged durable runner.log</span></div><div class="panel-body log-list">${logList(true)}</div></section></main><aside class="drawer-rail">${rightRail()}</aside></div>`;
}

function mainContent() {
  if (state.route === "history") {
    return `<div class="content">${variantKicker()}${launchIndex()}</div>`;
  }
  if (state.route === "preparation") {
    return `<div class="content">${variantKicker()}<section class="panel" style="max-width:720px;margin:0 auto;padding:28px"><h2 style="margin:0 0 8px;font-size:18px">Preparation is a separate ticket</h2><p style="margin:0;color:var(--muted);font-size:12px;line-height:1.6">This Launch prototype keeps the one-current-Preparation contract visible in the sidebar, but does not decide intake or conversion behavior. Use the Preparation ticket for that surface.</p></section></div>`;
  }
  const body = state.variant === "B" ? launchIndex() : state.variant === "C" ? observatory() : runtimeDesk();
  return `<div class="content">${variantKicker()}${body}</div>`;
}

function switcher() {
  const variant = currentVariant();
  const index = variantList.findIndex((item) => item.key === variant.key);
  const previous = variantList[(index + variantList.length - 1) % variantList.length].key;
  const next = variantList[(index + 1) % variantList.length].key;
  return `<nav class="prototype-switcher" aria-label="Prototype variants"><button data-action="variant" data-variant="${previous}" aria-label="Previous variant">←</button><div class="prototype-switcher-label"><strong>${variant.key} · ${variant.name}</strong><br /><span>use ← → to compare</span></div><button data-action="variant" data-variant="${next}" aria-label="Next variant">→</button></nav>`;
}

function render() {
  document.querySelector("#app").innerHTML = `<div class="app-shell">${shellSidebar()}<section class="surface">${topbar()}${mainContent()}</section>${switcher()}</div>`;
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  if (action === "variant") setVariant(target.dataset.variant);
  if (action === "stop") stopLaunch();
  if (action === "resume") resumeLaunch();
  if (action === "select-run") selectRun(target.dataset.id);
  if (action === "rail") toggleRail(target.dataset.section);
  if (action === "route") {
    state.route = target.dataset.route;
    if (state.route === "active") state.selectedRun = state.launch.id;
    render();
  }
});

window.addEventListener("keydown", (event) => {
  const tag = document.activeElement?.tagName;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || document.activeElement?.isContentEditable) return;
  if (event.key === "ArrowLeft") {
    const index = variantList.findIndex((item) => item.key === state.variant);
    setVariant(variantList[(index + variantList.length - 1) % variantList.length].key);
  }
  if (event.key === "ArrowRight") {
    const index = variantList.findIndex((item) => item.key === state.variant);
    setVariant(variantList[(index + 1) % variantList.length].key);
  }
});

window.addEventListener("popstate", () => {
  state.variant = new URLSearchParams(window.location.search).get("variant")?.toUpperCase() || "A";
  render();
});

render();
