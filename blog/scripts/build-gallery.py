#!/usr/bin/env python3
"""Build a self-contained HTML gallery of curation candidates for easy selection.

The curation flow (scripts/gen-character-sheet.py, or generate-images.py --count N)
archives N variants under .regen-archive/<key>/<key>-<sha>.png plus a contact
sheet. A contact sheet is fine for a glance; this builds a browsable, click-to-zoom
gallery you can open full-screen to compare candidates in detail before promoting one.

Usage:  python scripts/build-gallery.py [KEY]      (default KEY: "reference")
Writes: .regen-archive/<KEY>/gallery.html  (self-contained; images inlined as WebP)
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import yaml
from PIL import Image


def find_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".blog-craft.yaml").is_file():
            return d
    raise SystemExit("no .blog-craft.yaml found from " + str(start))


def main(argv: list[str]) -> int:
    key = argv[0] if argv else "reference"
    root = find_root(Path(__file__).resolve().parent)
    arch = root / ".regen-archive" / key
    cands = sorted(arch.glob(f"{key}-*.png"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise SystemExit(f"no candidates at {arch}/{key}-*.png — run gen-character-sheet.py first")

    try:
        cfg = yaml.safe_load((root / ".blog-craft.yaml").read_text())
        title = (cfg.get("project", {}) or {}).get("title") or "blog-craft"
    except Exception:
        title = "blog-craft"

    cards = []
    for i, p in enumerate(cands, 1):
        sha = p.stem.split("-", 1)[1]
        im = Image.open(p).convert("RGB")
        if im.width > 1000:
            im = im.resize((1000, round(im.height * 1000 / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=80, method=6)
        uri = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
        cards.append((i, sha, uri))

    figs = "\n".join(
        f'''<figure class="card">
      <button class="shot" type="button" data-num="{i:02d}" aria-label="Enlarge candidate {i:02d}">
        <img src="{uri}" alt="candidate {i:02d}" loading="lazy" decoding="async">
      </button>
      <figcaption><span class="num">{i:02d}</span><code class="sha">{sha}</code></figcaption>
    </figure>'''
        for i, sha, uri in cards
    )

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Choose — {title} ({key})</title>
<style>
  :root {{
    --bg:#e6e7ea;--panel:#f3f3f1;--panel-2:#ececeb;--ink:#161a20;--muted:#59636f;
    --accent:#1f63d6;--line:#ccd1d7;
    --serif:"Iowan Old Style","Hoefler Text",Palatino,Georgia,serif;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  }}
  @media (prefers-color-scheme:dark){{:root{{
    --bg:#0b0e13;--panel:#141a22;--panel-2:#0f141b;--ink:#e9edf3;--muted:#93a0b2;
    --accent:#5eb0ff;--line:#233042;}}}}
  *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
    font-family:var(--sans);padding:clamp(1.25rem,4vw,3rem)}}
  header{{max-width:66ch;margin:0 auto clamp(1.5rem,4vw,2.5rem)}}
  .eyebrow{{font:600 .72rem/1 var(--sans);letter-spacing:.22em;text-transform:uppercase;
    color:var(--accent);margin:0 0 .8rem}}
  h1{{font:600 clamp(2rem,6vw,3.2rem)/1.02 var(--serif);letter-spacing:-.01em;
    text-wrap:balance;margin:0 0 .6rem}}
  .lede{{font-size:1.02rem;line-height:1.6;color:var(--muted);margin:0;max-width:60ch}}
  .lede code{{font-family:var(--mono);font-size:.86em;background:var(--panel-2);
    border:1px solid var(--line);border-radius:5px;padding:.06em .38em;color:var(--ink)}}
  .grid{{max-width:1500px;margin:0 auto;display:grid;gap:clamp(.9rem,2vw,1.5rem);
    grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr))}}
  .card{{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:12px;
    overflow:hidden}}
  .shot{{display:block;width:100%;padding:0;border:0;background:var(--panel-2);
    cursor:zoom-in;line-height:0}}
  .shot img{{width:100%;height:auto;display:block}}
  .shot:focus-visible{{outline:3px solid var(--accent);outline-offset:-3px}}
  figcaption{{display:flex;align-items:center;gap:.6rem;padding:.6rem .85rem;
    border-top:1px solid var(--line)}}
  .num{{font:650 1.15rem/1 var(--serif);color:var(--accent);
    font-variant-numeric:tabular-nums;min-width:1.6em}}
  .sha{{font-family:var(--mono);font-size:.82rem;color:var(--muted)}}
  .lb{{position:fixed;inset:0;z-index:50;display:none;place-items:center;padding:2.5vmin;
    background:rgb(4 7 11/.86);backdrop-filter:blur(3px);cursor:zoom-out}}
  .lb.on{{display:grid}}
  .lb img{{max-width:96vw;max-height:92vh;border-radius:8px;box-shadow:0 12px 60px rgb(0 0 0/.6)}}
  .lb .tag{{position:fixed;top:1rem;left:1rem;font:650 .9rem/1 var(--mono);color:#fff;
    background:var(--accent);padding:.4rem .7rem;border-radius:6px}}
  @media (prefers-reduced-motion:no-preference){{.lb.on{{animation:f .18s ease}}
    @keyframes f{{from{{opacity:0}}to{{opacity:1}}}}}}
</style></head><body>
  <header>
    <p class="eyebrow">blog-craft · character curation</p>
    <h1>Choose a character sheet</h1>
    <p class="lede">{len(cards)} candidates for <code>{key}</code>. Click any sheet to enlarge.
      Pick the best one and promote it:
      <code>cp .regen-archive/{key}/{key}-&lt;sha&gt;.png static/images/reference.png</code></p>
  </header>
  <main class="grid">
    {figs}
  </main>
  <div class="lb" id="lb"><span class="tag" id="lbtag"></span><img id="lbimg" alt=""></div>
<script>
  (function(){{
    var lb=document.getElementById("lb"),img=document.getElementById("lbimg"),
        tag=document.getElementById("lbtag");
    document.querySelectorAll(".shot").forEach(function(b){{
      b.addEventListener("click",function(){{
        img.src=b.querySelector("img").src;
        tag.textContent="candidate "+b.dataset.num;lb.classList.add("on");}});}});
    function close(){{lb.classList.remove("on");img.src="";}}
    lb.addEventListener("click",close);
    document.addEventListener("keydown",function(e){{if(e.key==="Escape")close();}});
  }})();
</script></body></html>'''

    out = arch / "gallery.html"
    out.write_text(html)
    print(f"{len(cards)} candidates -> {out.relative_to(root)}  ({out.stat().st_size/1024/1024:.2f} MB)")
    print(f"open: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
