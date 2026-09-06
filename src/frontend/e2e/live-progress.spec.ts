import { expect, test, type Page, type Route } from "@playwright/test";

import { installVisualDemoRoutes, primeVisualAuth } from "./fixtures/visual-app";

type ArtifactCase = {
  endpoint: "book" | "slide" | "quiz" | "vid";
  tab: string;
  jobType: "book" | "slides" | "quiz" | "video";
  oldMarker: string;
  alternateMarker: string;
  completedMarker: string;
  data: (marker: string) => unknown;
};

const cases: ArtifactCase[] = [
  {
    endpoint: "book", tab: "Study Guide", jobType: "book",
    oldMarker: "BOOK OLD SELECTED", alternateMarker: "BOOK ALTERNATE", completedMarker: "BOOK COMPLETED",
    data: (marker) => ({ title: marker, summary: "Summary", chapters: [{ chapter_title: "Chapter", sections: [{ title: "Section", content: marker }] }] }),
  },
  {
    endpoint: "slide", tab: "Slide", jobType: "slides",
    oldMarker: "SLIDE OLD SELECTED", alternateMarker: "SLIDE ALTERNATE", completedMarker: "SLIDE COMPLETED",
    data: (marker) => ({ title: marker, slides: [{ slide_number: 1, title: marker, bullet_points: ["Point"] }] }),
  },
  {
    endpoint: "quiz", tab: "Quiz", jobType: "quiz",
    oldMarker: "QUIZ OLD SELECTED", alternateMarker: "QUIZ ALTERNATE", completedMarker: "QUIZ COMPLETED",
    data: (marker) => [{ question: marker, options: ["A", "B"], correct: "A" }],
  },
  {
    endpoint: "vid", tab: "Video", jobType: "video",
    oldMarker: "VIDEO OLD SELECTED", alternateMarker: "VIDEO ALTERNATE", completedMarker: "VIDEO COMPLETED",
    data: (marker) => ({ title: marker, scenes: [{ scene_number: 1, title: marker, narration: "Narration", duration_seconds: 5 }] }),
  },
];

function selectedVersion(route: Route): string | null {
  return new URL(route.request().url()).searchParams.get("version");
}

async function installArtifactDefaults(page: Page): Promise<void> {
  for (const item of cases) {
    await page.route(`**/api/course/demo-course/${item.endpoint}*`, (route) => route.fulfill({
      json: {
        status: "ready", progress: 100, version_id: `${item.endpoint}-stable`,
        active_version: `${item.endpoint}-stable`, versions: [], data: item.data(`${item.endpoint} stable`),
      },
    }));
  }
  await page.route("**/api/course/demo-course/slide-images/**", (route) => route.fulfill({ status: 204 }));
}

for (const item of cases) {
  test(`${item.tab} recovers a long active version while preserving selected content`, async ({ page, context }) => {
    await page.clock.install({ time: new Date("2026-09-05T00:00:00Z") });
    await primeVisualAuth(page);
    await installVisualDemoRoutes(page);
    await installArtifactDefaults(page);

    let completed = false;
    let jobReads = 0;
    const activeVersion = `${item.endpoint}-v2`;
    await page.route(`**/api/course/demo-course/${item.endpoint}*`, (route) => {
      const requested = selectedVersion(route);
      const version = requested ?? `${item.endpoint}-v1`;
      const marker = version === `${item.endpoint}-v0`
        ? item.alternateMarker
        : version === activeVersion
          ? item.completedMarker
          : item.oldMarker;
      const active = !completed;
      return route.fulfill({ json: {
        status: version === activeVersion && active ? "processing" : "ready",
        progress: version === activeVersion && active ? 52 : 100,
        version_id: version,
        active_version: activeVersion,
        job_id: version === activeVersion ? `${item.endpoint}-job` : `${item.endpoint}-old-job`,
        active_job: active ? { job_id: `${item.endpoint}-job`, version_id: activeVersion } : null,
        versions: [
          { version_id: `${item.endpoint}-v0`, label: "Bản thay thế", options: {}, status: "ready", progress: 100 },
          { version_id: `${item.endpoint}-v1`, label: "Bản đang xem", options: {}, status: "ready", progress: 100 },
          { version_id: activeVersion, label: "Bản đang tạo", options: {}, status: active ? "processing" : "ready", progress: active ? 52 : 100 },
        ],
        data: version === activeVersion && active ? null : item.data(marker),
      }});
    });
    await page.route(`**/api/jobs/${item.endpoint}-job`, (route) => {
      jobReads += 1;
      return route.fulfill({ json: {
        id: `${item.endpoint}-job`, document_id: "demo-course", job_type: item.jobType,
        status: completed ? "succeeded" : "running", progress: completed ? 100 : 52,
        stage: completed ? "completed" : "generating", message: "private worker text",
        created_at: "2026-09-05T00:00:00Z", updated_at: "2026-09-05T00:00:00Z",
      }});
    });

    await page.goto("/course/demo-course");
    await page.getByRole("tab", { name: item.tab }).click();
    await expect(page.getByText(item.oldMarker, { exact: false }).first()).toBeVisible();
    await expect(page.getByText(new RegExp("52%", "u")).first()).toBeVisible();

    await page.getByRole("button", { name: "Bản thay thế" }).click();
    await expect(page.getByText(item.alternateMarker, { exact: false }).first()).toBeVisible();
    await page.clock.fastForward(3_000);
    await expect(page.getByText(item.alternateMarker, { exact: false }).first()).toBeVisible();

    await page.reload();
    await page.getByRole("tab", { name: item.tab }).click();
    await expect(page.getByText(item.oldMarker, { exact: false }).first()).toBeVisible();
    await expect(page.getByText(new RegExp("52%", "u")).first()).toBeVisible();
    expect(jobReads).toBeGreaterThan(1);

    await context.setOffline(true);
    await page.clock.fastForward(361_000);
    await expect(page.getByText(/mất nhiều thời gian hơn dự kiến/u)).toBeVisible();
    completed = true;
    await context.setOffline(false);
    await page.clock.fastForward(3_100);
    await expect(page.getByText(item.completedMarker, { exact: false }).first()).toBeVisible({ timeout: 5_000 });
  });
}

for (const item of cases) {
  test(`${item.tab} ignores a late artifact response after course navigation`, async ({ page }) => {
    await primeVisualAuth(page);
    await installVisualDemoRoutes(page);
    await page.route("**/api/course/second-course/status", (route) => route.fulfill({ json: {
      course_id: "second-course", name: "Second course", status: "ready", progress: 100,
      filenames: ["second.txt"], file_count: 1,
    }}));
    await page.route("**/api/course/second-course/study-pack", (route) => route.fulfill({ json: {
      course_id: "second-course", stats: { course_id: "second-course", status: "ready", has_book: false, has_book_pdf: false, has_slide: false, has_slide_pptx: false, has_quiz: false, has_quiz_answer_key: false, has_vid: false }, study_pack: { title: "Second course" },
    }}));
    for (const candidate of cases) {
      await page.route(`**/api/course/second-course/${candidate.endpoint}*`, (route) => route.fulfill({ json: {
        status: "ready", progress: 100, version_id: "second-v1", active_version: "second-v1", versions: [], data: candidate.data("SECOND COURSE CONTENT"),
      }}));
    }
    await page.route(`**/api/course/demo-course/${item.endpoint}*`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 800));
      await route.fulfill({ json: { status: "ready", progress: 100, version_id: "late-v1", versions: [], data: item.data("LATE OLD COURSE CONTENT") } }).catch(() => undefined);
    });

    await page.goto("/course/demo-course");
    await page.getByRole("tab", { name: item.tab }).click();
    await page.goto("/course/second-course");
    await page.getByRole("tab", { name: item.tab }).click();
    const visiblePanel = page.locator('[role="tabpanel"]:visible');
    await expect(visiblePanel.getByText("SECOND COURSE CONTENT", { exact: false }).first()).toBeVisible();
    await page.waitForTimeout(1_000);
    await expect(page.getByText("LATE OLD COURSE CONTENT", { exact: false })).toHaveCount(0);
  });
}
