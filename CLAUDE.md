# CLAUDE.md

Guidance for Claude Code working in this repository.

## What This Is

Andrea Guarracino's personal website, plus the CV sources and the pipeline that builds them.

- **Website**: `index.adoc` → `index.html`, built with `asciidoctor -a docinfo=shared index.adoc`.
  A GitHub Pages user site (`andreaguarracino.github.io`), served from the `main` branch root
  via Jekyll. Asset folders: `images/`, `abstracts/`, `posters/`, `presentations/`, `slides/`,
  `certificates/`, `achievements/`, `other/`.
- **`cv/`** — all CV sources, excluded from the published site via `_config.yml` (`exclude: [cv]`):
  - `cv/cv-primary/` — main CV, `book` class, `lualatex` (`cv_current.tex`).
  - `cv/cv-overleaf/` — Overleaf variant, `moderncv`, `pdflatex` + `multibib`. Holds the master `.bib`.
  - `cv/cv-generation/` — the Python build pipeline.

  See `cv/README.md` for the short version.

## Publications are single-sourced from the .bib

**Canonical source for ALL publications is `cv/cv-overleaf/journal.bib` + `conference.bib`.**
Edit the `.bib`, then regenerate everything:

```bash
bash cv/cv-generation/build.sh                # rebuild primary CV, website table, index.html
bash cv/cv-generation/build.sh --no-network   # skip the PubMed lookup, use cached pubmed_cache.json
```

`cv/cv-generation/` (Python, needs `bibtexparser`) turns the `.bib` into:
- **primary CV** (`cv/cv-primary/`): `includes/publications.tex` + `includes/future_publications.tex`, and
  patches the header numbers. The header reads
  "**N** peer reviewed + **P** preprints = **T** total (**M** first or last)" where:
  peer-reviewed = published + in-press **journal** papers, preprints = `year={Submitted}`, and
  M = first-or-last-author count over all journal pubs, derived from the `.bib` asterisks.
  **Conference abstracts (`conference.bib`) are EXCLUDED** from these counts and from the primary CV's
  publication list (they show up only as talks/posters on the website). A live `Andrea Guarracino[au]`
  PubMed lookup (cached in `pubmed_cache.json`, skipped with `--no-network`) is used **only** to attach
  PMID/PMCID to the rendered publication list, **not** for the header counts.
- **website `index.adoc`**: the publications table, regenerated between
  `// cvgen:publications:begin/end` markers, then `index.html` rebuilt.
- **Overleaf** (`cv/cv-overleaf/main.tex`): consumes the `.bib` natively via bibtex, no generation.

See `cv/README.md` for the quick workflow. It replaced the old `pubmedSearch2tex.py`.

`.bib` conventions the generators rely on: `\textbf{Andrea Guarracino}` (bold marks him); a trailing
`*` on his name = **(co-)first author**, `**` = **last/senior author** (this drives the "first or last"
count); a matching `*` inside the `year` field (e.g. `year = {2024*}`) is an **intentional visible marker**
— keep it; `year = {Submitted}`/`{In press}`/`{YYYY}` for status; `\textbf{Journal}` for high-impact
emphasis; `note = {... Contribution: ...}` for the website's contribution column; and optional
`cvlinks = {Webserver=URL; Repository=URL}` for extra links.

**Not automated:** non-publication sections (positions, education, teaching, awards, talks).
Each CV writes them at a different level of detail, so there is no lossless single source. Edit
them by hand in each CV. The Scholar "Cited by" card (which shows citations + h-index + i10) is refreshed
by `python cv/cv-generation/scholar_card.py` (fetches Scholar live, regenerates
`cv/cv-primary/AndreaGuarracinoGoogleScholar.png`, and syncs the single
"Citations N (Month Year)" line in `cv_current.tex`; h-index/i10 live only on the card image).

## Sensitive files (this is a PUBLIC repo)

The site is public and git tracks the `cv/` `.tex`/`.bib` sources too (Jekyll only excludes them from the
*rendered* site), so anything committed is world-readable. Keep PII out:
- The gitignored **`private/`** dir holds local-only originals (the handwritten signature PNG, unmasked
  certificate scans). Publish only **masked** copies under the same filename so CV links still resolve.
- DOB / phone / tax-code in `cv_current.tex` are `XX...` commented placeholders — do not fill them with
  real values in the committed file.
- Referee contact details and some third-party signatures in `certificates/`/`other/` PDFs are known and
  were deliberately kept; don't re-flag them as new.

## Build

```bash
# one-time deps: texlive-full, bibtexparser + matplotlib (pip), asciidoctor, ruby
bash cv/cv-generation/build.sh          # everything except the Overleaf PDF
# Overleaf CV:
cd cv/cv-overleaf && pdflatex main && bibtex journal && bibtex conference && pdflatex main && pdflatex main
# website only:
asciidoctor -a docinfo=shared index.adoc
```
