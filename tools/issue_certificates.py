#!/usr/bin/env python3
"""
Issue certificates: mint serials, record them, print them.

The site can verify a certificate but nothing could create one, so the first
workshop would have meant hand-writing SQL for every participant. This reads a
roster CSV and does the whole job.

    export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
    python3 tools/issue_certificates.py roster.csv            # dry run
    python3 tools/issue_certificates.py roster.csv --commit   # write + print
    python3 tools/issue_certificates.py --template            # blank roster

Roster columns (header row required):
    participant_name, program_title, contact_hours, issue_date[, expiry_date]

issue_date is YYYY-MM-DD. expiry_date is optional and normally left empty —
a certificate of completion records something that happened and does not
expire. Fill it only for a program with a real refresh interval.

Outputs, next to the roster:
    <roster>-issued.csv        the roster plus the serial for each row
    certificates/<serial>.pdf  one printable certificate per participant

Nothing is written to the database without --commit, so a typo in a roster
costs you a re-run rather than a table full of wrong certificates.
"""
import argparse, csv, datetime, functools, http.server, json, os, pathlib
import re, secrets, socketserver, sys, threading, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PORT = 8733
SITE = "ballastwellbeing.com"

# Excludes I, O, 0, 1 — a serial gets read aloud, typed off a printout, and
# copied by an HR administrator who did not attend the session.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SERIAL_RE = re.compile(r"^BW-\d{4}-\d{4}-[A-HJ-NP-Z2-9]{4}$")
COLUMNS = ["participant_name", "program_title", "contact_hours", "issue_date"]

TEMPLATE = """participant_name,program_title,contact_hours,issue_date,expiry_date
Jane Doe,The Regulated Classroom: Trauma-Informed Practice,3,2026-09-15,
John Smith,The Regulated Classroom: Trauma-Informed Practice,3,2026-09-15,
"""


def mint(issue_date, sequence):
    """BW-YYYY-NNNN-XXXX. The random tail is what stops the serial space being
    walked from 0001 to harvest every participant name ever issued."""
    tail = "".join(secrets.choice(ALPHABET) for _ in range(4))
    serial = f"BW-{issue_date.year}-{sequence:04d}-{tail}"
    assert SERIAL_RE.match(serial), serial
    return serial


def supabase(method, path, body=None, prefer=None):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY first.\n"
                 "Both are in Netlify under Site configuration > Environment variables.")
    req = urllib.request.Request(
        url.rstrip("/") + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": key, "authorization": f"Bearer {key}",
                 "content-type": "application/json",
                 **({"prefer": prefer} if prefer else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else []
    except urllib.error.HTTPError as ex:
        sys.exit(f"Supabase {method} {path} failed: {ex.code} {ex.read().decode()[:400]}")


def next_sequence(year):
    """Continue the year's numbering rather than restarting, so two runs in the
    same year cannot collide on the sequence half of the serial."""
    rows = supabase("GET", f"/rest/v1/certificates?select=serial&serial=like.BW-{year}-*")
    used = [int(r["serial"].split("-")[2]) for r in rows
            if SERIAL_RE.match(r["serial"])]
    return max(used) + 1 if used else 1


def read_roster(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{path} has a header but no rows.")
    missing = [c for c in COLUMNS if c not in rows[0]]
    if missing:
        sys.exit(f"{path} is missing column(s): {', '.join(missing)}\n"
                 f"Run --template for a blank roster with the right headers.")
    clean = []
    for i, r in enumerate(rows, start=2):     # line 1 is the header
        rec = {k: (r.get(k) or "").strip() for k in COLUMNS}
        rec["expiry_date"] = (r.get("expiry_date") or "").strip() or None
        for k in COLUMNS:
            if not rec[k]:
                sys.exit(f"line {i}: {k} is empty")
        try:
            rec["_issue"] = datetime.date.fromisoformat(rec["issue_date"])
        except ValueError:
            sys.exit(f"line {i}: issue_date '{rec['issue_date']}' is not YYYY-MM-DD")
        if rec["expiry_date"]:
            try:
                datetime.date.fromisoformat(rec["expiry_date"])
            except ValueError:
                sys.exit(f"line {i}: expiry_date '{rec['expiry_date']}' is not YYYY-MM-DD")
        try:
            rec["contact_hours"] = float(rec["contact_hours"])
        except ValueError:
            sys.exit(f"line {i}: contact_hours '{rec['contact_hours']}' is not a number")
        clean.append(rec)
    return clean


CERT_CSS = """
  @font-face { font-family:"Source Serif 4"; src:url("/static/fonts/source-serif-4-variable.woff2") format("woff2-variations"); font-weight:200 900; }
  @font-face { font-family:"Inter Tight"; src:url("/static/fonts/inter-tight-variable.woff2") format("woff2-variations"); font-weight:100 900; }
  :root { --ink:#17242E; --sea:#2E6B5E; --grey:#40525F; --fog:#E4E9E8; --brass:#B98A3E; }
  * { box-sizing:border-box; }
  body { margin:0; width:279.4mm; height:215.9mm; padding:14mm;
         font-family:"Inter Tight",sans-serif; color:var(--ink); }
  .frame { height:100%; border:1.2pt solid var(--fog); border-top:5pt solid var(--ink);
           padding:13mm 16mm; display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:9mm; }
  header svg { width:19mm; flex:none; overflow:visible; }
  .hull { transform-origin:50% 62%; transform:rotate(-12deg); }
  .brand { font-size:9.5pt; letter-spacing:0.19em; text-transform:uppercase; color:var(--grey); }
  .kind { font-family:"Source Serif 4",Georgia,serif; font-size:17pt; font-weight:600; }
  .body { flex:1; display:flex; flex-direction:column; justify-content:center; }
  .awarded { font-size:10.5pt; color:var(--grey); margin:0 0 3mm; }
  .who { font-family:"Source Serif 4",Georgia,serif; font-size:34pt; font-weight:600;
         line-height:1.1; margin:0 0 5mm; }
  .rule { width:34mm; height:2.4pt; background:var(--brass); margin:0 0 5mm; }
  .what { font-size:14pt; line-height:1.4; margin:0; max-width:62ch; }
  .what strong { font-weight:600; }
  footer { display:flex; justify-content:space-between; align-items:flex-end;
           gap:10mm; border-top:1pt solid var(--fog); padding-top:5mm; }
  dl { display:flex; gap:11mm; margin:0; }
  dt { font-size:8pt; letter-spacing:0.08em; text-transform:uppercase;
       color:var(--grey); margin:0 0 1mm; }
  dd { margin:0; font-size:11pt; font-weight:600; font-variant-numeric:tabular-nums; }
  .serial dd { font-family:ui-monospace,"SFMono-Regular",Menlo,monospace; letter-spacing:0.03em; }
  .verify { text-align:right; font-size:8.6pt; color:var(--grey); line-height:1.45; }
  .verify strong { color:var(--ink); }
  .disclaimer { margin:4mm 0 0; font-size:8pt; color:var(--grey); }
"""

MARK = """<svg viewBox="0 0 100 108">
  <line x1="0" y1="80" x2="100" y2="80" stroke="#E4E9E8" stroke-width="3" stroke-linecap="round"/>
  <g class="hull"><path d="M 18,50 V 28 A 10,10 0 0 1 28,18 H 72 A 10,10 0 0 1 82,28 V 50 A 32,32 0 0 1 18,50 Z"
     fill="none" stroke="#17242E" stroke-width="7" stroke-linejoin="round" stroke-linecap="round"/></g>
  <rect x="35" y="59.5" width="30" height="13.5" rx="6.75" fill="#2E6B5E"/></svg>"""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def certificate_html(rec, serial):
    hours = rec["contact_hours"]
    hours = int(hours) if float(hours).is_integer() else hours
    issued = rec["_issue"].strftime("%d %B %Y").lstrip("0")
    expiry = (f"<div><dt>Valid until</dt><dd>"
              f"{datetime.date.fromisoformat(rec['expiry_date']).strftime('%d %B %Y').lstrip('0')}"
              f"</dd></div>") if rec["expiry_date"] else ""
    return f"""<!doctype html><meta charset="utf-8"><title>{esc(serial)}</title>
<style>{CERT_CSS}</style>
<div class="frame">
  <header>{MARK}<div><div class="brand">Ballast Wellbeing</div>
    <div class="kind">Certificate of Completion</div></div></header>
  <div class="body">
    <p class="awarded">This certifies that</p>
    <p class="who">{esc(rec['participant_name'])}</p>
    <div class="rule"></div>
    <p class="what">completed <strong>{esc(rec['program_title'])}</strong>,
      a training session of <strong>{hours} contact hour{'s' if hours != 1 else ''}</strong>,
      delivered by Ballast Wellbeing on {esc(issued)}.</p>
  </div>
  <footer>
    <dl>
      <div class="serial"><dt>Serial</dt><dd>{esc(serial)}</dd></div>
      <div><dt>Contact hours</dt><dd>{hours}</dd></div>
      <div><dt>Completed</dt><dd>{esc(issued)}</dd></div>
      {expiry}
    </dl>
    <div class="verify">Verify this certificate at<br>
      <strong>{SITE}/verify</strong><br>using the serial above</div>
  </footer>
  <p class="disclaimer">This records attendance and contact hours. It is not a
    professional designation and does not certify the holder in anything.
    Ballast Wellbeing delivers training and education; we do not provide
    counselling, assessment, or treatment.</p>
</div>"""


def render_pdfs(pairs, outdir):
    from playwright.sync_api import sync_playwright
    outdir.mkdir(parents=True, exist_ok=True)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))

    class S(socketserver.TCPServer):
        allow_reuse_address = True

    srv = S(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    tmp = ROOT / "_cert_tmp.html"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            for rec, serial in pairs:
                tmp.write_text(certificate_html(rec, serial), encoding="utf-8")
                pg.goto(f"http://127.0.0.1:{PORT}/_cert_tmp.html", wait_until="networkidle")
                pg.pdf(path=str(outdir / f"{serial}.pdf"), width="279.4mm",
                       height="215.9mm", print_background=True,
                       margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            b.close()
    finally:
        srv.shutdown()
        tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roster", nargs="?", help="CSV roster")
    ap.add_argument("--commit", action="store_true",
                    help="write to the database and render the PDFs")
    ap.add_argument("--template", action="store_true", help="print a blank roster")
    a = ap.parse_args()

    if a.template:
        print(TEMPLATE, end="")
        return
    if not a.roster:
        ap.error("give a roster CSV, or --template")

    roster = pathlib.Path(a.roster)
    records = read_roster(roster)
    year = records[0]["_issue"].year
    if len({r["_issue"].year for r in records}) > 1:
        sys.exit("All rows in one roster must share an issue year — "
                 "split them into one file per year.")

    seq = next_sequence(year)
    pairs = [(r, mint(r["_issue"], seq + i)) for i, r in enumerate(records)]

    print(f"{len(pairs)} certificate(s), year {year}, "
          f"sequence {seq}–{seq + len(pairs) - 1}\n")
    for rec, serial in pairs:
        print(f"  {serial}  {rec['participant_name']:28} "
              f"{rec['contact_hours']}h  {rec['program_title'][:44]}")

    if not a.commit:
        print("\nDry run. Nothing written. Re-run with --commit when this looks right.")
        return

    supabase("POST", "/rest/v1/certificates",
             [{"serial": s, "participant_name": r["participant_name"],
               "program_title": r["program_title"],
               "contact_hours": r["contact_hours"],
               "issue_date": r["issue_date"], "expiry_date": r["expiry_date"],
               "status": "valid"} for r, s in pairs],
             prefer="return=minimal")
    print(f"\nwrote {len(pairs)} row(s) to the certificates table")

    out_csv = roster.with_name(roster.stem + "-issued.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["serial"] + COLUMNS + ["expiry_date"])
        for rec, serial in pairs:
            w.writerow([serial] + [rec[c] for c in COLUMNS] + [rec["expiry_date"] or ""])
    print(f"wrote {out_csv}")

    outdir = roster.parent / "certificates"
    render_pdfs(pairs, outdir)
    print(f"wrote {len(pairs)} PDF(s) to {outdir}/")


if __name__ == "__main__":
    main()
