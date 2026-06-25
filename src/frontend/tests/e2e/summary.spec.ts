import { test, expect } from '@playwright/test';
import { SummaryPage } from '../pages/SummaryPage';

test.describe('Summary Feature - TC_SUMMARY_01 to TC_SUMMARY_09', () => {

  test('TC_SUMMARY_01: Generate Summary thành công @P0', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('short');
    await summaryPage.navigate();

    await summaryPage.clickGenerateSummary();
    await expect(summaryPage.getSummaryText()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SUMMARY_02: Citation trong summary @P0', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('detailed');
    await summaryPage.navigate();
    await summaryPage.clickGenerateSummary();

    await expect(summaryPage.getCitation()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SUMMARY_03: Summary độ dài Short @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('short');
    await summaryPage.navigate();
    await summaryPage.selectLength('short');
    await summaryPage.clickGenerateSummary();

    const text = await summaryPage.getSummaryText().textContent({ timeout: 10000 });
    expect(text?.length).toBeLessThan(300);
  });

  test('TC_SUMMARY_04: Summary độ dài Medium @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('medium');
    await summaryPage.navigate();
    await summaryPage.selectLength('medium');
    await summaryPage.clickGenerateSummary();

    await expect(summaryPage.getSummaryText()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SUMMARY_05: Summary độ dài Detailed @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('detailed');
    await summaryPage.navigate();
    await summaryPage.selectLength('detailed');
    await summaryPage.clickGenerateSummary();

    await expect(summaryPage.getSummaryText()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SUMMARY_06: Regenerate summary @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('short');
    await summaryPage.navigate();
    await summaryPage.clickGenerateSummary();

    await summaryPage.clickRegenerate();
    await expect(summaryPage.getSummaryText()).toBeVisible({ timeout: 10000 });
  });

  test('TC_SUMMARY_07: Copy summary @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockGenerateSummary('short');
    await summaryPage.navigate();
    await summaryPage.clickGenerateSummary();

    await summaryPage.clickCopy();
    await expect(summaryPage.getCopyToast()).toBeVisible({ timeout: 5000 });
  });

  test('TC_SUMMARY_08: Error khi backend fail @P1', async ({ page }) => {
    const summaryPage = new SummaryPage(page);
    await summaryPage.mockSummaryError();
    await summaryPage.navigate();

    await summaryPage.clickGenerateSummary();
    await expect(summaryPage.getError()).toBeVisible({ timeout: 10000 });
  });
});