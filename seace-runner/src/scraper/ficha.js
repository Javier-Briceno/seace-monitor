const RESULTS_TBODY = 'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]';

/**
 * Clicks on the "Ficha de Selección" link for a given row,
 * extracts all data from the ficha page, then navigates back.
 *
 * Returns null if extraction fails (item is still added without ficha data).
 */
export async function extractFicha(page, rowIndex, run_id) {
  try {
    await openFicha(page, rowIndex, run_id);
    const fichaData = await parseFicha(page);
    await closeFicha(page, run_id);

    console.log(`[${run_id}] ✓ Ficha extracted for item ${rowIndex + 1}`);
    return fichaData;

  } catch (err) {
    console.error(`[${run_id}] ✗ Ficha error for item ${rowIndex + 1}:`, err.message);

    // Try to navigate back if we're stuck on the ficha page
    await tryCloseFicha(page);

    return { error: err.message };
  }
}

// ─── Private helpers ──────────────────────────────────────────────────────────

/**
 * Clicks the ficha icon for the row at rowIndex and waits for the ficha to load.
 */
async function openFicha(page, rowIndex, run_id) {
  const clickResult = await page.evaluate(
    ({ selector, index }) => {
      const tbody = document.querySelector(selector);
      const rows = tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      const row = rows[index];

      if (!row) return { success: false, reason: "row not found" };

      // Primary: click the ficha icon link
      const link = row.querySelector('a:has(img[src*="fichaSeleccion"])');
      if (link) {
        link.click();
        return { success: true, method: "ficha-icon" };
      }

      // Fallback: first commandlink in the row
      const cmdLink = row.querySelector("a.ui-commandlink");
      if (cmdLink) {
        cmdLink.click();
        return { success: true, method: "commandlink-fallback" };
      }

      return { success: false, reason: "no clickable link found" };
    },
    { selector: RESULTS_TBODY, index: rowIndex }
  );

  if (!clickResult.success) {
    throw new Error(`Could not open ficha: ${clickResult.reason}`);
  }

  console.log(`[${run_id}] Ficha click method: ${clickResult.method}`);

  // Wait for ficha form to appear in DOM
  await page.waitForFunction(
    () => document.querySelector("#tbFicha\\:idFormFichaSeleccion") !== null,
    { timeout: 10000 }
  );

  await page.waitForSelector("#tbFicha\\:idFormFichaSeleccion", { timeout: 10000 });
  await page.waitForTimeout(1500);
}

/**
 * Parses all data sections from the ficha page.
 * 
 * The ficha has 4 semi-structured sections:
 * - Información General       (key-value table)
 * - Información de la Entidad (key-value table)
 * - Información del Procedimiento (key-value table, some nested tables)
 * - Cronograma                (structured table with columns)
 */
async function parseFicha(page) {
  return await page.evaluate(() => {

    // ── Helper: parse a generic key-value table ──────────────────────────────
    function parseKeyValueTable(tableSelector) {
      const result = {};
      const table = document.querySelector(tableSelector);
      if (!table) return result;

      table.querySelectorAll("tbody tr").forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 2) return;

        const label = cells[0]?.textContent?.trim().replace(/:$/, "");
        if (!label) return;

        // Handle "Lugar y cuenta de pago" which has a nested table
        const innerTable = cells[1]?.querySelector("table");
        if (innerTable) {
          const rows = innerTable.querySelectorAll("tr");
          const banco  = rows[1]?.cells[0]?.textContent?.trim() || null;
          const cuenta = rows[1]?.cells[1]?.textContent?.trim() || null;
          result[label] = { banco, cuenta };
        } else {
          result[label] = cells[1]?.textContent?.trim() || null;
        }
      });

      return result;
    }

    // ── Helper: parse the cronograma table ───────────────────────────────────
    function parseCronograma() {
      const cronograma = [];
      const tbody = document.querySelector("#tbFicha\\:dtCronograma_data");
      if (!tbody) return cronograma;

      tbody.querySelectorAll("tr").forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 3) return;

        const etapaText  = cells[0]?.textContent?.trim() || "";
        const etapaLines = etapaText.split("\n").map(l => l.trim()).filter(Boolean);

        cronograma.push({
          etapa:        etapaLines[0] || "",
          tipo:         etapaLines[1] || null,
          fecha_inicio: cells[1]?.textContent?.trim() || null,
          fecha_fin:    cells[2]?.textContent?.trim() || null
        });
      });

      return cronograma;
    }

    // ── Parse all sections ────────────────────────────────────────────────────
    return {
      informacion_general:       parseKeyValueTable("#tbFicha\\:j_idt30"),
      informacion_entidad:       parseKeyValueTable("#tbFicha\\:j_idt73"),
      informacion_procedimiento: parseKeyValueTable("#tbFicha\\:j_idt97"),
      cronograma:                parseCronograma()
    };
  });
}

/**
 * Clicks the "Regresar" button to go back to the results table.
 */
async function closeFicha(page, run_id) {
  await page.evaluate(() => {
    const btn = document.querySelector("#tbFicha\\:j_idt22");
    if (btn) btn.click();
  });

  // Wait until ficha form disappears
  await page.waitForFunction(
    () => !document.querySelector("#tbFicha\\:idFormFichaSeleccion"),
    { timeout: 10000 }
  );

  await page.waitForTimeout(500);
  console.log(`[${run_id}] ✓ Back to results`);
}

/**
 * Tries to close the ficha page silently (used in error recovery).
 */
async function tryCloseFicha(page) {
  try {
    const isOnFicha = await page.$('#tbFicha\\:j_idt22');
    if (isOnFicha) {
      await page.evaluate(() => {
        const btn = document.querySelector("#tbFicha\\:j_idt22");
        if (btn) btn.click();
      });

      await page.waitForFunction(
        () => !document.querySelector("#tbFicha\\:idFormFichaSeleccion"),
        { timeout: 10000 }
      ).catch(() => {});

      await page.waitForTimeout(500);
    }
  } catch (e) {
    console.error("[ficha] Could not navigate back:", e.message);
  }
}