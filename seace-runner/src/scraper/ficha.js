import fs from "fs";
import { log } from './logger.js';

/**
 * Clicks on the "Ficha de Selección" link for a given row,
 * takes a debug screenshot, extracts all sections dynamically,
 * then navigates back.
 * 
 * Returns null if extraction fails (item is still added without ficha data).
 */
export async function extractFicha(page, rowIndex) {
  try {
    await openFicha(page, rowIndex);

    await screenshotFicha(page, rowIndex);

    const fichaData = await parseFicha(page);

    if (fichaData.documentos?.length > 0) {
      fichaData.documentos = await resolveDownloadUrls(page, fichaData.documentos);
    }
    await closeFicha(page);

    log(`Ficha extracted for item ${rowIndex + 1}`);
    return fichaData;

  } catch (err) {
    console.error(`[Ficha] error for item ${rowIndex + 1}:`, err.message);

    // Try to navigate back if we're stuck on the ficha page
    await tryCloseFicha(page);

    return { error: err.message };
  }
}

// ─── Private helpers ──────────────────────────────────────────────────────────

/**
 * Clicks the ficha icon for the row at rowIndex and waits for the ficha to load.
 */
async function openFicha(page, rowIndex) {
  await page.waitForSelector(
    `img[id*="grafichaSel"]`,
    { timeout: 10000, state: 'attached' }
  );

  const navigationPromise = page.waitForNavigation({ waitUntil: 'networkidle', timeout: 30000 })

  log(`Clicking ficha icon for row ${rowIndex}`);
  page.evaluate((index) => {
      const imgs = document.querySelectorAll(`img[id*="grafichaSel"]`);
      const img = imgs[index];
      if (!img) throw new Error(`Ficha icon not found for row ${index}`)  
        img.parentElement.click();
    }, rowIndex);

  await navigationPromise;

  // Confirm ficha loaded
  await page.waitForSelector('#tbFicha\\:idFormFichaSeleccion', { timeout: 15000 });
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
    log(`[ficha] Screenshot saved: ${path}`);
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
     * Cleans text values: removes extra whitespace and adds space before units.
     */
    function cleanValue(text) {
      if (!text) return null;
      
      // Normalize all whitespace to single spaces
      text = text.replace(/\s+/g, " ").trim();
      
      // Add space before "Soles" if missing
      text = text.replace(/(\d)Soles/g, "$1 Soles");
      
      // Add space before "KB" if missing  
      text = text.replace(/(\d)KB/g, "$1 KB");
      
      return text;
    }

    /**
     * Parses a key-value table: each row has (label cell, value cell).
     * Handles nested tables in value cells (e.g. "Lugar y cuenta de pago").
     * 
     * IMPROVED: Skips the first row if it contains concatenated text (the giant key issue).
     */
    function parseKeyValueTable(table) {
    const result = {};
    
    const outerRows = table.querySelectorAll(':scope > tbody > tr, :scope > tr');
    
    outerRows.forEach(outerRow => {
      const outerCell = outerRow.querySelector(':scope > td');
      if (!outerCell) return;
      
      const innerTable = outerCell.querySelector(':scope > table, :scope > * > table');
      if (!innerTable) return;
      
      innerTable.querySelectorAll(':scope > tbody > tr, :scope > tr').forEach(row => {
        const cells = row.querySelectorAll(':scope > td');
        if (cells.length < 2) return;
        
        const label = cells[0]?.textContent?.trim().replace(/:$/, '');
        if (!label || label.split(':').length > 2) return;
        
        const nestedTable = cells[1]?.querySelector('table');
        if (nestedTable) {
          const headerRow = nestedTable.querySelector('tr');
          const dataRow = nestedTable.querySelectorAll('tr')[1];
          if (headerRow && dataRow) {
            const headers = [...headerRow.querySelectorAll('td,th')].map(c => c.textContent.trim());
            const values = [...dataRow.querySelectorAll('td')].map(c => c.textContent.trim());
            const nested = {};
            headers.forEach((h, i) => { if (h) nested[h] = cleanValue(values[i]) || null; });
            result[label] = nested;
          }
        } else {
          result[label] = cleanValue(cells[1]?.textContent) || null;
        }
      });
    });
    
    return result;
  }

    /**
     * Parses a columnar table (like Cronograma, Documentos):
     * uses the first row as headers, remaining rows as data.
     * 
     * IMPROVED: Better header detection and handling of empty tables.
     */
    function parseColumnarTable(table) {
      const rows = table.querySelectorAll("tbody tr, tr");
      const headers = [];
      const results = [];

      rows.forEach((row, i) => {
        const cells = row.querySelectorAll("td, th");
        
        // First row: extract headers
        if (i === 0) {
          cells.forEach(c => {
            const headerText = c.textContent.trim();
            if (headerText) headers.push(headerText);
          });
          return;
        }
        
        // Check if this is an empty message row
        if (row.classList.contains('ui-datatable-empty-message')) {
          return;
        }
        
        // Skip rows that say "No se encontraron Datos"
        if (cells.length === 1 && cells[0].textContent.includes('No se encontraron')) {
          return;
        }

        const entry = {};
        let hasData = false;
        
        cells.forEach((c, j) => {
          const key = headers[j] || `col_${j}`;
          const rawText = c.textContent || "";
          
          // Special handling for Cronograma's first column (Etapa + Tipo on separate lines)
          if (j === 0 && key.toLowerCase().includes("etapa")) {
            const lines = rawText.trim().split("\n").map(l => l.trim()).filter(Boolean);
            if (lines.length > 0) {
              entry["Etapa"] = cleanValue(lines[0]);
              entry["Tipo"] = lines.length > 1 ? cleanValue(lines[1]) : null;
              hasData = true;
            }
          } else {
            const cleanedValue = cleanValue(rawText);
            entry[key] = cleanedValue;
            if (cleanedValue) hasData = true;
          }
        });
        
        // Only add row if it has at least some data
        if (hasData) {
          results.push(entry);
        }
      });

      return results;
    }

    /**
     * Parses the "Lista de Documentos" table specifically.
     * Extracts download metadata from onclick attributes.
     * 
     * UNCHANGED: This already works perfectly.
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

        if (nro && etapa && documento) {
          documentos.push({
            "Nro": nro,
            "Etapa": etapa,
            "Documento": documento,
            "Archivo": archivoData,
            "Fecha de publicación": fechaPublicacion
          });
        }
      });

      return documentos;
    }

    /**
     * Detects whether a table is key-value or columnar.
     */
    function detectTableType(table) {
      const firstRow = table.querySelector("tbody tr, tr");
      if (!firstRow) return "key-value";

      const cells = firstRow.querySelectorAll("td, th");
      
      // If first row has exactly 2 cells and first cell ends with colon, it's key-value
      if (cells.length === 2 && cells[0]?.textContent?.trim().endsWith(":")) {
        return "key-value";
      }
      
      // If first row has many cells with short text, likely headers (columnar)
      if (cells.length > 2) {
        return "columnar";
      }

      return "key-value";
    }

    // ── Main extraction logic ──────────────────────────

    const ficha = document.querySelector("#tbFicha\\:idFormFichaSeleccion");
    if (!ficha) return {};

    const sections = {};

    // Strategy: find all <fieldset> containers first (most reliable)
    const fieldsets = ficha.querySelectorAll("fieldset");
    fieldsets.forEach(fieldset => {
      const legend = fieldset.querySelector("legend, .ui-fieldset-legend");
      const title  = legend?.textContent?.trim();
      if (!title) return;

      // Skip - handled separately or broken
      if (title === 'Ver documentos por Etapa') return;
      if (title === 'Criterios de Búsqueda') return;
      if (title === 'Resultado de Búsqueda') return;
      if (title === 'Opciones del procedimiento') return;
      if (title === 'Cronograma') return; // handled by safety net
      if (title === 'Entidad Contratante') return;
      if (title === 'Detalle de Calendarización') return;
      if (title === 'Ver listado de ítem') return;
      if (title === 'Datos del Procedimiento') return;
      if (title === 'Acuerdos Comerciales') return;

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

    // ── SPECIFIC EXTRACTIONS (safety nets for known sections) ──────────────

    /**
     * CRONOGRAMA: Extract by known tbody ID as safety net
     * IMPROVED: Better handling of empty cronograma
     */
    // Always use safety net for cronograma (more reliable)
    sections.cronograma = [];
    const cronTbody = document.querySelector("#tbFicha\\:dtCronograma_data");

    if (cronTbody) {
      const rows = cronTbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      const cronograma = [];
      
      rows.forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 3) return;
        
        const etapaCell = cells[0];

        // Get text before <br> only
        const firstTextNode = Array.from(etapaCell.childNodes)
          .find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
        const etapa = firstTextNode 
          ? cleanValue(firstTextNode.textContent) 
          : cleanValue(etapaCell.textContent);

        // Get span text after <br> as lugar
        const lugar = etapaCell.querySelector('span')?.textContent?.trim() || null;
        
        const fechaInicio = cleanValue(cells[1]?.textContent);
        const fechaFin = cleanValue(cells[2]?.textContent);
        
        // Only add if we have actual data
        if (etapa && (fechaInicio || fechaFin)) {
          cronograma.push({
            "Etapa": etapa,
            "Lugar": lugar,
            "Fecha Inicio": fechaInicio,
            "Fecha Fin": fechaFin
          });
        }
      });
      
      if (cronograma.length > 0) {
        sections.cronograma = cronograma;
      }
    }

    // ENTIDAD CONTRATANTE
    const entidadTbody = document.querySelector("#tbFicha\\:dtEntidadContrata_data");
    if (entidadTbody) {
      const rows = entidadTbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      const entidades = [];
      rows.forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 2) return;
        entidades.push({
          "N° Ruc": cleanValue(cells[0]?.textContent),
          "Entidad Contratante": cleanValue(cells[1]?.textContent)
        });
      });
      if (entidades.length > 0) sections.entidad_contratante = entidades;
    }

    // ACUERDOS COMERCIALES
    const acuerdosTbody = document.querySelector("#tbFicha\\:dtAcuerdosComerciales_data");
    if (acuerdosTbody) {
      const rows = acuerdosTbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
      const acuerdos = [];
      rows.forEach(row => {
        const cells = row.querySelectorAll("td");
        if (cells.length < 2) return;
        acuerdos.push({
          "Nro": cleanValue(cells[0]?.textContent),
          "Descripción del Acuerdo Comercial": cleanValue(cells[1]?.textContent)
        });
      });
      if (acuerdos.length > 0) sections.acuerdos_comerciales = acuerdos;
    }

    
    /**
     * DOCUMENTOS: Extract by known tbody ID as safety net
     * UNCHANGED: Already works perfectly
     */
    if (!sections.lista_de_documentos && !sections.documentos) {
      const docTbody = document.querySelector("#tbFicha\\:dtDocumentos_data");
      if (docTbody) {
        const documentos = parseDocumentosTable(docTbody);
        if (documentos.length > 0) sections.documentos = documentos;
      }
    }

    /**
     * VER DOCUMENTOS POR ETAPA: Clean extraction
     * NEW: Specific handler to avoid col_0, col_1 mess
     */
    if (!sections.ver_documentos_por_etapa) {
      // Try to find the accordion/tab section for "Ver documentos por etapa"
      const docPorEtapaTbody = document.querySelector("#tbFicha\\:dtDocumentosPorEtapa_data");
      if (docPorEtapaTbody) {
        const cleanDocs = [];
        const rows = docPorEtapaTbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
        
        rows.forEach(row => {
          const cells = row.querySelectorAll("td");
          if (cells.length < 5) return;
          
          const nro = cleanValue(cells[0]?.textContent);
          const etapa = cleanValue(cells[1]?.textContent);
          const documento = cleanValue(cells[2]?.textContent);
          const archivo = cleanValue(cells[3]?.textContent);
          const fecha = cleanValue(cells[4]?.textContent);
          
          if (nro && etapa) {
            cleanDocs.push({
              "Nro": nro,
              "Etapa": etapa,
              "Documento": documento,
              "Archivo": archivo,
              "Fecha y Hora de publicación": fecha,
              "Acciones": null
            });
          }
        });
        
        if (cleanDocs.length > 0) {
          sections.ver_documentos_por_etapa = cleanDocs;
        }
      }
    }

    /**
     * VER LISTADO DE ITEM: Clean extraction
     * NEW: Specific handler for items list
     */
    if (!sections.ver_listado_de_item) {
      const itemsTbody = document.querySelector("#tbFicha\\:dtItemsConvocatoria_data");
      if (itemsTbody) {
        const items = [];
        const rows = itemsTbody.querySelectorAll("tr:not(.ui-datatable-empty-message)");
        
        rows.forEach(row => {
          const cells = row.querySelectorAll("td");
          if (cells.length < 6) return;
          
          const postor = cleanValue(cells[0]?.textContent);
          const mype = cleanValue(cells[1]?.textContent);
          const leySelva = cleanValue(cells[2]?.textContent);
          const bonificacion = cleanValue(cells[3]?.textContent);
          const cantidadAdj = cleanValue(cells[4]?.textContent);
          const montoAdj = cleanValue(cells[5]?.textContent);
          
          if (postor) {
            items.push({
              "Postor": postor,
              "MYPE": mype,
              "Ley de promoción de la Selva": leySelva,
              "Bonificación colindante (Contratación fuera de provincia de Lima y Callao)": bonificacion,
              "Cantidad adjudicada": cantidadAdj,
              "Monto adjudicado": montoAdj
            });
          }
        });
        
        if (items.length > 0) {
          sections.ver_listado_de_item = items;
        }
      }
    }

    return sections;
  });
}

async function resolveDownloadUrls(page, documentos) {
  if (!fs.existsSync('downloads')) fs.mkdirSync('downloads', { recursive: true });

  const resolved = [];
  for (const doc of documentos) {
    if (!doc.Archivo?.uuid) {
      resolved.push(doc);
      continue;
    }
    try {
      const safeFilename = `${doc.Archivo.uuid}_${doc.Archivo.filename.replace(/[^a-z0-9._-]/gi, '_')}`;
      const filepath = `downloads/${safeFilename}`;

      const downloadPromise = page.waitForEvent('download', { timeout: 60000 });
      await page.evaluate((uuid) => {
        jsCmsSeaceUtil.descargaPriv(uuid);
      }, doc.Archivo.uuid);
      const download = await downloadPromise;
      await download.saveAs(filepath);
      fs.chmodSync(filepath, 0o644); // owner can read and write, rest can read

      let pageCount = null;
      let fileSizeMB = null;

      const fileSizeBytes = fs.statSync(filepath).size;
      fileSizeMB = fileSizeBytes / (1024 * 1024);

      const isPDF = filepath.toLowerCase().endsWith('.pdf');
      if (isPDF) {
        try {
          const { PDFDocument } = await import('pdf-lib');
          const pdfBytes = fs.readFileSync(filepath);
          const pdfDoc = await PDFDocument.load(pdfBytes);
          pageCount = pdfDoc.getPageCount();
        } catch (e) {
          log(`[ficha] Could not count pages for ${safeFilename}: ${e.message}`);
        }
      }

      log(`[ficha] Downloaded: ${safeFilename} (${fileSizeBytes} bytes, ${pageCount ?? '?'} pages)`);

      resolved.push({
        ...doc,
        Archivo: {
          ...doc.Archivo,
          local_path: filepath,
          pageCount: pageCount,
          fileSizeMB: fileSizeMB,
          exceedsClaudeLimit: isPDF 
              ? (fileSizeMB > 22 || pageCount > 100 || pageCount === null)
              : false,
        }
      });
    } catch (e) {
      log(`[ficha] Download error for ${doc.Archivo?.filename}: ${e.message}`);
      resolved.push(doc);
    }
  }
  return resolved;
}

/**
 * Clicks the "Regresar" button to go back to the results table.
 * Uses text search instead of hardcoded j_idt ID (more robust).
 */
async function closeFicha(page) {
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
      console.log(`Wrong tab active (${activeTabIndex}), switching to tab 1`);
      
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

  // Wait for DataTable widget to be ready after navigation back
  await page.waitForFunction(() => 
    window.widget_tbBuscador_idFormBuscarProceso_dtProcesos !== undefined,
    { timeout: 15000 }
  );
  log(`Back to results`);
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