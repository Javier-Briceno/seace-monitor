import { firefox } from 'playwright';
import fs from 'fs';

export async function launchBrowser() {
  // Firefox uses a different TLS fingerprint that SEACE doesn't block, unlike Chromium.
  const browser = await firefox.launch({
    headless: true
  });
  return browser;
}

export async function createPage(browser) {
  // Firefox + userAgent/locale/timezone from Peru to avoid anti-bot detection.
  // Inconsistencies between these values often raise alerts in SEACE. 
  const context = await browser.newContext({
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    locale: "es-PE",
    timezoneId: "America/Lima",
    ignoreHTTPSErrors: true,
    acceptDownloads: true
  });
  const page = await context.newPage();
  return page;
}

export async function closeBrowser(browser) {
  try {
    if (browser) await browser.close();
  } catch (e) {
    console.error("[browser] Error closing browser:", e.message);
  }
}

export async function captureDebugInfo(browser) {
  const run_id = new Date().toISOString();
  const debugDir = "debug";
  let screenshotPath = null;
  let htmlPath = null;
  try {
    if (!fs.existsSync(debugDir)) {
      fs.mkdirSync(debugDir, { recursive: true })
    }
    // ':' is not allowed in Windows filenames, so replace with '-'
    const safeId = run_id.replace(/:/g, '-');
    screenshotPath = `${debugDir}/${safeId}.png`;
    htmlPath = `${debugDir}/${safeId}.html`;

    const contexts = browser?.contexts() || [];
    const page = contexts[0]?.pages()[0];

    if (page && !page.isClosed()) {
      await page.screenshot({ path: screenshotPath, fullPage: true});
      console.log("[browser] Debug screenshot:", screenshotPath);

      const html = await page.content();
      await fs.promises.writeFile(htmlPath, html, "utf8");
      console.log("[browser] Debug html:", htmlPath);
    }
  } catch (e) {
    console.error("[browser] Error capturing debug info:", e.message);
  }

  return { screenshotPath, htmlPath };
}

// import { firefox } from "playwright";
// import { startLocalProxy, stopLocalProxy } from "./proxy.js";
// import fs from "fs";

// let proxyServer = null;

// export async function launchBrowser() {
//   // Start local HTTP CONNECT proxy BEFORE Firefox.
//   // Firefox's network stack also bypasses VPN routing in Docker,
//   // but unlike Chromium, Firefox accepts proxy at context level
//   // and uses a different TLS fingerprint that SEACE doesn't block.
//   proxyServer = await startLocalProxy(1080);

//   const browser = await firefox.launch({
//     headless: true,
//   });

//   return browser;
// }

// export async function createPage(browser) {
//   const context = await browser.newContext({
//     ignoreHTTPSErrors: true,
//     proxy: { server: "http://127.0.0.1:1080" },
//     userAgent:
//       "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
//     locale: "es-PE",
//     timezoneId: "America/Lima"
//   });

//   const page = await context.newPage();
//   return page;
// }

// export async function closeBrowser(browser) {
//   try {
//     if (browser) await browser.close();
//   } catch (e) {
//     console.error("[browser] Error closing browser:", e.message);
//   }

//   await stopLocalProxy(proxyServer);
//   proxyServer = null;
// }

// export async function captureDebugInfo(browser, run_id) {
//   const debugDir = "debug";
//   let screenshotPath = null;
//   let htmlPath = null;

//   try {
//     if (!fs.existsSync(debugDir)) {
//       fs.mkdirSync(debugDir, { recursive: true });
//     }

//     const safeId = run_id.replace(/:/g, "-");
//     screenshotPath = `${debugDir}/${safeId}.png`;
//     htmlPath = `${debugDir}/${safeId}.html`;

//     const contexts = browser?.contexts() || [];
//     const page = contexts[0]?.pages()[0];

//     if (page && !page.isClosed()) {
//       await page.screenshot({ path: screenshotPath, fullPage: true });
//       console.log(`[browser] Debug screenshot: ${screenshotPath}`);

//       const html = await page.content();
//       await fs.promises.writeFile(htmlPath, html, "utf8");
//       console.log(`[browser] Debug HTML: ${htmlPath}`);
//     }
//   } catch (e) {
//     console.error("[browser] Error capturing debug info:", e.message);
//   }

//   return { screenshotPath, htmlPath };
// }