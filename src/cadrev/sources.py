"""Source documents: hashing, text extraction, figure extraction and quote matching."""

from __future__ import annotations

import ctypes
import hashlib
import io
import math
import re
import unicodedata
import zipfile
from collections.abc import Callable
from functools import cache, partial
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

from . import threads, units

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_TIMES = dict.fromkeys(map(ord, "×✕✖⨯"), "x")
# The numbers naming figures, tables, equations or sections ("Fig. S2", "Eqs. (3)-(4)",
# "Sec. 4.2", "Figs. 2 and 3"). Abbreviations other than "fig" need their period, so "2 sec"
# stays a value, and a number followed by a unit ("section 4 mm thick") is a value; "in" and
# the inch mark are left out there, so "Fig. 2 in" stays a label.
_UNIT = units.spelling()
# A number as printed: 3.5 or .5, not the 5 of Fig.5; or a fraction before a unit (1/4 inch,
# 1 1/2 in, 1/4-in.; a bare 1/50 is two).
_NUMBER = re.compile(
    rf"-?(?:\d+\s)?\d+/[1-9]\d*(?={units.UNIT_GAP}{_UNIT})|-?(?:\d+(?:\.\d+)?|(?<![\w.])\.\d+)"
)
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
# "-10 to -5 deg", and a tolerance's nominal: "1.000 ± 0.005 in".
_SHARES_UNIT = re.compile(r"\s*[-±]\s*|x|,|\s+to\s+")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# Each character's superscript form, by the characters it raises: the later of two (ᵃ over ª),
# a whole run where one stands for it (™ for TM), and a dash as the minus.
_SUPERSCRIPT_OF = {unicodedata.normalize("NFKC", c): c for c in units.SUPERSCRIPTS} | dict.fromkeys(
    "-‐‑‒–—", "⁻"
)
# Marks a font sets high whether or not they are raised: primes, degrees, footnote and
# trademark signs.
_HIGH = frozenset("′″‴°◦*∗†‡®©" + units.SUPERSCRIPTS)


def superscript(run: str) -> str:
    """A raised run as source text writes it: in superscripts (10⁻⁵, cm², ™), as printed where
    each mark is one a font sets high anyway (″, ®, †), else as ^(run)."""
    if all(c in _HIGH for c in run):
        return run
    if run in _SUPERSCRIPT_OF:
        return _SUPERSCRIPT_OF[run]
    if all(c in _SUPERSCRIPT_OF for c in run):
        return "".join(_SUPERSCRIPT_OF[c] for c in run)
    return f"^({run})"


# A raised run typed with a caret: 10^5, 10^-5, cm^2, ^(a,b).
_CARET = re.compile(r"\^\(([^()]*)\)|\^([-+−]?\d+)")
_SUPERSCRIPT_RUN = re.compile(f"([{units.SUPERSCRIPTS}]+)")


def normalize(text: str, hyphen: str = "", cased: bool = False) -> str:
    """Canonical form for matching: NFKC but for superscripts, which stay apart from the line
    (a caret's run written as one), unified dashes and multiplication signs (an asterisk
    between digits among them), hyphenated line breaks re-joined with hyphen between the
    halves, single spaces, lower case unless cased."""
    text = _CARET.sub(lambda m: superscript(m[2] if m[1] is None else m[1]), text)
    parts = _SUPERSCRIPT_RUN.split(text)
    text = "".join(p if i % 2 else unicodedata.normalize("NFKC", p) for i, p in enumerate(parts))
    text = text.translate(_DASHES).translate(_TIMES)
    text = text.replace("­", "")
    text = re.sub(r"(\d)-\s*\n\s*(?=\d)", r"\1-", text)  # a range broken over a line: 60-80%
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


# Whitespace a quote may differ by: any but what stands between two digits, a decimal point among
# them or not (1 4, 1 .4, 1. 4, 1 . 4), which keeps two numbers from reading as one.
_IGNORED_SPACE = re.compile(r"(?<!\d)(?<!\d\.)(?<!\d\s\.)\s|\s(?!\.?\s?\d)")


def ignored_space(text: str, i: int) -> bool:
    """Whether normalized text[i] is whitespace a quote may differ by."""
    return _IGNORED_SPACE.match(text, i) is not None


def unspaced(text: str) -> str:
    """Normalized text without the whitespace a quote may differ by."""
    return _IGNORED_SPACE.sub("", text)


def squash(text: str, hyphen: str = "") -> str:
    return unspaced(normalize(text, hyphen))


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
    """The cardinal text is in words, whole ("Eight", "twenty-four"), or None."""
    m = _WORD_NUMBER.fullmatch(text.strip().lower())
    return int(_word_value(m)) if m else None


def _word_value(m: re.Match[str]) -> float:
    tens, ones, alone = m.groups()
    return float(_WORD_VALUES[alone] if alone else _WORD_VALUES[tens] + _WORD_VALUES[ones])


def _value(printed: str) -> float:
    *whole, last = printed.split()
    over, _, under = last.partition("/")
    value = float(over) / float(under) if under else float(over)
    if not whole:
        return value
    return float(whole[0]) + (-value if whole[0].startswith("-") else value)  # -1 1/2 is -1.5


# What follows a number, as printed, that is no unit of it though in lower case it would spell
# one: a thread size after it (4 M3 screws) or called out by it as a drawing counts its holes
# (4-M3, 4xM3, 8-M 2.0), a capital M and its digits, which would spell a length, an area or a
# volume; and a concentration in moles per litre (20 µM, 2 mM, 5 nM), a capital M after a
# lower-case prefix, which would spell a length or a torque.
_NO_UNIT_NEXT = re.compile(r"\s?M\d|\s?[-xX]\s?M\s?\d|\s?[μmn]M(?![A-Za-z])")


# A raised run that reads as a power of ten after a printed 10, and the product sign before
# that 10 in scientific notation, as normalized: 2.1x10⁵, 2.1 x 10⁵, 2.1 · 10⁵.
_EXPONENT = re.compile(r"[⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_PRODUCT_SIGN = re.compile(r"\s?[x·⋅]\s?")


def _exponents(text: str, numbers: list[_Number]) -> list[_Number]:
    """numbers in normalized text, each 10 with an exponent raised over it read as that power
    of ten, and as one number with the mantissa it multiplies: 10⁻⁵ is 1e-5, 2.1 × 10⁵ is
    210000. Any other raised run is no number: a unit's power, or a footnote marker."""
    read: list[_Number] = []
    for n in numbers:
        power = _EXPONENT.match(text, n.stop)
        if power is None or text[n.start : n.stop] != "10":
            read.append(n)
            continue
        ten = 10.0 ** int(unicodedata.normalize("NFKC", power.group()).translate(_DASHES))
        if read and _PRODUCT_SIGN.fullmatch(text, read[-1].stop, n.start):
            mantissa = read.pop()
            read.append(_Number(mantissa.value * ten, mantissa.start, power.end()))
        else:
            read.append(_Number(ten, n.start, power.end()))
    return read


def _tokens(text: str, as_printed: str | None = None) -> list[_Token]:
    """Every number in normalized text, in digits or as a word from zero to ninety-nine, with the
    unit printed after it. The numbers of a range, product or list share its last unit. Where
    as_printed gives the text normalized but for case, a thread size or a concentration is no
    unit of the number before it: four M3 screws are no four cubic metres, and 20 µM no 20 µm."""
    if as_printed is None or len(as_printed) != len(text):
        as_printed = text
    label_spans = [m.span(1) for m in _LABEL.finditer(text)]
    scanned = _DECIMAL_COMMA.sub(
        r"\1.\2", _RANGE_DASH.sub(r"\1 ", text.replace("x", " "))
    )  # same length
    # Words are read in text, since scanned blanks the x of six.
    numbers = _exponents(
        text,
        sorted(
            [_Number(_value(m.group()), *m.span()) for m in _NUMBER.finditer(scanned)]
            + [_Number(_word_value(m), *m.span()) for m in _WORD_NUMBER.finditer(text)],
            key=lambda n: n.start,
        ),
    )
    found: list[tuple[_Number, str | None, int]] = []  # each number, its unit, and where both end
    for n in numbers:
        if found and n.start < found[-1][2]:
            continue  # a digit of the unit before it: the 3 of g/cm3
        unit, end = units.unit_at(text, n.stop) or (None, n.stop)
        named = unit in _HYPHENED_NAMES and text.startswith("-", n.stop)
        if named or _NO_UNIT_NEXT.match(as_printed, n.stop):
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


@cache
def quantities_in(text: str) -> tuple[tuple[float, str | None], ...]:
    """The values a quote states, each with the unit printed after it (None if none): whole numeric
    tokens and number words from zero to ninety-nine, both endpoints of a range as positive
    values, and no number that labels a figure, table, equation or section. The numbers of a
    range or product share its last unit."""
    tokens = _tokens(normalize(text), normalize(text, cased=True))
    return tuple((t.value, t.unit) for t in tokens if not t.labelled)


@cache
def diameters_in(text: str) -> tuple[float, ...]:
    """The values a quote prints as a diameter callout (Ø 32.5): a length, whether or not a unit
    follows."""
    normalized = normalize(text)
    return tuple(
        t.value
        for t in _tokens(normalized)
        if not t.labelled and _DIAMETER.search(normalized, max(0, t.start - 2), t.start)
    )


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


# What a raised run after it is the exponent or the power of: a 10, or a unit's spelling.
_CUT_FROM_POWER = re.compile(rf"(?<![\d.,])10$|(?<![a-z]){units.spelling()}$")


def _whole(needle: str) -> re.Pattern[str]:
    """needle, refusing to start or end inside a larger number (37 within 137 or 3.7), or to
    end on a 10 or a unit cut from the run raised over it (10 of 10⁵, cm of cm²)."""
    head = r"(?<!\d)(?<!\d[.,])" if needle[:1].isdigit() else ""
    tail = r"(?![.,]?\d)" if needle[-1:].isdigit() else ""
    if _CUT_FROM_POWER.search(needle):
        tail += f"(?![{units.SUPERSCRIPTS}])"
    return re.compile(head + re.escape(needle) + tail)


_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(path: Path) -> str:
    """A DOCX's text runs, a line per paragraph, entities decoded, superscript runs raised."""
    import xml.etree.ElementTree as ET

    body = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    lines = []
    for p in body.iter(f"{_WORD}p"):
        runs = []  # (text, whether superscript), consecutive runs alike joined
        for r in p.iter(f"{_WORD}r"):
            align = r.find(f"{_WORD}rPr/{_WORD}vertAlign")
            up = align is not None and align.get(f"{_WORD}val") == "superscript"
            text = "".join(t.text or "" for t in r.iter(f"{_WORD}t"))
            if runs and runs[-1][1] == up:
                runs[-1] = (runs[-1][0] + text, up)
            elif text:
                runs.append((text, up))
        lines.append("".join(superscript(text) if up else text for text, up in runs))
    return "\n".join(line for line in lines if line.strip())


class _HtmlText(HTMLParser):
    """An HTML page's rendered text: script, style and title dropped, tags removed, entities
    decoded, each block element or table cell its own line, and a <sup> raised."""

    BLOCKS = frozenset(
        "address article aside blockquote br caption dd div dl dt figcaption figure footer form"
        " h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section table td th tr ul".split()
    )
    HIDDEN = frozenset({"script", "style", "title"})  # never shown on the page

    def __init__(self) -> None:
        super().__init__()  # convert_charrefs: entities arrive decoded
        self.parts: list[str] = []
        self.hidden_depth = 0  # how many hidden elements the parser is inside
        self.sup: list[str] | None = None  # the text of the <sup> the parser is inside

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN:
            self.hidden_depth += 1
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "sup" and self.sup is None:
            self.sup = []

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN:
            self.hidden_depth = max(self.hidden_depth - 1, 0)
        if tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "sup" and self.sup is not None:
            run, self.sup = " ".join("".join(self.sup).split()), None
            self.parts.append(superscript(run) if run else "")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            (self.parts if self.sup is None else self.sup).append(data.replace("\n", " "))

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
        import pypdf
        import pypdfium2

        # PDFium ends a line with \r\n, and writes a hyphen that ends one as U+FFFE with no break.
        pdf = pypdfium2.PdfDocument(path)
        reader = cache(lambda: pypdf.PdfReader(path))  # opened only for a symbol font's page
        texts = (
            _page_text(page.get_textpage(), partial(_font_codes, reader, n))
            for n, page in enumerate(pdf)
        )
        return tuple(t.replace("\r\n", "\n").replace("\ufffe", "-\n") for t in texts)
    if suffix == ".docx":
        return (_docx_text(path),)
    if suffix in {".html", ".htm"}:
        return (_html_text(path.read_text(encoding="utf8", errors="replace")),)
    if suffix in {".txt", ".md"}:
        return (path.read_text(encoding="utf8", errors="replace"),)
    raise ValueError(f"unsupported source format: {path.name}")


# What a typesetter's symbol font draws, by glyph name, where its text layer names another
# character. Its control codes are assigned per file (code 3 is × in one paper, ~ in another), so
# a glyph is known by the name the font's encoding gives its code: its /Differences name, else
# its standard encoding's, which for a letter is the letter. A glyph at a printable code that is no
# letter needs its character in _LOOKED_UP.
_DRAWN = {
    "AdvP4C4E74": {"C0": "−", "C2": "×", "C15": "•", "C24": "~", "y": "†", "zero": "′"},
    "AdvPSMP13": {"b": "β", "l": "µ"},
    "AdvPSSym": {"C176": "°", "C210": "®", "C211": "©"},
    "AdvPi1": {"m": "µ"},
}
# The characters whose font is looked up, those PDFium reports for the glyphs above: a control
# code, a letter as itself, and zero as 0.
_LOOKED_UP = frozenset(
    [chr(code) for code in range(32)]
    + [name for drawn in _DRAWN.values() for name in drawn if len(name) == 1]
    + ["0"]
)
# Characters on one line further apart than this many digit widths are in separate table cells.
_CELL_GAP = 3


def _in_separate_cells(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """Whether two characters' boxes (left, right, bottom, top) sit on one line, across the page
    or up it, too far apart to be one number."""
    for start, end, low, high in ((0, 1, 2, 3), (2, 3, 0, 1)):
        if min(a[high], b[high]) > max(a[low], b[low]):
            gap = max(b[start] - a[end], a[start] - b[end])
            return gap > _CELL_GAP * max(a[end] - a[start], b[end] - b[start])
    return False


def _font_codes(reader: Callable, n: int) -> dict[str, dict[int, str | None]]:
    """The glyph name of each code the /Differences of page n's fonts name, by font family; None
    for a code two subsets of a family name differently, since PDFium does not say which drew it."""
    codes: dict[str, dict[int, str | None]] = {}
    pending, seen = [reader().pages[n].get("/Resources")], set()
    while pending:
        resources = pending.pop()
        resources = resources.get_object() if resources is not None else None
        if not resources or id(resources) in seen:
            continue
        seen.add(id(resources))
        pending += [
            x.get_object().get("/Resources") for x in resources.get("/XObject", {}).values()
        ]
        for font in resources.get("/Font", {}).values():
            font = font.get_object()
            family = codes.setdefault(str(font.get("/BaseFont", "")).split("+")[-1].lstrip("/"), {})
            encoding = font.get("/Encoding")
            encoding = encoding.get_object() if encoding is not None else None
            code = 0
            for item in encoding.get("/Differences", []) if isinstance(encoding, dict) else []:
                item = item.get_object()
                if isinstance(item, int):
                    code = item
                else:
                    family[code] = item[1:] if family.get(code, item[1:]) == item[1:] else None
                    code += 1
    return codes


class _Glyph(NamedTuple):
    """Where a character is drawn: its baseline's start, its size, the direction its line runs
    (a unit vector), and where it is on the page, by which its box is found."""

    x: float
    y: float
    size: float
    dx: float
    dy: float
    at: int  # its index on the page

    def offset(self, other: _Glyph) -> tuple[float, float]:
        """How far along this glyph's line other starts, and how far above its baseline, in
        this glyph's size."""
        vx, vy = other.x - self.x, other.y - self.y
        return (vx * self.dx + vy * self.dy) / self.size, (self.dx * vy - self.dy * vx) / self.size


Box = Callable[[int], tuple[float, float, float, float]]  # a character's (left, right, bottom, top)


def _spaced(a: _Glyph, b: _Glyph, box: Box, size: float) -> bool:
    """Whether b's box starts further along a's line after a's ends than a space would, in a
    line of size."""
    (l1, r1, b1, t1), (l2, r2, b2, t2) = box(a.at), box(b.at)
    end = max(l1 * a.dx, r1 * a.dx) + max(b1 * a.dy, t1 * a.dy)
    return min(l2 * a.dx, r2 * a.dx) + min(b2 * a.dy, t2 * a.dy) - end > _SPACE * size


# A raised character is drawn smaller than the last character on its line, its baseline above
# that one's by more than this share of its size and less than a line. A capital or a bracket
# stands taller on the same baseline, at the same size.
_SMALLER, _RISE = 0.9, 0.15
# A wider gap than this share of the line's size beside a raised run is a space.
_SPACE = 0.25


def _is_raised(base: _Glyph, glyph: _Glyph, last: _Glyph) -> bool:
    """Whether glyph is raised over base, the last character on its line, starting just after
    last: base itself or the raised character before it."""
    if glyph.size >= _SMALLER * base.size:
        return False
    along, rise = base.offset(glyph)
    return _RISE < rise < 1 and -0.5 < along - base.offset(last)[0] < 2


def _written(chars: list[tuple[str, _Glyph | None]], box: Box) -> str:
    """A page's characters, each with where it is drawn (None for one PDFium adds), with each
    raised run written raised and kept on its line: what PDFium adds around it is a space where
    the page leaves one, else nothing. A fraction's numerator stands over its denominator,
    which steps back under it below the line, and is not raised."""
    out: list[str] = []
    base, added = None, 0  # the last character on the line; spaces and breaks added since it
    i = 0
    while i < len(chars):
        char, glyph = chars[i]
        if glyph is None or base is None or not _is_raised(base, glyph, base):
            out.append(char)
            base, added = (glyph, 0) if glyph else (base, added + 1 if char.isspace() else 0)
            i += 1
            continue
        run, last, j = [char], glyph, i + 1  # j: just after the run's last character
        while True:
            k = next((n for n in range(j, len(chars)) if chars[n][1]), len(chars))
            after = chars[k][1] if k < len(chars) else None  # the next character drawn
            if after is None or not _is_raised(base, after, last):
                break
            run.append(chars[k][0])
            last, j = after, k + 1
        along, rise = base.offset(after) if after else (0.0, 0.0)
        if after and -1 < rise < -_RISE and along < base.offset(last)[0]:  # a numerator
            out.append(char)
            base, added, i = glyph, 0, i + 1
            continue
        if added:
            out[len(out) - added :] = [" " if _spaced(base, glyph, box, base.size) else ""]
        out.append(superscript(_utf16("".join(run))))
        if after and abs(rise) < _RISE and along > base.offset(last)[0]:  # back on the line
            out.append(" " if _spaced(last, after, box, base.size) else "")
        else:
            out += [c for c, _ in chars[j:k]]
        added, i = 0, k
    return "".join(out)


def _utf16(text: str) -> str:
    """text as PDFium gives it, a surrogate pair for a character beyond the BMP, decoded."""
    return text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "ignore")


def _page_text(textpage, font_codes: Callable[[], dict[str, dict[int, str | None]]]) -> str:
    """A PDF page's text as PDFium extracts it, with what the text layer misstates put right: a
    symbol font's glyph is the character it draws, two numbers in separate table cells are
    kept apart, and a raised run is written raised."""
    import pypdfium2.raw as pdfium

    raw, chars = textpage.raw, []
    name, flags = ctypes.create_string_buffer(256), ctypes.c_int()
    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
    x, y, matrix = ctypes.c_double(), ctypes.c_double(), pdfium.FS_MATRIX()

    def box(i: int) -> tuple[float, float, float, float]:
        pdfium.FPDFText_GetCharBox(raw, i, left, right, bottom, top)
        return left.value, right.value, bottom.value, top.value

    codes, before = None, None  # the page's font codes once needed; the digit just before
    for i in range(pdfium.FPDFText_CountChars(raw)):
        code = pdfium.FPDFText_GetUnicode(raw, i)
        char = chr(code)
        if char in _LOOKED_UP and pdfium.FPDFText_GetFontInfo(raw, i, name, 256, flags):
            if drawn := _DRAWN.get(name.value.decode("utf8", "replace")):
                codes = font_codes() if codes is None else codes
                family = codes.get(name.value.decode("utf8", "replace"), {})
                char = drawn.get(family.get(code, char) or "", char)
        glyph = None
        if not pdfium.FPDFText_IsGenerated(raw, i):
            pdfium.FPDFText_GetMatrix(raw, i, matrix)
            a, b, c, d = matrix.a, matrix.b, matrix.c, matrix.d
            size = pdfium.FPDFText_GetFontSize(raw, i) * math.sqrt(abs(a * d - b * c))
            if size > 0 and (scale := math.hypot(a, b)) > 0:
                pdfium.FPDFText_GetCharOrigin(raw, i, x, y)
                glyph = _Glyph(x.value, y.value, size, a / scale, b / scale, i)
        if char.isascii() and (char.isdecimal() or char == "."):
            here = box(i)
            if before and _in_separate_cells(before, here):
                chars.append((" ", None))
            before = here if char != "." else None
        else:
            before = None
        # As PDFium's own text range: U+0002 is a line-end hyphen, written U+FFFE, and U+0003 is
        # left out.
        if char != "\x03":
            chars.append(("￾" if char == "\x02" else char, glyph))
    return _utf16(_written(chars, box))


def find_quote(path: Path, quote: str, page: int | None = None) -> int | None:
    """The page a verbatim quote is on, 1-based, looking only on the cited page when one is given;
    None where it is not found. Whitespace is matched as one space, then ignored, but for a space
    that keeps two numbers from reading as one. A line-break hyphen ends a split word (inter-|toe)
    or belongs to a compound (dual-|axis), so both readings are tried."""
    texts = pages(path)
    candidates = [n for n in ([page] if page else range(1, len(texts) + 1)) if 1 <= n <= len(texts)]
    for squashed in (False, True):
        forms = needles(quote)
        patterns = [_whole(unspaced(f) if squashed else f) for f in forms]
        for n in candidates:
            for hyphen in ("", "-"):
                text = (squash if squashed else normalize)(texts[n - 1], hyphen)
                if any(pattern.search(text) for pattern in patterns):
                    return n
    return None


def extract_figures(path: Path, out: Path) -> list[Path]:
    """Write every embedded image to out/, so figures can be viewed: a PDF's named by page, after
    that page rendered whole, which shows what no embedded image holds (a figure drawn as vector
    graphics, a table's layout)."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    if path.suffix.lower() == ".pdf":
        import pypdfium2

        for n, page in enumerate(pypdfium2.PdfDocument(path), 1):
            whole = out / f"p{n:03d}.png"
            page.render(scale=2).to_pil().save(whole)  # 144 dpi
            written.append(whole)
            images = [o for o in page.get_objects() if isinstance(o, pypdfium2.PdfImage)]
            for i, image in enumerate(images, 1):
                data = io.BytesIO()
                image.extract(data)  # JPEG and JPEG 2000 as stored, the rest as PNG or TIFF
                suffix = _MAGIC.get(data.getvalue()[:2], ".jp2")
                written.append(_write_viewable(out / f"p{n:03d}_{i:02d}{suffix}", data.getvalue()))
    elif path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist()):
                if name.startswith("word/media/"):
                    written.append(_write_viewable(out / Path(name).name, z.read(name)))
    return written


def pixel_size(path: Path) -> tuple[int, int] | None:
    """An image file's width and height in pixels, the frame `cadrev crop` takes its box in; None
    for a file Pillow cannot read."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError, ValueError):
        return None


VIEWABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}  # formats an image viewer shows as they are
_MAGIC = {b"\xff\xd8": ".jpg", b"\x89P": ".png", b"II": ".tif", b"MM": ".tif"}  # else JPEG 2000


def _write_viewable(target: Path, data: bytes) -> Path:
    """Write an extracted image to target, or as PNG beside it when Pillow can read it and a
    viewer cannot be counted on to show it: a format none shows (TIFF, BMP), or a JPEG that is
    not RGB, since a PDF's grayscale and CMYK ones are refused by some. Return the path written."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            if target.suffix.lower() not in VIEWABLE or (
                image.format == "JPEG" and image.mode != "RGB"
            ):
                png = target.with_suffix(".png")
                (image.convert("RGB") if image.mode == "CMYK" else image).save(png, format="PNG")
                return png
    except (UnidentifiedImageError, OSError, ValueError):
        pass  # a format Pillow cannot read (EMF, WMF) is kept as extracted
    target.write_bytes(data)
    return target


# Thread and fastener sizes (M3, M2.5x0.45): stated sizes the unit table cannot read; not the end
# of a model name hyphened to a word (an Olympus E-M10). A drawing calls one out by the count of
# its holes (4-M3, 4xM3, 8-M 2.0).
_THREAD = re.compile(
    r"(?:(?<![a-z0-9.])(?<![a-z]-)m|(?:(?<=\d-)|(?<=\dx))m ?)"
    r"\d+(?:\.\d+)?(?:x\d+(?:\.\d+)?)?(?![a-z0-9])"
)
# A diameter sign right before a number (Ø 32.5, Ø3, ⌀3; ∅ as some PDFs extract it), not a letter
# of a word: a diameter callout, a length in the project's unit unless a unit follows.
_DIAMETER = re.compile(r"(?<!\w)[ø⌀∅] ?$")
# A moment, when something happens (t = 2 s, a video frame's T=0s), not how long it lasts (Δt).
_MOMENT = re.compile(r"(?<!\w)t ?= ?$")
# A subscripted symbol (r2, p2, s1) after a one-letter unit: 2N r2 is a product of symbols, as is
# 2N p 1, its subscript on a line of its own as PDFium extracts it, and 1 % nᵖ 1, its superscript
# raised.
_SUBSCRIPTED = re.compile(
    rf" (?:[a-z]+[{units.SUPERSCRIPTS}]*\d+|[a-z][{units.SUPERSCRIPTS}]* [a-z0-9])(?![a-z0-9])"
)
# The colon of a ratio (60:1), whose second number takes no unit; a time's (1:30 min) does.
_RATIO = re.compile(r"\d:$")
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
    a unit (a whole range such as 3-5 mm, a nominal and its tolerance), an a×b×c product, a
    diameter callout (Ø 32.5), or a thread size; never digits inside a name or a figure, table,
    equation or section number, a model name (E-M10), a moment (t = 2 s), a one-letter unit
    before a subscripted symbol (2N r2), or a unit after a ratio's colon (60:1 in) except a time
    (1:30 min); and, where as_printed gives text normalized but for case, no one-letter unit
    printed as another symbol's capital (8G, 2S), nor a thread size printed in lower case (m1, a
    gear's module).

    It errs towards listing: a unit glued to a number is a candidate even where it is part of a
    name (1990s, 4g), because extracted text glues real ones too (0.5s, 20g), and a false
    candidate costs one skip where a missed one leaves a quantity unledgered."""
    case_unknown = as_printed is None or len(as_printed) != len(text)
    if as_printed is None or case_unknown:  # as_printed is None again, for pyright
        as_printed = text
    spans, group = [], []
    for t in _tokens(text, as_printed):
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
        subscript = _SUBSCRIPTED.match(text, t.end)
        before_subscript = (
            len(group) == 1
            and len(t.unit or "") == 1
            and not text[t.end - 2].isalpha()
            and subscript is not None
            and as_printed[subscript.start() + 1] != "M"  # a thread size: 10 N M4 bolt
        )
        ratio = (
            t.unit is not None
            and units.quantity(t.unit) != "time"
            and _RATIO.search(text, max(0, group[0].start - 2), group[0].start) is not None
        )
        misread = (
            moment
            or before_subscript
            or ratio
            or (len(group) == 1 and _capital_symbol(t, as_printed))
        )
        stated = t.unit or product or callout
        if stated and not glued and not misread and not any(g.labelled for g in group):
            spans.append((start, t.end))
        group = []
    # A thread size prints a capital M: m1, m2 in lower case are symbols (a gear's modules).
    metric = _THREAD.finditer(text)
    spans += [m.span() for m in metric if case_unknown or as_printed[m.start()] == "M"]
    spans += threads.unified_spans(text)
    whole = [
        (a, b)
        for a, b in spans
        if not any(c <= a and b <= d and (c, d) != (a, b) for c, d in spans)
    ]
    return [(a, b, text[a:b]) for a, b in sorted(set(whole))]
