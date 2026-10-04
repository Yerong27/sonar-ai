export type Row = Record<string, any>;
export type DashboardData = {
  overview: Row;
  metrics: Row[];
  intelligence: Row;
  stories: Row[];
  anomalies: Row[];
  runtime: Row | null;
  mode: "live" | "demo";
};

export async function loadDashboardData({ mode, base, snapshot, fetchImpl = fetch }: {
  mode: string | undefined;
  base: string;
  snapshot: DashboardData;
  fetchImpl?: typeof fetch;
}): Promise<DashboardData> {
  // Safe by default; even a leftover production URL cannot enable live requests.
  if (mode !== "live") return structuredClone(snapshot);
  if (!base) throw new Error("Live mode requires NEXT_PUBLIC_SONAR_API_BASE");
  async function get(path: string) {
    const response = await fetchImpl(`${base.replace(/\/$/, "")}${path}`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }
  const [overview, metrics, intelligence, stories, anomalies, runtime] = await Promise.all([
    get("/api/dashboard/overview"),
    get("/api/metrics/timeline?limit=160"),
    get("/api/ai/intelligence"),
    get("/api/stories?limit=80"),
    get("/api/anomalies?limit=40"),
    get("/api/runtime").catch(() => null),
  ]);
  return {
    overview, intelligence, runtime, mode: "live",
    metrics: metrics.timeline || [],
    stories: stories.stories || [],
    anomalies: anomalies.anomalies || [],
  };
}
