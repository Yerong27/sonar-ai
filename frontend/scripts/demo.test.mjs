import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { loadDashboardData } from "../app/data-source.ts";

const snapshot = JSON.parse(await readFile(new URL("../app/data/demo-snapshot.json", import.meta.url)));
const base = "https://sonar-api-4akcp3ehqa-ts.a.run.app";
for (const mode of ["demo", undefined, "invalid"]) {
  test(`${String(mode)}: no backend calls, even with a production API URL`, async () => {
    const data = await loadDashboardData({ mode, base, snapshot, fetchImpl: () => { throw new Error("Demo attempted a network request"); } });
    assert.deepEqual(data, snapshot);
    assert.notEqual(data, snapshot);
    assert.notEqual(data.stories, snapshot.stories);
    assert.equal(data.mode, "demo");
  });
}
test("live mode keeps the original six read-only endpoints", async () => {
  const calls = [];
  const data = await loadDashboardData({ mode: "live", base, snapshot, fetchImpl: async (url) => {
    calls.push(String(url));
    return new Response(JSON.stringify({ stories: [], timeline: [], anomalies: [] }));
  } });
  assert.equal(calls.length, 6);
  assert.ok(calls.every(url => url.startsWith(base + "/api/")));
  assert.equal(data.mode, "live");
});
test("recorded dataset includes original landscape, themes, keywords and investigations", () => {
  assert.equal(snapshot.runtime, null);
  assert.ok(snapshot.captured_at);
  assert.ok(snapshot.stories.length >= 40);
  assert.ok(snapshot.metrics.length);
  assert.ok(snapshot.intelligence.monitoring_summary);
  assert.ok(snapshot.intelligence.ranked_themes.length);
  assert.ok(snapshot.intelligence.topic_clusters.length);
  assert.ok(snapshot.intelligence.event_briefs.length);
});
