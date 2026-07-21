#!/usr/bin/env python3
"""Render the primary CV LaTeX publication lists from the canonical .bib.

Outputs (both \\input by cv/cv-primary/cv_current.tex):
  includes/publications.tex          -- peer-reviewed (published + in press), newest first
  includes/future_publications.tex   -- preprints under review ("Publications in pipeline")

Also patches the header counts in cv_current.tex:
  "{\\bf N} peer reviewed + {\\bf P} preprints = {\\bf T} total"
  "{\\bf M} first or last author"  -> M = first/last over ALL pubs, from the
                                      .bib asterisk convention (* first, ** last)

Author names are rendered PubMed-style ("Surname II") to match the existing CV
look; PMID/PMCID come from a live "Andrea Guarracino[au]" PubMed search plus
direct DOI lookups (cached in pubmed_cache.json, skipped with --no-network).

This REPLACES the old pubmedSearch2tex.py CSV pipeline. Run via build.sh.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_bib as pb  # noqa: E402

logger = logging.getLogger("cvgen.render_cvtex")

CVGEN_DIR = Path(__file__).resolve().parent
CV_DIR = CVGEN_DIR.parent / "cv-primary"   # the primary CV (cv_current.tex, includes/)
INCLUDES_DIR = CV_DIR / "includes"
CV_TEX = CV_DIR / "cv_current.tex"
PUBMED_CACHE = CVGEN_DIR / "pubmed_cache.json"
PUBMED_AUTHOR_TERM = "Andrea Guarracino[au]"
# NCBI throttles anonymous requests harder; identify ourselves and self-rate-limit.
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
EUTILS_ID = {"tool": "cvgen", "email": "aguarracino@tgen.org"}
EUTILS_TIMEOUT = 15


def _eutils(endpoint: str, params: dict) -> dict:
    time.sleep(0.34)  # stay under NCBI's 3 requests/sec anonymous limit
    q = urllib.parse.urlencode({**params, **EUTILS_ID, "retmode": "json"})
    with urllib.request.urlopen(f"{EUTILS}{endpoint}?{q}", timeout=EUTILS_TIMEOUT) as r:
        return json.loads(r.read())

GROUP_AUTHOR_KEYWORDS = ("consortium", "project", "group", "team", "network",
                         "initiative", "bank", "collective")


def latex_escape(s: str) -> str:
    """Escape LaTeX specials in plain text pulled from the .bib (parse_bib already
    stripped LaTeX markup, so no real commands survive to protect)."""
    for a, b in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"),
                 ("$", "\\$"), ("#", "\\#"), ("_", "\\_"),
                 ("{", "\\{"), ("}", "\\}"),
                 ("~", "\\textasciitilde{}"), ("^", "\\textasciicircum{}")):
        s = s.replace(a, b)
    return s


# ---- Author name -> "Surname II" ------------------------------------------
def is_group_author(token: str) -> bool:
    low = token.lower()
    return any(kw in low for kw in GROUP_AUTHOR_KEYWORDS)


def surname_initials(token: str) -> str:
    """'Gomes de Lima*, Leonardo' -> 'Gomes de Lima L*'; 'Andrea Guarracino' ->
    'Guarracino A'. Group/consortium authors are passed through verbatim. A
    trailing shared-authorship '*' is preserved."""
    token = token.strip()
    # The shared-authorship '*' may sit on the surname in comma form
    # ('Gomes de Lima*, Leonardo'); pull it off and re-append after the initials.
    star = "*" * min(token.count("*"), 2)   # preserve * (first) / ** (last)
    token = token.replace("*", "").strip()
    if not token:
        return ""
    if is_group_author(token):
        return token + star
    if "," in token:
        surname, given = token.split(",", 1)
    else:
        parts = token.split()
        if len(parts) == 1:
            return parts[0] + star
        surname, given = parts[-1], " ".join(parts[:-1])
    initials = "".join(
        w[0].upper() for w in re.split(r"[ \-]+", given.strip()) if w[:1].isalpha()
    )
    return f"{surname.strip()} {initials}".strip() + star


def format_authors_cv(pub: pb.Pub) -> str:
    """Bold Andrea and truncate the list the way the existing CV does:
    Andrea within first 8 -> up to 8 names then 'et al.'; deeper -> first 3,
    '...', Andrea (+ 'et al.' unless he is last)."""
    names = [latex_escape(surname_initials(a)) for a in pub.authors]
    pos = pub.andrea_index
    if pos < 0:
        return ", ".join(names)
    names[pos] = "\\textbf{" + names[pos] + "}"
    n = len(names)
    if pos < 8:
        if n > 8:
            return ", ".join(names[:8]) + " \\emph{et al.}"
        if n == 2:
            return " and ".join(names)
        return ", ".join(names)
    head = ", ".join(names[:3])
    if pos == n - 1:
        return f"{head}, ..., {names[pos]}"
    return f"{head}, ..., {names[pos]} \\emph{{et al.}}"


# ---- PubMed 'Andrea Guarracino[au]' index -----------------------------------
def pubmed_author_map(use_network: bool = True) -> dict:
    """Return {doi_lower: {'pmid','pmcid'}} for every record in the live PubMed
    search 'Andrea Guarracino[au]'. This IS the authoritative "indexed on PubMed"
    set: a .bib paper counts as on-PubMed iff its DOI is a key here. Also gives
    accurate PMID/PMCID for rendering (esummary covers non-PMC papers, which the
    old PMC ID Converter missed). Cached in pubmed_cache.json."""
    cached = json.loads(PUBMED_CACHE.read_text()) if PUBMED_CACHE.exists() else None
    if not use_network:
        return cached or {}
    try:
        ids = _eutils("esearch.fcgi", {"db": "pubmed", "term": PUBMED_AUTHOR_TERM,
                                       "retmax": "400"})["esearchresult"]["idlist"]
        logger.info("PubMed esearch %r -> %d records", PUBMED_AUTHOR_TERM, len(ids))
        out: dict = {}
        for i in range(0, len(ids), 200):
            batch = ids[i:i + 200]
            res = _eutils("esummary.fcgi", {"db": "pubmed", "id": ",".join(batch)})["result"]
            for pmid in batch:
                doc = res.get(pmid, {})
                doi = pmcid = ""
                for aid in doc.get("articleids", []):
                    if aid.get("idtype") == "doi":
                        doi = aid.get("value", "")
                    elif aid.get("idtype") == "pmc":
                        pmcid = aid.get("value", "")
                if doi:
                    out[doi.lower()] = {"pmid": pmid, "pmcid": pmcid}
        # merge into any prior cache so direct-DOI resolutions (added by
        # augment_pubmed_map) persist across network refreshes
        merged = {**(cached or {}), **out}
        PUBMED_CACHE.write_text(json.dumps(merged, indent=2, sort_keys=True))
        logger.info("PubMed map: %d from author search, %d total cached", len(out), len(merged))
        return merged
    except Exception as exc:  # network failure -> fall back to cache, don't crash
        logger.warning("PubMed fetch failed (%s); using cache", exc)
        return cached or {}


def augment_pubmed_map(pmmap: dict, dois: list[str], use_network: bool = True) -> dict:
    """Some of his papers are indexed on PubMed under "Guarracino A" (initials) and
    so are missed by the full-name author search. Resolve those by a direct DOI
    lookup so the "indexed on PubMed" count/PMIDs are complete. Merges into pmmap."""
    todo = sorted({d.lower() for d in dois if d and d.lower() not in pmmap})
    if not todo or not use_network:
        return pmmap
    for doi in todo:
        try:
            idlist = _eutils("esearch.fcgi", {"db": "pubmed", "term": f"{doi}[AID]"}
                             )["esearchresult"]["idlist"]
            if not idlist:
                logger.info("not on PubMed: %s", doi)
                continue
            pmid = idlist[0]
            doc = _eutils("esummary.fcgi", {"db": "pubmed", "id": pmid})["result"].get(pmid, {})
            pmcid = next((a.get("value", "") for a in doc.get("articleids", [])
                          if a.get("idtype") == "pmc"), "")
            pmmap[doi] = {"pmid": pmid, "pmcid": pmcid}
            logger.info("direct DOI->PMID: %s -> %s", doi, pmid)
        except Exception as exc:
            logger.warning("direct DOI lookup failed for %s (%s)", doi, exc)
    PUBMED_CACHE.write_text(json.dumps(pmmap, indent=2, sort_keys=True))
    return pmmap


# ---- Per-item LaTeX --------------------------------------------------------
def year_field(pub: pb.Pub) -> str:
    if pub.status == "submitted":
        return "Submitted"
    if pub.status == "in_press":
        return "In press"
    return str(pub.year) if pub.year else ""


def format_item(pub: pb.Pub, cache: dict) -> str:
    authors = format_authors_cv(pub)
    year = f"\\pyear{{{year_field(pub)}}}"
    title = f"\\ptitle{{{latex_escape(pub.title)}}}"
    macro = "\\hijournal" if pub.high_impact else "\\journal"
    venue = pub.venue
    if pub.status == "in_press":  # avoid "(In press) ... Cell (in press)"
        venue = re.sub(r"\s*\(in press\)\s*$", "", venue, flags=re.IGNORECASE)
    journal = f"{macro}{{{latex_escape(venue)}}}"
    vol = f"\\pvolume{{{pub.volume}}}" if pub.volume else ""
    # some entries carry a link (e.g. conference "Abstract") instead of page numbers
    pages = f"\\pages{{{latex_escape(pub.pages)}}}" if re.search(r"\d", pub.pages) else ""

    ids = cache.get(pub.doi.lower(), {}) if pub.doi else {}
    refs: list[str] = []
    if ids.get("pmcid"):
        refs.append(f"\\pmcid{{{ids['pmcid']}}}")
    if ids.get("pmid"):
        refs.append(f"\\pmid{{{ids['pmid']}}}")
    if pub.doi:
        # allow the (long) displayed DOI to wrap at '/' and '.' so it doesn't
        # overflow the right margin; the href URL stays intact for the link.
        doi_disp = pub.doi.replace("/", "/\\allowbreak{}").replace(".", ".\\allowbreak{}")
        refs.append(f"\\doi{{{doi_disp}}}~\\href{{https://doi.org/{pub.doi}}}{{\\ding{{234}}}}")
    refs_str = "\\prefs{" + ", ".join(refs) + "}" if refs else ""

    return f"\\item {authors}{year}{title}. \\ {journal} {vol}{pages} \\ {refs_str}\n"


def render_list(pubs: list[pb.Pub], cache: dict) -> str:
    body = "".join(format_item(p, cache) for p in pubs)
    return "\\begin{enumerate}\n" + body + "\\end{enumerate}\n"


# ---- Header patching -------------------------------------------------------
def patch_header(n_reviewed: int, n_preprints: int, first_last: int) -> None:
    total = n_reviewed + n_preprints
    text = CV_TEX.read_text()
    fields = [
        (r"peer reviewed \+", n_reviewed),      # "{\bf 41} peer reviewed +"
        (r"preprints", n_preprints),            # "{\bf 11} preprints"
        (r"total", total),                      # "{\bf 52} total"
        (r"first or last", first_last),         # "{\bf 10} first or last"
    ]
    for ctx, val in fields:
        text, n = re.subn(r"{\\bf\s+\d+}(\s+" + ctx + ")", r"{\\bf " + str(val) + r"}\g<1>", text)
        if n != 1:
            raise RuntimeError(f"header patch failed for {ctx!r} (n={n})")
    CV_TEX.write_text(text)
    logger.info("patched header: reviewed=%d preprints=%d total=%d first/last=%d",
                n_reviewed, n_preprints, total, first_last)


def main(use_network: bool = True) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    pubs = sorted(pb.parse_all(), key=pb.sort_key, reverse=True)

    # conference abstracts/posters (conference.bib) are NOT peer-reviewed papers:
    # exclude them from the primary CV list + header count so it matches the website
    # table (which renders journal pubs only).
    journal_pubs = [p for p in pubs if p.source != "conference"]
    reviewed = [p for p in journal_pubs if p.status in ("published", "in_press")]
    preprints = [p for p in journal_pubs if p.status == "submitted"]

    pmmap = pubmed_author_map(use_network=use_network)
    pmmap = augment_pubmed_map(pmmap, [p.doi for p in reviewed], use_network=use_network)

    INCLUDES_DIR.mkdir(exist_ok=True)
    (INCLUDES_DIR / "publications.tex").write_text(render_list(reviewed, pmmap))
    (INCLUDES_DIR / "future_publications.tex").write_text(render_list(preprints, pmmap))

    # first-or-last-author count is derived from the .bib asterisk convention
    # (single * = (co-)first, ** = last/senior), over ALL publications.
    first_last = sum(1 for p in journal_pubs if p.is_first or p.is_last)
    patch_header(len(reviewed), len(preprints), first_last)

    on_pubmed = [p for p in reviewed if p.doi and p.doi.lower() in pmmap]
    print(f"reviewed={len(reviewed)}  preprints={len(preprints)}  total={len(journal_pubs)}  "
          f"first/last(all, from *//**)={first_last}  indexed_on_pubmed={len(on_pubmed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(use_network="--no-network" not in sys.argv))
