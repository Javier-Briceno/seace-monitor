import { chromium } from "playwright";
import fs from "fs";

const PROXY_SERVER = process.env.PROXY_SERVER || null;
const PROXY_USER   = process.env.PROXY_USER   || null;
const PROXY_PASS   = process.env.PROXY_PASS   || null;

/**
 * Launches a Playwright Chromium browser.
 * Automatically configures proxy if PROXY_SERVER is set in env.
 */
export async function launchBrowser() {
  const options = { headless: true };

  if (PROXY_SERVER) {
    options.proxy = {
      server: PROXY_SERVER,
      ...(PROXY_USER && { username: PROXY_USER }),
      ...(PROXY_PASS && { password: PROXY_PASS })
    };
    console.log(`[browser] Using proxy: ${PROXY_SERVER}`);
  }

  return await chromium.launch(options);
}

/**
 * Safely closes the browser if it's still open.
 */
export async function closeBrowser(browser) {
  if (browser) {
    try {
      await browser.close();
    } catch (e) {
      console.error("[browser] Error closing browser:", e.message);
    }
  }
}

/**
 * On error: captures a screenshot and HTML dump for debugging.
 * Saves to /debug directory with the run_id as filename.
 */
export async function captureDebugInfo(browser, run_id) {
  const safeId = run_id.replace(/:/g, "-");
  const screenshotPath = `debug/${safeId}.png`;
  const htmlPath = `debug/${safeId}.html`;

  try {
    if (!fs.existsSync("debug")) {
      fs.mkdirSync("debug", { recursive: true });
    }

    if (browser) {
      const pages = browser.contexts()[0]?.pages() || [];
      const page = pages[0];

      if (page && !page.isClosed()) {
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.log(`[browser] Debug screenshot: ${screenshotPath}`);

        const html = await page.content();
        await fs.promises.writeFile(htmlPath, html, "utf8");
        console.log(`[browser] Debug HTML: ${htmlPath}`);
      }
    }
  } catch (e) {
    console.error("[browser] Could not capture debug info:", e.message);
  }

  return { screenshot: screenshotPath, html: htmlPath };
}