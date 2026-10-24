#!/usr/bin/env python3
"""Generate ai-engineering/index.html from the JSON files in content/.

No third-party dependencies. The design system is not copied: the <style>
block and the theme <script> are lifted out of the site's index.html at build
time, so this page cannot drift from the rest of the site.

Usage:
    python3 ai-engineering/build.py            # validate, then write the page
    python3 ai-engineering/build.py --check    # validate only, write nothing
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = HERE / "content"
OUT = HERE / "index.html"

STATUSES = ("planned", "in-progress", "completed")
STATUS_LABEL = {
    "planned": "Planned",
    "in-progress": "In progress",
    "completed": "Completed",
}
SKILL_STATES = ("planning", "practicing", "demonstrated")
SKILL_LABEL = {
    "planning": "Planning to learn",
    "practicing": "Currently practising",
    "demonstrated": "Demonstrated by an artifact",
}
KINDS = ("independent", "tutorial", "research", "production")
KIND_LABEL = {
    "independent": "Independent engineering",
    "tutorial": "Tutorial exercise",
    "research": "Research prototype",
    "production": "Production system",
}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load(name: str):
    path = CONTENT / name
    if not path.exists():
        err(f"{name}: missing")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        err(f"{name}: invalid JSON ({exc})")
        return None


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check_url(value, where: str) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        err(f"{where}: url must be a string")
    elif not (value.startswith(("http://", "https://", "../", "#", "/"))
              or value.endswith((".pdf", ".html"))):
        err(f"{where}: url looks malformed -> {value!r}")


def require(item: dict, fields: tuple[str, ...], where: str) -> None:
    for field in fields:
        if field not in item:
            err(f"{where}: missing required field {field!r}")
        elif item[field] in (None, "", []) and field not in ("skills", "outcomes"):
            err(f"{where}: required field {field!r} is empty")


def check_ids(items, where: str) -> set:
    seen: set = set()
    for i, item in enumerate(items or []):
        ident = item.get("id")
        if not ident:
            err(f"{where}[{i}]: missing id")
            continue
        if not SLUG.match(ident):
            err(f"{where}[{i}]: id {ident!r} must be lowercase-hyphen-slug")
        if ident in seen:
            err(f"{where}: duplicate id {ident!r}")
        seen.add(ident)
    return seen


def validate(page, pathways, courses, scratch, artifacts, notes, roadmap):
    if page:
        require(page, ("heading", "lede", "meta_description", "canonical"), "page.json")

    pathway_ids = check_ids(pathways, "pathways.json")
    artifact_ids = check_ids(artifacts, "artifacts.json")
    course_ids = check_ids(courses, "courses.json")
    check_ids(scratch, "scratch.json")
    check_ids(notes, "notes.json")

    for item in pathways or []:
        where = f"pathways.json[{item.get('id')}]"
        require(item, ("name", "summary", "competencies"), where)

    for item in courses or []:
        where = f"courses.json[{item.get('id')}]"
        require(item, ("title", "provider", "url", "status", "pathway"), where)
        status = item.get("status")
        if status not in STATUSES:
            err(f"{where}: status {status!r} not one of {STATUSES}")
        if status == "completed" and not item.get("placeholder"):
            if not (item.get("completed_date") or item.get("certificate_url")):
                err(f"{where}: marked completed with no completion date or certificate URL")
        if item.get("pathway") and item["pathway"] not in pathway_ids:
            err(f"{where}: pathway {item['pathway']!r} does not exist")
        ref = item.get("related_artifact")
        if ref and ref not in artifact_ids:
            err(f"{where}: related_artifact {ref!r} does not exist")
        check_url(item.get("url"), where)
        check_url(item.get("certificate_url"), where)

    for item in scratch or []:
        where = f"scratch.json[{item.get('id')}]"
        require(item, ("title", "concept", "status", "pathway"), where)
        if item.get("status") not in STATUSES:
            err(f"{where}: status {item.get('status')!r} not one of {STATUSES}")
        if item.get("pathway") and item["pathway"] not in pathway_ids:
            err(f"{where}: pathway {item['pathway']!r} does not exist")
        if item.get("status") == "completed" and not item.get("placeholder"):
            if not item.get("repo_url"):
                warn(f"{where}: completed module has no implementation repository")
        check_url(item.get("repo_url"), where)

    for item in artifacts or []:
        where = f"artifacts.json[{item.get('id')}]"
        require(item, ("name", "kind", "problem", "architecture", "stack", "pathway"), where)
        if item.get("kind") not in KINDS:
            err(f"{where}: kind {item.get('kind')!r} not one of {KINDS}")
        if item.get("pathway") and item["pathway"] not in pathway_ids:
            err(f"{where}: pathway {item['pathway']!r} does not exist")
        for ref in item.get("related_courses", []):
            if ref not in course_ids:
                err(f"{where}: related_courses entry {ref!r} does not exist")
        check_url(item.get("repo_url"), where)
        for link in item.get("extra_links", []):
            check_url(link.get("url"), where)

    for item in notes or []:
        where = f"notes.json[{item.get('id')}]"
        require(item, ("title", "summary"), where)
        if item.get("pathway") and item["pathway"] not in pathway_ids:
            err(f"{where}: pathway {item['pathway']!r} does not exist")
        check_url(item.get("url"), where)

    for stage in (roadmap or {}).get("stages", []):
        where = f"roadmap.json[{stage.get('id')}]"
        require(stage, ("name", "summary", "skills"), where)
        for skill in stage.get("skills", []):
            if skill.get("state") not in SKILL_STATES:
                err(f"{where}: skill state {skill.get('state')!r} not one of {SKILL_STATES}")
            ev = skill.get("evidence")
            if ev and ev not in artifact_ids:
                err(f"{where}: evidence {ev!r} does not exist in artifacts.json")
            if skill.get("state") == "demonstrated" and not ev:
                err(f"{where}: skill {skill.get('name')!r} is 'demonstrated' with no artifact")


# --------------------------------------------------------------------------
# rendering helpers
# --------------------------------------------------------------------------

def e(value) -> str:
    return html.escape(str(value), quote=True) if value is not None else ""


def real(items):
    """Entries that are not marked placeholders. Counts come only from these."""
    return [i for i in (items or []) if not i.get("placeholder")]


def status_pill(status: str) -> str:
    return (f'<span class="ae-pill ae-{e(status)}">'
            f'<span class="ae-dot" aria-hidden="true"></span>{e(STATUS_LABEL[status])}</span>')


def tags(values) -> str:
    if not values:
        return ""
    items = "".join(f'<li class="tag">{e(v)}</li>' for v in values)
    return f'<ul class="tags ae-plain">{items}</ul>'


def ext(url: str, label: str, cls: str = "mono lnk") -> str:
    rel = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
    arrow = " &#8599;" if url.startswith("http") else ""
    return f'<a class="{cls}" href="{e(url)}"{rel}>{e(label)}{arrow}</a>'


def facts(pairs) -> str:
    rows = "".join(
        f'<dt class="mono fl">{e(k)}</dt><dd>{v}</dd>'
        for k, v in pairs if v
    )
    return f'<dl class="facts ae-facts">{rows}</dl>' if rows else ""


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def render_pathways(pathways, courses, scratch, artifacts) -> str:
    cards = []
    for p in pathways:
        pid = p["id"]
        p_courses = [c for c in real(courses) if c.get("pathway") == pid]
        p_modules = [m for m in real(scratch) if m.get("pathway") == pid]
        p_artifacts = [a for a in real(artifacts) if a.get("pathway") == pid]
        counts = []
        if p_courses:
            counts.append(f"{len(p_courses)} course{'s' if len(p_courses) != 1 else ''}")
        if p_modules:
            counts.append(f"{len(p_modules)} module{'s' if len(p_modules) != 1 else ''}")
        if p_artifacts:
            counts.append(f"{len(p_artifacts)} artifact{'s' if len(p_artifacts) != 1 else ''}")
        tally = ", ".join(counts) if counts else "Nothing recorded yet"
        comps = "".join(f"<li>{e(c)}</li>" for c in p.get("competencies", []))
        linked = ""
        if p_artifacts:
            links = " ".join(
                f'<a class="ul" href="#artifact-{e(a["id"])}">{e(a["name"])}</a>'
                for a in p_artifacts
            )
            linked = f'<p class="ae-linked"><span class="mono pl">Evidence</span> {links}</p>'
        cards.append(f"""      <article class="card ae-pathway">
        <h3 class="card-t ae-h3">{e(p['name'])}</h3>
        <p class="card-d">{e(p['summary'])}</p>
        <ul class="ae-comps">{comps}</ul>
        {linked}
        <p class="mono ae-tally">{e(tally)}</p>
      </article>""")
    return "\n".join(cards)


def render_courses(courses, artifacts) -> str:
    by_id = {a["id"]: a for a in artifacts}
    rows = []
    for c in courses:
        ph = c.get("placeholder")
        meta = [c.get("provider"), c.get("institution")]
        meta = " &middot; ".join(e(m) for m in meta if m)
        bits = []
        if c.get("status") == "completed" and c.get("completed_date"):
            bits.append(("Completed", e(c["completed_date"])))
        if c.get("skills"):
            bits.append(("Skills", ", ".join(e(s) for s in c["skills"])))
        if c.get("outcomes"):
            bits.append(("Outcome", "<br>".join(e(o) for o in c["outcomes"])))
        ref = c.get("related_artifact")
        if ref and ref in by_id:
            bits.append(("Applied in",
                         f'<a class="ul" href="#artifact-{e(ref)}">{e(by_id[ref]["name"])}</a>'))
        links = []
        if c.get("url"):
            links.append(ext(c["url"], "Course page"))
        if c.get("certificate_url"):
            links.append(ext(c["certificate_url"], "Certificate"))
        links_html = f'<p class="ae-links">{" ".join(links)}</p>' if links else ""
        rows.append(f"""      <article class="card ae-course{' ae-ph' if ph else ''}">
        <div class="ae-course-top">{status_pill(c['status'])}{placeholder_tag(ph)}</div>
        <h3 class="card-t ae-h3">{e(c['title'])}</h3>
        <p class="mono ae-meta">{meta}</p>
        {facts(bits)}
        {links_html}
      </article>""")
    return "\n".join(rows)


def placeholder_tag(is_ph) -> str:
    return '<span class="ae-ph-tag mono">Example entry</span>' if is_ph else ""


def render_scratch(modules) -> str:
    rows = []
    for m in modules:
        ph = m.get("placeholder")
        bits = [
            ("Concept", e(m.get("concept"))),
            ("Tests", e(m.get("tests"))),
            ("Benchmarks", e(m.get("benchmarks"))),
            ("Notes", e(m.get("notes"))),
            ("Limitations", e(m.get("limitations"))),
        ]
        link = f'<p class="ae-links">{ext(m["repo_url"], "Implementation")}</p>' if m.get("repo_url") else ""
        rows.append(f"""      <article class="card ae-course{' ae-ph' if ph else ''}">
        <div class="ae-course-top">{status_pill(m['status'])}{placeholder_tag(ph)}</div>
        <h3 class="card-t ae-h3">{e(m['title'])}</h3>
        {facts(bits)}
        {link}
      </article>""")
    return "\n".join(rows)


def render_artifacts(artifacts, courses) -> str:
    by_id = {c["id"]: c for c in courses}
    blocks = []
    for a in artifacts:
        ph = a.get("placeholder")
        related = [by_id[r]["title"] for r in a.get("related_courses", []) if r in by_id]
        bits = [
            ("Problem", e(a.get("problem"))),
            ("Architecture", e(a.get("architecture"))),
            ("Decisions", "<br>".join(e(d) for d in a.get("decisions", []))),
            ("Testing", e(a.get("testing"))),
            ("Results", e(a.get("evaluation"))),
            ("Deployment", e(a.get("deployment"))),
            ("Limitations", e(a.get("limitations"))),
            ("Related coursework", ", ".join(e(r) for r in related)),
        ]
        links = []
        if a.get("repo_url"):
            links.append(ext(a["repo_url"], "Repository"))
        for link in a.get("extra_links", []):
            links.append(ext(link["url"], link["label"]))
        links_html = f'<p class="ae-links">{" ".join(links)}</p>' if links else ""
        blocks.append(f"""      <article class="ae-artifact{' ae-ph' if ph else ''}" id="artifact-{e(a['id'])}">
        <div class="ae-course-top"><span class="mono ae-kind">{e(KIND_LABEL[a['kind']])}</span>{placeholder_tag(ph)}</div>
        <h3 class="ae-h3 ae-artifact-h">{e(a['name'])}</h3>
        {tags(a.get('stack'))}
        {facts(bits)}
        {links_html}
      </article>""")
    return "\n".join(blocks)


def render_notes(notes) -> str:
    if not notes:
        return '<p class="body-md">No write-ups published yet.</p>'
    rows = []
    for n in notes:
        ph = n.get("placeholder")
        bits = [
            ("Learned", e(n.get("learned"))),
            ("Mechanism", e(n.get("mechanism"))),
            ("Implemented", e(n.get("implemented"))),
            ("What failed", e(n.get("failed"))),
            ("Tradeoffs", e(n.get("tradeoffs"))),
            ("In production", e(n.get("production"))),
        ]
        link = f'<p class="ae-links">{ext(n["url"], "Read the note")}</p>' if n.get("url") else ""
        rows.append(f"""      <article class="card ae-course{' ae-ph' if ph else ''}">
        <div class="ae-course-top"><span class="mono ae-meta">{e(n.get('date') or '')}</span>{placeholder_tag(ph)}</div>
        <h3 class="card-t ae-h3">{e(n['title'])}</h3>
        <p class="card-d">{e(n['summary'])}</p>
        {facts(bits)}
        {link}
      </article>""")
    return "\n".join(rows)


def render_roadmap(roadmap, artifacts) -> str:
    by_id = {a["id"]: a for a in artifacts}
    cols = []
    for stage in roadmap.get("stages", []):
        items = []
        for s in stage.get("skills", []):
            ev = s.get("evidence")
            tail = ""
            if ev and ev in by_id:
                tail = f' <a class="ul" href="#artifact-{e(ev)}">{e(by_id[ev]["name"])}</a>'
            items.append(
                f'<li class="ae-skill ae-s-{e(s["state"])}">'
                f'<span class="ae-state mono">{e(SKILL_LABEL[s["state"]])}</span>'
                f'<span class="ae-skill-n">{e(s["name"])}{tail}</span></li>'
            )
        cols.append(f"""      <section class="ae-stage">
        <h3 class="ae-h3 ae-stage-h">{e(stage['name'])}</h3>
        <p class="ae-stage-s">{e(stage['summary'])}</p>
        <ul class="ae-skills">{''.join(items)}</ul>
      </section>""")
    return "\n".join(cols)


def render_summary(courses, scratch, artifacts) -> str:
    rc, rm, ra = real(courses), real(scratch), real(artifacts)
    done = len([c for c in rc if c.get("status") == "completed"])
    prog = len([c for c in rc if c.get("status") == "in-progress"])
    mods = len([m for m in rm if m.get("status") == "completed"])
    cells = [
        (str(done), "Courses completed"),
        (str(prog), "Courses in progress"),
        (str(mods), "Modules implemented"),
        (str(len(ra)), "Artifacts with evidence"),
    ]
    out = "".join(
        f'<div class="stat"><div class="stat-v">{v}</div>'
        f'<div class="mono stat-l">{e(l)}</div></div>'
        for v, l in cells
    )
    return f'<div class="stats ae-stats">{out}</div>'


# --------------------------------------------------------------------------
# page assembly
# --------------------------------------------------------------------------

EXTRA_CSS = """
/* --- AI Engineering page ------------------------------------------------ */
.ae-main{padding-bottom:40px}
.ae-head{padding-top:140px}
.ae-head h1{font-size:clamp(34px,5vw,62px);line-height:1.04;max-width:14ch}
.ae-lede{margin:26px 0 0;max-width:680px;font-size:19px;line-height:1.6;color:var(--acc);text-wrap:pretty}
.ae-stand{margin:22px 0 0;max-width:680px;font-size:16.5px;line-height:1.65;color:var(--mid);text-wrap:pretty}
.ae-stats{margin-top:56px}
.ae-sec{padding-top:96px}
.ae-sec > .sec-head{margin-bottom:0}
.ae-intro{margin:26px 0 0;max-width:720px;font-size:16px;line-height:1.65;color:var(--mid);text-wrap:pretty}
.ae-grid{margin-top:30px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.ae-grid > .card{background:var(--bg)}
.ae-h3{margin:10px 0 0;font-size:20px;letter-spacing:-0.015em;line-height:1.3;font-weight:500;color:var(--fg)}
.ae-comps{margin:14px 0 0;padding-left:18px;font-size:14px;line-height:1.6;color:var(--mid)}
.ae-comps li{margin-top:4px}
.ae-tally{margin:16px 0 0;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--faint)}
.ae-linked{margin:14px 0 0;font-size:14px;line-height:1.6;color:var(--mid)}
.ae-linked .pl{margin-right:8px}
.ae-course-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ae-pill{display:inline-flex;align-items:center;gap:7px;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10.5px;letter-spacing:0.1em;text-transform:uppercase;color:var(--faint)}
.ae-dot{width:7px;height:7px;border-radius:50%;flex:none;border:1px solid var(--line3)}
.ae-completed .ae-dot{background:var(--acc);border-color:var(--acc)}
.ae-in-progress .ae-dot{background:var(--warm);border-color:var(--warm)}
.ae-completed{color:var(--fg2)}
.ae-in-progress{color:var(--warm)}
.ae-ph-tag{font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:var(--faint2);border:1px dashed var(--line2);border-radius:4px;padding:3px 7px}
.ae-ph{opacity:0.72}
.ae-meta{margin:8px 0 0;font-size:12px;letter-spacing:0.06em;color:var(--faint)}
.ae-kind{font-size:10.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--acc)}
.ae-facts{margin-top:18px;font-size:14px}
.ae-facts dd{margin:0}
.ae-links{margin:18px 0 0;display:flex;flex-wrap:wrap;gap:16px}
.tags.ae-plain{list-style:none;padding:0}
.ae-artifact{padding:34px 0;border-bottom:1px solid var(--line)}
.ae-artifact:last-child{border-bottom:0}
.ae-artifact-h{font-size:28px;margin-top:12px}
.ae-artifact .ae-facts{max-width:760px}
.ae-roadmap{margin-top:30px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.ae-stage{background:var(--bg);padding:26px 22px}
.ae-stage-h{font-size:17px;margin-top:0}
.ae-stage-s{margin:8px 0 0;font-size:13.5px;line-height:1.55;color:var(--faint)}
.ae-skills{margin:18px 0 0;padding:0;list-style:none}
.ae-skill{margin-top:14px;padding-left:12px;border-left:2px solid var(--line2)}
.ae-s-demonstrated{border-left-color:var(--acc)}
.ae-s-practicing{border-left-color:var(--warm)}
.ae-state{display:block;font-size:9.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--faint)}
.ae-skill-n{display:block;margin-top:4px;font-size:14px;line-height:1.5;color:var(--fg2)}
.ae-note{margin:26px 0 0;max-width:720px;font-size:14px;line-height:1.6;color:var(--faint);border-left:2px solid var(--line2);padding-left:14px}
@media (max-width:900px){
 .ae-roadmap{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media (max-width:640px){
 .ae-head{padding-top:86px}
 .ae-sec{padding-top:70px}
 .ae-grid,.ae-roadmap{grid-template-columns:1fr}
 .ae-artifact-h{font-size:24px}
}
"""

NAV = """<header class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="../"><span class="brand-name">Joseph Morante</span><span class="mono brand-tag">Measurement</span></a>
    <nav class="nav-links" aria-label="Primary">
      <a href="../#work">Work</a>
      <a href="../#research">Research</a>
      <a href="./" aria-current="page">AI Engineering</a>
      <a href="../#experience">Experience</a>
      <a href="../#about">About</a>
      <a class="btn-outline-sm" href="../JosephMorante_Resume.pdf" target="_blank" rel="noopener">Resume</a>
    </nav>
  </div>
</header>"""


def extract_shared():
    """Pull the <style> block and the theme <script> out of the site's index.html."""
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", source, re.S)
    if not style:
        err("index.html: could not find the <style> block to share")
        return "", "", ""
    script = re.search(r"<script>\s*\(function\(\)\{\s*var root=document\.documentElement.*?</script>",
                       source, re.S)
    if not script:
        err("index.html: could not find the theme script to share")
        return style.group(1), "", ""
    icon = re.search(r'<link rel="icon"[^>]*>', source)
    if not icon:
        warn("index.html: no favicon link found; the page will use the browser default")

    css = style.group(1)
    # The shared CSS is written for a page at the site root. This page lives one
    # level down, so root-relative asset paths have to be rewritten or they 404.
    css, n = re.subn(r'url\("fonts/', 'url("../fonts/', css)
    if n == 0:
        warn("index.html: no font URLs found to rewrite for the subdirectory")

    return css, script.group(0), (icon.group(0) if icon else "")


def build() -> int:
    page = load("page.json")
    pathways = load("pathways.json")
    courses = load("courses.json")
    scratch = load("scratch.json")
    artifacts = load("artifacts.json")
    notes = load("notes.json")
    roadmap = load("roadmap.json")

    validate(page, pathways, courses, scratch, artifacts, notes, roadmap)
    shared_css, theme_js, icon_tag = extract_shared()

    if errors:
        print("FAILED — content did not validate:\n", file=sys.stderr)
        for m in errors:
            print(f"  error: {m}", file=sys.stderr)
        for m in warnings:
            print(f"  warn:  {m}", file=sys.stderr)
        return 1

    for m in warnings:
        print(f"  warn:  {m}")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Engineering - Joseph Morante</title>
<meta name="description" content="{e(page['meta_description'])}">
<link rel="canonical" href="{e(page['canonical'])}">
<meta property="og:title" content="{e(page.get('og_title', 'AI Engineering'))}">
<meta property="og:description" content="{e(page.get('og_description', page['meta_description']))}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(page['canonical'])}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#08080a">
{icon_tag}
{theme_js}
<style>{shared_css}{EXTRA_CSS}</style>
</head>
<body>
<a class="skip" href="#pathways">Skip to content</a>
{NAV}

<main class="ae-main" id="top">

<header class="wrap ae-head">
  <p class="mono eyebrow">Continuing education &middot; Implementations &middot; Evidence</p>
  <h1>{e(page['heading'])}</h1>
  <p class="ae-lede">{e(page['lede'])}</p>
  <p class="ae-stand">{e(page['standfirst'])}</p>
  {render_summary(courses, scratch, artifacts)}
  <p class="ae-note">Counts above are derived only from entries recorded on this page, and exclude the example entries that show the content format. Coursework is listed as completed only where a completion date or certificate is recorded.</p>
</header>

<section id="pathways" class="wrap ae-sec">
  <div class="sec-head"><h2>Learning pathways</h2><div class="mono kicker">Six tracks</div></div>
  <p class="ae-intro">The curriculum split into the areas a production AI system actually demands. Each track lists the competencies I am working toward and links to whatever on this page stands as evidence for it.</p>
  <div class="ae-grid">
{render_pathways(pathways, courses, scratch, artifacts)}
  </div>
</section>

<section id="coursework" class="wrap ae-sec">
  <div class="sec-head"><h2>Coursework</h2><div class="mono kicker">Coursera</div></div>
  <p class="ae-intro">Structured courses, with the skills each one covers and the implementation it fed into where there is one. A course earns a completed status here only when a completion date or certificate is on file.</p>
  <div class="ae-grid">
{render_courses(courses, artifacts)}
  </div>
</section>

<section id="from-scratch" class="wrap ae-sec">
  <div class="sec-head"><h2>AI Engineering from Scratch</h2><div class="mono kicker">Implementation-first</div></div>
  <p class="ae-intro">Working through <a class="ul" href="https://aiengineeringfromscratch.com/" target="_blank" rel="noopener">aiengineeringfromscratch.com</a>, where the point is building the mechanism rather than watching someone else build it. Each module is recorded with its implementation, what the tests assert, what was measured, and what the implementation does not handle. Curriculum text is not reproduced here.</p>
  <div class="ae-grid">
{render_scratch(scratch)}
  </div>
</section>

<section id="built" class="wrap ae-sec">
  <div class="sec-head"><h2>Built, tested &amp; deployed</h2><div class="mono kicker">Engineering evidence</div></div>
  <p class="ae-intro">Artifacts, each labelled by what it actually is: independent engineering, a tutorial exercise, a research prototype, or a production system. Employer work appears without code or data.</p>
{render_artifacts(artifacts, courses)}
</section>

<section id="notes" class="wrap ae-sec">
  <div class="sec-head"><h2>Technical learning notes</h2><div class="mono kicker">Write-ups</div></div>
  <p class="ae-intro">Short pieces on a mechanism I had to understand properly: how it works, what I implemented, what broke, and what it would mean in production.</p>
  <div class="ae-grid">
{render_notes(notes)}
  </div>
</section>

<section id="roadmap" class="wrap ae-sec">
  <div class="sec-head"><h2>Roadmap</h2><div class="mono kicker">Foundations &#8594; Reliability</div></div>
  <p class="ae-intro">What I am planning to learn, what I am practising, and what an artifact on this page already demonstrates. Finishing a course does not move a skill into the demonstrated column; shipping something that works does.</p>
  <div class="ae-roadmap">
{render_roadmap(roadmap, artifacts)}
  </div>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2 class="h2-sm">Questions about any of this?</h2></div>
  <p class="ae-intro">I am glad to go deeper on any artifact here, including the employer work I cannot publish. <a class="ul" href="mailto:morantejoseph1@gmail.com">Email me</a>.</p>
  <div class="mono foot"><span><a href="../">&#8592; Back to the portfolio</a></span><span>morantejoseph1@gmail.com</span></div>
</section>

</main>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"built {OUT.relative_to(ROOT)} ({len(doc):,} bytes)")
    print(f"  pathways {len(pathways)} | courses {len(courses)} "
          f"({len(real(courses))} real) | modules {len(scratch)} "
          f"({len(real(scratch))} real) | artifacts {len(artifacts)} "
          f"({len(real(artifacts))} real) | notes {len(notes)} ({len(real(notes))} real)")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        data = [load(f) for f in ("page.json", "pathways.json", "courses.json",
                                  "scratch.json", "artifacts.json", "notes.json",
                                  "roadmap.json")]
        validate(*data)
        if errors:
            for m in errors:
                print(f"  error: {m}", file=sys.stderr)
            sys.exit(1)
        for m in warnings:
            print(f"  warn:  {m}")
        print("content OK")
        sys.exit(0)
    sys.exit(build())
