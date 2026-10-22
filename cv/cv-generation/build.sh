#!/usr/bin/env bash
# Single-source CV build.
#
# Canonical source of truth for PUBLICATIONS is cv-overleaf/journal.bib +
# conference.bib. This script regenerates every publication list from them:
#   - primary CV LaTeX (cv-primary/includes/publications.tex + future_publications.tex, header)
#   - website index.adoc publications table (between cvgen markers) + index.html
# The second CV (cv-overleaf/main.tex) reads the .bib via bibtex.
#
# NON-publication sections (positions, teaching, awards, ...) are intentionally
# NOT generated: each CV carries them at a different level of detail, so there is
# no lossless single source. Edit those by hand in each file.
#
# Usage:  bash cv/cv-generation/build.sh [--no-network]
#   --no-network  skip the PubMed lookup (use cached pubmed_cache.json only)
set -euxo pipefail

CVGEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # cv/cv-generation
CV_ROOT="$(dirname "$CVGEN_DIR")"                           # cv/ umbrella
PRIMARY="$CV_ROOT/cv-primary"
SITE="$(dirname "$CV_ROOT")"                               # repo root (index.adoc)

echo ">> [1/5] publications .bib -> primary CV LaTeX (+ header counts)"
python "$CVGEN_DIR/render_cvtex.py" "$@"

echo ">> [2/5] compile primary CV pdf (lualatex x2)"
cd "$PRIMARY"
lualatex -interaction=nonstopmode -halt-on-error cv_current.tex >/dev/null
lualatex -interaction=nonstopmode -halt-on-error cv_current.tex >/dev/null

echo ">> [3/5] publications .bib -> website index.adoc table"
python "$CVGEN_DIR/render_adoc.py"

echo ">> [4/5] rebuild website index.html (asciidoctor)"
if command -v asciidoctor >/dev/null; then
  cd "$SITE"
  asciidoctor -a docinfo=shared index.adoc
else
  echo "   asciidoctor not found; skipping index.html rebuild (run it manually)"
fi

echo ">> [5/5] compile second CV pdf (pdflatex + bibtex)"
cd "$CV_ROOT/cv-overleaf"
pdflatex -interaction=nonstopmode -halt-on-error main >/dev/null
bibtex journal >/dev/null
bibtex conference >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main >/dev/null

set +x
echo
echo ">> DONE."
echo "   primary CV : $PRIMARY/cv_current.pdf"
echo "   website    : $SITE/index.html (source index.adoc)"
echo "   second CV  : $CV_ROOT/cv-overleaf/main.pdf"
