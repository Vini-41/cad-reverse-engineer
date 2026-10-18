"""Source documents: hashing, text extraction, figure extraction and quote matching."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_TIMES = dict.fromkeys(map(ord, "×✕✖⨯"), "x")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


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


def numbers_in(text: str) -> list[float]:
    return [float(n) for n in _NUMBER.findall(normalize(text).replace("x", " "))]


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
        for n in candidates:
            if 1 <= n <= len(texts) and needle and needle in fn(texts[n - 1]):
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
