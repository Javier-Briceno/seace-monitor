import { extractFicha } from "./ficha.js";

const RESULTS_TBODY = 'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]';

/**
 * Iterates through ALL pages of results.
 * For each row: extracts basic data + navigates into ficha tecnica.
 * Returns flat array of all items across all pages.
 */
export async function scrapeAllPages(page, run_id) {
  const allItems = [];
  let currentPage = 1;
  let hasMorePages = true;

  while (hasMorePages) {
    console.log(`[${run_id}] Scraping page ${currentPage}...`);

    const pageItems = await scrapePage(page, run_id, currentPage);
    allItems.push(...pageItems);

    const isLastPage = await checkIfLastPage(page);

    if (isLastPage) {
      console.log(`[${run_id}] Last page reached. Total pages: ${currentPage}`);
      hasMorePages = false;
    } else {
      await goToNextPage(page, run_id, currentPage);
      currentPage++;
    }
  }

  console.log(`[${run_id}] ✓ Scraping complete. Total items: ${allItems.length}`);
  return allItems;
}

// ─── Private helpers ──────────────────────────────────────────────────────────

/**
 * Scrapes all rows on the current page.
 * For each row, also fetches the ficha tecnica.
 */
async function scrapePage(page, run_id, pageNumber) {
  const items = [];

  const rowCount = await page.evaluate((selector) => {
    const tbody = document.querySelector(selector);
    if (!tbody) return 0;
    return tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)").length;
  }, RESULTS_TBODY);

  console.log(`[${run_id}] Page ${pageNumber}: ${rowCount} rows found`);

  for (let i = 0; i < rowCount; i++) {
    console.log(`[${run_id}] Processing item ${i + 1}/${rowCount} (page ${pageNumber})...`);

    // Extract basic data from the table row
    const basicData = await extractBasicData(page, i);

    if (!basicData) {
      console.log(`[${run_id}] ⚠ Could not extract item ${i + 1}, skipping`);
      continue;
    }

    // Navigate into ficha tecnica and extract detailed data
    const fichaData = await extractFicha(page, i, run_id);

    items.push({ ...basicData, ficha: fichaData });
  }

  return items;
}

/**
 * Extracts the basic columns from a result row (no navigation needed).
 */
async function extractBasicData(page, rowIndex) {
  return await page.evaluate(
    ({ selector, index }) => {
      const tbody = document.querySelector(selector);
      if (!tbody) return null;

      const rows = tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      const row = rows[index];
      if (!row) return null;

      const cols = row.querySelectorAll("td");

      return {
        numero:             cols[0]?.innerText?.trim() || "",
        entidad:            cols[1]?.innerText?.trim() || "",
        fecha_publicacion:  cols[2]?.innerText?.trim() || "",
        nomenclatura:       cols[3]?.innerText?.trim() || "",
        reiniciado_desde:   cols[4]?.innerText?.trim() || "",
        objeto:             cols[5]?.innerText?.trim() || "",
        descripcion:        cols[6]?.innerText?.trim() || ""
      };
    },
    { selector: RESULTS_TBODY, index: rowIndex }
  );
}

/**
 * Returns true if the "next page" paginator button is disabled.
 */
async function checkIfLastPage(page) {
  return await page.evaluate(() => {
    const nextBtn = document.querySelector(
      "#tbBuscador\\:idFormBuscarProceso\\:dtProcesos_paginator_bottom .ui-paginator-next"
    );
    return nextBtn ? nextBtn.classList.contains("ui-state-disabled") : true;
  });
}

/**
 * Clicks the next page button and waits for the table to reload.
 */
async function goToNextPage(page, run_id, currentPage) {
  console.log(`[${run_id}] Going to page ${currentPage + 1}...`);

  await page.evaluate(() => {
    const nextBtn = document.querySelector(
      "#tbBuscador\\:idFormBuscarProceso\\:dtProcesos_paginator_bottom .ui-paginator-next"
    );
    if (nextBtn) nextBtn.click();
  });

  await page.waitForTimeout(1500 + Math.random() * 1000);

  // Wait for new rows to appear
  await page.waitForFunction(
    (selector) => {
      const tbody = document.querySelector(selector);
      if (!tbody) return false;
      return tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)").length > 0;
    },
    { timeout: 10000 },
    RESULTS_TBODY
  );

  console.log(`[${run_id}] ✓ Page ${currentPage + 1} loaded`);
}