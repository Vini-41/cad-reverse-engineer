"""Source documents: hashing, text extraction, figure extraction and quote matching."""

from __future__ import annotations

import hashlib
import io
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import cache
from html.parser import HTMLParser
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
# A number as printed: 3.5, or a fraction before a unit (1/4 inch, 1 1/2 in, 1/4-in.; a bare 1/50
# is two).
_NUMBER = re.compile(rf"-?(?:\d+\s)?\d+/[1-9]\d*(?={units.UNIT_GAP}{_UNIT})|-?\d+(?:\.\d+)?")
# The cardinals zero to ninety-nine in words, whole: eight is not read inside eighteen or weight,
# nor seven inside seventy. A compound may be hyphenated, spaced, or re-joined across a line break.
_ONES = "zero one two three four five six seven eight nine".split()
_TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_WORD_VALUES: dict[str, int] = {
    word: value
    for words, values in ((_ONES, range(10)), (_TEENS, range(10, 20)), (_TENS, range(20, 100, 10)))
    for word, value in zip(words, values)
}
# Nor is a word read that only begins a larger number, an ordinal or a fraction: twenty-first,
# one hundred, two-thirds.
_WORD_SCALED = (
    r"(?!-?(?:first|second)(?![a-z])|[\s-]?(?:hundred|thousand|million|billion|half|halves|third"
    r"|quarter|fourth|fifth|sixth|seventh|eighth|ninth|tenth)s?(?![a-z]))"
)
_WORD_NUMBER = re.compile(
    rf"(?<![a-z0-9])(?:({'|'.join(_TENS)})(?:-\s?|\s)?({'|'.join(_ONES[1:])})"
    rf"|({'|'.join(sorted(_WORD_VALUES, key=len, reverse=True))}))(?![a-z0-9]){_WORD_SCALED}"
)
# A decimal comma (3,5) joins its digits into one number; the comma of a thousands figure
# (1,250) or of a list (1,5,10) does not.
_DECIMAL_COMMA = re.compile(r"(?<![\d,])(\d+),(?!\d{3}(?!\d))(\d+)(?![\d,])")
# A comma before exactly three digits (1,250) is a thousands comma or a decimal one (1.25),
# depending on the locale; a list (1,5,10) or a decimal point after it (1,250.5) settles it.
_AMBIGUOUS_COMMA = re.compile(r"(?<![\d,])(\d+),(\d{3})(?![\d,]|\.\d)")
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


def normalize(text: str, hyphen: str = "", cased: bool = False) -> str:
    """Canonical form for matching: NFKC, unified dashes and multiplication signs (an asterisk
    between digits among them), hyphenated line breaks re-joined with hyphen between the halves,
    single spaces, lower case unless cased."""
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_TIMES)
    text = text.replace("­", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", rf"\1{hyphen}\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    # A product: 40 x 8, 40X8, or 19*12.5 written with an asterisk, never spaced (3500* 500 is a
    # footnote mark).
    return re.sub(r"(\d)(?:\s*[xX]\s*|\*)(?=\d)", r"\1x", text if cased else text.lower())


def needles(quote: str) -> list[str]:
    """The normalized forms of quote to look for: as written, and, where it was copied across a
    hyphenated line break as printed (dual- axis), with the break re-joined both ways."""
    needle = normalize(quote)
    broken = re.compile(r"(\w)- (?=\w)")
    forms = [needle, broken.sub(r"\1", needle), broken.sub(r"\1-", needle)]
    return [f for i, f in enumerate(forms) if f and f not in forms[:i]]


def squash(text: str, hyphen: str = "") -> str:
    return re.sub(r"\s+", "", normalize(text, hyphen))


class _Number(NamedTuple):
    value: float
    start: int
    stop: int  # after the number as printed


class _Token(NamedTuple):
    value: float
    start: int
    end: int  # after the number, or after its unit when one is printed
    unit: str | None
    joined: bool  # shares its unit with the next token, as 5 does in "5-10 mm"
    labelled: bool  # numbers a figure, table, equation or section


def word_number(text: str) -> int | None:
    """The cardinal text is in words, whole ("Eight", "twenty-four"), or None (ADR-0005)."""
    m = _WORD_NUMBER.fullmatch(text.strip().lower())
    return int(_word_value(m)) if m else None


def _word_value(m: re.Match[str]) -> float:
    tens, ones, alone = m.groups()
    return float(_WORD_VALUES[alone] if alone else _WORD_VALUES[tens] + _WORD_VALUES[ones])


def _value(printed: str) -> float:
    *whole, last = printed.split()
    over, _, under = last.partition("/")
    value = float(over) / float(under) if under else float(over)
    return float(whole[0]) + value if whole else value


def _tokens(text: str) -> list[_Token]:
    """Every number in normalized text, in digits or as a word from zero to ninety-nine, with the
    unit printed after it. The numbers of a range, product or list share its last unit."""
    label_spans = [m.span(1) for m in _LABEL.finditer(text)]
    scanned = _DECIMAL_COMMA.sub(
        r"\1.\2", _RANGE_DASH.sub(r"\1 ", text.replace("x", " "))
    )  # same length
    # Words are read in text, since scanned blanks the x of six.
    numbers = sorted(
        [_Number(_value(m.group()), *m.span()) for m in _NUMBER.finditer(scanned)]
        + [_Number(_word_value(m), *m.span()) for m in _WORD_NUMBER.finditer(text)],
        key=lambda n: n.start,
    )
    found: list[tuple[_Number, str | None, int]] = []  # each number, its unit, and where both end
    for n in numbers:
        if found and n.start < found[-1][2]:
            continue  # a digit of the unit before it: the 3 of g/cm3
        unit, end = units.unit_at(text, n.stop) or (None, n.stop)
        if unit in _HYPHENED_NAMES and text.startswith("-", n.stop):
            unit, end = None, n.stop
        found.append((n, unit, end))
    tokens: list[_Token] = []
    for i in reversed(range(len(found))):
        n, unit, end = found[i]
        joined = (
            unit is None
            and i + 1 < len(found)
            and _SHARES_UNIT.fullmatch(text, n.stop, found[i + 1][0].start) is not None
        )
        if joined:
            unit = tokens[0].unit
        tokens.insert(
            0,
            _Token(
                n.value, n.start, end, unit, joined, any(a <= n.start < b for a, b in label_spans)
            ),
        )
    return tokens


def quantities_in(text: str) -> list[tuple[float, str | None]]:
    """The values a quote states, each with the unit printed after it (None if none): whole numeric
    tokens and number words from zero to ninety-nine, both endpoints of a range as positive
    values, and no number that labels a figure, table, equation or section. The numbers of a
    range or product share its last unit."""
    return [(t.value, t.unit) for t in _tokens(normalize(text)) if not t.labelled]


def diameters_in(text: str) -> list[float]:
    """The values a quote prints as a diameter callout (Ø 32.5): a length, whether or not a unit
    follows."""
    normalized = normalize(text)
    return [
        t.value
        for t in _tokens(normalized)
        if not t.labelled and _DIAMETER.search(normalized, max(0, t.start - 2), t.start)
    ]


def numbers_in(text: str) -> list[float]:
    """The values of quantities_in(text), without their units."""
    return [value for value, _ in quantities_in(text)]


class Ambiguous(NamedTuple):
    printed: str  # 1,250
    thousands: float  # 1250
    decimal: float  # 1.25
    parts: tuple[float, float]  # 1 and 250, as the quote reader reads them

    def reads(self, value: float) -> bool:
        """Whether value is one way of reading the number."""
        readings = (self.thousands, self.decimal, *self.parts)
        return any(math.isclose(value, r, rel_tol=1e-9) for r in readings)


def ambiguous_numbers(text: str) -> list[Ambiguous]:
    """Each number in text whose comma could be a thousands or a decimal comma (1,250)."""
    return [
        Ambiguous(
            m.group(), float(m[1] + m[2]), float(f"{m[1]}.{m[2]}"), (float(m[1]), float(m[2]))
        )
        for m in _AMBIGUOUS_COMMA.finditer(normalize(text))
    ]


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


class _HtmlText(HTMLParser):
    """An HTML page's rendered text: script, style and title dropped, tags removed, entities
    decoded, each block element or table cell its own line."""

    BLOCKS = frozenset(
        "address article aside blockquote br caption dd div dl dt figcaption figure footer form"
        " h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table td th tr ul".split()
    )
    HIDDEN = frozenset({"script", "style", "title"})  # never shown on the page

    def __init__(self) -> None:
        super().__init__()  # convert_charrefs: entities arrive decoded
        self.parts: list[str] = []
        self.hidden_depth = 0  # how many hidden elements the parser is inside

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN:
            self.hidden_depth += 1
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN:
            self.hidden_depth = max(self.hidden_depth - 1, 0)
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data.replace("\n", " "))

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).split("\n"))
        return "\n".join(line for line in lines if line)


def _html_text(markup: str) -> str:
    parser = _HtmlText()
    parser.feed(markup)
    parser.close()
    return parser.text()


def pages(path: Path) -> tuple[str, ...]:
    """Text of each page. DOCX, TXT, MD and HTML are one page; HTML's is its rendered text."""
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
    if suffix in {".html", ".htm"}:
        return (_html_text(path.read_text(encoding="utf8", errors="replace")),)
    if suffix in {".txt", ".md"}:
        return (path.read_text(encoding="utf8", errors="replace"),)
    raise ValueError(f"unsupported source format: {path.name}")


def find_quote(path: Path, quote: str, page: int | None = None) -> Match | None:
    """Locate a verbatim quote, on the cited page when one is given. A line-break hyphen ends a
    split word (inter-|toe) or belongs to a compound (dual-|axis), so both readings are tried."""
    texts = pages(path)
    candidates = [n for n in ([page] if page else range(1, len(texts) + 1)) if 1 <= n <= len(texts)]
    for mode, squashed in (("exact", False), ("squashed", True)):
        forms = needles(quote)
        patterns = [_whole(re.sub(r"\s+", "", f) if squashed else f) for f in forms]
        for n in candidates:
            for hyphen in ("", "-"):
                text = (squash if squashed else normalize)(texts[n - 1], hyphen)
                if any(pattern.search(text) for pattern in patterns):
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
# A diameter sign right before a number (Ø 32.5, Ø3, ⌀3; ∅ as some PDFs extract it), not a letter
# of a word: a diameter callout, a length in the project's unit unless a unit follows.
_DIAMETER = re.compile(r"(?<!\w)[ø⌀∅] ?$")
# A moment, when something happens (t = 2 s, a video frame's T=0s), not how long it lasts (Δt).
_MOMENT = re.compile(r"(?<!\w)t ?= ?$")
# Units whose spelling, hyphened to a number, names a thing instead: a four-bar or 4-bar linkage
# (a pressure is 2 bar).
_HYPHENED_NAMES = ("bar",)


def _capital_symbol(t: _Token, as_printed: str) -> bool:
    """Whether t's unit is a one-letter symbol SI writes in lower case (g, s, m, h) printed as a
    capital, which names something else: 8G of memory, a 2S battery."""
    unit = t.unit or ""
    return (
        len(unit) == 1
        and unit.islower()
        and as_printed[t.end - 1].isupper()
        and not as_printed[t.end - 2].isalpha()
    )


def stated_quantities(text: str, as_printed: str | None = None) -> list[tuple[int, int, str]]:
    """Spans in normalized text that state a quantity: a number the quote reader would read with
    a unit (a whole range such as 3-5 mm), an a×b×c product, a diameter callout (Ø 32.5), or a
    thread size; never digits
    inside a name or a figure, table, equation or section number, a moment (t = 2 s), or, where
    as_printed gives text normalized but for case, a one-letter unit printed as another symbol's
    capital (8G, 2S).

    It errs towards listing: a unit glued to a number is a candidate even where it is part of a
    name (1990s, 4g), because extracted text glues real ones too (0.5s, 20g), and a false
    candidate costs one skip where a missed one leaves a quantity unledgered."""
    if as_printed is None or len(as_printed) != len(text):
        as_printed = text
    spans, group = [], []
    for t in _tokens(text):
        group.append(t)
        if t.joined:
            continue
        product = len(group) > 1 and all(
            text[a.end : b.start] == "x" for a, b in zip(group, group[1:])
        )
        start = group[0].start
        callout = _DIAMETER.search(text, max(0, start - 2), start)
        if callout is not None:
            start = callout.start()
        glued = start > 0 and text[start - 1].isalnum()  # in a name: ada2cc, L14
        moment = (
            t.unit is not None
            and units.quantity(t.unit) == "time"
            and _MOMENT.search(text, max(0, group[0].start - 4), group[0].start) is not None
        )
        misread = moment or (len(group) == 1 and _capital_symbol(t, as_printed))
        stated = t.unit or product or callout
        if stated and not glued and not misread and not any(g.labelled for g in group):
            spans.append((start, t.end))
        group = []
    spans += [m.span() for m in _THREAD.finditer(text)]
    whole = [
        (a, b)
        for a, b in spans
        if not any(c <= a and b <= d and (c, d) != (a, b) for c, d in spans)
    ]
    return [(a, b, text[a:b]) for a, b in sorted(set(whole))]
