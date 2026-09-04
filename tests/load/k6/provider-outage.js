import http from "k6/http";
import { check, fail, sleep } from "k6";
import { auth, BASE, login, pollJob } from "./common.js";

export const options = {
  vus: 1,
  iterations: 1,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  thresholds: { checks: ["rate==1"], http_req_failed: ["rate<0.20"] },
};
const CONTROL = __ENV.LOAD_TEST_CONTROL_TOKEN;
const MOCK = __ENV.MOCK_URL || "http://mock-openrouter:8080";
const fixture = open("../fixtures/load-document.txt", "b");

function fault(mode) {
  const response = http.put(`${MOCK}/__control/fault`, JSON.stringify({ mode }), { headers: { Authorization: `Bearer ${CONTROL}`, "Content-Type": "application/json" }, responseCallback: http.expectedStatuses(200) });
  if (response.status !== 200) fail(`control failed status=${response.status}`);
}

export default function () {
  const admin = login(0);
  const modes = (__ENV.OUTAGE_MODES || "key-limit,rate-limit,unavailable").split(",");
  for (const mode of modes) {
    fault(mode);
    const uploads = [];
    for (let i = 0; i < 20; i++) {
      const token = login((["key-limit", "rate-limit", "unavailable"].indexOf(mode) * 20) + i + 1);
      const body = { files: http.file(fixture, `${mode}-${i}.txt`, "text/plain") };
      uploads.push({ response: http.post(`${BASE}/api/upload`, body, auth(token, { endpoint: "outage-enqueue" })), token });
    }
    check(uploads, { "all 20 outage jobs accepted": (items) => items.length === 20 && items.every((item) => item.response.status === 201) });
    const accepted = uploads.filter((item) => item.response.status === 201);
    sleep(5);
    const stats = http.get(`${MOCK}/__control/stats`, { headers: { Authorization: `Bearer ${CONTROL}` } });
    check(stats, { "provider calls bounded": (r) => (r.json("total") || 0) <= accepted.length * 2 + 3 });
    fault("healthy");
    const health = http.get(`${BASE}/api/admin/provider-health?force=true`, auth(admin, { endpoint: "provider-recovery" }));
    check(health, { "provider recovered": (r) => r.status === 200 && r.json("available") === true });
    accepted.forEach((r) => {
      const originalId = r.response.json("job_id");
      const state = http.get(`${BASE}/api/jobs/${originalId}`, auth(r.token, { endpoint: "outage-state" }));
      let recovered;
      if (["failed", "cancelled"].includes(state.json("status"))) {
        const course = r.response.json("course_id");
        const retry = http.post(`${BASE}/api/documents/${course}/retry`, null, auth(r.token, { endpoint: "manual-retry" }));
        check(retry, { "manual retry accepted": (response) => response.status === 202 });
        recovered = retry.status === 202 ? pollJob(r.token, retry.json("job_id"), 120) : { status: "retry_rejected" };
      } else {
        recovered = pollJob(r.token, originalId, 120);
      }
      check(recovered, { "outage job recovered": (result) => result.status === "succeeded" });
    });
  }
}
