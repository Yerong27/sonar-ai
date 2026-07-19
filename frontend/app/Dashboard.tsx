"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ExternalLink,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
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

type Row = Record<string, any>;
type DashboardData = {
  overview: Row;
  metrics: Row[];
  intelligence: Row;
  stories: Row[];
  anomalies: Row[];
  mode: "live" | "demo";
};

const COLORS = {
  cyan: "#56d4ff",
  blue: "#2f6feb",
  orange: "#ff9f43",
  red: "#ff5d7a",
  green: "#25d0a2",
  muted: "#8297b8",
};

const demoStories = [
  { story_id: 1, source_feed: "topstories", title: "Open models are changing the economics of AI inference", score: 2277, num_comments: 482, collected_at: "2026-07-19T05:42:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 2, source_feed: "topstories", title: "Show HN: A privacy-first local coding agent", score: 1541, num_comments: 323, collected_at: "2026-07-19T05:36:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 3, source_feed: "newstories", title: "Inside the new generation of vector databases", score: 1191, num_comments: 476, collected_at: "2026-07-19T05:31:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 4, source_feed: "topstories", title: "A tiny compiler that explains every optimization", score: 864, num_comments: 172, collected_at: "2026-07-19T05:25:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 5, source_feed: "newstories", title: "Why observability systems fail during real incidents", score: 739, num_comments: 208, collected_at: "2026-07-19T05:18:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 6, source_feed: "topstories", title: "The hidden maintenance cost of generated code", score: 691, num_comments: 221, collected_at: "2026-07-19T05:11:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 7, source_feed: "newstories", title: "Postgres at the edge: lessons from production", score: 565, num_comments: 103, collected_at: "2026-07-19T05:03:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 8, source_feed: "topstories", title: "A practical guide to secure model context protocols", score: 493, num_comments: 156, collected_at: "2026-07-19T04:57:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 9, source_feed: "newstories", title: "Building a search engine with SQLite", score: 428, num_comments: 92, collected_at: "2026-07-19T04:48:00Z", permalink: "https://news.ycombinator.com/" },
  { story_id: 10, source_feed: "topstories", title: "What senior engineers actually do", score: 387, num_comments: 141, collected_at: "2026-07-19T04:40:00Z", permalink: "https://news.ycombinator.com/" },
];

const demoMetrics = [
  [0, 12, 4, 1180], [1, 19, 7, 1420], [2, 15, 5, 1290], [3, 10, 8, 1510],
  [4, 8, 6, 1330], [5, 11, 9, 1670], [6, 7, 12, 1810], [7, 16, 10, 1740],
  [8, 9, 14, 2130], [9, 13, 17, 2277], [10, 18, 21, 2460], [11, 22, 16, 2277],
].map(([slot, volume, entries, engagement]) => ({
  collected_at: new Date(Date.now() - (11 - slot) * 30 * 60 * 1000).toISOString(),
  source_feed: slot % 2 ? "topstories" : "newstories",
  story_volume: volume,
  avg_score: entries,
  avg_comments: Math.round(entries * 0.62),
  engagement_score: engagement,
}));

const demoAnomalies = [
  { id: 1, source_feed: "topstories", metric_name: "engagement_score", z_score: 3.8, metric_value: 2277, triggered_by: "engagement_score", detected_at: "2026-07-19T05:44:00Z", news_aligned: true, explanation_status: "complete" },
  { id: 2, source_feed: "newstories", metric_name: "story_volume", z_score: 2.9, metric_value: 22, triggered_by: "story_volume", detected_at: "2026-07-19T04:18:00Z", news_aligned: false, explanation_status: "complete" },
  { id: 3, source_feed: "topstories", metric_name: "avg_comments", z_score: 2.6, metric_value: 1274, triggered_by: "avg_comments", detected_at: "2026-07-19T03:27:00Z", news_aligned: true, explanation_status: "complete" },
  { id: 4, source_feed: "newstories", metric_name: "growth_rate", z_score: 2.3, metric_value: 1.8, triggered_by: "growth_rate", detected_at: "2026-07-19T02:42:00Z", news_aligned: false, explanation_status: "suppressed" },
  { id: 5, source_feed: "topstories", metric_name: "story_volume", z_score: 2.1, metric_value: 18, triggered_by: "story_volume", detected_at: "2026-07-19T01:18:00Z", news_aligned: false, explanation_status: "complete" },
];

const demoBriefs = [
  {
    id: 1,
    headline_summary: "Open AI infrastructure dominates today’s developer attention",
    topic: "AI Infrastructure",
    summary: "Open models and local coding agents are drawing unusually concentrated engagement. The signal is supported by several high-scoring, independently discussed stories.",
    event_type: "engagement_spike",
    sentiment_label: "positive",
    confidence: 0.87,
    news_aligned: true,
    evidence_count: 5,
    source_feed: "topstories",
    metric_name: "engagement_score",
    z_score: 3.8,
    triggered_by: "engagement_score",
    ai_status: "complete",
    model: "gemini-2.5-flash",
    bullet_insights: [
      "Local inference and coding agents account for most of the current engagement gain.",
      "Discussion spans cost, privacy, and developer control rather than a single product launch.",
      "External coverage confirms sustained interest in open model infrastructure.",
    ],
  },
  {
    id: 2,
    headline_summary: "Database tooling moves from storage toward AI retrieval",
    topic: "Data Infrastructure",
    summary: "Vector search and SQLite-based retrieval are rising together, suggesting renewed interest in simpler AI data stacks.",
    event_type: "research_breakthrough",
    sentiment_label: "neutral",
    confidence: 0.72,
    news_aligned: false,
    evidence_count: 4,
    source_feed: "newstories",
    metric_name: "story_volume",
    z_score: 2.9,
    triggered_by: "story_volume",
    ai_status: "complete",
    model: "gemini-2.5-flash",
    bullet_insights: ["Search infrastructure is the second-largest topic cluster.", "Interest is distributed across several stories.", "External confirmation remains limited."],
  },
  {
    id: 3,
    headline_summary: "Generated code quality becomes a high-comment controversy",
    topic: "Software Quality",
    summary: "A concentrated discussion is forming around the long-term maintenance cost of AI-generated code.",
    event_type: "controversy",
    sentiment_label: "mixed",
    confidence: 0.79,
    news_aligned: true,
    evidence_count: 3,
    source_feed: "topstories",
    metric_name: "avg_comments",
    z_score: 2.6,
    triggered_by: "avg_comments",
    ai_status: "complete",
    model: "gemini-2.5-flash",
    bullet_insights: ["Comment velocity is high relative to score.", "Most discussion focuses on review burden.", "The topic may persist beyond the current window."],
  },
];

function makeDemoData(): DashboardData {
  const counts = {
    stories: 22,
    anomalies: 1,
    explanations: demoBriefs.length,
    ai_runs: demoBriefs.length,
  };
  return {
    overview: {
      status: {
        counts,
        last_collection_time: new Date().toISOString(),
        gemini_status: "ok",
      },
      top_stories: demoStories.slice(0, 8),
      latest_anomalies: demoAnomalies,
      latest_brief: demoBriefs[0],
      feed_summary: [
        { source_feed: "topstories", story_count: 12, total_score: 7117, total_comments: 1800 },
        { source_feed: "newstories", story_count: 10, total_score: 3280, total_comments: 1120 },
      ],
    },
    metrics: demoMetrics,
    intelligence: {
      latest_brief: demoBriefs[0],
      event_briefs: demoBriefs,
      ranked_themes: [
        { rank: 1, theme: "AI Infrastructure", score: 9 },
        { rank: 2, theme: "Software Quality", score: 7 },
        { rank: 3, theme: "Data Infrastructure", score: 6 },
        { rank: 4, theme: "Developer Tools", score: 4 },
        { rank: 5, theme: "Security", score: 3 },
      ],
      heading_visibility: [
        { keyword: "AI", visibility: 501 }, { keyword: "Tools", visibility: 408 },
        { keyword: "Data", visibility: 161 }, { keyword: "Programming", visibility: 143 },
        { keyword: "Security", visibility: 121 },
      ],
      sentiment_distribution: [
        { label: "positive", count: 3 }, { label: "negative", count: 1 },
        { label: "neutral", count: 4 }, { label: "mixed", count: 2 },
      ],
      keyword_bubbles: [
        { keyword: "AI", weight: 100, story_count: 8 }, { keyword: "LLMs", weight: 45, story_count: 4 },
        { keyword: "Programming", weight: 33, story_count: 5 }, { keyword: "Data", weight: 38, story_count: 4 },
        { keyword: "Security", weight: 28, story_count: 3 }, { keyword: "Tools", weight: 24, story_count: 3 },
        { keyword: "Open Source", weight: 20, story_count: 3 },
      ],
      notable_stories: demoStories.slice(0, 5),
    },
    stories: demoStories,
    anomalies: demoAnomalies,
    mode: "demo",
  };
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

function apiBase() {
  const configured = process.env.NEXT_PUBLIC_SONAR_API_BASE;
  if (configured) return configured.replace(/\/$/, "");
  if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    return "http://127.0.0.1:8060";
  }
  return "";
}

async function fetchJson(path: string) {
  const response = await fetch(`${apiBase()}${path}`);
  if (!response.ok) throw new Error(`API ${response.status}`);
  return response.json();
}

async function loadDashboard(): Promise<DashboardData> {
  if (!apiBase()) return makeDemoData();
  const [overview, metrics, intelligence, stories, anomalies] = await Promise.all([
    fetchJson("/api/dashboard/overview"),
    fetchJson("/api/metrics/timeline?limit=160"),
    fetchJson("/api/ai/intelligence"),
    fetchJson("/api/stories?limit=80"),
    fetchJson("/api/anomalies?limit=40"),
  ]);
  return {
    overview,
    metrics: metrics.timeline || [],
    intelligence,
    stories: stories.stories || [],
    anomalies: anomalies.anomalies || [],
    mode: "live",
  };
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
  return (
    <div className="chart-tooltip">
      <strong>{label || payload[0]?.payload?.metric_name || "Signal"}</strong>
      {payload.map((item: Row) => (
        <span key={item.dataKey || item.name} style={{ color: item.color || item.fill }}>
          {item.name}: {formatNumber(item.value, 2)}
        </span>
      ))}
    </div>
  );
}

function BubbleField({ items }: { items: Row[] }) {
  const slots = [[50, 48], [23, 42], [78, 42], [30, 72], [69, 72], [15, 70], [85, 72]];
  const max = Math.max(...items.map((item) => Number(item.weight || 1)), 1);
  return (
    <div className="bubble-field" aria-label="Keyword explorer">
      {items.slice(0, slots.length).map((item, index) => {
        const size = 48 + (Number(item.weight || 1) / max) * 78;
        return (
          <button
            type="button"
            className={index === 0 ? "bubble-node primary" : "bubble-node"}
            key={item.keyword}
            style={{ left: `${slots[index][0]}%`, top: `${slots[index][1]}%`, width: size, height: size }}
            title={`${item.story_count || 0} related stories`}
          >
            {item.keyword}
          </button>
        );
      })}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState("");
  const [feed, setFeed] = useState("all");
  const [openBrief, setOpenBrief] = useState<number | string | null>(1);

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
    const timer = window.setInterval(() => refresh(), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const filteredStories = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.stories || []).filter((story) => {
      const matchesFeed = feed === "all" || story.source_feed === feed;
      const matchesText = !query || String(story.title || "").toLowerCase().includes(query);
      return matchesFeed && matchesText;
    });
  }, [data, search, feed]);

  if (loading || !data) {
    return (
      <main className="loading-screen">
        <div className="sonar-loader"><span /><span /><span /></div>
        <p>Calibrating signal radar…</p>
      </main>
    );
  }

  const status = data.overview.status || {};
  const counts = status.counts || {};
  const intelligence = data.intelligence || {};
  const latestBrief = intelligence.latest_brief || data.overview.latest_brief;
  const anomalies = data.anomalies || [];
  const alertCount = anomalies.filter((item) => Number(item.z_score || 0) >= 3).length;
  const metricData = data.metrics.map((row) => ({ ...row, time: formatTime(row.collected_at) }));
  const scatterData = anomalies.map((row, index) => ({
    ...row,
    timeIndex: index + 1,
    size: Math.max(60, Number(row.metric_value || 1)),
  }));
  const eventBriefs = intelligence.event_briefs || [];

  return (
    <main className="dashboard">
      <header className="hero">
        <div className="hero-copy">
          <div className="brand-pill"><Activity size={13} /> Sonar</div>
          <h1>Hacker News signal radar</h1>
          <p>Live HN signals, anomaly detection and evidence-grounded AI intelligence.</p>
        </div>
        <div className="command-center">
          <div className="command-topline">
            <span>Command center</span>
            <i className={alertCount ? "status-dot warning" : "status-dot"} />
          </div>
          <strong className={alertCount ? "alert-mode" : "stable-mode"}>
            {alertCount ? "Alert mode" : "Monitoring stable"}
          </strong>
          <p>
            {alertCount
              ? `${alertCount} high-confidence signal requires review.`
              : "No high-confidence anomalies in the current window."}
          </p>
          <div className="command-meta">
            <span><b>Mode</b>{data.mode === "live" ? "Live API" : "Demo snapshot"}</span>
            <span><b>Gemini</b>{status.gemini_status || "ready"}</span>
            <span><b>Last scan</b>{formatTime(status.last_collection_time)}</span>
          </div>
        </div>
        <button className="refresh-button" type="button" onClick={() => refresh(true)} disabled={refreshing}>
          <RefreshCw size={14} className={refreshing ? "spin" : ""} />
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </header>

      {(notice || data.mode === "demo") && (
        <div className="demo-banner">
          <Sparkles size={14} />
          {notice || "Portfolio demo mode — the deployed dashboard uses a curated snapshot; local mode connects to FastAPI."}
        </div>
      )}

      <section className="metric-grid">
        <MetricCard label="New stories volume" value={formatNumber(counts.stories || data.stories.length)} note="Current monitored window" />
        <MetricCard label="Hacker News score" value={formatNumber(data.stories.reduce((sum, row) => sum + Number(row.score || 0), 0))} note="Latest observed story scores" />
        <MetricCard label="HN comments" value={formatNumber(data.stories.reduce((sum, row) => sum + Number(row.num_comments || 0), 0))} note="Conversation intensity" />
        <MetricCard label="Active alerts" value={formatNumber(alertCount)} note={`${anomalies.length} signals under triage`} alert={alertCount > 0} />
      </section>

      <section className="chart-trio">
        <Panel title="New stories created over time">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={metricData}>
              <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="monotone" dataKey="story_volume" name="Stories" stroke={COLORS.cyan} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Top feed engagement over time">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={metricData}>
              <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
              <XAxis dataKey="time" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
              <Tooltip content={<ChartTooltip />} />
              <Line type="linear" dataKey="engagement_score" name="Engagement" stroke={COLORS.orange} strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="Anomaly alerts">
          <ResponsiveContainer width="100%" height={250}>
            <ScatterChart margin={{ left: 2, right: 18, top: 8, bottom: 0 }}>
              <CartesianGrid stroke="rgba(112,151,204,.10)" />
              <XAxis type="number" dataKey="timeIndex" name="Signal" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis type="number" dataKey="z_score" name="Z-score" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} width={32} />
              <ZAxis type="number" dataKey="size" range={[55, 190]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<ChartTooltip />} />
              <Scatter data={scatterData}>
                {scatterData.map((item, index) => <Cell key={item.id || index} fill={item.news_aligned ? COLORS.orange : COLORS.cyan} />)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </Panel>
      </section>

      <Panel title="Top feed new entries" className="top-entry-panel">
        <div className="table-intro">
          <span>Strongest new stories in the current observation window</span>
          <small>Ranked by score and conversation velocity</small>
        </div>
        <div className="compact-table">
          {data.stories.slice(0, 5).map((story) => (
            <a href={story.permalink || story.url} target="_blank" rel="noreferrer" key={story.story_id}>
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
                <a href={story.permalink || story.url} target="_blank" rel="noreferrer">{story.title}</a>
                <div className="score-track"><span style={{ width: `${width}%`, opacity: 1 - index * 0.09 }} /></div>
                <b>{formatNumber(story.score)}</b>
              </div>
            );
          })}
        </div>
      </Panel>

      <section className="intelligence-section">
        <SectionHeader eyebrow="AI intelligence" title="Evidence-backed signal briefing" copy="Concise model output, grounded in the stories and external context selected by the monitoring pipeline." />
        <div className="ai-grid">
          <article className="latest-brief">
            <div className="brief-heading">
              <span>Current assessment</span>
              <span className="confidence">{Math.round(Number(latestBrief?.confidence || 0) * 100)}% confidence</span>
            </div>
            <h3>{latestBrief?.headline_summary || "No AI brief generated yet"}</h3>
            <p>{latestBrief?.summary}</p>
            <ul>
              {(latestBrief?.bullet_insights || []).slice(0, 3).map((item: string) => <li key={item}>{item}</li>)}
            </ul>
            <div className="brief-tags">
              <span>{latestBrief?.topic || "Signal intelligence"}</span>
              <span>{latestBrief?.model || "provider ready"}</span>
              <span>{latestBrief?.evidence_count || 0} evidence items</span>
            </div>
          </article>
          <Panel title="Ranked themes" className="theme-panel">
            <ol>
              {(intelligence.ranked_themes || []).slice(0, 6).map((item: Row) => (
                <li key={item.theme}><span>{String(item.rank).padStart(2, "0")}</span><b>{item.theme}</b><i>{item.score}</i></li>
              ))}
            </ol>
          </Panel>
          <Panel title="Heading visibility" className="visibility-panel">
            <ResponsiveContainer width="100%" height={245}>
              <BarChart data={(intelligence.heading_visibility || []).slice(0, 6)} layout="vertical" margin={{ left: 20, right: 18 }}>
                <CartesianGrid stroke="rgba(112,151,204,.10)" horizontal={false} />
                <XAxis type="number" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="keyword" width={80} tick={{ fill: "#a6bad5", fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="visibility" name="Visibility" fill={COLORS.cyan} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Signal sentiment" className="sentiment-panel">
            <ResponsiveContainer width="100%" height={245}>
              <BarChart data={intelligence.sentiment_distribution || []}>
                <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: COLORS.muted, fontSize: 10 }} axisLine={false} tickLine={false} width={25} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Briefs" radius={[3, 3, 0, 0]}>
                  {(intelligence.sentiment_distribution || []).map((item: Row) => (
                    <Cell key={item.label} fill={{ positive: COLORS.green, negative: COLORS.red, neutral: "#7f8da5", mixed: COLORS.orange }[item.label as string] || COLORS.cyan} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Keywords explorer" className="keyword-panel">
            <BubbleField items={intelligence.keyword_bubbles || []} />
          </Panel>
          <Panel title="Notable stories" className="notable-panel">
            <div className="notable-list">
              {(intelligence.notable_stories || []).slice(0, 6).map((story: Row) => (
                <a href={story.permalink || story.url} target="_blank" rel="noreferrer" key={story.story_id}>
                  <span>{story.title}</span>
                  <small>{formatNumber(story.score)} pts · {formatNumber(story.num_comments)} comments</small>
                </a>
              ))}
            </div>
          </Panel>
        </div>
      </section>

      <section className="event-section">
        <SectionHeader eyebrow="Event briefs" title="Investigation queue" copy={`${eventBriefs.length} evidence-grounded cases available for analyst review.`} />
        <div className="brief-accordion">
          {eventBriefs.slice(0, 5).map((brief: Row) => {
            const open = openBrief === brief.id;
            return (
              <article className={open ? "brief-case open" : "brief-case"} key={brief.id}>
                <button type="button" onClick={() => setOpenBrief(open ? null : brief.id)}>
                  <span><i className={brief.news_aligned ? "case-dot aligned" : "case-dot"} />{brief.headline_summary || brief.topic}</span>
                  <small>{brief.event_type?.replaceAll("_", " ")} · z {formatNumber(brief.z_score, 1)}</small>
                  <ChevronDown size={17} />
                </button>
                {open && (
                  <div className="case-body">
                    <div className="case-facts">
                      <span><b>Feed</b>{brief.source_feed}</span>
                      <span><b>Triggered by</b>{brief.triggered_by}</span>
                      <span><b>Evidence</b>{brief.evidence_count || 0} linked records</span>
                      <span><b>News</b>{brief.news_aligned ? "Externally aligned" : "Unconfirmed"}</span>
                    </div>
                    <p>{brief.summary}</p>
                    <div className="case-tags">
                      <span>{brief.topic}</span><span>{brief.sentiment_label}</span><span>{Math.round(Number(brief.confidence || 0) * 100)}% confidence</span>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="story-section">
        <SectionHeader
          eyebrow="Story explorer"
          title="Latest monitored Hacker News stories"
          copy="Filter the current signal set by feed or search across titles."
          action={<span className="verified-badge"><ShieldCheck size={15} /> API-only data boundary</span>}
        />
        <div className="story-panel">
          <div className="story-toolbar">
            <label><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search titles or keywords" /></label>
            <select value={feed} onChange={(event) => setFeed(event.target.value)}>
              <option value="all">All feeds</option>
              <option value="topstories">Top stories</option>
              <option value="newstories">New stories</option>
              <option value="beststories">Best stories</option>
            </select>
            <span>{filteredStories.length} results</span>
          </div>
          <div className="story-table-wrap">
            <table>
              <thead><tr><th>Feed</th><th>Story</th><th>Score</th><th>Comments</th><th>Observed</th><th>Link</th></tr></thead>
              <tbody>
                {filteredStories.slice(0, 12).map((story) => (
                  <tr key={`${story.story_id}-${story.source_feed}`}>
                    <td><span className="feed-chip">{story.source_feed}</span></td>
                    <td>{story.title}</td>
                    <td>{formatNumber(story.score)}</td>
                    <td>{formatNumber(story.num_comments)}</td>
                    <td>{formatTime(story.collected_at)}</td>
                    <td><a href={story.permalink || story.url} target="_blank" rel="noreferrer" aria-label={`Open ${story.title}`}><ExternalLink size={15} /></a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <footer>
        <span><Activity size={14} /> Sonar AI</span>
        <p>Local-first signal intelligence · FastAPI + React + SQLite + Gemini</p>
      </footer>
    </main>
  );
}
