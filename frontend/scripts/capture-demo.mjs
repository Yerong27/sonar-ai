import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

// Deliberate operator action only: builds and visitors never refresh this file.
const [base, destination = "app/data/demo-snapshot.json"] = process.argv.slice(2);
if (!base || !/^https?:\/\//.test(base)) {
  throw new Error("Usage: node scripts/capture-demo.mjs <API URL> [destination]");
}
const paths = {
  overview: "/api/dashboard/overview",
  metrics: "/api/metrics/timeline?limit=160",
  intelligence: "/api/ai/intelligence",
  stories: "/api/stories?limit=80",
  anomalies: "/api/anomalies?limit=40",
};
const payload = Object.fromEntries(await Promise.all(Object.entries(paths).map(async ([key, path]) => {
  const response = await fetch(`${base.replace(/\/$/, "")}${path}`, { signal: AbortSignal.timeout(120_000) });
  if (!response.ok) throw new Error(`${key}: HTTP ${response.status}`);
  return [key, await response.json()];
})));
const snapshot = {
  captured_at: new Date().toISOString(),
  source: "Recorded Sonar production API responses (Hacker News and Gemini)",
  overview: payload.overview,
  metrics: payload.metrics.timeline,
  intelligence: payload.intelligence,
  stories: payload.stories.stories,
  anomalies: payload.anomalies.anomalies,
  runtime: null,
  mode: "demo",
};
if (!snapshot.stories?.length || !snapshot.metrics?.length || !snapshot.intelligence.monitoring_summary) {
  throw new Error("Refusing to replace the demo with an empty/incomplete snapshot");
}
const target = resolve(destination);
await mkdir(dirname(target), { recursive: true });
await writeFile(target, JSON.stringify(snapshot, null, 2) + "\n");
console.log(`Saved ${snapshot.stories.length} stories, ${snapshot.metrics.length} metrics, ${snapshot.anomalies.length} investigations at ${snapshot.captured_at}`);
