import { test, expect } from '@playwright/test';
import { CustomPromptPage } from '../pages/CustomPromptPage';

test.describe('Custom Prompt Feature - TC_CUSTOM_01 to TC_CUSTOM_10', () => {

  test.beforeEach(async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.mockCustomPromptSuccess();
    await customPromptPage.navigate();
  });

  test('TC_CUSTOM_01: Prompt input focus hiển thị cursor @P0', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.clickPromptInput();
    await expect(page.locator('textarea:focus, [contenteditable="true"]:focus')).toBeVisible({ timeout: 3000 });
  });

  test('TC_CUSTOM_02: Submit prompt nhận response @P0', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.enterPrompt('Phân tích nội dung chính của tài liệu');
    await customPromptPage.submitPrompt();
    await expect(customPromptPage.getResponse()).toBeVisible({ timeout: 10000 });
  });

  test('TC_CUSTOM_03: Citation markers trong response @P0', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.enterPrompt('Phân tích nội dung chính');
    await customPromptPage.submitPrompt();
    await expect(customPromptPage.getCitation()).toBeVisible({ timeout: 10000 });
  });

  test('TC_CUSTOM_04: Empty prompt báo lỗi @P1', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.submitPrompt();
    await expect(customPromptPage.getError()).toBeVisible({ timeout: 5000 });
  });

  test('TC_CUSTOM_05: Long prompt hiển thị char counter @P1', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.enterPrompt('A'.repeat(100));
    await expect(customPromptPage.getCharCounter()).toBeVisible({ timeout: 3000 });
  });

  test('TC_CUSTOM_06: Chat history hiển thị sau nhiều câu @P1', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.enterPrompt('Câu hỏi đầu tiên');
    await customPromptPage.submitPrompt();
    await page.waitForTimeout(1000);

    await expect(customPromptPage.getChatHistory()).toBeVisible({ timeout: 5000 });
  });

  test('TC_CUSTOM_07: Clear history xóa toàn bộ chat @P1', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.enterPrompt('Test');
    await customPromptPage.submitPrompt();
    await page.waitForTimeout(1000);

    await customPromptPage.clearHistory();
    if (await page.locator('text=Bạn có chắc').isVisible({ timeout: 2000 }).catch(() => false)) {
      await customPromptPage.confirmClear();
    }

    await expect(customPromptPage.getChatHistory()).not.toBeVisible({ timeout: 3000 });
  });

  test('TC_CUSTOM_08: Click suggestion tự động điền prompt @P2', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.clickSuggestion(0);
    await page.waitForTimeout(500);
    // Check textarea has content after clicking suggestion
    const textareaValue = await page.locator('textarea').inputValue().catch(() => '');
    expect(textareaValue.length).toBeGreaterThan(0);
  });

  test('TC_CUSTOM_10: Error handling khi backend fail @P1', async ({ page }) => {
    const customPromptPage = new CustomPromptPage(page);
    await customPromptPage.mockCustomPromptError();
    await customPromptPage.enterPrompt('Test error');
    await customPromptPage.submitPrompt();
    await expect(customPromptPage.getError()).toBeVisible({ timeout: 10000 });
  });
});