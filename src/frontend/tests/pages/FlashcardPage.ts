import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class FlashcardPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/flashcards');
  }

  async mockGenerateFlashcards() {
    await this.page.route('**/api/generate-flashcards', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.flashcards.success) });
    });
  }

  async clickGenerateFlashcards() {
    await this.page.getByRole('button', { name: /generate flashcards|tạo flashcard/i }).click();
  }

  async getCardFront() {
    return this.page.locator('.card-front, [data-testid="card-front"]');
  }

  async flipCard() {
    await this.page.getByRole('button', { name: /flip|lật/i }).click();
  }

  async getCardBack() {
    return this.page.locator('.card-back, [data-testid="card-back"]');
  }

  async clickMemoryButton(name: 'Again' | 'Hard' | 'Good' | 'Easy') {
    await this.page.getByRole('button', { name: new RegExp(name, 'i') }).click();
  }

  async getProgress() {
    return this.page.locator('.progress-bar, [role="progressbar"]');
  }

  async getProgressText() {
    return this.page.locator('text=/Card \\d+\\/\\d+|Progress/i');
  }

  async getCitation() {
    return this.page.locator('text=/Nguồn:|Trang \\d+/i');
  }

  async clickShuffle() {
    await this.page.getByRole('button', { name: /shuffle|đảo/i }).click();
  }

  async clickAutoPlay() {
    await this.page.getByRole('button', { name: /auto play|tự động/i }).click();
  }

  async getCompleteMessage() {
    return this.page.locator('text=Hoàn thành');
  }
}