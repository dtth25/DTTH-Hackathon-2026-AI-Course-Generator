import type { Page } from "@playwright/test";
import {
  DEMO_BOOK_STATUS,
  DEMO_COURSE_LIST,
  DEMO_STATUS,
  DEMO_STUDY_PACK,
  DEMO_VID_STATUS,
} from "./demo-data";

export async function primeVisualAuth(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("agy_auth_token", "visual-fixture-token");
    localStorage.setItem(
      "agy_auth_user",
      JSON.stringify({
        email: "demo@example.invalid",
        full_name: "Người học mẫu",
      })
    );
  });
}

export async function installVisualDemoRoutes(page: Page): Promise<void> {
  await page.route("**/api/courses/all", (route) =>
    route.fulfill({ json: DEMO_COURSE_LIST })
  );
  await page.route("**/api/course/demo-course/status", (route) =>
    route.fulfill({ json: DEMO_STATUS })
  );
  await page.route("**/api/course/demo-course/study-pack", (route) =>
    route.fulfill({ json: DEMO_STUDY_PACK })
  );
  await page.route("**/api/course/demo-course/book*", (route) =>
    route.fulfill({ json: DEMO_BOOK_STATUS })
  );
  await page.route("**/api/course/demo-course/vid*", (route) =>
    route.fulfill({ json: DEMO_VID_STATUS })
  );
}
