import { useEffect, useMemo, useState } from "react";
import "./youtube-prototype.css";

type Video = {
  id: string;
  channel: string;
  avatar: string;
  title: string;
  published: string;
  duration: string;
  language: string;
  status: "ready" | "error" | "pending";
  excerpt: string;
};

const VIDEOS: Video[] = [
  {
    id: "signals",
    channel: "ColdFusion",
    avatar: "CF",
    title: "The quiet infrastructure behind the AI boom",
    published: "Today · 08:42",
    duration: "18:24",
    language: "English",
    status: "ready",
    excerpt: "There is a layer of infrastructure most people never see. It decides what becomes possible before the model ever runs.",
  },
  {
    id: "systems",
    channel: "Fireship",
    avatar: "FS",
    title: "The web platform is changing again",
    published: "Yesterday · 21:10",
    duration: "12:08",
    language: "English · auto",
    status: "ready",
    excerpt: "The next phase of the web is less about another framework and more about the boundaries between local and remote software.",
  },
  {
    id: "design",
    channel: "The Futur",
    avatar: "TF",
    title: "Why good interfaces leave room for silence",
    published: "Yesterday · 16:03",
    duration: "31:46",
    language: "English",
    status: "ready",
    excerpt: "A calm interface is not an empty interface. It is a system that knows what deserves attention now and what can wait.",
  },
  {
    id: "research",
    channel: "Two Minute Papers",
    avatar: "2M",
    title: "This model learns to see the invisible",
    published: "Mon · 11:28",
    duration: "06:52",
    language: "No caption",
    status: "error",
    excerpt: "The paper introduces a surprisingly simple trick: keep the uncertainty visible instead of smoothing it away.",
  },
  {
    id: "history",
    channel: "Asianometry",
    avatar: "AS",
    title: "The supply chain that made modern chips possible",
    published: "Sun · 19:32",
    duration: "24:19",
    language: "Fetching…",
    status: "pending",
    excerpt: "A map of the companies, ports, and patient engineering decisions that quietly shaped the modern semiconductor world.",
  },
];

const statusLabel: Record<Video["status"], string> = {
  ready: "Caption ready",
  error: "Caption unavailable",
  pending: "Fetching caption",
};

function useVideoState() {
  const [selected, setSelected] = useState<Set<string>>(new Set(["signals", "design"]));
  const [active, setActive] = useState(VIDEOS[0].id);
  const [running, setRunning] = useState(false);
  const [runLabel, setRunLabel] = useState("Last run today · 00:00 Beijing");

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const run = () => {
    if (running) return;
    setRunning(true);
    window.setTimeout(() => {
      setRunning(false);
      setRunLabel("Just now · 00:00 Beijing");
    }, 650);
  };

  return { selected, active, setActive, toggle, run, running, runLabel };
}

function Status({ video }: { video: Video }) {
  return <span className={`yt-status yt-status-${video.status}`}><i />{statusLabel[video.status]}</span>;
}

function Header({ run, running, runLabel, selectedCount }: { run: () => void; running: boolean; runLabel: string; selectedCount: number }) {
  return (
    <header className="yt-header">
      <div>
        <div className="yt-eyebrow">Automation · YouTube</div>
        <h1>Subscription updates</h1>
        <p>{runLabel} <span className="yt-dot">·</span> {selectedCount} selected for translation</p>
      </div>
      <button className="yt-run-button" onClick={run} disabled={running}>
        <span className={running ? "yt-spinner" : "yt-play"} aria-hidden>{running ? "" : "▶"}</span>
        {running ? "Checking updates…" : "Run now"}
      </button>
    </header>
  );
}

function CaptionPreview({ video }: { video: Video }) {
  return (
    <aside className="yt-preview" key={video.id}>
      <div className="yt-preview-top">
        <span className="yt-preview-kicker">Raw caption preview</span>
        <span className="yt-duration">{video.duration}</span>
      </div>
      <div className="yt-preview-channel"><span className="yt-avatar large">{video.avatar}</span><div><strong>{video.channel}</strong><span>{video.published}</span></div></div>
      <h2>{video.title}</h2>
      <div className="yt-caption-meta"><span>{video.language}</span><span>·</span><span>{video.status === "ready" ? "youtube-transcript-api" : "Retry on next run"}</span></div>
      <p className="yt-caption-copy">{video.excerpt}</p>
      <div className="yt-preview-actions">
        <button className="yt-secondary">Open on YouTube ↗</button>
        <button className="yt-secondary">View full caption</button>
      </div>
    </aside>
  );
}

function QuietVariant() {
  const state = useVideoState();
  const [filter, setFilter] = useState("all");
  const filtered = VIDEOS.filter((video) => filter === "all" || video.status === filter);
  return (
    <div className="yt-proto-shell yt-quiet">
      <Header run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} />
      <div className="yt-quiet-toolbar"><span>{filtered.length} updates</span><div className="yt-filter-group">{[["all", "All"], ["ready", "Ready"], ["error", "Needs attention"]].map(([key, label]) => <button key={key} className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>{label}</button>)}</div></div>
      <div className="yt-quiet-list">
        {filtered.map((video) => <button key={video.id} className={`yt-quiet-row ${state.active === video.id ? "active" : ""}`} onClick={() => state.setActive(video.id)}>
          <span className="yt-check" onClick={(event) => { event.stopPropagation(); state.toggle(video.id); }} aria-label={state.selected.has(video.id) ? "Deselect" : "Select"}>{state.selected.has(video.id) ? "✓" : ""}</span>
          <span className="yt-avatar">{video.avatar}</span><span className="yt-row-copy"><strong>{video.title}</strong><span>{video.channel} <i>·</i> {video.published}</span></span><Status video={video} /><span className="yt-chevron">›</span>
        </button>)}
      </div>
      <div className="yt-quiet-footer"><span>English captions are preferred. Other languages are used only when English is unavailable.</span><button className="yt-link">Manage YouTube connection</button></div>
    </div>
  );
}

function EditorialVariant() {
  const state = useVideoState();
  const grouped = useMemo(() => {
    const map = new Map<string, Video[]>();
    VIDEOS.forEach((video) => map.set(video.channel, [...(map.get(video.channel) || []), video]));
    return [...map.entries()];
  }, []);
  return (
    <div className="yt-proto-shell yt-editorial">
      <Header run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} />
      <div className="yt-editorial-intro"><span className="yt-editorial-date">AUG 19, 2026</span><span className="yt-editorial-rule" /><span>Five new videos from your subscriptions</span></div>
      <div className="yt-editorial-grid">
        {grouped.map(([channel, videos]) => <section className="yt-channel-section" key={channel}><div className="yt-channel-heading"><span className="yt-avatar">{videos[0].avatar}</span><div><h2>{channel}</h2><span>{videos.length} update{videos.length > 1 ? "s" : ""}</span></div></div>{videos.map((video) => <article className={`yt-editorial-card ${state.active === video.id ? "active" : ""}`} key={video.id} onClick={() => state.setActive(video.id)}><div className="yt-editorial-card-head"><span>{video.published}</span><Status video={video} /></div><h3>{video.title}</h3><p>{video.excerpt}</p><div className="yt-editorial-card-foot"><button className={`yt-select-pill ${state.selected.has(video.id) ? "selected" : ""}`} onClick={(event) => { event.stopPropagation(); state.toggle(video.id); }}>{state.selected.has(video.id) ? "Selected for translation" : "Select for translation"}</button><span>{video.duration}</span></div></article>)}</section>)}
      </div>
    </div>
  );
}

function FlowVariant() {
  const state = useVideoState();
  const active = VIDEOS.find((video) => video.id === state.active) || VIDEOS[0];
  return (
    <div className="yt-proto-shell yt-flow">
      <Header run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} />
      <div className="yt-flow-layout">
        <div className="yt-flow-queue"><div className="yt-flow-queue-head"><span>Update queue</span><span>{VIDEOS.length}</span></div>{VIDEOS.map((video) => <button key={video.id} className={`yt-flow-item ${active.id === video.id ? "active" : ""}`} onClick={() => state.setActive(video.id)}><span className={`yt-flow-check ${state.selected.has(video.id) ? "selected" : ""}`} onClick={(event) => { event.stopPropagation(); state.toggle(video.id); }}>{state.selected.has(video.id) ? "✓" : ""}</span><span className="yt-flow-item-copy"><strong>{video.title}</strong><span>{video.channel} · {video.published}</span></span><span className={`yt-flow-dot ${video.status}`} /></button>)}</div>
        <CaptionPreview video={active} />
      </div>
      <div className="yt-flow-bar"><span><strong>{state.selected.size}</strong> videos ready for the next translation step</span><button className="yt-flow-cta" onClick={() => state.toggle(active.id)}>{state.selected.has(active.id) ? "Remove current" : "Select current"}</button></div>
    </div>
  );
}

const variants = [
  { name: "Quiet", axis: "Dense daily scan", render: QuietVariant },
  { name: "Editorial", axis: "Channel-led reading", render: EditorialVariant },
  { name: "Flow", axis: "Queue + preview", render: FlowVariant },
];

export function YouTubePrototype() {
  const params = new URLSearchParams(window.location.search);
  const initial = Math.min(variants.length - 1, Math.max(0, (Number(params.get("v")) || 1) - 1));
  const [current, setCurrent] = useState(initial);
  const [mountKey, setMountKey] = useState(0);
  const active = variants[current];
  const setActive = (index: number) => {
    if (index < 0 || index >= variants.length) return;
    setCurrent(index);
    const url = new URL(window.location.href);
    url.searchParams.set("v", String(index + 1));
    window.history.replaceState(null, "", url);
    setMountKey((key) => key + 1);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (/^(INPUT|TEXTAREA|SELECT)$/.test((event.target as HTMLElement)?.tagName || "") || (event.target as HTMLElement)?.isContentEditable) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const number = Number(event.key);
      if (number >= 1 && number <= variants.length) setActive(number - 1);
      else if (event.key === "ArrowRight") setActive((current + 1) % variants.length);
      else if (event.key === "ArrowLeft") setActive((current - 1 + variants.length) % variants.length);
      else if (event.key.toLowerCase() === "r") setMountKey((key) => key + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current]);

  const Variant = active.render;
  return <div className="youtube-prototype-page"><div className="youtube-prototype-stage" key={`${current}-${mountKey}`}><Variant /></div><nav className="proto-picker" aria-label="Prototype variants"><span className="proto-picker-highlight" aria-hidden="true" />{variants.map((variant, index) => <button key={variant.name} className="proto-picker-item" data-active={index === current ? "" : undefined} aria-current={index === current ? "true" : undefined} onClick={() => setActive(index)}>{variant.name}</button>)}<span className="proto-picker-divider" aria-hidden="true" /><button className="proto-picker-item proto-picker-replay" aria-label="Replay animation (R)" onClick={() => setMountKey((key) => key + 1)}>↻</button></nav><PickerHighlight current={current} /></div>;
}

function PickerHighlight({ current }: { current: number }) {
  useEffect(() => {
    const picker = document.querySelector<HTMLElement>(".proto-picker");
    const highlight = picker?.querySelector<HTMLElement>(".proto-picker-highlight");
    const items = picker ? [...picker.querySelectorAll<HTMLElement>(".proto-picker-item:not(.proto-picker-replay)")] : [];
    const move = () => { const item = items[current]; if (item && highlight) { highlight.style.width = `${item.offsetWidth}px`; highlight.style.transform = `translateX(${item.offsetLeft}px)`; } };
    move();
    window.addEventListener("resize", move);
    const first = requestAnimationFrame(() => requestAnimationFrame(() => picker?.setAttribute("data-ready", "")));
    return () => { cancelAnimationFrame(first); window.removeEventListener("resize", move); };
  }, [current]);
  return null;
}
