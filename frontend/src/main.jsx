import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Database,
  ExternalLink,
  FileJson,
  Gauge,
  Newspaper,
  RefreshCw,
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
} from "recharts";
import "./styles.css";

const API_BASE = import.meta.env.VITE_SONAR_API_BASE || "http://127.0.0.1:8060";
const POLL_INTERVAL_MS = Number(import.meta.env.VITE_SONAR_POLL_INTERVAL_MS || 60000);
const GRID_COLOR = "rgba(148, 163, 184, 0.12)";
const AXIS_COLOR = "#8aa0bb";
const CYAN = "#46c4f5";
const BLUE = "#2563eb";
const ORANGE = "#fb923c";
const RED = "#fb7185";

async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function apiPost(path) {
  const response = await fetch(`${API_BASE}${path}`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function useApi(path, refreshKey = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    apiGet(path)
      .then((payload) => {
        if (active) setData(payload);
      })
      .catch((err) => {
        if (active) setError(err.message || "Request failed");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, refreshKey]);

  return { data, loading, error };
}

function formatDate(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return numeric.toFixed(digits);
}

function truncateText(value, maxLength = 220) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
}

function compactDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function compactDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function usePagination(items, pageSize) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
  useEffect(() => {
    setPage(1);
  }, [items.length, pageSize]);
  const safePage = Math.min(page, totalPages);
  const start = (safePage - 1) * pageSize;
  return {
    page: safePage,
    totalPages,
    pageItems: items.slice(start, start + pageSize),
    setPage,
  };
}

function statusSignature(status) {
  if (!status) return "";
  return [
    status.last_collection_time,
    status.latest_story_time,
    status.latest_anomaly_time,
    status.latest_brief_time,
  ].join("|");
}

function Shell() {
  const [activeTab, setActiveTab] = useState("overview");
  const [refreshKey, setRefreshKey] = useState(0);
  const [pollStatus, setPollStatus] = useState(null);
  const [pollError, setPollError] = useState("");
  const [lastAutoRefreshAt, setLastAutoRefreshAt] = useState("");

  useEffect(() => {
    let active = true;
    let previousSignature = "";

    async function pollStatusEndpoint() {
      try {
        const payload = await apiGet("/api/status");
        if (!active) return;
        setPollStatus(payload);
        setPollError("");
        const nextSignature = statusSignature(payload);
        if (previousSignature && nextSignature && nextSignature !== previousSignature) {
          setRefreshKey((key) => key + 1);
          setLastAutoRefreshAt(new Date().toISOString());
        }
        previousSignature = nextSignature;
      } catch (err) {
        if (active) setPollError(err.message || "Polling failed");
      }
    }

    pollStatusEndpoint();
    const timer = window.setInterval(pollStatusEndpoint, POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const tabs = [
    { id: "overview", label: "Overview", icon: Gauge },
    { id: "stories", label: "Stories", icon: Newspaper },
    { id: "anomalies", label: "Anomalies", icon: AlertTriangle },
    { id: "system", label: "System", icon: Server },
  ];

  const ActivePage = {
    overview: Overview,
    stories: Stories,
    anomalies: Anomalies,
    system: System,
  }[activeTab];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <Activity size={22} />
          </div>
          <div>
            <h1>Sonar AI</h1>
            <p>Signal intelligence platform</p>
          </div>
        </div>
        <nav className="nav-list">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                className={activeTab === tab.id ? "nav-item active" : "nav-item"}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <span>API</span>
          <code>{API_BASE}</code>
        </div>
      </aside>

      <main className="content">
        <header className="content-header">
          <div>
            <p className="eyebrow">Full-stack monitoring interface</p>
            <h2>{tabs.find((tab) => tab.id === activeTab)?.label}</h2>
            <div className="poll-status">
              <Wifi size={14} />
              <span>{pollError ? "Polling issue" : `Polling every ${POLL_INTERVAL_MS / 1000}s`}</span>
              <span>Last collection {formatDate(pollStatus?.last_collection_time)}</span>
              {lastAutoRefreshAt && <span>Auto refreshed {compactDate(lastAutoRefreshAt)}</span>}
            </div>
          </div>
          <button className="icon-button" type="button" onClick={() => setRefreshKey((key) => key + 1)}>
            <RefreshCw size={17} />
            <span>Refresh</span>
          </button>
        </header>
        <ActivePage refreshKey={refreshKey} />
      </main>
    </div>
  );
}

function StateBlock({ loading, error, empty, children }) {
  if (loading) return <div className="state-block">Loading data...</div>;
  if (error) return <div className="state-block error">API request failed: {error}</div>;
  if (empty) return <div className="state-block">No data available yet. Run the collector to populate Sonar.</div>;
  return children;
}

function Overview({ refreshKey }) {
  const overview = useApi("/api/dashboard/overview", refreshKey);
  const metrics = useApi("/api/metrics/timeline?limit=160", refreshKey);
  const intelligence = useApi("/api/ai/intelligence", refreshKey);
  const data = overview.data;
  const status = data?.status || {};
  const counts = status?.counts || {};
  const timeline = useMemo(
    () => (metrics.data?.timeline || []).map((row) => ({ ...row, time: compactDate(row.collected_at) })),
    [metrics.data],
  );
  const anomalyPoints = useMemo(
    () => {
      const seen = new Map();
      return (data?.latest_anomalies || []).map((row) => {
        const base = new Date(row.detected_at).getTime();
        const count = seen.get(base) || 0;
        seen.set(base, count + 1);
        return {
          ...row,
          timestamp: Number.isNaN(base) ? count : base + count * 45000,
          display_time: compactDateTime(row.detected_at),
          z_score_abs: Math.abs(Number(row.z_score || 0)),
        };
      });
    },
    [data],
  );
  const topStories = data?.top_stories || [];
  const latestBrief = data?.latest_brief;
  const latestAnomaly = data?.latest_anomalies?.[0];

  return (
    <StateBlock loading={overview.loading || metrics.loading} error={overview.error || metrics.error} empty={false}>
      <CommandCenter status={status} latestBrief={latestBrief} latestAnomaly={latestAnomaly} />

      <section className="metric-grid">
        <Metric icon={Newspaper} label="Stories" value={counts.stories ?? 0} />
        <Metric icon={AlertTriangle} label="Anomalies" value={counts.anomalies ?? 0} tone="warning" />
        <Metric icon={Bot} label="AI Briefs" value={counts.briefs ?? 0} tone="accent" />
        <Metric icon={Database} label="Evidence Docs" value={counts.documents ?? 0} />
      </section>

      <section className="chart-grid">
        <ChartPanel title="New stories over time">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="time" tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: AXIS_COLOR }} allowDecimals={false} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8 }} />
              <Line type="monotone" dataKey="story_volume" name="Stories" stroke={CYAN} strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Engagement score over time">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="time" tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8 }} />
              <Line type="monotone" dataKey="engagement_score" name="Engagement" stroke={ORANGE} strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="avg_comments" name="Avg comments" stroke={CYAN} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Anomaly alerts">
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis
                dataKey="timestamp"
                name="Time"
                type="number"
                domain={["dataMin", "dataMax"]}
                tick={{ fontSize: 11, fill: AXIS_COLOR }}
                tickFormatter={(value) => compactDateTime(value)}
                axisLine={{ stroke: GRID_COLOR }}
                tickLine={false}
              />
              <YAxis dataKey="z_score_abs" name="Z-score" tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<AnomalyTooltip />} />
              <Scatter data={anomalyPoints} fill={RED}>
                {anomalyPoints.map((point) => (
                  <Cell key={point.id} fill={point.news_aligned ? CYAN : ORANGE} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </ChartPanel>

        <TopStoriesScorePanel stories={topStories} />
      </section>

      <TopMovers stories={topStories} />

      <AIIntelligenceSection data={intelligence.data} loading={intelligence.loading} error={intelligence.error} />

      <section className="panel-grid dashboard-lower">
        <FeedSummary feeds={data?.feed_summary || []} />
      </section>
    </StateBlock>
  );
}

function CommandCenter({ status, latestBrief, latestAnomaly }) {
  const hasAlert = Boolean(latestAnomaly);
  return (
    <section className="command-center">
      <div>
        <span className="mini-badge">SONAR</span>
        <h1>Hacker News signal radar</h1>
        <p>Live HN signals and AI intent monitoring.</p>
      </div>
      <div className="command-card">
        <span>Command Center</span>
        <strong>{hasAlert ? "ALERT MODE" : "MONITORING"}</strong>
        <p>{hasAlert ? "Recent anomaly detected in the monitoring window." : "No recent anomaly selected."}</p>
        <div className="command-stats">
          <div>
            <b>{latestAnomaly ? formatNumber(latestAnomaly.z_score, 2) : "-"}</b>
            <small>z-score</small>
          </div>
          <div>
            <b>{latestAnomaly?.metric_name?.replaceAll("_", " ") || "none"}</b>
            <small>trigger</small>
          </div>
          <div>
            <b>{status?.gemini?.value || latestBrief?.ai_status || "unknown"}</b>
            <small>AI status</small>
          </div>
        </div>
      </div>
    </section>
  );
}

function TopMovers({ stories }) {
  return (
    <section className="panel top-movers-panel">
      <div className="panel-toolbar">
        <h3>Top movers by current score</h3>
        <span className="status-pill">{stories.length} stories</span>
      </div>
      {stories.length === 0 ? (
        <p className="body-copy">No current story rows available.</p>
      ) : (
        <div className="top-mover-list">
          {stories.slice(0, 6).map((story) => (
            <a className="top-mover-row" href={story.permalink || story.url} target="_blank" rel="noreferrer" key={`${story.story_id}-${story.source_feed}`}>
              <span>{story.title}</span>
              <strong>{story.score}</strong>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

function FeedSummary({ feeds }) {
  return (
    <div className="panel feed-summary-panel">
      <h3>Feed summary</h3>
      <div className="feed-summary-list">
        {feeds.slice(0, 3).map((feed) => (
          <div key={feed.source_feed}>
            <span className="chip">{feed.source_feed}</span>
            <strong>{feed.story_count}</strong>
            <small>{feed.total_score} score · {feed.total_comments} comments</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChartPanel({ title, children, className = "" }) {
  return (
    <div className={`panel chart-panel ${className}`.trim()}>
      <h3>{title}</h3>
      {children}
    </div>
  );
}

function AnomalyTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <strong>{point.metric_name?.replaceAll("_", " ")}</strong>
      <span>{point.source_feed}</span>
      <span>z-score {formatNumber(point.z_score, 2)}</span>
      <span>{point.display_time}</span>
      <span>{point.news_aligned ? "news aligned" : "unconfirmed"}</span>
    </div>
  );
}

function TopStoriesScorePanel({ stories }) {
  const maxScore = Math.max(...stories.map((story) => Number(story.score || 0)), 1);
  return (
    <div className="panel chart-panel top-score-panel">
      <h3>Top stories by score</h3>
      <div className="score-bar-list">
        {stories.slice(0, 7).map((story) => (
          <div className="score-bar-row" key={`${story.story_id}-${story.source_feed}`}>
            <a href={story.permalink || story.url} target="_blank" rel="noreferrer">
              {story.title}
            </a>
            <div className="score-track">
              <span style={{ width: `${Math.max(8, (Number(story.score || 0) / maxScore) * 100)}%` }} />
            </div>
            <strong>{story.score}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function LatestBriefPanel({ brief }) {
  const bullets = (brief?.bullet_insights || []).filter(Boolean).slice(0, 3);
  return (
    <div className="panel ai-briefing-panel">
      <div className="panel-toolbar">
        <h3>AI insight briefing</h3>
        <span className="status-pill">{brief?.ai_status || "no brief"}</span>
      </div>
      {!brief ? (
        <p className="body-copy">No AI brief has been generated yet.</p>
      ) : (
        <div className="brief-summary">
          <h4>{brief.headline_summary || brief.topic || "Latest brief"}</h4>
          <div className="meta-row">
            <span>{brief.topic || brief.metric_name}</span>
            <span>confidence {formatNumber(brief.confidence, 2)}</span>
            <span>{brief.evidence_count} evidence</span>
            <span>{brief.model || brief.provider || "provider unavailable"}</span>
          </div>
          {bullets.length > 0 ? (
            <ul className="insight-list">
              {bullets.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="body-copy">{brief.summary || "No summary stored."}</p>
          )}
          {brief.summary && bullets.length > 0 && (
            <details className="summary-details">
              <summary>Summary</summary>
              <p className="body-copy">{brief.summary}</p>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value, tone = "default" }) {
  return (
    <div className={`metric-card ${tone}`}>
      <div className="metric-icon">
        <Icon size={18} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Stories({ refreshKey }) {
  const [feed, setFeed] = useState("");
  const path = useMemo(() => `/api/stories?limit=60${feed ? `&feed=${encodeURIComponent(feed)}` : ""}`, [feed]);
  const { data, loading, error } = useApi(path, refreshKey);
  const stories = data?.stories || [];
  const pagination = usePagination(stories, 12);

  return (
    <section className="panel">
      <div className="panel-toolbar">
        <div>
          <h3>Story explorer</h3>
          <p className="section-note">Showing 12 per page from the latest 60 rows.</p>
        </div>
        <div className="toolbar-controls">
          <select value={feed} onChange={(event) => setFeed(event.target.value)}>
            <option value="">All feeds</option>
            <option value="topstories">topstories</option>
            <option value="newstories">newstories</option>
            <option value="beststories">beststories</option>
          </select>
          <PaginationControls {...pagination} />
        </div>
      </div>
      <StateBlock loading={loading} error={error} empty={stories.length === 0}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Feed</th>
                <th>Score</th>
                <th>Comments</th>
                <th>Collected</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {pagination.pageItems.map((story) => (
                <tr key={`${story.story_id}-${story.source_feed}-${story.collected_at}`}>
                  <td>{story.title}</td>
                  <td><span className="chip">{story.source_feed}</span></td>
                  <td>{story.score}</td>
                  <td>{story.num_comments}</td>
                  <td>{formatDate(story.collected_at)}</td>
                  <td>
                    <a href={story.permalink || story.url} target="_blank" rel="noreferrer">
                      <ExternalLink size={15} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </StateBlock>
    </section>
  );
}

function Anomalies({ refreshKey }) {
  const { data, loading, error } = useApi("/api/anomalies?limit=40", refreshKey);
  const anomalies = data?.anomalies || [];
  const pagination = usePagination(anomalies, 8);

  return (
    <section className="panel">
      <div className="panel-toolbar">
        <div>
          <h3>Anomaly triage</h3>
          <p className="section-note">Showing 8 per page from the latest 40 anomalies.</p>
        </div>
        <PaginationControls {...pagination} />
      </div>
      <StateBlock loading={loading} error={error} empty={anomalies.length === 0}>
        <div className="timeline-list">
          {pagination.pageItems.map((item) => (
            <article className="timeline-item" key={item.id}>
              <div className="timeline-dot" />
              <div>
                <div className="row-title">
                  <strong>{item.metric_name.replaceAll("_", " ")}</strong>
                  <span className={item.news_aligned ? "status-pill aligned" : "status-pill"}>{item.news_aligned ? "news aligned" : "unconfirmed"}</span>
                </div>
                <p>{item.source_feed} triggered by {item.triggered_by}</p>
                <div className="meta-row">
                  <span>z-score {formatNumber(item.z_score, 2)}</span>
                  <span>{item.explanation_status}</span>
                  <span>{formatDate(item.detected_at)}</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </StateBlock>
    </section>
  );
}

function PaginationControls({ page, totalPages, setPage }) {
  return (
    <div className="pagination-controls">
      <button type="button" onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1}>Prev</button>
      <span>{page} / {totalPages}</span>
      <button type="button" onClick={() => setPage(Math.min(totalPages, page + 1))} disabled={page >= totalPages}>Next</button>
    </div>
  );
}

function Briefs({ refreshKey }) {
  const { data, loading, error } = useApi("/api/ai/intelligence", refreshKey);
  return <AIIntelligenceSection data={data} loading={loading} error={error} />;
}

function AIIntelligenceSection({ data, loading, error }) {
  const [openBriefId, setOpenBriefId] = useState(null);
  const [selectedKeyword, setSelectedKeyword] = useState(null);
  const eventBriefs = data?.event_briefs || [];
  const keywordBubbles = data?.keyword_bubbles || [];

  useEffect(() => {
    if (!selectedKeyword) return;
    if (!keywordBubbles.some((item) => item.keyword === selectedKeyword)) {
      setSelectedKeyword(null);
    }
  }, [keywordBubbles, selectedKeyword]);

  const selectedKeywordItem = keywordBubbles.find((item) => item.keyword === selectedKeyword) || null;

  return (
    <StateBlock loading={loading} error={error} empty={eventBriefs.length === 0}>
      <section className="ai-dashboard dash-parity-section">
        <LatestBriefPanel brief={data?.latest_brief} />
        <div className="panel ranked-theme-panel">
          <h3>Ranked themes</h3>
          <div className="theme-list">
            {(data?.ranked_themes || []).slice(0, 6).map((item) => (
              <div className="theme-row" key={item.theme}>
                <span>{item.rank}</span>
                <strong>{item.theme}</strong>
              </div>
            ))}
          </div>
        </div>
        <ChartPanel title="Heading visibility" className="heading-visibility-panel">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data?.heading_visibility || []} layout="vertical" margin={{ left: 12, right: 18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis type="number" tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <YAxis type="category" dataKey="keyword" width={90} tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8 }} />
              <Bar dataKey="visibility" name="Visibility" fill={CYAN} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Signal sentiment" className="sentiment-panel">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data?.sentiment_distribution || []}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS_COLOR }} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: AXIS_COLOR }} allowDecimals={false} axisLine={{ stroke: GRID_COLOR }} tickLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8 }} />
              <Bar dataKey="count" name="Briefs" radius={[4, 4, 0, 0]}>
                {(data?.sentiment_distribution || []).map((item) => (
                  <Cell key={item.label} fill={{ positive: "#34d399", negative: RED, neutral: "#94a3b8", mixed: ORANGE }[item.label] || CYAN} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
        <KeywordBubbleCloud items={keywordBubbles.slice(0, 12)} selectedKeyword={selectedKeyword} onSelectKeyword={setSelectedKeyword} />
        <NotableStories stories={data?.notable_stories || []} selectedKeywordItem={selectedKeywordItem} />
        <EventBriefs briefs={eventBriefs} openBriefId={openBriefId} setOpenBriefId={setOpenBriefId} />
      </section>
    </StateBlock>
  );
}

function KeywordBubbleCloud({ items, selectedKeyword, onSelectKeyword }) {
  const slots = [
    [50, 50], [28, 42], [72, 42], [36, 68], [67, 68], [20, 58], [82, 58],
    [50, 24], [50, 78], [30, 24], [72, 24], [18, 78],
  ];
  const maxWeight = Math.max(...items.map((item) => item.weight), 1);
  return (
    <div className="panel keyword-panel">
      <div className="panel-toolbar">
        <div>
          <h3>Keyword explorer</h3>
          <p className="section-note">Click a bubble to inspect related stories.</p>
        </div>
        <span className="status-pill">{items.length} signals</span>
      </div>
      <svg className="bubble-cloud" viewBox="0 0 100 100" role="img" aria-label="Keyword bubble cloud">
        {items.slice(0, slots.length).map((item, index) => {
          const [cx, cy] = slots[index];
          const isSelected = selectedKeyword === item.keyword;
          const radius = 5.5 + (item.weight / maxWeight) * 10;
          return (
            <g
              key={item.keyword}
              className={isSelected ? "bubble-group selected" : "bubble-group"}
              onClick={() => onSelectKeyword(isSelected ? null : item.keyword)}
              role="button"
              tabIndex="0"
              aria-label={`Show stories related to ${item.keyword}`}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectKeyword(isSelected ? null : item.keyword);
                }
              }}
            >
              <circle cx={cx} cy={cy} r={radius} className={index === 0 ? "bubble primary" : "bubble"} />
              <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle" className="bubble-label">
                {item.keyword}
              </text>
              <text x={cx} y={cy + radius + 3.6} textAnchor="middle" dominantBaseline="middle" className="bubble-count">
                {item.story_count || 0} stories
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function NotableStories({ stories, selectedKeywordItem }) {
  const relatedStories = selectedKeywordItem?.stories || [];
  const displayStories = selectedKeywordItem ? relatedStories : stories;
  return (
    <div className="panel notable-panel">
      <div className="panel-toolbar">
        <div>
          <h3>{selectedKeywordItem ? "Related stories" : "Notable stories"}</h3>
          <p className="section-note">
            {selectedKeywordItem
              ? `Matched to ${selectedKeywordItem.keyword}. Click the same bubble to reset.`
              : "Highest signal stories in the current window."}
          </p>
        </div>
        <span className="status-pill">{displayStories.length} rows</span>
      </div>
      <div className="compact-story-list">
        {displayStories.slice(0, 8).map((story) => (
          <a href={story.permalink || story.url} target="_blank" rel="noreferrer" key={`${story.story_id}-${story.source_feed}`}>
            <span>{story.title}</span>
            <small>{story.score} pts · {story.num_comments} comments</small>
          </a>
        ))}
        {displayStories.length === 0 && <p className="body-copy">No matched stories in this window.</p>}
      </div>
    </div>
  );
}

function EventBriefs({ briefs, openBriefId, setOpenBriefId }) {
  return (
    <div className="panel event-brief-panel">
      <div className="panel-toolbar">
        <h3>Event briefs</h3>
        <span className="status-pill">{briefs.length} investigations</span>
      </div>
      <div className="event-brief-list">
        {briefs.slice(0, 5).map((brief) => {
          const isOpen = openBriefId === brief.id;
          return (
            <article className="event-brief" key={brief.id}>
              <button type="button" className="event-brief-header" onClick={() => setOpenBriefId(isOpen ? null : brief.id)}>
                <span>{brief.headline_summary || brief.topic || brief.metric_name}</span>
                <strong>{isOpen ? "Close" : "Open"}</strong>
              </button>
              {isOpen && (
                <div className="event-brief-body">
                  <div className="meta-row">
                    <span className="chip">Event Type: {brief.event_type || "signal change"}</span>
                    <span className="chip">Confidence: {formatNumber(brief.confidence, 2)}</span>
                    <span className={brief.news_aligned ? "status-pill aligned" : "status-pill"}>{brief.news_aligned ? "News aligned" : "News aligned: no"}</span>
                    <span className="chip">Triggered by: {brief.triggered_by}</span>
                  </div>
                  <p className="body-copy">{truncateText(brief.summary || "No summary stored.", 260)}</p>
                  {(brief.bullet_insights || []).length > 0 && (
                    <ul className="insight-list">
                      {brief.bullet_insights.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function BriefDetail({ payload }) {
  const response = payload?.brief?.response || {};
  const evidence = payload?.evidence || [];
  return (
    <div className="brief-detail">
      <p className="body-copy">{response.summary || "No summary stored."}</p>
      <h4>Evidence</h4>
      {evidence.length === 0 ? (
        <p className="body-copy">No evidence rows stored for this brief.</p>
      ) : (
        <ul className="evidence-list">
          {evidence.map((item) => (
            <li key={item.id}>
              <span className="chip">{item.source}</span>
              <a href={item.url || "#"} target="_blank" rel="noreferrer">{item.title}</a>
              <small>{item.reason_used}</small>
            </li>
          ))}
        </ul>
      )}
      <h4>AI run</h4>
      <dl className="detail-list compact">
        <div>
          <dt>Provider</dt>
          <dd>{payload?.ai_run?.provider || "not recorded"}</dd>
        </div>
        <div>
          <dt>Model</dt>
          <dd>{payload?.ai_run?.model || "not recorded"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{payload?.ai_run?.status || "not recorded"}</dd>
        </div>
      </dl>
      <details>
        <summary><FileJson size={16} /> Raw JSON</summary>
        <pre>{JSON.stringify(payload, null, 2)}</pre>
      </details>
    </div>
  );
}

function System({ refreshKey }) {
  const { data, loading, error } = useApi("/api/status", refreshKey);
  const [running, setRunning] = useState(false);
  const [runMessage, setRunMessage] = useState("");

  async function runOnce() {
    setRunning(true);
    setRunMessage("");
    try {
      await apiPost("/api/run-once");
      setRunMessage("Collector cycle completed.");
    } catch (err) {
      setRunMessage(`Collector failed: ${err.message || "unknown error"}`);
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="panel-grid">
      <div className="panel">
        <h3>Services</h3>
        <StateBlock loading={loading} error={error} empty={false}>
          <dl className="detail-list">
            <div>
              <dt>FastAPI</dt>
              <dd>{API_BASE}</dd>
            </div>
            <div>
              <dt>Dash analyst workbench</dt>
              <dd>http://127.0.0.1:8050</dd>
            </div>
            <div>
              <dt>Stories</dt>
              <dd>{data?.counts?.stories ?? 0}</dd>
            </div>
            <div>
              <dt>AI runs</dt>
              <dd>{data?.counts?.ai_runs ?? 0}</dd>
            </div>
          </dl>
        </StateBlock>
      </div>
      <div className="panel">
        <h3>Manual collector run</h3>
        <p className="body-copy">
          Use this for local demos. The API and scheduled worker share the same collection cycle.
        </p>
        <button type="button" className="primary-button" onClick={runOnce} disabled={running}>
          <RefreshCw size={17} />
          <span>{running ? "Running..." : "Run once"}</span>
        </button>
        {runMessage && <p className="run-message">{runMessage}</p>}
      </div>
      <div className="panel wide">
        <h3>Architecture notes</h3>
        <p className="body-copy">
          The product UI proves the full-stack boundary. Dash remains useful for analysts because it
          exposes deeper Plotly diagnostics and operational monitoring than the product interface.
        </p>
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Shell />
  </React.StrictMode>
);
