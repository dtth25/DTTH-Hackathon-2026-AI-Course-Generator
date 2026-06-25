import { Page } from '@playwright/test';
import testData from '../fixtures/test-data.json';

export class QuizPage {
  constructor(private page: Page) {}

  async navigate() {
    await this.page.goto('/quiz');
  }

  async mockGenerateQuiz() {
    await this.page.route('**/api/generate-quiz', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(testData.quiz.success) });
    });
  }

  async clickGenerateQuiz() {
    await this.page.getByRole('button', { name: /generate quiz|tạo quiz/i }).click();
  }

  async getQuestion() {
    return this.page.locator('.question-text, [data-testid="question"]');
  }

  async getQuestionNumber() {
    return this.page.locator('text=/Câu \\d+\\/\\d+/i');
  }

  async getAnswerOptions() {
    return this.page.locator('[role="radio"], .answer-option, [data-testid="answer-option"]');
  }

  async selectAnswer(index: number) {
    const options = await this.getAnswerOptions().all();
    if (options[index]) await options[index].click();
  }

  async getCorrectAnswer() {
    return this.page.locator('.correct-answer, [data-testid="correct-answer"]');
  }

  async getWrongAnswer() {
    return this.page.locator('.wrong-answer, [data-testid="wrong-answer"]');
  }

  async getExplanation() {
    return this.page.locator('text=/Giải thích|Explanation/i');
  }

  async getCitation() {
    return this.page.locator('text=/Nguồn:|Trang \\d+/i');
  }

  async clickNext() {
    await this.page.getByRole('button', { name: /next|tiếp theo/i }).click();
  }

  async clickSkip() {
    await this.page.getByRole('button', { name: /skip|bỏ qua/i }).click();
  }

  async getProgress() {
    return this.page.locator('[role="progressbar"], .progress-bar');
  }

  async getScore() {
    return this.page.locator('text=/Score|Kết quả|\\d+\\/\\d+/i').first();
  }

  async getReviewButton() {
    return this.page.getByRole('button', { name: /review|xem lại/i });
  }
}