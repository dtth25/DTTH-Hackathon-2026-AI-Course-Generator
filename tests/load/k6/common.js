import http from "k6/http";
import { check, fail, sleep } from "k6";

export const BASE = __ENV.BASE_URL || "http://frontend:3000";
export const PASSWORD = __ENV.LOAD_TEST_PASSWORD;

export function login(number) {
  const email = number === 0 ? "loadtest-admin@example.com" : `loadtest-${String(number).padStart(3, "0")}@example.com`;
  const response = http.post(`${BASE}/api/auth/login`, JSON.stringify({ email, password: PASSWORD }), { headers: { "Content-Type": "application/json" }, tags: { endpoint: "login" } });
  if (!check(response, { "login 200": (r) => r.status === 200 })) fail(`login failed status=${response.status}`);
  return response.json("access_token");
}

export function auth(token, tags = {}) {
  return { headers: { Authorization: `Bearer ${token}` }, tags };
}

export function pollJob(token, jobId, timeoutSeconds = 120) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const response = http.get(`${BASE}/api/jobs/${encodeURIComponent(jobId)}`, auth(token, { endpoint: "job-status" }));
    if (response.status !== 200) return { status: "http_error", response };
    const state = response.json("status");
    if (["succeeded", "failed", "cancelled"].includes(state)) return { status: state, response };
    sleep(1);
  }
  return { status: "timeout", response: null };
}
