import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class MindmapPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/mindmap');
  }

  async mockGenerateMindmap() {
    await this.page.route('**/api/generate-mindmap', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.mindmap.success) });
    });
  }

  async clickGenerateMindmap() {
    await this.page.getByRole('button', { name: /generate mindmap|tạo mindmap|tạo sơ đồ tư duy/i }).click();
  }

  async getRootNode() {
    return this.page.locator('.mindmap-root, [data-testid="root-node"]');
  }

  async getChildNodes() {
    return this.page.locator('.mindmap-node, [data-testid="child-node"]');
  }

  async expandNode() {
    await this.page.locator('text=/\\+/i, .expand-button, [data-testid="expand"]').first().click();
  }

  async collapseNode() {
    await this.page.locator('text=/-/i, .collapse-button, [data-testid="collapse"]').first().click();
  }

  async clickLeafNode() {
    const leaves = await this.page.locator('.leaf-node, [data-testid="leaf-node"]').all();
    if (leaves.length > 0) await leaves[0].click();
  }

  async getTooltip() {
    return this.page.locator('[role="tooltip"], .mindmap-tooltip');
  }

  async getCitation() {
    return this.page.locator('text=/Nguồn:|Trang \\d+/i');
  }

  async panCanvas(dx: number, dy: number) {
    const canvas = this.page.locator('.mindmap-canvas, canvas, svg');
    const box = await canvas.boundingBox();
    if (box) {
      await this.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await this.page.mouse.down();
      await this.page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy);
      await this.page.mouse.up();
    }
  }

  async zoomIn() {
    await this.page.getByRole('button', { name: /zoom in|\\+/i }).click();
  }

  async clickReLayout() {
    await this.page.getByRole('button', { name: /re-layout|sắp xếp/i }).click();
  }

  async clickExport() {
    await this.page.getByRole('button', { name: /export|xuất/i }).click();
  }
}