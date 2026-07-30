#!/usr/bin/env node
// validate_mermaid_layout.mjs — the blocking mermaid WIDTH gate (MMD-3).
//
// Renders every mermaid diagram in the BUILT site (public/) with the site's
// own mermaid bundle inside a real headless Chrome, reads each diagram's
// natural width, and fails the build when one exceeds the budget.
//
// Usage:
//   node scripts/validate_mermaid_layout.mjs --public <site>/public [--max-width 1400]
//
//   --public      Hugo's output directory; walked for **/*.html.
//   --max-width   px budget (default 1400 — ~2x Hextra's 672px content column:
//                 a diagram needing more than two column-widths of scrolling
//                 cannot be held in the reader's head). 0 DISABLES the gate:
//                 diagrams are still counted and listed, loudly, but no
//                 browser is invoked and the exit code is 0.
//
// Exit codes: 0 pass/disabled · 1 over budget or render failure · 2 environment/usage.
//
// Per-diagram waiver: a `%% blog-craft: wide-ok — <reason>` comment line in
// the diagram source (`%%` is a mermaid comment, so it ships invisibly).
//
// WHY THIS SHAPE (each point verified during design, 2026-07-28):
//
//  - Built HTML, not markdown. Shortcode-emitted diagrams (papers/landscape
//    quadrantCharts) never appear as fenced blocks — exactly where frank's
//    real breakage lived (77e68e37: abbr markers injected into quadrantChart
//    source, missed by every markdown-level check). Findings are reported by
//    page URL + block index; built HTML has no source line numbers.
//
//  - A real browser, not jsdom. Mermaid derives every node's size from text
//    metrics; under jsdom getBBox/getComputedTextLength do not exist,
//    getBoundingClientRect() is 0x0, and mermaid.render() throws
//    `CSSStyleSheet is not defined`. A jsdom "width" would be fiction.
//    (Syntax checking on jsdom is legitimate — width measurement is not,
//    which is why this stays a separate tool from the syntax gate.)
//
//  - The SITE'S OWN bundle, from public/js/mermaid.*.js. Measuring with any
//    other mermaid build measures a different site. This is also why the
//    `mermaid` npm package is not a dependency.
//
//  - Zero npm dependencies. Node >= 22 (preinstalled on ubuntu-latest) ships
//    a global WebSocket, so headless Chrome is driven over raw CDP: no
//    package.json, no npm install, no supply-chain surface added to any
//    consumer blog. (It is also why the budget arrives as a flag rather than
//    being read from .blog-craft.yaml — zero-dep means no YAML parser; the CI
//    template renders the budget from config at materialization time.)
//
//  - Discovery, never a hardcoded browser path. The ubuntu-24.04 image
//    preinstalls Google Chrome and Chromium but defines NO CHROME_BIN (only
//    CHROMEWEBDRIVER/EDGEWEBDRIVER/GECKOWEBDRIVER), and ubuntu-latest rolls
//    to newer images. Resolution order: $CHROME_BIN, then google-chrome,
//    google-chrome-stable, chromium, chromium-browser on PATH.
//
//  - Width is read from the rendered SVG's inline `style="max-width: <n>px"`
//    — the exact value mermaid writes and mermaid-view.css keys off, so the
//    gate and the renderer cannot disagree (viewBox width is the fallback).
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

const USAGE =
  "usage: validate_mermaid_layout.mjs --public <dir> [--max-width <px>]  (0 disables the gate)";

function fail(code, msg) {
  console.error(msg);
  process.exit(code);
}

// ------------------------------------------------------------ browser discovery

const PATH_CANDIDATES = [
  "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
];

function isExecutable(p) {
  try {
    fs.accessSync(p, fs.constants.X_OK);
    return fs.statSync(p).isFile();
  } catch {
    return false;
  }
}

function whichOnPath(name, envPath) {
  for (const dir of (envPath || "").split(path.delimiter)) {
    if (!dir) continue;
    const p = path.join(dir, name);
    if (isExecutable(p)) return p;
  }
  return null;
}

function discoverBrowser(env) {
  const cb = env.CHROME_BIN;
  if (cb && isExecutable(cb)) return cb;
  for (const name of PATH_CANDIDATES) {
    const p = whichOnPath(name, env.PATH);
    if (p) return p;
  }
  fail(2,
    "mermaid layout gate: no Chrome/Chromium executable found.\n" +
    `Looked for, in order: $CHROME_BIN${cb ? ` (=${cb}, not an executable file)` : " (unset)"}, ` +
    PATH_CANDIDATES.join(", ") + " (each resolved on PATH).\n" +
    "Set CHROME_BIN to a Chrome/Chromium binary, or install one on PATH.\n" +
    "(ubuntu-24.04 runners preinstall Google Chrome and Chromium but define no\n" +
    "CHROME_BIN, and ubuntu-latest rolls to newer images — hence discovery over\n" +
    "a candidate list, never a hardcoded path.)");
}

// ------------------------------------------------------------------------ main

function parseArgs(argv) {
  const opts = { public: null, maxWidth: 1400 };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--public") opts.public = argv[++i];
    else if (a === "--max-width") {
      const v = Number(argv[++i]);
      if (!Number.isFinite(v) || v < 0) fail(2, `mermaid layout gate: --max-width must be a non-negative number, got ${argv[i]}\n${USAGE}`);
      opts.maxWidth = v;
    } else if (a === "--help" || a === "-h") {
      console.log(USAGE);
      process.exit(0);
    } else fail(2, `mermaid layout gate: unknown argument ${a}\n${USAGE}`);
  }
  if (!opts.public) fail(2, `mermaid layout gate: --public is required\n${USAGE}`);
  return opts;
}

function* walkHtml(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* walkHtml(p);
    else if (e.isFile() && e.name.endsWith(".html")) yield p;
  }
}

// Built HTML escapes the diagram source (the render hook htmlEscapes .Inner):
// `-->` arrives as `--&gt;`. Undo that, or every real diagram fails to parse.
function decodeEntities(s) {
  return s
    .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

// `%%` is a mermaid comment, so the waiver ships invisibly with the diagram.
const WAIVER_RE = /^\s*%%\s*blog-craft:\s*wide-ok\b/m;

function pageUrl(publicDir, file) {
  const rel = path.relative(publicDir, file).split(path.sep).join("/");
  return rel.endsWith("index.html")
    ? "/" + rel.slice(0, -"index.html".length)
    : "/" + rel;
}

// Every <pre class="mermaid"> body in public/**/*.html — the render hook's
// output AND shortcode-emitted diagrams (papers/landscape quadrantCharts),
// which never appear as fenced blocks in markdown. Reported by page URL +
// 1-based block index: built HTML has no source line numbers.
function extractDiagrams(publicDir) {
  const diagrams = [];
  const pages = new Set();
  for (const file of walkHtml(publicDir)) {
    const doc = fs.readFileSync(file, "utf8");
    const page = pageUrl(publicDir, file);
    let index = 0;
    for (const m of doc.matchAll(/<pre\b([^>]*)>([\s\S]*?)<\/pre>/gi)) {
      const cls = /class\s*=\s*"([^"]*)"/i.exec(m[1]);
      if (!cls || !/(^|\s)mermaid(\s|$)/.test(cls[1])) continue;
      index += 1;
      const source = decodeEntities(m[2]).trim();
      diagrams.push({ page, index, source, waived: WAIVER_RE.test(source) });
    }
    if (index > 0) pages.add(page);
  }
  return { diagrams, pageCount: pages.size };
}

function locateBundle(publicDir) {
  const jsDir = path.join(publicDir, "js");
  let names = [];
  try {
    names = fs.readdirSync(jsDir).filter((n) => /^mermaid\..+\.js$/.test(n));
  } catch { /* handled below */ }
  if (names.length === 0) {
    fail(2,
      `mermaid layout gate: no mermaid bundle found at ${jsDir}/mermaid.*.js — the\n` +
      "gate renders with the SITE'S OWN bundle so measured widths match exactly what\n" +
      "readers see. Build the site first (hugo --minify) on a page with a diagram.");
  }
  names.sort();
  const min = names.find((n) => n.startsWith("mermaid.min."));
  return path.join(jsDir, min || names[0]);
}

// ------------------------------------------------- CDP: drive headless Chrome
//
// Node >= 22 ships a global WebSocket (undici), which is the whole reason no
// puppeteer is needed: launch Chrome with --remote-debugging-port=0, read the
// resolved ws endpoint off stderr, and speak flat-mode CDP directly.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function withTimeout(promise, ms, what) {
  let t;
  const timer = new Promise((_, rej) => {
    t = setTimeout(() => rej(new Error(`timed out after ${ms}ms: ${what}`)), ms);
  });
  return Promise.race([promise, timer]).finally(() => clearTimeout(t));
}

class Cdp {
  constructor(url) {
    this.url = url;
    this.nextId = 0;
    this.pending = new Map();
  }

  async connect(timeoutMs = 15000) {
    this.ws = new WebSocket(this.url);
    await withTimeout(new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", () => reject(new Error(`could not connect to ${this.url}`)), { once: true });
    }), timeoutMs, "connecting to the DevTools websocket");
    this.ws.addEventListener("message", (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const entry = msg.id !== undefined && this.pending.get(msg.id);
      if (!entry) return; // CDP events are unsolicited; we poll instead of subscribing
      this.pending.delete(msg.id);
      if (msg.error) entry.reject(new Error(`CDP ${entry.method}: ${msg.error.message}`));
      else entry.resolve(msg.result);
    });
  }

  send(method, params = {}, sessionId = undefined, timeoutMs = 30000) {
    const id = ++this.nextId;
    const p = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject, method }));
    this.ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    return withTimeout(p, timeoutMs, `CDP ${method}`);
  }

  close() {
    try { this.ws?.close(); } catch { /* already gone */ }
  }
}

async function launchBrowser(bin, profileDir) {
  // --no-sandbox --disable-dev-shm-usage: required on CI runners (root user,
  // tiny /dev/shm). Fresh --user-data-dir: never touch (or lock against) a
  // real profile. Port 0: let Chrome pick, then read the resolved endpoint.
  const args = [
    "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
    `--user-data-dir=${profileDir}`, "--no-first-run", "--no-default-browser-check",
    "--remote-debugging-port=0", "about:blank",
  ];
  const proc = spawn(bin, args, { stdio: ["ignore", "ignore", "pipe"] });
  const wsUrl = await withTimeout(new Promise((resolve, reject) => {
    let buf = "";
    proc.stderr.on("data", (d) => {
      buf += d;
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) resolve(m[1]);
    });
    proc.on("error", (e) => reject(new Error(`could not launch ${bin}: ${e.message}`)));
    proc.on("exit", (code) => reject(new Error(`browser exited (code ${code}) before DevTools was ready:\n${buf.slice(-2000)}`)));
  }), 30000, `waiting for "DevTools listening on ws://…" from ${bin}`);
  return { proc, wsUrl };
}

// Runs INSIDE the page. The natural width is the inline
// `style="max-width: <n>px"` mermaid writes on the rendered svg — the exact
// value mermaid-view.css keys off — with the viewBox width as fallback.
function renderExpression(id, source) {
  return `(async () => {
    try {
      const r = await window.mermaid.render(${JSON.stringify(id)}, ${JSON.stringify(source)});
      const host = document.createElement("div");
      host.innerHTML = r.svg;
      document.body.appendChild(host);
      const svg = host.querySelector("svg");
      if (!svg) return { error: "mermaid.render produced no <svg>" };
      const m = /max-width:\\s*([0-9.]+)px/.exec(svg.getAttribute("style") || "");
      if (m) return { width: parseFloat(m[1]) };
      const vb = (svg.getAttribute("viewBox") || "").trim().split(/[\\s,]+/);
      if (vb.length === 4 && isFinite(parseFloat(vb[2]))) return { width: parseFloat(vb[2]) };
      return { error: "rendered svg has neither an inline max-width nor a viewBox" };
    } catch (e) {
      return { error: String((e && e.message) || e) };
    }
  })()`;
}

// Render every diagram in one page that has the site's bundle loaded, and
// return [{width} | {error}] in input order. One browser, one page, N renders.
async function measureAll(browserBin, bundlePath, diagrams) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mermaid-layout-gate-"));
  const harness = path.join(tmp, "harness.html");
  fs.writeFileSync(harness,
    `<!doctype html><html><head><meta charset="utf-8"><script src="${pathToFileURL(bundlePath)}"></script></head><body></body></html>`);
  let proc, cdp;
  try {
    let wsUrl;
    ({ proc, wsUrl } = await launchBrowser(browserBin, path.join(tmp, "profile")));
    cdp = new Cdp(wsUrl);
    await cdp.connect();
    const { targetId } = await cdp.send("Target.createTarget", { url: pathToFileURL(harness).href });
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });

    // Poll for readiness rather than racing load events we might have missed.
    const deadline = Date.now() + 20000;
    for (;;) {
      const r = await cdp.send("Runtime.evaluate", {
        expression: "document.readyState === 'complete' && typeof window.mermaid !== 'undefined'",
        returnByValue: true,
      }, sessionId);
      if (r.result?.value === true) break;
      if (Date.now() > deadline) {
        throw new Error(`the mermaid bundle (${path.basename(bundlePath)}) never defined window.mermaid in the page`);
      }
      await sleep(100);
    }
    await cdp.send("Runtime.evaluate", {
      expression: "window.mermaid.initialize && window.mermaid.initialize({ startOnLoad: false }); true",
      returnByValue: true,
    }, sessionId);

    const results = [];
    for (let i = 0; i < diagrams.length; i++) {
      const r = await cdp.send("Runtime.evaluate", {
        expression: renderExpression(`blogcraft-gate-${i}`, diagrams[i].source),
        awaitPromise: true,
        returnByValue: true,
      }, sessionId, 60000);
      if (r.exceptionDetails) {
        results.push({ error: r.exceptionDetails.exception?.description || r.exceptionDetails.text || "render evaluation threw" });
      } else {
        results.push(r.result?.value ?? { error: "render evaluation returned nothing" });
      }
    }
    return results;
  } finally {
    cdp?.close();
    if (proc && proc.exitCode === null) {
      proc.kill();
      // Wait for the exit (bounded) — rmSync racing a still-dying Chrome that
      // is writing its profile throws ENOTEMPTY.
      await new Promise((resolve) => {
        const t = setTimeout(resolve, 3000);
        proc.once("exit", () => { clearTimeout(t); resolve(); });
      });
    }
    // Best-effort: a leftover tmp dir must never override the gate's verdict.
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* OS-cleaned tmp */ }
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  let stat;
  try {
    stat = fs.statSync(opts.public);
  } catch { /* handled below */ }
  if (!stat || !stat.isDirectory()) {
    fail(2, `mermaid layout gate: public dir not found: ${opts.public} — run \`hugo\` first;\nthis gate measures the BUILT site, not the markdown.`);
  }
  const { diagrams, pageCount } = extractDiagrams(opts.public);

  if (opts.maxWidth === 0) {
    // A disabled gate must still SCAN and still be LOUD about how far behind
    // it is (frank 77e68e37: "a gate nobody runs reports nothing"). It only
    // skips the browser: exits 0, never build-breaking.
    console.error(
      `GATE DISABLED (quality.mermaid_max_width: 0) — ${diagrams.length} diagram(s) ` +
      `across ${pageCount} page(s) NOT measured (no browser invoked)`);
    for (const d of diagrams) {
      console.error(`  ${d.page} #${d.index}${d.waived ? " (wide-ok waived)" : ""}`);
    }
    process.exit(0);
  }

  if (diagrams.length === 0) {
    console.log(`MERMAID LAYOUT OK: 0 diagrams under ${opts.public} (no browser invoked)`);
    process.exit(0);
  }

  if (typeof WebSocket === "undefined") {
    // Node 22+ ships a global WebSocket — the whole zero-dependency CDP story.
    fail(2, `mermaid layout gate: needs Node >= 22 (global WebSocket); this is ${process.version}.`);
  }
  const bundle = locateBundle(opts.public);
  const browser = discoverBrowser(process.env);

  const toMeasure = diagrams.filter((d) => !d.waived);
  const waived = diagrams.length - toMeasure.length;
  let results;
  try {
    results = await measureAll(browser, bundle, toMeasure);
  } catch (e) {
    fail(2, `mermaid layout gate: could not measure: ${e.message}`);
  }

  const findings = [];
  let widest = 0;
  results.forEach((res, i) => {
    const d = toMeasure[i];
    if (res.error) {
      // A diagram that fails to render is an ERROR, not a silent skip — the
      // gate must not go blind exactly where the site is broken.
      findings.push(`  ${d.page} #${d.index}: RENDER ERROR — ${res.error}`);
    } else {
      const w = Math.round(res.width);
      widest = Math.max(widest, w);
      if (w > opts.maxWidth) {
        findings.push(`  ${d.page} #${d.index}: ${w}px > ${opts.maxWidth}px (${w - opts.maxWidth}px over)`);
      }
    }
  });

  if (findings.length > 0) {
    console.error(
      `MERMAID LAYOUT CHECK FAILED — ${findings.length} of ${diagrams.length} diagram(s) ` +
      `(budget quality.mermaid_max_width: ${opts.maxWidth}px${waived ? `, ${waived} waived` : ""})`);
    for (const f of findings) console.error(f);
    console.error(
      "\n  A diagram wider than the budget cannot be followed by scrolling. Restructure it\n" +
      "  (flowchart TD is usually far narrower than LR), waive this one with a\n" +
      "  `%% blog-craft: wide-ok — <reason>` comment in the diagram source, or set\n" +
      "  `quality.mermaid_max_width: 0` to disable the gate.");
    process.exit(1);
  }
  console.log(
    `MERMAID LAYOUT OK: ${toMeasure.length} diagram(s) across ${pageCount} page(s) ` +
    `within ${opts.maxWidth}px (widest ${widest}px${waived ? `, ${waived} waived` : ""})`);
  process.exit(0);
}

await main();
