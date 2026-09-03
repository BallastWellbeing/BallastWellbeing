#!/usr/bin/env python3
"""
Build the two program overview PDFs the enquiry autoresponder attaches.

Generated from content/programs/*.md and content/data/pricing.yml rather than
hand-made, so a price or a program that changes on the site changes here too.
A stale PDF attached to every enquiry is worse than no PDF: buyers forward
these internally, and the forwarded copy is what the person who signs reads.

Rendered through Chromium, not reportlab, because the brand faces ship as
woff2 and decoding those needs brotli, which is not installable here. Chromium
reads them natively and embeds them, so the PDF matches the site exactly.

    python3 tools/make_pdfs.py
      -> static/pdf/ballast-schools-overview.pdf
      -> static/pdf/ballast-workplaces-overview.pdf
"""
import functools, html, http.server, pathlib, re, socketserver, threading
import yaml
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "pdf"
PORT = 8732
SITE = "ballastwellbeing.com"
EMAIL = "info@ballastwellbeing.com"

TRACKS = {
    "schools": {
        "file": "ballast-schools-overview.pdf",
        "title": "Programs for Ontario schools",
        "intro": ("Independent schools sit outside the publicly funded mental health "
                  "support system. No board mental health lead, no ministry-funded "
                  "programming, no implementation coach. These programs build that "
                  "layer — student sessions, staff PD, and parent evenings, priced "
                  "for schools without a district budget behind them."),
        "pricing": True,
    },
    "workplaces": {
        "file": "ballast-workplaces-overview.pdf",
        "title": "Programs for Ontario workplaces",
        "intro": ("Mental health is the leading driver of disability claims in Canada, "
                  "and Ontario employers carry a legal duty of care for psychological "
                  "safety. These programs train the people who determine whether that "
                  "duty is met: the managers having the conversation."),
        "pricing": False,
    },
}

# Annual packages are deliberately not in this list: they carry a name, a note
# and an inclusions list rather than a program/detail/price row, and running
# them through the generic table printed three prices with no names beside them.
PRICING_SECTIONS = [
    ("students", "Student sessions"),
    ("student_multi", "More than one session in a visit"),
    ("staff", "Staff training"),
    ("parents", "Parent evenings"),
]


def load_programs():
    items = []
    for f in sorted((ROOT / "content" / "programs").glob("*.md")):
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", f.read_text(encoding="utf-8"), re.S)
        items.append(yaml.safe_load(m.group(1)))
    return items


def e(s):
    return html.escape(str(s if s is not None else ""))


def program_block(p):
    meta = [("Audience", p.get("audience")), ("Duration", p.get("duration")),
            ("Format", p.get("format")), ("Group size", p.get("group_size"))]
    rows = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>"
                   for k, v in meta if v)
    outcomes = "".join(f"<li>{e(o)}</li>" for o in (p.get("outcomes") or [])[:4])
    price = (f'<p class="price">{e(p["price"])}</p>' if p.get("price") else "")
    return f"""<section class="program">
  <h3>{e(p['title'])}</h3>
  <p class="stand">{e(p.get('standfirst',''))}</p>
  <dl class="meta">{rows}</dl>
  {'<p class="lead-in">Participants leave able to:</p><ul>' + outcomes + '</ul>' if outcomes else ''}
  {price}
</section>"""


def pricing_block(pricing):
    out = []
    for key, label in PRICING_SECTIONS:
        rows = pricing.get(key) or []
        if not rows:
            continue
        trs = "".join(
            "<tr><td>{}{}</td><td class='num'>{}</td></tr>".format(
                e(r.get("program") or r.get("label")),
                f"<span class='detail'>{e(r['detail'])}</span>" if r.get("detail") else "",
                e(r.get("price")))
            for r in rows)
        out.append(f"<h3>{e(label)}</h3><table>{trs}</table>")
    annual = pricing.get("annual") or []
    if annual:
        cards = "".join(
            "<div class='pkg{rec}'><div class='pkg-head'><h4>{name}</h4>"
            "<span class='pkg-price'>{price}</span></div>{note}<ul>{inc}</ul></div>".format(
                rec=" pkg-rec" if a.get("recommended") else "",
                name=e(a.get("name")), price=e(a.get("price")),
                note=(f"<p class='pkg-note'>{e(a['note'])}</p>" if a.get("note") else ""),
                inc="".join(f"<li>{e(i)}</li>" for i in (a.get("includes") or [])))
            for a in annual)
        out.append("<h3>Annual programs</h3><div class='pkgs'>" + cards + "</div>")

    return ("<section class='pricing'><h2>What it costs</h2>"
            + "".join(out)
            + "<p class='note'>Travel outside the Greater Toronto Area is quoted "
              "separately. Multi-session and annual bookings are discounted as "
              "shown.</p></section>") if out else ""


def build_html(track, programs, pricing):
    cfg = TRACKS[track]
    mine = [p for p in programs if p.get("track") == track]
    body = "".join(program_block(p) for p in mine)
    pricing_html = pricing_block(pricing) if cfg["pricing"] else ""
    return f"""<!doctype html><meta charset="utf-8"><title>{e(cfg['title'])}</title>
<style>
  @font-face {{ font-family:"Source Serif 4"; src:url("/static/fonts/source-serif-4-variable.woff2") format("woff2-variations"); font-weight:200 900; }}
  @font-face {{ font-family:"Inter Tight"; src:url("/static/fonts/inter-tight-variable.woff2") format("woff2-variations"); font-weight:100 900; }}
  :root {{ --ink:#17242E; --sea:#2E6B5E; --grey:#40525F; --fog:#E4E9E8; --brass:#B98A3E; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:"Inter Tight",sans-serif; color:var(--ink);
          font-size:10.2pt; line-height:1.5; }}
  h1,h2,h3 {{ font-family:"Source Serif 4",Georgia,serif; font-weight:600; margin:0; }}
  .cover {{ background:var(--ink); color:#FBFCFC; padding:26pt 30pt 24pt;
            display:flex; align-items:center; gap:22pt; }}
  .cover svg {{ width:64pt; flex:none; overflow:visible; }}
  .hull {{ transform-origin:50% 62%; transform:rotate(-12deg); }}
  .cover h1 {{ font-size:22pt; line-height:1.15; }}
  .cover .brand {{ font-size:9pt; letter-spacing:0.14em; text-transform:uppercase;
                   color:var(--fog); margin-bottom:5pt; }}
  main {{ padding:20pt 30pt 0; }}
  .intro {{ font-size:11.4pt; line-height:1.55; color:var(--grey);
            border-left:2.5pt solid var(--brass); padding-left:12pt; margin-bottom:18pt; }}
  h2 {{ font-size:14pt; margin:0 0 10pt; padding-bottom:5pt;
        border-bottom:1pt solid var(--fog); }}
  .program {{ break-inside:avoid; page-break-inside:avoid; margin-bottom:15pt;
              padding-bottom:13pt; border-bottom:0.6pt solid var(--fog); }}
  .program:last-of-type {{ border-bottom:0; }}
  .program h3 {{ font-size:12.4pt; margin-bottom:3pt; }}
  .stand {{ margin:0 0 7pt; color:var(--grey); }}
  dl.meta {{ display:grid; grid-template-columns:1fr 1fr; gap:2pt 16pt; margin:0 0 7pt; }}
  dl.meta div {{ display:flex; gap:5pt; font-size:8.9pt; }}
  dl.meta dt {{ color:var(--grey); font-weight:600; margin:0; flex:none; }}
  dl.meta dd {{ margin:0; }}
  .lead-in {{ margin:0 0 2pt; font-size:9pt; font-weight:600; color:var(--grey); }}
  ul {{ margin:0 0 7pt; padding-left:13pt; }}
  li {{ margin-bottom:1.5pt; }}
  .price {{ margin:0; font-weight:600; color:var(--sea); font-size:9.6pt;
            font-variant-numeric:tabular-nums; }}
  .pricing {{ break-before:page; page-break-before:always; padding-top:4pt; }}
  .pricing h3 {{ font-size:10.6pt; margin:12pt 0 4pt; }}
  /* Rows must not split across a page. Without this the long staff table broke
     mid-row and the second page showed three prices with no program names
     beside them — a price list with the products missing. */
  table {{ width:100%; border-collapse:collapse; }}
  tr {{ break-inside:avoid; page-break-inside:avoid; }}
  .pricing h3 {{ break-after:avoid; page-break-after:avoid; }}
  td {{ padding:3.5pt 0; border-bottom:0.6pt solid var(--fog);
        vertical-align:top; font-size:9.4pt; }}
  td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums;
            font-weight:600; padding-left:12pt; }}
  .detail {{ display:block; color:var(--grey); font-size:8.5pt; }}
  .note {{ margin-top:10pt; font-size:8.8pt; color:var(--grey); }}
  .pkgs {{ display:grid; gap:8pt; }}
  .pkg {{ break-inside:avoid; page-break-inside:avoid; border:0.8pt solid var(--fog);
          border-radius:2pt; padding:8pt 10pt; }}
  .pkg-rec {{ border-color:var(--brass); border-width:1.4pt; }}
  .pkg-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:10pt; }}
  .pkg h4 {{ font-family:"Source Serif 4",Georgia,serif; font-size:11pt;
             font-weight:600; margin:0; }}
  .pkg-price {{ font-weight:600; color:var(--sea); font-size:10.4pt;
                font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .pkg-note {{ margin:1pt 0 0; font-size:8.4pt; color:var(--brass);
               text-transform:uppercase; letter-spacing:0.07em; font-weight:600; }}
  .pkg ul {{ margin:5pt 0 0; padding-left:13pt; font-size:9pt; }}
  .disclaimer {{ margin:16pt 0 0; padding:9pt 12pt; background:var(--fog);
                 font-size:8.8pt; color:var(--grey); break-inside:avoid; }}
</style>
<div class="cover">
  <svg viewBox="0 0 100 108">
    <line x1="0" y1="80" x2="100" y2="80" stroke="#3D4E5A" stroke-width="3" stroke-linecap="round"/>
    <g class="hull"><path d="M 18,50 V 28 A 10,10 0 0 1 28,18 H 72 A 10,10 0 0 1 82,28 V 50 A 32,32 0 0 1 18,50 Z"
       fill="none" stroke="#FBFCFC" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/></g>
    <rect x="35" y="59.5" width="30" height="13.5" rx="6.75" fill="#45A08D"/>
  </svg>
  <div><div class="brand">Ballast Wellbeing</div><h1>{e(cfg['title'])}</h1></div>
</div>
<main>
  <p class="intro">{e(cfg['intro'])}</p>
  <h2>The programs</h2>
  {body}
  {pricing_html}
  <p class="disclaimer">Ballast Wellbeing delivers training and education. We do not
  provide counselling, assessment, or treatment. Every session includes a certificate
  of completion showing contact hours, verifiable at {SITE}/verify.</p>
</main>"""


FOOTER = f"""<div style="width:100%;font-size:7.5pt;font-family:sans-serif;color:#40525F;
  padding:0 14mm;display:flex;justify-content:space-between;">
  <span>Ballast Wellbeing &nbsp;·&nbsp; {EMAIL} &nbsp;·&nbsp; {SITE}</span>
  <span class="pageNumber"></span>
</div>"""


def main():
    programs = load_programs()
    pricing = (yaml.safe_load((ROOT / "content/data/pricing.yml")
                              .read_text(encoding="utf-8")) or {}).get("pricing", {})
    OUT.mkdir(parents=True, exist_ok=True)

    http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))

    class S(socketserver.TCPServer):
        allow_reuse_address = True

    srv = S(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = ROOT / "_pdf_tmp.html"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for track, cfg in TRACKS.items():
                tmp.write_text(build_html(track, programs, pricing), encoding="utf-8")
                pg = b.new_page()
                pg.goto(f"http://127.0.0.1:{PORT}/_pdf_tmp.html", wait_until="networkidle")
                pg.wait_for_timeout(300)
                pg.pdf(path=str(OUT / cfg["file"]), format="Letter",
                       print_background=True, display_header_footer=True,
                       header_template="<div></div>", footer_template=FOOTER,
                       margin={"top": "0mm", "bottom": "14mm",
                               "left": "0mm", "right": "0mm"})
                pg.close()
                print("wrote", (OUT / cfg["file"]).relative_to(ROOT))
            b.close()
    finally:
        srv.shutdown()
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
