import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { DEMO_COURSE_LIST, DEMO_STUDY_PACK } from "./fixtures/demo-data";
import { installVisualDemoRoutes, primeVisualAuth } from "./fixtures/visual-app";

const LANDING_VIEWPORTS = [
  { name: "mobile", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
] as const;

const PRODUCT_VIEWPORTS = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
] as const;

type VisualTheme = "light" | "dark";

const VISUAL_COPYRIGHT_YEAR = "2024";

async function setVisualTheme(page: Page, theme: VisualTheme): Promise<void> {
  await page.addInitScript((persistedTheme) => {
    localStorage.setItem("theme", persistedTheme);
  }, theme);
}

async function prepareAuthenticatedPage(
  page: Page,
  theme: VisualTheme = "light"
): Promise<void> {
  await setVisualTheme(page, theme);
  await primeVisualAuth(page);
  await installVisualDemoRoutes(page);
}

async function waitForVisualAssets(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      Array.from(document.images).map(async (image) => {
        if (!image.complete) {
          await new Promise<void>((resolve) => {
            image.addEventListener("load", () => resolve(), { once: true });
            image.addEventListener("error", () => resolve(), { once: true });
          });
        }
        await image.decode().catch(() => undefined);
      })
    );
  });
}

async function normalizeDynamicVisualContent(page: Page): Promise<void> {
  const footerCopyright = page
    .locator("footer p")
    .filter({ hasText: /^©\s+\d{4}\s+HackaGen$/u });
  await expect(footerCopyright).toHaveCount(1);
  await footerCopyright.evaluate(
    (element, fixedYear) => {
      element.textContent = `© ${fixedYear} HackaGen`;
    },
    VISUAL_COPYRIGHT_YEAR
  );
}

async function expectNoHighImpactA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const highImpactViolations = results.violations
    .filter((item) => ["serious", "critical"].includes(item.impact ?? ""))
    .map((item) => ({
      id: item.id,
      impact: item.impact,
      targets: item.nodes.flatMap((node) => node.target.map(String)),
    }));
  expect(highImpactViolations).toEqual([]);
}

async function expectNoInventedQualityMetric(page: Page): Promise<void> {
  await expect(page.getByText(/(?:Chất lượng|Cần rà soát|Bản nháp).*\/100/u)).toHaveCount(0);
}

async function expectVisualSnapshot(page: Page, name: string): Promise<void> {
  await normalizeDynamicVisualContent(page);
  await waitForVisualAssets(page);
  await expect(page).toHaveScreenshot(`${name}.png`, {
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
  await expectNoHighImpactA11yViolations(page);
}

async function expectLandingSemantics(page: Page, isDesktop: boolean): Promise<void> {
  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toBeVisible();

  if (isDesktop) {
    await expect
      .poll(() =>
        heading.evaluate((element) => ["left", "start"].includes(getComputedStyle(element).textAlign))
      )
      .toBe(true);
  }

  const evidence = page.locator("#evidence");
  const finalAction = page.locator("#start");
  const evidenceImages = evidence.locator("img");
  const landingImages = page.locator("main img");
  await evidence.scrollIntoViewIfNeeded();
  await expect(evidenceImages).toHaveCount(2);
  await expect(landingImages).toHaveCount(3);

  for (const image of await landingImages.all()) {
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute("alt", /\S/u);
    await expect
      .poll(() =>
        image.evaluate(
          (element) =>
            element instanceof HTMLImageElement &&
            element.complete &&
            element.naturalWidth > 0 &&
            element.naturalHeight > 0
        )
      )
      .toBe(true);
  }

  const evidenceBox = await evidence.boundingBox();
  const finalActionBox = await finalAction.boundingBox();
  expect(evidenceBox).not.toBeNull();
  expect(finalActionBox).not.toBeNull();
  expect(evidenceBox!.y + evidenceBox!.height).toBeLessThanOrEqual(finalActionBox!.y);

  await expect(
    page.locator(
      'main [id*="testimonial" i], main [class*="testimonial" i], main [aria-label*="testimonial" i]'
    )
  ).toHaveCount(0);
  await expect(page.locator('main [class*="gradient"], main [class*="blur"]')).toHaveCount(0);

  const semanticOrder = await page.evaluate(() => {
    const header = document.querySelector("header");
    const title = document.querySelector("#landing-title");
    const process = document.querySelector("#process");
    const evidenceRegion = document.querySelector("#evidence");
    const finalRegion = document.querySelector("#start");
    const nodes = [header, title, process, evidenceRegion, finalRegion];
    if (nodes.some((node) => node === null)) return false;

    return nodes.slice(0, -1).every((node, index) =>
      Boolean(node!.compareDocumentPosition(nodes[index + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING)
    );
  });
  expect(semanticOrder).toBe(true);

  const visibleFocusables = page.locator(
    'a:visible, button:visible, input:visible, select:visible, textarea:visible, [tabindex]:visible:not([tabindex="-1"])'
  );
  const focusRegions = await visibleFocusables.evaluateAll((elements) =>
    elements.map((element) => {
      if (element.closest("header")) return "header";
      if (element.closest("#workspace")) return "intro";
      if (element.closest("#start")) return "final";
      return "other";
    })
  );
  const firstIntro = focusRegions.indexOf("intro");
  const firstFinal = focusRegions.indexOf("final");
  expect(firstIntro).toBeGreaterThan(0);
  expect(focusRegions.slice(0, firstIntro).every((region) => region === "header")).toBe(true);
  expect(firstFinal).toBeGreaterThan(firstIntro);
  expect(focusRegions.lastIndexOf("intro")).toBeLessThan(firstFinal);

  await page.evaluate(() => scrollTo(0, 0));
}

for (const viewport of LANDING_VIEWPORTS) {
  test(`landing ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await setVisualTheme(page, "light");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expectLandingSemantics(page, viewport.name === "desktop");
    await expectVisualSnapshot(page, `landing-${viewport.name}-light`);
  });
}

for (const viewport of PRODUCT_VIEWPORTS) {
  test(`populated courses ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await prepareAuthenticatedPage(page);
    await page.route("**/api/courses/all", (route) =>
      route.fulfill({
        json: {
          ...DEMO_COURSE_LIST,
          courses: DEMO_COURSE_LIST.courses.map((course) => ({
            ...course,
            created_at: undefined,
          })),
        },
      })
    );
    await page.goto("/courses");
    await expect(page.locator('[data-visual-state="courses-populated"]')).toBeVisible();
    await expectVisualSnapshot(page, `courses-populated-${viewport.name}-light`);
  });

  test(`course Book workspace ${viewport.name}`, async ({ page }) => {
    const theme: VisualTheme = viewport.name === "desktop" ? "dark" : "light";
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await prepareAuthenticatedPage(page, theme);
    await page.goto("/course/demo-course");
    const workspace = page.locator('[data-visual-state="course-workspace"]');
    await expect(workspace).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 2, name: "Nhập môn sinh thái đô thị" })
    ).toBeVisible();
    await expectNoInventedQualityMetric(page);
    await expectVisualSnapshot(page, `course-book-${viewport.name}-${theme}`);
  });

  test(`queued video progress ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await prepareAuthenticatedPage(page);
    let terminalGetCount = 0;
    let firstJobRequestAt: number | null = null;
    await page.route("**/api/course/demo-course/vid*", (route) =>
      route.fulfill({ json: { status: "ready", progress: 100, data: null, versions: [] } })
    );
    await page.route("**/api/generate-vid", (route) =>
      route.fulfill({
        status: 202,
        json: { course_id: "demo-course", version_id: "vid-v2", job_id: "queued-video-job" },
      })
    );
    await page.route("**/api/jobs/queued-video-job", (route) => {
      terminalGetCount += 1;
      firstJobRequestAt ??= Date.now();
      const stillQueued = Date.now() - firstJobRequestAt < 1_000;
      return route.fulfill({
        json: {
          id: "queued-video-job",
          document_id: "demo-course",
          job_type: "video",
          status: stillQueued ? "queued" : "cancelled",
          queue_position: stillQueued ? 2 : null,
          progress: 0,
          message: "private worker payload",
          created_at: "2026-09-05T00:00:00Z",
          updated_at: "2026-09-05T00:00:00Z",
        },
      });
    });
    await page.goto("/course/demo-course");
    await expect(page.locator('[data-visual-state="course-workspace"]')).toBeVisible();
    await page.getByRole("tab", { name: "Video" }).click();
    await page.getByRole("button", { name: "Tạo video bài giảng" }).click();
    await expect(page.getByText("Đang chờ", { exact: true })).toBeVisible();
    await expect(page.getByText("Hàng chờ dựng video · vị trí 2")).toBeVisible();
    await expect(page.getByText(/private worker payload/iu)).toHaveCount(0);
    await expect(page.getByText("Đã hủy")).toBeVisible({ timeout: 5_000 });
    const requestsAtTerminal = terminalGetCount;
    await page.waitForTimeout(3_200);
    expect(terminalGetCount).toBe(requestsAtTerminal);
    await expectNoInventedQualityMetric(page);
  });

  test(`retry-scheduled video countdown ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await prepareAuthenticatedPage(page);
    await page.route("**/api/course/demo-course/vid*", (route) =>
      route.fulfill({ json: { status: "ready", progress: 100, data: null, versions: [] } })
    );
    await page.route("**/api/generate-vid", (route) =>
      route.fulfill({ json: { course_id: "demo-course", version_id: "vid-v2", job_id: "retry-video-job" } })
    );
    await page.route("**/api/jobs/retry-video-job", (route) =>
      route.fulfill({
        json: {
          id: "retry-video-job",
          document_id: "demo-course",
          job_type: "video",
          status: "retry_scheduled",
          queue_position: 1,
          progress: 34,
          message: "provider diagnostic must remain private",
          created_at: "2026-09-05T00:00:00Z",
          updated_at: "2026-09-05T00:00:00Z",
          next_attempt_at: "2026-09-05T00:02:00Z",
        },
      })
    );

    await page.goto("/course/demo-course");
    await page.getByRole("tab", { name: "Video" }).click();
    await page.getByRole("button", { name: "Tạo video bài giảng" }).click();
    await expect(page.getByText("Đang chờ thử lại")).toBeVisible();
    await expect(page.getByText(/Dự kiến thử lại lúc/u)).toBeVisible();
    await expect(page.getByText(/Thử lại sau 3 giây/u)).toHaveCount(0);
    await expect(page.getByText(/provider diagnostic/iu)).toHaveCount(0);
  });

  test(`cancel running video cooperatively ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await prepareAuthenticatedPage(page);
    let cancelRequested = false;
    let terminalGetCount = 0;
    const response = (status: "running" | "cancelled") => ({
      id: "cancel-video-job",
      document_id: "demo-course",
      job_type: "video",
      status,
      queue_position: status === "running" ? 1 : null,
      progress: 41,
      message: "worker-id-3 raw payload",
      created_at: "2026-09-05T00:00:00Z",
      updated_at: "2026-09-05T00:00:00Z",
    });
    await page.route("**/api/course/demo-course/vid*", (route) =>
      route.fulfill({ json: { status: "ready", progress: 100, data: null, versions: [] } })
    );
    await page.route("**/api/generate-vid", (route) =>
      route.fulfill({ json: { course_id: "demo-course", version_id: "vid-v2", job_id: "cancel-video-job" } })
    );
    await page.route("**/api/jobs/cancel-video-job", (route) => {
      if (route.request().method() === "DELETE") {
        cancelRequested = true;
        return route.fulfill({ status: 202, json: response("running") });
      }
      terminalGetCount += 1;
      return route.fulfill({ json: response(cancelRequested ? "cancelled" : "running") });
    });

    await page.goto("/course/demo-course");
    await page.getByRole("tab", { name: "Video" }).click();
    await page.getByRole("button", { name: "Tạo video bài giảng" }).click();
    await expect(page.getByText("Đang dựng video (41%)…")).toBeVisible();
    await page.getByRole("button", { name: "Yêu cầu hủy" }).click();
    await expect(
      page.getByText("Đã gửi yêu cầu hủy. Video sẽ dừng ở điểm an toàn gần nhất.")
    ).toBeVisible();
    await expect(page.getByText("Đã hủy")).toBeVisible({ timeout: 5_000 });
    const requestsAtTerminal = terminalGetCount;
    await page.waitForTimeout(3_200);
    expect(terminalGetCount).toBe(requestsAtTerminal);
    await expect(page.getByText(/worker-id|raw payload/iu)).toHaveCount(0);
  });

  test(`ingestion error ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await prepareAuthenticatedPage(page);
    await page.route("**/api/courses/all", (route) =>
      route.fulfill({
        json: {
          courses: [
            {
              course_id: "demo-course-error",
              name: "Tài liệu cần kiểm tra lại",
              status: "error",
              filenames: ["tai-lieu-minh-hoa.pdf"],
              file_count: 1,
              error: "Không thể đọc văn bản trong tệp.",
              error_code: "DOCUMENT_TEXT_EXTRACTION_FAILED",
            },
          ],
          total: 1,
        },
      })
    );
    await page.goto("/courses");
    await expect(page.getByText("Không thể đọc văn bản trong tệp.")).toBeVisible();
    await expectVisualSnapshot(page, `ingestion-error-${viewport.name}-light`);
  });
}

test("dark authentication form", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await setVisualTheme(page, "dark");
  await page.goto("/login");
  await expect(page.getByRole("heading", { level: 1, name: "Đăng nhập" })).toBeVisible();
  await expectVisualSnapshot(page, "auth-login-desktop-dark");
});

test("document retry recovers quota-paused indexing without upload navigation", async ({ page }) => {
  await primeVisualAuth(page);
  let recoveryStatusRequests = 0;
  let retryRequests = 0;

  await page.route("**/api/course/retry-course/status", (route) => {
    const status =
      retryRequests === 0
        ? {
            course_id: "retry-course",
            name: "Tài liệu đã tải lên",
            status: "paused_due_to_quota",
            error: "Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.",
            error_code: "AI_QUOTA_EXHAUSTED",
            can_retry: true,
            recommended_action: "restore_provider_quota",
          }
        : recoveryStatusRequests++ === 0
          ? { course_id: "retry-course", status: "processing", progress: 0 }
          : { course_id: "retry-course", status: "ready", progress: 100 };
    return route.fulfill({ json: status });
  });
  await page.route("**/api/course/retry-course/study-pack", (route) =>
    route.fulfill({ json: { ...DEMO_STUDY_PACK, course_id: "retry-course" } })
  );
  for (const artifact of ["book", "slide", "quiz", "vid"]) {
    await page.route(`**/api/course/retry-course/${artifact}*`, (route) =>
      route.fulfill({ json: { status: "ready", data: null } })
    );
  }
  await page.route("**/api/documents/retry-course/retry", (route) => {
    retryRequests += 1;
    return route.fulfill({
      status: 202,
      json: {
        document_id: "retry-course",
        status: "processing",
        stage: "extracting",
        progress: 0,
        message: "Đang thử lại xử lý tài liệu từ tệp đã tải lên.",
        job_id: "retry-job",
      },
    });
  });
  await page.route("**/api/jobs/retry-job", (route) =>
    route.fulfill({
      json: {
        id: "retry-job",
        document_id: "retry-course",
        job_type: "preprocess",
        status: "succeeded",
        progress: 100,
        message: "Hoàn tất",
        created_at: "2026-09-05T00:00:00Z",
        updated_at: "2026-09-05T00:00:03Z",
        completed_at: "2026-09-05T00:00:03Z",
      },
    })
  );
  await page.goto("/course/retry-course");
  await expect(page.getByText("Dịch vụ AI đang tạm dừng vì hạn mức sử dụng.")).toBeVisible();
  await expect(page.getByText(/(?:quét|scan).*PDF|PDF.*(?:quét|scan|hỏng)/iu)).toHaveCount(0);

  await page.getByRole("button", { name: "Thử lập chỉ mục lại" }).click();
  await expect(page.getByText("Sẵn sàng")).toBeVisible({ timeout: 7_000 });
  await expect(page.getByRole("tab", { name: "Study Guide" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Slide" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Quiz" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Video" })).toBeVisible();
  expect(retryRequests).toBe(1);
  await expect(page).toHaveURL(/\/course\/retry-course$/u);
});

test("document retry shows a stable network recovery control after a status abort", async ({ page }) => {
  await primeVisualAuth(page);
  await page.route("**/api/course/network-course/status", (route) => route.abort("failed"));
  await page.route("**/api/course/network-course/study-pack", (route) =>
    route.fulfill({ json: { ...DEMO_STUDY_PACK, course_id: "network-course" } })
  );

  await page.goto("/course/network-course");
  await expect(
    page.getByText("Không thể kết nối đến máy chủ. Vui lòng kiểm tra backend và thử lại.")
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Thử kết nối lại" })).toBeVisible();
  await expect(page.getByText("Failed to fetch", { exact: false })).toHaveCount(0);
  await expect(page).toHaveURL(/\/course\/network-course$/u);
});
