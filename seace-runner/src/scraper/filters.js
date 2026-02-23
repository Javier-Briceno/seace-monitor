import { log } from './logger.js';

const SEACE_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml";

/**
 * Navigates to SEACE and activates the "Buscador de Procedimientos de Seleccion" tab.
 * SEACE uses PrimeFaces (JSF).
 * This function depends on the PrimeFaces TabView widget (window.widget_tbBuscador).
 * If the widget is not available, it throws an error.
 */
export async function navigateToSEACE(page) {
  log(`Navigating to SEACE...`);

  await page.goto(SEACE_URL, { waitUntil: "networkidle", timeout: 60000 });

  await page.waitForFunction(
    () => window.widget_tbBuscador !== undefined,
    {timeout: 15000}
  );
  
  await page.waitForTimeout(2000 + Math.random() * 1000);
  log(`Activating search tab...`);

  await page.evaluate(() => {
    const tabWidget = window.widget_tbBuscador;
    
    if(!tabWidget) throw new Error('TabView Widget not found');
    // Buscador de Procedimientos de Seleccion is tab 1
    tabWidget.select(1);
  });

  await page.waitForTimeout(3000 + Math.random() * 1000);
  log(`Tab activated`);
}

/**
 * Applies search filters: departamento, objeto, anio.
 * Each filter uses a PrimeFaces selectOneMenu dropdown.
 */
export async function applyFilters(page, { departamento, objeto, anio }) {
  // Expand "Busqueda Avanzada" to access the Departamento field
  log(`Expanding Búsqueda Avanzada...`);
  await page.evaluate(() => {
    const fieldsetId = 'tbBuscador:idFormBuscarProceso:j_idt232';
    const fieldsetVar = 'widget_' + fieldsetId.replace(/:/g, '_');
    const fieldset = window[fieldsetVar];
    if (fieldset && fieldset.cfg.collapsed) {
      fieldset.toggle();
    }
  });
  await page.waitForTimeout(1000 + Math.random() * 1000);

  if (departamento) await setDepartamento(page, departamento);
  if (objeto)       await setObjeto(page, objeto);
  if (anio)         await setAnio(page, anio);
}

/**
 * Clicks the search button and waits for results to load.
 * 
 * SEACE uses reCAPTCHA v3. There are TWO buttons:
 * 1. btnBuscarSelToken (visible) - loads reCAPTCHA token
 * 2. btnBuscarSel (hidden) - actual AJAX submit
 * 
 * We need to wait for the token to load, then click the hidden submit button
 * to trigger the PrimeFaces AJAX
 */
export async function runSearch(page, run_id) {
  log(`Running search...`);

  await page.click("#tbBuscador\\:idFormBuscarProceso\\:btnBuscarSelToken")
  log(`Token button clicked, waiting for reCAPTCHA...`);

  // Wait for reCAPTCHA token to be loaded into hidden field
  try {
    await page.waitForFunction(
      () => {
        const tokenField = document.querySelector("#tbBuscador\\:idFormBuscarProceso\\:tokenBusProSel");
        return tokenField && tokenField.value && tokenField.value.length > 100;
      },
      { timeout: 15000 }
    );
    log(`reCAPTCHA token loaded`);
  } catch (e) {
    console.warn(`Warning: reCAPTCHA token not detected, continuing anyway...`);
  }

  await page.waitForTimeout(1500);

  log(`Triggering PrimeFaces AJAX search...`);
  await page.evaluate(() => {
    document.querySelector('#tbBuscador\\:idFormBuscarProceso\\:btnBuscarSel').click();
  });
  
  log(`AJAX search triggered, waiting for results...`);
  
  await page.waitForTimeout(500);

  await page.waitForFunction(() => 
    window.PrimeFaces?.ajax?.Queue?.isEmpty?.() === true,
  {timeout: 45000});

  log(`Waiting for results table...`);
  
  try {
    // Wait for results table to appear and contain either data rows or an empty-message row
    await page.waitForFunction(
      () => {
        const tbody = document.querySelector(
          'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]'
        );
        if (!tbody) return false;
        
        const rows = tbody.querySelectorAll("tr");
        
        if (rows.length === 0) return false;
        
        // If first row is the empty message, search finished with no results
        const firstRow = rows[0];
        if (firstRow.classList.contains("ui-datatable-empty-message")) {
          return true; // search completed, no results found
        }
        
        const cells = firstRow.querySelectorAll("td");
        if (cells.length === 0) return false;
        
        const hasContent = Array.from(cells).some(cell => cell.textContent.trim().length > 0);
        
        return hasContent;
      },
      { timeout: 45000 }
    );
    
    log(`Results table loaded with data`);
    
  } catch (e) {
    log(`Timeout waiting for results table`);
    
    const debugInfo = await page.evaluate(() => {
      const tbody = document.querySelector('tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]');
      if (!tbody) return { error: "tbody not found" };
      
      const rows = tbody.querySelectorAll("tr");
      const tokenField = document.querySelector("#tbBuscador\\:idFormBuscarProceso\\:tokenBusProSel");
      const departamentoLabel = document.querySelector("#tbBuscador\\:idFormBuscarProceso\\:departamento_label");
      const objetoLabel = document.querySelector("#tbBuscador\\:idFormBuscarProceso\\:j_idt188_label");
      const anioLabel = document.querySelector("#tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_label");
      return {
        rowCount: rows.length,
        firstRowClasses: rows[0]?.className || "no first row",
        firstRowText: rows[0]?.textContent?.substring(0, 100) || "no text",
        tokenValue: tokenField?.value?.substring(0, 50) || "no token",
        departamento: departamentoLabel?.textContent || "no depto",
        objeto: objetoLabel?.textContent || "no objeto",
        anio: anioLabel?.textContent || "no anio"
      };
    });
    
    log(`Debug info: ${JSON.stringify(debugInfo)}`);
    throw e;
  }

  await page.waitForTimeout(1000);
  
  log(`Results loaded`);
}

// -------- Private helpers --------

async function setDepartamento(page, departamento) {
  log(`Setting Departamento: ${departamento}`);

  await page.evaluate((value) => {
    const widgetId = 'tbBuscador:idFormBuscarProceso:departamento';
    const widgetVar = 'widget_' + widgetId.replace(/:/g, '_');
    const widget = window[widgetVar];
    if (widget) {
      const selectElement = document.querySelector('#tbBuscador\\:idFormBuscarProceso\\:departamento_input');
      if (selectElement) {
        for (const option of selectElement.options) {
          if (option.text === value) {
            widget.selectValue(option.value);
            return;
          }
        }
        throw new Error(`Departamento ${value} not found`);
      }
    }
    throw new Error(`Widget not found for ${widgetId}`);
  }, departamento);

  await page.waitForTimeout(500 + Math.random() * 500);
  log(`Departamento set`);
}

async function setObjeto(page, objeto) {
  log(`Setting Objeto: ${objeto}`);

  // Normalize: "OBRA" -> "Obra"
  const normalized = objeto.charAt(0).toUpperCase() + objeto.slice(1).toLowerCase();

  await page.evaluate((value) => {
    const widgetId = 'tbBuscador:idFormBuscarProceso:j_idt188';
    
    const widgetVar = 'widget_' + widgetId.replace(/:/g, '_');
    const widget = window[widgetVar];
    if (widget) {
      const selectElement = document.querySelector('#tbBuscador\\:idFormBuscarProceso\\:j_idt188_input');
      if (selectElement) {
        for (const option of selectElement.options) {
          if (option.text === value) {
            widget.selectValue(option.value);
            return;
          }
        }
        throw new Error(`Objeto ${value} not found`);
      }
    }
    throw new Error(`Widget not found for ${widgetId}`);
  }, normalized);

  await page.waitForTimeout(500 + Math.random() * 500);
  log(`Objeto set`);
}

async function setAnio(page, anio) {
  log(`Setting Año: ${anio}`);

  await page.evaluate((value) => {
    const widgetId = 'tbBuscador:idFormBuscarProceso:anioConvocatoria';
    
    const widgetVar = 'widget_' + widgetId.replace(/:/g, '_');
    const widget = window[widgetVar];
    if (widget) {
      const selectElement = document.querySelector('#tbBuscador\\:idFormBuscarProceso\\:anioConvocatoria_input');
      if (selectElement) {
        for (const option of selectElement.options) {
          if (option.text === value) {
            widget.selectValue(option.value);
            return;
          }
        }
        throw new Error(`Año ${value} not found`);
      }
    }
    throw new Error(`Widget not found for ${widgetId}`);
  }, anio);

  await page.waitForTimeout(500 + Math.random() * 500);
  log(`Año set`);
}