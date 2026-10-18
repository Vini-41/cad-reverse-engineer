"""Source documents: hashing, text extraction, figure extraction and quote matching."""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NamedTuple

from . import units

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_TIMES = dict.fromkeys(map(ord, "×✕✖⨯"), "x")
# The numbers naming figures, tables, equations or sections ("Fig. S2", "Eqs. (3)-(4)",
# "Sec. 4.2", "Figs. 2 and 3"). Abbreviations other than "fig" need their period, so "2 sec"
# stays a value, and a number followed by a unit ("section 4 mm thick") is a value; "in" and
# the inch mark are left out there, so "Fig. 2 in" stays a label.
_UNIT = units.spelling()
# A number as printed: 3.5, or a fraction before a unit (1/4 inch, 1 1/2 in; a bare 1/50 is two).
_NUMBER = re.compile(rf"-?(?:\d+\s)?\d+/[1-9]\d*(?=\s?{_UNIT})|-?\d+(?:\.\d+)?")
# A decimal comma (3,5) joins its digits into one number; the comma of a thousands figure
# (1,250) or of a list (1,5,10) does not.
_DECIMAL_COMMA = re.compile(r"(?<![\d,])(\d+),(?!\d{3}(?!\d))(\d+)(?![\d,])")
_NOT_INCHES = units.spelling(but=(units.INCH_IN, '"', "′′"))
_LABEL_NUMBER = rf"\(?s?\d+(?:\.\d+)*(?![\d.])[a-z]?\)?(?!\s*{_NOT_INCHES})"
_LABEL = re.compile(
    r"(?:\b(?:(?:fig(?:ure)?|table|equation|section)s?\.?|(?:tab|eq|sec|sect)s?\.)|§)\s*"
    rf"({_LABEL_NUMBER}(?:\s*(?:,|-|and|&|to)\s*{_LABEL_NUMBER})*)"
)
# The dash of a range ("5-10", "5 mm - 10 mm"), which separates two values rather than negating one.
_RANGE_DASH = re.compile(rf"(?<=\d)(\s*(?:{_UNIT}\s*)?)-(?=\s*\d)")
# What joins a number to the next one it shares a unit with: "5-10 mm", "40x8x5 mm", "1,5,10 mm",
# "-10 to -5 deg".
_SHARES_UNIT = re.compile(r"\s*-\s*|x|,|\s+to\s+")


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


class _Token(NamedTuple):
    value: float
    start: int
    end: int  # after the number, or after its unit when one is printed
    unit: str | None
    joined: bool  # shares its unit with the next token, as 5 does in "5-10 mm"
    labelled: bool  # numbers a figure, table, equation or section


def _value(printed: str) -> float:
    *whole, last = printed.split()
    over, _, under = last.partition("/")
    value = float(over) / float(under) if under else float(over)
    return float(whole[0]) + value if whole else value


def _tokens(text: str) -> list[_Token]:
    """Every number in normalized text with the unit printed after it. The numbers of a range,
    product or list share its last unit."""
    label_spans = [m.span(1) for m in _LABEL.finditer(text)]
    scanned = _DECIMAL_COMMA.sub(
        r"\1.\2", _RANGE_DASH.sub(r"\1 ", text.replace("x", " "))
    )  # same length
    found: list[
        tuple[re.Match[str], str | None, int]
    ] = []  # each number, its unit, and where both end
    for m in _NUMBER.finditer(scanned):
        if found and m.start() < found[-1][2]:
            continue  # a digit of the unit before it: the 3 of g/cm3
        unit, end = units.unit_at(text, m.end()) or (None, m.end())
        found.append((m, unit, end))
    tokens: list[_Token] = []
    for i in reversed(range(len(found))):
        m, unit, end = found[i]
        joined = (
            unit is None
            and i + 1 < len(found)
            and _SHARES_UNIT.fullmatch(text, m.end(), found[i + 1][0].start()) is not None
        )
        if joined:
            unit = tokens[0].unit
        tokens.insert(
            0,
            _Token(
                _value(m.group()),
                m.start(),
                end,
                unit,
                joined,
                any(a <= m.start() < b for a, b in label_spans),
            ),
        )
    return tokens


def quantities_in(text: str) -> list[tuple[float, str | None]]:
    """The values a quote states, each with the unit printed after it (None if none):
    whole numeric tokens, both endpoints of a range as positive values, and no number that labels
    a figure, table, equation or section. The numbers of a range or product share its last unit."""
    return [(t.value, t.unit) for t in _tokens(normalize(text)) if not t.labelled]


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


def pages(path: Path) -> tuple[str, ...]:
    """Text of each page. DOCX, TXT and MD are one page."""
    return _pages(path, sha256(path))


@cache
def _pages(path: Path, digest: str) -> tuple[str, ...]:
    """pages(path), cached by its content: a source rewritten in place is read afresh."""
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
                name = f"p{n:03d}_{i:02d}{Path(image.name).suffix or '.png'}"
                written.append(_write_viewable(out / name, image.data))
    elif path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.startswith("word/media/"):
                    written.append(_write_viewable(out / Path(name).name, z.read(name)))
    return written


VIEWABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}  # formats an image viewer shows as they are


def _write_viewable(target: Path, data: bytes) -> Path:
    """Write an extracted image to target, or as PNG beside it when a viewer cannot show its
    format (TIFF, BMP) and Pillow can read it; return the path written."""
    if target.suffix.lower() not in VIEWABLE:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(io.BytesIO(data)) as image:
                png = target.with_suffix(".png")
                image.save(png, format="PNG")
                return png
        except (UnidentifiedImageError, OSError, ValueError):
            pass  # a format Pillow cannot read (EMF, WMF) is kept as extracted
    target.write_bytes(data)
    return target


# Thread and fastener sizes (M3, M2.5x0.45): stated sizes the unit table cannot read.
_THREAD = re.compile(r"(?<![a-z0-9.])m\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?(?![a-z0-9])")


def stated_quantities(text: str) -> list[tuple[int, int, str]]:
    """Spans in normalized text that state a quantity: a number the quote reader would read with
    a unit (a whole range such as 3-5 mm), an a×b×c product, or a thread size; never digits
    inside a name or a figure, table, equation or section number.

    It errs towards listing: a unit glued to a number is a candidate even where it is part of a
    name (1990s, 4G), because extracted text glues real ones too (t=0s, 20g), and a false
    candidate costs one skip where a missed one leaves a quantity unledgered."""
    spans, group = [], []
    for t in _tokens(text):
        group.append(t)
        if t.joined:
            continue
        product = len(group) > 1 and all(
            text[a.end : b.start] == "x" for a, b in zip(group, group[1:])
        )
        glued = group[0].start > 0 and text[group[0].start - 1].isalnum()  # in a name: ada2cc, L14
        if (t.unit or product) and not glued and not any(g.labelled for g in group):
            spans.append((group[0].start, t.end))
        group = []
    spans += [m.span() for m in _THREAD.finditer(text)]
    whole = [
        (a, b)
        for a, b in spans
        if not any(c <= a and b <= d and (c, d) != (a, b) for c, d in spans)
    ]
    return [(a, b, text[a:b]) for a, b in sorted(set(whole))]
