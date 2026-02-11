import fs from "fs";

const RESULTS_TBODY = 'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]';
const FICHA_FORM    = "#tbFicha\\:idFormFichaSeleccion";

/**
 * Clicks on the "Ficha de Selección" link for a given row,
 * takes a debug screenshot, extracts all sections dynamically,
 * then navigates back.
 * 
 * Returns null if extraction fails (item is still added without ficha data).
 */
export async function extractFicha(page, rowIndex, run_id) {
  try {
    await openFicha(page, rowIndex, run_id);
    await screenshotFicha(page, rowIndex);
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
  await page.waitForTimeout(1500 + Math.random() * 1000);

}

/**
 * Takes a full-page screenshot of the ficha and saves it as:
 * debug/ficha_item{rowIndex + 1}.png
 * 
 * This makes it easy to compare screenshots with JSON output
 * and discover new/unexpected section structures.
 */
async function screenshotFicha(page, rowIndex) {
  try {
    if (!fs.existsSync("debug")) {
      fs.mkdirSync("debug", { recursive: true });
    }
    const path = `debug/ficha_item${rowIndex + 1}.png`;
    await page.screenshot({ path, fullPage: true });
    console.log(`[ficha] Screenshot saved: ${path}`);
  } catch (e) {
    console.error("[ficha] Could not save screenshot:", e.message);
  }
}

/**
 * Dynamically parses ALL sections from the ficha page.
 *
 * Instead of relying on hardcoded j_idt IDs (which change between SEACE
 * deployments), we find sections by their visible heading text and infer
 * the table type automatically:
 *
 *   - Key-value tables  → { "Label": "value", ... }
 *   - Columnar tables   → [ { col1: val, col2: val, ... }, ... ]
 *
 * This handles any number of sections, including new ones like
 * "Entidad Contratante" that weren't present before.
 */
async function parseFicha(page) {
  return await page.evaluate(() => {

    // ── Helpers ──────────────────────────────

    /**
     * Parses a key-value table: each row has (label cell, value cell).
     * Handles nested tables in value cells (e.g. "Lugar y cuenta de pago").
     */
    function parseKeyValueTable(table) {
      const result = {};
      table.querySelectorAll("tbody tr, tr").forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 2) return;

        const label = cells[0]?.textContent?.trim().replace(/:$/, "");
        if (!label) return;

        const innerTable = cells[1]?.querySelector("table");
        if (innerTable) {
          // Nested table: extract as { col1: val, col2: val }
          const headerRow = innerTable.querySelector("tr");
          const dataRow   = innerTable.querySelectorAll("tr")[1];
          if (headerRow && dataRow) {
            const headers = [...headerRow.querySelectorAll("td, th")].map(c => c.textContent.trim());
            const values  = [...dataRow.querySelectorAll("td")].map(c => c.textContent.trim());
            const nested  = {};
            headers.forEach((h, i) => { if (h) nested[h] = values[i] || null; });
            result[label] = nested;
          } else {
            result[label] = cells[1]?.textContent?.trim() || null;
          }
        } else {
          // Fix: trim whitespace to avoid "8,361,815.10Soles" → "8,361,815.10 Soles"
          result[label] = cells[1]?.textContent?.replace(/\s+/g, " ").trim() || null;
        }
      });
      return result;
    }

    /**
     * Parses a columnar table (like Cronograma, Entidad Contratante):
     * uses the first row as headers, remaining rows as data.
     */
    function parseColumnarTable(table) {
      const rows    = table.querySelectorAll("tbody tr, tr");
      const headers = [];
      const results = [];

      rows.forEach((row, i) => {
        const cells = row.querySelectorAll("td, th");
        if (i === 0) {
          cells.forEach(c => headers.push(c.textContent.trim()));
          return;
        }
        const entry = {};
        cells.forEach((c, j) => {
          const key = headers[j] || `col_${j}`;
          // For Cronograma: split "Etapa\nA través del SEACE" into etapa + tipo
          if (j === 0 && headers[j]?.toLowerCase().includes("etapa")) {
            const lines = c.textContent.trim().split("\n").map(l => l.trim()).filter(Boolean);
            entry["Etapa"] = lines[0] || null;
            entry["Tipo"]  = lines[1] || null;
          } else {
            entry[key] = c.textContent.replace(/\s+/g, " ").trim() || null;
          }
        });
        results.push(entry);
      });

      return results;
    }

    /**
     * Parses the "Lista de Documentos" table specifically.
     * Extracts download metadata from onclick attributes.
     */
    function parseDocumentosTable(tbody) {
      const documentos = [];
      const rows = tbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      
      rows.forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 5) return;

        const nro = cells[0]?.textContent?.trim();
        const etapa = cells[1]?.textContent?.trim();
        const documento = cells[2]?.textContent?.trim();
        const fechaPublicacion = cells[4]?.textContent?.trim();

        // Parse download link from onclick="descargaDocGeneral('uuid','tipo','filename')"
        let archivoData = null;
        const linkWithOnclick = cells[3]?.querySelector('a[onclick*="descargaDocGeneral"]');
        
        if (linkWithOnclick) {
          const onclick = linkWithOnclick.getAttribute('onclick');
          const match = onclick.match(/descargaDocGeneral\('([^']+)','([^']+)','([^']+)'\)/);
          
          if (match) {
            const [, uuid, tipo, filename] = match;
            const tamanioText = linkWithOnclick.textContent?.trim() || "";
            
            archivoData = {
              uuid: uuid,
              tipo: tipo,
              filename: filename,
              tamanio: tamanioText
            };
          }
        }

        documentos.push({
          Nro: nro || null,
          Etapa: etapa || null,
          Documento: documento || null,
          Archivo: archivoData,
          "Fecha de publicación": fechaPublicacion || null
        });
      });

      return documentos;
    }

    /**
     * Decides if a table is key-value or columnar.
     * Key-value: first cell of each row is a label (th-like), second is value.
     * Columnar: has a clear header row with multiple columns.
     */
    function detectTableType(table) {
      const firstRow    = table.querySelector("tbody tr, tr");
      if (!firstRow) return "empty";

      const cells       = firstRow.querySelectorAll("td, th");
      const headerRow   = table.querySelector("thead tr") || table.querySelector("tr");
      const hasHeaders  = [...(headerRow?.querySelectorAll("th") || [])].length > 0;
      const hasTwoColsOnly = cells.length === 2;

      // If there's a <thead> with multiple headers, it's columnar
      if (hasHeaders && !hasTwoColsOnly) return "columnar";

      // If first row has class or style suggesting it's a header row
      const allRows = table.querySelectorAll("tbody tr");
      if (allRows.length > 0) {
        // Count rows with exactly 2 cells (key-value pattern)
        const twoColRows = [...allRows].filter(r => r.querySelectorAll("td").length === 2).length;
        if (twoColRows / allRows.length > 0.6) return "key-value";
      }

      // Default: if first row has > 2 cells, assume columnar
      return cells.length > 2 ? "columnar" : "key-value";
    }

    // ── Find and parse all sections ──────────────────────────────────────────

    const ficha  = document.querySelector("#tbFicha\\:idFormFichaSeleccion");
    if (!ficha) return { error: "Ficha form not found in DOM" };

    const sections = {};

    // Find all visible section headings (fieldset legends or div headings)
    const headingSelectors = [
      "fieldset legend",
      ".ui-fieldset-legend",
      ".ui-panel-title",
      "h3", "h4",
      // SEACE uses plain text in certain span/div patterns
      ".card-header",
    ];

    // Strategy: find all <fieldset> containers first (most reliable)
    const fieldsets = ficha.querySelectorAll("fieldset");
    fieldsets.forEach(fieldset => {
      const legend = fieldset.querySelector("legend, .ui-fieldset-legend");
      const title  = legend?.textContent?.trim();
      if (!title) return;

      const table = fieldset.querySelector("table");
      if (!table) return;

      const type = detectTableType(table);
      const key  = title.toLowerCase()
        .replace(/\s+/g, "_")
        .replace(/[áàä]/g, "a").replace(/[éèë]/g, "e")
        .replace(/[íìï]/g, "i").replace(/[óòö]/g, "o")
        .replace(/[úùü]/g, "u").replace(/[ñ]/g, "n")
        .replace(/[^a-z0-9_]/g, "");

      sections[key] = type === "columnar"
        ? parseColumnarTable(table)
        : parseKeyValueTable(table);
    });

    // Strategy fallback: if no fieldsets found, look for panels or divs with headings
    if (Object.keys(sections).length === 0) {
      const panels = ficha.querySelectorAll(".ui-panel, .card, [class*='section']");
      panels.forEach(panel => {
        const titleEl = panel.querySelector(".ui-panel-title, .card-title, h3, h4");
        const title   = titleEl?.textContent?.trim();
        if (!title) return;

        const table = panel.querySelector("table");
        if (!table) return;

        const type = detectTableType(table);
        const key  = title.toLowerCase()
          .replace(/\s+/g, "_")
          .replace(/[^a-z0-9_]/g, "");

        sections[key] = type === "columnar"
          ? parseColumnarTable(table)
          : parseKeyValueTable(table);
      });
    }

    // Always try to grab Cronograma by its known tbody ID as a safety net
    if (!sections.cronograma) {
      const cronTbody = document.querySelector("#tbFicha\\:dtCronograma_data");
      if (cronTbody) {
        // Reconstruct as if it were a table
        const rows = cronTbody.querySelectorAll("tr");
        const cronograma = [];
        rows.forEach(row => {
          const cells = row.querySelectorAll("td");
          if (cells.length < 3) return;
          const etapaText  = cells[0]?.textContent?.trim() || "";
          const etapaLines = etapaText.split("\n").map(l => l.trim()).filter(Boolean);
          cronograma.push({
            Etapa:        etapaLines[0] || "",
            Tipo:         etapaLines[1] || null,
            "Fecha Inicio": cells[1]?.textContent?.trim() || null,
            "Fecha Fin":    cells[2]?.textContent?.trim() || null
          });
        });
        if (cronograma.length > 0) sections.cronograma = cronograma;
      }
    }
    
    // Always try to grab Documentos by its known tbody ID as a safety net
    if (!sections.lista_de_documentos && !sections.documentos) {
      const docTbody = document.querySelector("#tbFicha\\:dtDocumentos_data");
      if (docTbody) {
        const documentos = parseDocumentosTable(docTbody);
        if (documentos.length > 0) sections.documentos = documentos;
      }
    }

    return sections;
  });
}

/**
 * Clicks the "Regresar" button to go back to the results table.
 * Uses text search instead of hardcoded j_idt ID (more robust).
 */
async function closeFicha(page, run_id) {
  await page.evaluate(() => {
    // Find "Regresar" button by text (more stable than j_idt22 which can change)
    const buttons = document.querySelectorAll("button, a.ui-button, .ui-button");
    for (const btn of buttons) {
      if (btn.textContent?.trim().includes("Regresar")) {
        btn.click();
        return;
      }
    }
    // Fallback to known ID
    const btn = document.querySelector("#tbFicha\\:j_idt22");
    if (btn) btn.click();
  });

  await page.waitForFunction(
    () => !document.querySelector("#tbFicha\\:idFormFichaSeleccion"),
    { timeout: 10000 }
  );

  await page.waitForTimeout(500 + Math.random() * 1000);

  // Ensure we're back on the correct tab after closing ficha
  // Sometimes closing ficha can switch tabs, especially after last item
  await page.evaluate(() => {
    const tabLinks = document.querySelectorAll('.ui-tabs-nav li');
    const tabPanels = document.querySelectorAll('.ui-tabs-panel');
    
    // Check if we're on the correct tab (index 1 = "Buscador de Procedimientos")
    const activeTabIndex = Array.from(tabLinks).findIndex(tab => 
      tab.classList.contains('ui-tabs-selected') || tab.classList.contains('ui-state-active')
    );
    
    if (activeTabIndex !== 1) {
      console.log(`[TAB FIX] Wrong tab active (${activeTabIndex}), switching to tab 1`);
      
      // Deactivate all
      tabLinks.forEach((tab) => {
        tab.classList.remove('ui-tabs-selected', 'ui-state-active');
        tab.setAttribute('aria-expanded', 'false');
      });
      tabPanels.forEach((panel) => {
        panel.style.display = 'none';
        panel.classList.add('ui-helper-hidden');
      });
      
      // Activate correct tab (index 1)
      if (tabLinks[1]) {
        tabLinks[1].classList.add('ui-tabs-selected', 'ui-state-active');
        tabLinks[1].setAttribute('aria-expanded', 'true');
      }
      if (tabPanels[1]) {
        tabPanels[1].style.display = 'block';
        tabPanels[1].classList.remove('ui-helper-hidden');
      }
      
      const hiddenInput = document.querySelector('#tbBuscador_activeIndex');
      if (hiddenInput) hiddenInput.value = '1';
    }
  });
  
  // Let tab settle
  await page.waitForTimeout(300);
  
  console.log(`[${run_id}] ✓ Back to results`);
}

/**
 * Tries to close the ficha page silently (used in error recovery).
 */
async function tryCloseFicha(page) {
  try {
    const isOnFicha = await page.$("#tbFicha\\:idFormFichaSeleccion");
    if (isOnFicha) {
      await page.evaluate(() => {
        const buttons = document.querySelectorAll("button, a.ui-button, .ui-button");
        for (const btn of buttons) {
          if (btn.textContent?.trim().includes("Regresar")) {
            btn.click();
            return;
          }
        }
        const btn = document.querySelector("#tbFicha\\:j_idt22");
        if (btn) btn.click();
      });

      await page.waitForFunction(
        () => !document.querySelector("#tbFicha\\:idFormFichaSeleccion"),
        { timeout: 10000 }
      ).catch(() => {});

      await page.waitForTimeout(500 + Math.random() * 1000);

      // Also ensure correct tab after error recovery
      await page.evaluate(() => {
        const tabLinks = document.querySelectorAll('.ui-tabs-nav li');
        const tabPanels = document.querySelectorAll('.ui-tabs-panel');
        
        const activeTabIndex = Array.from(tabLinks).findIndex(tab => 
          tab.classList.contains('ui-tabs-selected') || tab.classList.contains('ui-state-active')
        );
        
        if (activeTabIndex !== 1) {
          tabLinks.forEach((tab) => {
            tab.classList.remove('ui-tabs-selected', 'ui-state-active');
            tab.setAttribute('aria-expanded', 'false');
          });
          tabPanels.forEach((panel) => {
            panel.style.display = 'none';
            panel.classList.add('ui-helper-hidden');
          });
          
          if (tabLinks[1]) {
            tabLinks[1].classList.add('ui-tabs-selected', 'ui-state-active');
            tabLinks[1].setAttribute('aria-expanded', 'true');
          }
          if (tabPanels[1]) {
            tabPanels[1].style.display = 'block';
            tabPanels[1].classList.remove('ui-helper-hidden');
          }
          
          const hiddenInput = document.querySelector('#tbBuscador_activeIndex');
          if (hiddenInput) hiddenInput.value = '1';
        }
      }).catch(() => {});
    }
  } catch (e) {
    console.error("[ficha] Could not navigate back:", e.message);
  }
}