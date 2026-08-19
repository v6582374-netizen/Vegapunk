import { useEffect, useMemo, useState } from "react";
import { PanelHead } from "./PanelHead";
import { Icon } from "./Icon";
import { BrandIcon } from "./brandIcons";
import "./youtube-prototype.css";

// PROTOTYPE — three YouTube views embedded in the real Automations surface.
// Question: which information hierarchy belongs in production without inventing
// a second visual language for Vegapunk?

type VideoStatus = "ready" | "error" | "pending";
type TranslationStatus = "translated" | "selected" | "unselected";

type Video = {
  id: string;
  channel: string;
  avatar: string;
  title: string;
  published: string;
  language: string;
  source: string;
  status: VideoStatus;
  translationStatus: TranslationStatus;
  dateKey: string;
  dateLabel: string;
  excerpt: string;
};

const VIDEOS: Video[] = [
  { id: "signals", channel: "ColdFusion", avatar: "CF", title: "The quiet infrastructure behind the AI boom", published: "Today · 08:42", language: "English", source: "YouTube captions", status: "ready", translationStatus: "selected", dateKey: "2026-08-19", dateLabel: "Today · Aug 19", excerpt: "There is a layer of infrastructure most people never see. It decides what becomes possible before the model ever runs." },
  { id: "systems", channel: "Fireship", avatar: "FS", title: "The web platform is changing again", published: "Yesterday · 21:10", language: "English · auto", source: "Transcript fallback", status: "ready", translationStatus: "translated", dateKey: "2026-08-18", dateLabel: "Yesterday · Aug 18", excerpt: "The next phase of the web is less about another framework and more about the boundaries between local and remote software." },
  { id: "design", channel: "The Futur", avatar: "TF", title: "Why good interfaces leave room for silence", published: "Yesterday · 16:03", language: "English", source: "YouTube captions", status: "ready", translationStatus: "selected", dateKey: "2026-08-18", dateLabel: "Yesterday · Aug 18", excerpt: "A calm interface is not an empty interface. It is a system that knows what deserves attention now and what can wait." },
  { id: "research", channel: "Two Minute Papers", avatar: "2M", title: "This model learns to see the invisible", published: "Mon · 11:28", language: "No caption", source: "Will retry next run", status: "error", translationStatus: "unselected", dateKey: "2026-08-17", dateLabel: "Mon · Aug 17", excerpt: "The paper introduces a surprisingly simple trick: keep the uncertainty visible instead of smoothing it away." },
  { id: "history", channel: "Asianometry", avatar: "AS", title: "The supply chain that made modern chips possible", published: "Sun · 19:32", language: "Fetching caption", source: "Scheduled retry", status: "pending", translationStatus: "unselected", dateKey: "2026-08-16", dateLabel: "Sun · Aug 16", excerpt: "A map of the companies, ports, and patient engineering decisions that quietly shaped the modern semiconductor world." },
  { id: "chips", channel: "Asianometry", avatar: "AS", title: "The geography of advanced packaging", published: "Fri · 18:06", language: "English", source: "YouTube captions", status: "ready", translationStatus: "translated", dateKey: "2026-08-14", dateLabel: "Fri · Aug 14", excerpt: "The manufacturing map is changing again, and the most important moves are happening below the level of the finished chip." },
  { id: "models", channel: "ColdFusion", avatar: "CF", title: "A short history of machine learning winters", published: "Wed · 09:14", language: "English", source: "YouTube captions", status: "ready", translationStatus: "translated", dateKey: "2026-08-12", dateLabel: "Wed · Aug 12", excerpt: "The cycle is familiar: exuberance, disappointment, and then a quiet technology that survives long enough to matter." },
];

const STATUS_LABEL: Record<VideoStatus, string> = { ready: "Caption ready", error: "Needs attention", pending: "Fetching caption" };
const DATE_FILTERS = [
  ["all", "All history"],
  ["2026-08-19", "Today"],
  ["2026-08-18", "Yesterday"],
  ["week", "This week"],
] as const;
type DateFilter = (typeof DATE_FILTERS)[number][0];

function translationLabel(video: Video, selected: Set<string>): string {
  if (video.translationStatus === "translated") return "Translated · PDF ready";
  if (selected.has(video.id)) return "Selected for translation";
  return "Not selected";
}

function matchesDate(video: Video, filter: DateFilter): boolean {
  if (filter === "all") return true;
  if (filter === "week") return video.dateKey >= "2026-08-12";
  return video.dateKey === filter;
}

function useVideoState() {
  const [selected, setSelected] = useState<Set<string>>(new Set(["signals", "design"]));
  const [active, setActive] = useState(VIDEOS[0].id);
  const [running, setRunning] = useState(false);
  const [runLabel, setRunLabel] = useState("Last run today · 00:00 Beijing");
  const toggle = (id: string) => setSelected((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const run = () => { if (running) return; setRunning(true); window.setTimeout(() => { setRunning(false); setRunLabel("Just now · 00:00 Beijing"); }, 650); };
  return { active, run, runLabel, running, selected, setActive, toggle };
}

function PrototypeFrame({ children }: { children: React.ReactNode }) {
  return <main className="yt-prototype-page"><div className="yt-prototype-scroll hairline-scroll"><div className="yt-prototype-content">{children}</div></div></main>;
}

function PageActions({ run, running, runLabel, selectedCount }: { run: () => void; running: boolean; runLabel: string; selectedCount: number }) {
  return <div className="yt-page-actions"><span className="yt-run-meta">{runLabel} · {selectedCount} selected</span><button className="btn sm" type="button"><Icon name="plug" size={14} /> Manage connection</button><button className="btn-primary sm" type="button" onClick={run} disabled={running}><Icon name={running ? "refresh" : "clock"} size={14} className={running ? "yt-spin" : undefined} />{running ? "Checking…" : "Run now"}</button></div>;
}

function Status({ status }: { status: VideoStatus }) {
  return <span className={`yt-status yt-status-${status}`}><i />{STATUS_LABEL[status]}</span>;
}

function SelectBox({ checked, onClick }: { checked: boolean; onClick: () => void }) {
  return <span className={`yt-select-box${checked ? " is-selected" : ""}`} role="checkbox" aria-checked={checked} aria-label={checked ? "Remove from translation selection" : "Select for translation"} tabIndex={0} onClick={(event) => { event.stopPropagation(); onClick(); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); onClick(); } }}>{checked ? "✓" : ""}</span>;
}

function ConnectionCard() {
  return <div className="yt-connection yt-card"><span className="yt-connection-mark" role="img" aria-label="YouTube"><BrandIcon name="youtube" size={28} /></span><div className="yt-connection-copy"><strong>YouTube is connected</strong><span>Personal account · subscriptions synced 12 minutes ago</span></div><span className="yt-connected-dot"><i />Connected</span></div>;
}

function PageHeading({ run, running, runLabel, selectedCount, sub }: { run: () => void; running: boolean; runLabel: string; selectedCount: number; sub: string }) {
  return <div className="yt-heading-row"><PanelHead title="YouTube updates" sub={sub} /><PageActions run={run} running={running} runLabel={runLabel} selectedCount={selectedCount} /></div>;
}

function OverviewVariant() {
  const state = useVideoState();
  const [filter, setFilter] = useState<"all" | VideoStatus>("all");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const videos = useMemo(
    () => VIDEOS.filter((video) => (filter === "all" || video.status === filter) && matchesDate(video, dateFilter)),
    [dateFilter, filter],
  );
  const groups = useMemo(() => {
    const map = new Map<string, { label: string; videos: Video[] }>();
    videos.forEach((video) => {
      const group = map.get(video.dateKey);
      if (group) group.videos.push(video);
      else map.set(video.dateKey, { label: video.dateLabel, videos: [video] });
    });
    return [...map.values()];
  }, [videos]);
  const translatedCount = VIDEOS.filter((video) => video.translationStatus === "translated").length;
  const readyCount = VIDEOS.filter((video) => video.status === "ready").length;
  const channelsCount = new Set(VIDEOS.map((video) => video.channel)).size;
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="A daily task watches your subscriptions and keeps one raw caption per new video." />
    <ConnectionCard />
    <div className="yt-summary-row"><div><strong>{VIDEOS.length}</strong><span>videos in library</span></div><div><strong>{readyCount}</strong><span>captions ready</span></div><div><strong>{translatedCount}</strong><span>translated PDFs</span></div><div><strong>{channelsCount}</strong><span>channels tracked</span></div><div className="yt-summary-schedule"><Icon name="clock" size={14} /><span>Daily · 00:00 Beijing</span></div></div>
    <div className="yt-toolbar"><span>{videos.length} {videos.length === 1 ? "video" : "videos"} shown</span><div className="yt-segmented" role="group" aria-label="Filter caption status">{([["all", "All"], ["ready", "Ready"], ["error", "Needs attention"]] as const).map(([key, label]) => <button key={key} type="button" className={filter === key ? "is-active" : ""} onClick={() => setFilter(key)}>{label}</button>)}</div></div>
    <div className="yt-date-tabs" role="tablist" aria-label="Filter by date">{DATE_FILTERS.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={dateFilter === key} className={`yt-date-tab${dateFilter === key ? " is-active" : ""}`} onClick={() => setDateFilter(key)}>{label}</button>)}</div>
    <div className="yt-history-list">{groups.length === 0 && <div className="yt-empty yt-card">No videos match these filters.</div>}{groups.map((group) => <section className="yt-date-group" key={group.label}><div className="yt-date-group-head"><span>{group.label}</span><span>{group.videos.length} {group.videos.length === 1 ? "video" : "videos"}</span></div><div className="yt-list yt-card">{group.videos.map((video) => <button className={`yt-list-row${state.active === video.id ? " is-active" : ""}`} key={video.id} type="button" onClick={() => state.setActive(video.id)}><SelectBox checked={state.selected.has(video.id)} onClick={() => state.toggle(video.id)} /><span className="yt-avatar">{video.avatar}</span><span className="yt-list-copy"><strong>{video.title}</strong><span>{video.channel} · {video.published}</span></span><span className="yt-row-status"><Status status={video.status} /><span className="yt-translation-state">{translationLabel(video, state.selected)}</span></span><Icon name="chevronRight" size={14} className="text-faint" /></button>)}</div></section>)}</div>
    {state.selected.size > 0 && <div className="yt-selection-bar"><span><strong>{state.selected.size}</strong> videos selected for the next translation step.</span><button className="link" type="button">Review selection →</button></div>}
    <p className="yt-footnote"><Icon name="database" size={13} /> Everything stays on this machine. Translation and PDF generation are not part of this first step.</p>
  </PrototypeFrame>;
}

function ChannelsVariant() {
  const state = useVideoState();
  const groups = useMemo(() => { const map = new Map<string, Video[]>(); VIDEOS.forEach((video) => map.set(video.channel, [...(map.get(video.channel) || []), video])); return [...map.entries()]; }, []);
  const [channel, setChannel] = useState(groups[0]?.[0] || "");
  const [historyMode, setHistoryMode] = useState<"all" | "translated">("all");
  const channelVideos = groups.find(([name]) => name === channel)?.[1] || [];
  const videos = historyMode === "translated" ? channelVideos.filter((video) => video.translationStatus === "translated") : channelVideos;
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="Browse the same update set by channel, using the page patterns already used by Integrations." />
    <div className="yt-channel-layout"><aside className="yt-channel-nav yt-card"><div className="yt-section-label">Subscriptions <span>{groups.length}</span></div>{groups.map(([name, channelVideos]) => { const translated = channelVideos.filter((video) => video.translationStatus === "translated").length; return <button key={name} type="button" className={channel === name ? "is-active" : ""} onClick={() => setChannel(name)}><span className="yt-avatar">{channelVideos[0].avatar}</span><span><strong>{name}</strong><small>{channelVideos.length} videos · {translated} translated</small></span></button>; })}<div className="yt-channel-nav-foot"><Icon name="refresh" size={13} /> RSS checked at 00:00 Beijing</div></aside><section className="yt-channel-feed"><div className="yt-feed-head"><div><span className="yt-kicker">Channel history</span><h3>{channel}</h3></div><span>{videos.length} {videos.length === 1 ? "video" : "videos"}</span></div><div className="yt-history-switch" role="tablist" aria-label="Channel history view"><button type="button" role="tab" aria-selected={historyMode === "all"} className={historyMode === "all" ? "is-active" : ""} onClick={() => setHistoryMode("all")}>All videos <span>{channelVideos.length}</span></button><button type="button" role="tab" aria-selected={historyMode === "translated"} className={historyMode === "translated" ? "is-active" : ""} onClick={() => setHistoryMode("translated")}>Translated history <span>{channelVideos.filter((video) => video.translationStatus === "translated").length}</span></button></div><div className="yt-feed-list yt-card">{videos.length === 0 && <div className="yt-empty">No translated videos from this channel yet.</div>}{videos.map((video) => <article className={`yt-feed-row${state.active === video.id ? " is-active" : ""}`} key={video.id} onClick={() => state.setActive(video.id)}><div className="yt-feed-row-top"><span>{video.published}</span><Status status={video.status} /></div><h4>{video.title}</h4><p>{video.excerpt}</p><div className="yt-feed-row-bottom"><button className={`yt-inline-select${state.selected.has(video.id) ? " is-selected" : ""}`} type="button" onClick={(event) => { event.stopPropagation(); state.toggle(video.id); }}>{state.selected.has(video.id) ? "Selected for translation" : translationLabel(video, state.selected)}</button><span>{video.language} · {video.dateLabel}</span></div></article>)}</div></section></div>
  </PrototypeFrame>;
}

function ReaderVariant() {
  const state = useVideoState();
  const active = VIDEOS.find((video) => video.id === state.active) || VIDEOS[0];
  const [readerMode, setReaderMode] = useState<"new" | "translated">("new");
  const queueVideos = useMemo(() => VIDEOS.filter((video) => readerMode === "translated" ? video.translationStatus === "translated" : video.translationStatus !== "translated"), [readerMode]);
  const queueActive = queueVideos.find((video) => video.id === active.id) || queueVideos[0] || active;
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="A focused queue for checking the raw caption before deciding what should be translated." />
    <div className="yt-reader-layout"><section className="yt-reader-queue yt-card"><div className="yt-section-label">Update queue <span>{queueVideos.length}</span></div><div className="yt-reader-tabs" role="tablist" aria-label="Reader queue"><button type="button" role="tab" aria-selected={readerMode === "new"} className={readerMode === "new" ? "is-active" : ""} onClick={() => setReaderMode("new")}>New updates <span>{VIDEOS.filter((video) => video.translationStatus !== "translated").length}</span></button><button type="button" role="tab" aria-selected={readerMode === "translated"} className={readerMode === "translated" ? "is-active" : ""} onClick={() => setReaderMode("translated")}>Translated history <span>{VIDEOS.filter((video) => video.translationStatus === "translated").length}</span></button></div>{queueVideos.map((video) => <button className={`yt-reader-item${video.id === queueActive.id ? " is-active" : ""}`} key={video.id} type="button" onClick={() => state.setActive(video.id)}><SelectBox checked={state.selected.has(video.id)} onClick={() => state.toggle(video.id)} /><span className="yt-reader-item-copy"><strong>{video.title}</strong><span>{video.channel} · {video.published}</span></span><span className={`yt-reader-dot yt-reader-dot-${video.status}`} /></button>)}</section><article className="yt-reader-preview yt-card"><div className="yt-preview-header"><span className="yt-kicker">{queueActive.translationStatus === "translated" ? "Translated history" : "Raw caption"}</span><Status status={queueActive.status} /></div><div className="yt-preview-channel"><span className="yt-avatar yt-avatar-large">{queueActive.avatar}</span><div><strong>{queueActive.channel}</strong><span>{queueActive.published}</span></div></div><h3>{queueActive.title}</h3><div className="yt-preview-meta"><span>{queueActive.language}</span><span>·</span><span>{queueActive.source}</span><span>·</span><span>{translationLabel(queueActive, state.selected)}</span></div><p>{queueActive.excerpt}</p><div className="yt-preview-actions"><button className="btn sm" type="button">Open on YouTube</button><button className={`btn sm${state.selected.has(queueActive.id) ? " yt-btn-selected" : ""}`} type="button" onClick={() => state.toggle(queueActive.id)}>{state.selected.has(queueActive.id) ? "Selected" : "Select for translation"}</button></div></article></div>
  </PrototypeFrame>;
}

const variants = [{ name: "Overview", axis: "Daily scan", render: OverviewVariant }, { name: "Channels", axis: "Subscription groups", render: ChannelsVariant }, { name: "Reader", axis: "Queue + caption", render: ReaderVariant }];

export function YouTubePrototype() {
  const params = new URLSearchParams(window.location.search);
  const initial = Math.min(variants.length - 1, Math.max(0, (Number(params.get("variant") || params.get("v")) || 1) - 1));
  const [current, setCurrent] = useState(initial);
  const [mountKey, setMountKey] = useState(0);
  const active = variants[current];
  const setActive = (index: number) => { if (index < 0 || index >= variants.length) return; setCurrent(index); const url = new URL(window.location.href); url.searchParams.set("variant", String(index + 1)); url.searchParams.delete("v"); window.history.replaceState(null, "", url); setMountKey((key) => key + 1); };
  useEffect(() => { const onKey = (event: KeyboardEvent) => { const target = event.target as HTMLElement | null; if (target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable)) return; if (event.metaKey || event.ctrlKey || event.altKey) return; if (event.key === "ArrowRight") setActive((current + 1) % variants.length); else if (event.key === "ArrowLeft") setActive((current - 1 + variants.length) % variants.length); else if (event.key.toLowerCase() === "r") setMountKey((key) => key + 1); else if (/^[1-3]$/.test(event.key)) setActive(Number(event.key) - 1); }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, [current]);
  const Variant = active.render;
  return <><div key={`${current}-${mountKey}`} className="yt-prototype-stage"><Variant /></div><nav className="proto-picker" aria-label="Prototype variants"><span className="proto-picker-label">Prototype</span><span className="proto-picker-divider" aria-hidden="true" /><button className="proto-picker-arrow" type="button" aria-label="Previous variant" onClick={() => setActive((current - 1 + variants.length) % variants.length)}>←</button><span className="proto-picker-current">{active.name} <small>{active.axis}</small></span><button className="proto-picker-arrow" type="button" aria-label="Next variant" onClick={() => setActive((current + 1) % variants.length)}>→</button><button className="proto-picker-replay" type="button" aria-label="Replay" onClick={() => setMountKey((key) => key + 1)}>↻</button></nav></>;
}
