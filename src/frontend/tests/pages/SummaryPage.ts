import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class SummaryPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/generate');
  }

  async mockGenerateSummary(type: 'short' | 'medium' | 'detailed') {
    const mockData = testData.summary[type];
    await this.page.route('**/api/generate-summary', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockData) });
    });
  }

  async mockSummaryError() {
    await this.page.route('**/api/generate-summary', async route => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Lỗi tạo tóm tắt' }) });
    });
  }

  async clickGenerateSummary() {
    await this.page.getByRole('button', { name: /generate summary|tạo tóm tắt/i }).click();
  }

  async selectLength(length: 'short' | 'medium' | 'detailed') {
    const labelMap = { short: /ngắn|short/i, medium: /trung bình|medium/i, detailed: /chi tiết|detailed/i };
    await this.page.getByRole('radio', { name: labelMap[length] }).click();
  }

  async getSummaryText() {
    return this.page.locator('.summary-content, [data-testid="summary"]');
  }

  async getCitation() {
    return this.page.locator('text=/\[Trang \\d+\]|citation|Nguồn/i');
  }

  async clickRegenerate() {
    await this.page.getByRole('button', { name: /regenerate|tạo lại/i }).click();
  }

  async clickCopy() {
    await this.page.getByRole('button', { name: /copy|sao chép/i }).click();
  }

  async getCopyToast() {
    return this.page.locator('text=Đã copy');
  }

  async clickDownload() {
    await this.page.getByRole('button', { name: /download|tải xuống/i }).click();
  }

  async getError() {
    return this.page.locator('text=/Lỗi|thử lại/i');
  }
}