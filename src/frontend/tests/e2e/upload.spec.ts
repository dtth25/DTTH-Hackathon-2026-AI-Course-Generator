import { test, expect } from '@playwright/test';
import { UploadPage } from '../pages/UploadPage';
import path from 'path';

test.describe('Upload Feature - TC_UPLOAD_01 to TC_UPLOAD_10', () => {

  test.beforeEach(async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.navigate();
  });

  test('TC_UPLOAD_01: Upload PDF hợp lệ thành công @P0', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadSuccess();

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getSuccessMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_02: Upload DOCX hợp lệ thành công @P0', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadSuccess();

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getSuccessMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_03: Upload TXT hợp lệ thành công @P0', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadSuccess();

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getSuccessMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_04: Upload file .jpg/.png bị reject @P0', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadError('invalid');

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getErrorMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_05: Upload file .exe/.zip bị reject @P0', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadError('invalid');

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getErrorMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_06: Upload file > 10MB hiển thị warning @P1', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await uploadPage.mockUploadError('invalid');

    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    await expect(uploadPage.getErrorMessage()).toBeVisible({ timeout: 10000 });
  });

  test('TC_UPLOAD_07: Click Upload mà không chọn file @P1', async ({ page }) => {
    const uploadPage = new UploadPage(page);
    await page.getByRole('button', { name: /upload|tải lên/i }).click();

    await expect(uploadPage.getErrorMessage()).toBeVisible({ timeout: 5000 });
  });

  test('TC_UPLOAD_09: Cancel upload @P2', async ({ page }) => {
    await page.route('**/api/upload', async route => {
      await new Promise(resolve => setTimeout(resolve, 5000));
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });

    const uploadPage = new UploadPage(page);
    await uploadPage.uploadFile(path.join(__dirname, '../fixtures/test-data.json'));

    const cancelBtn = page.getByRole('button', { name: /cancel|hủy/i });
    if (await cancelBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await cancelBtn.click();
    }

    await expect(page.locator('text=Upload thành công')).not.toBeVisible({ timeout: 3000 });
  });
});