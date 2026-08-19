import { useEffect, useMemo, useState } from "react";
import { PanelHead } from "./PanelHead";
import { Icon } from "./Icon";
import "./youtube-prototype.css";

// PROTOTYPE — three YouTube views embedded in the real Automations surface.
// Question: which information hierarchy belongs in production without inventing
// a second visual language for Vegapunk?

type VideoStatus = "ready" | "error" | "pending";

type Video = {
  id: string;
  channel: string;
  avatar: string;
  title: string;
  published: string;
  language: string;
  source: string;
  status: VideoStatus;
  excerpt: string;
};

const VIDEOS: Video[] = [
  { id: "signals", channel: "ColdFusion", avatar: "CF", title: "The quiet infrastructure behind the AI boom", published: "Today · 08:42", language: "English", source: "YouTube captions", status: "ready", excerpt: "There is a layer of infrastructure most people never see. It decides what becomes possible before the model ever runs." },
  { id: "systems", channel: "Fireship", avatar: "FS", title: "The web platform is changing again", published: "Yesterday · 21:10", language: "English · auto", source: "Transcript fallback", status: "ready", excerpt: "The next phase of the web is less about another framework and more about the boundaries between local and remote software." },
  { id: "design", channel: "The Futur", avatar: "TF", title: "Why good interfaces leave room for silence", published: "Yesterday · 16:03", language: "English", source: "YouTube captions", status: "ready", excerpt: "A calm interface is not an empty interface. It is a system that knows what deserves attention now and what can wait." },
  { id: "research", channel: "Two Minute Papers", avatar: "2M", title: "This model learns to see the invisible", published: "Mon · 11:28", language: "No caption", source: "Will retry next run", status: "error", excerpt: "The paper introduces a surprisingly simple trick: keep the uncertainty visible instead of smoothing it away." },
  { id: "history", channel: "Asianometry", avatar: "AS", title: "The supply chain that made modern chips possible", published: "Sun · 19:32", language: "Fetching caption", source: "Scheduled retry", status: "pending", excerpt: "A map of the companies, ports, and patient engineering decisions that quietly shaped the modern semiconductor world." },
];

const STATUS_LABEL: Record<VideoStatus, string> = { ready: "Caption ready", error: "Needs attention", pending: "Fetching caption" };

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
  return <div className="yt-connection yt-card"><div className="yt-connection-mark"><span>YT</span></div><div className="yt-connection-copy"><strong>YouTube is connected</strong><span>Personal account · subscriptions synced 12 minutes ago</span></div><span className="yt-connected-dot"><i />Connected</span></div>;
}

function PageHeading({ run, running, runLabel, selectedCount, sub }: { run: () => void; running: boolean; runLabel: string; selectedCount: number; sub: string }) {
  return <div className="yt-heading-row"><PanelHead title="YouTube updates" sub={sub} /><PageActions run={run} running={running} runLabel={runLabel} selectedCount={selectedCount} /></div>;
}

function OverviewVariant() {
  const state = useVideoState();
  const [filter, setFilter] = useState<"all" | VideoStatus>("all");
  const videos = VIDEOS.filter((video) => filter === "all" || video.status === filter);
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="A daily task watches your subscriptions and keeps one raw caption per new video." />
    <ConnectionCard />
    <div className="yt-summary-row"><div><strong>5</strong><span>new videos</span></div><div><strong>3</strong><span>captions ready</span></div><div><strong>2</strong><span>selected for translation</span></div><div className="yt-summary-schedule"><Icon name="clock" size={14} /><span>Daily · 00:00 Beijing</span></div></div>
    <div className="yt-toolbar"><span>{videos.length} updates</span><div className="yt-segmented" role="group" aria-label="Filter updates">{([["all", "All"], ["ready", "Ready"], ["error", "Needs attention"]] as const).map(([key, label]) => <button key={key} type="button" className={filter === key ? "is-active" : ""} onClick={() => setFilter(key)}>{label}</button>)}</div></div>
    <div className="yt-list yt-card">{videos.map((video) => <button className={`yt-list-row${state.active === video.id ? " is-active" : ""}`} key={video.id} type="button" onClick={() => state.setActive(video.id)}><SelectBox checked={state.selected.has(video.id)} onClick={() => state.toggle(video.id)} /><span className="yt-avatar">{video.avatar}</span><span className="yt-list-copy"><strong>{video.title}</strong><span>{video.channel} · {video.published}</span></span><Status status={video.status} /><Icon name="chevronRight" size={14} className="text-faint" /></button>)}</div>
    {state.selected.size > 0 && <div className="yt-selection-bar"><span><strong>{state.selected.size}</strong> videos selected for the next translation step.</span><button className="link" type="button">Review selection →</button></div>}
    <p className="yt-footnote"><Icon name="database" size={13} /> Everything stays on this machine. Translation and PDF generation are not part of this first step.</p>
  </PrototypeFrame>;
}

function ChannelsVariant() {
  const state = useVideoState();
  const groups = useMemo(() => { const map = new Map<string, Video[]>(); VIDEOS.forEach((video) => map.set(video.channel, [...(map.get(video.channel) || []), video])); return [...map.entries()]; }, []);
  const [channel, setChannel] = useState(groups[0]?.[0] || "");
  const videos = groups.find(([name]) => name === channel)?.[1] || [];
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="Browse the same update set by channel, using the page patterns already used by Integrations." />
    <div className="yt-channel-layout"><aside className="yt-channel-nav yt-card"><div className="yt-section-label">Subscriptions <span>{groups.length}</span></div>{groups.map(([name, channelVideos]) => <button key={name} type="button" className={channel === name ? "is-active" : ""} onClick={() => setChannel(name)}><span className="yt-avatar">{channelVideos[0].avatar}</span><span><strong>{name}</strong><small>{channelVideos.length} update{channelVideos.length === 1 ? "" : "s"}</small></span></button>)}<div className="yt-channel-nav-foot"><Icon name="refresh" size={13} /> RSS checked at 00:00 Beijing</div></aside><section className="yt-channel-feed"><div className="yt-feed-head"><div><span className="yt-kicker">Channel updates</span><h3>{channel}</h3></div><span>{videos.length} videos</span></div><div className="yt-feed-list yt-card">{videos.map((video) => <article className={`yt-feed-row${state.active === video.id ? " is-active" : ""}`} key={video.id} onClick={() => state.setActive(video.id)}><div className="yt-feed-row-top"><span>{video.published}</span><Status status={video.status} /></div><h4>{video.title}</h4><p>{video.excerpt}</p><div className="yt-feed-row-bottom"><button className={`yt-inline-select${state.selected.has(video.id) ? " is-selected" : ""}`} type="button" onClick={(event) => { event.stopPropagation(); state.toggle(video.id); }}>{state.selected.has(video.id) ? "Selected for translation" : "Select for translation"}</button><span>{video.language}</span></div></article>)}</div></section></div>
  </PrototypeFrame>;
}

function ReaderVariant() {
  const state = useVideoState();
  const active = VIDEOS.find((video) => video.id === state.active) || VIDEOS[0];
  return <PrototypeFrame>
    <PageHeading run={state.run} running={state.running} runLabel={state.runLabel} selectedCount={state.selected.size} sub="A focused queue for checking the raw caption before deciding what should be translated." />
    <div className="yt-reader-layout"><section className="yt-reader-queue yt-card"><div className="yt-section-label">Update queue <span>{VIDEOS.length}</span></div>{VIDEOS.map((video) => <button className={`yt-reader-item${video.id === active.id ? " is-active" : ""}`} key={video.id} type="button" onClick={() => state.setActive(video.id)}><SelectBox checked={state.selected.has(video.id)} onClick={() => state.toggle(video.id)} /><span className="yt-reader-item-copy"><strong>{video.title}</strong><span>{video.channel} · {video.published}</span></span><span className={`yt-reader-dot yt-reader-dot-${video.status}`} /></button>)}</section><article className="yt-reader-preview yt-card"><div className="yt-preview-header"><span className="yt-kicker">Raw caption</span><Status status={active.status} /></div><div className="yt-preview-channel"><span className="yt-avatar yt-avatar-large">{active.avatar}</span><div><strong>{active.channel}</strong><span>{active.published}</span></div></div><h3>{active.title}</h3><div className="yt-preview-meta"><span>{active.language}</span><span>·</span><span>{active.source}</span></div><p>{active.excerpt}</p><div className="yt-preview-actions"><button className="btn sm" type="button">Open on YouTube</button><button className={`btn sm${state.selected.has(active.id) ? " yt-btn-selected" : ""}`} type="button" onClick={() => state.toggle(active.id)}>{state.selected.has(active.id) ? "Selected" : "Select for translation"}</button></div></article></div>
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
