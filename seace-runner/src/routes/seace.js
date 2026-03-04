import { Router } from "express";
import { launchBrowser, createPage, closeBrowser, captureDebugInfo } from "../scraper/browser.js";
import { navigateToSEACE, applyFilters, runSearch } from "../scraper/filters.js";
import { scrapeAllPages } from "../scraper/results.js";
import { log } from '../scraper/logger.js';

export const seaceRouter = Router();

/**
 * POST /seace/export
 * 
 * Scrapes SEACE procurement portal and returns structured JSON data.
 * 
 * Body: {
 *   departamento?: string  - e.g. "LIMA"
 *   objeto?: string        - e.g. "Obra"
 *   anio?: string          - e.g. "2025"
 * }
 */
seaceRouter.post("/export", async (req, res) => {
  let browser = null;

  log(`=== NEW EXPORT REQUEST ===`);
  log(`Filters: ${JSON.stringify(req.body)}`);

  try {
    const { departamento, objeto, anio } = req.body;

    // 1. Launch browser
    browser = await launchBrowser();
    const page = await createPage(browser);

    // 2. Navigate to SEACE and activate search tab
    await navigateToSEACE(page);

    // 3. Apply filters (departamento, objeto, año)
    await applyFilters(page, { departamento, objeto, anio });

    // 4. Run search
    await runSearch(page);

    // 5. Scrape all pages (results + ficha for each item)
    const allItems = await scrapeAllPages(page);

    await closeBrowser(browser);

    log(`=== EXPORT COMPLETE: ${allItems.length} items ===\n`);

    return res.json({
      total: allItems.length,
      meta: {
        fuente: "SEACE",
        scraped_at: new Date().toISOString(),
        filtros_aplicados: { departamento, objeto, anio }
      },
      items: allItems
    });

  } catch (err) {
    console.error(`FATAL ERROR:`, err.message);

    const debugInfo = await captureDebugInfo(browser);
    await closeBrowser(browser);

    return res.status(500).json({
      error: err.message,
      debug: debugInfo
    });
  }
});