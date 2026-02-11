import { Router } from "express";
import { launchBrowser, createPage, closeBrowser, captureDebugInfo } from "../scraper/browser.js";
import { navigateToSEACE, applyFilters, runSearch } from "../scraper/filters.js";
import { scrapeAllPages } from "../scraper/results.js";

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
  const run_id = new Date().toISOString();
  let browser = null;

  console.log(`\n[${run_id}] === NEW EXPORT REQUEST ===`);
  console.log(`[${run_id}] Filters:`, req.body);

  try {
    const { departamento, objeto, anio } = req.body;

    // 1. Launch browser
    browser = await launchBrowser();
    const page = await createPage(browser);

    // 2. Navigate to SEACE and activate search tab
    await navigateToSEACE(page, run_id);

    // 3. Apply filters (departamento, objeto, año)
    await applyFilters(page, { departamento, objeto, anio }, run_id);

    // 4. Run search
    await runSearch(page, run_id);

    // 5. Scrape all pages (results + ficha for each item)
    const allItems = await scrapeAllPages(page, run_id);

    await closeBrowser(browser);

    console.log(`[${run_id}] === EXPORT COMPLETE: ${allItems.length} items ===\n`);

    return res.json({
      run_id,
      total: allItems.length,
      meta: {
        fuente: "SEACE",
        scraped_at: run_id,
        filtros_aplicados: { departamento, objeto, anio }
      },
      items: allItems
    });

  } catch (err) {
    console.error(`[${run_id}] FATAL ERROR:`, err.message);

    const debugInfo = await captureDebugInfo(browser, run_id);
    await closeBrowser(browser);

    return res.status(500).json({
      run_id,
      error: err.message,
      debug: debugInfo
    });
  }
});