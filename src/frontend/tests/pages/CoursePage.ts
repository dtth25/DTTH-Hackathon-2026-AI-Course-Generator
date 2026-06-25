import { Page, Locator } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class CoursePage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/course');
  }

  async mockGenerateCourseSuccess() {
    await this.page.route('**/api/generate-course', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.course.success) });
    });
  }

  async mockGenerateCourseError() {
    await this.page.route('**/api/generate-course', async route => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify(testData.course.error) });
    });
  }

  async clickGenerateCourse() {
    await this.page.getByRole('button', { name: /generate course|tạo bài học/i }).click();
  }

  async getLoadingSpinner() {
    return this.page.locator('[role="progressbar"], .loading-spinner, .animate-spin');
  }

  async getModules() {
    return this.page.locator('.module, [data-testid="module"]');
  }

  async getKeyPoints() {
    return this.page.locator('text=Key Points').first();
  }

  async getCitationMarker(index: number = 1) {
    return this.page.locator(`text=[${index}]`).first();
  }

  async getCitationTooltip() {
    return this.page.locator('[role="tooltip"], .citation-tooltip, .citation-popup');
  }

  async clickModuleByTitle(title: string) {
    await this.page.getByText(title).click();
  }

  async getCourseError() {
    return this.page.locator('text=Không thể tạo bài học');
  }

  async getRetryButton() {
    return this.page.getByRole('button', { name: /retry|thử lại/i });
  }
}