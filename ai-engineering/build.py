#!/usr/bin/env python3
"""Generate the AI Engineering hub from the JSON files in content/.

No third-party dependencies. The design system is not copied: the <style>
block, theme script and favicon are lifted out of the site's index.html at
build time, so these pages cannot drift from the rest of the site.

    python3 ai-engineering/build.py --check    # validate only, write nothing
    python3 ai-engineering/build.py            # validate, then write pages
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
CONTENT = HERE / "content"

STATUSES = ("planned", "in-progress", "completed")
STATUS_LABEL = {"planned": "Planned", "in-progress": "In progress", "completed": "Completed"}
SKILL_STATES = ("planning", "practicing", "demonstrated")
SKILL_LABEL = {"planning": "Planning to learn",
               "practicing": "Currently practising",
               "demonstrated": "Demonstrated by an artifact"}
KINDS = ("independent", "tutorial", "research", "production")
KIND_LABEL = {"independent": "Independent engineering", "tutorial": "Tutorial exercise",
              "research": "Research prototype", "production": "Production system"}

errors: list[str] = []
warnings: list[str] = []
SLUG = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")


def err(m): errors.append(m)
def warn(m): warnings.append(m)
def e(v): return html.escape(str(v), quote=True) if v is not None else ""


def load(name):
    p = CONTENT / name
    if not p.exists():
        err(f"{name}: missing")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        err(f"{name}: invalid JSON ({exc})")
        return None


class Data:
    def __init__(self):
        self.page = load("page.json") or {}
        cur = load("curricula.json") or {}
        self.curricula = cur.get("curricula", [])
        self.specs = cur.get("specializations", [])
        self.source_note = cur.get("source_note", "")
        self.courses = load("courses.json") or []
        mod = load("modules.json") or {}
        self.modules = mod.get("modules", [])
        self.modmeta = mod
        self.competencies = load("competencies.json") or []
        self.artifacts = load("artifacts.json") or []
        self.notes = load("notes.json") or []
        self.roadmap = load("roadmap.json") or {}
        self.signal = load("signal.json") or {}
        self.scenesearch = load("scenesearch.json") or {}
        self.spec_by_id = {s["id"]: s for s in self.specs}
        self.cur_by_id = {c["id"]: c for c in self.curricula}
        self.art_by_id = {a["id"]: a for a in self.artifacts}
        self.comp_by_id = {c["id"]: c for c in self.competencies}
        self.mod_by_id = {m["id"]: m for m in self.modules}
        self.course_by_id = {c["id"]: c for c in self.courses}

    # --- derived, always from real records -------------------------------
    def real(self, items):
        return [i for i in items if not i.get("placeholder")]

    def courses_for(self, curriculum, role=None):
        out = []
        for c in self.courses:
            for m in c.get("curricula", []):
                if m["curriculum"] == curriculum and (role is None or m["role"] == role):
                    out.append(c)
        return out

    def specs_for(self, curriculum, role):
        seen, out = set(), []
        for c in self.courses_for(curriculum, role):
            s = c["specialization"]
            if s not in seen:
                seen.add(s)
                out.append(self.spec_by_id[s])
        return out

    def counts(self):
        rc = self.courses
        return {
            "unique_courses": len(rc),
            "completed": len([c for c in rc if c["status"] == "completed"]),
            "in_progress": len([c for c in rc if c["status"] == "in-progress"]),
            "planned": len([c for c in rc if c["status"] == "planned"]),
            "modules": len(self.modules),
            "modules_done": len([m for m in self.modules if m["status"] == "completed"]),
            "artifacts": len(self.real(self.artifacts)),
            "notes": len(self.real(self.notes)),
            "competencies_with_evidence": len([c for c in self.competencies if c.get("artifacts")]),
        }


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(d: Data):
    if d.page:
        for f in ("heading", "lede", "disclosure", "meta_description", "canonical"):
            if not d.page.get(f):
                err(f"page.json: missing or empty {f!r}")

    spec_ids = {s["id"] for s in d.specs}
    cur_ids = {c["id"] for c in d.curricula}
    art_ids = {a["id"] for a in d.artifacts}
    comp_ids = {c["id"] for c in d.competencies}
    mod_ids = {m["id"] for m in d.modules}
    course_ids = set()

    for s in d.specs:
        if s.get("status") not in ("available", "in-development"):
            err(f"curricula.json[{s['id']}]: status {s.get('status')!r} must be available or in-development")

    for c in d.curricula:
        if c.get("status") not in STATUSES:
            err(f"curricula.json[{c['id']}]: status {c.get('status')!r} not one of {STATUSES}")
        if not c.get("source_url"):
            err(f"curricula.json[{c['id']}]: no source_url")
        if not c.get("verified_on"):
            warn(f"curricula.json[{c['id']}]: not yet verified against its source")

    for i, c in enumerate(d.courses):
        w = f"courses.json[{c.get('id', i)}]"
        for f in ("id", "title", "status", "official_url",
                  "source_url", "verified_on"):
            if not c.get(f):
                err(f"{w}: missing required field {f!r}")
        if c.get("id"):
            if c["id"] in course_ids:
                err(f"{w}: duplicate course id")
            course_ids.add(c["id"])
            if not SLUG.match(c["id"]):
                err(f"{w}: id must be a lowercase slug")
        if c.get("status") not in STATUSES:
            err(f"{w}: status {c.get('status')!r} not one of {STATUSES}")
        if c.get("status") == "completed" and not (c.get("completed_date") or c.get("certificate_url")):
            err(f"{w}: marked completed with no completion date or certificate URL")
        if not c.get("specialization") and not any(
                d.cur_by_id.get(m["curriculum"], {}).get("layout") == "sequence"
                for m in c.get("curricula", [])):
            err(f"{w}: no specialization, and none of its curricula use the sequence layout")
        if c.get("specialization") and c["specialization"] not in spec_ids:
            err(f"{w}: specialization {c['specialization']!r} does not exist")
        if not c.get("curricula"):
            err(f"{w}: belongs to no curriculum")
        for m in c.get("curricula", []):
            if m.get("curriculum") not in cur_ids:
                err(f"{w}: curriculum {m.get('curriculum')!r} does not exist")
            if m.get("role") not in ("breadth", "elective"):
                err(f"{w}: role {m.get('role')!r} must be breadth or elective")
        for a in c.get("related_artifacts", []):
            if a not in art_ids:
                err(f"{w}: related_artifacts entry {a!r} does not exist")
        for k in c.get("competencies", []):
            if k not in comp_ids:
                err(f"{w}: competency {k!r} does not exist")
        sch = c.get("scheduled_start")
        if sch is not None:
            if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(sch)):
                err(f"{w}: scheduled_start {sch!r} must be YYYY-MM")
            if c.get("started_date") or c.get("status") != "planned":
                err(f"{w}: carries a schedule and also a start or non-planned status; "
                    f"a schedule is an intention, not progress")
        ins = c.get("instructors")
        if ins is not None and not isinstance(ins, list):
            err(f"{w}: instructors must be a list or null")
        sc = c.get("signal_component")
        if sc is not None and not isinstance(sc, str):
            err(f"{w}: signal_component must be a string or null")
        if c.get("official_url") and not str(c["official_url"]).startswith("https://"):
            err(f"{w}: official_url must be absolute https")

    # each CU curriculum must declare exactly two admission pathway specializations
    for cur in d.curricula:
        if cur.get("breadth_credits") is None:
            continue
        pw = {c["specialization"] for c in d.courses
              for m in c["curricula"]
              if m["curriculum"] == cur["id"] and m.get("pathway")}
        if len(pw) != 2:
            err(f"curricula.json[{cur['id']}]: {len(pw)} pathway specializations marked, expected 2")

    # credit arithmetic, straight from the records
    for cur in d.curricula:
        if cur.get("breadth_credits") is None:
            continue
        for role, want in (("breadth", cur.get("breadth_credits")), ("elective", cur.get("elective_credits"))):
            if want is None:
                continue
            got = len(d.courses_for(cur["id"], role))
            if got != want:
                err(f"curricula.json[{cur['id']}]: {role} has {got} one-credit courses, expected {want}")

    for m in d.modules:
        w = f"modules.json[{m.get('id')}]"
        for f in ("id", "number", "title", "status"):
            if not m.get(f):
                err(f"{w}: missing required field {f!r}")
        if m.get("status") not in STATUSES:
            err(f"{w}: status {m.get('status')!r} not one of {STATUSES}")
        sch = m.get("scheduled_start")
        if sch is not None:
            if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", str(sch)):
                err(f"{w}: scheduled_start {sch!r} must be YYYY-MM")
            if m.get("started_date") or m.get("status") != "planned":
                err(f"{w}: carries a schedule and also a start or non-planned status")
        if m.get("url") and not m.get("slug_verified"):
            err(f"{w}: has a url but slug_verified is false")
        if m.get("status") == "completed" and not m.get("repo_url"):
            warn(f"{w}: completed with no implementation repository")
        for c in m.get("competencies", []):
            if c not in comp_ids:
                err(f"{w}: competency {c!r} does not exist")

    for c in d.competencies:
        w = f"competencies.json[{c.get('id')}]"
        for f in ("id", "name", "summary"):
            if not c.get(f):
                err(f"{w}: missing required field {f!r}")
        for s in c.get("specializations", []):
            if s not in spec_ids:
                err(f"{w}: specialization {s!r} does not exist")
        for m in c.get("modules", []):
            if m not in mod_ids:
                err(f"{w}: module {m!r} does not exist")
        for a in c.get("artifacts", []):
            if a not in art_ids:
                err(f"{w}: artifact {a!r} does not exist")

    for a in d.artifacts:
        w = f"artifacts.json[{a.get('id')}]"
        for f in ("name", "kind", "problem", "architecture", "stack"):
            if not a.get(f):
                err(f"{w}: missing required field {f!r}")
        if a.get("kind") not in KINDS:
            err(f"{w}: kind {a.get('kind')!r} not one of {KINDS}")
        for c in a.get("competencies", []):
            if c not in comp_ids:
                err(f"{w}: competency {c!r} does not exist")
        for c in a.get("related_courses", []):
            if c not in course_ids:
                err(f"{w}: related_courses entry {c!r} does not exist")

    for st in d.roadmap.get("stages", []):
        w = f"roadmap.json[{st.get('id')}]"
        for s in st.get("specializations", []):
            if s not in spec_ids:
                err(f"{w}: specialization {s!r} does not exist")
        for m in st.get("modules", []):
            if m not in mod_ids:
                err(f"{w}: module {m!r} does not exist")
        for sk in st.get("skills", []):
            if sk.get("state") not in SKILL_STATES:
                err(f"{w}: skill state {sk.get('state')!r} not one of {SKILL_STATES}")
            ev = sk.get("evidence")
            if ev and ev not in art_ids:
                err(f"{w}: evidence {ev!r} does not exist")
            if sk.get("state") == "demonstrated" and not ev:
                err(f"{w}: skill {sk.get('name')!r} is demonstrated with no artifact")

    sig = d.signal
    if sig:
        for f in ("name", "summary", "positioning", "repo_url", "status_summary"):
            if not sig.get(f):
                err(f"signal.json: missing or empty {f!r}")
        if not sig.get("business", {}).get("disclaimer"):
            err("signal.json: business section must carry a disclaimer that revenue claims are hypotheses")
        for st in sig.get("roadmap", []):
            if st.get("status") not in STATUSES:
                err(f"signal.json roadmap[{st.get('id')}]: status {st.get('status')!r} not one of {STATUSES}")
        for t in sig.get("timeline", []):
            if t.get("status") not in STATUSES:
                err(f"signal.json timeline[{t.get('id')}]: status {t.get('status')!r} not one of {STATUSES}")
            if t.get("status") == "completed" and not t.get("evidence"):
                err(f"signal.json timeline[{t.get('id')}]: marked completed with no evidence")
        for post in sig.get("blogs", []):
            for f in ("id", "month", "title", "set_out", "built"):
                if not post.get(f):
                    err(f"signal.json blogs[{post.get('id')}]: missing {f!r}")
        for v in sig.get("videos", []):
            for f in ("id", "title", "youtube_id", "published"):
                if not v.get(f):
                    err(f"signal.json videos[{v.get('id')}]: missing {f!r}")

    ss = d.scenesearch
    if ss:
        for f in ("name", "subtitle", "short_description", "status", "build_window"):
            if not ss.get(f):
                err(f"scenesearch.json: missing {f!r}")
        if ss.get("status") not in STATUSES:
            err(f"scenesearch.json: status {ss.get('status')!r} not one of {STATUSES}")
        dm = ss.get("demo")
        if dm:
            for f in ("src", "alt", "caption"):
                if not dm.get(f):
                    err(f"scenesearch/signal demo: missing {f!r}")
        vc = ss.get("video_collection")
        if vc:
            for f in vc.get("films", []):
                if not f.get("source"):
                    err(f"scenesearch.json film {f.get('title')!r}: no source URL")
                if f.get("status") == "confirmed" and not f.get("quote"):
                    err(f"scenesearch.json film {f.get('title')!r}: marked confirmed without a "
                        f"quoted licence statement from its own page")
                if f.get("status") == "confirmed" and "Creative Commons" not in str(f.get("licence")):
                    err(f"scenesearch.json film {f.get('title')!r}: confirmed but no named licence")
        for m in ss.get("roadmap", []):
            if m.get("status") not in STATUSES:
                err(f"scenesearch.json roadmap[{m.get('month')}]: bad status")
            if m.get("status") == "completed":
                err(f"scenesearch.json roadmap[{m.get('month')}]: completed requires stored evidence; "
                    f"a passed date is not evidence")
        for r in ss.get("skill_audit", {}).get("rows", []):
            if r.get("verdict") not in ("covered", "partial", "gap", "unverified"):
                err(f"scenesearch.json skill_audit[{r.get('skill')}]: verdict "
                    f"{r.get('verdict')!r} must be covered, partial, gap or unverified")
        for m in ss.get("evaluation", {}).get("measures", []):
            v = str(m.get("value", ""))
            if v != "Not yet measured" and not ss.get("results_exist"):
                err(f"scenesearch.json: measure {m.get('name')!r} carries a value but no "
                    f"experiment data is recorded; set results_exist once it does")
        for row in ss.get("learning_plan", {}).get("rows", []):
            for f in ("month", "resource", "scope", "deliverable", "status"):
                if not row.get(f):
                    err(f"scenesearch.json learning_plan[{row.get('resource')}]: missing {f!r}")
            if row.get("status") not in ("Planned", "Not started", "In progress",
                                         "Candidate — syllabus verification needed"):
                err(f"scenesearch.json learning_plan[{row.get('resource')}]: unexpected status "
                    f"{row.get('status')!r}")

    for n in d.notes:
        w = f"notes.json[{n.get('id')}]"
        for f in ("title", "summary"):
            if not n.get(f):
                err(f"{w}: missing required field {f!r}")


# --------------------------------------------------------------------------
# shared rendering
# --------------------------------------------------------------------------

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def when(rec):
    """Render a scheduled month. A schedule is an intention, never progress."""
    v = rec.get("scheduled_start")
    if not v:
        return ""
    y, _, mth = str(v).partition("-")
    label = f"{MONTHS[int(mth) - 1]} {y}" if mth.isdigit() and 1 <= int(mth) <= 12 else str(v)
    note = f' &mdash; {e(rec["schedule_note"])}' if rec.get("schedule_note") else ""
    return f'<span class="ae-xl">Scheduled {e(label)}{note}</span>'


def status_pill(s):
    return (f'<span class="ae-pill ae-{e(s)}"><span class="ae-dot" aria-hidden="true"></span>'
            f'{e(STATUS_LABEL[s])}</span>')


DEPTH = {"d": 1}


def resolve(url):
    """Replace the {root} token with the right number of ../ for this page."""
    return str(url).replace("{root}", "../" * DEPTH["d"])


def ext(url, label, cls="mono lnk"):
    url = resolve(url)
    rel = ' target="_blank" rel="noopener"' if url.startswith("http") else ""
    arrow = " &#8599;" if url.startswith("http") else ""
    return f'<a class="{cls}" href="{e(url)}"{rel}>{e(label)}{arrow}</a>'


def facts(pairs):
    rows = "".join(f'<dt class="mono fl">{e(k)}</dt><dd>{v}</dd>' for k, v in pairs if v)
    return f'<dl class="facts ae-facts">{rows}</dl>' if rows else ""


def tags(values):
    if not values:
        return ""
    return '<ul class="tags ae-plain">' + "".join(f'<li class="tag">{e(v)}</li>' for v in values) + "</ul>"


EXTRA_CSS = """
/* --- AI Engineering hub ------------------------------------------------- */
.ae-main{padding-bottom:40px}
.ae-head{padding-top:140px}
.ae-head h1{font-size:clamp(32px,4.6vw,58px);line-height:1.05;max-width:15ch}
.ae-lede{margin:26px 0 0;max-width:700px;font-size:18px;line-height:1.6;color:var(--acc);text-wrap:pretty}
.ae-stand{margin:22px 0 0;max-width:700px;font-size:16px;line-height:1.65;color:var(--mid);text-wrap:pretty}
.ae-disclosure{margin:30px 0 0;max-width:720px;font-size:14px;line-height:1.6;color:var(--faint);border-left:2px solid var(--line2);padding-left:14px;text-wrap:pretty}
.ae-stats{margin-top:52px}
.ae-sec{padding-top:88px}
.ae-intro{margin:26px 0 0;max-width:740px;font-size:16px;line-height:1.65;color:var(--mid);text-wrap:pretty}
.ae-grid{margin-top:30px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}
.ae-grid.one{grid-template-columns:1fr}
.ae-grid > .card{background:var(--bg)}
.ae-h3{margin:10px 0 0;font-size:19px;letter-spacing:-0.015em;line-height:1.3;font-weight:500;color:var(--fg)}
.ae-crumb{margin:0 0 18px;font-size:12px;letter-spacing:0.08em;color:var(--faint)}
.ae-crumb a{color:var(--faint)}.ae-crumb a:hover{color:var(--acc)}
.ae-entry{display:block;background:var(--bg);padding:26px 24px;transition:background .2s}
.ae-entry:hover{background:var(--card-hover)}
.ae-entry .ae-h3{color:var(--fg)}
.ae-entry-d{margin:10px 0 0;font-size:14.5px;line-height:1.6;color:var(--mid)}
.ae-tally{margin:16px 0 0;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--faint)}
.ae-pill{display:inline-flex;align-items:center;gap:7px;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10.5px;letter-spacing:0.1em;text-transform:uppercase;color:var(--faint)}
.ae-dot{width:7px;height:7px;border-radius:50%;flex:none;border:1px solid var(--line3)}
.ae-completed .ae-dot{background:var(--acc);border-color:var(--acc)}
.ae-in-progress .ae-dot{background:var(--warm);border-color:var(--warm)}
.ae-completed{color:var(--fg2)}.ae-in-progress{color:var(--warm)}
.ae-ph-tag{font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:var(--faint2);border:1px dashed var(--line2);border-radius:4px;padding:3px 7px}
.ae-ph{opacity:0.72}
.ae-meta{margin:8px 0 0;font-size:12px;letter-spacing:0.06em;color:var(--faint)}
.ae-kind{font-size:10.5px;letter-spacing:0.14em;text-transform:uppercase;color:var(--acc)}
.ae-facts{margin-top:18px;font-size:14px}
.ae-facts dd{margin:0}
.ae-links{margin:18px 0 0;display:flex;flex-wrap:wrap;gap:16px}
.tags.ae-plain{list-style:none;padding:0}
.ae-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
/* specialization blocks */
.ae-spec{border:1px solid var(--line);margin-top:22px}
.ae-spec-h{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:18px 22px;border-bottom:1px solid var(--line)}
.ae-spec-n{font-size:17px;letter-spacing:-0.015em;color:var(--fg)}
.ae-spec-t{font-size:10.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--faint);white-space:nowrap}
.ae-spec-t.pathway{color:var(--acc)}
.ae-spec-t.dev{color:var(--warm)}
.ae-rows{display:flex;flex-direction:column}
.ae-row{display:grid;grid-template-columns:96px minmax(0,1fr) auto;gap:18px;align-items:baseline;padding:13px 22px;border-top:1px solid var(--line)}
.ae-row:first-child{border-top:0}
.ae-code{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;color:var(--faint)}
.ae-ct{font-size:14.5px;line-height:1.45;color:var(--fg2)}
.ae-xl{display:block;margin-top:3px;font-size:11.5px;color:var(--faint)}
.ae-note-inline{display:block;margin-top:5px;font-size:12px;line-height:1.5;color:var(--warm)}
/* competency + roadmap */
.ae-skills{margin:18px 0 0;padding:0;list-style:none}
.ae-skill{margin-top:14px;padding-left:12px;border-left:2px solid var(--line2)}
.ae-s-demonstrated{border-left-color:var(--acc)}
.ae-s-practicing{border-left-color:var(--warm)}
.ae-state{display:block;font-size:9.5px;letter-spacing:0.12em;text-transform:uppercase;color:var(--faint)}
.ae-skill-n{display:block;margin-top:4px;font-size:14px;line-height:1.5;color:var(--fg2)}
.ae-stage{padding:28px 0;border-bottom:1px solid var(--line)}
.ae-stage:last-child{border-bottom:0}
.ae-stage-h{font-size:19px;margin:0}
.ae-stage-s{margin:8px 0 0;font-size:14.5px;line-height:1.6;color:var(--mid);max-width:680px}
.ae-artifact{padding:34px 0;border-bottom:1px solid var(--line)}
.ae-artifact:last-child{border-bottom:0}
.ae-artifact-h{font-size:26px;margin-top:12px}
.ae-artifact .ae-facts{max-width:770px}
.sig-demo{margin:28px 0 0;padding:0;border:1px solid var(--line2);border-radius:8px;overflow:hidden;background:var(--panel)}
.sig-demo img{display:block;width:100%;height:auto}
.sig-demo figcaption{padding:12px 16px;border-top:1px solid var(--line);font-size:11px;letter-spacing:0.06em;color:var(--faint)}
.sig-steps{margin-top:24px;padding-left:20px;max-width:720px}
.sig-steps li{margin-top:8px}
.ae-note{margin:26px 0 0;max-width:740px;font-size:13.5px;line-height:1.6;color:var(--faint);border-left:2px solid var(--line2);padding-left:14px}
.ae-back{margin-top:70px;padding-top:24px;border-top:1px solid var(--line)}
@media (max-width:640px){
 .ae-head{padding-top:86px}
 .ae-sec{padding-top:66px}
 .ae-grid{grid-template-columns:1fr}
 .ae-row{grid-template-columns:1fr;gap:4px;padding:14px 18px}
 .ae-spec-h{padding:16px 18px}
 .ae-artifact-h{font-size:22px}
}
"""


def nav(depth, current):
    up = "../" * depth
    def mark(key):
        return ' aria-current="page"' if current == key else ""
    return f"""<header class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="{up}"><span class="brand-name">Joseph Morante</span><span class="mono brand-tag">Measurement &amp; AI</span></a>
    <nav class="nav-links" aria-label="Primary">
      <a href="{up}#work">Work</a>
      <a href="{up}#research">Research</a>
      <a class="nav-keep" href="{up}ai-engineering/"{mark('hub')}>AI Engineering</a>
      <a href="{up}#experience">Experience</a>
      <a href="{up}#about">About</a>
      <a class="nav-keep" href="{up}bookshelf/">Bookshelf</a>
      <a class="btn-outline-sm" href="{up}JosephMorante_Resume.pdf" target="_blank" rel="noopener">Resume</a>
    </nav>
  </div>
</header>"""


def extract_shared():
    src = (ROOT / "index.html").read_text(encoding="utf-8")
    style = re.search(r"<style>(.*?)</style>", src, re.S)
    if not style:
        err("index.html: could not find the <style> block to share")
        return "", "", ""
    script = re.search(r"<script>\s*\(function\(\)\{\s*var root=document\.documentElement.*?</script>",
                       src, re.S)
    if not script:
        err("index.html: could not find the theme script to share")
        return style.group(1), "", ""
    icon = re.search(r'<link rel="icon"[^>]*>', src)
    return style.group(1), script.group(0), (icon.group(0) if icon else "")


SHARED = {"css": "", "js": "", "icon": ""}


def page(path: Path, depth: int, title: str, description: str, canonical: str,
         body: str, current="hub"):
    up = "../" * depth
    css = SHARED["css"]
    css = re.sub(r'url\("fonts/', f'url("{up}fonts/', css)
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(canonical)}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://covers.openlibrary.org https://archive.org https://*.archive.org; font-src 'self'; frame-src https://www.youtube-nocookie.com; connect-src 'none'; form-action 'none'; base-uri 'none'">\n<meta name="referrer" content="strict-origin-when-cross-origin">\n<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#08080a">
{SHARED['icon'].replace('href="data:', 'href="data:')}
{SHARED['js']}
<style>{css}{EXTRA_CSS}</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{nav(depth, current)}
<main class="ae-main" id="main">
{body}
</main>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    return len(doc)


def crumb(depth, extra=None):
    up = "../" * depth
    bits = [f'<a href="{up}">Portfolio</a>', f'<a href="{up}ai-engineering/">AI Engineering</a>']
    if extra:
        bits.append(e(extra))
    return f'<p class="mono ae-crumb">{" / ".join(bits)}</p>'


def back(depth):
    up = "../" * depth
    return (f'<section class="wrap ae-back"><p class="mono">'
            f'<a href="{up}ai-engineering/">&#8592; Back to AI Engineering</a></p></section>')


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------

def render_curriculum(d: Data, cur, depth):
    """Specialization blocks for one CU Boulder curriculum."""
    out = []
    for role, heading in (("breadth", "Breadth requirement"), ("elective", "Electives")):
        specs = d.specs_for(cur["id"], role)
        credits = len(d.courses_for(cur["id"], role))
        out.append(f'<div class="sec-head" style="margin-top:56px"><h2 class="h2-sm">{e(heading)}</h2>'
                   f'<div class="mono kicker">{credits} one-credit courses</div></div>')
        for sp in specs:
            courses = [c for c in d.courses_for(cur["id"], role) if c["specialization"] == sp["id"]]
            courses.sort(key=lambda c: c["sequence"])
            labels = []
            if any(m.get("pathway") for c in courses for m in c["curricula"]
                   if m["curriculum"] == cur["id"]):
                labels.append('<span class="mono ae-spec-t pathway">Pathway</span>')
            if sp.get("status") == "in-development":
                labels.append('<span class="mono ae-spec-t dev">In development</span>')
            rows = []
            for c in courses:
                xl = f'<span class="ae-xl">Cross-listed as {e(c["cross_listed_as"])}</span>' if c.get("cross_listed_as") else ""
                note = f'<span class="ae-note-inline">{e(c["availability_note"])}</span>' if c.get("availability_note") else ""
                sk = [d.comp_by_id[k]["name"] for k in c.get("competencies", []) if k in d.comp_by_id]
                skills = f'<span class="ae-xl">Skills: {", ".join(e(x) for x in sk)}</span>' if sk else ""
                fc = f'<span class="ae-xl">SIGNAL: {e(c["signal_component"])}</span>' if c.get("signal_component") else ""
                arts = [d.art_by_id[x] for x in c.get("related_artifacts", []) if x in d.art_by_id]
                extra = ""
                if arts:
                    up = "../" * DEPTH["d"]
                    links = " ".join(
                        f'<a class="ul" href="{up}ai-engineering/engineering-evidence/'
                        f'#artifact-{e(x["id"])}">{e(x["name"])}</a>' for x in arts)
                    extra = f'<span class="ae-xl">Connects to: {links}</span>'
                label = e(c["code"]) if c.get("code") else e(c.get("institution", ""))
                title = (ext(c["official_url"], c["title"], "ul") if c.get("official_url")
                         else e(c["title"]) + '<span class="ae-xl">No syllabus page published</span>')
                rows.append(
                    f'<div class="ae-row"><span class="ae-code">{label}</span>'
                    f'<span class="ae-ct">{title}{xl}{when(c)}{skills}{fc}{extra}{note}</span>'
                    f'<span>{status_pill(c["status"])}</span></div>'
                )
            note = f'<p class="ae-intro" style="margin:0 22px 18px">{e(sp["note"])}</p>' if sp.get("note") else ""
            out.append(f"""<section class="ae-spec">
  <div class="ae-spec-h"><span class="ae-spec-n">{e(sp['name'])}</span><span class="ae-top">{''.join(labels)}</span></div>
  {note}
  <div class="ae-rows">{''.join(rows)}</div>
</section>""")
    return "\n".join(out)


def build_curriculum_page(d: Data, cur):
    depth = 3
    DEPTH["d"] = depth
    base = d.page["canonical"]
    slug = {"ms-cs": "computer-science", "ms-ai": "artificial-intelligence"}[cur["id"]]
    body = f"""<header class="wrap ae-head">
  {crumb(depth, cur['name'])}
  <h1>{e(cur['long_name'])}</h1>
  <p class="ae-lede">{e(cur['structure'])}</p>
  <p class="ae-disclosure">{e(d.page['disclosure'])}</p>
  <p class="ae-top" style="margin-top:20px">{status_pill(cur['status'])}</p>
  {facts([("Progress", e(cur.get('status_note'))),
          ("Elective rule", e(cur.get('elective_rule'))),
          ("Source", ext(cur['source_url'], 'Official curriculum page')),
          ("Verified", e(cur.get('verified_on')))])}
  <p class="ae-note">{e(d.source_note)}</p>
</header>
<section class="wrap ae-sec">
{render_curriculum(d, cur, depth)}
</section>
{back(depth)}"""
    n = len(d.courses_for(cur["id"]))
    return page(HERE / "curriculum" / slug / "index.html", depth,
                f"{cur['name']} curriculum - AI Engineering - Joseph Morante",
                f"The CU Boulder {cur['name']} curriculum ({n} one-credit courses), studied independently through Coursera's open non-credit versions.",
                f"{base}curriculum/{slug}/", body)


def build_sequence_page(d: Data, cur):
    depth = 3
    DEPTH["d"] = depth
    base = d.page["canonical"]
    courses = d.courses_for(cur["id"])

    def seq(c):
        for m in c["curricula"]:
            if m["curriculum"] == cur["id"]:
                return m.get("sequence", c.get("sequence") or 99)
        return 99
    courses.sort(key=seq)

    rows = []
    for c in courses:
        who = ", ".join(c.get("instructors") or [])
        extra = ""
        if c.get("relevance"):
            extra += f'<span class="ae-xl">Relevance: {e(c["relevance"])}</span>'
        if c.get("suggested_evidence"):
            extra += f'<span class="ae-xl">Evidence to produce: {e(c["suggested_evidence"])}</span>'
        if who:
            extra += f'<span class="ae-xl">{e(who)}</span>'
        if len(c["curricula"]) > 1:
            others = [d.cur_by_id[m["curriculum"]]["name"] for m in c["curricula"]
                      if m["curriculum"] != cur["id"] and m["curriculum"] in d.cur_by_id]
            if others:
                extra += (f'<span class="ae-xl">Shared with {", ".join(e(o) for o in others)}'
                          f' &mdash; one record, counted once</span>')
        arts = [d.art_by_id[x] for x in c.get("related_artifacts", []) if x in d.art_by_id]
        if arts:
            up = "../" * depth
            links = " ".join(f'<a class="ul" href="{up}ai-engineering/engineering-evidence/'
                             f'#artifact-{e(x["id"])}">{e(x["name"])}</a>' for x in arts)
            extra += f'<span class="ae-xl">Connects to: {links}</span>'
        note = (f'<span class="ae-note-inline">{e(c["availability_note"])}</span>'
                if c.get("availability_note") else "")
        rows.append(f'<div class="ae-row"><span class="ae-code">{seq(c)}. {e(c["institution"])}</span>'
                    f'<span class="ae-ct">{ext(c["coursera_url"] or c["official_url"], c["title"], "ul")}'
                    f'{extra}{note}</span><span>{status_pill(c["status"])}</span></div>')

    done = len([c for c in courses if c["status"] == "completed"])
    prog = len([c for c in courses if c["status"] == "in-progress"])
    plan = len([c for c in courses if c["status"] == "planned"])
    dot = "\u00b7"
    progress = (f"{len(courses)} selected {dot} {done} completed {dot} "
                f"{prog} in progress {dot} {plan} planned")
    reused = len([c for c in courses if len(c["curricula"]) > 1])
    reuse_line = (f"{reused} of these records also sit in another pathway. "
                  f"A shared course is one record, so it is never counted twice."
                  if reused else "")
    body = f"""<header class="wrap ae-head">
  {crumb(depth, cur['name'])}
  <h1>{e(cur['name'])}</h1>
  <p class="ae-lede">{e(cur['short_subtitle'])}</p>
  <p class="ae-stand">{e(cur['description'])}</p>
  <p class="ae-top" style="margin-top:20px">{status_pill(cur['status'])}</p>
  {facts([("Progress", e(progress)), ("Verified", e(cur.get('verified_on')))])}
  <p class="ae-note">Every course page was fetched and confirmed live on {e(cur.get('verified_on'))}. {e(reuse_line)}</p>
</header>
<section class="wrap ae-sec">
  <div class="sec-head"><h2>Courses</h2><div class="mono kicker">In recommended order</div></div>
  <section class="ae-spec" style="margin-top:26px"><div class="ae-rows">{''.join(rows)}</div></section>
</section>
{back(depth)}"""
    return page(HERE / "curriculum" / cur["id"] / "index.html", depth,
                f"{cur['name']} - Joseph Morante",
                e(cur["description"])[:180],
                f"{base}curriculum/{cur['id']}/", body)


def build_adtech_page(d: Data):
    depth = 3
    DEPTH["d"] = depth
    base = d.page["canonical"]
    cur = d.cur_by_id["adtech"]
    courses = d.courses_for("adtech")
    blocks = []
    for sp in d.specs_for("adtech", "elective"):
        rows = [c for c in courses if c["specialization"] == sp["id"]]
        rows.sort(key=lambda c: c["sequence"])
        blocks.append((sp, rows))
    out = []
    for sp, rows in blocks:
        body_rows = []
        for c in rows:
            who = ", ".join(c.get("instructors") or [])
            extra = f'<span class="ae-xl">Relevance: {e(c["relevance"])}</span>'
            extra += f'<span class="ae-xl">Evidence to produce: {e(c["suggested_evidence"])}</span>'
            if who:
                extra += f'<span class="ae-xl">{e(who)}</span>'
            arts = [d.art_by_id[x] for x in c.get("related_artifacts", []) if x in d.art_by_id]
            if arts:
                links = " ".join(f'<a class="ul" href="{"../" * depth}ai-engineering/engineering-evidence/#artifact-{e(x["id"])}">{e(x["name"])}</a>' for x in arts)
                extra += f'<span class="ae-xl">Connects to: {links}</span>'
            note = f'<span class="ae-note-inline">{e(c["availability_note"])}</span>' if c.get("availability_note") else ""
            body_rows.append(
                f'<div class="ae-row"><span class="ae-code">{e(c["institution"])}</span>'
                f'<span class="ae-ct">{ext(c["official_url"], c["title"], "ul")}{extra}{note}</span>'
                f'<span>{status_pill(c["status"])}</span></div>')
        note = f'<p class="ae-intro" style="margin:0 22px 18px">{e(sp["note"])}</p>' if sp.get("note") else ""
        out.append(f"""<section class="ae-spec">
  <div class="ae-spec-h"><span class="ae-spec-n">{e(sp['name'])}</span>
    <span class="mono ae-spec-t">{len(rows)} course{'s' if len(rows) != 1 else ''}</span></div>
  {note}
  <div class="ae-rows">{''.join(body_rows)}</div>
</section>""")
    done = len([c for c in courses if c["status"] == "completed"])
    prog = len([c for c in courses if c["status"] == "in-progress"])
    plan = len([c for c in courses if c["status"] == "planned"])
    dot = "\u00b7"
    progress = (f"{len(courses)} selected {dot} {done} completed {dot} "
                f"{prog} in progress {dot} {plan} planned")
    body = f"""<header class="wrap ae-head">
  {crumb(depth, cur['name'])}
  <h1>{e(cur['name'])}</h1>
  <p class="ae-lede">{e(cur['short_subtitle'])}</p>
  <p class="ae-stand">{e(cur['description'])}</p>
  <p class="ae-top" style="margin-top:20px">{status_pill(cur['status'])}</p>
  {facts([("Progress", e(progress)),
          ("Verified", e(cur.get('verified_on')))])}
  <p class="ae-note">All six course pages were fetched and confirmed live on 2026-10-23. Where a page's enrolment terms or provenance differ from the rest, the course carries a note saying so.</p>
</header>
<section class="wrap ae-sec">
{chr(10).join(out)}
</section>
{back(depth)}"""
    return page(HERE / "curriculum" / "adtech" / "index.html", depth,
                "AdTech Measurement Science & AI Engineering - Joseph Morante",
                "An independent pathway in causal inference, optimization and production machine learning, applied to advertising measurement.",
                f"{base}curriculum/adtech/", body)


def build_from_scratch_page(d: Data):
    depth = 3
    DEPTH["d"] = depth
    base = d.page["canonical"]
    rows = []
    for m in d.modules:
        title = e(m["title"])
        link = ext(m["url"], "Open phase") if m.get("url") else '<span class="mono ae-code">slug not published</span>'
        lessons = f'<span class="ae-xl">{m["lesson_count"]} lessons</span>' if m.get("lesson_count") else ""
        rows.append(f'<div class="ae-row"><span class="ae-code">{e(m["number"])}</span>'
                    f'<span class="ae-ct">{title}{lessons}{when(m)}<span class="ae-xl">{link}</span></span>'
                    f'<span>{status_pill(m["status"])}</span></div>')
    meta = d.modmeta
    fs = d.cur_by_id["from-scratch"]
    body = f"""<header class="wrap ae-head">
  {crumb(depth, 'AI Engineering from Scratch')}
  <h1>AI Engineering from Scratch</h1>
  <p class="ae-lede">{e(meta.get('access'))}</p>
  <p class="ae-stand">An implementation-first curriculum: the point is building the mechanism rather than watching someone build it. Each phase is tracked here with its implementation, what the tests assert, what was measured, and what it does not handle. No lesson content is reproduced.</p>
  <p class="ae-top" style="margin-top:20px">{status_pill(fs['status'])}</p>
  {facts([("Progress", e(fs.get('status_note'))),
          ("Source", ext(meta.get('source_url'), 'aiengineeringfromscratch.com')),
          ("Verified", e(meta.get('verified_on')))])}
  <p class="ae-note">{e(meta.get('note'))}</p>
</header>
<section class="wrap ae-sec">
  <div class="sec-head"><h2>Phases</h2><div class="mono kicker">{len(d.modules)} phases</div></div>
  <section class="ae-spec" style="margin-top:28px"><div class="ae-rows">{''.join(rows)}</div></section>
</section>
{back(depth)}"""
    return page(HERE / "curriculum" / "from-scratch" / "index.html", depth,
                "AI Engineering from Scratch - Joseph Morante",
                "Progress through the AI Engineering from Scratch curriculum: 20 phases tracked with implementations, tests and limitations.",
                f"{base}curriculum/from-scratch/", body)


def build_competencies_page(d: Data):
    depth = 2
    DEPTH["d"] = depth
    base = d.page["canonical"]
    cards = []
    for c in d.competencies:
        specs = [d.spec_by_id[s]["name"] for s in c.get("specializations", []) if s in d.spec_by_id]
        mods = [d.mod_by_id[m]["title"] for m in c.get("modules", []) if m in d.mod_by_id]
        arts = c.get("artifacts", [])
        art_links = " ".join(f'<a class="ul" href="../engineering-evidence/#artifact-{e(a)}">{e(d.art_by_id[a]["name"])}</a>'
                             for a in arts if a in d.art_by_id)
        demonstrated = ('<span class="mono ae-spec-t pathway">Evidence on file</span>' if arts
                        else '<span class="mono ae-spec-t">Studied, not yet demonstrated</span>')
        cards.append(f"""      <article class="card">
        <div class="ae-top">{demonstrated}</div>
        <h3 class="card-t ae-h3">{e(c['name'])}</h3>
        <p class="card-d">{e(c['summary'])}</p>
        {facts([("Evidence", art_links),
                ("Coursework", ", ".join(e(s) for s in specs)),
                ("Modules", ", ".join(e(m) for m in mods))])}
      </article>""")
    body = f"""<header class="wrap ae-head">
  {crumb(depth, 'Competencies')}
  <h1>Skills &amp; competencies</h1>
  <p class="ae-lede">The same work, organised by capability rather than by course catalogue.</p>
  <p class="ae-stand">Each area separates what I have studied from what I can point at. An area counts as demonstrated only when an artifact on this site backs it, which is why several show coursework and no evidence yet.</p>
</header>
<section class="wrap ae-sec">
  <div class="ae-grid">
{chr(10).join(cards)}
  </div>
</section>
{back(depth)}"""
    return page(HERE / "competencies" / "index.html", depth,
                "Skills & competencies - AI Engineering - Joseph Morante",
                "AI engineering competencies, each separating studied material from capability backed by a working artifact.",
                f"{base}competencies/", body)


def build_evidence_page(d: Data):
    depth = 2
    DEPTH["d"] = depth
    base = d.page["canonical"]
    blocks = []
    for a in d.artifacts:
        ph = a.get("placeholder")
        comps = [d.comp_by_id[c]["name"] for c in a.get("competencies", []) if c in d.comp_by_id]
        bits = [("Problem", e(a.get("problem"))),
                ("Architecture", e(a.get("architecture"))),
                ("Decisions", "<br>".join(e(x) for x in a.get("decisions", []))),
                ("Testing", e(a.get("testing"))),
                ("Results", e(a.get("evaluation"))),
                ("Deployment", e(a.get("deployment"))),
                ("Limitations", e(a.get("limitations"))),
                ("Competencies", ", ".join(e(c) for c in comps))]
        links = []
        if a.get("repo_url"):
            links.append(ext(a["repo_url"], "Repository"))
        for l in a.get("extra_links", []):
            u = str(l.get("url", ""))
            if not (u.startswith(("http://", "https://", "{root}", "#"))):
                err(f"{w}: extra link url {u!r} must be absolute, an anchor, or use the {{root}} token")
            links.append(ext(l["url"], l["label"]))
        lh = f'<p class="ae-links">{" ".join(links)}</p>' if links else ""
        track = f'<span class="mono ae-spec-t">{e(a["track"])}</span>' if a.get("track") else ""
        blocks.append(f"""      <article class="ae-artifact{' ae-ph' if ph else ''}" id="artifact-{e(a['id'])}">
        <div class="ae-top"><span class="mono ae-kind">{e(KIND_LABEL[a['kind']])}</span>{track}</div>
        <h3 class="ae-h3 ae-artifact-h">{e(a['name'])}</h3>
        {tags(a.get('stack'))}
        {facts(bits)}
        {lh}
      </article>""")
    body = f"""<header class="wrap ae-head">
  {crumb(depth, 'Engineering evidence')}
  <h1>Built, tested &amp; deployed</h1>
  <p class="ae-lede">Artifacts, each labelled by what it actually is.</p>
  <p class="ae-stand">Independent engineering, tutorial exercise, research prototype, or production system. Employer work appears without code or data. Where there are no measured results yet, the entry says so rather than implying any.</p>
</header>
<section class="wrap ae-sec">
{chr(10).join(blocks)}
</section>
{back(depth)}"""
    return page(HERE / "engineering-evidence" / "index.html", depth,
                "Engineering evidence - AI Engineering - Joseph Morante",
                "Engineering artifacts with architecture, testing methodology, measured results and stated limitations.",
                f"{base}engineering-evidence/", body)


def build_notes_page(d: Data):
    depth = 2
    DEPTH["d"] = depth
    base = d.page["canonical"]
    if not d.notes:
        cards = '<p class="ae-intro">No write-ups published yet.</p>'
    else:
        out = []
        for n in d.notes:
            ph = n.get("placeholder")
            bits = [("Learned", e(n.get("learned"))), ("Mechanism", e(n.get("mechanism"))),
                    ("Implemented", e(n.get("implemented"))), ("What failed", e(n.get("failed"))),
                    ("Tradeoffs", e(n.get("tradeoffs"))), ("In production", e(n.get("production")))]
            link = f'<p class="ae-links">{ext(n["url"], "Read the note")}</p>' if n.get("url") else ""
            tag = '<span class="ae-ph-tag mono">Example entry</span>' if ph else ""
            out.append(f"""      <article class="card{' ae-ph' if ph else ''}">
        <div class="ae-top"><span class="mono ae-meta">{e(n.get('date') or '')}</span>{tag}</div>
        <h3 class="card-t ae-h3">{e(n['title'])}</h3>
        <p class="card-d">{e(n['summary'])}</p>
        {facts(bits)}
        {link}
      </article>""")
        cards = '<div class="ae-grid">' + "\n".join(out) + "</div>"
    body = f"""<header class="wrap ae-head">
  {crumb(depth, 'Technical notes')}
  <h1>Technical notes</h1>
  <p class="ae-lede">Short pieces on a mechanism I had to understand properly.</p>
  <p class="ae-stand">How it works, what I implemented, what broke, and what it would mean in production. Written only where I actually did the work.</p>
</header>
<section class="wrap ae-sec">
{cards}
</section>
{back(depth)}"""
    return page(HERE / "technical-notes" / "index.html", depth,
                "Technical notes - AI Engineering - Joseph Morante",
                "Short engineering write-ups: the mechanism, the implementation, the failures and the tradeoffs.",
                f"{base}technical-notes/", body)


def build_signal_page(d: Data):
    depth = 2
    DEPTH["d"] = depth
    base = d.page["canonical"]
    sig = d.signal
    biz = sig.get("business", {})

    dm = sig.get("demo")
    if dm:
        up = "../" * depth
        steps = "".join(f"<li>{e(x)}</li>" for x in dm.get("steps", []))
        demo_html = f"""<section class="wrap ae-sec">
  <div class="sec-head"><h2>See it work</h2><div class="mono kicker">Live app</div></div>
  <p class="ae-intro">{e(dm['caption'])}</p>
  <figure class="sig-demo">
    <img src="{up}ai-engineering/{e(dm['src'])}" alt="{e(dm['alt'])}" loading="lazy" decoding="async">
    <figcaption class="mono">{e(dm.get('caveat') or '')}</figcaption>
  </figure>
  <ol class="ae-comps sig-steps">{steps}</ol>
</section>"""
    else:
        demo_html = ""

    stages = []
    for st in sig.get("roadmap", []):
        nxt = f'<p class="ae-stage-s"><strong style="font-weight:500">Next:</strong> {e(st["next"])}</p>' if st.get("next") else ""
        stages.append(f"""      <section class="ae-stage">
        <div class="ae-top">{status_pill(st['status'])}</div>
        <h3 class="ae-h3 ae-stage-h">{e(st['name'])}</h3>
        <p class="ae-stage-s">{e(st['goal'])}</p>
        <p class="ae-stage-s">{e(st['detail'])}</p>
        {nxt}
      </section>""")

    tl = []
    for t in sig.get("timeline", []):
        ev = e(t["evidence"]) if t.get("evidence") else '<span style="color:var(--faint)">Not started</span>'
        if t.get("evidence_url"):
            ev += " " + ext(t["evidence_url"], "Evidence")
        tl.append(f'<div class="ae-row"><span>{status_pill(t["status"])}</span>'
                  f'<span class="ae-ct">{e(t["name"])}<span class="ae-xl">{ev}</span></span><span></span></div>')

    posts = sig.get("blogs", [])
    if posts:
        out = []
        for p in posts:
            bits = [("Set out to", e(p.get("set_out"))), ("Built", e(p.get("built"))),
                    ("Learned", e(p.get("learned"))), ("Decisions", e(p.get("decisions"))),
                    ("Difficulties", e(p.get("difficulties"))), ("Testing", e(p.get("testing"))),
                    ("Feedback", e(p.get("feedback"))), ("Metrics", e(p.get("metrics"))),
                    ("Next", e(p.get("next")))]
            link = f'<p class="ae-links">{ext(p["url"], "Read in full")}</p>' if p.get("url") else ""
            out.append(f'<article class="card"><div class="ae-top"><span class="mono ae-meta">{e(p["month"])}</span></div>'
                       f'<h3 class="card-t ae-h3">{e(p["title"])}</h3>{facts(bits)}{link}</article>')
        blog_html = '<div class="ae-grid one">' + "".join(out) + "</div>"
    else:
        blog_html = ('<p class="ae-intro">No monthly entries published yet. The first one covers the month '
                     'the prediction log gets resolved against real outcomes.</p>')

    vids = sig.get("videos", [])
    if vids:
        out = []
        for v in vids:
            out.append(f"""<article class="card">
        <div class="ae-top"><span class="mono ae-meta">{e(v['published'])}</span></div>
        <h3 class="card-t ae-h3">{e(v['title'])}</h3>
        <p class="card-d">{e(v.get('description'))}</p>
        <div style="margin-top:16px;position:relative;padding-bottom:56.25%;height:0;overflow:hidden">
          <iframe style="position:absolute;top:0;left:0;width:100%;height:100%;border:0"
            src="https://www.youtube-nocookie.com/embed/{e(v['youtube_id'])}"
            title="{e(v['title'])}" loading="lazy"
            allow="accelerometer; clipboard-write; encrypted-media; picture-in-picture"
            allowfullscreen></iframe>
        </div>
      </article>""")
        video_html = '<div class="ae-grid one">' + "".join(out) + "</div>"
    else:
        video_html = '<p class="ae-intro">No video updates published yet.</p>'

    body = f"""<header class="wrap ae-head">
  {crumb(depth, 'Building SIGNAL')}
  <h1>Building SIGNAL</h1>
  <p class="ae-lede">{e(sig['tagline'])}</p>
  <p class="ae-stand">{e(sig['summary'])}</p>
  <p class="ae-stand">{e(sig['positioning'])}</p>
  <p class="ae-links">{ext(sig['live_url'], 'Live app')} {ext(sig['repo_url'], 'Repository')}
    {ext('{root}ai-engineering/engineering-evidence/#artifact-signal', 'Engineering detail')}</p>
  <p class="ae-disclosure">{e(sig['status_summary'])}</p>
</header>

{demo_html}

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Roadmap</h2><div class="mono kicker">Ship &#8594; Improve</div></div>
  <p class="ae-intro">Four stages, no dates. A stage advances on evidence, not on a calendar.</p>
{chr(10).join(stages)}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Development timeline</h2><div class="mono kicker">Evidence required</div></div>
  <p class="ae-intro">A milestone is marked complete only when something in the repository or the live app backs it.</p>
  <section class="ae-spec" style="margin-top:26px"><div class="ae-rows">{''.join(tl)}</div></section>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Monthly engineering blog</h2><div class="mono kicker">{len(posts)} published</div></div>
  {blog_html}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Video updates</h2><div class="mono kicker">{len(vids)} published</div></div>
  {video_html}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Product and business</h2><div class="mono kicker">Hypotheses</div></div>
  <p class="ae-intro">Written down so they can be tested and so I can be held to them.</p>
  {facts([("Target customer", e(biz.get('target_customer'))),
          ("Problem", e(biz.get('problem'))),
          ("Core value", e(biz.get('value'))),
          ("Competing products", e(biz.get('competitors'))),
          ("Monetization options", "<br>".join(e(x) for x in biz.get('monetization_hypotheses', []))),
          ("Operating costs", e(biz.get('operating_costs'))),
          ("Smallest useful version", e(biz.get('smallest_useful_mvp'))),
          ("First users", e(biz.get('acquisition_idea')))])}
  <p class="ae-note">{e(biz.get('disclaimer'))}</p>
</section>
{back(depth)}"""
    return page(HERE / "building-signal" / "index.html", depth,
                "Building SIGNAL - Joseph Morante",
                "Build-in-public log for SIGNAL: roadmap, evidence-backed milestones, monthly engineering notes and the business hypotheses behind it.",
                f"{base}building-signal/", body)


VERDICT = {"covered": ("Covered", "pathway"), "partial": ("Partially covered", "dev"),
           "gap": ("Gap", "dev"), "unverified": ("Unverified", "")}


def build_scenesearch_page(d: Data):
    depth = 2
    DEPTH["d"] = depth
    base = d.page["canonical"]
    p = d.scenesearch

    ov = p["overview"]
    rq = p["research_question"]
    arch = p["architecture"]

    vc = p["video_collection"]
    film_rows = []
    for f in vc["films"]:
        ok = f["status"] == "confirmed"
        cls = "pathway" if ok else "dev"
        quote = f'<span class="ae-xl">&ldquo;{e(f["quote"])}&rdquo;</span>' if f.get("quote") else ""
        note = "" if ok else f'<span class="ae-note-inline">{e(f["status"])}</span>'
        film_rows.append(
            f'<div class="ae-row"><span class="ae-code">{e(f["project"])}</span>'
            f'<span class="ae-ct">{ext(f["source"], f["title"], "ul")}'
            f'<span class="ae-xl">{e(f["licence"])}</span>{quote}{note}</span>'
            f'<span class="mono ae-spec-t {cls}">{"Confirmed" if ok else "Check first"}</span></div>')
    films = "".join(film_rows)

    flow = []
    for i, st in enumerate(arch["stages"]):
        flow.append(f'<div class="layer"><div class="mono pl">Stage {i + 1}</div>'
                    f'<div class="layer-t">{e(st["name"])}</div>'
                    f'<div class="row-d">{e(st["detail"])}</div></div>')
        if i < len(arch["stages"]) - 1:
            flow.append('<div class="mono arrow">&#8595;</div>')
    cross = "".join(f'<div class="layer accent"><div class="mono pl">Cross-cutting</div>'
                    f'<div class="layer-t">{e(c["name"])}</div>'
                    f'<div class="row-d">{e(c["detail"])}</div></div>'
                    for c in arch["cross_cutting"])

    bl = "".join(f'<div class="ae-row"><span class="ae-code">{b["id"]}</span>'
                 f'<span class="ae-ct">{e(b["name"])}<span class="ae-xl">{e(b["note"])}</span></span>'
                 f'<span></span></div>' for b in p["baselines"])

    meas = "".join(f'<div class="row"><div><div class="row-t">{e(m["name"])}</div></div>'
                   f'<div class="mono row-v">{e(m["value"])}</div></div>'
                   for m in p["evaluation"]["measures"])

    months = []
    for m in p["roadmap"]:
        learn = ("".join(f"<li>{e(x)}</li>" for x in m["learning"]))
        build = ("".join(f"<li>{e(x)}</li>" for x in m["build"]))
        learn_block = (f'<div><p class="mono pl">Learning</p><ul class="ae-comps">{learn}</ul></div>'
                       if learn else "")
        months.append(f"""      <section class="ae-stage">
        <div class="ae-top">{status_pill(m['status'])}<span class="mono ae-spec-t">{e(m['month'])}</span></div>
        <h3 class="ae-h3 ae-stage-h">{e(m['theme'])}</h3>
        <div class="split2" style="margin-top:16px">
          {learn_block}
          <div><p class="mono pl">Build</p><ul class="ae-comps">{build}</ul></div>
        </div>
        <p class="ae-stage-s"><span class="mono pl">Exit</span> {e(m['exit'])}</p>
      </section>""")

    audit = []
    for r in p["skill_audit"]["rows"]:
        label, cls = VERDICT[r["verdict"]]
        ex = "".join(f"<li>{e(x)}</li>" for x in r["existing"])
        audit.append(f"""      <article class="card">
        <div class="ae-top"><span class="mono ae-spec-t {cls}">{e(label)}</span></div>
        <h3 class="card-t ae-h3">{e(r['skill'])}</h3>
        <p class="mono pl" style="margin-top:14px">Already in the plan</p>
        <ul class="ae-comps">{ex}</ul>
        <p class="card-d">{e(r['reasoning'])}</p>
      </article>""")

    props = []
    for it in p["proposed_changes"]["items"]:
        bits = [("Gap", e(it.get("gap"))), ("Milestone", e(it.get("milestone"))),
                ("The case for", e(it.get("case"))), ("The case against", e(it.get("against"))),
                ("Recommendation", e(it.get("recommendation")))]
        props.append(f"""      <article class="ae-artifact">
        <div class="ae-top"><span class="mono ae-kind">{e(it['kind'])}</span></div>
        <h3 class="ae-h3" style="font-size:20px">{e(it['title'])}</h3>
        {facts(bits)}
      </article>""")

    rows = p["learning_plan"]["rows"]
    if rows:
        parts = []
        for r in rows:
            name = ext(r["url"], r["resource"], "ul") if r.get("url") else e(r["resource"])
            caveat = (f'<span class="ae-note-inline">{e(r["caveat"])}</span>'
                      if r.get("caveat") else "")
            parts.append(
                '<div class="ae-row" style="grid-template-columns:120px minmax(0,1fr) auto">'
                f'<span class="ae-code">{e(r["month"])}</span>'
                f'<span class="ae-ct">{name}'
                f'<span class="ae-xl">Study scope: {e(r["scope"])}</span>'
                f'<span class="ae-xl">Project deliverable: {e(r["deliverable"])}</span>'
                f'{caveat}</span>'
                f'<span class="mono ae-spec-t">{e(r["status"])}</span></div>')
        lp = ('<section class="ae-spec" style="margin-top:26px">'
              f'<div class="ae-rows">{"".join(parts)}</div></section>')
    else:
        lp = ('<p class="ae-intro">No resources scheduled yet. Candidates are under the proposals '
              'above and move here only once you approve them.</p>')

    lists = lambda key: "".join(f"<li>{e(x)}</li>" for x in p[key])
    body = f"""<header class="wrap ae-head">
  {crumb(depth, p['name'])}
  <div class="ae-top">{status_pill(p['status'])}<span class="mono ae-spec-t">{e(p['build_window'])}</span></div>
  <h1>{e(p['name'])}</h1>
  <p class="ae-lede">{e(p['subtitle'])}</p>
  <p class="ae-stand">{e(p['short_description'])}</p>
  <p class="ae-disclosure">{e(ov['status_note'])} {e(p['links_note'])}</p>
  <p class="ae-links"><span class="mono ae-spec-t">Repository coming soon</span>
    <span class="mono ae-spec-t">Demo planned</span></p>
</header>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Overview</h2><div class="mono kicker">Problem and scope</div></div>
  {facts([("The problem", e(ov['problem'])), ("The approach", e(ov['solution'])),
          ("Initial scope", e(ov['scope'])),
          ("Example queries", "<br>".join(e(q) for q in p["example_queries"]))])}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>The video collection</h2><div class="mono kicker">Licence first</div></div>
  <p class="ae-intro">{e(vc['why'])}</p>
  <section class="ae-spec" style="margin-top:26px">
    <div class="ae-spec-h"><span class="ae-spec-n">{e(vc['name'])}</span>
      <span class="mono ae-spec-t">Checked {e(vc['verified_on'])}</span></div>
    <div class="ae-rows">{films}</div>
  </section>
  <ul class="ae-comps" style="margin-top:22px">{"".join(f"<li>{e(x)}</li>" for x in vc["caveats"])}</ul>
  <p class="ae-note">{e(vc['recording'])}</p>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Research question</h2><div class="mono kicker">Open, not answered</div></div>
  <p class="ae-lede" style="margin-top:24px">{e(rq['question'])}</p>
  <div class="split2" style="margin-top:28px">
    <div><p class="mono pl">To investigate</p><ul class="ae-comps">{"".join(f"<li>{e(x)}</li>" for x in rq["to_investigate"])}</ul></div>
    <div><p class="mono pl">Already established</p><ul class="ae-comps">{"".join(f"<li>{e(x)}</li>" for x in rq["already_established"])}</ul></div>
  </div>
  <p class="ae-note">{e(rq['caveat'])}</p>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Proposed architecture</h2><div class="mono kicker">Design, not built</div></div>
  <p class="ae-intro">{e(arch['note'])}</p>
  <div class="panel dashed-panel" style="margin-top:28px">
    <div class="panel-bar"><i></i><i></i><span class="mono">scenesearch / proposed flow</span></div>
    <div class="panel-body"><div class="layers">{"".join(flow)}</div>
      <div style="margin-top:22px">{cross}</div>
    </div>
  </div>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Baselines and experiments</h2><div class="mono kicker">Planned</div></div>
  <section class="ae-spec" style="margin-top:26px"><div class="ae-rows">{bl}</div></section>
  <p class="mono pl" style="margin-top:30px">Planned experiments</p>
  <ul class="ae-comps">{lists('experiments')}</ul>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Evaluation</h2><div class="mono kicker">Nothing measured yet</div></div>
  <div class="panel" style="margin-top:26px">
    <div class="panel-bar"><i></i><i></i><span class="mono">scenesearch / planned measures</span></div>
    <div class="panel-body"><div class="rows">{meas}</div>
      <div class="mono panel-foot"><span>No experiment has run</span><span>planned</span></div>
    </div>
  </div>
  <p class="mono pl" style="margin-top:30px">Evaluation design</p>
  <ul class="ae-comps">{"".join(f"<li>{e(x)}</li>" for x in p["evaluation"]["design"])}</ul>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Month by month</h2><div class="mono kicker">November to March</div></div>
  <p class="ae-intro">{e(p['workload_note'])}</p>
{chr(10).join(months)}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>What the curriculum already covers</h2><div class="mono kicker">Audit first</div></div>
  <p class="ae-intro">{e(p['skill_audit']['note'])}</p>
  <div class="ae-grid">
{chr(10).join(audit)}
  </div>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Sequencing</h2><div class="mono kicker">Undetermined</div></div>
  <p class="ae-lede" style="margin-top:24px">{e(p['sequencing']['finding'])}</p>
  <ul class="ae-comps" style="margin-top:20px">{"".join(f"<li>{e(x)}</li>" for x in p["sequencing"]["consequences"])}</ul>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Proposed changes &mdash; approval needed</h2><div class="mono kicker">Not applied</div></div>
  <p class="ae-intro">{e(p['proposed_changes']['note'])}</p>
{chr(10).join(props)}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>SceneSearch learning plan</h2><div class="mono kicker">Build-aligned</div></div>
  <p class="ae-intro">{e(p['learning_plan']['note'])}</p>
  {lp}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Deliverables, limits and cost</h2><div class="mono kicker">Scope discipline</div></div>
  <div class="split2" style="margin-top:26px">
    <div><p class="mono pl">Engineering deliverables</p><ul class="ae-comps">{lists('deliverables')}</ul></div>
    <div><p class="mono pl">Out of scope for the first release</p><ul class="ae-comps">{lists('out_of_scope')}</ul></div>
  </div>
  <p class="mono pl" style="margin-top:30px">Responsible development</p>
  <ul class="ae-comps">{lists('responsible')}</ul>
  {facts([("Planning envelope", e(p['budget']['estimate'])),
          ("Excludes", e(p['budget']['excludes'])),
          ("Caveat", e(p['budget']['caveat']))])}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Why this project</h2><div class="mono kicker">Portfolio objective</div></div>
  <p class="mono pl" style="margin-top:26px">Designed to demonstrate</p>
  <ul class="ae-comps">{"".join(f"<li>{e(x)}</li>" for x in p["hiring_relevance"]["skills"])}</ul>
  <p class="ae-note">{e(p['hiring_relevance']['disclaimer'])}</p>
</section>
{back(depth)}"""
    return page(HERE / "scenesearch" / "index.html", depth,
                f"SceneSearch - {p['subtitle']} - Joseph Morante",
                e(p["short_description"]),
                f"{base}scenesearch/", body)


def build_hub(d: Data):
    depth = 1
    DEPTH["d"] = depth
    base = d.page["canonical"]
    c = d.counts()
    cells = [(str(c["unique_courses"]), "Unique courses selected"),
             (str(c["completed"]), "Courses completed"),
             (str(c["in_progress"]), "Courses in progress"),
             (f'{c["modules_done"]}/{c["modules"]}', "From Scratch phases done"),
             (str(c["artifacts"]), "Artifacts with evidence"),
             (str(c["notes"]), "Technical notes published")]
    stats = "".join(f'<div class="stat"><div class="stat-v">{v}</div>'
                    f'<div class="mono stat-l">{e(l)}</div></div>' for v, l in cells)

    entries = []
    for cur in d.curricula:
        if cur["id"] == "from-scratch":
            href, desc = "curriculum/from-scratch/", f"{len(d.modules)} phases, free and open source. Implementation-first."
            tally = f'{STATUS_LABEL[cur["status"]]} \u00b7 {c["modules_done"]} of {len(d.modules)} phases complete'
        elif cur.get("layout") == "sequence" or cur["id"] == "adtech":
            href = f"curriculum/{cur['id']}/"
            n = len(d.courses_for(cur["id"]))
            desc = e(cur["short_subtitle"])
            done = len([x for x in d.courses_for(cur["id"]) if x["status"] == "completed"])
            tally = f'{STATUS_LABEL[cur["status"]]} \u00b7 {done} of {n} complete'
            entries.append(f"""      <a class="ae-entry" href="{href}">
        <h3 class="ae-h3">{e(cur['name'])}</h3>
        <p class="ae-entry-d">{desc}</p>
        <p class="mono ae-tally">{tally}</p>
      </a>""")
            continue
        else:
            slug = {"ms-cs": "computer-science", "ms-ai": "artificial-intelligence"}[cur["id"]]
            href = f"curriculum/{slug}/"
            n = len(d.courses_for(cur["id"]))
            desc = f"{n} one-credit course positions across breadth and electives, studied independently."
            done = len([x for x in d.courses_for(cur["id"]) if x["status"] == "completed"])
            tally = f'{STATUS_LABEL[cur["status"]]} \u00b7 {done} of {n} complete'
        entries.append(f"""      <a class="ae-entry" href="{href}">
        <h3 class="ae-h3">{e(cur['long_name'])}</h3>
        <p class="ae-entry-d">{e(desc)}</p>
        <p class="mono ae-tally">{e(tally)}</p>
      </a>""")
    for href, name, desc, tally in [
        ("scenesearch/", "SceneSearch",
         "Multimodal video retrieval with reproducible evaluation. Planned, with a curriculum audit behind it.",
         f'{STATUS_LABEL[d.scenesearch.get("status", "planned")]} \u00b7 '
         f'{len(d.scenesearch.get("roadmap", []))} month plan'),
        ("building-signal/", "Building SIGNAL",
         "The flagship product: roadmap, milestones backed by evidence, and the build log.",
         f'{len([t for t in d.signal.get("timeline", []) if t["status"] == "completed"])} of '
         f'{len(d.signal.get("timeline", []))} milestones complete'),
        ("engineering-evidence/", "Engineering evidence",
         "Artifacts with architecture, tests, measured results and limitations.",
         f'{c["artifacts"]} artifacts'),
        ("competencies/", "Skills &amp; competencies",
         "The same work by capability, separating studied from demonstrated.",
         f'{c["competencies_with_evidence"]} of {len(d.competencies)} backed by evidence'),
        ("technical-notes/", "Technical notes",
         "Write-ups on a mechanism, its implementation and its failures.",
         f'{c["notes"]} published')]:
        entries.append(f"""      <a class="ae-entry" href="{href}">
        <h3 class="ae-h3">{name}</h3>
        <p class="ae-entry-d">{e(desc)}</p>
        <p class="mono ae-tally">{e(tally)}</p>
      </a>""")

    stages = []
    for st in d.roadmap.get("stages", []):
        items = []
        for sk in st.get("skills", []):
            ev = sk.get("evidence")
            tail = (f' <a class="ul" href="engineering-evidence/#artifact-{e(ev)}">{e(d.art_by_id[ev]["name"])}</a>'
                    if ev and ev in d.art_by_id else "")
            items.append(f'<li class="ae-skill ae-s-{e(sk["state"])}">'
                         f'<span class="ae-state mono">{e(SKILL_LABEL[sk["state"]])}</span>'
                         f'<span class="ae-skill-n">{e(sk["name"])}{tail}</span></li>')
        stages.append(f"""      <section class="ae-stage">
        <h3 class="ae-h3 ae-stage-h">{e(st['name'])}</h3>
        <p class="ae-stage-s">{e(st['summary'])}</p>
        <ul class="ae-skills">{''.join(items)}</ul>
      </section>""")

    body = f"""<header class="wrap ae-head">
  <p class="mono eyebrow">Independent study &middot; Implementations &middot; Evidence</p>
  <h1>{e(d.page['heading'])}</h1>
  <p class="ae-lede">{e(d.page['lede'])}</p>
  <p class="ae-stand">{e(d.page['standfirst'])}</p>
  <p class="ae-disclosure">{e(d.page['disclosure'])}</p>
  <div class="stats ae-stats">{stats}</div>
  <p class="ae-note">Every number above is counted from the records behind this section. Nothing is estimated, and a zero means zero.</p>
</header>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Independent study</h2><div class="mono kicker">{len(d.curricula)} pathways</div></div>
  <p class="ae-intro">Two graduate curricula followed on my own through their open, non-credit versions, a free implementation-first course, and a focused pathway in advertising measurement. Each tracks its own progress.</p>
  <div class="ae-grid">
{chr(10).join(entries[:len(d.curricula)])}
  </div>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Evidence</h2><div class="mono kicker">Five views</div></div>
  <p class="ae-intro">What the study has actually produced, and what it has not yet.</p>
  <div class="ae-grid">
{chr(10).join(entries[len(d.curricula):])}
  </div>
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2>Progression</h2><div class="mono kicker">Foundations &#8594; Advanced</div></div>
  <p class="ae-intro">A personal ordering, not a sequence either university mandates. Finishing a course does not move a skill into the demonstrated column; shipping something that works does.</p>
{chr(10).join(stages)}
</section>

<section class="wrap ae-sec">
  <div class="sec-head"><h2 class="h2-sm">Questions about any of this?</h2></div>
  <p class="ae-intro">I am glad to go deeper on any artifact here, including the employer work I cannot publish. <a class="ul" href="mailto:morantejoseph1@gmail.com">Email me</a>.</p>
  <div class="mono foot"><span><a href="../">&#8592; Back to the portfolio</a></span><span>morantejoseph1@gmail.com</span></div>
</section>"""
    return page(HERE / "index.html", depth,
                "AI Engineering - Joseph Morante",
                e(d.page["meta_description"]), base, body)


def build():
    d = Data()
    validate(d)
    SHARED["css"], SHARED["js"], SHARED["icon"] = extract_shared()
    if errors:
        print("FAILED - content did not validate:\n", file=sys.stderr)
        for m in errors:
            print(f"  error: {m}", file=sys.stderr)
        for m in warnings:
            print(f"  warn:  {m}", file=sys.stderr)
        return 1
    for m in warnings:
        print(f"  warn:  {m}")

    # remove stale generated dirs so deletions in content propagate
    for sub in ("curriculum", "engineering-evidence", "competencies", "technical-notes",
                "building-signal", "scenesearch"):
        p = HERE / sub
        if p.exists():
            shutil.rmtree(p)

    # every course row must render its link — a computed-but-unused link has
    # shipped twice now, so assert it instead of trusting the renderer
    total = build_hub(d)
    for cur in d.curricula:
        if cur["id"] == "from-scratch":
            total += build_from_scratch_page(d)
        elif cur.get("layout") == "sequence":
            total += build_sequence_page(d, cur)
        elif cur["id"] == "adtech":
            total += build_adtech_page(d)
        else:
            total += build_curriculum_page(d, cur)
    total += build_signal_page(d)
    total += build_scenesearch_page(d)
    total += build_evidence_page(d)
    total += build_competencies_page(d)
    total += build_notes_page(d)

    import re as _re
    for cur in d.curricula:
        slug = {"ms-cs": "computer-science", "ms-ai": "artificial-intelligence"}.get(
            cur["id"], cur["id"])
        pg = (HERE / "curriculum" / slug / "index.html").read_text(encoding="utf-8")
        rows = len(_re.findall(r'class="ae-row"', pg))
        want = (len(d.modules) if cur["id"] == "from-scratch"
                else len(d.courses_for(cur["id"])))
        if rows != want:
            print(f"  warn:  {slug}: {rows} rows rendered, expected {want}")
        linked = (len([m for m in d.modules if m.get("url")]) if cur["id"] == "from-scratch"
                  else len([x for x in d.courses_for(cur["id"]) if x.get("official_url")]))
        hrefs = len(_re.findall(r'<a class="[^"]*" href="https://', pg))
        if hrefs < linked:
            print(f"  warn:  {slug}: {hrefs} course links rendered, "
                  f"{linked} records carry a url")

    c = d.counts()
    print(f"built {8 + len(d.curricula)} pages, {total:,} bytes total")
    print(f"  courses {c['unique_courses']} unique "
          f"(ms-cs {len(d.courses_for('ms-cs'))}, ms-ai {len(d.courses_for('ms-ai'))}, "
          f"shared {len([x for x in d.courses if len(x['curricula'])==2])})")
    print(f"  completed {c['completed']} | in progress {c['in_progress']} | planned {c['planned']}")
    print(f"  phases {c['modules']} | artifacts {c['artifacts']} | notes {c['notes']}")
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        d = Data()
        validate(d)
        if errors:
            for m in errors:
                print(f"  error: {m}", file=sys.stderr)
            sys.exit(1)
        for m in warnings:
            print(f"  warn:  {m}")
        print("content OK")
        sys.exit(0)
    sys.exit(build())
