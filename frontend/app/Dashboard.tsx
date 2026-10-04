"use client";

import { useEffect, useMemo, useState } from "react";
import demoSnapshot from "./data/demo-snapshot.json";
import { loadDashboardData, type DashboardData, type Row } from "./data-source";
import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Database,
  ExternalLink,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Server,
  Wifi,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

const COLORS = {
  cyan: "#56d4ff",
  blue: "#2f6feb",
  orange: "#ff9f43",
  red: "#ff5d7a",
  green: "#25d0a2",
  muted: "#8297b8",
};

function makeDemoData(): DashboardData {
  return structuredClone(demoSnapshot) as DashboardData;
}

function formatNumber(value: unknown, digits = 0) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatTime(value: unknown) {
  const date = new Date(String(value || ""));
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(value: unknown) {
  const date = new Date(String(value || ""));
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatTimelineTick(value: unknown, spanMs: number) {
  const date = new Date(Number(value));
  if (Number.isNaN(date.getTime())) return "—";
  if (spanMs >= 36 * 60 * 60 * 1000) {
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function storyHref(story: Row) {
  const permalink = String(story.permalink || "");
  if (permalink.includes("news.ycombinator.com/item?id=")) return permalink;
  if (story.story_id !== undefined && story.story_id !== null) {
    return `https://news.ycombinator.com/item?id=${story.story_id}`;
  }
  return permalink || String(story.url || "https://news.ycombinator.com/");
}

function discussionHref(story: Row) {
  return storyHref(story);
}

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_SONAR_API_BASE;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return "http://127.0.0.1:8060";
  }
  return "";
}

// Live is opt-in. An API URL left in an environment cannot activate a demo build.
function liveEnabled() {
  return process.env.NEXT_PUBLIC_SONAR_MODE === "live";
}

async function loadDashboard(): Promise<DashboardData> {
  return loadDashboardData({ mode: process.env.NEXT_PUBLIC_SONAR_MODE, base: apiBase(), snapshot: makeDemoData() });
}

function SectionHeader({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy?: string; action?: React.ReactNode }) {
  return (
    <div className="section-header">
      <div>
        <span className="section-kicker">{eyebrow}</span>
        <h2>{title}</h2>
        {copy && <p>{copy}</p>}
      </div>
      {action}
    </div>
  );
}

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`.trim()}>
      <h3 className="panel-title">{title}</h3>
      {children}
    </section>
  );
}

function MetricCard({ label, value, note, alert = false }: { label: string; value: string; note: string; alert?: boolean }) {
  return (
    <div className={`metric-card ${alert ? "metric-alert" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function ChartTooltip({ active, payload, label }: Row) {
  if (!active || !payload?.length) return null;
  const displayLabel = typeof label === "number" && label > 1_000_000_000_000
    ? formatDateTime(label)
    : label;
  return (
    <div className="chart-tooltip">
      <strong>{displayLabel || payload[0]?.payload?.metric_name || "Signal"}</strong>
      {payload.map((item: Row) => (
        <span key={item.dataKey || item.name} style={{ color: item.color || item.fill }}>
          {item.name}: {formatNumber(item.value, 2)}
        </span>
      ))}
    </div>
  );
}

function StoryEngagementTooltip({ active, payload }: Row) {
  if (!active || !payload?.length) return null;
  const story = payload[0]?.payload || {};
  return (
    <div className="chart-tooltip engagement-tooltip">
      <strong>{story.title || "Story"}</strong>
      <span style={{ color: COLORS.cyan }}>HN score: {formatNumber(story.score || 0)}</span>
      <span style={{ color: COLORS.orange }}>Comments: {formatNumber(story.comments || 0)}</span>
    </div>
  );
}

const TOPIC_COLORS = ["#42c8ee", "#3f88d9", "#386fc3", "#407acb", "#327caf", "#4777bc", "#2f659f", "#4a74a8", "#32688d", "#3a79a1"];

function bubbleSignalStrength(item: Row) {
  const explicit = Number(item.signal_strength || 0);
  if (explicit > 0) return explicit;
  const derived = (item.stories || []).reduce(
    (total: number, story: Row) => total + Number(story.score || 0) + (1.5 * Number(story.num_comments || 0)),
    0,
  );
  return derived > 0 ? derived : Number(item.weight || 0);
}

function splitBubbleLabel(label: string, maxCharacters: number) {
  const words = label.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  for (const word of words) {
    const current = lines[lines.length - 1];
    if (current && `${current} ${word}`.length <= maxCharacters) {
      lines[lines.length - 1] = `${current} ${word}`;
    } else if (lines.length < 3) {
      lines.push(word);
    } else {
      lines[2] = `${lines[2]} ${word}`;
    }
  }
  return lines;
}

function packTopicBubbles(items: Row[], width: number, height: number) {
  const ranked = items.slice(0, 10).map((item, index) => ({
    item,
    index,
    strength: bubbleSignalStrength(item),
  }));
  const strengths = ranked.map((entry) => entry.strength);
  const minimum = Math.min(...strengths, 0);
  const maximum = Math.max(...strengths, 1);
  const nodes = ranked
    .map((entry) => {
      const normalized = maximum === minimum ? .5 : (entry.strength - minimum) / (maximum - minimum);
      const area = 4200 + (normalized * 11200);
      return { ...entry, radius: Math.sqrt(area / Math.PI) };
    })
    .sort((a, b) => b.radius - a.radius);

  const centerX = width * .5;
  const centerY = height * .5;
  for (const scale of [1, .92, .84, .76, .68, .6, .52]) {
    const scaled = nodes.map((node) => ({ ...node, radius: node.radius * scale }));
    const placed: Array<(typeof scaled)[number] & { x: number; y: number }> = [];
    let complete = true;

    for (let nodeIndex = 0; nodeIndex < scaled.length; nodeIndex += 1) {
      const node = scaled[nodeIndex];
      if (nodeIndex === 0) {
        placed.push({ ...node, x: centerX, y: centerY });
        continue;
      }

      let best: { x: number; y: number } | null = null;
      for (let step = 0; step < 4200; step += 1) {
        const angle = (step * 2.399963) + (nodeIndex * .83);
        const distance = 18 + (step * .18);
        const x = centerX + (Math.cos(angle) * distance);
        const y = centerY + (Math.sin(angle) * distance * .7);
        const inside = (
          x - node.radius >= 10
          && x + node.radius <= width - 10
          && y - node.radius >= 10
          && y + node.radius <= height - 10
        );
        const clear = placed.every(
          (other) => Math.hypot(x - other.x, y - other.y) >= node.radius + other.radius + 9,
        );
        if (inside && clear) {
          best = { x, y };
          break;
        }
      }

      if (!best) {
        complete = false;
        break;
      }
      placed.push({ ...node, ...best });
    }

    if (complete) return placed;
  }

  return [];
}

function TopicBubbleChart({
  items,
  selectedKeyword,
  onSelectKeyword,
}: {
  items: Row[];
  selectedKeyword: string | null;
  onSelectKeyword: (keyword: string | null) => void;
}) {
  const width = 720;
  const height = 240;
  const nodes = useMemo(() => packTopicBubbles(items, width, height), [items]);
  const maxCoverage = Math.max(...items.map((item) => Number(item.story_count || 0)), 1);
  if (items.length > 0 && items.length < 3) {
    return (
      <div className="topic-signal-list" aria-label={`${items.length} coherent topic signal${items.length === 1 ? "" : "s"}`}>
        {items.map((item) => {
          const isSelected = selectedKeyword === item.keyword;
          return (
            <button
              type="button"
              className={`topic-signal-card${isSelected ? " selected" : ""}`}
              key={item.keyword}
              aria-pressed={isSelected}
              onClick={() => onSelectKeyword(isSelected ? null : item.keyword)}
            >
              <span>
                <b>{item.keyword}</b>
                <small>{item.story_count} supporting stories · {Math.round(Number(item.confidence || 0) * 100)}% reviewed confidence</small>
              </span>
              <strong>{formatNumber(bubbleSignalStrength(item))}<small>HN attention</small></strong>
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <div className="bubble-field">
      {nodes.length ? (
        <svg className="topic-bubble-chart" viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Topic landscape sized by Hacker News attention">
          <defs>
            {nodes.map((node) => {
              const coverage = Number(node.item.story_count || 0) / maxCoverage;
              return (
                <radialGradient key={node.item.keyword} id={`topic-gradient-${node.index}`} cx="32%" cy="24%" r="78%">
                  <stop offset="0%" stopColor={TOPIC_COLORS[node.index % TOPIC_COLORS.length]} stopOpacity={.68 + (coverage * .28)} />
                  <stop offset="100%" stopColor="#173b70" stopOpacity=".94" />
                </radialGradient>
              );
            })}
          </defs>
          {nodes.map((node) => {
            const item = node.item;
            const isSelected = selectedKeyword === item.keyword;
            const maxCharacters = node.radius >= 48 ? 15 : node.radius >= 36 ? 12 : 10;
            const lines = splitBubbleLabel(String(item.keyword), maxCharacters).slice(0, 3);
            const lineHeight = node.radius >= 48 ? 13 : 11;
            const labelStart = -((lines.length - 1) * lineHeight * .5) - (node.radius >= 38 ? 5 : 0);
            const showCount = node.radius >= 34;
            return (
              <g
                className={`topic-bubble${isSelected ? " selected" : ""}`}
                key={item.keyword}
                transform={`translate(${node.x} ${node.y})`}
                role="button"
                tabIndex={0}
                aria-label={`Filter notable stories by ${item.keyword}; ${item.story_count} supporting stories`}
                aria-pressed={isSelected}
                onClick={() => onSelectKeyword(isSelected ? null : item.keyword)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelectKeyword(isSelected ? null : item.keyword);
                  }
                }}
              >
                <title>{`${item.keyword}: ${item.story_count} stories · ${formatNumber(bubbleSignalStrength(item))} HN attention`}</title>
                <circle r={node.radius} fill={`url(#topic-gradient-${node.index})`} />
                <text className={`topic-bubble-label${node.radius < 38 ? " compact" : ""}`} textAnchor="middle">
                  {lines.map((line, lineIndex) => (
                    <tspan key={`${line}-${lineIndex}`} x="0" y={labelStart + (lineIndex * lineHeight)}>{line}</tspan>
                  ))}
                </text>
                {showCount && (
                  <text className="topic-bubble-count" textAnchor="middle" y={labelStart + (lines.length * lineHeight) + 5}>
                    {item.story_count} stories
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      ) : (
        <div className="bubble-empty">No recurring topic has enough supporting stories in this window.</div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [activeView, setActiveView] = useState<"overview" | "intelligence" | "investigations">("overview");
  const [search, setSearch] = useState("");
  const [feed, setFeed] = useState("all");
  const [timeWindow, setTimeWindow] = useState("current");
  const [rankBy, setRankBy] = useState("score");
  const [flagFilter, setFlagFilter] = useState("all");
  const [storyPage, setStoryPage] = useState(1);
  const [selectedKeyword, setSelectedKeyword] = useState<string | null>(null);
  const [selectedWindowIndex, setSelectedWindowIndex] = useState<number | null>(null);

  const refresh = async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const next = await loadDashboard();
      setData(next);
      setNotice("");
    } catch {
      setData(makeDemoData());
      setNotice("Live API unavailable — showing the built-in demonstration snapshot.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    refresh();
    if (!liveEnabled()) return;
    const timer = window.setInterval(() => refresh(), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const filteredStories = useMemo(() => {
    const query = search.trim().toLowerCase();
    const terms = query.split(/\s+/).filter(Boolean);
    const stories = [...(data?.stories || [])];
    const notableIds = new Set(
      (data?.intelligence?.notable_stories || []).map((story: Row) => String(story.story_id)),
    );
    const anomalyFeeds = new Set((data?.anomalies || []).map((item: Row) => item.source_feed));
    const newestObservedAt = Math.max(
      ...stories.map((story) => new Date(String(story.collected_at || 0)).getTime()).filter(Number.isFinite),
      0,
    );
    const cutoffHours = timeWindow === "24h" ? 24 : timeWindow === "7d" ? 168 : null;

    const filtered = stories.filter((story) => {
      const title = String(story.title || "").toLowerCase();
      const observedAt = new Date(String(story.collected_at || 0)).getTime();
      const matchesFeed = feed === "all" || story.source_feed === feed;
      const matchesText = terms.every((term) => title.includes(term));
      const matchesTime = cutoffHours === null || (
        Number.isFinite(observedAt) && observedAt >= newestObservedAt - cutoffHours * 60 * 60 * 1000
      );
      const isBriefing = notableIds.has(String(story.story_id));
      const isAnomaly = anomalyFeeds.has(story.source_feed);
      const matchesFlag = flagFilter === "all"
        || (flagFilter === "briefing" && isBriefing)
        || (flagFilter === "anomaly" && isAnomaly);
      return matchesFeed && matchesText && matchesTime && matchesFlag;
    });

    return filtered.sort((a, b) => {
      if (rankBy === "comments") return Number(b.num_comments || 0) - Number(a.num_comments || 0);
      if (rankBy === "engagement") {
        return (Number(b.score || 0) + Number(b.num_comments || 0))
          - (Number(a.score || 0) + Number(a.num_comments || 0));
      }
      if (rankBy === "newest") {
        return new Date(String(b.collected_at || 0)).getTime() - new Date(String(a.collected_at || 0)).getTime();
      }
      return Number(b.score || 0) - Number(a.score || 0);
    });
  }, [data, search, feed, timeWindow, rankBy, flagFilter]);

  useEffect(() => {
    setStoryPage(1);
  }, [search, feed, timeWindow, rankBy, flagFilter, data]);

  if (loading || !data) {
    return (
      <main className="loading-screen">
        <div className="sonar-loader"><span /><span /><span /></div>
        <p>Calibrating signal radar…</p>
      </main>
    );
  }

  const status = data.overview.status || {};
  const runtime = data.runtime;
  const counts = status.counts || {};
  const intelligence = data.intelligence || {};
  const landscapeBrief = intelligence.monitoring_summary;
  const anomalies = data.anomalies || [];
  const alertCount = anomalies.filter((item) => Number(item.z_score || 0) >= 3).length;
  const metricBuckets = new Map<number, Row>();
  data.metrics.forEach((row) => {
    const timestamp = new Date(String(row.collected_at || "")).getTime();
    if (Number.isNaN(timestamp)) return;
    const bucket = metricBuckets.get(timestamp) || {
      timestamp,
      engagement_score: 0,
      story_volume: 0,
    };
    bucket.engagement_score += Number(row.engagement_score || 0);
    bucket.story_volume += Number(row.story_volume || 0);
    metricBuckets.set(timestamp, bucket);
  });
  const metricData = Array.from(metricBuckets.values()).sort(
    (left, right) => Number(left.timestamp) - Number(right.timestamp),
  );
  const metricSpanMs = metricData.length > 1
    ? Number(metricData[metricData.length - 1].timestamp) - Number(metricData[0].timestamp)
    : 0;
  const timelineTickCount = Math.min(7, metricData.length);
  const metricTicks = Array.from({ length: timelineTickCount }, (_, index) => {
    const dataIndex = timelineTickCount === 1
      ? 0
      : Math.round((index * (metricData.length - 1)) / (timelineTickCount - 1));
    return Number(metricData[dataIndex]?.timestamp);
  });
  const scatterData: Row[] = anomalies.length
    ? anomalies.map((row, index) => ({
        ...row,
        timeIndex: index + 1,
        volume: Math.max(0.1, Number(row.metric_value || index + 1)),
        velocity: Math.max(0.1, Number(row.z_score || 0)),
        size: Math.max(60, Number(row.metric_value || 1)),
        signalType: "Anomaly",
      }))
    : data.metrics.map((row, index) => ({
        ...row,
        id: `${row.source_feed}-${row.collected_at}-${index}`,
        timeIndex: index + 1,
        volume: Math.max(0.1, Number(row.story_volume || 0)),
        velocity: Math.max(0.01, Math.abs(Number(row.growth_rate || 0))),
        size: Math.max(60, Number(row.engagement_score || 1)),
        signalType: "Baseline",
      }));
  const eventBriefs = intelligence.event_briefs || [];
  const totalScore = data.stories.reduce((sum, row) => sum + Number(row.score || 0), 0);
  const totalComments = data.stories.reduce((sum, row) => sum + Number(row.num_comments || 0), 0);
  const emergingTopics = (intelligence.ranked_themes || []).slice(0, 5);
  const maxTopicScore = Math.max(...emergingTopics.map((item: Row) => Number(item.score || 0)), 1);
  const sentimentData = intelligence.sentiment_distribution || [];
  const hasSentiment = sentimentData.some((item: Row) => Number(item.count || 0) > 0);
  const storyPageSize = 10;
  const storyTotalPages = Math.max(1, Math.ceil(filteredStories.length / storyPageSize));
  const safeStoryPage = Math.min(storyPage, storyTotalPages);
  const visibleStories = filteredStories.slice((safeStoryPage - 1) * storyPageSize, safeStoryPage * storyPageSize);
  const notableStoryIds = new Set(
    (intelligence.notable_stories || []).map((story: Row) => String(story.story_id)),
  );
  const anomalyFeeds = new Set(anomalies.map((item: Row) => item.source_feed));
  const selectedWindowStories = selectedWindowIndex === null
    ? []
    : data.stories.slice(selectedWindowIndex % Math.max(data.stories.length - 2, 1), (selectedWindowIndex % Math.max(data.stories.length - 2, 1)) + 3);
  const topicClusters = intelligence.topic_clusters || intelligence.keyword_bubbles || [];
  const selectedKeywordItem = topicClusters.find(
    (item: Row) => item.keyword === selectedKeyword,
  );
  const selectedTokens = String(
    selectedKeywordItem?.raw_keyword || selectedKeyword || "",
  ).toLowerCase().split(/\s+/).filter(Boolean);
  const matchedStories = selectedKeyword
    ? ((selectedKeywordItem?.stories || []).length
      ? selectedKeywordItem.stories
      : data.stories.filter((story) => {
          const title = String(story.title || "").toLowerCase();
          return selectedTokens.some((token) => title.includes(token));
        }))
    : (intelligence.notable_stories || data.stories);
  const matchedStoryScore = matchedStories.reduce((sum: number, story: Row) => sum + Number(story.score || 0), 0);
  const matchedStoryComments = matchedStories.reduce((sum: number, story: Row) => sum + Number(story.num_comments || 0), 0);
  const engagementData = (intelligence.notable_stories || data.stories).slice(0, 14).map((story: Row) => ({
    title: story.title,
    score: Number(story.score || 0),
    comments: Number(story.num_comments || 0),
    attention: Math.max(1, Number(story.score || 0) + Number(story.num_comments || 0)),
  }));
  const statusRows = [
    { icon: Wifi, label: "Data stream", detail: data.mode === "live" ? "Healthy" : "Demo snapshot", value: data.mode === "live" ? "Live" : "Ready" },
    { icon: Radio, label: "Coverage", detail: "Hacker News feeds", value: `${data.overview.feed_summary?.length || 2} feeds` },
    { icon: Database, label: "Signals analyzed", detail: "Current dataset", value: formatNumber(counts.stories || data.stories.length) },
    { icon: RefreshCw, label: "Refresh rate", detail: data.mode === "live" ? "Status-aware polling" : "Recorded data · no polling", value: data.mode === "live" ? "60 sec" : "Off" },
    { icon: ShieldCheck, label: "Confidence filter", detail: "Evidence-backed", value: "On" },
  ];

  return (
    <main className="dashboard">
      <header className="hero">
        <div className="app-bar">
          <div className="brand-pill"><Activity size={13} /> Sonar</div>
          <nav className="workspace-tabs" aria-label="Dashboard sections">
            {[
              ["overview", "Overview"],
              ["intelligence", "AI intelligence"],
              ["investigations", "Investigations"],
            ].map(([id, label]) => (
              <button
                type="button"
                key={id}
                aria-pressed={activeView === id}
                onClick={() => setActiveView(id as typeof activeView)}
              >
                {label}
              </button>
            ))}
          </nav>
          <button className="refresh-button" type="button" onClick={() => refresh(true)} disabled={refreshing}>
            <RefreshCw size={14} className={refreshing ? "spin" : ""} />
            {refreshing ? "Refreshing" : data.mode === "demo" ? "Reload snapshot" : "Refresh"}
          </button>
        </div>
        <div className="hero-copy">
          <h1>Hacker News signal radar</h1>
          <p>{data.mode === "demo" ? "Explore recorded HN signals, anomaly detection and evidence-grounded AI intelligence." : "Live HN signals, anomaly detection and evidence-grounded AI intelligence."}</p>
        </div>
        <div className="command-center">
          <div className="command-topline">
            <span>Command center</span>
            <i className={alertCount ? "status-dot warning" : "status-dot"} />
          </div>
          <strong className={alertCount ? "alert-mode" : "stable-mode"}>
            {data.mode === "demo" ? "Interactive demo" : alertCount ? "Alert mode" : "Monitoring stable"}
          </strong>
          <p>
            {data.mode === "demo" ? "Recorded production data. Live collection is offline." : alertCount
              ? `${alertCount} high-confidence signal requires review.`
              : "No high-confidence anomalies in the current window."}
          </p>
          <div className="command-meta">
            <span><b>Mode</b>{data.mode === "live" ? "Live API" : "Demo snapshot"}</span>
            <span><b>Gemini</b>{data.mode === "demo" ? "Recorded output" : status.gemini_status || "ready"}</span>
            <span><b>{data.mode === "demo" ? "Snapshot" : "Last scan"}</b>{data.mode === "demo" ? formatDateTime(demoSnapshot.captured_at) : formatTime(status.last_collection_time)}</span>
          </div>
        </div>
      </header>

      {(notice || data.mode === "demo") && (
        <div className="demo-banner">
          <Sparkles size={14} />
          {notice || `Demo · production snapshot captured ${formatDateTime(demoSnapshot.captured_at)} · no live API, database, or Gemini calls.`}
        </div>
      )}

      <section className="metric-grid">
        <MetricCard label="New stories volume" value={formatNumber(counts.stories || data.stories.length)} note="Current monitored window" />
        <MetricCard label="Hacker News score" value={formatNumber(totalScore)} note="Latest observed story scores" />
        <MetricCard label="HN comments" value={formatNumber(totalComments)} note="Conversation intensity" />
        <MetricCard label="Active alerts" value={formatNumber(alertCount)} note={`${anomalies.length} signals under triage`} alert={alertCount > 0} />
      </section>

      {activeView === "overview" && (
        <>
          <section className="overview-board">
            <Panel title="Signal overview" className="signal-overview-panel">
                <div className="overview-stats">
                  <span><small>Signals</small><b>{formatNumber(counts.stories || data.stories.length)}</b></span>
                  <span><small>Trending</small><b className="cyan-value">{formatNumber(totalComments)}</b></span>
                  <span><small>Emerging</small><b className="orange-value">{formatNumber(emergingTopics.length)}</b></span>
                  <span><small>Anomalies</small><b className="red-value">{formatNumber(anomalies.length)}</b></span>
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart
                    data={metricData}
                    onClick={(state: Row) => {
                      const index = Number(state?.activeTooltipIndex);
                      if (Number.isInteger(index)) setSelectedWindowIndex(index);
                    }}
                  >
                    <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
                    <XAxis
                      type="number"
                      scale="time"
                      dataKey="timestamp"
                      domain={["dataMin", "dataMax"]}
                      ticks={metricTicks}
                      minTickGap={36}
                      tickFormatter={(value) => formatTimelineTick(value, metricSpanMs)}
                      tick={{ fill: COLORS.muted, fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={42} />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="engagement_score" name="Signal intensity" stroke={COLORS.cyan} strokeWidth={2} dot={false} activeDot={{ r: 5 }} />
                    <Line type="monotone" dataKey="story_volume" name="Story volume" stroke={COLORS.blue} strokeWidth={1.2} dot={false} activeDot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
                <div className="chart-action-row">
                  <span>Click a point to inspect stories from that signal window.</span>
                  {selectedWindowIndex !== null && <button type="button" onClick={() => setSelectedWindowIndex(null)}>Close detail</button>}
                </div>
                {selectedWindowIndex !== null && (
                  <div className="trend-story-detail">
                    <strong>{formatDateTime(metricData[selectedWindowIndex]?.timestamp) || "Selected window"} · {selectedWindowStories.length} related stories</strong>
                    {selectedWindowStories.map((story) => (
                      <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                        <span>{story.title}</span>
                        <small>{formatNumber(story.score)} pts</small>
                      </a>
                    ))}
                  </div>
                )}
            </Panel>

            <Panel title={data.mode === "demo" ? "Snapshot status" : "Live status"} className="operations-status-panel">
              <div className={alertCount ? "operations-alert active" : "operations-alert"}>
                <AlertTriangle size={18} />
                <span><b>{data.mode === "demo" ? "Recorded monitoring state" : alertCount ? "Anomaly detected" : "Monitoring stable"}</b><small>{data.mode === "demo" ? "Explore the captured signals below" : alertCount ? "High-confidence signal requires review" : "All monitored feeds are within range"}</small></span>
                <em>{data.mode === "demo" ? "Snapshot" : alertCount ? "Now" : "Healthy"}</em>
              </div>
              <div className="operations-status-list">
                {statusRows.map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.label}>
                      <Icon size={18} />
                      <span><b>{item.label}</b><small>{item.detail}</small></span>
                      <strong>{item.value}</strong>
                    </div>
                  );
                })}
              </div>
            </Panel>

            <Panel title="Top emerging topics" className="emerging-panel">
              <div className="emerging-list">
                {emergingTopics.map((item: Row, index: number) => {
                  const isSelected = selectedKeyword === item.theme;
                  return (
                    <button
                      type="button"
                      key={item.theme}
                      aria-pressed={isSelected}
                      onClick={() => {
                        setSelectedKeyword(isSelected ? null : item.theme);
                        setActiveView("intelligence");
                      }}
                    >
                      <span><b>{item.theme}</b><em>{formatNumber(item.score)}</em></span>
                      <i><span style={{ width: `${Math.max(14, (Number(item.score || 0) / maxTopicScore) * 100)}%`, opacity: 1 - index * 0.1 }} /></i>
                    </button>
                  );
                })}
                {!emergingTopics.length && (
                  <div className="panel-empty-state">
                    <b>Building the semantic baseline</b>
                    <span>Topics will appear after the first successful Gemini landscape summary.</span>
                  </div>
                )}
              </div>
            </Panel>

            <Panel title="Signal velocity" className="velocity-panel">
              {scatterData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ left: 2, right: 20, top: 8, bottom: 0 }}>
                    <CartesianGrid stroke="rgba(112,151,204,.10)" />
                    <XAxis type="number" dataKey="volume" name="Volume" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis type="number" dataKey="velocity" name="Velocity" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                    <ZAxis type="number" dataKey="size" range={[55, 190]} />
                    <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<ChartTooltip />} />
                    <Scatter data={scatterData}>
                      {scatterData.map((item, index) => (
                        <Cell
                          key={item.id || index}
                          fill={item.signalType === "Anomaly" && item.news_aligned ? COLORS.orange : COLORS.cyan}
                        />
                      ))}
                    </Scatter>
                  </ScatterChart>
                </ResponsiveContainer>
              ) : (
                <div className="panel-empty-state">
                  <b>Waiting for the first metrics window</b>
                  <span>Velocity will populate after the collector records a baseline.</span>
                </div>
              )}
            </Panel>

            <Panel title={data.mode === "demo" ? "Signal feed (snapshot)" : "Signal feed (live)"} className="signal-feed-panel">
              <div className="signal-feed-list">
                {data.stories.slice(0, 7).map((story, index) => (
                  <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                    <time>{formatTime(story.collected_at)}</time>
                    <span className={story.source_feed === "topstories" ? "feed-kind hot" : "feed-kind"}>{story.source_feed === "topstories" ? "Top" : "New"}</span>
                    <b>{story.title}</b>
                    <i className="micro-trend" aria-hidden="true">
                      {[32, 45, 39, 64, 48, 75, 57].map((height, point) => (
                        <span key={point} style={{ height: `${Math.max(14, height - index * 4)}%` }} />
                      ))}
                    </i>
                    <strong>↑ {formatNumber(Number(story.score || 0) + Number(story.num_comments || 0))}</strong>
                  </a>
                ))}
              </div>
            </Panel>
          </section>

          <section className="overview-lower-grid">
            <Panel title="Top feed new entries" className="top-entry-panel">
              <div className="table-intro">
                <span>Strongest new stories in the current observation window</span>
                <small>Ranked by score and conversation velocity</small>
              </div>
              <div className="compact-table">
                {data.stories.slice(0, 5).map((story) => (
                  <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                    <span>{story.title}</span>
                    <b>{formatNumber(story.score)}</b>
                    <em>{formatNumber(story.num_comments)} comments</em>
                    <small>{formatTime(story.collected_at)}</small>
                  </a>
                ))}
              </div>
            </Panel>

            <Panel title="Top stories by score gain" className="score-panel">
              <div className="score-bars">
                {data.stories.slice(0, 6).map((story, index) => {
                  const max = Number(data.stories[0]?.score || 1);
                  const width = Math.max(12, (Number(story.score || 0) / max) * 100);
                  return (
                    <div className="score-row" key={story.story_id}>
                      <div className="score-track">
                        <span style={{ width: `${width}%`, opacity: 1 - index * 0.09 }} />
                        <a href={storyHref(story)} target="_blank" rel="noreferrer">{story.title}</a>
                      </div>
                      <b>{formatNumber(story.score)}</b>
                    </div>
                  );
                })}
              </div>
            </Panel>
          </section>
        </>
      )}

      {activeView === "intelligence" && (
      <section className="intelligence-section">
        <SectionHeader eyebrow="AI intelligence" title="Current news landscape" copy="Gemini synthesis of the themes, technologies, and discussions across the latest monitored stories." />
        <div className="ai-grid">
          <article className="latest-brief">
            <div className="brief-heading">
              <span>Current landscape</span>
              <span className="confidence">Gemini landscape summary</span>
            </div>
            <h3>{landscapeBrief?.headline_summary || "No landscape summary generated yet"}</h3>
            <p>{landscapeBrief?.summary}</p>
            <ul>
              {(landscapeBrief?.bullet_insights || []).slice(0, 3).map((item: string) => <li key={item}>{item}</li>)}
            </ul>
            <div className="brief-tags">
              <span>{landscapeBrief?.topic || "News landscape"}</span>
              <span>{landscapeBrief?.model || "provider ready"}</span>
              <span>{landscapeBrief?.evidence_count || 0} stories analyzed</span>
            </div>
          </article>
          <div className="intelligence-summary-row">
            <Panel title="Ranked themes" className="theme-panel">
              {emergingTopics.length ? (
                <ol>
                  {emergingTopics.map((item: Row, index: number) => {
                    const score = Number(item.score || 0);
                    const prominence = score > 0
                      ? (score / maxTopicScore) * 100
                      : ((emergingTopics.length - index) / emergingTopics.length) * 100;
                    return (
                    <li key={item.theme}>
                      <span className="theme-rank">{String(item.rank).padStart(2, "0")}</span>
                      <div className="theme-rank-copy">
                        <b>{item.theme}</b>
                        <i><span style={{ width: `${Math.max(12, prominence)}%` }} /></i>
                      </div>
                    </li>
                    );
                  })}
                </ol>
              ) : (
                <div className="panel-empty-state compact">
                  <b>No themes classified yet</b>
                  <span>The next Gemini landscape summary will populate this ranking.</span>
                </div>
              )}
            </Panel>
            <Panel title="Signal sentiment" className="sentiment-panel">
              {hasSentiment ? (
                <ResponsiveContainer width="100%" height={190}>
                  <BarChart data={sentimentData}>
                    <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
                    <XAxis dataKey="label" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
                    <Tooltip content={<ChartTooltip />} />
                    <Bar dataKey="count" name="Share" radius={[3, 3, 0, 0]}>
                      {sentimentData.map((item: Row) => (
                        <Cell key={item.label} fill={{ positive: COLORS.green, negative: COLORS.red, neutral: "#7f8da5", mixed: COLORS.orange }[item.label as string] || COLORS.cyan} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="panel-empty-state compact">
                  <b>No sentiment distribution yet</b>
                  <span>The next semantic scan will classify the current story landscape.</span>
                </div>
              )}
            </Panel>
            <Panel title="Engagement profile" className="engagement-panel">
              <p className="chart-caption">HN score → · comments ↑ · bubble size = total attention</p>
              <ResponsiveContainer width="100%" height={174}>
                <ScatterChart margin={{ top: 6, right: 8, bottom: 2, left: -8 }}>
                  <CartesianGrid stroke="rgba(112,151,204,.10)" />
                  <XAxis type="number" dataKey="score" name="HN score" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis type="number" dataKey="comments" name="Comments" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} width={38} />
                  <ZAxis type="number" dataKey="attention" range={[45, 170]} />
                  <Tooltip content={<StoryEngagementTooltip />} cursor={{ stroke: "rgba(86,212,255,.25)", strokeDasharray: "3 3" }} />
                  <Scatter data={engagementData} fill={COLORS.cyan}>
                    {engagementData.map((story: Row, index: number) => (
                      <Cell key={`${story.title}-${index}`} fill={story.comments > story.score ? COLORS.orange : COLORS.cyan} fillOpacity={.86} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </Panel>
          </div>
          <section className="topic-evidence-workspace">
            <div className="keyword-workspace">
              <h3 className="panel-title">Keyword explorer</h3>
              <div className="interactive-panel-heading">
                <span>{topicClusters.length < 3 ? "Only concepts supported by multiple stories are shown" : "Select a concept to inspect its supporting stories · bubble area = HN attention"}</span>
                {selectedKeyword && <button type="button" onClick={() => setSelectedKeyword(null)}>Clear filter</button>}
              </div>
              <TopicBubbleChart
                items={topicClusters}
                selectedKeyword={selectedKeyword}
                onSelectKeyword={setSelectedKeyword}
              />
            </div>
            <div className="evidence-workspace">
              <div className="evidence-workspace-heading">
                <div>
                  <h3 className="panel-title">Notable stories</h3>
                  <span>{selectedKeyword ? `Evidence for “${selectedKeyword}”` : "Highest-signal stories"}</span>
                </div>
                <b>{matchedStories.length} stories</b>
              </div>
              <dl className="evidence-summary">
                <div><dt>Coverage</dt><dd>{matchedStories.length}</dd></div>
                <div><dt>HN score</dt><dd>{formatNumber(matchedStoryScore)}</dd></div>
                <div><dt>Comments</dt><dd>{formatNumber(matchedStoryComments)}</dd></div>
              </dl>
              <div className="notable-list evidence-list">
                {matchedStories.slice(0, 8).map((story: Row) => (
                  <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                    <span>{story.title}</span>
                    <small>{formatNumber(story.score)} pts · {formatNumber(story.num_comments)} comments</small>
                  </a>
                ))}
                {matchedStories.length === 0 && <p className="empty-filter">No stories match this topic in the current window.</p>}
              </div>
            </div>
          </section>
        </div>
      </section>
      )}

      {activeView === "investigations" && (
      <section className="investigation-workspace">
        <SectionHeader
          eyebrow="Investigation workspace"
          title="Evidence briefs and monitored stories"
          copy={`${eventBriefs.length} active cases connected to ${data.stories.length} Hacker News stories.`}
          action={<span className="verified-badge"><ShieldCheck size={15} /> API-only data boundary</span>}
        />

        <div className="investigation-cases" aria-label="Investigation cases">
          {eventBriefs.slice(0, 5).map((brief: Row, index: number) => {
            return (
              <article
                className="investigation-case"
                tabIndex={0}
                key={brief.id}
              >
                <span className="case-summary-top">
                  <span><i className={brief.news_aligned ? "case-dot aligned" : "case-dot"} /> Case {String(index + 1).padStart(2, "0")}</span>
                  <em>{Math.round(Number(brief.confidence || 0) * 100)}%</em>
                </span>
                <b>{brief.headline_summary || brief.topic}</b>
                <small>{brief.topic} · {brief.evidence_count || 0} evidence items</small>
                <div className="case-expanded">
                  <div className="case-facts">
                    <span><b>Feed</b>{brief.source_feed || "—"}</span>
                    <span><b>Triggered by</b>{brief.triggered_by || "—"}</span>
                    <span><b>Evidence</b>{brief.evidence_count || 0} linked records</span>
                    <span><b>News</b>{brief.news_aligned ? "Externally aligned" : "Unconfirmed"}</span>
                  </div>
                  <p>{brief.summary || "No investigation summary is available."}</p>
                  <div className="case-tags">
                    <span>{brief.event_type?.replaceAll("_", " ") || "signal review"} · z {formatNumber(brief.z_score, 1)}</span>
                    <span>{brief.sentiment_label || "neutral"}</span>
                    <span>{Math.round(Number(brief.confidence || 0) * 100)}% confidence</span>
                  </div>
                </div>
              </article>
            );
          })}
          {!eventBriefs.length && (
            <div className="panel-empty-state compact">
              <b>No active investigations</b>
              <span>Evidence cases appear here when a monitored signal crosses the anomaly threshold.</span>
            </div>
          )}
        </div>

        <div className="story-workspace-heading">
          <div>
            <span className="section-kicker">Story explorer</span>
            <h3>Latest monitored Hacker News stories</h3>
          </div>
          <p>Filter the evidence set by feed, time, rank or title.</p>
        </div>

        <div className="story-panel">
          <div className="story-toolbar">
            <label className="story-search"><span>Search</span><span><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Titles or keywords" /></span></label>
            <label><span>Time window</span><select value={timeWindow} onChange={(event) => setTimeWindow(event.target.value)}>
              <option value="current">Current snapshot</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select></label>
            <label><span>Rank by</span><select value={rankBy} onChange={(event) => setRankBy(event.target.value)}>
              <option value="score">Highest score</option>
              <option value="comments">Most comments</option>
              <option value="engagement">Highest engagement</option>
              <option value="newest">Newest</option>
            </select></label>
            <label><span>Feed</span><select value={feed} onChange={(event) => setFeed(event.target.value)}>
              <option value="all">All feeds</option>
              <option value="topstories">Top stories</option>
              <option value="newstories">New stories</option>
              <option value="beststories">Best stories</option>
            </select></label>
            <label><span>Evidence flag</span><select value={flagFilter} onChange={(event) => setFlagFilter(event.target.value)}>
              <option value="all">All signals</option>
              <option value="briefing">★ Briefing evidence</option>
              <option value="anomaly">⚠ Anomaly-adjacent</option>
            </select></label>
          </div>
          <div className="story-table-summary">
            <span>★ briefing evidence · ⚠ anomaly-adjacent</span>
            <b>
              {filteredStories.length
                ? `${(safeStoryPage - 1) * storyPageSize + 1}–${Math.min(safeStoryPage * storyPageSize, filteredStories.length)} of ${filteredStories.length}`
                : "0 stories"}
            </b>
          </div>
          <div className="story-table-wrap">
            <table>
              <thead><tr><th>Flag</th><th>Feed</th><th>Story</th><th>Score</th><th>Comments</th><th>Observed</th><th>Discussion</th></tr></thead>
              <tbody>
                {visibleStories.map((story) => {
                  const isBriefing = notableStoryIds.has(String(story.story_id));
                  const isAnomaly = anomalyFeeds.has(story.source_feed);
                  return (
                    <tr key={`${story.story_id}-${story.source_feed}`}>
                      <td className="story-flag">{isBriefing ? "★" : isAnomaly ? "⚠" : ""}</td>
                      <td><span className="feed-chip">{story.source_feed}</span></td>
                      <td><a className="story-title-link" href={storyHref(story)} target="_blank" rel="noreferrer">{story.title}</a></td>
                      <td>{formatNumber(story.score)}</td>
                      <td>{formatNumber(story.num_comments)}</td>
                      <td>{formatDateTime(story.collected_at)}</td>
                      <td><a href={discussionHref(story)} target="_blank" rel="noreferrer" aria-label={`Open Hacker News discussion for ${story.title}`}><ExternalLink size={15} /></a></td>
                    </tr>
                  );
                })}
                {visibleStories.length === 0 && <tr><td colSpan={7} className="empty-table">No stories match the selected filters.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="pagination-controls" aria-label="Story pages">
            <span className="pagination-range">
              Showing <b>{filteredStories.length ? (safeStoryPage - 1) * storyPageSize + 1 : 0}–{Math.min(safeStoryPage * storyPageSize, filteredStories.length)}</b> of {filteredStories.length}
            </span>
            <div className="pagination-stepper">
              <button type="button" onClick={() => setStoryPage(Math.max(1, safeStoryPage - 1))} disabled={safeStoryPage === 1}>
                <ChevronLeft size={16} /> Previous
              </button>
              <span className="pagination-status"><small>Page</small> {safeStoryPage} <i>/</i> {storyTotalPages}</span>
              <button type="button" onClick={() => setStoryPage(Math.min(storyTotalPages, safeStoryPage + 1))} disabled={safeStoryPage === storyTotalPages}>
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </section>
      )}

      {data.mode === "live" ? <aside className="runtime-verification" aria-label="Live infrastructure verification">
        <div className="runtime-verification-heading">
          <Server size={17} />
          <span>
            <small>Live infrastructure verification</small>
            <b>{runtime?.cloud_run_verified ? "Running on Google Cloud Run" : "Runtime verification unavailable"}</b>
          </span>
        </div>
        <dl>
          <div><dt>Service</dt><dd>{runtime?.service || "—"}</dd></div>
          <div><dt>Revision</dt><dd>{runtime?.revision || "—"}</dd></div>
          <div><dt>Database</dt><dd>{runtime?.database?.status === "connected" ? "PostgreSQL connected" : "—"}</dd></div>
        </dl>
        <a href={`${apiBase()}/api/runtime`} target="_blank" rel="noreferrer">
          Open live runtime record <ExternalLink size={14} />
        </a>
      </aside> : <aside className="runtime-verification" aria-label="Demo data provenance">
        <div className="runtime-verification-heading">
          <Database size={17} />
          <span><small>Recorded production snapshot</small><b>Interactive demo · cloud backend offline</b></span>
        </div>
        <dl>
          <div><dt>Captured</dt><dd>{formatDateTime(demoSnapshot.captured_at)}</dd></div>
          <div><dt>Stories available</dt><dd>{data.stories.length}</dd></div>
          <div><dt>Live API / AI calls</dt><dd>None</dd></div>
        </dl>
        <a href="https://github.com/Yerong27/sonar-ai" target="_blank" rel="noreferrer">Explore the project <ExternalLink size={14} /></a>
      </aside>}

      <footer>
        <span><Activity size={14} /> Sonar AI</span>
        <p>{data.mode === "demo" ? "Interactive demo · Recorded data · No live collection" : "Sites dashboard · Cloud Run API · Cloud SQL PostgreSQL"}</p>
      </footer>
    </main>
  );
}
