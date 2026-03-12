import { extractFicha } from "./ficha.js";
import { log } from './logger.js';

const RESULTS_TBODY = 'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]';

/** Scrape all paginated results and return a flat array of items. */
export async function scrapeAllPages(page) {
  const allItems = [];
  let currentPage = 1;
  let hasMorePages = true;

  while (hasMorePages) {
    log(`Scraping page ${currentPage}...`);

    const pageItems = await scrapePage(page, currentPage);
    allItems.push(...pageItems);

    const isLastPage = await checkIfLastPage(page);

    if (isLastPage) {
      log(`Last page reached. Total pages: ${currentPage}`);
      hasMorePages = false;
    } else {
      await goToNextPage(page, currentPage);
      currentPage++;
    }
  }

  log(`Scraping complete. Total items: ${allItems.length}`);
  return allItems;
}

// Private helpers

/** Scrape every row in the current page, including ficha details. */
async function scrapePage(page, pageNumber) {
  const items = [];

  const rowCount = await page.evaluate((selector) => {
    const tbody = document.querySelector(selector);
    if (!tbody) return 0;
    return tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)").length;
  }, RESULTS_TBODY);

  log(`Page ${pageNumber}: ${rowCount} rows found`);

  for (let i = 0; i < rowCount; i++) {
    log(`Processing item ${i + 1}/${rowCount} (page ${pageNumber})...`);

    const basicData = await extractBasicData(page, i);

    if (!basicData) {
      log(`Could not extract item ${i + 1}, skipping`);
      continue;
    }

    const fichaData = await extractFicha(page, i);

    items.push({ ...basicData, ficha: fichaData });
  }

  return items;
}

/** Extract base columns from one result row without page navigation. */
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
        objeto_de_contratacion: cols[5]?.innerText?.trim() || "",
        descripcion:        cols[6]?.innerText?.trim() || "",
        codigo_snip: cols[7]?.innerText?.trim() || "",
        codigo_cui: cols[8]?.innerText?.trim() || "",
        monto: cols[9]?.innerText?.trim() || "",
        moneda: cols[10]?.innerText?.trim() || "",
        version_seace: cols[11]?.innerText?.trim() || ""
      };
    },
    { selector: RESULTS_TBODY, index: rowIndex }
  );
}

/** Return true when the paginator "next" button is disabled. */
async function checkIfLastPage(page) {
  return await page.evaluate(() => {
    const paginatorId = "tbBuscador:idFormBuscarProceso:dtProcesos";
    const paginatorEl = "widget_" + paginatorId.replace(/:/g, '_');
    const paginator = window[paginatorEl];
    if (!paginator) throw new Error('DataTable paginator widget not found')
    return paginator.getPaginator().nextLink[0].classList.contains('ui-state-disabled');
  });
}

/** Click paginator next and wait until the PrimeFaces AJAX queue is empty. */
async function goToNextPage(page, currentPage) {
  log(`Going to page ${currentPage + 1}...`);

  await page.evaluate(() => {
    const paginatorId = "tbBuscador:idFormBuscarProceso:dtProcesos";
    const paginatorEl = "widget_" + paginatorId.replace(/:/g, '_');
    const paginator = window[paginatorEl];
    if (!paginator) throw new Error('DataTable paginator widget not found');
    paginator.getPaginator().nextLink.click();
  })

  await page.waitForFunction(() =>
    window.PrimeFaces?.ajax?.Queue?.isEmpty?.() === true,
  {timeout: 45000});

  log(`Page ${currentPage + 1} loaded`);
}
