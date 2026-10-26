#!/usr/bin/env python3
"""Generate The Bookshelf from content/bookshelf.json.

Reuses the shared page shell, design system and theme script from the
ai-engineering builder, so this section cannot drift from the rest of the site.

    python3 bookshelf/build.py --check    # validate only
    python3 bookshelf/build.py            # validate, then write pages
"""

from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "ai-engineering"))

import build as ae  # noqa: E402  the AI Engineering builder, used for the shared shell

CONTENT = HERE / "content" / "bookshelf.json"
errors: list[str] = []
warnings: list[str] = []
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def e(v):
    return html.escape(str(v), quote=True) if v is not None else ""


def inline(text: str) -> str:
    """Escape, then honour *emphasis* and **strong** from the reflection text."""
    out = e(text)
    out = re.sub(r"\*\*(.+?)\*\*", r'<strong style="font-weight:500;color:var(--fg)">\1</strong>', out)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    return out


def validate(d):
    for f in ("title", "subtitle", "canonical", "meta_description"):
        if not d.get(f):
            errors.append(f"bookshelf.json: missing {f!r}")
    allowed = set(d.get("designations", []))
    seen = set()
    years_with_books = {b.get("read_year") for b in d.get("books", [])}
    for i, b in enumerate(d.get("books", [])):
        w = f"bookshelf.json books[{b.get('id', i)}]"
        for f in ("id", "title", "authors", "reflection"):
            if not b.get(f):
                errors.append(f"{w}: missing required field {f!r}")
        if b.get("id"):
            if not SLUG.match(b["id"]):
                errors.append(f"{w}: id must be a lowercase slug")
            if b["id"] in seen:
                errors.append(f"{w}: duplicate book id")
            seen.add(b["id"])
        if not isinstance(b.get("authors", []), list):
            errors.append(f"{w}: authors must be a list")
        if not isinstance(b.get("reflection", []), list):
            errors.append(f"{w}: reflection must be a list of paragraphs")
        for g in b.get("designations", []):
            if g not in allowed:
                errors.append(f"{w}: designation {g!r} is not one of {sorted(allowed)}")
        if b.get("cover_url") and not str(b["cover_url"]).startswith("https://"):
            errors.append(f"{w}: cover_url must be https")
        if b.get("external_url") and not str(b["external_url"]).startswith("https://"):
            errors.append(f"{w}: external_url must be https")
        for r in b.get("related_books", []):
            if r not in {x.get("id") for x in d.get("books", [])}:
                errors.append(f"{w}: related_books entry {r!r} does not exist")
        if b.get("read_year") is not None and not isinstance(b["read_year"], int):
            errors.append(f"{w}: read_year must be a number or null")
        if b.get("read_year") is None and not b.get("external_note"):
            errors.append(f"{w}: undated books must carry an external_note saying they are "
                          f"outside the yearly archive")
        if b.get("group") and b["group"] not in {g["id"] for g in d.get("groups", [])}:
            errors.append(f"{w}: group {b['group']!r} is not defined")
    # a year block may only exist when that year has at least one finished book
    for y in d.get("years", []):
        if y.get("year") not in years_with_books:
            errors.append(f"bookshelf.json years[{y.get('year')}]: no books recorded for that year; "
                          f"empty years are not published")


def cover(b, big=False):
    """Cover image with a typographic fallback if the remote image fails."""
    size = "ae-cover-lg" if big else "ae-cover"
    alt = f'Cover of {b["title"]}'
    # initials from the main title only, ignoring any subtitle after a colon
    main = b["title"].split(":")[0]
    initials = e("".join(w[0] for w in main.split() if w[0].isalpha())[:3].upper())
    fallback = (f'<span class="ae-cover-fb mono" aria-hidden="true">{initials}</span>')
    if not b.get("cover_url"):
        return f'<span class="{size} ae-cover-none">{fallback}</span>'
    return (f'<span class="{size}">{fallback}'
            f'<img src="{e(b["cover_url"])}" alt="{e(alt)}"'
            f' loading="{"eager" if big else "lazy"}" decoding="async"'
            f' onerror="this.remove()"></span>')


def badges(b):
    out = "".join(f'<span class="mono ae-badge">{e(g)}</span>' for g in b.get("designations", []))
    return f'<span class="ae-top">{out}</span>' if out else ""


EXTRA = """
.bk-head{padding-top:140px}
.bk-year{padding-top:76px}
.bk-grid{margin-top:28px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.bk-card{display:block;background:var(--bg);padding:26px 24px;transition:background .2s}
.bk-card:hover{background:var(--card-hover)}
.ae-cover,.ae-cover-lg{position:relative;display:block;overflow:hidden;border:1px solid var(--line2);border-radius:3px;background:var(--panel)}
.ae-cover{width:104px;height:158px}
.ae-cover-lg{width:168px;height:255px}
.ae-cover img,.ae-cover-lg img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.ae-cover-fb{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:20px;letter-spacing:0.1em;color:var(--faint)}
.bk-t{margin:16px 0 0;font-size:18px;letter-spacing:-0.015em;line-height:1.3;color:var(--fg)}
.bk-a{margin:6px 0 0;font-size:13.5px;color:var(--mid)}
.bk-p{margin:12px 0 0;font-size:14.5px;line-height:1.6;color:var(--mid)}
.ae-badge{display:inline-block;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:var(--acc);border:1px solid var(--acc-line);border-radius:4px;padding:3px 7px;margin-right:6px}
.bk-cat{margin:14px 0 0;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--faint)}
.bk-detail{display:grid;grid-template-columns:168px minmax(0,1fr);gap:40px;align-items:start;margin-top:34px}
.bk-body p{margin:0 0 18px;font-size:17px;line-height:1.7;color:var(--fg2);max-width:660px;text-wrap:pretty}
.bk-idea{border-left:2px solid var(--acc);padding-left:16px;margin-top:22px;max-width:660px}
.bk-idea h3{margin:0;font-size:16px;font-weight:500;color:var(--fg)}
.bk-idea p{margin:8px 0 0;font-size:15px;line-height:1.65;color:var(--mid)}
.bk-group{margin-top:44px}
.bk-gh{margin:0;font-size:21px;letter-spacing:-0.02em;font-weight:500;color:var(--fg)}
.bk-gs{margin:8px 0 0;max-width:620px;font-size:15px;line-height:1.6;color:var(--mid);text-wrap:pretty}
.bk-group .bk-grid{margin-top:20px}
.bk-empty{margin:30px 0 0;max-width:620px;font-size:16px;line-height:1.65;color:var(--mid);border-left:2px solid var(--line2);padding-left:16px}
@media (max-width:640px){
 .bk-head{padding-top:86px}
 .bk-detail{grid-template-columns:1fr;gap:24px}
 .bk-body p{font-size:16px}
}
"""


def shell(path, depth, title, desc, canonical, body):
    ae.SHARED["css"], ae.SHARED["js"], ae.SHARED["icon"] = ae.extract_shared()
    ae.EXTRA_CSS = ae.EXTRA_CSS + EXTRA
    ae.HERE = HERE
    return ae.page(path, depth, title, desc, canonical, body)


def build():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    validate(d)
    if errors:
        print("FAILED - content did not validate:\n", file=sys.stderr)
        for m in errors:
            print(f"  error: {m}", file=sys.stderr)
        return 1
    for m in warnings:
        print(f"  warn:  {m}")

    for sub in HERE.iterdir():
        if sub.is_dir() and sub.name != "content":
            shutil.rmtree(sub)

    books = d["books"]
    dated = [b for b in books if b.get("read_year") is not None]
    undated = [b for b in books if b.get("read_year") is None]
    by_year = {}
    for b in dated:
        by_year.setdefault(b["read_year"], []).append(b)
    reflections = {y["year"]: y.get("reflection") for y in d.get("years", [])}
    groups = d.get("groups", [])

    def cards_for(rows):
        out = []
        for b in rows:
            cats = " &middot; ".join(e(c) for c in b.get("categories", []))
            out.append(f"""      <a class="bk-card" href="{e(b['id'])}/">
        {cover(b)}
        {badges(b)}
        <h3 class="bk-t">{e(b['title'])}</h3>
        <p class="bk-a">{e(", ".join(b['authors']))}</p>
        <p class="bk-p">{e(b.get('preview') or '')}</p>
        <p class="mono bk-cat">{cats}</p>
      </a>""")
        return chr(10).join(out)

    total = 0
    sections = []
    for year in sorted(by_year, reverse=True):
        rows = by_year[year]
        note = f'<p class="ae-intro">{e(reflections.get(year))}</p>' if reflections.get(year) else ""
        blocks = []
        for g in groups:
            g_rows = [b for b in rows if b.get("group", "nonfiction") == g["id"]]
            if not g_rows:
                continue
            blocks.append(f"""  <div class="bk-group">
    <h3 class="bk-gh">{e(g['name'])}</h3>
    <p class="bk-gs">{e(g['subtitle'])}</p>
    <div class="bk-grid">
{cards_for(g_rows)}
    </div>
  </div>""")
        if not blocks:
            blocks = [f'<div class="bk-grid">{cards_for(rows)}</div>']
        sections.append(f"""<section class="wrap bk-year">
  <div class="sec-head"><h2>{year}</h2>
    <div class="mono kicker">{len(rows)} book{'s' if len(rows) != 1 else ''}</div></div>
  {note}
{chr(10).join(blocks)}
</section>""")

    if undated:
        sections.append(f"""<section class="wrap bk-year">
  <div class="sec-head"><h2>{e(d.get('unconfirmed_heading', 'Also on the shelf'))}</h2>
    <div class="mono kicker">Undated</div></div>
  <p class="ae-intro">{e(d.get('unconfirmed_note', ''))}</p>
  <div class="bk-grid">
{cards_for(undated)}
  </div>
</section>""")

    if not sections:
        sections = ['<section class="wrap bk-year"><p class="bk-empty">'
                    'The first entries are being written up. A book appears here once I have '
                    'finished it and have something worth saying about it.</p></section>']

    body = f"""<header class="wrap bk-head">
  <p class="mono eyebrow">Reading record</p>
  <h1>{e(d['title'])}</h1>
  <p class="ae-lede">{e(d['subtitle'])}</p>
  <p class="ae-stand">{e(d['intro'])}</p>
</header>
{chr(10).join(sections)}
<section class="wrap ae-sec">
  <div class="mono foot"><span><a href="../">&#8592; Back to the portfolio</a></span>
    <span>morantejoseph1@gmail.com</span></div>
</section>"""
    total += shell(HERE / "index.html", 1, f"{d['title']} - Joseph Morante",
                   d["meta_description"], d["canonical"], body)

    # ---- one page per book ----------------------------------------------
    for b in books:
        paras = "".join(f"<p>{inline(x)}</p>" for x in b["reflection"])
        ideas = "".join(
            f'<div class="bk-idea"><h3>{e(i["title"])}</h3><p>{e(i["body"])}</p></div>'
            for i in b.get("key_ideas", []))
        links = []
        if b.get("external_url"):
            links.append(ae.ext(b["external_url"], b.get("external_label") or "More about this book"))
        meta = [("Authors", e(", ".join(b["authors"]))),
                ("Read", e(b["read_year"]) if b.get("read_year") else "Year not yet confirmed"),
                ("Published", e(b.get("published_year"))),
                ("Categories", " &middot; ".join(e(c) for c in b.get("categories", [])))]
        if b.get("finished_date"):
            meta.insert(2, ("Finished", e(b["finished_date"])))
        cover_credit = (f'<p class="mono bk-cat">Cover via {e(b["cover_source"])}</p>'
                        if b.get("cover_source") else "")
        body = f"""<header class="wrap bk-head">
  <p class="mono ae-crumb"><a href="../../">Portfolio</a> / <a href="../">The Bookshelf</a> / {e(b['title'])}</p>
  <h1>{e(b['title'])}</h1>
  {badges(b)}
  <div class="bk-detail">
    <div>{cover(b, big=True)}{cover_credit}</div>
    <div>
      {ae.facts(meta)}
      <p class="ae-stand">{e(b.get('preview') or '')}</p>
      {f'<p class="ae-links">{" ".join(links)}</p>' if links else ''}
      {f'<p class="ae-note">{e(b["external_note"])}</p>' if b.get("external_note") else ''}
    </div>
  </div>
</header>

{f'''<section class="wrap ae-sec">
  <div class="sec-head"><h2 class="h2-sm">What I took away</h2></div>
  {ideas}
</section>''' if ideas else ""}

<section class="wrap ae-sec">
  <div class="sec-head"><h2 class="h2-sm">The full reflection</h2></div>
  <div class="bk-body" style="margin-top:26px">{paras}</div>
</section>

<section class="wrap ae-sec">
  <div class="mono foot"><span><a href="../">&#8592; Back to The Bookshelf</a></span>
    <span>morantejoseph1@gmail.com</span></div>
</section>"""
        total += shell(HERE / b["id"] / "index.html", 2,
                       f"{b['title']} - The Bookshelf - Joseph Morante",
                       (b.get("preview") or b["title"])[:180],
                       f"{d['canonical']}{b['id']}/", body)

    print(f"built {1 + len(books)} pages, {total:,} bytes total")
    print(f"  books {len(books)} | years published {sorted(by_year, reverse=True)}")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        validate(json.loads(CONTENT.read_text(encoding="utf-8")))
        if errors:
            for m in errors:
                print(f"  error: {m}", file=sys.stderr)
            sys.exit(1)
        print("content OK")
        sys.exit(0)
    sys.exit(build())
