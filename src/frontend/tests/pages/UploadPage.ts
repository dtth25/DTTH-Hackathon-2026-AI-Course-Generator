import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class UploadPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/');
  }

  async uploadFile(filePath: string) {
    const fileInput = this.page.locator('input[type="file"]');
    await fileInput.setInputFiles(filePath);
    await this.page.getByRole('button', { name: /upload|tải lên/i }).click();
  }

  async mockUploadSuccess() {
    await this.page.route('**/api/upload', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(testData.upload.success),
      });
    });
  }

  async mockUploadError(format: 'invalid' | 'empty' | 'exists') {
    const errorMap = {
      invalid: { status: 422, data: testData.upload.error_invalid_format },
      empty: { status: 422, data: testData.upload.error_empty },
      exists: { status: 409, data: testData.upload.file_exists },
    };
    const { status, data } = errorMap[format];
    await this.page.route('**/api/upload', async route => {
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
  }

  async getSuccessMessage() {
    return this.page.locator('text=Upload thành công');
  }

  async getErrorMessage() {
    return this.page.locator('[role="alert"], .error-message, .toast-error');
  }

  async getFileList() {
    return this.page.locator('.file-list, [data-testid="file-list"]');
  }
}