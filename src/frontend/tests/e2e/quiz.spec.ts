import { test, expect } from '@playwright/test';
import { QuizPage } from '../pages/QuizPage';

test.describe('Quiz Feature - TC_QUIZ_01 to TC_QUIZ_13', () => {

  test.beforeEach(async ({ page }) => {
    const quizPage = new QuizPage(page);
    await quizPage.mockGenerateQuiz();
    await quizPage.navigate();
    await quizPage.clickGenerateQuiz();
    await page.waitForTimeout(1000);
  });

  test('TC_QUIZ_01: Generate Quiz thành công @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await expect(quizPage.getQuestion()).toBeVisible({ timeout: 10000 });
  });

  test('TC_QUIZ_02: Hiển thị câu hỏi có số thứ tự @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await expect(quizPage.getQuestionNumber()).toBeVisible({ timeout: 5000 });
  });

  test('TC_QUIZ_03: Hiển thị đủ 4 đáp án @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    const options = await quizPage.getAnswerOptions();
    await expect(options).toHaveCount(4, { timeout: 5000 });
  });

  test('TC_QUIZ_05: Đáp án đúng highlight xanh + icon check @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await quizPage.selectAnswer(0);
    await expect(quizPage.getCorrectAnswer()).toBeVisible({ timeout: 5000 });
  });

  test('TC_QUIZ_07: Hiển thị phần Giải thích sau khi submit @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await quizPage.selectAnswer(0);
    await expect(quizPage.getExplanation()).toBeVisible({ timeout: 5000 });
  });

  test('TC_QUIZ_11: Citation hiển thị trong explanation @P0', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await quizPage.selectAnswer(0);
    await expect(quizPage.getCitation()).toBeVisible({ timeout: 5000 });
  });

  test('TC_QUIZ_08: Progress bar hiển thị @P1', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await expect(quizPage.getProgress()).toBeVisible({ timeout: 5000 });
  });

  test('TC_QUIZ_10: Click Next chuyển câu hỏi @P1', async ({ page }) => {
    const quizPage = new QuizPage(page);
    await quizPage.selectAnswer(0);
    await quizPage.clickNext();
    await expect(page.locator('text=Phương pháp nào')).toBeVisible({ timeout: 5000 });
  });
});