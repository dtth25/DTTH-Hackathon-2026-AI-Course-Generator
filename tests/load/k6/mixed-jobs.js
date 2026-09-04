import http from "k6/http";
import { check, sleep } from "k6";
import exec from "k6/execution";
import { auth, BASE, login, pollJob } from "./common.js";

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  scenarios: { mixed_jobs: { executor: "constant-arrival-rate", rate: 20, timeUnit: "1m", duration: __ENV.MIXED_DURATION || "10m", preAllocatedVUs: 100, maxVUs: 100 } },
  thresholds: { checks: ["rate==1"], http_req_failed: ["rate<0.01"], "http_req_duration{endpoint:enqueue}": ["p(95)<2000"], dropped_iterations: ["count==0"] },
};

const seen = {};
const fixture = open("../fixtures/load-document.txt", "b");
export default function () {
  const number = (exec.scenario.iterationInTest % 100) + 1;
  const token = login(number);
  const body = { files: http.file(fixture, `load-${__VU}-${__ITER}.txt`, "text/plain") };
  const upload = http.post(`${BASE}/api/upload`, body, auth(token, { endpoint: "enqueue" }));
  if (!check(upload, { "upload queued": (r) => r.status === 201 })) return;
  const ingestId = upload.json("job_id");
  if (seen[ingestId]) check(false, { "job ids unique": () => false });
  seen[ingestId] = true;
  const ingested = pollJob(token, ingestId, 120);
  if (!check(ingested, { "ingestion succeeded": (r) => r.status === "succeeded" })) return;
  const courseId = upload.json("course_id");
  const variants = [
    ["book", "/api/generate-book", { course_id: courseId, detail_level: "Tóm tắt" }],
    ["slide", "/api/generate-slide", { course_id: courseId, mode: "summary", topic: "Load" }],
    ["quiz", "/api/generate-quiz", { course_id: courseId, quantity: 1, difficulty: "easy" }],
    ["video", "/api/generate-vid", { course_id: courseId, format: "shorts", voice: "female" }],
  ];
  const [kind, path, payload] = variants[exec.scenario.iterationInTest % variants.length];
  const generated = http.post(`${BASE}${path}`, JSON.stringify(payload), { ...auth(token, { endpoint: "enqueue", artifact: kind }), headers: { ...auth(token).headers, "Content-Type": "application/json" } });
  if (!check(generated, { "artifact queued": (r) => r.status === 200 })) return;
  const generatedId = generated.json("job_id");
  check(seen[generatedId] === undefined, { "job ids unique": (ok) => ok }); seen[generatedId] = true;
  check(pollJob(token, generatedId, kind === "video" ? 300 : 180), { "artifact succeeded": (r) => r.status === "succeeded" });
  if (__ITER % 10 === 0) {
    const admin = login(0); const summary = http.get(`${BASE}/api/admin/jobs/summary`, auth(admin, { endpoint: "summary" }));
    const counts = summary.json("counts") || {}; let backlog = 0;
    Object.values(counts).forEach((queue) => { backlog += (queue.queued || 0) + (queue.running || 0) + (queue.retry_scheduled || 0); });
    check(backlog < 200, { "global backlog below 200": (ok) => ok });
  }
  sleep(0.1);
}
