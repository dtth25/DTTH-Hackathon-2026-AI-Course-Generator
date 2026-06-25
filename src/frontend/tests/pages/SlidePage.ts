import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class SlidePage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/slides');
  }

  async mockGenerateSlides() {
    await this.page.route('**/api/generate-slides', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.slides.success) });
    });
  }

  async mockSlideError() {
    await this.page.route('**/api/generate-slides', async route => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Lỗi tạo slide' }) });
    });
  }

  async clickGenerateSlides() {
    await this.page.getByRole('button', { name: /generate slides|tạo slide/i }).click();
  }

  async getSlideTitle() {
    return this.page.locator('.slide-title, [data-testid="slide-title"]');
  }

  async getBulletPoints() {
    return this.page.locator('.bullet-point, [data-testid="bullet-point"]');
  }

  async clickNext() {
    await this.page.getByRole('button', { name: /next|→/i }).click();
  }

  async clickPrev() {
    await this.page.getByRole('button', { name: /prev|←/i }).click();
  }

  async getSlideNumber() {
    return this.page.locator('text=/Slide \\d+\\/\\d+/i');
  }

  async getCitation() {
    return this.page.locator('text=/\\[\\d+\\]|citation|Nguồn/i');
  }

  async clickFullscreen() {
    await this.page.getByRole('button', { name: /fullscreen|toàn màn hình/i }).click();
  }

  async clickThumbnail(index: number) {
    const thumbs = await this.page.locator('.thumbnail, [data-testid="thumbnail"]').all();
    if (thumbs[index]) await thumbs[index].click();
  }

  async getError() {
    return this.page.locator('text=/Lỗi|thử lại|Retry/i');
  }
}