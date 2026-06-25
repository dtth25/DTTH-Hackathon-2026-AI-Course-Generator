import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class CustomPromptPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/generate');
  }

  async mockCustomPromptSuccess() {
    await this.page.route('**/api/custom-prompt', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.custom_prompt.success) });
    });
  }

  async mockCustomPromptError() {
    await this.page.route('**/api/custom-prompt', async route => {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Không thể xử lý. Vui lòng thử lại' }) });
    });
  }

  async clickPromptInput() {
    await this.page.locator('textarea, [contenteditable="true"]').first().click();
  }

  async enterPrompt(text: string) {
    await this.page.locator('textarea, [contenteditable="true"]').first().fill(text);
  }

  async submitPrompt() {
    await this.page.getByRole('button', { name: /gửi|submit|send/i }).click();
  }

  async getResponse() {
    return this.page.locator('.chat-response, [data-testid="ai-response"], .message-bubble');
  }

  async getCitation() {
    return this.page.locator('text=/\\[\\d+\\]|citation|Nguồn/i');
  }

  async getChatHistory() {
    return this.page.locator('.chat-history, [data-testid="chat-history"]');
  }

  async clearHistory() {
    await this.page.getByRole('button', { name: /xóa lịch sử|clear/i }).click();
  }

  async confirmClear() {
    await this.page.getByRole('button', { name: /có|confirm|đồng ý/i }).click();
  }

  async getError() {
    return this.page.locator('text=/Không thể xử lý|Vui lòng thử lại/i');
  }

  async getCharCounter() {
    return this.page.locator('text=/\\d+\\/\\d+/i');
  }

  async clickSuggestion(index: number) {
    const suggestions = await this.page.locator('.suggestion, [data-testid="suggestion"]').all();
    if (suggestions[index]) await suggestions[index].click();
  }
}