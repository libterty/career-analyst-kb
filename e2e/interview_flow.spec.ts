/**
 * E2E: Interview query flow
 *
 * Preconditions: full Docker stack running (make up), env vars set:
 *   E2E_USERNAME, E2E_PASSWORD, BASE_URL (default http://localhost)
 */
import { test, expect } from '@playwright/test';

const USERNAME = process.env.E2E_USERNAME ?? 'admin';
const PASSWORD = process.env.E2E_PASSWORD ?? 'admin';

test.describe('Interview query flow', () => {
  test('can ask an interview question with topic filter', async ({ page }) => {
    await page.goto('/');
    await page.click('#login-btn');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('button:has-text("登入")');
    await expect(page.locator('#faq-section')).toBeVisible({ timeout: 10_000 });

    // Select interview topic
    await page.selectOption('#topic-select', 'interview');

    await page.fill('#question-input', '面試前應該如何準備 STAR 結構回答？');
    await page.click('#send-btn');

    const botReply = page.locator('.msg-bot').last();
    await expect(botReply).not.toBeEmpty({ timeout: 60_000 });

    const replyText = await botReply.textContent();
    expect(replyText!.length).toBeGreaterThan(20);
  });

  test('topic dropdown filters results to interview topic', async ({ page }) => {
    await page.goto('/');
    await page.click('#login-btn');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('button:has-text("登入")');
    await expect(page.locator('#faq-section')).toBeVisible({ timeout: 10_000 });

    // Verify dropdown has interview option
    const dropdown = page.locator('#topic-select');
    await expect(dropdown).toBeVisible();
    const options = await dropdown.locator('option').allTextContents();
    expect(options).toContain('🎤 面試');

    await page.selectOption('#topic-select', 'interview');
    await page.fill('#question-input', '被問到薪資期望怎麼回答？');
    await page.click('#send-btn');

    // Wait for sources panel — interview videos should appear
    const sourcesPanel = page.locator('.sources-panel').first();
    await sourcesPanel.waitFor({ state: 'attached', timeout: 60_000 });
    expect(await sourcesPanel.locator('a.source-link').count()).toBeGreaterThan(0);
  });

  test('new session button resets chat', async ({ page }) => {
    await page.goto('/');
    await page.click('#login-btn');
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('button:has-text("登入")');
    await expect(page.locator('#faq-section')).toBeVisible({ timeout: 10_000 });

    // Send one message
    await page.fill('#question-input', '面試緊張怎麼辦？');
    await page.click('#send-btn');
    await page.locator('.msg-bot').last().waitFor({ timeout: 60_000 });

    // Open new session
    await page.click('#newChatBtn');

    // Chat box should show welcome only (no previous messages)
    const msgs = await page.locator('.msg-bot').count();
    expect(msgs).toBe(1);
  });
});
