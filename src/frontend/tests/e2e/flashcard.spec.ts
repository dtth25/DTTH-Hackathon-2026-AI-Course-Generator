import { test, expect } from '@playwright/test';
import { FlashcardPage } from '../pages/FlashcardPage';

test.describe('Flashcard Feature - TC_FLASHCARD_01 to TC_FLASHCARD_13', () => {

  test.beforeEach(async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.mockGenerateFlashcards();
    await flashcardPage.navigate();
    await flashcardPage.clickGenerateFlashcards();
    await page.waitForTimeout(1000);
  });

  test('TC_FLASHCARD_01: Generate Flashcards thành công @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await expect(flashcardPage.getCardFront()).toBeVisible({ timeout: 10000 });
  });

  test('TC_FLASHCARD_02: Hiển thị mặt trước flashcard @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    const front = await flashcardPage.getCardFront();
    await expect(front).toContainText('Câu hỏi', { timeout: 5000 });
  });

  test('TC_FLASHCARD_03: Flip card hiển thị mặt sau @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await expect(flashcardPage.getCardBack()).toBeVisible({ timeout: 5000 });
  });

  test('TC_FLASHCARD_04: Memory State - Again (Chưa nhớ) @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await flashcardPage.clickMemoryButton('Again');
    await expect(flashcardPage.getProgress()).toBeVisible({ timeout: 3000 });
  });

  test('TC_FLASHCARD_05: Memory State - Hard (Nhớ một phần) @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await flashcardPage.clickMemoryButton('Hard');
    await expect(flashcardPage.getProgress()).toBeVisible({ timeout: 3000 });
  });

  test('TC_FLASHCARD_06: Memory State - Good (Đã nhớ) @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await flashcardPage.clickMemoryButton('Good');
    await expect(flashcardPage.getProgress()).toBeVisible({ timeout: 3000 });
  });

  test('TC_FLASHCARD_07: Memory State - Easy (Đã nhớ kỹ) @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await flashcardPage.clickMemoryButton('Easy');
    await expect(flashcardPage.getProgress()).toBeVisible({ timeout: 3000 });
  });

  test('TC_FLASHCARD_08: Navigation Next sau khi đánh giá @P1', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await flashcardPage.clickMemoryButton('Good');
    await expect(page.locator('text=Câu hỏi 2')).toBeVisible({ timeout: 5000 });
  });

  test('TC_FLASHCARD_11: Citation hiển thị ở mặt sau @P0', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.flipCard();
    await expect(flashcardPage.getCitation()).toBeVisible({ timeout: 5000 });
  });

  test('TC_FLASHCARD_12: Shuffle cards @P2', async ({ page }) => {
    const flashcardPage = new FlashcardPage(page);
    await flashcardPage.clickShuffle();
    await expect(flashcardPage.getCardFront()).toBeVisible({ timeout: 3000 });
  });
});