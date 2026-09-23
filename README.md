# Joseph Morante — Portfolio

Static, single-page portfolio site. No build step, no JavaScript, no external requests.

## Structure

```
index.html                  the page (markup + inline CSS)
404.html                    not-found page
fonts/                      IBM Plex Mono 400/500, latin + latin-ext (woff2)
robots.txt
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

## Editing

All content lives in `index.html`. Sections in order: hero, work, research, experience, teaching, about, contact. The `Resume` links currently point to LinkedIn; to ship a PDF, drop `resume.pdf` in the root and change those two `href`s.
