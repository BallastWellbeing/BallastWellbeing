#!/usr/bin/env python3
"""
Render the Open Graph share card.

Rendered in Chromium rather than drawn in Pillow so it uses the real Source
Serif 4 and the real mark geometry — the same files the site serves. A share
card drawn with substitute fonts looks like someone else's brand.

    python3 tools/make_og.py     ->  static/og/default.png  (1200x630)
"""
import functools, http.server, pathlib, socketserver, threading
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "og" / "default.png"
PORT = 8731

# Tokens copied from static/styles/tokens.css. Kept literal because this runs
# standalone and must not depend on the build having happened.
SLATE_INK, PAPER, FOG, BRASS, DEEP_SEA_LIGHT = (
    "#17242E", "#FBFCFC", "#E4E9E8", "#B98A3E", "#45A08D")

HTML = f"""<!doctype html><meta charset="utf-8"><style>
  @font-face {{ font-family:"Source Serif 4"; src:url("/static/fonts/source-serif-4-variable.woff2") format("woff2-variations"); font-weight:200 900; }}
  @font-face {{ font-family:"Inter Tight"; src:url("/static/fonts/inter-tight-variable.woff2") format("woff2-variations"); font-weight:100 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1200px; height:630px; }}
  body {{ background:{SLATE_INK}; color:{PAPER}; display:flex; align-items:center;
          gap:64px; padding:0 86px; font-family:"Inter Tight",sans-serif; }}
  .copy {{ flex:1 1 auto; min-width:0; }}
  h1 {{ font-family:"Source Serif 4",Georgia,serif; font-weight:600;
        font-size:82px; line-height:1.05; letter-spacing:-0.015em; }}
  .rule {{ width:96px; height:3px; background:{BRASS}; margin:34px 0 30px; }}
  p {{ font-size:31px; line-height:1.4; color:{FOG}; max-width:19ch; font-weight:420; }}
  .mark {{ flex:0 0 340px; }}
  svg {{ width:340px; height:auto; overflow:visible; }}
  .hull {{ transform-origin:50% 62%; transform:rotate(-12deg); }}
</style>
<div class="copy">
  <h1>Ballast<br>Wellbeing</h1>
  <div class="rule"></div>
  <p>Mental health training for Ontario schools and workplaces</p>
</div>
<div class="mark">
  <svg viewBox="0 0 100 108">
    <line x1="0" y1="80" x2="100" y2="80" stroke="#3D4E5A" stroke-width="3" stroke-linecap="round"/>
    <g class="hull">
      <path d="M 18,50 V 28 A 10,10 0 0 1 28,18 H 72 A 10,10 0 0 1 82,28 V 50 A 32,32 0 0 1 18,50 Z"
            fill="none" stroke="{PAPER}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/>
    </g>
    <rect x="35" y="59.5" width="30" height="13.5" rx="6.75" fill="{DEEP_SEA_LIGHT}"/>
  </svg>
</div>"""


def main():
    page_file = ROOT / "_og_tmp.html"
    page_file.write_text(HTML, encoding="utf-8")
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))

    class S(socketserver.TCPServer):
        allow_reuse_address = True

    srv = S(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1200, "height": 630},
                            device_scale_factor=1)
            pg.goto(f"http://127.0.0.1:{PORT}/_og_tmp.html", wait_until="networkidle")
            pg.wait_for_timeout(400)          # let the variable fonts settle
            OUT.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(OUT))
            b.close()
    finally:
        srv.shutdown()
        page_file.unlink(missing_ok=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
