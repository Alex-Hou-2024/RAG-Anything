const { chromium } = require("playwright");
const fs = require("fs");

const deployUrl = fs.readFileSync("/workspace/.deploy_url", "utf8").trim();

async function main() {
  if (!deployUrl) {
    console.log("UI_VERIFY: FAIL | /workspace/.deploy_url empty");
    return;
  }

  const failures = [];
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console error: ${message.text()}`);
  });
  page.on("pageerror", (error) => failures.push(`page error: ${error.message}`));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failures.push(`network ${response.status()}: ${response.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    failures.push(`failed request: ${request.url()} (${request.failure()?.errorText || "unknown"})`);
  });

  try {
    const response = await page.goto(deployUrl, { waitUntil: "networkidle", timeout: 30000 });
    if (!response || response.status() >= 400) failures.push(`root response ${response?.status() || "missing"}`);
    await page.waitForSelector(".app-shell", { timeout: 15000 });

    const initial = await page.evaluate(() => ({
      title: document.title,
      text: document.body.innerText.trim(),
      appShell: Boolean(document.querySelector(".app-shell")),
      links: [...document.querySelectorAll("nav a")].map((link) => ({ href: link.getAttribute("href"), text: link.textContent.trim() })),
      hasAuthControls: Boolean(document.querySelector('[href*="auth"], [data-auth], button[name="logout"], button[name="login"]')),
      hasLogoutText: /logout|sign out|退出登录/i.test(document.body.innerText),
      style: (() => {
        const shell = document.querySelector(".app-shell");
        const computed = shell ? getComputedStyle(shell) : null;
        return computed ? { display: computed.display, background: computed.backgroundColor, font: computed.fontFamily } : null;
      })(),
    }));

    if (!initial.appShell || initial.text.length < 80) failures.push("page lacks meaningful rendered application content");
    if (!initial.style || initial.style.display === "inline" || initial.style.font === "") failures.push("CSS appears not applied");
    if (!initial.links.some((link) => link.href === "/documents") || !initial.links.some((link) => link.href === "/chat")) {
      failures.push("main navigation links missing");
    }
    if (initial.hasLogoutText && !initial.hasAuthControls) failures.push("incoherent unauthenticated logout UI");

    await page.locator('nav a[href="/chat"]').click();
    await page.waitForURL(/\/chat$/, { timeout: 10000 });
    await page.waitForSelector(".chat-form", { timeout: 10000 });
    const chatText = await page.locator("body").innerText();
    if (!/对话问答|检索问答/.test(chatText)) failures.push("chat navigation did not render chat content");

    await page.locator('nav a[href="/documents"]').click();
    await page.waitForURL(/\/documents$/, { timeout: 10000 });
    await page.waitForSelector(".page--documents", { timeout: 10000 });
    await page.screenshot({ path: "/workspace/verify-screenshot.png", fullPage: true });
  } catch (error) {
    failures.push(`browser verification exception: ${error.message}`);
  } finally {
    await browser.close();
  }

  const uniqueFailures = [...new Set(failures)];
  console.log(uniqueFailures.length ? `UI_VERIFY: FAIL | ${uniqueFailures.join(" | ")}` : "UI_VERIFY: PASS");
}

main().catch((error) => console.log(`UI_VERIFY: FAIL | script exception: ${error.message}`));
