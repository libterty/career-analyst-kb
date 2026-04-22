/**
 * E2E: Resume query flow
 *
 * Preconditions: full Docker stack running (make up), env vars set:
 *   E2E_USERNAME, E2E_PASSWORD, BASE_URL (default http://localhost)
 */
import { test, expect } from '@playwright/test';

const USERNAME = process.env.E2E_USERNAME ?? 'admin';
const PASSWORD = process.env.E2E_PASSWORD ?? 'admin';

test.describe('Resume query flow', () => {
  test('can login and ask a resume question', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('職涯 AI');

    // Open login modal
    await page.click('#login-btn');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('button:has-text("登入")');

    // Wait for sidebar to show session list
    await expect(page.locator('#faq-section')).toBeVisible({ timeout: 10_000 });

    // Select resume topic
    await page.selectOption('#topic-select', 'resume');

    // Ask a resume question
    await page.fill('#question-input', '如何寫一份吸引人的履歷？');
    await page.click('#send-btn');

    // Wait for bot reply
    const botReply = page.locator('.msg-bot').last();
    await expect(botReply).not.toBeEmpty({ timeout: 60_000 });

    // Expect at least some text content
    const replyText = await botReply.textContent();
    expect(replyText!.length).toBeGreaterThan(20);

    // Sources panel should appear (if KB has resume videos)
    // It's optional — skip assertion if no sources
  });

  test('sources panel shows YouTube links after resume answer', async ({ page }) => {
    await page.goto('/');
    await page.click('#login-btn');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('button:has-text("登入")');
    await expect(page.locator('#faq-section')).toBeVisible({ timeout: 10_000 });

    await page.selectOption('#topic-select', 'resume');
    await page.fill('#question-input', '履歷上應該放什麼技能？');
    await page.click('#send-btn');

    // Wait for [DONE] to trigger source attachment
    const sourcesPanel = page.locator('.sources-panel').first();
    await sourcesPanel.waitFor({ state: 'attached', timeout: 60_000 });

    const links = sourcesPanel.locator('a.source-link');
    const count = await links.count();
    expect(count).toBeGreaterThan(0);

    // Each link should point to YouTube
    const href = await links.first().getAttribute('href');
    expect(href).toMatch(/youtube\.com|youtu\.be/);
  });
});
