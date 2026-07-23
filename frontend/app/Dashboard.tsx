"use client";

import { useEffect, useMemo, useState } from "react";
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

const demoTimestamp = (hoursAgo: number) => new Date(Date.now() - hoursAgo * 60 * 60 * 1000).toISOString();

const demoStories = [
  { story_id: 47687273, source_feed: "topstories", title: "Git commands I run before reading any code", score: 2278, num_comments: 494, collected_at: demoTimestamp(1), permalink: "https://news.ycombinator.com/item?id=47687273", url: "https://piechowski.io/post/git-commands-before-reading-code/" },
  { story_id: 47659135, source_feed: "topstories", title: "Sam Altman may control our future – can he be trusted?", score: 2172, num_comments: 904, collected_at: demoTimestamp(2), permalink: "https://news.ycombinator.com/item?id=47659135", url: "https://www.newyorker.com/magazine/2026/04/13/sam-altman-may-control-our-future-can-he-be-trusted" },
  { story_id: 47691730, source_feed: "topstories", title: "I ported Mac OS X to the Nintendo Wii", score: 1901, num_comments: 323, collected_at: demoTimestamp(3), permalink: "https://news.ycombinator.com/item?id=47691730", url: "https://bryankeller.github.io/2026/04/08/porting-mac-os-x-nintendo-wii.html" },
  { story_id: 48311647, source_feed: "topstories", title: "Claude Opus 4.8", score: 1736, num_comments: 1351, collected_at: demoTimestamp(4), permalink: "https://news.ycombinator.com/item?id=48311647", url: "https://www.anthropic.com/news/claude-opus-4-8" },
  { story_id: 47706268, source_feed: "topstories", title: "EFF is leaving X", score: 1401, num_comments: 1274, collected_at: demoTimestamp(6), permalink: "https://news.ycombinator.com/item?id=47706268", url: "https://www.eff.org/deeplinks/2026/04/eff-leaving-x" },
  { story_id: 47697870, source_feed: "newstories", title: "LittleSnitch for Linux", score: 1352, num_comments: 452, collected_at: demoTimestamp(8), permalink: "https://news.ycombinator.com/item?id=47697870", url: "https://obdev.at/products/littlesnitch-linux/index.html" },
  { story_id: 48314136, source_feed: "topstories", title: "Bricks and Minifigs Stole a Man's $200k Lego Collection", score: 1309, num_comments: 589, collected_at: demoTimestamp(12), permalink: "https://news.ycombinator.com/item?id=48314136", url: "https://mybricklog.com/blog/bricks-minifigs-corporate-stole-old-mans-200000-lego-collection" },
  { story_id: 48299753, source_feed: "topstories", title: "YouTube to automatically label AI-generated videos", score: 1308, num_comments: 818, collected_at: demoTimestamp(18), permalink: "https://news.ycombinator.com/item?id=48299753", url: "https://blog.youtube/news-and-events/improving-ai-labels-viewers-creators/" },
  { story_id: 48324712, source_feed: "newstories", title: "The dead economy theory", score: 1049, num_comments: 1185, collected_at: demoTimestamp(23), permalink: "https://news.ycombinator.com/item?id=48324712", url: "https://www.owenmcgrann.com/p/the-dead-economy-theory" },
  { story_id: 47725583, source_feed: "topstories", title: "Artemis II safely splashes down", score: 900, num_comments: 280, collected_at: demoTimestamp(28), permalink: "https://news.ycombinator.com/item?id=47725583", url: "https://www.cbsnews.com/live-updates/artemis-ii-splashdown-return/" },
  { story_id: 47719740, source_feed: "newstories", title: "1D Chess", score: 819, num_comments: 142, collected_at: demoTimestamp(36), permalink: "https://news.ycombinator.com/item?id=47719740", url: "https://rowan441.github.io/1dchess/chess.html" },
  { story_id: 47724352, source_feed: "topstories", title: "Filing the corners off my MacBooks", score: 816, num_comments: 403, collected_at: demoTimestamp(48), permalink: "https://news.ycombinator.com/item?id=47724352", url: "https://kentwalters.com/posts/corners/" },
  { story_id: 48323683, source_feed: "newstories", title: "I am retiring from tech to live offline", score: 800, num_comments: 548, collected_at: demoTimestamp(60), permalink: "https://news.ycombinator.com/item?id=48323683", url: "https://openpath.quest/2026/i-am-retiring-from-tech-to-live-offline/" },
  { story_id: 48324499, source_feed: "topstories", title: "GTA 6 Developers Unionize", score: 689, num_comments: 468, collected_at: demoTimestamp(72), permalink: "https://news.ycombinator.com/item?id=48324499", url: "https://rockstarintel.com/gta-6-developers-announce-rockstar-games-union/" },
  { story_id: 47708818, source_feed: "newstories", title: "Native Instant Space Switching on macOS", score: 625, num_comments: 310, collected_at: demoTimestamp(84), permalink: "https://news.ycombinator.com/item?id=47708818", url: "https://arhan.sh/blog/native-instant-space-switching-on-macos/" },
  { story_id: 47703419, source_feed: "topstories", title: "Meta removes ads for social media addiction litigation", score: 624, num_comments: 248, collected_at: demoTimestamp(96), permalink: "https://news.ycombinator.com/item?id=47703419", url: "https://www.axios.com/2026/04/09/meta-social-media-addiction-ads" },
  { story_id: 47704804, source_feed: "newstories", title: "How NASA built Artemis II’s fault-tolerant computer", score: 613, num_comments: 222, collected_at: demoTimestamp(108), permalink: "https://news.ycombinator.com/item?id=47704804", url: "https://cacm.acm.org/news/how-nasa-built-artemis-iis-fault-tolerant-computer/" },
  { story_id: 48309233, source_feed: "topstories", title: "UC faculty demand a return to SAT tests for STEM", score: 603, num_comments: 801, collected_at: demoTimestamp(120), permalink: "https://news.ycombinator.com/item?id=48309233", url: "https://www.latimes.com/california/story/2026-05-27/uc-math-professors-demand-return-of-sat-for-stem-admissions" },
  { story_id: 47716490, source_feed: "newstories", title: "FBI used iPhone notification data to retrieve deleted Signal messages", score: 588, num_comments: 290, collected_at: demoTimestamp(132), permalink: "https://news.ycombinator.com/item?id=47716490", url: "https://9to5mac.com/2026/04/09/fbi-used-iphone-notification-data-to-retrieve-deleted-signal-messages/" },
  { story_id: 48326802, source_feed: "topstories", title: "SQLite is all you need for durable workflows", score: 568, num_comments: 285, collected_at: demoTimestamp(144), permalink: "https://news.ycombinator.com/item?id=48326802", url: "https://obeli.sk/blog/sqlite-is-all-you-need-for-durable-workflows/" },
  { story_id: 48315968, source_feed: "newstories", title: "GitHub bans security researcher who posted zero-day Windows exploits", score: 541, num_comments: 251, collected_at: demoTimestamp(156), permalink: "https://news.ycombinator.com/item?id=48315968", url: "https://www.tomshardware.com/tech-industry/cyber-security/microsofts-github-bans-security-researcher-who-posted-zero-day-windows-exploits-because-company-ruined-their-life-expert-claims-action-is-vindictive-and-promises-further-retaliation" },
  { story_id: 47719486, source_feed: "topstories", title: "France to ditch Windows for Linux to reduce reliance on US tech", score: 508, num_comments: 637, collected_at: demoTimestamp(168), permalink: "https://news.ycombinator.com/item?id=47719486", url: "https://techcrunch.com/2026/04/10/france-to-ditch-windows-for-linux-to-reduce-reliance-on-us-tech/" },
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
    model: "gemini-3.5-flash-lite",
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
    model: "gemini-3.5-flash-lite",
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
    model: "gemini-3.5-flash-lite",
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
        { keyword: "AI", raw_keyword: "ai", weight: 100, story_count: 5, stories: [demoStories[1], demoStories[3], demoStories[7], demoStories[15], demoStories[20]] },
        { keyword: "Security", raw_keyword: "security", weight: 58, story_count: 5, stories: [demoStories[4], demoStories[5], demoStories[18], demoStories[20], demoStories[21]] },
        { keyword: "Programming", raw_keyword: "programming", weight: 52, story_count: 5, stories: [demoStories[0], demoStories[2], demoStories[10], demoStories[14], demoStories[19]] },
        { keyword: "Open Source", raw_keyword: "open source", weight: 46, story_count: 4, stories: [demoStories[5], demoStories[19], demoStories[20], demoStories[21]] },
        { keyword: "Developer Tools", raw_keyword: "developer tools", weight: 41, story_count: 5, stories: [demoStories[0], demoStories[2], demoStories[5], demoStories[14], demoStories[19]] },
        { keyword: "Data", raw_keyword: "data", weight: 35, story_count: 4, stories: [demoStories[7], demoStories[18], demoStories[19], demoStories[20]] },
        { keyword: "Space", raw_keyword: "space", weight: 26, story_count: 3, stories: [demoStories[9], demoStories[14], demoStories[16]] },
      ],
      notable_stories: demoStories.slice(0, 8),
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

function formatDateTime(value: unknown) {
  const date = new Date(String(value || ""));
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
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

function BubbleField({
  items,
  selectedKeyword,
  onSelectKeyword,
}: {
  items: Row[];
  selectedKeyword: string | null;
  onSelectKeyword: (keyword: string | null) => void;
}) {
  const slots = [[50, 48], [23, 42], [78, 42], [30, 72], [69, 72], [15, 70], [85, 72]];
  const max = Math.max(...items.map((item) => Number(item.weight || 1)), 1);
  return (
    <div className="bubble-field" aria-label="Keyword explorer">
      {items.slice(0, slots.length).map((item, index) => {
        const size = 48 + (Number(item.weight || 1) / max) * 78;
        const isSelected = selectedKeyword === item.keyword;
        return (
          <button
            type="button"
            className={`bubble-node${index === 0 ? " primary" : ""}${isSelected ? " selected" : ""}`}
            key={item.keyword}
            style={{ left: `${slots[index][0]}%`, top: `${slots[index][1]}%`, width: size, height: size }}
            aria-label={`Filter notable stories by ${item.keyword}`}
            aria-pressed={isSelected}
            onClick={() => onSelectKeyword(isSelected ? null : item.keyword)}
          >
            <span>{item.keyword}</span>
            <small>{item.story_count || 0}</small>
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
  const [activeView, setActiveView] = useState<"overview" | "intelligence" | "investigations">("overview");
  const [search, setSearch] = useState("");
  const [feed, setFeed] = useState("all");
  const [timeWindow, setTimeWindow] = useState("current");
  const [rankBy, setRankBy] = useState("score");
  const [flagFilter, setFlagFilter] = useState("all");
  const [storyPage, setStoryPage] = useState(1);
  const [openBrief, setOpenBrief] = useState<number | string | null>(1);
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
  const counts = status.counts || {};
  const intelligence = data.intelligence || {};
  const latestBrief = intelligence.latest_brief || data.overview.latest_brief;
  const anomalies = data.anomalies || [];
  const alertCount = anomalies.filter((item) => Number(item.z_score || 0) >= 3).length;
  const metricData = data.metrics.map((row) => ({ ...row, time: formatTime(row.collected_at) }));
  const scatterData = anomalies.map((row, index) => ({
    ...row,
    timeIndex: index + 1,
    volume: Math.max(0.1, Number(row.metric_value || index + 1)),
    velocity: Math.max(0.1, Number(row.z_score || 0)),
    size: Math.max(60, Number(row.metric_value || 1)),
  }));
  const eventBriefs = intelligence.event_briefs || [];
  const selectedBrief = eventBriefs.find((brief: Row) => brief.id === openBrief) || eventBriefs[0] || {};
  const totalScore = data.stories.reduce((sum, row) => sum + Number(row.score || 0), 0);
  const totalComments = data.stories.reduce((sum, row) => sum + Number(row.num_comments || 0), 0);
  const emergingTopics = (intelligence.ranked_themes || []).slice(0, 5);
  const maxTopicScore = Math.max(...emergingTopics.map((item: Row) => Number(item.score || 0)), 1);
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
  const selectedKeywordItem = (intelligence.keyword_bubbles || []).find(
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
  const statusRows = [
    { icon: Wifi, label: "Data stream", detail: data.mode === "live" ? "Healthy" : "Demo snapshot", value: data.mode === "live" ? "Live" : "Ready" },
    { icon: Radio, label: "Coverage", detail: "Hacker News feeds", value: `${data.overview.feed_summary?.length || 2} feeds` },
    { icon: Database, label: "Signals analyzed", detail: "Current dataset", value: formatNumber(counts.stories || data.stories.length) },
    { icon: RefreshCw, label: "Refresh rate", detail: "Status-aware polling", value: "60 sec" },
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
            {refreshing ? "Refreshing" : "Refresh"}
          </button>
        </div>
        <div className="hero-copy">
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
      </header>

      {(notice || data.mode === "demo") && (
        <div className="demo-banner">
          <Sparkles size={14} />
          {notice || "Hosted demo mode — the deployed dashboard uses a curated snapshot; local mode connects to FastAPI."}
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
                    <XAxis dataKey="time" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
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
                    <strong>{metricData[selectedWindowIndex]?.time || "Selected window"} · {selectedWindowStories.length} related stories</strong>
                    {selectedWindowStories.map((story) => (
                      <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                        <span>{story.title}</span>
                        <small>{formatNumber(story.score)} pts</small>
                      </a>
                    ))}
                  </div>
                )}
            </Panel>

            <Panel title="Live status" className="operations-status-panel">
              <div className={alertCount ? "operations-alert active" : "operations-alert"}>
                <AlertTriangle size={18} />
                <span><b>{alertCount ? "Anomaly detected" : "Monitoring stable"}</b><small>{alertCount ? "High-confidence signal requires review" : "All monitored feeds are within range"}</small></span>
                <em>{alertCount ? "Now" : "Healthy"}</em>
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
              </div>
            </Panel>

            <Panel title="Signal velocity" className="velocity-panel">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ left: 2, right: 20, top: 8, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(112,151,204,.10)" />
                  <XAxis type="number" dataKey="volume" name="Volume" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis type="number" dataKey="velocity" name="Velocity" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
                  <ZAxis type="number" dataKey="size" range={[55, 190]} />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} content={<ChartTooltip />} />
                  <Scatter data={scatterData}>
                    {scatterData.map((item, index) => <Cell key={item.id || index} fill={item.news_aligned ? COLORS.orange : COLORS.cyan} />)}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </Panel>

            <Panel title="Signal feed (live)" className="signal-feed-panel">
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
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={(intelligence.heading_visibility || []).slice(0, 6)} layout="vertical" margin={{ left: 6, right: 18 }}>
                <CartesianGrid stroke="rgba(112,151,204,.10)" horizontal={false} />
                <XAxis type="number" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="keyword" width={92} tick={{ fill: "#c3d2e3", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="visibility" name="Visibility" fill={COLORS.cyan} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
          <Panel title="Signal sentiment" className="sentiment-panel">
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={intelligence.sentiment_distribution || []}>
                <CartesianGrid stroke="rgba(112,151,204,.10)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: COLORS.muted, fontSize: 11 }} axisLine={false} tickLine={false} width={30} />
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
            <div className="interactive-panel-heading">
              <span>Click a topic to filter stories</span>
              {selectedKeyword && <button type="button" onClick={() => setSelectedKeyword(null)}>Clear filter</button>}
            </div>
            <BubbleField
              items={intelligence.keyword_bubbles || []}
              selectedKeyword={selectedKeyword}
              onSelectKeyword={setSelectedKeyword}
            />
          </Panel>
          <Panel title="Notable stories" className="notable-panel">
            <div className="interactive-panel-heading">
              <span>{selectedKeyword ? `Filtered by “${selectedKeyword}”` : "Highest-signal stories"}</span>
              <b>{matchedStories.length} stories</b>
            </div>
            <div className="notable-list">
              {matchedStories.slice(0, 7).map((story: Row) => (
                <a href={storyHref(story)} target="_blank" rel="noreferrer" key={story.story_id}>
                  <span>{story.title}</span>
                  <small>{formatNumber(story.score)} pts · {formatNumber(story.num_comments)} comments</small>
                </a>
              ))}
              {matchedStories.length === 0 && <p className="empty-filter">No stories match this topic in the current window.</p>}
            </div>
          </Panel>
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

        <div className="investigation-cases">
          {eventBriefs.slice(0, 5).map((brief: Row, index: number) => {
            const selected = selectedBrief.id === brief.id;
            return (
              <button
                type="button"
                className={selected ? "investigation-case active" : "investigation-case"}
                aria-pressed={selected}
                onClick={() => setOpenBrief(brief.id)}
                key={brief.id}
              >
                <span className="case-summary-top">
                  <span><i className={brief.news_aligned ? "case-dot aligned" : "case-dot"} /> Case {String(index + 1).padStart(2, "0")}</span>
                  <em>{Math.round(Number(brief.confidence || 0) * 100)}%</em>
                </span>
                <b>{brief.headline_summary || brief.topic}</b>
                <small>{brief.topic} · {brief.evidence_count || 0} evidence items</small>
              </button>
            );
          })}
        </div>

        <article className="investigation-detail">
          <div className="investigation-detail-heading">
            <span>Selected assessment</span>
            <strong>{selectedBrief.event_type?.replaceAll("_", " ") || "signal review"} · z {formatNumber(selectedBrief.z_score, 1)}</strong>
          </div>
          <div className="case-facts">
            <span><b>Feed</b>{selectedBrief.source_feed || "—"}</span>
            <span><b>Triggered by</b>{selectedBrief.triggered_by || "—"}</span>
            <span><b>Evidence</b>{selectedBrief.evidence_count || 0} linked records</span>
            <span><b>News</b>{selectedBrief.news_aligned ? "Externally aligned" : "Unconfirmed"}</span>
          </div>
          <p>{selectedBrief.summary || "No investigation summary is available."}</p>
          <div className="case-tags">
            <span>{selectedBrief.topic || "Signal intelligence"}</span>
            <span>{selectedBrief.sentiment_label || "neutral"}</span>
            <span>{Math.round(Number(selectedBrief.confidence || 0) * 100)}% confidence</span>
          </div>
        </article>

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

      <footer>
        <span><Activity size={14} /> Sonar AI</span>
        <p>Technology signal monitoring · FastAPI + React + PostgreSQL + Gemini</p>
      </footer>
    </main>
  );
}
