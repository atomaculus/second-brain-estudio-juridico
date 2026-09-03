const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const SCW_URL = "https://scw.pjn.gov.ar/scw/consultaListaRelacionados.seam";

function labRoot() {
  return path.resolve(__dirname, "..");
}

function localStateRoot() {
  if (process.env.PJN_LOCAL_STATE_DIR) return path.resolve(process.env.PJN_LOCAL_STATE_DIR);
  const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  return path.join(base, "SegundoCerebroJuridico", "PJN");
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
    profileDir: path.join(localStateRoot(), "browser-profile"),
    outDir: path.join(localStateRoot(), "runs", "scw-favoritos", timestamp()),
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--headed") args.headed = true;
    else if (arg === "--timeout-sec") args.timeoutSec = Number(argv[++i]);
    else if (arg === "--profile-dir") args.profileDir = argv[++i];
    else if (arg === "--out-dir") args.outDir = argv[++i];
  }
  return args;
}

function parseExpediente(value) {
  const match = String(value || "").match(/^([A-Z]+)\s+0*(\d+)\/(\d{4})(?:\/(\w+))?/);
  if (!match) return {};
  return {
    fuero: match[1],
    numero: Number(match[2]),
    anio: Number(match[3]),
    subexpediente: match[4] || null,
  };
}

async function waitForScw(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const text = await page.locator("body").innerText().catch(() => "");
    if (/Sistema de Consulta Web/i.test(text) && !/Ingresar a Poder Judicial/i.test(text)) return;
    await page.waitForTimeout(1000);
  }
  throw new Error("SCW did not load. If login is visible, complete it and rerun.");
}

async function goToFavorites(page) {
  const favoriteLink = page.locator("a", { hasText: /^Favoritos$/ }).first();
  if (await favoriteLink.count()) {
    const href = await favoriteLink.evaluate((anchor) => anchor.href);
    await page.goto(href, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);
    return;
  }
  await page.goto("https://scw.pjn.gov.ar/scw/consultaListaFavoritos.seam", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(3000);
}

async function extractCurrentPage(page) {
  return await page.evaluate(() => {
    const tables = [...document.querySelectorAll("table")];
    const table = tables.find((item) => {
      const text = item.innerText || "";
      return /Expediente/i.test(text) && /Car.tula/i.test(text);
    });
    if (!table) return [];
    const rows = [...table.querySelectorAll("tr")].map((row) =>
      [...row.querySelectorAll("th,td")].map((cell) => cell.innerText.trim())
    );
    const bodyRows = rows.filter((row) => /^[A-Z]{2,}\s+0*\d+\/\d{4}/.test(row[0] || ""));
    return bodyRows.map((row) => ({
      expediente: row[0] || "",
      dependencia: row[1] || "",
      caratula: row[2] || "",
      situacion: row[3] || "",
      ultimaActuacion: row[4] || "",
      source: "scw-favoritos",
    }));
  });
}

async function paginationLabels(page) {
  return await page
    .locator("a")
    .evaluateAll((anchors) =>
      [...new Set(anchors.map((a) => a.innerText.trim()).filter((text) => /^\d+$/.test(text)))]
        .map(Number)
        .sort((a, b) => a - b)
    )
    .catch(() => []);
}

async function extractAllPages(page) {
  const seen = new Map();
  const addRows = async () => {
    const rows = await extractCurrentPage(page);
    for (const row of rows) seen.set(`${row.expediente}|${row.caratula}`, row);
  };

  await addRows();
  const labels = await paginationLabels(page);
  const pages = labels.length ? labels : [];
  for (const label of pages) {
    const pageLink = await page
      .locator("a")
      .evaluateAll(
        (anchors, wanted) => {
          const anchor = anchors.find((item) => item.innerText.trim() === String(wanted));
          if (!anchor) return null;
          return { id: anchor.id, text: anchor.innerText.trim() };
        },
        label
      )
      .catch(() => null);
    if (!pageLink || !pageLink.id) continue;
    await page.evaluate((id) => {
      const anchor = document.getElementById(id);
      if (!anchor) throw new Error(`pagination link not found: ${id}`);
      anchor.click();
    }, pageLink.id);
    await page.waitForTimeout(3500);
    await addRows();
  }
  return [...seen.values()].map((item) => ({ ...item, ...parseExpediente(item.expediente) }));
}

function writeMarkdown(file, rows) {
  const lines = [
    "---",
    "type: scw-favorites",
    `created: ${new Date().toISOString().slice(0, 19)}`,
    "---",
    "",
    "# Expedientes Favoritos SCW",
    "",
    `Total: ${rows.length}`,
    "",
    "| Expediente | Dependencia | Caratula | Situacion | Ult. Act. |",
    "|---|---|---|---|---|",
    ...rows.map((row) =>
      `| ${row.expediente} | ${row.dependencia} | ${row.caratula} | ${row.situacion} | ${row.ultimaActuacion} |`
        .replace(/\n/g, " ")
    ),
    "",
  ];
  fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  fs.mkdirSync(args.outDir, { recursive: true });
  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: !args.headed,
  });
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(SCW_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
  await waitForScw(page, args.timeoutSec * 1000);
  await goToFavorites(page);
  await waitForScw(page, 30000);
  const rows = await extractAllPages(page);
  const output = {
    createdAt: new Date().toISOString().slice(0, 19),
    sourceUrl: page.url(),
    count: rows.length,
    favorites: rows,
  };
  fs.writeFileSync(path.join(args.outDir, "favorites.json"), `${JSON.stringify(output, null, 2)}\n`, "utf8");
  writeMarkdown(path.join(args.outDir, "favorites.md"), rows);
  await context.close();
  console.log(JSON.stringify({ status: "ok", count: rows.length, outDir: args.outDir }, null, 2));
}

main().catch((error) => {
  console.error(`ERROR: ${error && error.message ? error.message : error}`);
  process.exit(1);
});
