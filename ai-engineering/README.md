# AI Engineering section

The page at `/ai-engineering/` is **generated**. Edit the JSON in `content/`, run the
build, commit the result. Do not hand-edit `ai-engineering/index.html` — the next build
overwrites it.

```bash
python3 ai-engineering/build.py --check   # validate content, write nothing
python3 ai-engineering/build.py           # validate, then regenerate index.html
```

No dependencies beyond Python 3. The build fails loudly rather than writing a page from
content that does not validate.

## Why it is generated

The rest of the site is hand-written static HTML with inline CSS and no build step. A
client-side renderer would have put the content out of reach of crawlers and broken it for
anyone with JavaScript off, so the content is rendered to static HTML at author time
instead. The design system is **not** duplicated: `build.py` lifts the `<style>` block, the
theme script, and the favicon out of the site's `index.html` every time it runs, so this
page cannot drift from the rest of the site. Change a colour token in `index.html`, rebuild,
and this page follows.

## Files

```
content/page.json        headings, intro copy, meta description, canonical URL
content/pathways.json    the six learning tracks
content/courses.json     Coursera coursework
content/scratch.json     AI Engineering from Scratch modules
content/artifacts.json   things built, tested, deployed
content/notes.json       technical write-ups
content/roadmap.json     Foundations -> Implementation -> Production -> Reliability
build.py                 validator + generator
index.html               GENERATED — do not edit
```

## What the validator enforces

- Every `id` is a unique lowercase-hyphen slug.
- `status` is one of `planned`, `in-progress`, `completed`.
- A course marked `completed` must carry a `completed_date` or a `certificate_url`.
  This is deliberate: the page should never show a credential claim without evidence.
- `pathway`, `related_artifact`, `related_courses`, and roadmap `evidence` must all point
  at ids that actually exist.
- A roadmap skill marked `demonstrated` must name an artifact.
- Required fields are present and non-empty; URLs are well-formed.

Set `"placeholder": true` on any entry that is a format example. Placeholders render with a
dashed "Example entry" tag, are dimmed, and are **excluded from every count** on the page.
Delete them once you have real entries.

---

## Add your first Coursera course

1. Open `content/courses.json`.
2. Delete the three `example-*` entries once you have a real one.
3. Add your course. A planned course needs very little:

```json
{
  "id": "deep-learning-specialization",
  "title": "Deep Learning Specialization",
  "provider": "Coursera",
  "institution": "DeepLearning.AI",
  "url": "https://www.coursera.org/specializations/deep-learning",
  "status": "planned",
  "completed_date": null,
  "certificate_url": null,
  "pathway": "foundations",
  "skills": ["Backpropagation", "CNNs", "Sequence models"],
  "related_artifact": null,
  "outcomes": []
}
```

4. When you finish it, change `status` to `"completed"` and fill in `completed_date`
   (`YYYY-MM-DD`) and `certificate_url`. The build **fails** if you mark it completed
   without one of those. Add an `outcomes` entry saying what you can now do, and point
   `related_artifact` at whatever you built with it.
5. Rebuild: `python3 ai-engineering/build.py`

`pathway` must be one of: `foundations`, `transformers`, `applications`, `agents`,
`mlops`, `evaluation`.

## Add your first AI Engineering from Scratch module

1. Open `content/scratch.json` and replace the example entries.

```json
{
  "id": "attention-from-scratch",
  "title": "Attention from scratch",
  "concept": "Scaled dot-product attention, implemented without a framework's layer.",
  "pathway": "transformers",
  "status": "completed",
  "repo_url": "https://github.com/morantejr/ai-from-scratch",
  "tests": "Asserts the output matches a reference implementation to 1e-6 on random inputs.",
  "benchmarks": "Forward pass timing against the framework layer at three sequence lengths.",
  "notes": "The mask has to be applied before the softmax, not after.",
  "limitations": "Single head, no KV cache, float32 only."
}
```

2. Keep `tests`, `benchmarks`, and `limitations` honest and specific. They are the fields
   that make this section worth more than a list of lesson titles. A completed module with
   no `repo_url` produces a build warning.
3. Do not paste curriculum text from the course into these fields. Describe your own
   implementation in your own words.
4. Rebuild.

## Add a GitHub implementation as an artifact

1. Open `content/artifacts.json`.

```json
{
  "id": "ai-from-scratch",
  "placeholder": false,
  "name": "ai-from-scratch",
  "kind": "tutorial",
  "pathway": "transformers",
  "problem": "What the code is for, in a sentence a stranger understands.",
  "architecture": "How it is put together.",
  "stack": ["Python", "NumPy", "pytest"],
  "repo_url": "https://github.com/morantejr/ai-from-scratch",
  "extra_links": [{"label": "Benchmarks", "url": "https://github.com/morantejr/ai-from-scratch#benchmarks"}],
  "decisions": ["A choice you made and why."],
  "testing": "What is asserted and what passing proves.",
  "evaluation": "What you measured, with the number.",
  "deployment": null,
  "limitations": "What it does not do.",
  "related_courses": ["deep-learning-specialization"]
}
```

2. Set `kind` accurately. It is rendered as a visible label and it is the honest part:
   - `independent` — your own engineering, your own problem
   - `tutorial` — followed a course or book
   - `research` — a prototype built to answer a question
   - `production` — running somewhere people depend on it
3. `related_courses` must contain ids that exist in `courses.json`, or the build fails.
4. Link it from the roadmap by putting its id in a skill's `evidence` field in
   `content/roadmap.json`. Only then may that skill be `demonstrated`.
5. Rebuild and check the page.

## Deploying

`.github/workflows/deploy.yml` uploads the repository root as-is, so the generated
`index.html` must be committed. Run the build before you commit, or the published page will
lag the content files. If you would rather the workflow build it for you, add a step that
runs `python3 ai-engineering/build.py` before `upload-pages-artifact`.
