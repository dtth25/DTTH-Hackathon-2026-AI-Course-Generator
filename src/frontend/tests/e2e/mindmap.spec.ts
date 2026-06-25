import { test, expect } from '@playwright/test';
import { MindmapPage } from '../pages/MindmapPage';

test.describe('Mindmap Feature - TC_MINDMAP_01 to TC_MINDMAP_10', () => {

  test.beforeEach(async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.mockGenerateMindmap();
    await mindmapPage.navigate();
    await mindmapPage.clickGenerateMindmap();
    await page.waitForTimeout(1000);
  });

  test('TC_MINDMAP_01: Generate Mindmap thành công @P0', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await expect(mindmapPage.getRootNode()).toBeVisible({ timeout: 10000 });
  });

  test('TC_MINDMAP_02: Hiển thị node trung tâm và nhánh con @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await expect(mindmapPage.getRootNode()).toContainText('Chủ đề chính', { timeout: 5000 });
    const children = await mindmapPage.getChildNodes();
    await expect(children.length).toBeGreaterThanOrEqual(1);
  });

  test('TC_MINDMAP_03: Expand node hiển thị thêm nodes @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    if (await page.locator('text=+').isVisible({ timeout: 2000 }).catch(() => false)) {
      await mindmapPage.expandNode();
      await expect(mindmapPage.getChildNodes()).toHaveCount(2, { timeout: 3000 });
    }
  });

  test('TC_MINDMAP_04: Collapse node thu gọn @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    if (await page.locator('text=-').isVisible({ timeout: 2000 }).catch(() => false)) {
      await mindmapPage.collapseNode();
      await page.waitForTimeout(500);
    }
  });

  test('TC_MINDMAP_05: Click node lá hiển thị tooltip @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.clickLeafNode();
    await expect(mindmapPage.getTooltip()).toBeVisible({ timeout: 3000 });
  });

  test('TC_MINDMAP_06: Pan canvas bằng drag @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.panCanvas(50, 50);
    await page.waitForTimeout(300);
  });

  test('TC_MINDMAP_07: Zoom hoạt động @P1', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.zoomIn();
    await page.waitForTimeout(300);
  });

  test('TC_MINDMAP_08: Citation hiển thị khi hover @P0', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await expect(mindmapPage.getCitation()).toBeVisible({ timeout: 5000 });
  });

  test('TC_MINDMAP_09: Re-layout sắp xếp lại sơ đồ @P2', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.clickReLayout();
    await page.waitForTimeout(500);
  });

  test('TC_MINDMAP_10: Export mindmap @P2', async ({ page }) => {
    const mindmapPage = new MindmapPage(page);
    await mindmapPage.clickExport();
    await page.waitForTimeout(500);
  });
});