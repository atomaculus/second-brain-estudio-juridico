const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");

function labRoot() {
  return path.resolve(__dirname, "..");
}

function localStateRoot() {
  if (process.env.PJN_LOCAL_STATE_DIR) return path.resolve(process.env.PJN_LOCAL_STATE_DIR);
  const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  return path.join(base, "SegundoCerebroJuridico", "PJN");
}

function requirePlaywright() {
  try {
    return require("playwright");
  } catch (error) {
    return require(path.join(labRoot(), "node-tools", "node_modules", "playwright"));
  }
}

const { chromium } = requirePlaywright();

const SCW_HOME = "https://scw.pjn.gov.ar/scw/home.seam";

function vaultRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function timestamp() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function parseArgs(argv) {
  const args = {
    headed: false,
    timeoutSec: 180,
    registry: path.join(vaultRoot(), "08-context", "registries", "matter-registry.json"),
    profileDir: path.join(localStateRoot(), "browser-profile"),
    outDir: null,
    matterId: null,
    keepOpenOnError: false,
    errorPauseSec: 180,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--headed") args.headed = true;
    else if (arg === "--timeout-sec") args.timeoutSec = Number(argv[++i]);
    else if (arg === "--registry") args.registry = argv[++i];
    else if (arg === "--profile-dir") args.profileDir = argv[++i];
    else if (arg === "--out-dir") args.outDir = argv[++i];
    else if (arg === "--matter-id") args.matterId = argv[++i];
    else if (arg === "--keep-open-on-error") args.keepOpenOnError = true;
    else if (arg === "--error-pause-sec") args.errorPauseSec = Number(argv[++i]);
    else if (!args.matterId) args.matterId = arg;
  }
  if (!args.matterId) throw new Error("missing --matter-id");
  return args;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
}

function findMatter(registryPath, matterId) {
  const registry = readJson(registryPath);
  const matters = Array.isArray(registry) ? registry : registry.matters || [];
  const matter = matters.find((item) => item.matterId === matterId);
  if (!matter) throw new Error(`matterId not found: ${matterId}`);
  for (const key of ["fuero", "numero", "anio"]) {
    if (!matter[key]) throw new Error(`matterId ${matterId} missing ${key}`);
  }
  return matter;
}

function cleanText(value) {
  return fixMojibake(String(value || "")).replace(/\s+/g, " ").trim();
}

function fixMojibake(value) {
  let text = String(value || "");
  const replacements = {
    "Ã¡": "á",
    "Ã©": "é",
    "Ã­": "í",
    "Ã³": "ó",
    "Ãº": "ú",
    "Ã±": "ñ",
    "Ã": "Á",
    "Ã‰": "É",
    "Ã": "Í",
    "Ã“": "Ó",
    "Ãš": "Ú",
    "Ã‘": "Ñ",
    "Â°": "°",
    "Âº": "º",
    "Âª": "ª",
    "Â ": " ",
  };
  for (const [bad, good] of Object.entries(replacements)) {
    text = text.split(bad).join(good);
  }
  return text;
}

function valueAfterLabel(value) {
  const text = cleanText(value);
  const match = text.match(/^[^:]+:\s*(.*)$/);
  return match ? match[1].trim() : text;
}

function absoluteUrl(href) {
  return new URL(href, "https://scw.pjn.gov.ar").toString();
}

function redactViewerUrl(href) {
  if (!href) return null;
  const url = new URL(absoluteUrl(href));
  const id = url.searchParams.get("id") || "";
  if (id) {
    const decoded = decodeURIComponent(id);
    const redacted = `${decoded.slice(0, 6)}...${decoded.slice(-4)}`;
    url.searchParams.set("id", redacted);
  }
  return url.toString();
}

function hashValue(value) {
  if (!value) return null;
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function sessionState(page) {
  const text = await page.locator("body").innerText().catch(() => "");
  return {
    text,
    hasChallenge: /VER DESAF[IÍ]O|desaf[ií]o|captcha|campo verificador|verificador/i.test(text),
    hasLogin: /Iniciar sesi[oó]n|Ingresar a Poder Judicial|Registrarse/i.test(text),
    hasPrivateUser: /\b\d{10,11}\b/.test(text) || /Mis Expedientes/i.test(text),
  };
}

async function detectBlockedSession(page) {
  const state = await sessionState(page);
  const text = state.text;
  if (state.hasChallenge) {
    throw new Error("SCW showed CAPTCHA/challenge; authenticated session is not usable");
  }
  if (state.hasLogin && !state.hasPrivateUser) {
    throw new Error("SCW requires authenticated session; rerun with --headed and login through Portal PJN/Consultas");
  }
}

async function waitForScw(page, timeoutMs, allowLogin = false) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!allowLogin) await detectBlockedSession(page);
    const text = await page.locator("body").innerText().catch(() => "");
    if (/Sistema de Consulta Web/i.test(text)) return;
    await page.waitForTimeout(1000);
  }
  throw new Error("SCW did not become ready");
}

async function waitForAuthenticatedScw(context, page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastLogAt = 0;
  let returnedFromPortal = false;
  while (Date.now() < deadline) {
    const pages = context.pages();
    for (const candidate of pages) {
      const state = await sessionState(candidate);
      if (state.hasChallenge) {
        throw new Error("SCW showed CAPTCHA/challenge; authenticated session is not usable");
      }
      if (
        /scw\.pjn\.gov\.ar/i.test(candidate.url()) &&
        /Sistema de Consulta Web/i.test(state.text) &&
        !state.hasLogin
      ) {
        return candidate;
      }
      if (!returnedFromPortal && /portalpjn\.pjn\.gov\.ar\/inicio/i.test(candidate.url())) {
        returnedFromPortal = true;
        console.log("Portal PJN authenticated. Returning to SCW with the active SSO session...");
        await candidate.goto(SCW_HOME, { waitUntil: "domcontentloaded", timeout: 60000 });
        await waitForScw(candidate, 60000, true);
        const scwState = await sessionState(candidate);
        if (scwState.hasLogin && !scwState.hasPrivateUser) {
          const loginLink = candidate.locator("a", { hasText: /Iniciar sesi[oó]n/i }).first();
          if (await loginLink.count()) {
            await loginLink.click();
            await candidate.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
          }
        }
        page = candidate;
      }
    }
    if (Date.now() - lastLogAt > 5000) {
      const urls = pages.map((item) => item.url()).join(" | ");
      console.log(`Waiting for authenticated SCW session. Open pages: ${urls}`);
      lastLogAt = Date.now();
    }
    await page.waitForTimeout(1500);
  }
  throw new Error("SCW did not become authenticated before timeout");
}

async function goToPublicSearch(context, page, headed, timeoutMs) {
  await page.goto(SCW_HOME, { waitUntil: "domcontentloaded", timeout: 60000 });
  await waitForScw(page, 60000, headed);
  const state = await sessionState(page);
  if (state.hasLogin && !state.hasPrivateUser) {
    if (!headed) throw new Error("SCW requires authenticated session; rerun with --headed and login through Portal PJN/Consultas");
    console.log("SCW login is required. Complete Portal PJN/Consultas login in the opened browser; waiting...");
    const loginLink = page.locator("a", { hasText: /Iniciar sesi[oó]n/i }).first();
    if (await loginLink.count()) {
      await loginLink.click();
      await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
      console.log(`Opened login URL: ${page.url()}`);
    }
    page = await waitForAuthenticatedScw(context, page, timeoutMs);
  }
  const publicLink = page.locator("a", { hasText: /Nueva Consulta P[uú]blica/i }).first();
  if (await publicLink.count()) {
    await publicLink.click();
    await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
  }
  await waitForScw(page, 30000);
  return page;
}

async function submitSearch(page, matter) {
  const form = page.locator('form#formPublica, form[name="formPublica"]').first();
  await form.waitFor({ state: "attached", timeout: 60000 });
  const fueroValue = await page.locator('select[name="formPublica:camaraNumAni"] option').evaluateAll(
    (options, fuero) => {
      const wanted = String(fuero).toUpperCase();
      const option = options.find((item) => (item.textContent || "").trim().toUpperCase().startsWith(`${wanted} -`));
      return option ? option.value : null;
    },
    matter.fuero
  );
  if (!fueroValue) throw new Error(`SCW jurisdiction option not found for ${matter.fuero}`);
  await page.selectOption('select[name="formPublica:camaraNumAni"]', fueroValue);
  await page.fill('input[name="formPublica:numero"]', String(matter.numero));
  await page.fill('input[name="formPublica:anio"]', String(matter.anio));

  const consultButton = page
    .locator('input[type="submit"], button, a')
    .filter({ hasText: /Consultar/i })
    .first();
  if (await consultButton.count()) {
    await Promise.all([
      page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {}),
      consultButton.click(),
    ]);
  } else {
    await page.press('input[name="formPublica:anio"]', "Enter");
    await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
  }
  await waitForScw(page, 60000);
}

async function waitForActuacionesTable(page) {
  const text = await page.locator("body").innerText().catch(() => "");
  if (/Expediente inexistente o no disponible/i.test(text)) {
    return "unavailable";
  }
  const table = page.locator('table[id="expediente:action-table"]').first();
  if (await table.count()) {
    await table.waitFor({ state: "attached", timeout: 60000 });
    return "ok";
  }
  const actuacionesTab = page.locator("a, button, span").filter({ hasText: /^Actuaciones$/i }).first();
  if (await actuacionesTab.count()) {
    await actuacionesTab.click();
    await table.waitFor({ state: "attached", timeout: 60000 });
    return "ok";
  }
  throw new Error("SCW action table not found");
}

async function extractActuaciones(page) {
  return await page.evaluate(() => {
    const table = document.querySelector('table[id="expediente:action-table"]');
    if (!table) return [];
    return [...table.querySelectorAll("tbody tr")].map((row, index) => {
      const cells = [...row.querySelectorAll("td")].map((cell) => cell.innerText || "");
      const links = [...row.querySelectorAll('a[href*="viewer.seam"]')].map((anchor) => ({
        text: (anchor.innerText || anchor.title || "").trim(),
        href: anchor.getAttribute("href"),
        absoluteHref: anchor.href,
      }));
      return {
        rowIndex: index + 1,
        rawCells: cells,
        links,
      };
    });
  });
}

function normalizeActuacion(item) {
  const cells = item.rawCells || [];
  const links = (item.links || []).map((link) => {
    const href = link.absoluteHref || absoluteUrl(link.href);
    const url = new URL(href);
    const token = url.searchParams.get("id") || "";
    return {
      label: cleanText(link.text),
      href,
      redactedHref: redactViewerUrl(href),
      tokenSha256: hashValue(token),
      tipoDoc: url.searchParams.get("tipoDoc"),
      download: url.searchParams.get("download") === "true",
    };
  });
  const viewLink = links.find((link) => !link.download) || null;
  const downloadLink = links.find((link) => link.download) || null;
  return {
    rowIndex: item.rowIndex,
    oficina: valueAfterLabel(cells[1]),
    fecha: valueAfterLabel(cells[2]),
    tipoActuacion: valueAfterLabel(cells[3]),
    detalle: valueAfterLabel(cells[4]),
    aFs: cleanText(cells[5]),
    hasDocument: links.length > 0,
    tipoDoc: (viewLink || downloadLink || {}).tipoDoc || null,
    viewHref: viewLink ? viewLink.href : null,
    downloadHref: downloadLink ? downloadLink.href : null,
    redactedViewHref: viewLink ? viewLink.redactedHref : null,
    redactedDownloadHref: downloadLink ? downloadLink.redactedHref : null,
    tokenSha256: (viewLink || downloadLink || {}).tokenSha256 || null,
    links,
  };
}

function writeMarkdown(file, payload) {
  const rows = payload.actuaciones || [];
  const lines = [
    "---",
    "type: scw-actuaciones",
    `created: ${payload.createdAt}`,
    `matterId: ${payload.matterId}`,
    "---",
    "",
    `# Actuaciones SCW - ${payload.expediente}`,
    "",
    `Estado: ${payload.status || "ok"}`,
    "",
    `Caratula: ${payload.caratula || ""}`,
    "",
    `Total actuaciones: ${rows.length}`,
    `Con documento: ${rows.filter((row) => row.hasDocument).length}`,
    "",
    "| Fecha | Oficina | Tipo | Detalle | A fs. | Doc | Link |",
    "|---|---|---|---|---|---|---|",
    ...rows.map((row) =>
      [
        row.fecha,
        row.oficina,
        row.tipoActuacion,
        row.detalle,
        row.aFs,
        row.tipoDoc || "",
        row.redactedViewHref || row.redactedDownloadHref || "",
      ]
        .map((value) => String(value || "").replace(/\|/g, "\\|").replace(/\n/g, " "))
        .join(" | ")
    ).map((line) => `| ${line} |`),
    "",
  ];
  fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
}

async function writeDebugArtifacts(outDir, page, error) {
  const debug = {
    createdAt: new Date().toISOString().slice(0, 19),
    error: error && error.message ? error.message : String(error),
    url: page.url(),
    title: await page.title().catch(() => ""),
    textPath: path.join(outDir, "scw-error-page-text.txt"),
    screenshotPath: path.join(outDir, "scw-error.png"),
  };
  const text = await page.locator("body").innerText().catch(() => "");
  fs.writeFileSync(debug.textPath, text, "utf8");
  await page.screenshot({ path: debug.screenshotPath, fullPage: true }).catch(() => {});
  fs.writeFileSync(path.join(outDir, "scw-error.json"), `${JSON.stringify(debug, null, 2)}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const matter = findMatter(args.registry, args.matterId);
  const outDir = args.outDir || path.join(labRoot(), "runs", matter.matterId, timestamp(), "scw");
  fs.mkdirSync(outDir, { recursive: true });

  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: !args.headed,
    acceptDownloads: false,
  });
  let page = context.pages()[0] || (await context.newPage());
  page.setDefaultTimeout(args.timeoutSec * 1000);

  try {
    page = await goToPublicSearch(context, page, args.headed, args.timeoutSec * 1000);
    await submitSearch(page, matter);
    const tableStatus = await waitForActuacionesTable(page);
    const rawRows = tableStatus === "ok" ? await extractActuaciones(page) : [];
    const actuaciones = rawRows.map(normalizeActuacion);
    const payload = {
      createdAt: new Date().toISOString().slice(0, 19),
      source: "scw-public-search",
      status: tableStatus,
      unavailableReason: tableStatus === "unavailable" ? "Expediente inexistente o no disponible para su consulta publica" : null,
      matterId: matter.matterId,
      expediente: matter.pjnNumeracion,
      fuero: matter.fuero,
      numero: matter.numero,
      anio: matter.anio,
      subexpediente: matter.subexpediente || null,
      caratula: matter.caratula || matter.matterName || "",
      url: page.url(),
      selector: 'table[id="expediente:action-table"]',
      actuacionesCount: actuaciones.length,
      documentCount: actuaciones.filter((row) => row.hasDocument).length,
      actuaciones,
    };
    fs.writeFileSync(path.join(outDir, "scw-actuaciones.json"), `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    writeMarkdown(path.join(outDir, "scw-actuaciones.md"), payload);
    console.log(JSON.stringify({
      status: tableStatus,
      matterId: matter.matterId,
      actuaciones: payload.actuacionesCount,
      documents: payload.documentCount,
      outDir,
    }, null, 2));
  } catch (error) {
    await writeDebugArtifacts(outDir, page, error);
    if (args.keepOpenOnError && args.headed) {
      console.error(`ERROR: ${error && error.message ? error.message : error}`);
      console.error(`Keeping browser open for ${args.errorPauseSec} seconds for inspection.`);
      await page.waitForTimeout(Math.max(1, args.errorPauseSec) * 1000);
    }
    throw error;
  } finally {
    await context.close();
  }
}

main().catch((error) => {
  console.error(`ERROR: ${error && error.message ? error.message : error}`);
  process.exit(1);
});
