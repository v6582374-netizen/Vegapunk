/*
 * THROWAWAY PROTOTYPE — Current Launch seam integration, second pass.
 *
 * First-principles question:
 * Can a researcher keep the Current Launch console as the primary workspace,
 * while seeing all three fixed checkpoint slots and the one active Resume
 * action without leaving the Launch surface?
 */

const VARIANTS = [
  { key: "1", name: "Console First", axis: "terminal-led layout" },
  { key: "2", name: "Stage Strip", axis: "pipeline-led layout" },
  { key: "3", name: "Review Dock", axis: "checkpoint-led layout" },
];

const CHECKPOINTS = [
  {
    key: "mas",
    order: 1,
    label: "After MAS ranking",
    short: "Every ranking → AWAITING_FEEDBACK",
    reason: "Inspect ranked ideas before the next MAS cycle.",
    artifacts: [
      ["ranked-ideas.json", "8 ideas · scores + rank"],
      ["critique-and-evidence.md", "12 evidence links"],
      ["traj.json", "session trajectory"],
    ],
    preview: [
      ["Top candidates", "Adaptive sparse routing · 0.91"],
      ["Ranking context", "Iteration 3 of 5 · 3 ideas selected"],
      ["Next operation", "Reflection / evolution"],
    ],
  },
  {
    key: "method",
    order: 2,
    label: "Before experiment",
    short: "One batch per Discovery Round",
    reason: "Inspect refined methods before ExperimentRunner or ReportWriter starts.",
    artifacts: [
      ["method-batch.json", "3 refined methods"],
      ["baseline-metrics.json", "run_0 comparison"],
      ["execution-plan.md", "resources + limits"],
    ],
    preview: [
      ["Round", "Round 2 · 3 refined methods"],
      ["Execution context", "OpenHands · 2.4h GPU budget"],
      ["Next operation", "Experiment / report path"],
    ],
  },
  {
    key: "handoff",
    order: 3,
    label: "Before PaperOrchestra",
    short: "One checkpoint per Launch",
    reason: "Inspect the aggregate Discovery outcome before paper generation.",
    artifacts: [
      ["discovery_summary.json", "3 rounds · 9 results"],
      ["candidate-reports/", "7 successful candidates"],
      ["paper-input-manifest.json", "source-faithful inputs"],
    ],
    preview: [
      ["Outcome", "7 of 9 candidates succeeded"],
      ["Provenance", "28 Launch-owned artifacts"],
      ["Next operation", "One PaperOrchestra Run"],
    ],
  },
];

const STAGES = {
  before: {
    key: "before",
    label: "Preparing",
    state: "running",
    active: null,
    meta: "Launch admitted · no review seam reached",
    notice: "The Launch is active. Checkpoint slots remain unavailable until their boundary is reached.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:04:32", "preparing", "Loading Discovery input and runtime"],
      ["12:04:35", "research", "Starting MAS session"],
      ["12:04:36", "stdout", "No human review boundary reached yet"],
    ],
  },
  running: {
    key: "running",
    label: "Running",
    state: "running",
    active: null,
    meta: "Round 2 · MAS and experiment path active",
    notice: "The runner is active. Review slots are prepared but cannot be opened before their seam.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:05:08", "MAS", "Ranking candidates for round 2"],
      ["12:05:16", "experiment", "Preparing refined method batch"],
      ["12:05:18", "stdout", "Terminal remains the live source of execution detail"],
    ],
  },
  mas: {
    key: "mas",
    label: "MAS ranking",
    state: "awaiting_review",
    active: "mas",
    meta: "Round 2 · iteration 3 · ranking complete",
    notice: "Execution inactive at the MAS seam. Review the read-only bundle, then Resume.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:05:08", "MAS", "Ranking candidates for round 2"],
      ["12:05:16", "checkpoint", "MAS ranking bundle written"],
      ["12:05:16", "state", "awaiting_review · runner exited"],
    ],
  },
  method: {
    key: "method",
    label: "Method review",
    state: "awaiting_review",
    active: "method",
    meta: "Round 2 · refined methods ready · execution not started",
    notice: "Execution inactive before the experiment/report path. Review the complete method batch, then Resume.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:05:16", "MAS", "Ranking checkpoint resumed"],
      ["12:06:02", "methods", "3 refined methods written"],
      ["12:06:02", "state", "awaiting_review · ExperimentRunner not started"],
    ],
  },
  handoff: {
    key: "handoff",
    label: "Handoff review",
    state: "awaiting_review",
    active: "handoff",
    meta: "Launch complete · summary written · PaperOrchestra not started",
    notice: "Execution inactive at the research-to-paper boundary. Review the aggregate result, then Resume.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:18:42", "rounds", "3 Discovery rounds completed"],
      ["12:18:43", "summary", "discovery_summary.json written"],
      ["12:18:43", "state", "awaiting_review · PaperOrchestra not started"],
    ],
  },
  complete: {
    key: "complete",
    label: "Completed",
    state: "completed",
    active: null,
    meta: "Launch complete · PaperOrchestra finished",
    notice: "This Launch is complete. All three checkpoint bundles remain available as read-only history.",
    logs: [
      ["12:04:31", "launch admitted", "Immutable Launch snapshot created"],
      ["12:18:43", "summary", "discovery_summary.json written"],
      ["12:19:12", "PaperOrchestra", "One paper run completed"],
      ["12:19:12", "state", "completed · read-only history"],
    ],
  },
};

const STAGE_ORDER = { before: 0, running: 0, mas: 1, method: 2, handoff: 3, complete: 4 };
const LEGACY_VARIANTS = { A: "1", B: "2", C: "3" };
const LEGACY_SEAMS = { mas: "mas", method: "method", handoff: "handoff" };

const params = new URLSearchParams(window.location.search);
const requestedVariant = params.get("v") || LEGACY_VARIANTS[(params.get("variant") || "").toUpperCase()] || "1";
const requestedStage = params.get("stage") || LEGACY_SEAMS[params.get("seam")] || "mas";
if (params.get("theme") === "dark") document.documentElement.dataset.theme = "dark";
if (params.get("theme") === "light") document.documentElement.removeAttribute("data-theme");

const state = {
  variant: VARIANTS.some((item) => item.key === requestedVariant) ? requestedVariant : "1",
  stage: STAGES[requestedStage] ? requestedStage : "mas",
  selectedArtifact: requestedStage === "complete" ? "handoff" : STAGES[requestedStage]?.active || "mas",
  rawOpen: false,
  resumed: false,
};

function currentStage() {
  return STAGES[state.stage];
}

function currentVariant() {
  return VARIANTS.find((item) => item.key === state.variant) || VARIANTS[0];
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function updateUrl() {
  const next = new URL(window.location.href);
  next.searchParams.set("v", state.variant);
  next.searchParams.set("stage", state.stage);
  next.searchParams.delete("variant");
  next.searchParams.delete("seam");
  window.history.replaceState({}, "", next);
}

function setVariant(key) {
  if (!VARIANTS.some((item) => item.key === key)) return;
  state.variant = key;
  updateUrl();
  render();
}

function setStage(key) {
  if (!STAGES[key]) return;
  state.stage = key;
  state.selectedArtifact = STAGES[key].active || (key === "complete" ? "handoff" : "mas");
  state.rawOpen = false;
  state.resumed = false;
  updateUrl();
  render();
}

function selectArtifact(key) {
  const slot = CHECKPOINTS.find((item) => item.key === key);
  if (!slot || checkpointState(key) === "locked") return;
  state.selectedArtifact = key;
  render();
}

function toggleRaw() {
  state.rawOpen = !state.rawOpen;
  render();
}

function nextStageForResume() {
  if (state.stage === "mas") return "method";
  if (state.stage === "method") return "handoff";
  if (state.stage === "handoff") return "complete";
  return state.stage;
}

function resumeLaunch() {
  const next = nextStageForResume();
  if (next === state.stage) return;
  state.stage = next;
  state.selectedArtifact = STAGES[next].active || (next === "complete" ? "handoff" : "mas");
  state.resumed = true;
  state.rawOpen = false;
  updateUrl();
  render();
}

function checkpointState(key) {
  const stage = currentStage();
  if (stage.key === "before" || stage.key === "running") return "locked";
  if (stage.key === "complete") return "done";
  const checkpoint = CHECKPOINTS.find((item) => item.key === key);
  if (!checkpoint) return "locked";
  const activeOrder = STAGE_ORDER[stage.key];
  if (checkpoint.order < activeOrder) return "done";
  if (checkpoint.order === activeOrder) return "active";
  return "locked";
}

function statusLabel(status) {
  if (status === "active") return "Current checkpoint";
  if (status === "done") return "Available";
  return "Not reached";
}

function statusClass(status) {
  return status === "active" ? "is-active" : status === "done" ? "is-done" : "is-locked";
}

function statusPill(stateKey) {
  const map = {
    running: ["Live", "is-live"],
    awaiting_review: ["Execution inactive", "is-review"],
    completed: ["Completed", "is-done"],
  };
  const [label, tone] = map[stateKey] || [stateKey, ""];
  return `<span class="status-pill ${tone}"><span class="status-dot"></span>${escapeHtml(label)}</span>`;
}

function productButton(label, tone = "") {
  return `<button type="button" class="product-button ${tone}" onclick="${label === "Resume" ? "resumeLaunch()" : "noop()"}">${escapeHtml(label)}</button>`;
}

function renderSidebar() {
  return `<aside class="app-sidebar" aria-label="Application navigation">
    <div class="brand-row"><span class="brand-mark">V</span><span class="brand-name">Vegapunk</span><span class="beta-chip">BETA</span></div>
    <div class="sidebar-group-label">Workspace</div>
    <nav class="sidebar-nav">
      <a class="sidebar-item" href="#"><span class="sidebar-icon">⌂</span><span>Workbench</span></a>
      <a class="sidebar-item is-selected" href="#"><span class="sidebar-icon">✦</span><span>Discovery</span></a>
      <a class="sidebar-item" href="#"><span class="sidebar-icon">◌</span><span>Memory</span></a>
      <a class="sidebar-item" href="#"><span class="sidebar-icon">▣</span><span>Experiments</span></a>
    </nav>
    <div class="sidebar-spacer"></div>
    <div class="sidebar-group-label">System</div>
    <nav class="sidebar-nav">
      <a class="sidebar-item" href="#"><span class="sidebar-icon">⚙</span><span>Settings</span></a>
    </nav>
    <div class="sidebar-footer"><span class="connection-dot"></span><span>Local sidecar</span><span class="sidebar-version">v0.1</span></div>
  </aside>`;
}

function renderPageHeader() {
  const stage = currentStage();
  const action = stage.state === "awaiting_review"
    ? productButton("Resume", "is-primary")
    : stage.state === "running"
      ? productButton("Stop", "")
      : "";
  return `<header class="page-header">
    <div class="page-heading"><h1>Discovery <span>/</span> <em>Current Launch</em></h1><p>One active Launch · server-authoritative observation</p></div>
    <div class="page-actions"><span class="connection"><span class="connection-dot"></span>Sidecar connected</span>${action}</div>
  </header>
  <nav class="context-nav" aria-label="Discovery sections"><button>Preparation</button><button class="is-active">Current Launch</button><button>History</button></nav>`;
}

function renderLaunchHero() {
  const stage = currentStage();
  return `<section class="launch-hero product-panel" aria-label="Current Discovery Launch">
    <div class="hero-row"><div><div class="eyebrow">CURRENT DISCOVERY LAUNCH</div><h2>Research direction discovery</h2><div class="launch-meta">launch-20260804-02 · ${escapeHtml(stage.state)} · ${escapeHtml(stage.label)} · round 2</div></div><div class="hero-actions">${statusPill(stage.state)}${stage.state === "awaiting_review" ? productButton("Resume", "is-primary") : stage.state === "running" ? productButton("Stop", "") : ""}</div></div>
    <div class="hero-facts"><div><span>Stage</span><strong>${escapeHtml(stage.label)}</strong></div><div><span>Round</span><strong>${stage.key === "complete" ? "3 / 3" : "2 / 3"}</strong></div><div><span>Progress</span><strong>${stage.key === "complete" ? "100%" : stage.key === "handoff" ? "92%" : stage.key === "method" ? "62%" : stage.key === "mas" ? "44%" : "18%"}</strong></div><div><span>Snapshot</span><strong>rev-7f2c31a9</strong></div></div>
  </section>`;
}

function renderTimeline() {
  const stage = currentStage();
  const steps = [
    ["preparation", "Preparation", "Input snapshot"],
    ["mas", "MAS", "Rank + refine"],
    ["method", "Method", "Execution boundary"],
    ["experiment", "Experiments", "Runner + reports"],
    ["paper", "PaperOrchestra", "One paper handoff"],
  ];
  const progress = stage.key === "complete" ? 5 : stage.key === "handoff" ? 4 : stage.key === "method" ? 3 : stage.key === "mas" ? 2 : 1;
  return `<div class="timeline-list">${steps.map(([key, label, summary], index) => {
    const done = index < progress - 1 || stage.key === "complete";
    const active = !done && index === progress - 1 && stage.key !== "complete";
    return `<div class="timeline-row ${done ? "is-done" : active ? "is-active" : "is-pending"}"><span class="timeline-node"></span><span class="timeline-number">${String(index + 1).padStart(2, "0")}</span><div class="timeline-copy"><strong>${label}</strong><span>${summary}</span></div><span class="timeline-state">${done ? "Done" : active ? "Live" : "Next"}</span></div>`;
  }).join("")}</div>`;
}

function renderTerminal() {
  const stage = currentStage();
  const lines = stage.logs.concat(state.resumed ? [["12:06:04", "resume", "Continuation recorded from previous checkpoint"]] : []);
  const visible = state.rawOpen ? lines.concat([["12:06:05", "stdout", "No process remains active while awaiting_review"]]) : lines;
  return `<section class="terminal-panel product-panel" aria-label="Launch terminal">
    <div class="panel-head terminal-head"><div><h3>Terminal</h3><span>stdout + stderr · ${stage.state === "awaiting_review" ? "last attempt" : "live observation"}</span></div><div class="terminal-head-actions"><span class="terminal-source">runner.log</span><button type="button" class="quiet-button" onclick="toggleRaw()">${state.rawOpen ? "Hide raw" : "View raw"}</button></div></div>
    <div class="terminal-toolbar"><span class="terminal-live ${stage.state === "awaiting_review" ? "is-paused" : stage.state === "completed" ? "is-complete" : ""}"></span><span>${stage.state === "awaiting_review" ? "Execution inactive" : stage.state === "completed" ? "Archived observation" : "Streaming"}</span><span class="terminal-id">launch-20260804-02</span></div>
    <div class="terminal-output">${visible.map(([time, tag, text]) => `<div class="terminal-line"><span class="terminal-time">${time}</span><span class="terminal-tag ${tag === "checkpoint" || tag === "state" ? "is-accent" : tag === "summary" || tag === "resume" ? "is-ok" : ""}">${tag}</span><span class="terminal-text">${escapeHtml(text)}</span></div>`).join("")}</div>
    <div class="terminal-footer"><span>${stage.notice}</span><span class="terminal-count">${visible.length} lines</span></div>
  </section>`;
}

function renderArtifactSlot(slot) {
  const status = checkpointState(slot.key);
  const disabled = status === "locked";
  const openAction = disabled ? `<span class="artifact-lock">Locked</span>` : `<button type="button" class="artifact-open" onclick="selectArtifact('${slot.key}')">Open</button>`;
  return `<article class="checkpoint-slot ${statusClass(status)}" aria-disabled="${disabled}">
    <div class="checkpoint-slot-top"><span class="checkpoint-icon">${status === "done" ? "✓" : status === "active" ? "•" : "—"}</span><div class="checkpoint-slot-title"><strong>${escapeHtml(slot.label)}</strong><span>${escapeHtml(slot.short)}</span></div><span class="checkpoint-status">${statusLabel(status)}</span></div>
    <p>${escapeHtml(slot.reason)}</p>
    <div class="artifact-mini-list">${slot.artifacts.map(([name, detail]) => `<div class="artifact-mini ${disabled ? "is-disabled" : ""}"><span class="artifact-file">${escapeHtml(name)}</span><span>${escapeHtml(detail)}</span></div>`).join("")}</div>
    <div class="checkpoint-slot-footer"><span class="read-only">${status === "locked" ? "Available after seam" : "Read-only bundle"}</span>${openAction}</div>
  </article>`;
}

function renderCheckpointSlots(layout = "stack") {
  return `<section class="checkpoint-slots ${layout}" aria-label="Human review checkpoints"><div class="slots-head"><div><h3>Review checkpoints</h3><span>Fixed Launch artifacts · open as each seam is reached</span></div><span class="slots-count">3 seams</span></div><div class="slots-grid">${CHECKPOINTS.map(renderArtifactSlot).join("")}</div></section>`;
}

function renderArtifactPreview() {
  const slot = CHECKPOINTS.find((item) => item.key === state.selectedArtifact) || CHECKPOINTS[0];
  const status = checkpointState(slot.key);
  if (status === "locked") {
    return `<section class="artifact-preview product-panel is-empty" aria-label="Review bundle preview"><div class="empty-mark">—</div><div><h3>No review bundle yet</h3><p>Reach <strong>${escapeHtml(slot.label)}</strong> to make its fixed artifacts available here.</p></div></section>`;
  }
  return `<section class="artifact-preview product-panel" aria-label="Review bundle preview"><div class="preview-head"><div><div class="eyebrow">READ-ONLY ARTIFACT BUNDLE</div><h3>${escapeHtml(slot.label)}</h3></div><span class="preview-state">${status === "active" ? "Current" : "Available"}</span></div><p class="preview-reason">${escapeHtml(slot.reason)}</p><div class="preview-facts">${slot.preview.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div><div class="preview-foot"><span>Launch-owned · immutable snapshot · no edits in v1</span><span>${slot.artifacts.length} artifacts</span></div></section>`;
}

function renderProgressPanel() {
  const stage = currentStage();
  const completed = CHECKPOINTS.filter((slot) => checkpointState(slot.key) === "done").length;
  return `<section class="progress-panel product-panel"><div class="panel-head"><h3>Progress</h3><span>${stage.key === "complete" ? "100%" : stage.key === "handoff" ? "92%" : stage.key === "method" ? "62%" : stage.key === "mas" ? "44%" : "18%"} · ${escapeHtml(stage.label)}</span></div><div class="progress-body"><div class="progress-bar"><span style="width:${stage.key === "complete" ? "100" : stage.key === "handoff" ? "92" : stage.key === "method" ? "62" : stage.key === "mas" ? "44" : "18"}%"></span></div><div class="progress-caption"><span>${escapeHtml(stage.label)}</span><strong>${stage.key === "complete" ? "100" : stage.key === "handoff" ? "92" : stage.key === "method" ? "62" : stage.key === "mas" ? "44" : "18"}%</strong></div><div class="progress-stat"><span>Checkpoint bundles</span><strong>${completed} / 3 available</strong></div><div class="progress-stat"><span>Terminal lines</span><strong>${currentStage().logs.length}</strong></div></div></section>`;
}

function renderVariantOne() {
  return `<div class="runtime-layout variant-console-first"><div class="runtime-main">${renderTerminal()}</div><aside class="runtime-rail">${renderProgressPanel()}${renderCheckpointSlots("stack")}${renderArtifactPreview()}</aside></div>`;
}

function renderVariantTwo() {
  return `<div class="variant-stage-strip"><div class="stage-strip-wrap">${renderCheckpointSlots("strip")}</div><div class="stage-body"><div class="stage-console">${renderTerminal()}</div><aside class="stage-inspector">${renderTimeline()}${renderArtifactPreview()}</aside></div></div>`;
}

function renderVariantThree() {
  return `<div class="variant-review-dock"><div class="dock-console">${renderTerminal()}</div><div class="dock-lower"><div class="dock-timeline product-panel"><div class="panel-head"><h3>Launch timeline</h3><span>${escapeHtml(currentStage().meta)}</span></div>${renderTimeline()}</div><div class="dock-review"><div class="dock-review-header"><div><div class="eyebrow">CURRENT CHECKPOINT</div><h3>${currentStage().active ? escapeHtml(CHECKPOINTS.find((slot) => slot.key === currentStage().active).label) : "No active checkpoint"}</h3></div>${currentStage().state === "awaiting_review" ? productButton("Resume", "is-primary") : ""}</div>${renderArtifactPreview()}</div></div><div class="dock-slots">${renderCheckpointSlots("compact")}</div></div>`;
}

function renderVariantContent() {
  if (state.variant === "1") return renderVariantOne();
  if (state.variant === "2") return renderVariantTwo();
  return renderVariantThree();
}

function renderPicker() {
  const position = state.variant === "3" ? ' data-position="top"' : "";
  return `<nav class="proto-picker"${position} aria-label="Prototype variants"><span class="proto-picker-highlight" aria-hidden="true"></span>${VARIANTS.map((item) => `<button class="proto-picker-item" data-variant="${item.key}">${escapeHtml(item.name)}</button>`).join("")}<span class="proto-picker-divider" aria-hidden="true"></span><button class="proto-picker-item proto-picker-replay" aria-label="Replay animation (R)">↻</button></nav>`;
}

function render() {
  const variant = currentVariant();
  const stage = currentStage();
  document.querySelector("#app").innerHTML = `<div class="prototype-shell"><div class="prototype-ribbon">THROWAWAY PROTOTYPE · Current Launch seam integration · ${escapeHtml(variant.axis)}</div>${renderSidebar()}<main class="app-main"><div class="app-scroll"><div class="page-frame">${renderPageHeader()}${renderLaunchHero()}<div class="launch-notice ${stage.state === "awaiting_review" ? "is-review" : ""}"><span class="notice-dot"></span><span>${escapeHtml(stage.notice)}</span></div><div class="variant-mount">${renderVariantContent()}</div><div class="prototype-note"><span>Preview state: <strong>${escapeHtml(stage.label)}</strong></span><span>URL: <code>?v=${variant.key}&amp;stage=${stage.key}</code></span><span>Artifacts are read-only; Resume is the only seam action.</span></div></div></div></main>${renderPicker()}</div>`;
  setupPicker();
}

function setupPicker() {
  const picker = document.querySelector(".proto-picker");
  const highlight = picker.querySelector(".proto-picker-highlight");
  const items = [...picker.querySelectorAll(".proto-picker-item:not(.proto-picker-replay)")];
  const replay = picker.querySelector(".proto-picker-replay");
  const current = Math.max(0, VARIANTS.findIndex((item) => item.key === state.variant));

  function moveHighlight() {
    const item = items[current];
    highlight.style.width = `${item.offsetWidth}px`;
    highlight.style.transform = `translateX(${item.offsetLeft}px)`;
  }

  items.forEach((item) => {
    const active = item.dataset.variant === state.variant;
    if (active) {
      item.setAttribute("data-active", "true");
      item.setAttribute("aria-current", "true");
    } else {
      item.removeAttribute("data-active");
    }
    item.addEventListener("click", () => setVariant(item.dataset.variant));
  });
  replay?.addEventListener("click", () => render());
  moveHighlight();
  window.addEventListener("resize", moveHighlight, { once: true });
  requestAnimationFrame(() => requestAnimationFrame(() => picker.setAttribute("data-ready", "")));
}

function noop() {}

window.setVariant = setVariant;
window.setStage = setStage;
window.selectArtifact = selectArtifact;
window.toggleRaw = toggleRaw;
window.resumeLaunch = resumeLaunch;
window.noop = noop;

document.addEventListener("keydown", (event) => {
  const target = event.target;
  if (target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable)) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const index = Number.parseInt(event.key, 10);
  if (index >= 1 && index <= VARIANTS.length) setVariant(VARIANTS[index - 1].key);
  else if (event.key === "ArrowRight") setVariant(VARIANTS[(VARIANTS.findIndex((item) => item.key === state.variant) + 1) % VARIANTS.length].key);
  else if (event.key === "ArrowLeft") setVariant(VARIANTS[(VARIANTS.findIndex((item) => item.key === state.variant) - 1 + VARIANTS.length) % VARIANTS.length].key);
  else if (event.key === "r" || event.key === "R") render();
});

render();
