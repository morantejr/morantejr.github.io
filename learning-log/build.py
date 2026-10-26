#!/usr/bin/env python3
"""Generate The Learning Log from content/learning-log.json.

Reuses the shared page shell, design system and theme script from the
ai-engineering builder, so this section cannot drift from the rest of the site.

    python3 learning-log/build.py --check     # validate only, write nothing
    python3 learning-log/build.py             # validate, then write published entries
    python3 learning-log/build.py --drafts    # also render drafts under preview/ for review
    python3 learning-log/build.py --test      # run the built-in bite tests

Drafts are never written by a plain build. They render only under
learning-log/preview/, carry a visible banner and a noindex robots meta, and are
linked from nothing. A plain build deletes that directory, so the committed tree
never contains an unreviewed entry.
"""

from __future__ import annotations

import datetime
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

CONTENT = HERE / "content" / "learning-log.json"
PREVIEW = HERE / "preview"

errors: list[str] = []
warnings: list[str] = []

MONTH_ID = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]

# Where a pathway id points. Validated against the real tree at build time, so a
# renamed section fails the build instead of shipping a dead cross-link.
PATHWAYS = {
    "ms-cs":         ("CU Boulder MS-CS",                 "ai-engineering/curriculum/computer-science/"),
    "ms-ai":         ("CU Boulder MS-AI",                 "ai-engineering/curriculum/artificial-intelligence/"),
    "from-scratch":  ("AI Engineering from Scratch",      "ai-engineering/curriculum/from-scratch/"),
    "adtech":        ("AdTech",                           "ai-engineering/curriculum/adtech/"),
    "discrete-math": ("Discrete Mathematics",             "ai-engineering/curriculum/discrete-math/"),
    "attribution":   ("Attribution & Causal Measurement", "ai-engineering/curriculum/attribution/"),
    "signal":        ("SIGNAL",                           "ai-engineering/building-signal/"),
    "evidence":      ("Engineering evidence",             "ai-engineering/engineering-evidence/"),
    "notes":         ("Technical notes",                  "ai-engineering/technical-notes/"),
}

# Retrospective fields. A published entry that fills none of these is a statement
# of intent, not a log entry, and the build says so.
EVIDENCE_FIELDS = ("built", "misunderstood", "failures", "tested", "changed_thinking", "differently")

# Rendered section order for the structured fields, with their headings.
SECTIONS = [
    ("subjects",         "Subjects studied"),
    ("built",            "What I built"),
    ("misunderstood",    "What I had wrong"),
    ("failures",         "Where it broke"),
    ("tested",           "How I checked my understanding"),
    ("changed_thinking", "What changed my mind"),
    ("differently",      "What I would do differently"),
]

BLOCK_TYPES = {"text", "heading", "list", "quote", "code", "math", "figure", "principles", "note"}


def e(v):
    return html.escape(str(v), quote=True) if v is not None else ""


def inline(text: str) -> str:
    """Escape, then honour *emphasis* and **strong**, matching the Bookshelf."""
    out = e(text)
    out = re.sub(r"\*\*(.+?)\*\*", r'<strong style="font-weight:500;color:var(--fg)">\1</strong>', out)
    out = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", out)
    return out


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(d, *, today=None):
    today = today or datetime.date.today()
    this_month = f"{today.year:04d}-{today.month:02d}"

    for f in ("title", "subtitle", "canonical", "meta_description"):
        if not d.get(f):
            errors.append(f"learning-log.json: missing {f!r}")

    entries = d.get("entries", [])
    if not isinstance(entries, list):
        errors.append("learning-log.json: entries must be a list")
        return

    seen = set()
    for i, en in enumerate(entries):
        w = f"learning-log.json entries[{en.get('id', i)}]"

        eid = en.get("id")
        if not eid:
            errors.append(f"{w}: missing required field 'id'")
            continue
        m = MONTH_ID.match(str(eid))
        if not m:
            errors.append(f"{w}: id must be YYYY-MM")
            continue
        if eid in seen:
            errors.append(f"{w}: duplicate entry id")
        seen.add(eid)

        # No fabricated progress: an entry may not be dated in the future.
        if eid > this_month:
            errors.append(f"{w}: month is in the future (today is {this_month})")

        expected = f"{MONTH_NAMES[int(m.group(2)) - 1]} {m.group(1)}"
        if en.get("month") != expected:
            errors.append(f"{w}: month should read {expected!r}, got {en.get('month')!r}")

        for f in ("title", "summary"):
            if not en.get(f):
                errors.append(f"{w}: missing required field {f!r}")

        if not isinstance(en.get("draft", False), bool):
            errors.append(f"{w}: draft must be true or false")

        body = en.get("body", [])
        if not isinstance(body, list):
            errors.append(f"{w}: body must be a list of blocks")
            body = []
        for j, b in enumerate(body):
            if not isinstance(b, dict) or b.get("type") not in BLOCK_TYPES:
                errors.append(f"{w} body[{j}]: type must be one of {sorted(BLOCK_TYPES)}")
                continue
            t = b["type"]
            if t in ("text", "heading", "quote") and not b.get("text"):
                errors.append(f"{w} body[{j}]: {t} needs 'text'")
            if t == "list" and not b.get("items"):
                errors.append(f"{w} body[{j}]: list needs 'items'")
            if t == "principles":
                for k, p in enumerate(b.get("items") or []):
                    if not (p.get("when") and p.get("rule")):
                        errors.append(f"{w} body[{j}].items[{k}]: needs 'when' and 'rule'")
            if t == "code" and not b.get("code"):
                errors.append(f"{w} body[{j}]: code needs 'code'")
            if t == "math" and not b.get("mathml"):
                errors.append(f"{w} body[{j}]: math needs 'mathml' (MathML markup, no external renderer)")
            if t == "figure":
                if not b.get("src") and not b.get("svg"):
                    errors.append(f"{w} body[{j}]: figure needs 'src' or inline 'svg'")
                if b.get("src") and not b.get("alt"):
                    errors.append(f"{w} body[{j}]: figure with an image needs 'alt'")

        for f in EVIDENCE_FIELDS + ("subjects", "tags", "pathways", "resources", "links"):
            if f in en and not isinstance(en[f], list):
                errors.append(f"{w}: {f!r} must be a list")

        for k, r in enumerate(en.get("resources") or []):
            for f in ("author", "title", "url"):
                if not r.get(f):
                    errors.append(f"{w} resources[{k}]: missing {f!r}")
            if r.get("url") and not str(r["url"]).startswith("https://"):
                errors.append(f"{w} resources[{k}]: url must be absolute https")

        for k, l in enumerate(en.get("links") or []):
            if not (l.get("label") and l.get("url")):
                errors.append(f"{w} links[{k}]: needs 'label' and 'url'")
            u = str(l.get("url", ""))
            if u and not (u.startswith("https://") or u.startswith("{root}") or u.startswith("#")):
                errors.append(f"{w} links[{k}]: url must be https, an anchor, or use the {{root}} token")

        for p in en.get("pathways") or []:
            if p not in PATHWAYS:
                errors.append(f"{w}: pathway {p!r} is not one of {sorted(PATHWAYS)}")

        # The honesty gate. A published entry with neither retrospective content
        # nor a written body is an empty claim.
        if not en.get("draft", False):
            has_evidence = any(en.get(f) for f in EVIDENCE_FIELDS)
            if not has_evidence and len(body) < 3:
                errors.append(f"{w}: published entries need retrospective content "
                              f"({', '.join(EVIDENCE_FIELDS)}) or a written body")
            elif not has_evidence:
                warnings.append(f"{w}: published with reflection but no retrospective field filled "
                                f"({', '.join(EVIDENCE_FIELDS)})")


def check_pathway_targets():
    """Every pathway must point at a page that exists in the built tree."""
    for pid, (_, rel) in PATHWAYS.items():
        if not (ROOT / rel / "index.html").exists():
            warnings.append(f"pathway {pid!r} points at {rel} which has no index.html yet")


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def block(b, depth):
    t = b["type"]
    if t == "text":
        return f'<p>{inline(b["text"])}</p>'
    if t == "heading":
        return f'<h2 class="ll-h">{inline(b["text"])}</h2>'
    if t == "note":
        return f'<aside class="ll-note">{inline(b["text"])}</aside>'
    if t == "quote":
        who = f'<cite class="mono">{e(b["attribution"])}</cite>' if b.get("attribution") else ""
        return f'<blockquote class="ll-quote"><p>{inline(b["text"])}</p>{who}</blockquote>'
    if t == "list":
        items = "".join(f"<li>{inline(x)}</li>" for x in b["items"])
        return f'<ul class="ll-list">{items}</ul>'
    if t == "principles":
        rows = "".join(
            f'<div class="ll-rule"><div class="mono ll-when">{e(p["when"])}</div>'
            f'<div class="ll-what">{inline(p["rule"])}</div></div>'
            for p in b["items"])
        return f'<div class="ll-rules">{rows}</div>'
    if t == "code":
        lang = f'<div class="mono ll-code-lang">{e(b["lang"])}</div>' if b.get("lang") else ""
        cap = f'<figcaption class="mono ll-cap">{inline(b["caption"])}</figcaption>' if b.get("caption") else ""
        return (f'<figure class="ll-code">{lang}'
                f'<pre><code>{e(b["code"])}</code></pre>{cap}</figure>')
    if t == "math":
        # MathML renders natively. No CDN, no bundled renderer, no CSP change.
        cap = f'<figcaption class="mono ll-cap">{inline(b["caption"])}</figcaption>' if b.get("caption") else ""
        return f'<figure class="ll-math">{b["mathml"]}{cap}</figure>'
    if t == "figure":
        up = "../" * depth
        cap = f'<figcaption class="mono ll-cap">{inline(b["caption"])}</figcaption>' if b.get("caption") else ""
        if b.get("svg"):
            return f'<figure class="ll-fig">{b["svg"]}{cap}</figure>'
        src = str(b["src"])
        src = src if src.startswith("http") else f"{up}learning-log/{src}"
        return (f'<figure class="ll-fig"><img src="{e(src)}" alt="{e(b["alt"])}" '
                f'loading="lazy" decoding="async">{cap}</figure>')
    return ""


def section_list(key, heading, en):
    vals = en.get(key) or []
    if not vals:
        return ""          # never render an empty section
    items = "".join(f"<li>{inline(v)}</li>" for v in vals)
    return (f'<section class="ll-sec"><h2 class="ll-h">{e(heading)}</h2>'
            f'<ul class="ll-list">{items}</ul></section>')


def resources_block(en):
    rs = en.get("resources") or []
    if not rs:
        return ""
    rows = []
    for r in rs:
        note = f'<div class="ll-res-note">{inline(r["note"])}</div>' if r.get("note") else ""
        kind = f'<span class="mono ll-kind">{e(r["kind"])}</span>' if r.get("kind") else ""
        rows.append(
            f'<li class="ll-res">{kind}'
            f'<a class="ll-res-t" href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["title"])} &#8599;</a>'
            f'<div class="mono ll-res-a">{e(r["author"])}</div>{note}</li>')
    return ('<section class="ll-sec"><h2 class="ll-h">Read and watched</h2>'
            '<p class="ll-sec-note">Other people\'s ideas, credited. Where I have borrowed a framing '
            'rather than tested it myself, the entry says so.</p>'
            f'<ul class="ll-res-list">{"".join(rows)}</ul></section>')


def pathways_block(en, depth):
    ps = en.get("pathways") or []
    if not ps:
        return ""
    up = "../" * depth
    links = "".join(
        f'<a class="tag ll-path" href="{up}{PATHWAYS[p][1]}">{e(PATHWAYS[p][0])}</a>' for p in ps)
    return ('<section class="ll-sec"><h2 class="ll-h">Connected to</h2>'
            f'<div class="ll-paths">{links}</div></section>')


def links_block(en, depth):
    ls = en.get("links") or []
    if not ls:
        return ""
    ae.DEPTH["d"] = depth
    items = "".join(f'<li>{ae.ext(l["url"], l["label"])}</li>' for l in ls)
    return ('<section class="ll-sec"><h2 class="ll-h">Source and notes</h2>'
            f'<ul class="ll-links">{items}</ul></section>')


def entry_page(d, en, prev_en, draft_preview=False):
    # /learning-log/<id>/ is two levels below the site root;
    # /learning-log/preview/<id>/ is three.
    depth = 3 if draft_preview else 2
    up = "../" * depth
    tags = "".join(f'<li class="tag">{e(t)}</li>' for t in (en.get("tags") or []))
    tags = f'<ul class="tags ae-plain ll-tags">{tags}</ul>' if tags else ""

    body = "".join(block(b, depth) for b in en.get("body", []))
    sections = "".join(section_list(k, h, en) for k, h in SECTIONS)

    nxt = ""
    if en.get("next_focus"):
        nxt = ('<section class="ll-sec ll-next"><h2 class="ll-h">Next month</h2>'
               f'<p>{inline(en["next_focus"])}</p></section>')

    prev = ""
    if prev_en:
        prev = (f'<p class="mono ll-prev">Previously: '
                f'<a href="{up}learning-log/{e(prev_en["id"])}/">{e(prev_en["month"])} &mdash; '
                f'{e(prev_en["title"])}</a></p>')

    banner = ""
    if draft_preview:
        banner = ('<div class="ll-draft-banner"><p class="mono">Draft &mdash; not published. '
                  'This page exists only under <code>learning-log/preview/</code> for review, '
                  'is excluded from the index and carries a noindex robots tag.</p></div>')

    crumbs = (f'<p class="mono ae-crumb"><a href="{up}">Portfolio</a> / '
              f'<a href="{up}learning-log/">The Learning Log</a> / {e(en["month"])}</p>')

    html_body = f"""{banner}
<section class="wrap ll-entry-head">
  {crumbs}
  <p class="mono ll-month">{e(en['month'])}</p>
  <h1>{e(en['title'])}</h1>
  <p class="ll-sum">{inline(en['summary'])}</p>
  {tags}
</section>
<article class="wrap ll-body">
{body}
{sections}
{resources_block(en)}
{nxt}
{pathways_block(en, depth)}
{links_block(en, depth)}
{prev}
</article>
<section class="wrap ae-back"><p class="mono">
  <a href="{up}learning-log/">&#8592; All entries</a></p></section>"""

    out = (PREVIEW / en["id"] / "index.html") if draft_preview else (HERE / en["id"] / "index.html")
    canonical = f"https://morantejr.github.io/learning-log/{en['id']}/"
    return shell(out, depth, f"{en['title']} - The Learning Log - Joseph Morante",
                 en["summary"][:180], canonical, html_body, noindex=draft_preview)


def index_page(d, published):
    if published:
        rows = []
        for en in published:
            tags = "".join(f'<li class="tag">{e(t)}</li>' for t in (en.get("tags") or []))
            tags = f'<ul class="tags ae-plain ll-tags">{tags}</ul>' if tags else ""
            rows.append(f"""<a class="ll-card" href="{e(en['id'])}/">
  <div class="mono ll-month">{e(en['month'])}</div>
  <h2 class="ll-card-t">{e(en['title'])}</h2>
  <p class="ll-card-s">{inline(en['summary'])}</p>
  {tags}
</a>""")
        listing = f'<section class="wrap ll-grid">{"".join(rows)}</section>'
    else:
        listing = ('<section class="wrap"><p class="ll-empty">No entries published yet. '
                   'The first one is written and under review &mdash; it goes up when it has '
                   'something to show beyond good intentions.</p></section>')

    body = f"""<section class="wrap ll-head">
  <p class="mono ae-crumb"><a href="../">Portfolio</a> / The Learning Log</p>
  <h1>{e(d['title'])}</h1>
  <p class="ll-lede">{e(d['subtitle'])}</p>
  <p class="ll-stand">{inline(d['lede'])}</p>
  <p class="ae-disclosure">{inline(d['standard'])}</p>
</section>
{listing}
<section class="wrap ae-back"><p class="mono">
  <a href="../ai-engineering/">&#8592; Independent Study</a></p></section>"""
    return shell(HERE / "index.html", 1, f"{d['title']} - Joseph Morante",
                 d["meta_description"], d["canonical"], body)


EXTRA = """
/* --- The Learning Log --------------------------------------------------- */
.ll-head{padding-top:140px;padding-bottom:10px}
.ll-head h1{font-size:clamp(32px,4.6vw,58px);line-height:1.05;letter-spacing:-0.03em}
.ll-lede{margin:18px 0 0;max-width:640px;font-size:18px;line-height:1.6;color:var(--acc)}
.ll-stand{margin:22px 0 0;max-width:680px;font-size:16px;line-height:1.7;color:var(--mid);text-wrap:pretty}
.ll-grid{margin-top:46px;display:grid;gap:0;border-top:1px solid var(--line)}
.ll-card{display:block;padding:34px 0;border-bottom:1px solid var(--line);text-decoration:none;color:inherit;transition:opacity .18s}
.ll-card:hover{opacity:.62}
.ll-month{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint2)}
.ll-card-t{margin:10px 0 0;font-size:clamp(21px,2.3vw,28px);font-weight:500;letter-spacing:-0.02em;color:var(--fg)}
.ll-card-s{margin:12px 0 0;max-width:660px;font-size:16px;line-height:1.7;color:var(--mid);text-wrap:pretty}
.ll-tags{margin-top:16px}
.ll-empty{margin:46px 0 0;max-width:620px;font-size:16px;line-height:1.7;color:var(--mid);border-left:2px solid var(--line2);padding-left:16px}
.ll-entry-head{padding-top:140px;max-width:760px}
.ll-entry-head h1{margin:14px 0 0;font-size:clamp(28px,3.8vw,46px);line-height:1.1;letter-spacing:-0.03em;max-width:18ch}
.ll-sum{margin:20px 0 0;font-size:18px;line-height:1.65;color:var(--acc);text-wrap:pretty}
.ll-body{max-width:720px;padding-top:34px;padding-bottom:30px}
.ll-body p{margin:20px 0 0;font-size:17px;line-height:1.75;color:var(--mid);text-wrap:pretty}
.ll-h{margin:48px 0 0;font-size:21px;font-weight:500;letter-spacing:-0.02em;color:var(--fg)}
.ll-sec{margin-top:4px}
.ll-sec-note{margin:10px 0 0;font-size:14px;line-height:1.6;color:var(--faint)}
.ll-list{margin:18px 0 0;padding-left:20px}
.ll-list li{margin-top:10px;font-size:17px;line-height:1.75;color:var(--mid);text-wrap:pretty}
.ll-quote{margin:30px 0 0;padding:0 0 0 20px;border-left:2px solid var(--line2)}
.ll-quote p{margin:0;font-size:19px;line-height:1.6;color:var(--fg);font-style:italic}
.ll-quote cite{display:block;margin-top:10px;font-size:11px;font-style:normal;color:var(--faint2)}
.ll-note{display:block;margin:26px 0 0;padding:16px 18px;border:1px solid var(--line2);border-radius:8px;background:var(--panel);font-size:15px;line-height:1.7;color:var(--mid)}
.ll-rules{margin:22px 0 0;border-top:1px solid var(--line)}
.ll-rule{display:grid;grid-template-columns:160px minmax(0,1fr);gap:20px;padding:18px 0;border-bottom:1px solid var(--line)}
.ll-when{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint2);padding-top:3px}
.ll-what{font-size:16px;line-height:1.7;color:var(--mid);text-wrap:pretty}
.ll-code{margin:26px 0 0;border:1px solid var(--line2);border-radius:8px;background:var(--panel);overflow:hidden}
.ll-code-lang{padding:9px 14px;border-bottom:1px solid var(--line);font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint2)}
.ll-code pre{margin:0;padding:16px;overflow-x:auto}
.ll-code code{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;line-height:1.65;color:var(--fg)}
.ll-math{margin:26px 0 0;padding:18px;border:1px solid var(--line2);border-radius:8px;background:var(--panel);overflow-x:auto;text-align:center}
.ll-math math{font-size:18px;color:var(--fg)}
.ll-fig{margin:28px 0 0;padding:0;border:1px solid var(--line2);border-radius:8px;background:var(--panel);overflow:hidden}
.ll-fig img,.ll-fig svg{display:block;width:100%;height:auto}
.ll-cap{padding:12px 16px;border-top:1px solid var(--line);font-size:10.5px;letter-spacing:.05em;color:var(--faint2)}
.ll-res-list{margin:18px 0 0;padding:0;list-style:none;border-top:1px solid var(--line)}
.ll-res{padding:18px 0;border-bottom:1px solid var(--line)}
.ll-kind{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint2)}
.ll-res-t{display:inline-block;margin-top:7px;font-size:17px;color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line2)}
.ll-res-t:hover{opacity:.7}
.ll-res-a{margin-top:6px;font-size:12px;color:var(--faint)}
.ll-res-note{margin-top:9px;font-size:15px;line-height:1.65;color:var(--mid);max-width:620px}
.ll-paths{margin:18px 0 0;display:flex;flex-wrap:wrap;gap:8px}
.ll-path{text-decoration:none;color:var(--mid)}
.ll-path:hover{color:var(--fg)}
.ll-links{margin:18px 0 0;padding-left:20px}
.ll-links li{margin-top:9px}
.ll-next p{color:var(--mid)}
.ll-prev{margin:52px 0 0;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--faint)}
.ll-prev a{color:var(--acc)}
.ll-draft-banner{position:sticky;top:0;z-index:40;background:var(--panel);border-bottom:1px solid var(--line2)}
.ll-draft-banner p{margin:0;max-width:1160px;padding:11px 32px;font-size:11.5px;letter-spacing:.04em;color:var(--acc)}
.ll-draft-banner code{font-size:11px}
@media (max-width:640px){
 .ll-head,.ll-entry-head{padding-top:86px}
 .ll-rule{grid-template-columns:1fr;gap:6px}
 .ll-body p,.ll-list li{font-size:16px}
 .ll-draft-banner p{padding:11px 20px}
}
"""


def shell(path, depth, title, desc, canonical, body, noindex=False):
    ae.SHARED["css"], ae.SHARED["js"], ae.SHARED["icon"] = ae.extract_shared()
    ae.EXTRA_CSS = ae.EXTRA_CSS + EXTRA
    ae.HERE = HERE
    n = ae.page(path, depth, title, desc, canonical, body)
    if noindex:
        p = Path(path)
        s = p.read_text(encoding="utf-8").replace(
            "<title>", '<meta name="robots" content="noindex, nofollow">\n<title>', 1)
        p.write_text(s, encoding="utf-8")
        n = len(s)
    return n


def check_assets():
    """Every relative src/href in a generated page must resolve to a real file.

    An off-by-one in a page's depth silently produces 404s for fonts and
    cross-links, so the build resolves them against the tree instead of trusting
    the arithmetic.
    """
    problems = []
    pages = list(HERE.rglob("index.html"))
    for page_path in pages:
        text = page_path.read_text(encoding="utf-8")
        refs = set(re.findall(r'(?:src|href)="([^"#:]+?)"', text))
        refs |= set(re.findall(r'url\("([^"]+?)"\)', text))
        for ref in refs:
            if ref.startswith(("http", "data:", "mailto:", "//", "#")) or not ref.strip():
                continue
            target = (page_path.parent / ref).resolve()
            # A directory reference means its index.html.
            if ref.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                rel = page_path.relative_to(ROOT)
                problems.append(f"{rel} -> {ref} (resolves to {target}, which is missing)")
    return problems


def build(render_drafts=False):
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    validate(d)
    check_pathway_targets()
    if errors:
        print("FAILED - content did not validate:\n", file=sys.stderr)
        for m in errors:
            print(f"  error: {m}", file=sys.stderr)
        return 1
    for m in warnings:
        print(f"  warning: {m}")

    entries = sorted(d["entries"], key=lambda x: x["id"], reverse=True)
    published = [x for x in entries if not x.get("draft", False)]
    drafts = [x for x in entries if x.get("draft", False)]

    # A plain build must never leave a rendered draft behind.
    if PREVIEW.exists():
        shutil.rmtree(PREVIEW)

    total = index_page(d, published)
    pages = 1
    for i, en in enumerate(published):
        prev_en = published[i + 1] if i + 1 < len(published) else None
        total += entry_page(d, en, prev_en)
        pages += 1

    if render_drafts:
        for en in drafts:
            total += entry_page(d, en, None, draft_preview=True)
            pages += 1

    # Stale published directories for entries that were later turned into drafts.
    for child in HERE.iterdir():
        if child.is_dir() and MONTH_ID.match(child.name):
            if child.name not in {x["id"] for x in published}:
                shutil.rmtree(child)
                print(f"  removed stale page for unpublished entry {child.name}")

    bad = check_assets()
    if bad:
        print("FAILED - generated pages reference files that do not exist:\n", file=sys.stderr)
        for m in bad:
            print(f"  error: {m}", file=sys.stderr)
        return 1

    print(f"built {pages} pages, {total:,} bytes total")
    print(f"  published {len(published)} | drafts {len(drafts)}"
          f"{' (rendered under preview/, not linked)' if render_drafts and drafts else ''}")
    for en in drafts:
        print(f"  draft, not published: {en['id']} {en['title']!r}")
    return 0


# --------------------------------------------------------------------------
# bite tests: inject a defect, assert the validator rejects it
# --------------------------------------------------------------------------

def _bite(name, mutate):
    global errors, warnings
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    mutate(d)
    errors, warnings = [], []
    validate(d, today=datetime.date(2026, 10, 26))
    ok = bool(errors)
    print(f"  {'pass' if ok else 'FAIL'}  {name}")
    return ok


def run_tests():
    global errors, warnings
    print("bite tests (each injects a defect and asserts the build rejects it)")
    results = [
        _bite("future-dated entry is rejected",
              lambda d: d["entries"].insert(0, dict(d["entries"][0], id="2027-06", month="June 2027"))),
        _bite("duplicate entry id is rejected",
              lambda d: d["entries"].append(dict(d["entries"][0]))),
        _bite("month name that disagrees with the id is rejected",
              lambda d: d["entries"][0].update(month="March 2026")),
        _bite("published entry with no evidence and no body is rejected",
              lambda d: d["entries"][0].update(draft=False, body=[], **{f: [] for f in EVIDENCE_FIELDS})),
        _bite("unknown pathway id is rejected",
              lambda d: d["entries"][0].update(pathways=["not-a-real-section"])),
        _bite("resource without a url is rejected",
              lambda d: d["entries"][0]["resources"][0].pop("url")),
        _bite("non-https resource url is rejected",
              lambda d: d["entries"][0]["resources"][0].update(url="http://example.com")),
        _bite("unknown block type is rejected",
              lambda d: d["entries"][0]["body"].append({"type": "marquee", "text": "no"})),
        _bite("figure without alt text is rejected",
              lambda d: d["entries"][0]["body"].append({"type": "figure", "src": "a.png"})),
        _bite("draft flag that is not a boolean is rejected",
              lambda d: d["entries"][0].update(draft="yes")),
    ]
    # And the clean file must pass.
    errors, warnings = [], []
    validate(json.loads(CONTENT.read_text(encoding="utf-8")), today=datetime.date(2026, 10, 26))
    clean = not errors
    print(f"  {'pass' if clean else 'FAIL'}  the real content file validates")
    if not clean:
        for m in errors:
            print(f"      {m}")
    results.append(clean)
    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(run_tests())
    if "--check" in sys.argv:
        validate(json.loads(CONTENT.read_text(encoding="utf-8")))
        if errors:
            for m in errors:
                print(f"  error: {m}", file=sys.stderr)
            sys.exit(1)
        for m in warnings:
            print(f"  warning: {m}")
        print("content OK")
        sys.exit(0)
    sys.exit(build(render_drafts="--drafts" in sys.argv))
