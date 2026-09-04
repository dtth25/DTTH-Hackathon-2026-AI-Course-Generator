import http from "k6/http";
import { check, sleep } from "k6";
import { auth, BASE, login } from "./common.js";

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  scenarios: { active_users: { executor: "constant-vus", vus: 100, duration: __ENV.READ_DURATION || "10m" } },
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<500"], dropped_iterations: ["count==0"] },
};

let token;
export default function () {
  const number = ((__VU - 1) % 100) + 1;
  token ||= login(number);
  const course = `load-course-${String(number).padStart(3, "0")}`;
  const job = `load-job-${String(number).padStart(3, "0")}`;
  const requests = [
    ["courses", `${BASE}/api/courses/all`],
    ["course-status", `${BASE}/api/course/${course}/status`],
    ["study-pack", `${BASE}/api/course/${course}/study-pack`],
    ["job-status", `${BASE}/api/jobs/${job}`],
  ];
  const [name, url] = requests[__ITER % requests.length];
  const response = http.get(url, auth(token, { endpoint: name }));
  check(response, { [`${name} 200`]: (r) => r.status === 200 });
  sleep(0.5);
}
