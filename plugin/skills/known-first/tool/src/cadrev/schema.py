"""The shape of every project file, checked before any rule runs.

A spec is a type (str, int, bool, dict), NUMBER, a tuple of alternatives, Items(spec) for a list,
Table(spec) for a mapping of names, a Record for a mapping with known keys, or OneOf for one of a
few words. An unknown key is
a problem, since it is most often a typo or a value split at an unquoted comma; a key set to null
counts as absent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .sources import word_number

NUMBER = "number"
# A number, or a cardinal in words read as the number it names: a ledger value written as printed.
NUMBER_OR_WORD = "number or word"
TEXT_OR_NUMBER = (str, NUMBER)
# What a complete model follows where the object is hard to make as its sources show it.
FOLLOWS = ("design", "function")


@dataclass(frozen=True)
class Items:
    of: object


@dataclass(frozen=True)
class Table:
    of: object


@dataclass(frozen=True)
class OneOf:
    words: tuple[str, ...]


@dataclass(frozen=True)
class Record:
    fields: dict
    required: tuple[str, ...] = ()
    exclusive: tuple[tuple[str, ...], ...] = ()  # groups of keys of which an entry gives one


_TYPES = {"int": int, "bool": bool, "number": NUMBER, "word": NUMBER_OR_WORD, "any": TEXT_OR_NUMBER}


def _spec(text: str):
    """The spec a field's type names: [T] a list, {T} a mapping of names; text where it names
    none."""
    if text.startswith(("[", "{")):
        return (Items if text[0] == "[" else Table)(_spec(text[1:-1]))
    return _TYPES.get(text, str)


def record(fields: str, exclusive: tuple = (), **nested) -> Record:
    """A Record from its fields, each `name` (text) or `name:type`, a `!` after the name marking it
    required; nested gives the fields that are records themselves."""
    specs, required = dict(nested), []
    for field in fields.split():
        name, _, kind = field.partition(":")
        if name.endswith("!"):
            name = name[:-1]
            required.append(name)
        specs[name] = _spec(kind)
    return Record(specs, tuple(required), exclusive)


SOURCE = record("id! kind path sha256 citation url coverage:bool")
EVIDENCE = record(
    "id! source page:int locator quote values:{word} scope reason image image_sha256 reading:any "
    "confirmed_by probe body axes:{str} between:[str] along at tol:number"
)
SKIP = record("source page:int pages:[int] quote from to body within:[[number]] reason")
CONFLICT = record("id:any evidence:[str] summary resolution")
PARAM = record(
    "basis from value:number expr thread:any length method uncertainty:any rationale gap "
    "interpretation physics:bool"
)
CHECK = record(
    "id!:any kind part thread instances:[str] parts:[str] evidence key expect axes:{str} "
    "between:[str] "
    "along at density counts:{str} add:[str] tol:number tol_rel:number max_volume:number "
    "pairs:[[str]] pose:{any} from:{any} claim joint cable body ends:[str] interpretation",
    exclusive=(("part", "instances"), ("part", "thread")),
    sweep=record("joint! steps!"),
)
# A datum on a released body: a point, or one derived from datums declared on the same body.
DATUM = (Items(NUMBER), record("circle:[str] mid:[str]", exclusive=(("circle", "mid"),)))
# A part's mass: its datasheet mass, or a density its volume is weighed by; one param either way.
PART = record("mass density", exclusive=(("mass", "density"),))
GAP = record("id! question ask")
# What model.py's build returns for a mechanism, held to the same shapes as the YAML.
JOINT = record(
    "type parent child axis:[str] range:[str] drive damping stiffness friction spring_rest"
)
GEAR = record("driver driven ratio lead")
CABLE = record("path:[str] wheel closes:{str}")
# A step of the plan: the instances it places, the screws it drives of each thread param, and
# how. `with` is a Python keyword, which a mapping's key may be.
STEP = record("place:[str] with:{int} note")

# file -> top-level key -> (spec of each entry, the collection holding the entries or None)
FILES = {
    "project.yaml": {
        "name": (TEXT_OR_NUMBER, None),
        "target": (str, None),
        "units": (dict, None),
        "tolerance": (record("length:number angle:number"), None),
        "clearance": (str, None),
        "material": (str, None),
        "follows": (OneOf(FOLLOWS), None),
        "up": (OneOf(("y", "z")), None),
        "known_first": (bool, None),
        "sources": (SOURCE, list),
    },
    "evidence.yaml": {
        "evidence": (EVIDENCE, list),
        "skipped": (SKIP, list),
        "conflicts": (CONFLICT, list),
        "datums": (DATUM, dict),
    },
    "params.yaml": {"params": (PARAM, dict), "parts": (PART, dict)},
    "checks.yaml": {"checks": (CHECK, list)},
    "gaps.yaml": {"gaps": (GAP, list)},
    # The plan: how each part is made, in one operation or several in order; what is bought for
    # a part, a screw or anything else; and the steps that assemble the instances.
    "plan.yaml": {
        "make": ((str, Items(str)), dict),
        "buy": (str, dict),
        "steps": (STEP, list),
    },
}

_NAMES = {
    str: "text",
    int: "a whole number",
    bool: "true or false",
    dict: "a mapping",
    list: "a list",
    NUMBER: "a number",
    NUMBER_OR_WORD: "a number",
}


def _expected(spec) -> str:
    if isinstance(spec, tuple):
        return " or ".join(_expected(s) for s in spec)
    if isinstance(spec, Items):
        return "a list"
    if isinstance(spec, OneOf):
        return " or ".join(spec.words)
    return "a mapping" if isinstance(spec, (Table, Record)) else _NAMES[spec]


def _given(value) -> str:
    if isinstance(value, (dict, list)):
        return "a mapping" if isinstance(value, dict) else "a list"
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _is(value, spec) -> bool:
    if spec in (NUMBER, NUMBER_OR_WORD):  # finite: .nan and .inf state nothing
        return type(value) in (int, float) and math.isfinite(value)
    if spec is int:
        return type(value) is int
    return isinstance(value, spec)


def conform(value, spec, where: str, problems: list[str]) -> Any:
    """value with null record keys dropped; each mismatch appended to problems as `where: why`."""
    if isinstance(spec, tuple):
        for alternative in spec:
            found: list[str] = []
            conformed = conform(value, alternative, where, found)
            if not found:
                return conformed
    elif isinstance(spec, Items):
        if isinstance(value, (list, tuple)):
            return [conform(v, spec.of, f"{where}[{i}]", problems) for i, v in enumerate(value)]
    elif isinstance(spec, Table):
        if isinstance(value, dict):
            for k in value:
                if not isinstance(k, str):
                    problems.append(f"{where}.{k}: name must be text, not {_given(k)}")
            return {k: conform(v, spec.of, f"{where}.{k}", problems) for k, v in value.items()}
    elif isinstance(spec, Record):
        if isinstance(value, dict):
            for key in value:
                if key not in spec.fields:
                    problems.append(
                        f"{where}: unknown key {key!r}; if it is the rest of a value split at a "
                        "comma, quote that value"
                    )
            value = {k: v for k, v in value.items() if v is not None}
            problems += [f"{where}: {key} is required" for key in spec.required if key not in value]
            for group in spec.exclusive:
                given = [key for key in group if key in value]
                if len(given) > 1:
                    problems.append(f"{where}: give {' or '.join(given)}, not both")
            return {
                k: conform(v, spec.fields[k], f"{where}.{k}", problems) if k in spec.fields else v
                for k, v in value.items()
            }
    elif isinstance(spec, OneOf):
        if value in spec.words:
            return value
    elif _is(value, spec):
        return value
    elif spec == NUMBER_OR_WORD and isinstance(value, str) and word_number(value) is not None:
        return word_number(value)
    problems.append(f"{where}: must be {_expected(spec)}, not {_given(value)}")
    return value


def conform_file(name: str, data, problems: list[str]) -> dict:
    """The file's known keys, keeping only the entries whose shape is right."""
    if not isinstance(data, dict):
        problems.append(f"{name}: must be a mapping of keys, not {_given(data)}")
        return {}
    out = dict(data)
    for key in data.keys() - FILES[name].keys() - {"format"}:  # format: project.yaml's own rules
        problems.append(f"{name}: unknown key {key!r}")
    for key, (spec, collection) in FILES[name].items():
        value, where = data.get(key), f"{name} {key}"
        if value is None:
            out.pop(key, None)
        elif collection is None:
            before = len(problems)
            out[key] = conform(value, spec, where, problems)
            if len(problems) > before:
                out.pop(key)
        elif not isinstance(value, collection):
            problems.append(
                f"{where}: must be {_NAMES[collection]} of entries, not {_given(value)}"
            )
            out.pop(key)
        else:
            kept = {}
            for k, entry in value.items() if collection is dict else enumerate(value):
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
