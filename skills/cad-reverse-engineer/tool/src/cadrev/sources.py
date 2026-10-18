"""Source documents: hashing, text extraction, figure extraction and quote matching."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import units

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_TIMES = dict.fromkeys(map(ord, "×✕✖⨯"), "x")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
# The numbers naming figures, tables, equations or sections ("Fig. S2", "Eqs. (3)-(4)",
# "Sec. 4.2", "Figs. 2 and 3"). Abbreviations other than "fig" need their period, so "2 sec"
# stays a value, and a number followed by a unit ("section 4 mm thick") is a dimension; "in" and
# the inch mark are left out there, so "Fig. 2 in" stays a label.
_UNIT = units.spelling()
_LABEL_NUMBER = rf"\(?s?\d+(?:\.\d+)*(?![\d.])[a-z]?\)?(?!\s*{units.spelling(but=(units.INCH_IN, '"', '′′'))})"
_LABEL = re.compile(r"(?:\b(?:(?:fig(?:ure)?|table|equation|section)s?\.?|(?:tab|eq|sec|sect)s?\.)|§)\s*"
                    rf"({_LABEL_NUMBER}(?:\s*(?:,|-|and|&|to)\s*{_LABEL_NUMBER})*)")
# The dash of a range ("5-10", "5 mm - 10 mm"), which separates two values rather than negating one.
_RANGE_DASH = re.compile(rf"(?<=\d)(\s*(?:{_UNIT}\s*)?)-(?=\s*\d)")
# What joins a number to the next one it shares a unit with: "5-10 mm", "40x8x5 mm", "-10 to -5 deg".
_SHARES_UNIT = re.compile(r"\s*-\s*|x|\s+to\s+")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(text: str) -> str:
    """Canonical form for matching: NFKC, unified dashes and multiplication signs,
    re-joined hyphenated line breaks, single spaces, lower case."""
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_TIMES)
    text = text.replace("­", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return re.sub(r"(\d)\s*x\s*(?=\d)", r"\1x", text)


def squash(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def quantities_in(text: str) -> list[tuple[float, str | None]]:
    """The dimension candidates of a quote, each with the unit printed after it (None if none):
    whole numeric tokens, both endpoints of a range as positive values, and no number that labels
    a figure, table, equation or section. The numbers of a range or product share its last unit."""
    text = normalize(text)
    label_spans = [m.span(1) for m in _LABEL.finditer(text)]
    tokens, printed, end = [], [], 0
    for m in _NUMBER.finditer(_RANGE_DASH.sub(r"\1 ", text.replace("x", " "))):  # same length
        if m.start() < end:
            continue  # a digit of the unit before it: the 3 of g/cm3
        unit = units.unit_at(text, m.end())
        tokens.append(m)
        printed.append(unit and unit[0])
        end = unit[1] if unit else m.end()
    for i in reversed(range(len(tokens) - 1)):
        if printed[i] is None and _SHARES_UNIT.fullmatch(text, tokens[i].end(), tokens[i + 1].start()):
            printed[i] = printed[i + 1]
    return [(float(m.group()), unit) for m, unit in zip(tokens, printed)
            if not any(a <= m.start() < b for a, b in label_spans)]


def numbers_in(text: str) -> list[float]:
    """The values of quantities_in(text), without their units."""
    return [value for value, _ in quantities_in(text)]


def _whole(needle: str) -> re.Pattern[str]:
    """needle, refusing to start or end inside a larger number (37 within 137 or 3.7)."""
    head = r"(?<!\d)(?<!\d[.,])" if needle[:1].isdigit() else ""
    tail = r"(?![.,]?\d)" if needle[-1:].isdigit() else ""
    return re.compile(head + re.escape(needle) + tail)


@dataclass(frozen=True)
class Match:
    page: int  # 1-based; 1 for single-page formats
    mode: str  # "exact" (whitespace-normalized) or "squashed" (whitespace ignored)


def _docx_text(path: Path) -> str:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf8")
    paragraphs = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    lines = ("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paragraphs)
    return "\n".join(line for line in lines if line.strip())


@lru_cache(maxsize=None)
def pages(path: Path) -> tuple[str, ...]:
    """Text of each page. DOCX, TXT and MD are one page."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        return tuple(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        return (_docx_text(path),)
    if suffix in {".txt", ".md", ".html", ".htm"}:
        return (path.read_text(encoding="utf8", errors="replace"),)
    raise ValueError(f"unsupported source format: {path.name}")


def find_quote(path: Path, quote: str, page: int | None = None) -> Match | None:
    """Locate a verbatim quote, on the cited page when one is given."""
    texts = pages(path)
    candidates = [page] if page else range(1, len(texts) + 1)
    for mode, fn in (("exact", normalize), ("squashed", squash)):
        needle = fn(quote)
        pattern = _whole(needle)
        for n in candidates:
            if 1 <= n <= len(texts) and needle and pattern.search(fn(texts[n - 1])):
                return Match(n, mode)
    return None


def extract_figures(path: Path, out: Path) -> list[Path]:
    """Write every embedded image to out/, named by page, so figures can be viewed."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        for n, page in enumerate(PdfReader(path).pages, 1):
            for i, image in enumerate(page.images, 1):
                target = out / f"p{n:03d}_{i:02d}{Path(image.name).suffix or '.png'}"
                target.write_bytes(image.data)
                written.append(target)
    elif path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.startswith("word/media/"):
                    target = out / Path(name).name
                    target.write_bytes(z.read(name))
                    written.append(target)
    return written


_CANDIDATE = re.compile(
    r"\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)+"  # products such as 40x8x5
    r"|\d+(?:\.\d+)?\s?(?:mm|cm|µm|μm|m|°|deg|degrees?|g|kg|n|nm|n·m|mah|turns)\b"
    r"|\d+(?:\.\d+)?°"
)


def dimension_candidates(text: str) -> list[tuple[int, int, str]]:
    """Spans in normalized text that look like dimensions, masses or angles."""
    return [(m.start(), m.end(), m.group()) for m in _CANDIDATE.finditer(text)]
