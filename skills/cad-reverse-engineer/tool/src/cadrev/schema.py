"""The expected shape of every project file, checked before any rule runs.

A spec is a Python type (str, int, bool, dict), NUMBER, a tuple of alternatives,
Items(spec) for a list, Table(spec) for a mapping of names, or Record for a
mapping with known keys. Unknown keys pass through; keys set to null count as absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NUMBER = "number"


@dataclass(frozen=True)
class Items:
    of: object


@dataclass(frozen=True)
class Table:
    of: object


@dataclass(frozen=True)
class Record:
    fields: dict = field(default_factory=dict)
    required: tuple[str, ...] = ()


TEXT_OR_NUMBER = (str, NUMBER)

SOURCE = Record(
    {
        "id": str,
        "kind": str,
        "path": str,
        "sha256": str,
        "citation": str,
        "url": str,
        "license": str,
        "coverage": bool,
    },
    required=("id",),
)
EVIDENCE = Record(
    {
        "id": str,
        "source": str,
        "page": int,
        "locator": str,
        "quote": str,
        "values": Table(NUMBER),
        "scope": str,
        "reason": str,
        "image": str,
        "image_sha256": str,
        "reading": TEXT_OR_NUMBER,
        "confirmed_by": str,
    },
    required=("id",),
)
SKIP = Record(
    {
        "source": str,
        "page": int,
        "pages": Items(int),
        "quote": str,
        "from": str,
        "to": str,
        "reason": str,
    }
)
CONFLICT = Record({"id": TEXT_OR_NUMBER, "evidence": Items(str), "summary": str, "resolution": str})
PARAM = Record(
    {
        "basis": str,
        "from": str,
        "value": NUMBER,
        "expr": str,
        "method": str,
        "uncertainty": TEXT_OR_NUMBER,
        "rationale": str,
        "gap": str,
        "interpretation": str,
    }
)
CHECK = Record(
    {
        "id": TEXT_OR_NUMBER,
        "kind": str,
        "part": str,
        "parts": Items(str),
        "evidence": str,
        "key": str,
        "axes": Table(str),
        "between": Items(str),
        "along": str,
        "density": str,
        "counts": Table(str),
        "add": Items(str),
        "tol": NUMBER,
        "tol_rel": NUMBER,
        "max_volume": NUMBER,
        "pairs": Items(Items(str)),
        "interpretation": str,
    }
)
GAP = Record({"id": str, "question": str, "ask": str}, required=("id",))
OVERLAY = Record(
    {
        "id": TEXT_OR_NUMBER,
        "image": str,
        "part": str,
        "view": str,
        "origin": Items(NUMBER),
        "mirror": bool,
        "color": str,
        "calibration": Record({"pixels": Items(Items(NUMBER)), "evidence": str}),
    }
)

# file -> top-level key -> (spec of each entry, collection type)
FILES = {
    "project.yaml": {
        "name": (TEXT_OR_NUMBER, None),
        "target": (str, None),
        "units": (dict, None),
        "tolerance": (Record({"length": NUMBER}), None),
        "model_literals": (Items(NUMBER), None),
        "sources": (SOURCE, list),
    },
    "evidence.yaml": {
        "evidence": (EVIDENCE, list),
        "skipped": (SKIP, list),
        "conflicts": (CONFLICT, list),
    },
    "params.yaml": {"params": (PARAM, dict)},
    "checks.yaml": {"checks": (CHECK, list)},
    "gaps.yaml": {"gaps": (GAP, list)},
    "overlays.yaml": {"overlays": (OVERLAY, list)},
}

_NAMES = {
    str: "text",
    int: "a whole number",
    bool: "true or false",
    dict: "a mapping",
    NUMBER: "a number",
    list: "a list",
}


def _expected(spec) -> str:
    if isinstance(spec, tuple):
        return " or ".join(_expected(s) for s in spec)
    if isinstance(spec, Items):
        return "a list"
    if isinstance(spec, (Table, Record)):
        return "a mapping"
    return _NAMES[spec]


def _given(value) -> str:
    if isinstance(value, (dict, list)):
        return "a mapping" if isinstance(value, dict) else "a list"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _is(value, spec) -> bool:
    if spec == NUMBER:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if spec is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, spec)


def conform(value, spec, where: str, problems: list[str]):
    """value with null record keys dropped; each mismatch appended to problems as 'where: message'."""
    if isinstance(spec, tuple):
        if any(_is(value, s) for s in spec):
            return value
    elif isinstance(spec, Items):
        if isinstance(value, list):
            return [conform(v, spec.of, f"{where}[{i}]", problems) for i, v in enumerate(value)]
    elif isinstance(spec, Table):
        if isinstance(value, dict):
            for k in value:
                if not isinstance(k, str):
                    problems.append(f"{where}.{k}: name must be text, not {_given(k)}")
            return {k: conform(v, spec.of, f"{where}.{k}", problems) for k, v in value.items()}
    elif isinstance(spec, Record):
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if v is not None}
            for key in spec.required:
                if key not in value:
                    problems.append(f"{where}: {key} is required")
            return {
                k: conform(v, spec.fields[k], f"{where}.{k}", problems) if k in spec.fields else v
                for k, v in value.items()
            }
    elif _is(value, spec):
        return value
    problems.append(f"{where}: must be {_expected(spec)}, not {_given(value)}")
    return value


def conform_file(name: str, data, problems: list[str]) -> dict:
    """The file's known keys, keeping only the entries whose shape is right."""
    if not isinstance(data, dict):
        problems.append(f"{name}: must be a mapping of keys, not {_given(data)}")
        return {}
    out = dict(data)
    for key, (spec, collection) in FILES[name].items():
        value = data.get(key)
        where = f"{name} {key}"
        if value is None:
            out.pop(key, None)
            continue
        if collection is None:
            before = len(problems)
            out[key] = conform(value, spec, where, problems)
            if len(problems) > before:
                out.pop(key)
            continue
        if not isinstance(value, collection):
            problems.append(
                f"{where}: must be {_NAMES[collection]} of entries, not {_given(value)}"
            )
            out.pop(key)
            continue
        entries = value.items() if collection is dict else enumerate(value)
        kept = {}
        for k, entry in entries:
            found: list[str] = []
            label = f"{where}.{k}" if collection is dict else f"{where}[{k}]"
            entry = conform(entry, spec, label, found)
            if collection is dict and not isinstance(k, str):
                found.append(f"{label}: name must be text, not {_given(k)}")
            problems += found
            if not found:
                kept[k] = entry
        out[key] = kept if collection is dict else list(kept.values())
    return out
