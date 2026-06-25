import { test, expect } from '@playwright/test';
import { SlidePage } from '../pages/SlidePage';

test.describe('Slide Feature - TC_SLIDE_01 to TC_SLIDE_10', () => {

  test.beforeEach(async ({ page }) => {
    const slidePage = new SlidePage(page);
    await slidePage.mockGenerateSlides();
    await slidePage.navigate();
    await slidePage.clickGenerateSlides();
    await page.waitForTimeout(1000);
  });

  test('TC_SLIDE_01: Generate Slides thành công @P0', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await expect(slidePage.getSlideTitle()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SLIDE_02: Slide hiển thị title và bullet points @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await expect(slidePage.getSlideTitle()).toBeVisible({ timeout: 5000 });
    await expect(slidePage.getBulletPoints()).toHaveCount(3, { timeout: 5000 });
  });

  test('TC_SLIDE_03: Navigation Next chuyển slide @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await slidePage.clickNext();
    await expect(page.locator('text=Slide 2')).toBeVisible({ timeout: 5000 });
  });

  test('TC_SLIDE_04: Navigation Prev quay lại slide @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await slidePage.clickNext();
    await slidePage.clickPrev();
    await expect(page.locator('text=Slide 1')).toBeVisible({ timeout: 5000 });
  });

  test('TC_SLIDE_06: Progress dots hiển thị @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await expect(slidePage.getSlideNumber()).toBeVisible({ timeout: 5000 });
  });

  test('TC_SLIDE_07: Citation trong slide @P0', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await expect(slidePage.getCitation()).toBeVisible({ timeout: 5000 });
  });

  test('TC_SLIDE_08: Fullscreen mode @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await slidePage.clickFullscreen();
    await page.waitForTimeout(500);
    // Check fullscreen element is active
    const fsElement = page.locator(':fullscreen, [data-fullscreen="true"]');
    await expect(fsElement).toBeVisible({ timeout: 3000 });
  });

  test('TC_SLIDE_09: Error khi backend fail @P1', async ({ page }) => {
    const slidePage = new SlidePage(page);
    await slidePage.mockSlideError();
    await slidePage.navigate();
    await slidePage.clickGenerateSlides();

    await expect(slidePage.getError()).toBeVisible({ timeout: 10000 });
  });
});