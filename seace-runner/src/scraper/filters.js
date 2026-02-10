const SEACE_URL =
  "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml";

/**
 * Navigates to SEACE and activates the "Buscador de Procedimientos" tab.
 * SEACE uses PrimeFaces (JSF) which requires direct DOM manipulation to switch tabs.
 */
export async function navigateToSEACE(page, run_id) {
  console.log(`[${run_id}] Navigating to SEACE...`);

  await page.goto(SEACE_URL, { waitUntil: "networkidle", timeout: 60000 });
  await page.waitForSelector(".ui-tabs", { timeout: 15000 });
  await page.waitForTimeout(2000);

  console.log(`[${run_id}] Activating search tab...`);

  // PrimeFaces tabs don't respond to normal clicks in headless mode.
  // We manipulate the DOM directly to activate tab index 1.
  await page.evaluate(() => {
    const tabLinks  = document.querySelectorAll(".ui-tabs-nav li");
    const tabPanels = document.querySelectorAll(".ui-tabs-panel");

    // Deactivate all tabs
    tabLinks.forEach(tab => {
      tab.classList.remove("ui-tabs-selected", "ui-state-active", "ui-state-focus");
      tab.setAttribute("aria-expanded", "false");
    });

    // Hide all panels
    tabPanels.forEach(panel => {
      panel.style.display = "none";
      panel.classList.add("ui-helper-hidden");
      panel.setAttribute("aria-hidden", "true");
    });

    // Activate tab 1 ("Buscador de Procedimientos de Selección")
    if (tabLinks[1]) {
      tabLinks[1].classList.add("ui-tabs-selected", "ui-state-active");
      tabLinks[1].setAttribute("aria-expanded", "true");
    }

    // Show corresponding panel
    if (tabPanels[1]) {
      tabPanels[1].style.display = "block";
      tabPanels[1].classList.remove("ui-helper-hidden");
      tabPanels[1].setAttribute("aria-hidden", "false");
    }

    // Update hidden input that PrimeFaces uses to track active tab
    const hiddenInput = document.querySelector("#tbBuscador_activeIndex");
    if (hiddenInput) hiddenInput.value = "1";
  });

  await page.waitForTimeout(3000);
  console.log(`[${run_id}] ✓ Tab activated`);
}

/**
 * Applies search filters: departamento, objeto, anio.
 * Each filter uses a PrimeFaces selectOneMenu dropdown.
 */
export async function applyFilters(page, { departamento, objeto, anio }, run_id) {
  // Expand "Búsqueda Avanzada" to access the Departamento field
  console.log(`[${run_id}] Expanding Búsqueda Avanzada...`);
  await page.click('.ui-fieldset-legend:has-text("Búsqueda Avanzada")');
  await page.waitForTimeout(1000);

  if (departamento) await setDepartamento(page, departamento, run_id);
  if (objeto)       await setObjeto(page, objeto, run_id);
  if (anio)         await setAnio(page, anio, run_id);
}

/**
 * Clicks the search button and waits for results to load.
 */
export async function runSearch(page, run_id) {
  console.log(`[${run_id}] Running search...`);

  await page.click("#tbBuscador\\:idFormBuscarProceso\\:btnBuscarSelToken");
  await page.waitForTimeout(1000);

  // Wait for AJAX loading overlay to disappear
  await page.waitForSelector(".ui-blockui-content", {
    state: "hidden",
    timeout: 30000
  }).catch(() => {
    console.log(`[${run_id}] No block overlay detected, continuing...`);
  });

  await page.waitForTimeout(2000);

  // Wait for results table to have rows
  await page.waitForFunction(
    () => {
      const tbody = document.querySelector(
        'tbody[id="tbBuscador:idFormBuscarProceso:dtProcesos_data"]'
      );
      if (!tbody) return false;
      const rows = tbody.querySelectorAll("tr");
      return (
        rows.length > 0 &&
        !rows[0].classList.contains("ui-datatable-empty-message")
      );
    },
    { timeout: 30000 }
  );

  console.log(`[${run_id}] ✓ Results loaded`);
}

// ─── Private helpers ──────────────────────────────────────────────────────────

async function setDepartamento(page, departamento, run_id) {
  console.log(`[${run_id}] Setting Departamento: ${departamento}`);

  const selector = await page.evaluate(() => {
    const dept = document.querySelector(
      "#tbBuscador\\:idFormBuscarProceso\\:departamento"
    );
    return dept ? "#tbBuscador\\:idFormBuscarProceso\\:departamento" : null;
  });

  if (!selector) throw new Error("Departamento dropdown not found");

  await page.click(selector);
  await waitForDropdown(page);
  await page.click(
    `.ui-selectonemenu-panel:visible .ui-selectonemenu-item:has-text("${departamento}")`
  );
  await page.waitForTimeout(500);

  console.log(`[${run_id}] ✓ Departamento set`);
}

async function setObjeto(page, objeto, run_id) {
  console.log(`[${run_id}] Setting Objeto: ${objeto}`);

  const selector = await page.evaluate(() => {
    const selects = document.querySelectorAll(
      "#tbBuscador\\:idFormBuscarProceso\\:pnlFiltro .ui-selectonemenu"
    );
    if (selects.length >= 2) {
      return "#" + selects[1].id.replace(/:/g, "\\:");
    }
    return null;
  });

  if (!selector) throw new Error("Objeto dropdown not found");

  await page.click(selector);
  await waitForDropdown(page);

  // Normalize: "OBRA" → "Obra"
  const normalized = objeto.charAt(0).toUpperCase() + objeto.slice(1).toLowerCase();

  await page.evaluate((texto) => {
    const panels = document.querySelectorAll(".ui-selectonemenu-panel");
    let visiblePanel = null;

    for (const panel of panels) {
      const style = window.getComputedStyle(panel);
      if (style.display !== "none" && style.visibility !== "hidden") {
        visiblePanel = panel;
        break;
      }
    }

    if (!visiblePanel) throw new Error("No visible dropdown panel found");

    const items = visiblePanel.querySelectorAll(".ui-selectonemenu-item");
    for (const item of items) {
      if (item.innerText.trim() === texto) {
        item.click();
        return;
      }
    }

    throw new Error(`Option not found: ${texto}`);
  }, normalized);

  await page.waitForTimeout(500);
  console.log(`[${run_id}] ✓ Objeto set`);
}

async function setAnio(page, anio, run_id) {
  console.log(`[${run_id}] Setting Año: ${anio}`);

  const selector = await page.evaluate(() => {
    const selects = document.querySelectorAll(
      "#tbBuscador\\:idFormBuscarProceso\\:pnlFiltro .ui-selectonemenu"
    );
    for (let i = 0; i < selects.length; i++) {
      const label =
        selects[i].closest("td")?.previousElementSibling?.textContent || "";
      if (label.includes("Año")) {
        return "#" + selects[i].id.replace(/:/g, "\\:");
      }
    }
    return null;
  });

  if (!selector) throw new Error("Año dropdown not found");

  await page.click(selector);
  await waitForDropdown(page);
  await page.click(
    `.ui-selectonemenu-panel .ui-selectonemenu-item:has-text("${anio}")`
  );
  await page.waitForTimeout(500);

  console.log(`[${run_id}] ✓ Año set`);
}

async function waitForDropdown(page) {
  await page.waitForFunction(
    () => {
      const panels = document.querySelectorAll(".ui-selectonemenu-panel");
      for (const panel of panels) {
        const style = window.getComputedStyle(panel);
        if (style.display !== "none" && style.visibility !== "hidden") {
          return panel.querySelectorAll(".ui-selectonemenu-item").length > 0;
        }
      }
      return false;
    },
    { timeout: 5000 }
  );
  await page.waitForTimeout(300);
}