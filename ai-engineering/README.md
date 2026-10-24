# AI Engineering hub

Seven **generated** pages under `/ai-engineering/`. Edit the JSON in `content/`, run the
build, commit the result. Do not hand-edit any generated `index.html` — the next build
overwrites it.

```bash
python3 ai-engineering/build.py --check   # validate content, write nothing
python3 ai-engineering/build.py           # validate, then regenerate all pages
```

No dependencies beyond Python 3. The build refuses to write pages from content that does
not validate.

## Why it is generated

The rest of the site is hand-written static HTML with inline CSS and no build step. A
client-side renderer would have hidden the content from crawlers and broken it without
JavaScript, so content renders to static HTML at author time. The design system is **not**
duplicated: `build.py` lifts the `<style>` block, the theme script and the favicon out of
the site's `index.html` on every run. Change a colour token there, rebuild, and all seven
pages follow.

## Pages

| Route | Source |
|---|---|
| `/ai-engineering/` | hub: counts, entry points, five-stage progression |
| `/ai-engineering/curriculum/computer-science/` | `courses.json` filtered to `ms-cs` |
| `/ai-engineering/curriculum/artificial-intelligence/` | `courses.json` filtered to `ms-ai` |
| `/ai-engineering/curriculum/from-scratch/` | `modules.json` |
| `/ai-engineering/curriculum/adtech/` | `courses.json` filtered to `adtech` |
| `/ai-engineering/engineering-evidence/` | `artifacts.json` |
| `/ai-engineering/competencies/` | `competencies.json` |
| `/ai-engineering/technical-notes/` | `notes.json` |
| `/ai-engineering/building-signal/` | `signal.json` |

## Content files

```
content/page.json          headings, intro copy, the independent-study disclosure, meta
content/curricula.json     the three curricula + the specialization catalogue
content/courses.json       42 canonical CU Boulder course records
content/modules.json       the 20 AI Engineering from Scratch phases
content/competencies.json  12 competency areas and what backs each
content/artifacts.json     things built, tested, deployed
content/notes.json         technical write-ups
content/roadmap.json       Stage 1-5 study progression
content/signal.json        SIGNAL: positioning, business hypotheses, roadmap, timeline, blogs, videos
```

### Credit-bearing and non-credit pathways

A curriculum with `breadth_credits` set (the two CU plans) is held to its credit arithmetic
and to exactly two pathway specializations. A curriculum with `breadth_credits: null` (AI
Engineering from Scratch, AdTech) is exempt from both, because its courses carry no credit
value. Course `code` is likewise optional: the row falls back to the institution name, which
is what the Coursera courses use.

AdTech courses carry extra fields the CU records leave null: `instructors`, `relevance`,
`suggested_evidence`, `experiments`, `benchmarks`, `decisions`, `learned` and `results`.
They also set `coursera_url`, since unlike the CU courses these have direct Coursera pages.

### One course, two curricula

A course appears **once** in `courses.json` and declares its memberships:

```json
"curricula": [
  {"curriculum": "ms-cs", "role": "elective", "pathway": false},
  {"curriculum": "ms-ai", "role": "breadth",  "pathway": true}
]
```

Both curriculum pages render from that single record, so updating a status once updates
both views. 18 of the 42 courses sit in both plans. `pathway` is per-curriculum because a
specialization that is an admission pathway for MS-AI is not one for MS-CS.

## What the validator enforces

- Unique slug ids; every cross-reference resolves (specialization, curriculum, competency,
  module, artifact, course).
- `status` is `planned`, `in-progress` or `completed`.
- **A course marked `completed` must carry a `completed_date` or a `certificate_url`.**
  The page should never show a credential claim without evidence behind it.
- Breadth and elective course counts must equal the credits declared for that curriculum
  (15 and 15), so a miscount fails the build instead of shipping.
- Exactly two pathway specializations per CU curriculum.
- A module may not carry a URL unless `slug_verified` is true, which stops guessed links.
- A roadmap skill may be `demonstrated` only if it names an artifact.
- `official_url` must be absolute https; artifact links must be absolute, an anchor, or use
  the `{root}` token.
- Curriculum-level `status` is separate from course status, so a curriculum can be in
  progress while its courses are still planned.
- `signal_component` must be a string or null.
- Each course's `competencies` must reference real competency ids; these drive the "Skills"
  line on the curriculum rows.

Links that must point back to the site root use `{root}`, for example `{root}#work`. The
builder expands it to the right number of `../` for each page's depth. Never hardcode `../`
in content, because the same record renders at several depths.

## Accuracy rules this encodes

Course titles, codes and specialization membership were read from the official CU Boulder
curriculum pages on 2026-10-23 and each record stores its `source_url` and `verified_on`.
Neither CU Boulder nor Coursera publishes direct per-course Coursera URLs on those pages,
so `coursera_url` is `null` for all 42 and links point at CU's own syllabus pages. All 42
were checked and return HTTP 200.

Four From Scratch phases (12, 16, 18, 19) had no slug observable on the pages read, so they
carry no link rather than a guessed one, and the page says so.

The independent-study disclosure in `page.json` appears on the hub and on both CU
curriculum pages. Keep it accurate if the situation changes.

---

## Adding a monthly blog entry or a video

Both live in `content/signal.json`. A blog entry needs `id`, `month`, `title`, `set_out` and
`built` at minimum; the other fields render only when present:

```json
{"id": "2026-11", "month": "November 2026", "title": "Closing the prediction loop",
 "set_out": "...", "built": "...", "learned": "...", "decisions": "...",
 "difficulties": "...", "testing": "...", "feedback": "...", "metrics": "...",
 "next": "...", "url": null}
```

A video needs `id`, `title`, `youtube_id` and `published`; it embeds through
youtube-nocookie with lazy loading:

```json
{"id": "v1", "title": "SIGNAL in two minutes", "youtube_id": "XXXXXXXXXXX",
 "published": "2026-11-30", "description": "..."}
```

Timeline milestones may be marked `completed` only with an `evidence` string, and the build
fails otherwise. The business block must keep its `disclaimer` field.

## Linking a course to SIGNAL

SIGNAL is the one flagship project, so coursework points at it rather than at new projects.
Every course record carries a nullable `signal_component` field. Fill it with the component
name and it renders on the curriculum row beside the course:

```json
"signal_component": "Quant scorer (quant/score.py)",
"related_artifacts": ["signal"]
```

Not every course needs one. Some contribute architecture, testing or understanding rather
than a feature, and leaving it null is the honest outcome.

## Add your first course progress update

1. Open `content/courses.json` and find the course by its code, for example `csca-5414`.
2. Starting it:

```json
"status": "in-progress",
"started_date": "2026-11-01",
"notes": "Working through the dynamic programming section."
```

3. Finishing it — this is the part the validator polices:

```json
"status": "completed",
"completed_date": "2027-01-15",
"certificate_url": "https://www.coursera.org/account/accomplishments/verify/XXXX",
"concepts": ["Memoisation vs tabulation", "Greedy exchange arguments"],
"competencies": ["algorithms"],
"related_artifacts": ["algo-benchmarks"]
```

Omit both `completed_date` and `certificate_url` and the build **fails**. If you studied a
course in the free non-credit version and there is no certificate, put the completion date
and leave `certificate_url` null — that is honest and it passes.

4. Rebuild. The hub counter, both curriculum pages and any competency that references the
   course all update from that one edit.

## Attach an engineering artifact

1. Add it to `content/artifacts.json`:

```json
{
  "id": "algo-benchmarks",
  "placeholder": false,
  "name": "Algorithm Benchmarking Library",
  "kind": "independent",
  "track": "Track 1 — Algorithms & Data Structures",
  "competencies": ["algorithms", "software-engineering"],
  "problem": "What it is for, in a sentence a stranger understands.",
  "architecture": "How it is put together.",
  "stack": ["Python", "pytest", "hypothesis"],
  "repo_url": "https://github.com/morantejr/algo-benchmarks",
  "extra_links": [{"label": "Benchmarks", "url": "https://github.com/morantejr/algo-benchmarks#results"}],
  "decisions": ["A choice you made, and what you rejected."],
  "testing": "What is asserted and what passing proves.",
  "evaluation": "What you measured, with the number.",
  "deployment": null,
  "limitations": "What it does not handle.",
  "related_courses": ["csca-5414"]
}
```

2. Set `kind` honestly: `independent`, `tutorial`, `research`, or `production`. It renders
   as a visible label.
3. Reference the id from `competencies.json` under `artifacts`, and from a roadmap skill's
   `evidence` field. Only then may that skill be `demonstrated`.
4. Rebuild. It appears on the evidence page with an `#artifact-algo-benchmarks` anchor that
   the competency and roadmap links point at.

## Publish a technical note

1. Add it to `content/notes.json` and drop the `"placeholder": true` flag:

```json
{
  "id": "why-attention-masks-first",
  "title": "The mask goes before the softmax",
  "date": "2026-11-20",
  "competencies": ["llm-engineering"],
  "summary": "One or two sentences a reader can judge the note by.",
  "learned": "What I did not understand before.",
  "mechanism": "How it actually works.",
  "implemented": "What I built to test the understanding.",
  "failed": "What broke, and what it taught.",
  "tradeoffs": "The design choice and what it cost.",
  "production": "Why it matters when the system has users.",
  "url": "https://github.com/morantejr/ai-from-scratch/blob/main/notes/attention-mask.md"
}
```

2. Keep it specific. A note that could have been written without doing the work is worse
   than no note.
3. Rebuild. Placeholder entries are dimmed, tagged "Example entry", and excluded from every
   count on the site.

## Deploying

`.github/workflows/deploy.yml` uploads the repository root as-is, so the generated pages
must be committed. Run the build before committing, or the published pages lag the content.
To have CI build instead, add a `python3 ai-engineering/build.py` step before
`upload-pages-artifact`.
