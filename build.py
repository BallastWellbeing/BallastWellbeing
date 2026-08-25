#!/usr/bin/env python3
"""
Ballast Wellbeing static site generator.

Deliberately small. Jinja2 templates + Markdown content + one YAML data file.
No JS toolchain, no runtime, no framework upgrade treadmill. Output is plain
static HTML that Netlify serves directly.

    python3 build.py          build into dist/
    python3 build.py --serve  build, then serve dist/ on :8000
"""
import re, shutil, sys, datetime, hashlib
from pathlib import Path

import yaml, markdown, markupsafe
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
SITE_URL = "https://ballastwellbeing.com"

MD = markdown.Markdown(extensions=["extra", "sane_lists", "smarty", "toc"],
                       extension_configs={"toc": {"permalink": False}})


def load_data():
    data = {}
    for f in sorted((ROOT / "content" / "data").glob("*.yml")):
        loaded = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise SystemExit(f"{f}: expected a mapping at the top level")
        # Top-level keys merge into the template context, so site.yml's `site:`
        # block is reachable as {{ site.* }} rather than {{ site.site.* }}.
        data.update(loaded)
    return data


def load_collection(name):
    """Markdown files with YAML frontmatter -> list of dicts, newest first."""
    items = []
    for f in sorted((ROOT / "content" / name).glob("*.md")):
        raw = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
        if not m:
            raise SystemExit(f"{f}: missing YAML frontmatter")
        check_charset(raw, str(f))
        meta = yaml.safe_load(m.group(1)) or {}
        MD.reset()
        # Markup(), not a bare str: Jinja autoescaping is on, and without
        # this the article renders its own <p> tags as visible text.
        MD.reset()
        meta["body"] = markupsafe.Markup(MD.convert(m.group(2).strip()))
        meta["slug"] = meta.get("slug", f.stem)
        meta["source_file"] = str(f.relative_to(ROOT))
        items.append(meta)
    items.sort(key=lambda i: str(i.get("date", "")), reverse=True)
    return items


ALLOWED_NON_ASCII = set("\u2013\u2014\u2018\u2019\u201c\u201d\u00b7\u2026\u00e9\u00e8\u00ea\u00fc\u00f6\u00e0\u00e7\u00ae\u00a9\u2122\u00a0\u2192\u2713\u00d7\u2212")


def check_charset(text, label):
    """Guard against stray characters from another script sneaking into copy.
    A single CJK glyph mid-sentence shipped to a school is not a good look, and
    it is invisible in a diff review."""
    bad = sorted({c for c in text if ord(c) > 127 and c not in ALLOWED_NON_ASCII})
    if bad:
        raise SystemExit(
            f"{label}: unexpected characters {[f'{c} (U+{ord(c):04X})' for c in bad]}. "
            f"Add to ALLOWED_NON_ASCII in build.py if intentional.")



# ---------------------------------------------------------------------------
# Placeholders
# Values only Norman can supply. Rendered visibly rather than as blank space,
# so an unfilled one is impossible to miss in review and cannot quietly ship.
# `python3 build.py --check` exits non-zero while any remain.
# ---------------------------------------------------------------------------
PLACEHOLDERS = []


def ph(key, hint=""):
    value = PLACEHOLDER_VALUES.get(key)
    if value:
        return markupsafe.Markup(markupsafe.escape(value))
    PLACEHOLDERS.append(key)
    label = markupsafe.escape(hint or key)
    return markupsafe.Markup(
        f'<mark class="placeholder" title="Needs Norman">[{label}]</mark>')



TABLE_RE = re.compile(r"(<table\b.*?</table>)", re.S | re.I)


def wrap_tables(html):
    """Wrap data tables in a horizontally scrollable, keyboard-focusable region.

    A three-column data table cannot reflow below its minimum content width, so
    at 320px it pushes the whole page into horizontal scroll. WCAG 1.4.10
    exempts content requiring two-dimensional layout, but the scrollable region
    itself must be keyboard operable — hence tabindex and the labelled role.
    Applied at build time so any table added later gets it automatically.
    """
    def repl(m):
        table = m.group(1)
        if 'class="table-scroll"' in table:
            return table
        cap = re.search(r"<caption[^>]*>(.*?)</caption>", table, re.S | re.I)
        label = re.sub(r"<[^>]+>", "", cap.group(1)).strip() if cap else "Table"
        return (f'<div class="table-scroll" role="region" tabindex="0" '
                f'aria-label="{label}, scrollable">{table}</div>')
    return TABLE_RE.sub(repl, html)


def write(path, html):
    html = wrap_tables(html)
    """`/schools/staff` -> dist/schools/staff/index.html, so URLs stay clean."""
    path = path.strip("/")
    out = DIST / (path or ".") / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return "/" + path if path else "/"



# ---------------------------------------------------------------------------
# Asset fingerprinting
#
# netlify.toml serves /static/* with `immutable, max-age=31536000`. That is
# only safe if a changed file gets a changed URL. Without it, a returning
# visitor keeps a year-old stylesheet against new markup — which is exactly
# what happened: a dark hero rendered with the old light-surface tokens, so
# the buttons and the brand mark fell back to defaults and broke.
#
# So every referenced asset gets a content hash in its filename. Leaf assets
# (fonts, images) are hashed first and their references rewritten inside CSS;
# only then are the stylesheets hashed, since their content just changed.
# ---------------------------------------------------------------------------
def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:10]


def fingerprint_assets():
    """Rename static assets to include a content hash. Returns {old_url: new_url}."""
    static = DIST / "static"
    if not static.exists():
        return {}

    mapping = {}

    def stamp(paths):
        out = {}
        for f in paths:
            if not f.is_file():
                continue
            new_name = f"{f.stem}.{_hash(f)}{f.suffix}"
            new_path = f.with_name(new_name)
            f.rename(new_path)
            old_url = "/" + str(f.relative_to(DIST)).replace("\\", "/")
            new_url = "/" + str(new_path.relative_to(DIST)).replace("\\", "/")
            out[old_url] = new_url
        return out

    def rewrite(paths, table):
        for f in paths:
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8")
            original = text
            for old, new in table.items():
                text = text.replace(old, new)
            if text != original:
                f.write_text(text, encoding="utf-8")

    # 1. Leaf assets: nothing inside them points at anything else.
    leaves = [f for f in static.rglob("*")
              if f.suffix.lower() in {".woff2", ".woff", ".svg", ".png", ".jpg", ".webp", ".pdf"}]
    leaf_map = stamp(leaves)
    mapping.update(leaf_map)

    # 2. Stylesheets reference the leaves, so rewrite before hashing them.
    sheets = [f for f in static.rglob("*.css")]
    rewrite(sheets, leaf_map)

    # 3. Now hash the stylesheets and scripts.
    code_map = stamp([f for f in static.rglob("*") if f.suffix.lower() in {".css", ".js"}])
    mapping.update(code_map)

    # 4. Point every built page at the new names.
    rewrite(list(DIST.rglob("*.html")), mapping)
    return mapping


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.filters["markdown"] = lambda t: markupsafe.Markup(
        MD.reset() or MD.convert(t or ""))

    data = load_data()
    global PLACEHOLDER_VALUES
    PLACEHOLDER_VALUES = data.get("placeholders", {}) or {}

    programs = load_collection("programs")
    insights = load_collection("insights")

    ctx = {
        "site": data.get("site", {}),
        "pricing": data.get("pricing", {}),
        "programs": programs,
        "insights": insights,
        "year": datetime.date.today().year,
        "site_url": SITE_URL,
        "ph": ph,
        # Used by /contact to resolve ?program=[slug] into a readable title
        # and to preselect the right form for the program's track.
        "program_titles": {p["slug"]: p["title"] for p in programs},
        "workplace_slugs": [p["slug"] for p in programs if p.get("track") == "workplaces"],
        # Categories present in the article set, in a fixed display order.
        "categories": [c for c in ("Schools", "Workplaces", "Research")
                       if any(a.get("category") == c for a in insights)],
    }

    urls = []

    # --- One template per structured page -----------------------------------
    counselling_on = bool(ctx["site"].get("counselling_enabled"))
    for tpl in sorted((ROOT / "templates" / "pages").glob("*.html")):
        if not counselling_on and tpl.stem.startswith("counselling"):
            continue
        t = env.get_template(f"pages/{tpl.name}")
        # Filename is the route: home.html -> /, schools--staff.html -> /schools/staff
        route = "/" if tpl.stem == "home" else "/" + tpl.stem.replace("--", "/")
        urls.append(write(route, t.render(**ctx, route=route)))

    # --- Collections --------------------------------------------------------
    prog_t = env.get_template("program.html") if programs else None
    for p in programs:
        route = f"/programs/{p['slug']}"
        urls.append(write(route, prog_t.render(**ctx, program=p, route=route)))

    art_t = env.get_template("article.html") if insights else None
    for a in insights:
        route = f"/insights/{a['slug']}"
        urls.append(write(route, art_t.render(**ctx, article=a, route=route)))

    # Real filtered archive pages, one per category. The category filter used to
    # be a set of #anchor links that jumped down the unfiltered list, which also
    # gave every article an id equal to its category — duplicate ids as soon as
    # two articles shared one.
    if insights:
        arch_t = env.get_template("pages/insights.html")
        for cat in ctx["categories"]:
            route = f"/insights/category/{cat.lower()}"
            urls.append(write(route, arch_t.render(
                **ctx, route=route, active_category=cat)))

    # --- Static assets ------------------------------------------------------
    shutil.copytree(ROOT / "static", DIST / "static")
    for extra in ("_redirects", "_headers"):
        src = ROOT / "static" / extra
        if src.exists():
            shutil.copy(src, DIST / extra)

    # --- Fingerprint assets, then repoint the pages at them -----------------
    fingerprinted = fingerprint_assets()

    # --- sitemap.xml + robots.txt ------------------------------------------
    today = datetime.date.today().isoformat()
    entries = "\n".join(
        f"  <url><loc>{SITE_URL}{u}</loc><lastmod>{today}</lastmod></url>"
        for u in sorted(set(urls)))
    (DIST / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{entries}\n</urlset>\n',
        encoding="utf-8")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")

    print(f"built {len(urls)} pages -> {DIST}  ({len(fingerprinted)} assets fingerprinted)")
    if PLACEHOLDERS:
        unique = sorted(set(PLACEHOLDERS))
        print(f"\n{len(unique)} unfilled placeholder(s) — not launch ready:")
        for k in unique:
            print(f"   [{k}]")
        if "--check" in sys.argv:
            raise SystemExit(1)
    for u in sorted(set(urls)):
        print("  ", u)

    if "--serve" in sys.argv:
        import http.server, socketserver, functools, os
        os.chdir(DIST)
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
        with socketserver.TCPServer(("", 8000), h) as httpd:
            print("serving on http://localhost:8000")
            httpd.serve_forever()


if __name__ == "__main__":
    main()
