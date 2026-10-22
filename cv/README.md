# CV

Three formats, one shared publication list.

- `cv-primary/`     main CV (LaTeX)
- `cv-overleaf/`    Overleaf CV + the master `.bib` (`journal.bib` + `conference.bib`)
- `cv-generation/`  scripts that build the pubs from the `.bib`

## Update a publication

1. Edit `cv-overleaf/journal.bib`
2. Run `bash cv-generation/build.sh`   (`--no-network` skips the PubMed lookup)

That regenerates the main CV (`cv-primary/cv_current.pdf`) and the website's
publications table, and compiles `cv-overleaf/main.pdf`. Overleaf is no longer used.

Everything else (positions, teaching, talks) is hand-edited in each CV.

Refresh the Google Scholar card + numbers: `python cv-generation/scholar_card.py`

`.bib` conventions and pipeline internals: see the repo-root `CLAUDE.md`.
