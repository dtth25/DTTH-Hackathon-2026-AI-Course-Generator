import { stat } from "node:fs/promises";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { installVisualDemoRoutes, primeVisualAuth } from "./fixtures/visual-app";

const productAsset = (filename: string) =>
  path.resolve(process.cwd(), "public", "product", filename);

test("capture product evidence", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await primeVisualAuth(page);
  await installVisualDemoRoutes(page);

  await page.goto("/course/demo-course");
  await expect(
    page.evaluate(() => localStorage.getItem("agy_auth_token"))
  ).resolves.toBe("visual-fixture-token");
  const workspace = page.locator('[data-visual-state="course-workspace"]');
  await expect(workspace).toBeVisible({ timeout: 20_000 });
  await expect(workspace.getByText(/(?:Chất lượng|Cần rà soát|Bản nháp).*\/100/u)).toHaveCount(0);

  const bookPanel = page.locator('[data-slot="tabs-content"]:visible');
  await expect(
    bookPanel.getByRole("heading", {
      level: 2,
      name: "Nhập môn sinh thái đô thị",
    })
  ).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  await workspace.screenshot({
    path: productAsset("course-workspace.png"),
    animations: "disabled",
  });
  await bookPanel.screenshot({
    path: productAsset("book-reading.png"),
    animations: "disabled",
  });

  await page.getByRole("tab", { name: "Video" }).click();
  const videoPanel = page.locator('[data-slot="tabs-content"]:visible');
  await expect(videoPanel.getByText("Đang dựng video (64%)…")).toBeVisible();
  await videoPanel.screenshot({
    path: productAsset("video-progress.png"),
    animations: "disabled",
  });

  for (const filename of [
    "course-workspace.png",
    "book-reading.png",
    "video-progress.png",
  ]) {
    await expect((await stat(productAsset(filename))).size).toBeGreaterThan(20_000);
  }
});
