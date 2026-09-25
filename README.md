# Joseph Morante — Portfolio

Static, single-page portfolio site. No build step, no external requests. JavaScript is limited to the theme picker and the animated globe in the hero.

## Theme

The page switches between light and dark by the visitor's local clock: light from 07:00 to 18:59, dark otherwise. It re-checks every minute and on window focus. Append `?theme=light` or `?theme=dark` to the URL to force one. The hours live in `themeForHour` in the `<script>` at the top of `index.html`; colors are CSS variables on `:root` (dark) and `:root[data-theme="light"]`.

## Structure

```
index.html                  the page (markup + inline CSS)
404.html                    not-found page
fonts/                      IBM Plex Mono 400/500, latin + latin-ext (woff2)
vendor/                     three.js r134 + vanta.globe (hero background), vendored locally
robots.txt
JosephMorante_Resume.pdf     resume
SilentFail_AAAI_Proposal.pdf SilentFail-Bench research proposal
SilentFail_Auditing_the_Winner_draft.pdf   SilentFail-Bench paper draft
.nojekyll                   tells GitHub Pages to serve files as-is
.github/workflows/deploy.yml   GitHub Pages deploy on push to main
```

## Run locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Deploy to GitHub Pages

1. Create a GitHub repo (for a `username.github.io` URL, name it `<username>.github.io`; any other name serves at `<username>.github.io/<repo>/`).
2. Push this directory to the `main` branch.
3. In the repo, go to **Settings → Pages** and set **Source** to **GitHub Actions**.
4. The workflow in `.github/workflows/deploy.yml` runs on every push to `main`.

### Custom domain

Add a `CNAME` file containing just the domain (for example `josephmorante.com`), point the domain's DNS at GitHub Pages, and set the domain under **Settings → Pages**.

## Deploy elsewhere

Netlify, Vercel, and Cloudflare Pages all serve this as a static site with no configuration. Point them at the repo root, no build command, publish directory `.`.

## Hero globe

The hero background is [Vanta Globe](https://www.vantajs.com/?effect=globe) on three.js r134, both vendored in `vendor/` so the page makes no third-party requests. It mounts into `#vanta-bg` after `load`, is re-created with matching colors whenever the theme changes, and is skipped entirely for visitors with `prefers-reduced-motion: reduce`. Colors per theme are in the `palettes` object in the script at the bottom of `index.html`.

## Editing

All content lives in `index.html`. Sections in order: hero, work, research, experience, teaching, about, contact. The `Resume` links point to `JosephMorante_Resume.pdf` in the root; replace that file to update the resume.
