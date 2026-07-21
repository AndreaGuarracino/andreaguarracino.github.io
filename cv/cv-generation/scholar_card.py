#!/usr/bin/env python3
"""Fetch live Google Scholar metrics and render the "Cited by" card used on the
primary CV (cv-primary/AndreaGuarracinoGoogleScholar.png). Also syncs the
citation-count text (h-index/i10-index live in the card image) in cv_current.tex.

Run: python cv/cv-generation/scholar_card.py   (needs network + matplotlib)

Scholar is fetchable server-side (no login), so this replaces the manual
screenshot. If Scholar ever serves a captcha it exits with a clear message.
"""
from __future__ import annotations

import datetime
import math
import re
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Match Google Scholar's typeface (Arial; Liberation Sans is metric-compatible).
matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"]

SCHOLAR_URL = "https://scholar.google.com/citations?user=zABbjIoAAAAJ&hl=en"
CVGEN = Path(__file__).resolve().parent
CV_PRIMARY = CVGEN.parent / "cv-primary"
PNG = CV_PRIMARY / "AndreaGuarracinoGoogleScholar.png"
CV_TEX = CV_PRIMARY / "cv_current.tex"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch() -> tuple[dict, list[int], list[int]]:
    req = urllib.request.Request(SCHOLAR_URL, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    if re.search(r"captcha|unusual traffic", html, re.I):
        raise SystemExit("Scholar returned a captcha/block; retry later or grab the screenshot manually.")
    v = [int(x) for x in re.findall(r'gsc_rsb_std">(\d+)</td>', html)]
    metrics = {"Citations": (v[0], v[1]), "h-index": (v[2], v[3]), "i10-index": (v[4], v[5])}
    years = [int(y) for y in re.findall(r'gsc_g_t[^>]*>(\d{4})<', html)]
    counts = [int(c) for c in re.findall(r'gsc_g_al">(\d+)<', html)]
    # Scholar omits leading zero-count bars; right-align counts to years.
    if len(counts) > len(years):
        counts = counts[-len(years):]
    elif len(counts) < len(years):
        counts = [0] * (len(years) - len(counts)) + counts
    return metrics, years, counts


def render(metrics: dict, years: list[int], counts: list[int]) -> None:
    dark, grey, grid, line = "#222222", "#777777", "#e9e9e9", "#d9d9d9"
    bar = "#777777"                      # Scholar's grey bars
    x_all, x_since = 0.60, 1.00          # right-aligned column positions
    fig = plt.figure(figsize=(5.6, 6.1), dpi=210)
    fig.patch.set_facecolor("white")

    # --- Cited by table ---
    ax = fig.add_axes([0.05, 0.63, 0.92, 0.34])
    ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.text(0.0, 1.0, "Cited by", color="#3c3c3c", fontsize=23, va="top")
    ax.text(x_all, 0.74, "All", color=dark, fontsize=20, ha="right")
    ax.text(x_since, 0.74, "Since 2021", color=dark, fontsize=20, ha="right")
    ax.plot([0, 1], [0.66, 0.66], color=line, lw=1.1)
    for i, (name, (a, s)) in enumerate(metrics.items()):
        y = 0.50 - i * 0.16
        ax.text(0.0, y, name, color=dark, fontsize=20, va="center")
        ax.text(x_all, y, str(a), color=dark, fontsize=20, ha="right", va="center")
        ax.text(x_since, y, str(s), color=dark, fontsize=20, ha="right", va="center")

    # --- per-year bar chart (grey bars, right y-axis, gridlines) ---
    axb = fig.add_axes([0.04, 0.08, 0.82, 0.46])
    peak = max(counts) if counts else 1
    top = math.ceil(peak / 100.0) * 100 or 100
    ticks = [round(top * k / 4) for k in range(5)]
    for gy in ticks:
        axb.axhline(gy, color=grid, lw=1.1, zorder=0)
    axb.bar(range(len(years)), counts, color=bar, width=0.55, zorder=2)
    axb.set_ylim(0, top); axb.set_xlim(-0.7, len(years) - 0.3)
    for sp in axb.spines.values():
        sp.set_visible(False)
    axb.yaxis.tick_right()
    axb.set_yticks(ticks)
    axb.set_yticklabels([str(t) for t in ticks], color=grey, fontsize=20)
    axb.set_xticks(range(len(years)))
    axb.set_xticklabels([str(y) for y in years], color=grey, fontsize=20)
    axb.tick_params(length=0)
    axb.tick_params(axis="x", pad=9)   # a little gap between bars and year labels

    fig.savefig(PNG, facecolor="white")
    plt.close(fig)


def sync_text(metrics: dict) -> None:
    t = CV_TEX.read_text()
    when = datetime.date.today().strftime("%B %Y")
    cit = metrics["Citations"][0]
    t, n = re.subn(r"(Google Scholar & Citations )\d+ \([^)]*\)",
                   rf"\g<1>{cit} ({when})", t)
    if n != 1:
        raise RuntimeError(f"cv_current.tex Scholar citation patch failed (n={n})")
    CV_TEX.write_text(t)


def main() -> int:
    metrics, years, counts = fetch()
    render(metrics, years, counts)
    sync_text(metrics)
    print(f"Scholar card -> {PNG.name}: {metrics['Citations'][0]} citations, "
          f"h={metrics['h-index'][0]}, i10={metrics['i10-index'][0]}; "
          f"{dict(zip(years, counts))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
