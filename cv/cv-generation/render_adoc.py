#!/usr/bin/env python3
"""Render the website (index.adoc) publications table from the canonical .bib.

The website's publication table is regenerated in place between two markers:
  // cvgen:publications:begin ... // cvgen:publications:end
so you stop hand-maintaining publications in BOTH journal.bib and index.adoc.
Everything else in index.adoc is left untouched.

Cell conventions matched from the existing table:
  - Journal cell bold (*Venue, Year*) when Andrea is first/last author AND the
    paper is published; preprints show `Venue, _Submitted_` / `Venue, _In press_`.
  - Title cell: first author -> **title*, last author -> ***title*, else plain.
  - Contribution cell bold for first/last, plain otherwise.
  - Links: direct DOI link (icon:book[] Paper for published, icon:spinner[]
    Preprint for submitted/in press). NOTE: extra per-paper links a few entries
    used to carry (webserver/repository) are not in the .bib and are dropped.

Usage:
  python cvgen/render_adoc.py --preview   # write preview to scratch, don't touch site
  python cvgen/render_adoc.py             # inject into index.adoc in place
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_bib as pb  # noqa: E402

logger = logging.getLogger("cvgen.render_adoc")

CVGEN_DIR = Path(__file__).resolve().parent
REPO_ROOT = CVGEN_DIR.parent.parent  # repo root (holds index.adoc)
INDEX_ADOC = REPO_ROOT / "index.adoc"
PREVIEW = CVGEN_DIR / "publications.adoc.preview"

BEGIN = "// cvgen:publications:begin  (generated from cv-overleaf/*.bib -- do not edit by hand)"
END = "// cvgen:publications:end"

# .bib venue string -> website display name (only the ones that differ)
VENUE_DISPLAY = {
    "openRxiv": "bioRxiv",
    "JNCI: Journal of the National Cancer Institute": "Journal of the National Cancer Institute",
    "NAR Genomics and Bioinformatics": "NAR Genomics & Bioinformatics",
}


def venue_display(pub: pb.Pub) -> str:
    v = pub.venue
    v = re.sub(r"\s*\(in press\)\s*$", "", v, flags=re.IGNORECASE)
    return VENUE_DISPLAY.get(v, v)


def status_word(pub: pb.Pub) -> str:
    if pub.status == "submitted":
        return "_Submitted_"
    if pub.status == "in_press":
        return "_In press_"
    return str(pub.year) if pub.year else ""


def cell_escape(s: str) -> str:
    return s.replace("|", "\\|")


LINK_ICONS = {
    "webserver": "globe", "web server": "globe", "server": "globe",
    "repository": "github", "repo": "github", "code": "github",
    "graphical abstract": "file-image-o", "data": "database",
}


def link_icon(label: str) -> str:
    return LINK_ICONS.get(label.strip().lower(), "link")


def row(pub: pb.Pub) -> str:
    fl = pub.is_first or pub.is_last
    venue = cell_escape(venue_display(pub))
    stat = status_word(pub)
    # Unconstrained bold (**..**) is used throughout so it renders regardless of
    # neighbouring characters; the literal authorship asterisks use pass:[] (the
    # same mechanism the page's legend uses).
    if fl and pub.status == "published":
        journal = f"**{venue}, {stat}**"
    else:
        journal = f"{venue}, {stat}"

    title = cell_escape(pub.title)
    if pub.is_last:
        title_cell = f"pass:[**]**{title}**"
    elif pub.is_first:
        title_cell = f"pass:[*]**{title}**"
    else:
        title_cell = title

    contrib = cell_escape(pub.contribution) if pub.contribution else ""
    contrib_cell = f"**{contrib}**" if (fl and contrib) else contrib

    icon, label = ("spinner", "Preprint") if pub.status == "submitted" else ("book", "Paper")
    parts = [f"icon:{icon}[] https://doi.org/{pub.doi}[{label}]" if pub.doi
             else f"icon:{icon}[] {label}"]
    # optional supplementary links (web server / repo / ...) from the .bib cvlinks field
    for lbl, url in pub.extra.get("cvlinks", []):
        parts.append(f"icon:{link_icon(lbl)}[] {url}[{lbl}]")
    link = " +\n".join(parts)

    return f"| {journal}\n| {title_cell}\n| {contrib_cell}\n| {link}\n"


def render_table(pubs: list[pb.Pub]) -> str:
    head = (
        '[cols="1,3,3,1",options="header"]\n|===\n\n'
        "^| icon:newspaper-o[] Journal\n^| icon:book[] Title\n"
        "^| icon:pencil[] Contribution\n^| icon:link[] Links\n"
    )
    body = "\n".join(row(p) for p in pubs)
    return head + "\n" + body + "\n|===\n"


def build() -> str:
    # Website journal table: journal.bib only. Conference posters (conference.bib)
    # have no DOI and are not part of the site's journal-publications table.
    pubs = [p for p in sorted(pb.parse_all(), key=pb.sort_key, reverse=True)
            if p.source == "journal"]
    logger.info("rendering %d journal pubs into adoc table", len(pubs))
    return f"{BEGIN}\n{render_table(pubs)}{END}\n"


def inject(block: str) -> None:
    text = INDEX_ADOC.read_text()
    if BEGIN in text and END in text:
        new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
                     block, text, flags=re.DOTALL)
        logger.info("replaced existing generated block")
    else:
        # First run: replace the hand-written table (from the [cols=...] after the
        # Publications header through its closing |===) with the generated block.
        lines = text.splitlines(keepends=True)
        pub_hdr = next(i for i, l in enumerate(lines) if l.startswith("== icon:book[] Publications"))
        start = next(i for i in range(pub_hdr, len(lines)) if lines[i].startswith("[cols="))
        opens = [i for i in range(start + 1, len(lines)) if lines[i].strip() == "|==="]
        open_idx, close_idx = opens[0], opens[1]
        new = "".join(lines[:start]) + block + "".join(lines[close_idx + 1:])
        logger.info("first-run injection: replaced lines %d-%d", start + 1, close_idx + 1)
    INDEX_ADOC.write_text(new)


def main(preview: bool) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    block = build()
    if preview:
        PREVIEW.write_text(block)
        print(f"wrote preview -> {PREVIEW} ({block.count('| icon') // 1} link cells, "
              f"{block.count(chr(10))} lines)")
    else:
        inject(block)
        print(f"injected generated publications table into {INDEX_ADOC}")
    return 0


if __name__ == "__main__":
    sys.exit(main(preview="--preview" in sys.argv))
