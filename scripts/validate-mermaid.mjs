#!/usr/bin/env node
/**
 * Validate every Mermaid diagram in a rendered Hugo site.
 *
 * Walks the given public directory (default: blog/public), extracts every
 * `<pre class="mermaid">…</pre>` block, HTML-decodes its contents, and calls
 * mermaid.parse() to check syntax. Exits 1 with per-block diagnostics on any
 * failure, 0 otherwise.
 *
 * Why post-Hugo and not raw markdown: many diagrams are wrapped in Hugo
 * shortcodes (papers/landscape, etc.) that inject template fragments into
 * the diagram body. Bugs like the Paper 15 case (duplicate `quadrantChart`
 * from shortcode + user content) only surface after Hugo renders.
 *
 * Why mermaid + jsdom and not @mermaid-js/parser: the Langium-based parser
 * only covers a subset of diagram types (info, pie, packet, architecture,
 * gitGraph, radar, treemap). quadrantChart and flowchart — the two most
 * common on Frank — still go through the legacy parser embedded in the
 * mermaid package itself.
 */
import { readdir, readFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
// Node 21+ ships its own read-only `navigator`; jsdom's is only assigned where missing.
if (!('navigator' in globalThis)) globalThis.navigator = dom.window.navigator;
globalThis.DOMPurify = (await import('dompurify')).default(dom.window);

const mermaid = (await import('mermaid')).default;

async function* walkHtml(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walkHtml(path);
    else if (entry.name.endsWith('.html')) yield path;
  }
}

function htmlDecode(s) {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#34;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

function extractMermaid(html) {
  // The character classes below exclude `>` so attribute matching can't bleed
  // past the opener and into the diagram body (which contains unescaped `>`
  // from Mermaid arrows like `-->`). Use `[^>"']` instead of `[^"']` for
  // attribute-internal text; non-greedy quantifiers reinforce that the
  // opening tag should be as short as possible.
  const blocks = [];
  const re = /<pre[^>]*?class=["']?[^>"']*?\bmermaid\b[^>"']*?["']?[^>]*?>([\s\S]*?)<\/pre>/gi;
  for (const m of html.matchAll(re)) {
    blocks.push(htmlDecode(m[1]).trim());
  }
  return blocks;
}

const publicDir = process.argv[2] ?? 'blog/public';
let total = 0;
const failures = [];

for await (const file of walkHtml(publicDir)) {
  const html = await readFile(file, 'utf8');
  const blocks = extractMermaid(html);
  for (const [i, src] of blocks.entries()) {
    total++;
    try {
      await mermaid.parse(src);
    } catch (e) {
      failures.push({
        file: relative(process.cwd(), file),
        index: i + 1,
        message: e?.message ?? String(e),
        source: src,
      });
    }
  }
}

if (failures.length > 0) {
  for (const f of failures) {
    console.error(`\nFAIL: ${f.file} (mermaid block ${f.index})`);
    console.error(`  Error: ${f.message.split('\n')[0]}`);
    console.error(`  Source:`);
    for (const line of f.source.split('\n')) console.error(`    ${line}`);
  }
  console.error(`\n${failures.length} of ${total} mermaid block(s) failed to parse.`);
  process.exit(1);
}

console.log(`Validated ${total} mermaid block(s) — all OK.`);
