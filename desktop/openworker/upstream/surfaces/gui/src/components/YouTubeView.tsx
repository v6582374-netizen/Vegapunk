import { useEffect, useMemo, useState } from "react";
import {
  createYouTubeAutomation,
  announceAutomationsChanged,
  deleteYouTubeVideo,
  disconnectYouTube,
  getAutomations,
  getYouTubeStatus,
  getYouTubeVideo,
  getYouTubeVideos,
  refreshYouTubeSubscriptions,
  runYouTubeAutomation,
  setYouTubeVideoSelected,
  startYouTubeOAuth,
  type Automation,
  type YouTubeStatus,
  type YouTubeVideo,
} from "../api";
import { PanelHead } from "./PanelHead";
import { Icon } from "./Icon";
import { BrandIcon } from "./brandIcons";
import "./youtube-prototype.css";

type ViewMode = "overview" | "channels" | "reader";
type DateFilter = "all" | "today" | "yesterday" | "week";
type ReaderFilter = "all" | "selected" | "ready" | "attention";

type VideoMeta = YouTubeVideo & {
  avatar: string;
  dateKey: string;
  dateLabel: string;
  publishedLabel: string;
};

const TIME_ZONE = "Asia/Shanghai";

function partsFor(value: number | string | null | undefined) {
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value || "");
  if (Number.isNaN(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const map = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    dateKey: `${map.year}-${map.month}-${map.day}`,
    weekday: map.weekday,
    hour: map.hour,
    minute: map.minute,
    monthDay: new Intl.DateTimeFormat("en-US", { timeZone: TIME_ZONE, month: "short", day: "numeric" }).format(date),
  };
}

function dateKeyForNow(offsetDays = 0): string {
  const now = new Date(Date.now() - offsetDays * 86400000);
  return partsFor(now.toISOString())?.dateKey || "";
}

function dateLabel(dateKey: string, monthDay: string, weekday: string): string {
  const today = dateKeyForNow();
  const yesterday = dateKeyForNow(1);
  if (dateKey === today) return `Today · ${monthDay}`;
  if (dateKey === yesterday) return `Yesterday · ${monthDay}`;
  return `${weekday} · ${monthDay}`;
}

function weekStartKey(): string {
  const now = new Date();
  const day = now.getDay();
  return partsFor(new Date(now.getTime() - ((day + 6) % 7) * 86400000).toISOString())?.dateKey || "";
}

function avatarFor(title: string): string {
  const words = title.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "CH";
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
}

function toMeta(video: YouTubeVideo): VideoMeta {
  const parts = partsFor(video.published_ts ?? video.published_at);
  const dateKey = parts?.dateKey || "unknown";
  return {
    ...video,
    avatar: avatarFor(video.channel_title),
    dateKey,
    dateLabel: parts ? dateLabel(dateKey, parts.monthDay, parts.weekday) : "Unknown date",
    publishedLabel: parts ? `${parts.weekday} · ${parts.hour}:${parts.minute}` : video.published_at,
  };
}

function statusLabel(video: YouTubeVideo): string {
  if (video.caption_status === "ready") return "Caption ready";
  if (video.caption_status === "error") return "Needs attention";
  return "Fetching caption";
}

function statusClass(video: YouTubeVideo): string {
  if (video.caption_status === "ready") return "ready";
  if (video.caption_status === "error") return "error";
  return "pending";
}

function formatTime(value?: number | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value * 1000));
}

function Status({ video }: { video: YouTubeVideo }) {
  return <span className={`yt-status yt-status-${statusClass(video)}`}><i />{statusLabel(video)}</span>;
}

function SelectBox({ checked, onClick }: { checked: boolean; onClick: () => void }) {
  return <span
    className={`yt-select-box${checked ? " is-selected" : ""}`}
    role="checkbox"
    aria-checked={checked}
    aria-label={checked ? "Remove from translation selection" : "Select for translation"}
    tabIndex={0}
    onClick={(event) => { event.stopPropagation(); onClick(); }}
    onKeyDown={(event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        onClick();
      }
    }}
  >{checked ? "✓" : ""}</span>;
}

function Shell({ children }: { children: React.ReactNode }) {
  return <main className="yt-prototype-page"><div className="yt-prototype-scroll hairline-scroll"><div className="yt-prototype-content">{children}</div></div></main>;
}

export function YouTubeView({ automationId, onBack }: { automationId?: string; onBack?: () => void }) {
  const [status, setStatus] = useState<YouTubeStatus | null>(null);
  const [videos, setVideos] = useState<VideoMeta[]>([]);
  const [automation, setAutomation] = useState<Automation | null>(null);
  const [view, setView] = useState<ViewMode>("overview");
  const [dateFilter, setDateFilter] = useState<DateFilter>("all");
  const [readerFilter, setReaderFilter] = useState<ReaderFilter>("all");
  const [channel, setChannel] = useState<string>("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<YouTubeVideo | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"connect" | "disconnect" | "refresh" | "run" | "create" | "delete" | null>(null);
  const [waitingForOAuth, setWaitingForOAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [nextStatus, nextVideos, tasks] = await Promise.all([
        getYouTubeStatus(),
        getYouTubeVideos(),
        getAutomations(),
      ]);
      setStatus(nextStatus);
      setVideos(nextVideos.videos.map(toMeta));
      setAutomation(
        (automationId ? tasks.find((task) => task.id === automationId) : tasks.find((task) => task.kind === "youtube")) || null,
      );
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load YouTube data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [automationId]);

  useEffect(() => {
    if (!waitingForOAuth) return;
    const poll = window.setInterval(() => {
      getYouTubeStatus()
        .then((next) => {
          if (!next.connected) return;
          setWaitingForOAuth(false);
          setNotice("YouTube connected. Your subscriptions are ready to scan.");
          void load();
        })
        .catch(() => {});
    }, 2000);
    return () => window.clearInterval(poll);
  }, [waitingForOAuth]);

  useEffect(() => {
    if (!activeId) return;
    const cached = videos.find((video) => video.video_id === activeId);
    if (!cached) return;
    setDetail((current) => current?.video_id === activeId ? current : cached);
    getYouTubeVideo(activeId)
      .then((result) => setDetail(result.video))
      .catch(() => {});
  }, [activeId, videos]);

  const channelGroups = useMemo(() => {
    const groups = new Map<string, VideoMeta[]>();
    videos.forEach((video) => groups.set(video.channel_title, [...(groups.get(video.channel_title) || []), video]));
    return [...groups.entries()];
  }, [videos]);

  useEffect(() => {
    if (!channel && channelGroups[0]) setChannel(channelGroups[0][0]);
    if (channel && !channelGroups.some(([name]) => name === channel)) setChannel(channelGroups[0]?.[0] || "");
  }, [channel, channelGroups]);

  const selectedCount = videos.filter((video) => video.selected).length;
  const readyCount = videos.filter((video) => video.caption_status === "ready").length;
  const attentionCount = videos.filter((video) => video.caption_status === "error").length;

  const run = async () => {
    if (!automation) {
      setBusy("create");
      try {
        const result = await createYouTubeAutomation();
        if (!result.ok || !result.task) throw new Error(result.error || "Unable to create the daily task.");
        setAutomation(result.task);
        announceAutomationsChanged();
        setNotice("Daily YouTube task is active at 00:00 Beijing.");
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Unable to create the daily task.");
      } finally {
        setBusy(null);
      }
      return;
    }
    setBusy("run");
    try {
      const result = await runYouTubeAutomation(automation.id);
      if (!result?.ok) throw new Error(result?.error || "The YouTube run failed.");
      setNotice("YouTube updates checked. New captions are now available locally.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The YouTube run failed.");
    } finally {
      setBusy(null);
    }
  };

  const connect = async () => {
    setBusy("connect");
    try {
      const result = await startYouTubeOAuth();
      if (!result.ok || !result.authorization_url) throw new Error(result.error || "Unable to start YouTube authorization.");
      window.open(result.authorization_url, "youtube-oauth", "noopener,noreferrer");
      setWaitingForOAuth(true);
      setNotice("Finish Google sign-in in the new tab, then return here.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start YouTube authorization.");
    } finally {
      setBusy(null);
    }
  };

  const disconnect = async () => {
    setBusy("disconnect");
    try {
      await disconnectYouTube();
      setNotice("YouTube disconnected. Local videos were kept.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to disconnect YouTube.");
    } finally {
      setBusy(null);
    }
  };

  const refreshSubscriptions = async () => {
    setBusy("refresh");
    try {
      const result = await refreshYouTubeSubscriptions();
      if (!result.ok) throw new Error(result.error || "Unable to refresh subscriptions.");
      setNotice(`${result.count || 0} subscriptions synced.`);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to refresh subscriptions.");
    } finally {
      setBusy(null);
    }
  };

  const toggleSelected = async (video: Pick<YouTubeVideo, "video_id" | "selected">) => {
    const next = !video.selected;
    setVideos((current) => current.map((item) => item.video_id === video.video_id ? { ...item, selected: next } : item));
    try {
      await setYouTubeVideoSelected(video.video_id, next);
    } catch (cause) {
      setVideos((current) => current.map((item) => item.video_id === video.video_id ? { ...item, selected: video.selected } : item));
      setError(cause instanceof Error ? cause.message : "Unable to update selection.");
    }
  };

  const removeVideo = async (video: Pick<YouTubeVideo, "video_id" | "title">) => {
    if (!window.confirm(`Delete “${video.title}” from this local library?`)) return;
    setBusy("delete");
    try {
      await deleteYouTubeVideo(video.video_id);
      setVideos((current) => current.filter((item) => item.video_id !== video.video_id));
      if (activeId === video.video_id) {
        setActiveId(null);
        setDetail(null);
      }
      setNotice("Video removed from the local library.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete video.");
    } finally {
      setBusy(null);
    }
  };

  const filterDate = (video: VideoMeta) => {
    if (dateFilter === "all") return true;
    if (dateFilter === "today") return video.dateKey === dateKeyForNow();
    if (dateFilter === "yesterday") return video.dateKey === dateKeyForNow(1);
    return video.dateKey >= weekStartKey() && video.dateKey <= dateKeyForNow();
  };

  const overviewVideos = videos.filter(filterDate);
  const groupedOverview = useMemo(() => {
    const map = new Map<string, { label: string; videos: VideoMeta[] }>();
    overviewVideos.forEach((video) => {
      const group = map.get(video.dateKey);
      if (group) group.videos.push(video);
      else map.set(video.dateKey, { label: video.dateLabel, videos: [video] });
    });
    return [...map.values()];
  }, [overviewVideos]);

  const channelVideos = videos.filter((video) => video.channel_title === channel);
  const readerVideos = videos.filter((video) => {
    if (readerFilter === "selected") return video.selected;
    if (readerFilter === "ready") return video.caption_status === "ready";
    if (readerFilter === "attention") return video.caption_status === "error";
    return true;
  });
  const selectedVideo = (activeId ? videos.find((video) => video.video_id === activeId) : null) || readerVideos[0] || videos[0] || null;

  if (loading && !status) {
    return <Shell><div className="yt-empty-state"><span className="yt-loading-dot" /><span>Loading YouTube library…</span></div></Shell>;
  }

  return <Shell>
    {onBack && <button className="yt-back-link" type="button" onClick={onBack}>← Automations</button>}
    <div className="yt-heading-row">
      <PanelHead title="YouTube updates" sub="A daily task watches your subscriptions, keeps the best available raw caption, and stores everything locally." />
      <div className="yt-page-actions">
        <span className="yt-run-meta">{status?.last_scan_at ? `Last check ${formatTime(status.last_scan_at)}` : "No update check yet"}</span>
        {status?.connected ? <button className="btn sm" type="button" onClick={disconnect} disabled={busy !== null}><Icon name="plug" size={14} />{busy === "disconnect" ? "Disconnecting…" : "Disconnect"}</button> : <button className="btn sm" type="button" onClick={connect} disabled={busy !== null || !status?.configured}><BrandIcon name="youtube" size={15} />{busy === "connect" ? "Opening…" : "Connect YouTube"}</button>}
        <button className="btn-primary sm" type="button" onClick={run} disabled={busy !== null || !status?.connected}>{busy === "create" ? "Creating task…" : busy === "run" ? "Checking…" : automation ? "Run now" : "Enable daily task"}</button>
      </div>
    </div>

    {error && <div className="yt-inline-alert yt-inline-alert-error"><span>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
    {notice && <div className="yt-inline-alert"><span>{notice}</span><button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notice">×</button></div>}

    <div className={`yt-connection yt-card${status?.connected ? "" : " yt-connection-disconnected"}`}><span className="yt-connection-mark" role="img" aria-label="YouTube"><BrandIcon name="youtube" size={28} /></span><div className="yt-connection-copy"><strong>{status?.connected ? "YouTube is connected" : status?.configured ? "Connect your YouTube account" : "YouTube OAuth is not configured"}</strong><span>{status?.connected ? `${status.account_title || "Personal account"} · ${status.channel_count} subscriptions synced locally` : status?.configured ? "Google sign-in is required before RSS discovery can run." : "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET on the server first."}</span></div><span className={`yt-connected-dot${status?.connected ? "" : " yt-disconnected-dot"}`}><i />{status?.connected ? "Connected" : "Not connected"}</span></div>

    {!status?.connected && <div className="yt-setup-card yt-card"><div><span className="yt-kicker">First step</span><h3>Connect once, then let the task run unattended.</h3><p>The OAuth refresh token stays in the local secret store. Disconnecting removes the token but keeps your local video library.</p></div><button className="btn-primary sm" type="button" onClick={connect} disabled={busy !== null || !status?.configured}>{busy === "connect" ? "Opening…" : "Connect YouTube"}</button></div>}

    <div className="yt-view-tabs" role="tablist" aria-label="YouTube library views"><button type="button" role="tab" aria-selected={view === "overview"} className={view === "overview" ? "is-active" : ""} onClick={() => setView("overview")}>Overview <span>{videos.length}</span></button><button type="button" role="tab" aria-selected={view === "channels"} className={view === "channels" ? "is-active" : ""} onClick={() => setView("channels")}>Channels <span>{channelGroups.length}</span></button><button type="button" role="tab" aria-selected={view === "reader"} className={view === "reader" ? "is-active" : ""} onClick={() => setView("reader")}>Caption reader <span>{readyCount}</span></button></div>

    <div className="yt-summary-row"><div><strong>{videos.length}</strong><span>videos in library</span></div><div><strong>{readyCount}</strong><span>captions ready</span></div><div><strong>{selectedCount}</strong><span>selected for translation</span></div><div><strong>{channelGroups.length}</strong><span>channels tracked</span></div><div className="yt-summary-schedule"><Icon name="clock" size={14} /><span>{automation ? "Daily · 00:00 Beijing" : "Daily task not enabled"}</span></div></div>

    {view === "overview" && <>
      <div className="yt-toolbar"><span>{overviewVideos.length} {overviewVideos.length === 1 ? "video" : "videos"} shown</span><div className="yt-segmented" role="group" aria-label="Filter by date status"><button type="button" className={dateFilter === "all" ? "is-active" : ""} onClick={() => setDateFilter("all")}>All history</button><button type="button" className={dateFilter === "today" ? "is-active" : ""} onClick={() => setDateFilter("today")}>Today</button><button type="button" className={dateFilter === "yesterday" ? "is-active" : ""} onClick={() => setDateFilter("yesterday")}>Yesterday</button><button type="button" className={dateFilter === "week" ? "is-active" : ""} onClick={() => setDateFilter("week")}>This week</button></div></div>
      <div className="yt-history-list">{groupedOverview.length === 0 && <div className="yt-empty yt-card">No videos match this date range.</div>}{groupedOverview.map((group) => <section className="yt-date-group" key={group.label}><div className="yt-date-group-head"><span>{group.label}</span><span>{group.videos.length} {group.videos.length === 1 ? "video" : "videos"}</span></div><div className="yt-list yt-card">{group.videos.map((video) => <article className={`yt-list-row${activeId === video.video_id ? " is-active" : ""}`} key={video.video_id} role="button" tabIndex={0} onClick={() => { setActiveId(video.video_id); setView("reader"); }} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setActiveId(video.video_id); setView("reader"); } }}><SelectBox checked={video.selected} onClick={() => void toggleSelected(video)} /><span className="yt-avatar">{video.avatar}</span><span className="yt-list-copy"><strong>{video.title}</strong><span>{video.channel_title} · {video.publishedLabel}</span></span><span className="yt-row-status"><Status video={video} /><span className="yt-translation-state">{video.selected ? "Selected for translation" : "Not selected"}</span></span><button className="yt-row-delete" type="button" aria-label={`Delete ${video.title}`} onClick={(event) => { event.stopPropagation(); void removeVideo(video); }}><Icon name="trash" size={13} /></button></article>)}</div></section>)}</div>
      {selectedCount > 0 && <div className="yt-selection-bar"><span><strong>{selectedCount}</strong> videos selected for the later translation step.</span><span className="yt-selection-note">Raw captions are the current implementation boundary.</span></div>}
      <div className="yt-library-foot"><button className="link" type="button" onClick={refreshSubscriptions} disabled={busy !== null || !status?.connected}><Icon name="refresh" size={13} /> {busy === "refresh" ? "Syncing subscriptions…" : "Sync subscriptions"}</button><span><Icon name="database" size={13} /> All data stays on this machine.</span></div>
    </>}

    {view === "channels" && <div className="yt-channel-layout"><aside className="yt-channel-nav yt-card"><div className="yt-section-label">Subscriptions <span>{channelGroups.length}</span></div>{channelGroups.map(([name, channelVideos]) => <button key={name} type="button" className={channel === name ? "is-active" : ""} onClick={() => setChannel(name)}><span className="yt-avatar">{channelVideos[0]?.avatar || avatarFor(name)}</span><span><strong>{name}</strong><small>{channelVideos.length} videos · {channelVideos.filter((video) => video.caption_status === "ready").length} captions ready</small></span></button>)}{channelGroups.length === 0 && <div className="yt-empty">No subscriptions synced yet.</div>}<div className="yt-channel-nav-foot"><Icon name="refresh" size={13} /> RSS checked by the daily task</div></aside><section className="yt-channel-feed"><div className="yt-feed-head"><div><span className="yt-kicker">Channel history</span><h3>{channel || "No channel selected"}</h3></div><span>{channelVideos.length} {channelVideos.length === 1 ? "video" : "videos"}</span></div><div className="yt-feed-list yt-card">{channelVideos.length === 0 && <div className="yt-empty">No videos from this channel yet.</div>}{channelVideos.map((video) => <article className={`yt-feed-row${activeId === video.video_id ? " is-active" : ""}`} key={video.video_id} onClick={() => { setActiveId(video.video_id); setView("reader"); }}><div className="yt-feed-row-top"><span>{video.dateLabel} · {video.publishedLabel.split(" · ").pop()}</span><Status video={video} /></div><h4>{video.title}</h4><p>{video.caption_status === "ready" ? "Raw caption is available locally and ready for review." : video.caption_error || "Caption retrieval is still in progress."}</p><div className="yt-feed-row-bottom"><button className={`yt-inline-select${video.selected ? " is-selected" : ""}`} type="button" onClick={(event) => { event.stopPropagation(); void toggleSelected(video); }}>{video.selected ? "Selected for translation" : "Select for translation"}</button><button className="yt-inline-delete" type="button" onClick={(event) => { event.stopPropagation(); void removeVideo(video); }}><Icon name="trash" size={12} /> Delete</button></div></article>)}</div></section></div>}

    {view === "reader" && <div className="yt-reader-layout"><section className="yt-reader-queue yt-card"><div className="yt-section-label">Caption queue <span>{readerVideos.length}</span></div><div className="yt-reader-tabs" role="tablist" aria-label="Caption queue filter"><button type="button" role="tab" aria-selected={readerFilter === "all"} className={readerFilter === "all" ? "is-active" : ""} onClick={() => setReaderFilter("all")}>All videos <span>{videos.length}</span></button><button type="button" role="tab" aria-selected={readerFilter === "selected"} className={readerFilter === "selected" ? "is-active" : ""} onClick={() => setReaderFilter("selected")}>Selected <span>{selectedCount}</span></button><button type="button" role="tab" aria-selected={readerFilter === "ready"} className={readerFilter === "ready" ? "is-active" : ""} onClick={() => setReaderFilter("ready")}>Ready <span>{readyCount}</span></button><button type="button" role="tab" aria-selected={readerFilter === "attention"} className={readerFilter === "attention" ? "is-active" : ""} onClick={() => setReaderFilter("attention")}>Needs attention <span>{attentionCount}</span></button></div>{readerVideos.map((video) => <button className={`yt-reader-item${activeId === video.video_id ? " is-active" : ""}`} key={video.video_id} type="button" onClick={() => setActiveId(video.video_id)}><SelectBox checked={video.selected} onClick={() => void toggleSelected(video)} /><span className="yt-reader-item-copy"><strong>{video.title}</strong><span>{video.channel_title} · {video.dateLabel}</span></span><span className={`yt-reader-dot yt-reader-dot-${statusClass(video)}`} /></button>)}{readerVideos.length === 0 && <div className="yt-empty">Nothing in this queue.</div>}</section><article className="yt-reader-preview yt-card">{selectedVideo ? <><div className="yt-preview-header"><span className="yt-kicker">Raw caption</span><Status video={selectedVideo} /></div><div className="yt-preview-channel"><span className="yt-avatar yt-avatar-large">{selectedVideo.channel_title ? avatarFor(selectedVideo.channel_title) : "CH"}</span><div><strong>{selectedVideo.channel_title}</strong><span>{selectedVideo.dateLabel} · {selectedVideo.publishedLabel.split(" · ").pop()}</span></div></div><h3>{selectedVideo.title}</h3><div className="yt-preview-meta"><span>{selectedVideo.caption?.language_name || "No caption"}</span><span>·</span><span>{selectedVideo.caption?.source || selectedVideo.caption_error || "Waiting for caption"}</span></div><div className="yt-caption-body">{detail?.video_id === selectedVideo.video_id && detail.caption_body ? detail.caption_body : selectedVideo.caption_status === "error" ? selectedVideo.caption_error : selectedVideo.caption_status === "pending" ? "Caption retrieval is still in progress. The next scheduled run will retry all available fallbacks." : "Caption body is loading…"}</div><div className="yt-preview-actions"><a className="btn sm" href={selectedVideo.url} target="_blank" rel="noreferrer">Open on YouTube</a><button className={`btn sm${selectedVideo.selected ? " yt-btn-selected" : ""}`} type="button" onClick={() => void toggleSelected(selectedVideo)}>{selectedVideo.selected ? "Selected" : "Select for translation"}</button><button className="btn sm danger-btn" type="button" onClick={() => void removeVideo(selectedVideo)}><Icon name="trash" size={13} /> Delete</button></div></> : <div className="yt-empty-state"><span>Select a video to inspect its caption.</span></div>}</article></div>}
  </Shell>;
}
