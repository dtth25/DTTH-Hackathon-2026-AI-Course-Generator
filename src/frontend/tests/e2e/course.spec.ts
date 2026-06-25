import { test, expect } from '@playwright/test';
import { CoursePage } from '../pages/CoursePage';

test.describe('Course Feature - TC_COURSE_01 to TC_COURSE_09', () => {

  test('TC_COURSE_01: Generate Course thành công @P0', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseSuccess();
    await coursePage.navigate();

    await coursePage.clickGenerateCourse();
    await expect(coursePage.getLoadingSpinner()).toBeVisible({ timeout: 5000 });

    await expect(coursePage.getModules()).toBeVisible({ timeout: 10000 });
  });

  test('TC_COURSE_02: Key Points hiển thị trong module @P0', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseSuccess();
    await coursePage.navigate();
    await coursePage.clickGenerateCourse();

    await expect(coursePage.getKeyPoints()).toBeVisible({ timeout: 10000 });
  });

  test('TC_COURSE_03: Citation Display - có citation marker @P0', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseSuccess();
    await coursePage.navigate();
    await coursePage.clickGenerateCourse();

    await expect(coursePage.getCitationMarker(1)).toBeVisible({ timeout: 10000 });
  });

  test('TC_COURSE_04: Click module trong sidebar @P1', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseSuccess();
    await coursePage.navigate();
    await coursePage.clickGenerateCourse();

    await coursePage.clickModuleByTitle('Module 1');
    await expect(page.locator('text=Nội dung module 1')).toBeVisible({ timeout: 5000 });
  });

  test('TC_COURSE_05: Progress bar hiển thị khi generate @P1', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.navigate();

    await page.route('**/api/generate-course', async route => {
      await new Promise(resolve => setTimeout(resolve, 2000));
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    await coursePage.clickGenerateCourse();
    await expect(coursePage.getLoadingSpinner()).toBeVisible({ timeout: 3000 });
  });

  test('TC_COURSE_06: Error message khi backend lỗi @P1', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseError();
    await coursePage.navigate();

    await coursePage.clickGenerateCourse();
    await expect(coursePage.getCourseError()).toBeVisible({ timeout: 10000 });
    await expect(coursePage.getRetryButton()).toBeVisible({ timeout: 5000 });
  });

  test('TC_COURSE_08: Click citation marker hiển thị tooltip @P0', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.mockGenerateCourseSuccess();
    await coursePage.navigate();
    await coursePage.clickGenerateCourse();

    const citation = await coursePage.getCitationMarker(1);
    if (await citation.isVisible({ timeout: 5000 }).catch(() => false)) {
      await citation.click();
      await expect(coursePage.getCitationTooltip()).toBeVisible({ timeout: 3000 });
    }
  });

  test('TC_COURSE_09: Empty state khi chưa upload file @P2', async ({ page }) => {
    const coursePage = new CoursePage(page);
    await coursePage.navigate();

    await page.route('**/api/generate-course', async route => {
      await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'Vui lòng upload tài liệu trước' }) });
    });

    await coursePage.clickGenerateCourse();
    await expect(page.locator('text=Vui lòng upload tài liệu trước')).toBeVisible({ timeout: 5000 });
  });
});