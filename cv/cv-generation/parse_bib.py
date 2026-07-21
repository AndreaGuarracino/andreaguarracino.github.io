#!/usr/bin/env python3
"""Parse the canonical Overleaf .bib files into normalized publication records.

Canonical source of truth for ALL publications is:
  cv-overleaf/journal.bib      (journal articles + preprints, DOI-keyed)
  cv-overleaf/conference.bib   (conference proceedings)

Everything else (primary cv/ LaTeX list, website index.adoc table) is generated
from these records. Edit the .bib, re-run the build, all outputs update.

This module only PARSES + NORMALIZES. Rendering lives in render_*.py.

Run directly to validate: `python cvgen/parse_bib.py` dumps a summary + JSON so
you can eyeball authorship/status/venue detection before trusting a renderer.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser

logger = logging.getLogger("cvgen.parse_bib")

# Layout: this file is cv/cv-generation/parse_bib.py; the .bib live in ../cv-overleaf/
CVGEN_DIR = Path(__file__).resolve().parent
CV_ROOT = CVGEN_DIR.parent  # the cv/ umbrella (cv-primary, cv-overleaf, cv-generation)
BIB_DIR = CV_ROOT / "cv-overleaf"
JOURNAL_BIB = BIB_DIR / "journal.bib"
CONFERENCE_BIB = BIB_DIR / "conference.bib"

# Journals that get high-impact emphasis in the primary CV (\hijournal).
# The .bib ALSO encodes emphasis by wrapping the journal name in \textbf{...};
# we treat either signal as high-impact.
HIGH_IMPACT_JOURNALS: set[str] = {
    "Nature", "Nature Methods", "Nature Immunology", "Nature Biotechnology",
    "Nature Genetics", "Nature Communications", "Cell", "Cell Systems",
    "Cell Genomics", "Science",
}

PREPRINT_PUBLISHERS: set[str] = {"openrxiv", "biorxiv", "medrxiv", "arxiv", "research square"}


@dataclass
class Pub:
    key: str
    source: str                 # "journal" | "conference"
    entrytype: str
    title: str
    authors: list[str]          # cleaned display names, in order
    andrea_index: int           # position of Andrea in authors, -1 if absent
    n_authors: int
    position: str               # "sole" | "first" | "last" | "middle" | "unknown"
    is_first: bool              # first or co-first author
    is_last: bool               # last/senior or co-last author
    shared: bool                # co-first / co-last (asterisk marker)
    year: int | None
    year_raw: str
    status: str                 # "published" | "in_press" | "submitted"
    venue: str                  # clean journal/publisher name shown to reader
    high_impact: bool
    doi: str
    url: str
    volume: str = ""
    pages: str = ""
    month: str = ""
    contribution: str = ""      # from the note field, "Contribution: ..." stripped
    extra: dict = field(default_factory=dict)


# ---- LaTeX / string cleaning ----------------------------------------------
def strip_latex(s: str) -> str:
    """Reduce a .bib field to clean plain text.

    Handles the markup these Overleaf-flavored files actually use: \\href{url}{txt}
    -> txt, \\textcolor{c}{txt} / \\myul[opt]{txt} -> txt, \\color{c} dropped, font
    wrappers (\\textbf/\\textit/...) unwrapped even when nested, stray command
    tokens (\\faGithub, ...) dropped, then braces removed and escapes unescaped.
    """
    if not s:
        return ""
    s = s.replace("\n", " ")
    # Resolve inner macros before outer ones (the href link text itself contains
    # \color/\myul), iterating until stable.
    for _ in range(6):
        prev = s
        s = re.sub(r"\\color\s*\{[^{}]*\}", "", s)
        s = re.sub(r"\\myul\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\textcolor\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1", s)
        s = re.sub(r"\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1", s)
        if s == prev:
            break
    s = re.sub(r"\\(?:textbf|textit|emph|text|mathbf|textsc|textrm)\b", "", s)
    s = re.sub(r"\\[a-zA-Z]+\b", "", s)          # drop remaining command tokens
    s = re.sub(r"\[[a-z]+\]", "", s)             # drop leftover [teal]-style options
    s = s.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_").replace("\\$", "$")
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_field(entry: dict, name: str) -> str:
    return strip_latex(entry.get(name, "") or "")


def _raw_field(entry: dict, name: str) -> str:
    return (entry.get(name, "") or "").strip()


# ---- Author parsing --------------------------------------------------------
def split_authors(raw: str) -> list[str]:
    """Split a BibTeX author field on ' and ' at brace level 0.

    Whitespace is collapsed first so newline-delimited entries (`... \\nand ...`)
    split the same as space-delimited ones.
    """
    raw = re.sub(r"\s+", " ", raw).strip()
    tokens, depth, cur = [], 0, ""
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if depth == 0 and raw[i:i + 5].lower() == " and ":
            tokens.append(cur.strip())
            cur = ""
            i += 5
            continue
        cur += c
        i += 1
    if cur.strip():
        tokens.append(cur.strip())
    return tokens


def find_andrea_index(raw_authors: list[str]) -> int:
    """Andrea is the only \\textbf-bolded author in these files; fall back to a
    Guarracino+Andrea text match."""
    for i, a in enumerate(raw_authors):
        if "\\textbf" in a and "uarracino" in a:
            return i
    for i, a in enumerate(raw_authors):
        if "uarracino" in a and "ndrea" in a:
            return i
    return -1


def analyze_authorship(raw_authors: list[str], idx: int) -> tuple[str, bool, bool, bool]:
    """Return (position, is_first, is_last, shared) from the asterisk convention.

    The .bib marks co-first / co-last authors with a trailing '*'. So:
      - leading contiguous starred authors form the co-first block;
      - trailing contiguous starred authors form the co-last block.
    Andrea is a first author if he leads (idx 0) or sits in the co-first block
    (e.g. Relative Information Gain: he is 3rd of three starred co-first authors).
    He is a last/senior author if he sits in the co-last block, or is the final
    author of a paper with >2 authors (excludes 2-author papers where he is
    simply the second author, e.g. seqwish/Garrison & Guarracino).
    """
    n = len(raw_authors)
    if idx < 0 or n == 0:
        return "unknown", False, False, False
    # Author's own convention (marker on his name): a single '*' = (co-)first
    # author, '**' = last / senior author. A sole first author with no marker
    # (position 0) still counts as first.
    stars = raw_authors[idx].count("*")
    is_last = stars >= 2
    is_first = (not is_last) and (stars == 1 or idx == 0)
    others_starred = any("*" in a for j, a in enumerate(raw_authors) if j != idx)
    shared = (is_first or is_last) and others_starred
    if n == 1:
        position = "sole"
    elif is_first:
        position = "first"
    elif is_last:
        position = "last"
    else:
        position = "middle"
    return position, is_first, is_last, shared


# ---- Year / status ---------------------------------------------------------
def parse_year_status(year_raw: str) -> tuple[int | None, str]:
    y = year_raw.strip()
    low = y.lower()
    if "submitted" in low:
        return None, "submitted"
    if "in press" in low or "in-press" in low or "accepted" in low:
        return None, "in_press"
    m = re.search(r"(\d{4})", y)
    if m:
        return int(m.group(1)), "published"
    return None, "published"


# ---- Venue -----------------------------------------------------------------
def parse_venue(entry: dict, status: str) -> tuple[str, bool, str]:
    """Return (display_venue, high_impact, publisher_clean)."""
    journal_raw = _raw_field(entry, "journal")
    publisher = clean_field(entry, "publisher")
    # high-impact if the .bib bolded the journal, or it's in our set
    bolded = "\\textbf" in journal_raw
    journal = strip_latex(journal_raw)
    high = bolded or journal in HIGH_IMPACT_JOURNALS
    if journal:
        return journal, high, publisher
    # preprint / no journal: fall back to publisher
    return publisher or "Preprint", False, publisher


# ---- Contribution note -----------------------------------------------------
def parse_contribution(entry: dict) -> str:
    note = clean_field(entry, "note")
    if not note:
        return ""
    m = re.search(r"contribution:\s*(.*)", note, flags=re.IGNORECASE)
    return (m.group(1) if m else note).strip().rstrip(".")


def parse_cvlinks(entry: dict) -> list[tuple[str, str]]:
    """Optional supplementary links, from a custom `cvlinks` field formatted as
    `Label=URL; Label=URL` (e.g. a paper's web server / code repository). Returns
    [(label, url), ...]. Rendered next to the paper link on the website."""
    raw = _raw_field(entry, "cvlinks")
    out: list[tuple[str, str]] = []
    for part in raw.split(";"):
        if "=" in part:
            label, url = part.split("=", 1)
            if label.strip() and url.strip():
                out.append((label.strip(), url.strip()))
    return out


# ---- Main entry point ------------------------------------------------------
def _load(path: Path) -> list[dict]:
    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    text = path.read_text()
    # The .bib uses bare full-word months (`month = July`) which aren't standard
    # BibTeX string macros; brace them so they parse as literal strings instead of
    # raising UndefinedString('july').
    text = re.sub(
        r"(?im)^(\s*month\s*=\s*)([A-Za-z]+)(\s*,?\s*)$", r"\1{\2}\3", text
    )
    db = bibtexparser.loads(text, parser=parser)
    logger.info("loaded %s: %d entries", path.name, len(db.entries))
    return db.entries


def parse_all() -> list[Pub]:
    pubs: list[Pub] = []
    for path, source in [(JOURNAL_BIB, "journal"), (CONFERENCE_BIB, "conference")]:
        for e in _load(path):
            raw_authors = split_authors(_raw_field(e, "author"))
            idx = find_andrea_index(raw_authors)
            position, is_first, is_last, shared = analyze_authorship(raw_authors, idx)
            authors = [strip_latex(a) for a in raw_authors]
            year, status = parse_year_status(_raw_field(e, "year"))
            venue, high, publisher = parse_venue(e, status)
            pub = Pub(
                key=e.get("ID", "?"),
                source=source,
                entrytype=e.get("ENTRYTYPE", "article"),
                title=clean_field(e, "title"),
                authors=authors,
                andrea_index=idx,
                n_authors=len(authors),
                position=position,
                is_first=is_first,
                is_last=is_last,
                shared=shared,
                year=year,
                year_raw=_raw_field(e, "year"),
                status=status,
                venue=venue,
                high_impact=high,
                doi=clean_field(e, "doi"),
                url=clean_field(e, "url"),
                volume=clean_field(e, "volume"),
                pages=clean_field(e, "pages"),
                month=clean_field(e, "month"),
                contribution=parse_contribution(e),
                extra={"publisher": publisher, "issn": clean_field(e, "issn"),
                       "cvlinks": parse_cvlinks(e)},
            )
            if idx < 0:
                logger.warning("Andrea not found in authors of %s: %r", pub.key, authors[:3])
            pubs.append(pub)
    logger.info("parsed %d publications total", len(pubs))
    return pubs


def sort_key(p: Pub):
    """Newest first; submitted/in-press float above published; within a year keep
    a stable order by DOI so runs are reproducible."""
    status_rank = {"submitted": 3, "in_press": 2, "published": 1}.get(p.status, 0)
    y = p.year if p.year is not None else 9999  # unknown-year (preprints) on top
    return (y, status_rank, p.doi or p.key)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    pubs = sorted(parse_all(), key=sort_key, reverse=True)

    # Human-readable validation summary
    n_first = sum(1 for p in pubs if p.is_first)
    n_last = sum(1 for p in pubs if p.is_last)
    n_fl = sum(1 for p in pubs if p.is_first or p.is_last)
    n_sub = sum(1 for p in pubs if p.status == "submitted")
    n_press = sum(1 for p in pubs if p.status == "in_press")
    n_pub = sum(1 for p in pubs if p.status == "published")
    print(f"\n{'='*100}")
    print(f"TOTAL {len(pubs)}  |  published {n_pub}  in-press {n_press}  submitted {n_sub}")
    print(f"first/sole {n_first}  last {n_last}  first-or-last {n_fl}")
    print(f"{'='*100}")
    print(f"{'YEAR':6}{'STAT':10}{'POS':7}{'HI':3}{'VENUE':22} TITLE")
    for p in pubs:
        yr = str(p.year) if p.year else p.status[:4]
        pos = ("*" if p.shared else " ") + p.position[:5]
        hi = "HI" if p.high_impact else "  "
        print(f"{yr:6}{p.status:10}{pos:7}{hi:3}{p.venue[:22]:22} {p.title[:60]}")

    print(f"\n--- classified FIRST-or-LAST author ({n_fl}) ---")
    for p in pubs:
        if p.is_first or p.is_last:
            role = "first" if p.is_first else "last"
            role += "/shared" if p.shared else ""
            print(f"  [{role:13}] {p.venue[:20]:20} {p.title[:55]}")
    absent = [p.key for p in pubs if p.andrea_index < 0]
    if absent:
        print(f"\n!! Andrea not detected in: {absent}")

    out = CVGEN_DIR / "pubs.debug.json"
    out.write_text(json.dumps([dataclasses.asdict(p) for p in pubs], indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
