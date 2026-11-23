"""Small reconstruction projects, built and verified through the cadrev CLI alone.

Two projects serve the suite: `proj_dir`, a link with two holes from a five-line paper, and
`mech_dir`, a slider-crank whose closed form is one cosine. A test changes one of them with `add`,
`change`, `meta` and `remodel`, runs `check`, and reads the findings and report.json.
"""

import contextlib
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml
from build123d import Box, Cylinder, Pos, export_step, export_stl

from cadrev import cli  # noqa: TID251

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "plugin" / "skills"
# The skill that ships the CLI and the file formats; the other two use them from beside it.
SKILL = SKILLS / "build-model"
PASSING = ("VERIFIED PENDING REVIEW", "VERIFIED")
STATUSES = ("NOT VERIFIED", *PASSING, "PARTIAL")
REFUSED = "the project was not read, so no report was written"


def pytest_configure(config):
    # Registered here because pytest's rootdir is the repo, which holds no pytest config.
    config.addinivalue_line("markers", "slow: runs cadrev check on a whole example project")


PAPER = """\
Table 1. Dimensions of key components
Name L×H×W (mm×mm×mm)
Link 40×8×5
The pivot holes of the link are spaced 30 mm apart.
Tests used branches of 60 mm diameter.
"""
ASSEMBLY = '"assembly": {"link_1": ("link", Location())},'
MODEL = f"""\
from build123d import *


def build(p):
    link = Box(p.link_L, p.link_W, p.link_H)
    link -= Pos(-p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    link -= Pos(p.pitch / 2, 0, 0) * Cylinder(p.hole_d / 2, p.link_H)
    datums = {{
        "link.a": (-p.pitch / 2, 0, 0),
        "link.b": (p.pitch / 2, 0, 0),
        "link.top": (-p.pitch / 2, 0, p.link_H / 2),
        "link.wall": ((p.hole_d - p.pitch) / 2, 0, 0),
        "link.side": (0, p.link_W / 2, 0),
        "link.over": (0, 0, p.link_H / 2),
        "link.under": (0, 0, -p.link_H / 2),
    }}
    return {{
        "parts": {{"link": link}},
        "datums": datums,
        {ASSEMBLY}
    }}
"""
LINK = {
    "evidence.yaml": """\
evidence:
  - {id: T1-link, source: paper, locator: Table 1, quote: "Link 40×8×5",
     values: {L: 40, H: 8, W: 5}}
  - {id: pitch, source: paper, locator: Sec. 2, quote: spaced 30 mm apart, values: {pitch: 30}}
skipped:
  - {source: paper, quote: branches of 60 mm diameter, reason: test condition}
conflicts: []
""",
    "params.yaml": """\
params:
  link_L: {basis: source, from: T1-link.L, interpretation: envelope along X}
  link_H: {basis: source, from: T1-link.H}
  link_W: {basis: source, from: T1-link.W}
  pitch: {basis: source, from: pitch.pitch}
  hole_d: {basis: proposed, value: 3, rationale: M3 pin, gap: G1}
""",
    "gaps.yaml": "gaps:\n  - {id: G1, question: 'pin diameter?', ask: authors}\n",
    "checks.yaml": """\
checks:
  - {id: env, kind: bbox, part: link, evidence: T1-link, axes: {L: x, H: z, W: y}}
  - {id: pitch, kind: distance, between: [link.a, link.b], evidence: pitch, key: pitch}
  - {id: clear, kind: interference}
""",
    "model.py": MODEL,
}

# A slider-crank: crank and coupler of one length L, so with the crank at θ above the rail the
# coupler's tip, and the slider pinned to it, lie 2 L cos θ along the rail from the crank pivot.
# It is built at rest, θ = 30°, the rail under the crank and the slider, the coupler over them,
# and turns from θ = 10° to 80°: short of 0° and 90°, where its two ways of closing meet. The
# slider is a shoe as long as the crank, which the crank's hub runs into past θ = 73°.
MECH_PAPER = """\
The crank and the coupler are each 40 mm long, and at rest the crank stands 30° above the rail.
Turned 30° on, the crank stands 60° above the rail and the slider 40 mm from the crank pivot.
The crank turns from -20° to 50° from rest.
The linkage weighs 6.1 g with its 2 g slider, printed in resin of 1.2 g/cm3.
"""
INPUT_RANGE = '"range": ["input_min", "input_max"]'
KNEE = '"drive": "passive"},  # knee'
SLIDE = """"slide": {"type": "slide", "parent": "rail_1", "child": "slider_1",
                      "axis": ["slider_1.a", "slider_1.x"], "drive": "passive"},"""
LOOP = '"loops": {"closure": ["coupler_1.down", "slider_1.up"]},'
MECH_MODEL = f"""\
import math

from build123d import *


def bar(p, length):
    body = Pos(length / 2, 0, 0) * Box(length + p.W, p.W, p.H)
    for x in (0, length):
        body -= Pos(x, 0, 0) * Cylinder(p.hole / 2, p.H)
    return body


def build(p):
    rest = math.radians(p.rest)
    bx, by = p.L * math.cos(rest), p.L * math.sin(rest)
    lengths = {{"rail": 2 * p.L, "crank": p.L, "coupler": p.L, "slider": 0}}
    parts = {{name: bar(p, length) for name, length in lengths.items()}}
    parts["slider"] = Box(p.L, p.W, p.H) - Cylinder(p.hole / 2, p.H)
    datums = {{"slider.x": (p.L / 2, 0, 0)}}
    for name, length in lengths.items():
        datums[f"{{name}}.a"] = (0, 0, 0)
        datums[f"{{name}}.up"] = (0, 0, p.H / 2)
        datums[f"{{name}}.d"] = (length, 0, 0)
        datums[f"{{name}}.down"] = (length, 0, -p.H / 2)
        datums[f"{{name}}.top"] = (length, 0, p.H / 2)
    return {{
        "parts": parts,
        "datums": datums,
        "assembly": {{
            "rail_1": ("rail", Location()),
            "crank_1": ("crank", Location((0, 0, p.H), (0, 0, p.rest))),
            "coupler_1": ("coupler", Location((bx, by, 2 * p.H), (0, 0, -p.rest))),
            "slider_1": ("slider", Location((2 * bx, 0, p.H))),
        }},
        "joints": {{
            "input": {{"type": "revolute", "parent": "rail_1", "child": "crank_1",
                      "axis": ["crank_1.a", "crank_1.up"], {INPUT_RANGE},
                      "drive": "actuated"}},
            "knee": {{"type": "revolute", "parent": "crank_1", "child": "coupler_1",
                     "axis": ["coupler_1.a", "coupler_1.up"],
                     {KNEE}
            {SLIDE}
        }},
        {LOOP}
    }}
"""
# The pose the paper states: the crank turned S2.turn on from rest.
TURNED = "pose: {input: S2.turn}"
MECH = {
    "evidence.yaml": """\
evidence:
  - {id: S1, source: paper, locator: Sec. 1, values: {L: 40, rest: 30},
     quote: "each 40 mm long, and at rest the crank stands 30° above the rail"}
  - {id: S2, source: paper, locator: Sec. 2, values: {turn: 30, stand: 60, reach: 40},
     quote: "Turned 30° on, the crank stands 60° above the rail and the slider 40 mm from"}
  - {id: S3, source: paper, locator: Sec. 3, values: {low: -20, high: 50},
     quote: "turns from -20° to 50° from rest"}
  - {id: S4, source: paper, locator: Sec. 4, values: {total: 6.1, slider: 2, rho: 1.2},
     quote: "weighs 6.1 g with its 2 g slider, printed in resin of 1.2 g/cm3"}
""",
    "params.yaml": """\
params:
  L: {basis: source, from: S1.L}
  rest: {basis: source, from: S1.rest}
  input_min: {basis: source, from: S3.low}
  input_max: {basis: source, from: S3.high}
  rho: {basis: source, from: S4.rho}
  slider_m: {basis: source, from: S4.slider}
  W: {basis: proposed, value: 5, rationale: a printable bar, gap: G1}
  H: {basis: proposed, value: 4, rationale: a printable bar, gap: G1}
  hole: {basis: proposed, value: 2, rationale: a printable bar, gap: G1}
parts:
  rail: {density: rho}
  crank: {density: rho}
  coupler: {density: rho}
  slider: {mass: slider_m}
""",
    "gaps.yaml": "gaps:\n  - {id: G1, question: 'bar section?', ask: authors}\n",
    "checks.yaml": f"""\
checks:
  - {{id: length, kind: distance, between: [crank.a, crank.d], evidence: S1, key: L}}
  - {{id: rest, kind: angle, instances: [rail_1, crank_1], evidence: S1, key: rest,
     between: [rail_1.top, rail_1.up, crank_1.down]}}
  - {{id: stand, kind: angle, instances: [rail_1, crank_1], evidence: S2, key: stand,
     between: [rail_1.top, rail_1.up, crank_1.down], {TURNED}}}
  - {{id: reach, kind: distance, instances: [rail_1, coupler_1], evidence: S2, key: reach,
     between: [rail_1.a, coupler_1.d], along: x, {TURNED}}}
  - {{id: swing, kind: range, joint: input, ends: [S3.low, S3.high]}}
  - {{id: mass, kind: mass, evidence: S4, key: total, tol_rel: 0.05}}
""",
    "model.py": MECH_MODEL,
}
# What replaces LOOP in an open chain, where no loop ties the knee and the slide to the crank: a
# coupling folding the coupler back twice as fast as the crank turns, which keeps its tip on the
# rail as the loop does; a lead screw; and a cable from the crank pivot to the slider, the path a
# stroke check reads.
FOLD = '"couplings": {"fold": {"driver": "input", "driven": "knee", "ratio": "fold"}},'
SCREW = '"couplings": {"screw": {"driver": "input", "driven": "slide", "lead": "lead"}},'
CORD = '"cables": {"cord": {"path": ["rail_1.up", "slider_1.down"]}},'


def write(root: Path, name: str, data) -> None:
    text = data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False)
    (root / name).write_text(text, encoding="utf8")


def edit(root: Path, name: str, change) -> None:
    """Change a project file's data in place."""
    path = root / name
    data = (yaml.safe_load(path.read_text(encoding="utf8")) if path.exists() else None) or {}
    change(data)
    write(root, name, data)


def swap(text: str, old: str, new: str) -> str:
    """text with old replaced by new, failing when old is absent, so no change is a no-op."""
    assert old in text, f"{old!r} is not in the text it should replace"
    return text.replace(old, new)


def remodel(root: Path, old: str, new: str) -> None:
    write(root, "model.py", swap((root / "model.py").read_text(), old, new))


def add_line(root: Path, line: str) -> None:
    """Make line the first statement of build(), on model.py line 5."""
    remodel(root, "def build(p):\n", f"def build(p):\n    {line}\n")


_FILES = {
    "evidence": "evidence.yaml",
    "skipped": "evidence.yaml",
    "conflicts": "evidence.yaml",
    "datums": "evidence.yaml",
    "params": "params.yaml",
    "parts": "params.yaml",
    "checks": "checks.yaml",
    "gaps": "gaps.yaml",
    "sources": "project.yaml",
    "make": "plan.yaml",
    "buy": "plan.yaml",
    "steps": "plan.yaml",
}


def add(root: Path, **entries) -> None:
    """Add to the project's collections, each as data or as YAML text: an entry or a list of them
    for evidence, skipped, conflicts, checks, gaps and the plan's steps; a mapping of
    names for params, parts, datums and the plan's make and buy."""
    for key, given in entries.items():
        new = yaml.safe_load(given) if isinstance(given, str) else given

        def apply(d, key=key, new=new):
            if key in ("params", "parts", "datums", "make", "buy"):
                d[key] = (d.get(key) or {}) | new
            else:
                d[key] = (d.get(key) or []) + (new if isinstance(new, list) else [new])

        edit(root, _FILES[key], apply)


def change(root: Path, key: str, name, /, **fields) -> None:
    """Set fields of the entry called name (its id, or its name in a mapping) in a collection;
    a field set to None is removed."""

    def apply(d):
        entries = d[key]
        entry = (
            entries[name]
            if isinstance(entries, dict)
            else next(e for e in entries if e.get("id") == name)
        )
        entry.update(fields)
        for field in [f for f, value in fields.items() if value is None]:
            del entry[field]

    edit(root, _FILES[key], apply)


def meta(root: Path, **keys) -> None:
    """Set project.yaml's top-level keys; one set to None is removed."""

    def apply(d):
        d.update(keys)
        for key in [k for k, value in keys.items() if value is None]:
            del d[key]

    edit(root, "project.yaml", apply)


def place(root: Path, **instances: str) -> None:
    """Replace the link project's assembly: each instance of the link at the Location given as
    model.py source."""
    placed = ", ".join(f'"{name}": ("link", {at})' for name, at in instances.items())
    remodel(root, ASSEMBLY, f'"assembly": {{{placed}}},')


def stack(root: Path, count: int) -> None:
    """Place up to three links, each one link height above the last: link_1, link_2, link_3."""
    lifts = ["0", "p.link_H", "2 * p.link_H"]
    place(root, **{f"link_{i + 1}": f"Location((0, 0, {lifts[i]}))" for i in range(count)})


M3 = "screw: {basis: proposed, thread: M3, rationale: the pins are M3 screws, gap: G1}"
# The same thread as a screw: its length is the param screw_len, which a test adds.
M3_SCREW = M3.replace("thread: M3", "thread: M3, length: screw_len")
TEN_LONG = "screw_len: {basis: proposed, value: 10, rationale: through the link, gap: G1}"


def threaded(root: Path, size: str = "tap", spec: str = M3) -> None:
    """The link with both holes sized by a thread param, in place of hole_d, and declared for
    it: at its tap drill, or at its clearance hole."""
    edit(root, "params.yaml", lambda d: d["params"].pop("hole_d"))
    add(root, params=spec)
    remodel(root, "p.hole_d", f"p.screw.{size}")
    remodel(
        root, ASSEMBLY, ASSEMBLY + '\n        "threads": {"link.a": "screw", "link.b": "screw"},'
    )


def cadrev(*args) -> tuple[int, str]:
    """Run a cadrev command; its exit code and everything it prints."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main([str(arg) for arg in args])
    return code, out.getvalue()


class Run(NamedTuple):
    """A verification run: what it printed, the status it ended on, and the report it wrote."""

    root: Path
    out: str
    status: str
    report: dict  # report.json, or {} for a run that writes none

    @property
    def findings(self) -> list[tuple[str, str]]:
        """Each finding printed, as (level, rule)."""
        return re.findall(r"^(error|warning): \[([a-z-]+)\]", self.out, re.M)

    @property
    def rules(self) -> list[str]:
        return [rule for _, rule in self.findings]

    @property
    def errors(self) -> list[str]:
        return [rule for level, rule in self.findings if level == "error"]

    def messages(self, rule: str) -> list[str]:
        return re.findall(rf"^\w+: \[{rule}\] (.*)$", self.out, re.M)

    def result(self, check_id: str) -> dict:
        (found,) = [c for c in self.report["checks"] if c["id"] == check_id]
        return found

    @property
    def md(self) -> str:
        return (self.root / "build" / "report.md").read_text(encoding="utf8")

    @property
    def plan_md(self) -> str:
        return (self.root / "build" / "plan.md").read_text(encoding="utf8")


def check(root: Path, *flags: str) -> Run:
    """Run `cadrev check`. Whatever the project holds, the run ends on a status, exits by it,
    and writes a report unless it is partial or the project was refused."""
    code, out = cadrev("check", root, *flags)
    last = out.strip().splitlines()[-1]
    status = next((s for s in STATUSES if last.startswith(f"{s}: ")), None)
    assert status and "Traceback" not in out, out
    assert code == (0 if status in PASSING else 1), out
    report = {}
    if "Report: build/report.md" in last:
        report = json.loads((root / "build" / "report.json").read_text())
        assert report["status"] == status
    else:
        assert status == "PARTIAL" or REFUSED in last, out
    return Run(root, out, status, report)


def number(result: dict) -> float:
    """The value a check measured, which its `measured` text starts with."""
    return float(result["measured"].split()[0].rstrip("°"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register(root: Path, path: Path, sid: str, kind: str = "paper", *flags: str) -> None:
    code, out = cadrev(
        "source", root, path, "--id", sid, "--kind", kind, "--citation", f"Doe 2026, {sid}", *flags
    )
    assert code == 0, out


def add_source(root: Path, tmp_path: Path, name: str, content, sid="doc", kind="paper") -> Path:
    """Register content, saved as name, as a source; the file as the project holds it."""
    path = tmp_path / name
    path.write_bytes(content.encode() if isinstance(content, str) else content)
    register(root, path, sid, kind)
    return root / "sources" / name


def add_quote(root: Path, tmp_path: Path, text: str, quote=None, values=None, **fields) -> None:
    """Register one more text source, notes, holding text, and ledger a quote from it (the whole
    text by default) as evidence N1."""
    add_source(root, tmp_path, fields.pop("name", "notes.txt"), text, "notes")
    entry = {"id": "N1", "source": "notes", "locator": "Sec. 1", "quote": quote or text.strip()}
    add(root, evidence=entry | {"values": values or {}} | fields)


def ledgered(root: Path, tmp_path: Path, rows, **fields) -> Run:
    """Register a notes source with one paragraph per row, ledger row i's quote from it as
    evidence N<i> with its values, and run."""
    add_source(root, tmp_path, "notes.txt", "\n\n".join(row[0] for row in rows), "notes")
    for i, (_, quote, values) in enumerate(rows):
        entry = {"id": f"N{i}", "source": "notes", "locator": f"par. {i}", "quote": quote}
        add(root, evidence=entry | {"values": values} | fields)
    return check(root)


def add_reading(root: Path, **fields) -> dict:
    """Ledger a figure crop pinned by `cadrev crop`, its reading unconfirmed; return its entry."""
    from PIL import Image

    (root / "figures").mkdir(exist_ok=True)
    Image.new("RGB", (40, 20), "white").save(root / "figures" / "page2.png")
    code, out = cadrev("crop", root, "figures/page2.png", 0, 0, 20, 10, "--name", "fig2")
    assert code == 0, out
    entry = {
        "id": "F2",
        "source": "paper",
        "locator": "Fig. 2",
        "scope": "context",
        "reason": "a label",
        "image": "figures/crops/fig2.png",
        "image_sha256": out.split("image_sha256: ")[1].strip(),
        "reading": "70 mm",
    } | fields
    add(root, evidence=entry)
    return entry


def project(tmp_path: Path, paper: str, files: dict[str, str], target: str) -> Path:
    root = tmp_path / "demo"
    assert cadrev("init", root)[0] == 0
    write(root, "project.yaml", swap((root / "project.yaml").read_text(), "TODO one", target))
    add_source(root, tmp_path, "paper.txt", paper, "paper")
    for name, text in files.items():
        write(root, name, text)
    return root


@pytest.fixture
def proj_dir(tmp_path):
    """The link project: VERIFIED, with one proposed param and five check results."""
    return project(tmp_path, PAPER, LINK, "A demo link, as")


@pytest.fixture
def mech_dir(tmp_path):
    """The slider-crank project: VERIFIED, with joints, a loop and a mass model."""
    return project(tmp_path, MECH_PAPER, MECH, "A demo slider-crank, at rest, as")


def open_chain(root: Path, motion: str, **params: str) -> None:
    """The slider-crank with its loop replaced by motion (FOLD, SCREW, CORD...), which names the
    params given as YAML."""
    remodel(root, LOOP, motion)
    add(root, params={name: yaml.safe_load(spec) for name, spec in params.items()})


# Released geometry: the link as its authors released it. A released part is built in its body's
# frame, so the file holds the link where model.py builds it and a shape check compares in place.
def link_body(pitch: float = 30, extra_hole: bool = False):
    """The link as released: 40×5×8 with its two 3 mm holes pitch apart, and with extra_hole a
    2 mm hole at its middle that the built link lacks."""
    body = Box(40, 5, 8)
    for x in (-pitch / 2, pitch / 2) + ((0,) if extra_hole else ()):
        body -= Pos(x, 0, 0) * Cylinder(1 if x == 0 else 1.5, 8)
    return body


def released(root: Path, tmp_path: Path, solid=None, at=None, name="link.step", **shape):
    """Register solid (the link by default), moved by `at` where given, as geometry source
    link_step, and compare the built link with it by shape check `shape`, whose other keys `shape`
    gives (check=False for no check). Returns the file as the project holds it."""
    path = tmp_path / name
    export = export_stl if name.endswith(".stl") else export_step
    body = link_body() if solid is None else solid
    export(body if at is None else body.moved(at), str(path))
    register(root, path, "link_step", "geometry")
    if shape.pop("check", True):
        entry = {"id": "shape", "kind": "shape", "part": "link", "body": "link_step"}
        add(root, checks=entry | shape)
    return root / "sources" / name


# A cut file drawn at half size: 600 mm wide over a 300-unit viewBox, so each length doubles. Its
# group moves its two filled paths by (10, 20): the link's outline with its two holes, which the
# sheet puts at x 20..60, y 40..45 mm with holes at x 25 and 55, and a square plate at x 120..140,
# y 40..60 mm.
SHEET = """\
<svg xmlns="http://www.w3.org/2000/svg" width="600mm" height="400mm" viewBox="0 0 300 200">
  <g transform="translate(10, 20)">
    <path fill="black" fill-rule="evenodd" d="M 0 0 H 20 V 2.5 H 0 Z
      M 1.75 1.25 a 0.75 0.75 0 1 0 1.5 0 a 0.75 0.75 0 1 0 -1.5 0 Z
      M 16.75 1.25 a 0.75 0.75 0 1 0 1.5 0 a 0.75 0.75 0 1 0 -1.5 0 Z"/>
    <path fill="black" d="M 50 0 h 10 v 10 h -10 Z"/>
  </g>
</svg>
"""
LINK_AT = "sheet@30,41"
# Where model.py places the link on the sheet: its outline along Z, centred on the region at
# (40, 42.5), not turned over.
SHEET_PLACED = {LINK_AT: (40, 42.5, False)}


def place_on_sheet(root: Path, places: dict) -> None:
    """Have model.py place the link on each region places names, at (x, y) and turned over about
    X or not, each number a param citing the region."""
    entries = []
    for i, (region, (x, y, over)) in enumerate(places.items()):
        cite = {"basis": "source", "from": region}
        add(root, params={f"s{i}_x": cite | {"value": x}, f"s{i}_y": cite | {"value": y}})
        turn = ", (1, 0, 0), 180" if over else ""
        entries.append(f'"{region}": ("link", Location((p.s{i}_x, p.s{i}_y, 0){turn}))')
    remodel(root, ASSEMBLY, f'{ASSEMBLY}\n        "sheets": {{{", ".join(entries)}}},')


def sheet(root: Path, tmp_path: Path, svg: str = SHEET, places: dict = SHEET_PLACED, **shape):
    """Register svg as cut file `sheet`, have model.py place the link on it by `places`
    (place_on_sheet), and compare the built link with its region by shape check `shape`, projected
    along Z (shape gives its other keys, None dropping one; check=False for no check), skipping
    the plate by the rectangle around it."""
    add_source(root, tmp_path, "sheet.svg", svg, "sheet", "geometry")
    if places:
        place_on_sheet(root, places)
    if shape.pop("check", True):
        entry = {"id": "shape", "kind": "shape", "part": "link", "body": LINK_AT, "along": "z"}
        entry = entry | shape
        add(root, checks={k: v for k, v in entry.items() if v is not None})
        add(root, skipped={"source": "sheet", "within": [[110, 30], [150, 70]], "reason": "plate"})


def pdf(pages: list[str], image: bool = False) -> bytes:
    """A PDF with one page per text, each line drawn as text; image puts a 2×2 picture on page 1."""
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", font]
    if image:
        head = b"<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB "
        head += b"/BitsPerComponent 8 /Length 12 >>\nstream\n"
        objects.append(head + bytes(range(0, 240, 20)) + b"\nendstream")
    kids = []
    for n, text in enumerate(pages):
        draw = "".join(
            f"BT /F1 10 Tf 72 {720 - 14 * i} Td ({line}) Tj ET\n"
            for i, line in enumerate(re.sub(r"([\\()])", r"\\\1", text).splitlines())
        )
        shown = image and n == 0
        stream = (draw + "q 50 0 0 50 72 400 cm /Im1 Do Q\n" * shown).encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources "
            b"<< /Font << /F1 3 0 R >>%s >> >>"
            % (len(objects), b" /XObject << /Im1 4 0 R >>" * shown)
        )
        kids.append(len(objects))
    listed = b" ".join(b"%d 0 R" % k for k in kids)
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (listed, len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    return bytes(out + b"startxref\n%d\n%%%%EOF\n" % xref)


def docx(text: str, image: bytes | None = None, name: str = "image1.png") -> bytes:
    """A DOCX with one paragraph per line of text, and image as word/media/<name>."""
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines())
    space = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{space}">{body}</w:document>')
        if image is not None:
            z.writestr(f"word/media/{name}", image)
    return out.getvalue()


def png(size: tuple[int, int] = (4, 2), format: str = "PNG", mode: str = "RGB") -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new(mode, size, "red" if mode == "RGB" else 0).save(out, format=format)
    return out.getvalue()
