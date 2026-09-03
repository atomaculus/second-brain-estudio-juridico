const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const DEFAULT_SESSION_KEY = "oidc.user:https://sso.pjn.gov.ar/auth/realms/pjn:pjn-portal";
const DEFAULT_START_URL = "https://portalpjn.pjn.gov.ar/";

function labRoot() {
  return path.resolve(__dirname, "..");
}

function localStateRoot() {
  if (process.env.PJN_LOCAL_STATE_DIR) return path.resolve(process.env.PJN_LOCAL_STATE_DIR);
  const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  return path.join(base, "SegundoCerebroJuridico", "PJN");
}

function parseArgs(argv) {
  const args = {
    headed: false,
    timeoutSec: 120,
    minTtlSec: 60,
    profileDir: path.join(localStateRoot(), "browser-profile"),
    cacheFile: path.join(localStateRoot(), "pjn-token-cache.json"),
    sessionKey: DEFAULT_SESSION_KEY,
    startUrl: DEFAULT_START_URL,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--headed") args.headed = true;
    else if (arg === "--timeout-sec") args.timeoutSec = Number(argv[++i]);
    else if (arg === "--min-ttl-sec") args.minTtlSec = Number(argv[++i]);
    else if (arg === "--profile-dir") args.profileDir = argv[++i];
    else if (arg === "--cache-file") args.cacheFile = argv[++i];
    else if (arg === "--session-key") args.sessionKey = argv[++i];
    else if (arg === "--start-url") args.startUrl = argv[++i];
  }
  return args;
}

function ttlSeconds(user) {
  if (!user || !user.expires_at) return -1;
  return Number(user.expires_at) - Math.floor(Date.now() / 1000);
}

function clientIdFromSessionKey(sessionKey) {
  return sessionKey.includes(":") ? sessionKey.split(":").pop() : "pjn-sne";
}

async function readSessionUser(page, sessionKey) {
  try {
    const raw = await page.evaluate((key) => window.sessionStorage.getItem(key), sessionKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    if (message.includes("Execution context was destroyed") || message.includes("navigation")) {
      return null;
    }
    throw error;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  fs.mkdirSync(args.profileDir, { recursive: true });
  const context = await chromium.launchPersistentContext(args.profileDir, {
    headless: !args.headed,
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(args.startUrl, { waitUntil: "domcontentloaded" });

  const deadline = Date.now() + args.timeoutSec * 1000;
  let user = null;
  let staleSessionCleared = false;
  while (Date.now() < deadline) {
    user = await readSessionUser(page, args.sessionKey);
    if (user && ttlSeconds(user) >= args.minTtlSec) break;
    if (user && ttlSeconds(user) < args.minTtlSec && !staleSessionCleared) {
      // An expired OIDC object can remain in sessionStorage. Reloading it once
      // per second creates an endless visible refresh loop and never gives the
      // operator a stable login screen. Remove only that stale session and let
      // the portal rebuild it from SSO or from the manual login.
      await page.evaluate((key) => window.sessionStorage.removeItem(key), args.sessionKey);
      staleSessionCleared = true;
      user = null;
      await page.reload({ waitUntil: "domcontentloaded" });
    }
    await page.waitForTimeout(1000);
  }

  if (!user) {
    await context.close();
    console.error("ERROR: No PJN OIDC session found. Run with --headed and log in manually.");
    process.exit(1);
  }

  const ttl = ttlSeconds(user);
  if (ttl < args.minTtlSec) {
    await context.close();
    console.error(`ERROR: PJN token found but TTL is too short: ${ttl}s`);
    process.exit(1);
  }

  if (!user.access_token) {
    await context.close();
    console.error("ERROR: OIDC session exists but access_token is missing");
    process.exit(1);
  }

  fs.mkdirSync(path.dirname(args.cacheFile), { recursive: true });
  const cache = {
    createdAt: new Date().toISOString().slice(0, 19),
    source: `${args.startUrl} sessionStorage ${args.sessionKey}`,
    session_key: args.sessionKey,
    client_id: user.client_id || clientIdFromSessionKey(args.sessionKey),
    token_type: user.token_type || "bearer",
    scope: user.scope,
    expires_at: user.expires_at,
    refresh_expires_at: user.refresh_expires_at || (user.refresh_expires_in ? Math.floor(Date.now() / 1000) + Number(user.refresh_expires_in) : undefined),
    access_token: user.access_token,
  };
  for (const key of ["refresh_token", "id_token", "session_state", "profile"]) {
    if (user[key]) cache[key] = user[key];
  }
  fs.writeFileSync(args.cacheFile, `${JSON.stringify(cache, null, 2)}\n`, "utf8");
  await context.close();

  console.log(JSON.stringify({
    status: "ok",
    cacheFile: args.cacheFile,
    expires_at: cache.expires_at,
    ttl_seconds: ttl,
  }, null, 2));
}

main().catch((error) => {
  console.error(`ERROR: ${error && error.message ? error.message : error}`);
  process.exit(1);
});
