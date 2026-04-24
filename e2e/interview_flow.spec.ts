/**
 * E2E: Interview query flow
 *
 * Preconditions: full Docker stack running (make up), env vars set:
 *   E2E_USERNAME, E2E_PASSWORD, BASE_URL (default http://localhost)
 */
import { test, expect, Page } from "@playwright/test";

const USERNAME = process.env.E2E_USERNAME ?? "admin";
const PASSWORD = process.env.E2E_PASSWORD ?? "admin";

async function login(page: Page) {
  await page.goto("/");
  await page.click("#login-btn");
  await page.fill("#username", USERNAME);
  await page.fill("#password", PASSWORD);
  await page.click("#login-submit-btn");
  await expect(page.locator("#faq-section")).toBeVisible({ timeout: 10_000 });
}

test.describe("Interview query flow", () => {
  test("can ask an interview question with topic filter", async ({ page }) => {
    await login(page);

    // Select interview topic
    await page.selectOption("#topic-select", "interview");

    await page.fill("#question-input", "面試前應該如何準備 STAR 結構回答？");
    await page.click("#send-btn");

    // Wait for streaming to complete (send-btn re-enabled in finally block)
    await expect(page.locator("#send-btn")).toBeEnabled({ timeout: 90_000 });

    const botReply = page.locator(".msg-bot").last();
    const replyText = await botReply.textContent();
    expect(replyText!.length).toBeGreaterThan(20);
  });

  test("topic dropdown filters results to interview topic", async ({
    page,
  }) => {
    await login(page);

    // Verify dropdown has interview option
    const dropdown = page.locator("#topic-select");
    await expect(dropdown).toBeVisible();
    const options = await dropdown.locator("option").allTextContents();
    expect(options).toContain("🎤 面試");

    await page.selectOption("#topic-select", "interview");
    await page.fill("#question-input", "被問到薪資期望怎麼回答？");
    await page.click("#send-btn");

    // Wait for sources panel — interview videos should appear
    const sourcesPanel = page.locator(".sources-panel").first();
    await sourcesPanel.waitFor({ state: "attached", timeout: 90_000 });
    expect(await sourcesPanel.locator("a.source-link").count()).toBeGreaterThan(
      0,
    );
  });

  test("new session button resets chat", async ({ page }) => {
    await login(page);

    // Send one message
    await page.fill("#question-input", "面試緊張怎麼辦？");
    await page.click("#send-btn");

    // Wait for streaming to finish before creating new session
    await expect(page.locator("#send-btn")).toBeEnabled({ timeout: 90_000 });

    // Open new session
    await page.click("#newChatBtn");

    // Wait for clearChat to run (async fetch + clearChat)
    await expect(page.locator(".msg-bot")).toHaveCount(1, { timeout: 10_000 });
  });
});
