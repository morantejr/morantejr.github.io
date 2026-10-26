# The Learning Log

A monthly journal, **generated** from `content/learning-log.json`. Edit the JSON, run the
build, commit the result. Do not hand-edit a generated `index.html` — the next build
overwrites it.

```bash
python3 learning-log/build.py --check    # validate content, write nothing
python3 learning-log/build.py            # validate, then write PUBLISHED entries only
python3 learning-log/build.py --drafts   # also render drafts under preview/ for review
python3 learning-log/build.py --test     # bite tests: inject a defect, assert the build rejects it
```

No dependencies beyond Python 3. The design system is not duplicated: the builder lifts the
`<style>` block, the theme script and the favicon out of the site's `index.html` through the
ai-engineering builder, so a colour token changed there follows here on the next build.

## Drafts never ship by accident

An entry with `"draft": true` is excluded from the index, from every count, and from the
built tree. It renders only under `learning-log/preview/<id>/`, where it carries a visible
banner and `<meta name="robots" content="noindex, nofollow">`, and is linked from nothing.

**A plain `build.py` run deletes `preview/` entirely.** So the sequence before committing is:

```bash
python3 learning-log/build.py     # drafts gone, published entries written
```

If you reviewed a draft with `--drafts`, run the plain build again before committing or the
preview directory goes into the repository.

## Where it is linked from

Not in the main nav. The nav already carries eight items and overflows at 375px, so adding a
ninth would have made an existing problem worse. The section is reached from:

- **Research & Writing** on the home page (a card in `index.html`)
- **The AI Engineering hub**, as an entry point whose tally reads `N entries published` —
  or `N in draft` when nothing is published yet, so the hub never implies more than exists

## Adding next month's entry

Append an object to `entries` in `content/learning-log.json`. Only `id`, `month`, `title`
and `summary` are required; **every other field is optional and an empty one renders
nothing**, so a thin month looks thin rather than padded.

```json
{
  "id": "2026-11",
  "month": "November 2026",
  "draft": true,
  "title": "What the first problem set actually cost me",
  "summary": "One paragraph a reader can judge the entry by.",
  "tags": ["Algorithms", "Working practice"],
  "body": [
    {"type": "text", "text": "A paragraph. **Strong** and *emphasis* work."},
    {"type": "heading", "text": "A section heading"},
    {"type": "list", "items": ["A point.", "Another point."]},
    {"type": "quote", "text": "A line worth setting apart.", "attribution": "Someone, or null"},
    {"type": "note", "text": "An aside in a bordered panel."},
    {"type": "code", "lang": "python", "caption": "optional",
     "code": "def f(x):\n    return x * 2"},
    {"type": "math", "caption": "optional",
     "mathml": "<math><mi>O</mi><mo>(</mo><mi>n</mi><mo>log</mo><mi>n</mi><mo>)</mo></math>"},
    {"type": "figure", "src": "media/plot.png", "alt": "Required. Describe the plot.",
     "caption": "optional"},
    {"type": "figure", "svg": "<svg viewBox=\"0 0 10 10\">…</svg>", "caption": "optional"},
    {"type": "principles", "items": [{"when": "Before coding", "rule": "…"}]}
  ],
  "subjects": ["Dynamic programming"],
  "built": ["What I made, with a link in 'links'."],
  "misunderstood": ["What I had wrong at the start."],
  "failures": ["What broke, and what it cost."],
  "tested": ["How I checked I actually understood it."],
  "changed_thinking": ["The evidence that moved me."],
  "differently": ["What I would change next time."],
  "next_focus": "One paragraph.",
  "resources": [
    {"kind": "Paper", "author": "Author Name", "title": "Title",
     "url": "https://…", "note": "Why it mattered. Say if you borrowed the framing rather than tested it."}
  ],
  "pathways": ["from-scratch", "signal"],
  "links": [{"label": "Repository", "url": "https://github.com/…"}]
}
```

Then rebuild. The index, the chronology, the previous-entry link and the hub tally all
follow from that one edit.

### Images and diagrams

Put image files in `learning-log/media/` and reference them as `media/<file>` — the builder
resolves the path for the page's depth. Diagrams can also be inlined as `svg`, which avoids
a request and themes with the rest of the site. The page CSP allows `img-src 'self'`, so a
remote image needs the CSP in `ai-engineering/build.py` widened first.

### Mathematics

Math is **MathML**, rendered natively by the browser. There is no KaTeX or MathJax, because
the site has no build step for the hand-written pages and a strict CSP that a CDN script
would force open. For heavier typesetting, vendor a renderer into `vendor/` the way
`three.r160.min.js` is vendored, and widen `script-src` — but that is a real cost, so it
should wait until an entry genuinely needs it.

## What the validator enforces

The rules exist to stop the journal drifting into a progress dashboard.

- `id` is `YYYY-MM`, unique, and **may not be in the future** — no entries written ahead of
  the work.
- `month` must agree with `id` (`2026-11` must read `November 2026`).
- `draft` must be a boolean.
- **A published entry needs either a retrospective field** (`built`, `misunderstood`,
  `failures`, `tested`, `changed_thinking`, `differently`) **or a written body of at least
  three blocks.** Publishing an entry with neither fails the build. Publishing with a body
  but no retrospective field passes with a warning, because a reflection is a legitimate
  entry — it just should not be the norm.
- `resources` need `author`, `title` and an absolute https `url`.
- `links` need `label` and a url that is https, an anchor, or uses the `{root}` token.
- `pathways` ids must be known, and each target must exist in the built tree.
- A `figure` with an image must have `alt`.
- Block `type` must be known — a typo fails instead of silently rendering nothing.
- **Every relative `src`/`href` in a generated page must resolve to a real file.** This
  catches an off-by-one in a page's depth, which otherwise ships as working links and
  silently 404ing fonts.

Run `--test` to see each rule demonstrated: the suite injects a defect and asserts the
build rejects it.

## Deploying

`.github/workflows/deploy.yml` uploads the repository root as-is, so the generated pages
must be committed. Run the plain build before committing, or the published pages lag the
content — and a `preview/` directory left behind would publish an unreviewed draft.
