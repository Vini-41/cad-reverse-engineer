"""The ledger: how a quote is matched and read, the units it prints, what the coverage sweep
lists, what each param rests on, and a known-first project's waiting list."""

import math

import pytest
from conftest import (
    add,
    add_quote,
    add_reading,
    add_source,
    cadrev,
    change,
    check,
    edit,
    ledgered,
    meta,
    pdf,
    png,
    sheet,
    write,
)


# A quote as its source prints it and as it was copied: (printed, quoted, whether it matches).
MATCHING = [
    ("and two dual-\naxis servos of 12 mm serve", "two dual-axis servos of 12 mm", True),
    ("and one tri-\naxis servo of 13 mm serves", "one tri- axis servo of 13 mm", True),
    ("with an inter-\ntoe gap of 14 mm", "with an intertoe gap of 14 mm", True),
    ("with an intra-\ntoe gap of 15 mm", "with an intra- toe gap of 15 mm", True),
    ("Bent Link-\nage 37 × 6.5×5", "Bent Linkage 37×6.5×5", True),
    ("A  Gap\nof 3–5 mm,   or so", "a gap of 3-5 mm, or so", True),
    ("19*12.5 mm pads", "19x12.5 mm pads", True),
    ("The rod is 137 mm long.", "37 mm long", False),
    ("The rod is 3.7 mm wide.", "7 mm wide", False),
    ("The pin is 16 mm long", "The pin is 16 mm long.", False),
    ("a shaft of 17 mm", "a shaft of 17 cm", False),
]


def test_quote_matches_across_line_breaks_spacing_case_and_dashes_but_never_inside_a_number(
    proj_dir, tmp_path
):
    rows = [(printed, quoted, {}) for printed, quoted, _ in MATCHING]
    run = ledgered(proj_dir, tmp_path, rows, scope="context", reason="matching")
    missed = {message.split(":")[0] for message in run.messages("quote-not-found")}
    assert missed == {f"N{i}" for i, row in enumerate(MATCHING) if not row[2]}
    # A quote that matches covers the quantities inside it.
    uncovered = [m.split("quantity ")[1].split("  …")[0] for m in run.messages("coverage")]
    assert uncovered == ["137 mm", "3.7 mm", "16 mm", "17 mm"]


def test_pdf_quote_matches_a_word_hyphenated_across_lines_either_way(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "notes.pdf", pdf(["with an inter-\ntoe gap of 14 mm"]), "notes")
    for i, quote in enumerate(["an intertoe gap of 14 mm", "an inter-toe gap of 14 mm"]):
        entry = {"id": f"N{i}", "source": "notes", "locator": "p. 1", "quote": quote}
        add(proj_dir, evidence=entry | {"values": {"g": 14}, "scope": "context", "reason": "test"})
    assert check(proj_dir).messages("quote-not-found") == []


# The numbers a quote states, and near misses it does not: quote -> (values in it, values not).
READING = {
    "Fig. 2 shows the 4 cm link": ([4], [2]),
    "Figs. 2 and 3 show the 5 cm link": ([5], [2, 3]),
    "Tables 1-3 list the 6 cm link": ([6], [1, 3]),
    "Eq. (6) and Sec. 4.2 give the 7 cm link": ([7], [6, 4.2]),
    "Fig. 2 in the text, then a section 4 mm thick": ([4], [2]),
    "2 sec per stride": ([2], []),
    "Hole spacing 5–10 mm": ([5, 10], [-10]),
    "tilted from -10 to -5 deg": ([-10, -5], [10, 5]),
    "The pin is 3.7 mm wide and 137 mm long.": ([3.7, 137], [37, 7]),
    "a .250 in pin, -.5 mm off, from Fig.5": ([0.25, -0.5], [250, 5, 0.5]),
    "Link 40×8×5": ([40, 8, 5], [408]),
    "Walls 3,5 mm": ([3.5], [5, 3]),
    "widths 1,5,10 mm": ([1, 5, 10], [1.5]),
    "a 1/4 inch shaft and a 1 1/2 in key": ([0.25, 1.5], [4, 0.5, 2]),
    "set -1 1/2 in back": ([-1.5], [-0.5, 1.5]),
    "a 1/4-in. bolt": ([0.25], [1, 4]),
    "gear ratio 1/50": ([1, 50], [0.02]),
    "Eight tension springs": ([8, "eight", "Eight"], [18, "seven"]),
    "twenty-four bolts, or twenty four": ([24, "twenty four"], [20, 4]),
    "eighteen springs carry the weight": ([18], [8]),
    "seventy links": ([70], [7]),
    "the first of a pair of pins": ([], [1, 2]),
    "the twenty-first of one hundred links": ([], [20, 21, 1, 100]),
    "two-thirds of the plate": ([], [2]),
}


def test_quote_states_its_numbers_in_digits_or_words_and_no_near_miss(proj_dir, tmp_path):
    rows = []
    for quote, (stated, unstated) in READING.items():
        values = {f"in{j}": v for j, v in enumerate(stated)}
        rows.append((quote, quote, values | {f"out{j}": v for j, v in enumerate(unstated)}))
    run = ledgered(proj_dir, tmp_path, rows)
    assert run.messages("schema") == []
    refused = {message.split(" = ")[0] for message in run.messages("value-not-in-quote")}
    unstated = enumerate(unstated for _, unstated in READING.values())
    assert refused == {f"N{i}.out{j}" for i, values in unstated for j in range(len(values))}


@pytest.mark.parametrize("word", ["eighth", "a pair", "dozen", "eight mm"])
def test_value_in_words_that_is_no_cardinal_is_no_number(proj_dir, tmp_path, word):
    add_quote(proj_dir, tmp_path, "Eight tension springs", values={"n": word})
    assert "evidence[2].values.n" in check(proj_dir).messages("schema")[0]


# A value as its quote prints it, and what a param reading it holds in the project's units: by
# default mm, deg, g, N and s, and what follows from them. A few of each way a unit is read.
MM = {
    "The link is 4 cm long": (4, 40),
    "a 3 centimetre boss": (3, 30),
    'a 0.5" shaft': (0.5, 12.7),
    "a 1/4 inch key": (0.25, 6.35),
    "a 2-in. plate": (2, 50.8),
    "a 5-mm pin": (5, 5),
    "a 2-in-1 tool": (2, 2),
    "a 1.5 ft boom": (1.5, 457.2),
    "a 250 μm film": (250, 0.25),
    "Walls 3–5 cm": (3, 30),
    "Plate 40×8×5 cm": (8, 80),
    "The pin is 1.000 ± 0.005 in long": (1.0, 25.4),
    "Cell 37×6.5×5": (6.5, 6.5),
    "of 12 links": (12, 12),
    "3 m long links, 4 in total": (4, 4),
    "turned 0.5 rad": (0.5, math.degrees(0.5)),
    "preset at 45◦": (45, 45),
    "weighs 0.43 kg": (0.43, 430),
    "The arm weighs 2.5 lb": (2.5, 1133.98092),
    "a 2 kN load": (2, 2000),
    "torque of 1.2 kg ·cm": (1.2, 117.6798),
    "torque of 0.3 Nm": (0.3, 300),
    "rated at 0.3 MPa": (0.3, 0.3),
    "rated at 100 kPa": (100, 0.1),
    "a resin of 1.2 g/cm3": (1.2, 0.0012),
    "a foam of 1200 kg·m−3": (1200, 0.0012),
    "a 40 ms stride": (40, 0.04),
    "moving at 2 m/s": (2, 2000),
    "spinning at 300 rpm": (300, 1800),
    "at 40% infill": (40, 0.4),
    "a 10 ml cavity": (10, 10000),
    "a spring of 0.25 N·m/rad": (0.25, 250),
    "a cord of 300 N/m": (300, 0.3),
    "a sun of 25 teeth": (25, 25),
}
# The same reader in a project that sets its own units.
CM = {
    "The link is 40 mm long": (40, 4),
    "a 0.5 in shaft": (0.5, 1.27),
    "rotated 90°": (90, math.pi / 2),
    "weighs 420 g": (420, 0.42),
    "a 2 kN load": (2, 2),
    "torque of 0.3 Nm": (0.3, 0.03),
    "a resin of 1.2 g/cm3": (1.2, 0.0012),
    "spinning at 300 rpm": (300, 10 * math.pi),
}
UNITS = {"length": "cm", "angle": "radians", "mass": "kg", "force": "kN"}


@pytest.mark.parametrize("units, table", [(None, MM), (UNITS, CM)], ids=["default", "set"])
def test_param_reads_its_quotes_value_in_the_projects_units(proj_dir, tmp_path, units, table):
    if units:
        meta(proj_dir, units=units)
    params = {f"u{i}": {"basis": "source", "from": f"N{i}.v"} for i in range(len(table))}
    add(proj_dir, params=params)
    rows = [(quote, quote, {"v": printed}) for quote, (printed, _) in table.items()]
    report = ledgered(proj_dir, tmp_path, rows).report
    read = {quote: report["params"][f"u{i}"]["value"] for i, quote in enumerate(table)}
    assert read == {quote: pytest.approx(value) for quote, (_, value) in table.items()}


def test_project_in_its_own_units_verifies_with_each_check_in_them(proj_dir, tmp_path):
    # Table 1's cells print no unit, so they are centimetres now; the pitch is 3 cm.
    meta(proj_dir, units={"length": "cm", "angle": "rad"})
    add_quote(proj_dir, tmp_path, "The holes stand 90° square to the face.", values={"sq": 90})
    angle = "{id: sq, kind: angle, between: [link.b, link.a, link.top], evidence: N1, key: sq}"
    add(proj_dir, checks=angle)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["params"]["pitch"]["value"] == 3
    assert run.result("pitch")["measured"].startswith("3 ")
    assert run.result("sq")["expected"].startswith("90 ")  # an angle is compared in degrees


# What the sweep lists in each sentence: every stated quantity whole, and no look-alike.
SWEPT = {
    'A 0.5 in shaft, a 2" bore and a 1/4 inch key.': ["0.5 in", '2"', "1/4 inch"],
    "It is 5 millimeters, 5 um or 3 ft.": ["5 millimeters", "5 um", "3 ft"],
    "An M3 screw, an M10x1.5 bolt and 4 × M2.5 nuts.": ["m3", "m10x1.5", "m2.5"],
    "Of 10 cm3, 2.5 mm² and 30◦.": ["10 cm3", "2.5 mm2", "30◦"],
    "At 5 MPa and 1.2 kg·cm.": ["5 mpa", "1.2 kg·cm"],
    "It runs at 300 rpm for 9 s at 40%.": ["300 rpm", "9 s", "40%"],
    "Walls 3,5 mm, 3–5 mm or 10,20,30 mm.": ["3,5 mm", "3-5 mm", "10,20,30 mm"],
    "Efficiency was 60–\n80% for SSPG.": ["60-80%"],
    "A 2-in. plate on a 5-mm pin, 1.000 ± 0.005 in long.": ["2-in", "5-mm", "1.000 ± 0.005 in"],
    "Wound six turns on 25 teeth by three degrees.": ["six turns", "25 teeth", "three degrees"],
    "Bores Ø 32.5 and Ø3, then Ø6 mm.": ["ø 32.5", "ø3", "ø6 mm"],
    "Pads 19*12.5 mm in cells 13*13*10.": ["19x12.5 mm", "13x13x10"],
    "Rated at 2 bar, weighs 8 g, closes in 2s over a Δt = 2 s step.": ["2 bar", "8 g", "2s", "2 s"],
    "A load of 2 N on the 10 N M4 bolt.": ["2 n", "10 n", "m4"],
    "Held by four M3 screws and 2 M4 nuts in 2 m3 of air.": ["m3", "m4", "2 m3"],
    'A 1/4-20 bolt, a 1/4"-20 UNC stud, #6-32 and 10-32 UNF screws.': [
        "1/4-20",
        '1/4"-20 unc',
        "#6-32",
        "10-32 unf",
    ],
    "A plate 5 in wide ran for 1:30 min.": ["5 in", "30 min"],
    # Look-alikes: a unit's spelling that names something else.
    "The shin is a four-bar linkage, or 4-bar.": [],
    "An onboard computer (8G; NVIDIA) and a battery (2S, HUAYPG).": [],
    "(A) T=0s, in the initial state; at t = 2 s the toes close.": [],
    "Price (EUR) 500 n.a. 20": [],
    "Pages 10-32 hold sizes 1/4-21 and 6-32.": [],
    "Fig. 2 shows 2 in each leg of L14 beside an M3a cell (doi:10.1088/ada2cc).": [],
    "An Olympus OM-D E-M10 camera on gear modules m1, m2.": [],
    "CPG:m 2N r2 =m 1(N s1 +N p1 ) +m 2N p2 ,": [],
    # A subscript on a line of its own, as PDFium extracts one, and a modulo between symbols.
    "WPG: N\nr\n1 = N\ns\n1 + 2N\np\n1, SSPG: 2(R\ns\ni + R\np\ni) sin π\n2N\np\ni": [],
    "CPG: N\ns\n1 % n\np\n1 = 0, Nr\n2 % n\np\n1 = 0, (N\ns\ni + N\nr\ni\n) % n\np\ni = 0": [],
    "Ratios from 4:1 to 60:1 in unit increments, 4:1 in total.": [],
    # Numbers that state no quantity: no unit, a count noun, a table cell.
    "The part is 32.5 here, built at Ørsted 3.": [],
    "Eight springs hold its 3 planets; SSPG [25, 65, 155, 0.5, 3] lists each.": [],
    "Price 3500* 500 g here.": ["500 g"],
}


def test_coverage_lists_each_stated_quantity_whole_and_no_look_alike(proj_dir, tmp_path):
    add_source(proj_dir, tmp_path, "notes.txt", "\n".join(SWEPT), "notes")
    lines = cadrev("coverage", proj_dir)[1].splitlines()
    listed = [line.removeprefix("notes p1: ").split("  …")[0] for line in lines[:-1]]
    assert listed == [candidate for candidates in SWEPT.values() for candidate in candidates]
    assert lines[-1] == f"{len(listed)} unledgered stated quantities"


def test_html_source_is_quoted_and_swept_as_its_rendered_text(proj_dir, tmp_path):
    page = (
        "<html><head><title>Servo 5 mm</title><style>td{width:32px}</style></head><body><p>Servo "
        "&amp; horn</p><table><tr><td>Weight</td><td>20.6 g</td></tr></table></body></html>"
    )
    add_quote(proj_dir, tmp_path, page, "Weight 20.6 g", {"m": 20.6}, name="ds.html")
    run = check(proj_dir)
    assert run.rules == ["evidence-unused"]  # found, and nothing in the markup is swept


SKIPS = {
    "a quote": "{source: doc, page: 2, quote: branches of 60 mm diameter, reason: test}",
    "a block from its first words to its last": (
        "{source: doc, from: Tests used, to: diameter., reason: test}"
    ),
    "a page": "[{source: doc, pages: [2], reason: tests}, {source: doc, pages: [1], reason: r}]",
}


@pytest.mark.parametrize("by", SKIPS)
def test_skip_sets_aside_what_it_names_and_a_quote_on_its_page_covers_the_rest(
    proj_dir, tmp_path, by
):
    # The paper again as a two-page PDF: the table, then the pitch and the test condition.
    pages = ["Table 1. Dimensions\nLink 40x8x5", "Holes spaced 30 mm apart.\nTests used "]
    pages[1] += "branches of 60 mm diameter."
    add_source(proj_dir, tmp_path, "paper.pdf", pdf(pages))
    entries = [
        {"id": "D1", "locator": "Table 1", "page": 1, "quote": "Link 40×8×5"},
        {"id": "D2", "locator": "Sec. 2", "page": 2, "quote": "spaced 30 mm apart"},
    ]
    restated = {"source": "doc", "scope": "context", "reason": "restates the paper"}
    add(proj_dir, evidence=[entry | restated for entry in entries], skipped=SKIPS[by])
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == []
    change(proj_dir, "evidence", "D2", page=None)
    assert check(proj_dir).messages("quote-page") == ["D2: add page: 2"]


def test_statement_about_what_is_not_built_keeps_its_values_out_of_the_model(proj_dir):
    extra = {"id": "rig", "source": "paper", "locator": "Sec. 3", "values": {"d": 60}}
    extra |= {"quote": "branches of 60 mm diameter", "scope": "not-modeled", "reason": "a test rig"}
    edit(proj_dir, "evidence.yaml", lambda d: d.pop("skipped"))
    add(proj_dir, evidence=extra)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and "| rig | paper | Sec. 3 | d=60 |" in run.md


def test_figure_reading_awaits_a_named_human_and_a_measured_param_scales_off_it(proj_dir):
    entry = add_reading(proj_dir, values={"w": 70}, scope="not-modeled")
    foot = "{basis: measured, from: F2, value: 5.5, method: pitch as scale, uncertainty: ±0.3 mm}"
    add(proj_dir, params=f"foot: {foot}")
    run = check(proj_dir)
    assert run.status == "VERIFIED PENDING REVIEW"
    assert run.report["awaiting_confirmation"] == [
        {"evidence": "F2", "locator": "Fig. 2", "reading": "70 mm", "image": entry["image"]}
    ]
    measured = {"param": "foot", "value": 5.5, "from": "F2", "method": "pitch as scale"}
    assert run.report["measured"] == [measured | {"uncertainty": "±0.3 mm"}]
    assert run.report["counts"]["measured"] == 1
    change(proj_dir, "evidence", "F2", confirmed_by="A. Reviewer")
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.report["awaiting_confirmation"] == []


@pytest.mark.parametrize("figure", ["paper", "photo", "sheet"])
def test_a_measured_param_scales_a_figure_of_the_object_not_a_render_of_released_geometry(
    proj_dir, tmp_path, figure
):
    sheet(proj_dir, tmp_path)
    if figure == "photo":
        add_source(proj_dir, tmp_path, "photo.png", png(), "photo", "other")
    add_reading(proj_dir, source=figure, confirmed_by="A. Reviewer")
    foot = "{basis: measured, from: F2, value: 5.5, method: by scale, uncertainty: ±0.3 mm}"
    add(proj_dir, params=f"foot: {foot}")
    run = check(proj_dir)
    if figure == "sheet":  # the cut file, a geometry source
        assert run.errors == ["param-from"]
        assert all(name in run.messages("param-from")[0] for name in ("foot", "sheet"))
    else:
        assert run.status == "VERIFIED" and run.report["measured"][0]["param"] == "foot"


def no_proposed(root) -> None:
    """Derive the hole from the link's width, so no param is proposed and no gap is asked."""
    change(root, "params", "hole_d", basis="derived", expr="link_W * 3 / 5", value=None)
    change(root, "params", "hole_d", rationale=None, gap=None)
    write(root, "gaps.yaml", "gaps: []\n")


# What a derived param rests on: the weakest basis among the params its expr reads.
RESTS = {
    "pitch / 2": "source",
    "pitch - foot": "measured",
    "pitch - hole_d": "proposed",
    "pitch - foot - hole_d": "proposed",
    "twice - pitch": "measured",
    "sqrt(twice ** 2 + max(link_L, link_W))": "measured",
}


def test_derived_param_rests_on_the_weakest_basis_its_expr_reads(proj_dir):
    add_reading(proj_dir, confirmed_by="A. Reviewer")
    foot = "{basis: measured, from: F2, value: 5.5, method: by scale, uncertainty: ±0.3 mm}"
    add(proj_dir, params=f"{{foot: {foot}, twice: {{basis: derived, expr: 2 * foot}}}}")
    add(proj_dir, params={f"r{i}": {"basis": "derived", "expr": e} for i, e in enumerate(RESTS)})
    report = check(proj_dir).report
    rests = {expr: report["params"][f"r{i}"]["rests_on"] for i, expr in enumerate(RESTS)}
    assert rests == RESTS and report["params"]["r0"]["value"] == 15
    # The headline counts the params by what they rest on, not by the basis they declare.
    counted = {basis: report["counts"][basis] for basis in ("source", "measured", "proposed")}
    assert counted == {"source": 5, "measured": 5, "proposed": 3}
    assert report["bases"] == {"source": 4, "proposed": 1, "measured": 1, "derived": 7}
    assert report["rests_on_proposed"] == ["hole_d", "r2", "r3"]


def test_project_with_no_proposed_param_is_exact_and_a_derived_choice_ends_that(proj_dir):
    no_proposed(proj_dir)
    run = check(proj_dir)
    assert (run.status, run.report["exact"]) == ("VERIFIED", True) and "**Exact**" in run.md
    # A derived param naming a gap is a reconstruction choice: it rests on proposed.
    add(proj_dir, gaps="{id: G2, question: 'where do the pins sit?'}")
    centres = "{basis: derived, expr: link_L - link_H, gap: G2, interpretation: at the end radii}"
    add(proj_dir, params=f"{{centres: {centres}, half: {{basis: derived, expr: centres / 2}}}}")
    run = check(proj_dir)
    assert (run.status, run.report["exact"]) == ("VERIFIED", False) and "**Exact**" not in run.md
    assert run.report["rests_on_proposed"] == ["centres", "half"]
    assert "| centres | 32 | derived (rests on proposed) |" in run.md
    assert "| G2 | where do the pins sit? |  | centres |" in run.md


# Known first: the link's every dimension is settled; a pin's length is stated, its diameter not.
PIN = "{id: pin, source: notes, locator: Sec. 3, quote: Each pin is 12 mm long, values: {L: 12}}"
PIN_GAP = "{id: G-pin, question: 'What diameter are the pins?', ask: authors}"


def known_first(root, tmp_path) -> None:
    no_proposed(root)
    meta(root, known_first=True)
    add_source(root, tmp_path, "notes.txt", "Each pin is 12 mm long.", "notes")
    add(root, evidence=PIN, gaps=PIN_GAP)


def test_known_first_project_lists_what_waits_in_place_of_findings(proj_dir, tmp_path):
    known_first(proj_dir, tmp_path)
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [] and run.report["exact"]
    assert "5/5 checks pass. Known first: 1 stated value waits. Report:" in run.out
    waits = {"evidence": "pin", "key": "L", "value": 12, "source": "notes", "locator": "Sec. 3"}
    asked = {"gap": "G-pin", "question": "What diameter are the pins?", "ask": "authors"}
    assert run.report["known_first"] is True
    assert run.report["waiting"] == {"values": [waits], "gaps": [asked]}
    waiting = run.md.split("## Waiting")[1].split("\n## ")[0]
    assert "| pin.L | 12 | notes | Sec. 3 |" in waiting and "| G-pin |" in waiting
    assert "**Known first**" in run.md
    assert "G-pin" not in run.md.split("## Open gaps")[1].split("\n## ")[0]
    # Without it the same project is held to every rule again.
    meta(proj_dir, known_first=None)
    run = check(proj_dir)
    assert run.rules == ["evidence-unused", "gap-unused"] and "## Waiting" not in run.md


def test_known_first_holds_no_proposed_param_but_allows_a_measured_one(proj_dir, tmp_path):
    known_first(proj_dir, tmp_path)
    add_reading(proj_dir, confirmed_by="A. Reviewer")
    foot = "{basis: measured, from: F2, value: 5.5, method: by scale, uncertainty: ±0.3 mm}"
    add(proj_dir, params=f"foot: {foot}")
    assert check(proj_dir).errors == []
    add(proj_dir, params="pin_d: {basis: proposed, value: 2, rationale: a guess, gap: G-pin}")
    run = check(proj_dir)
    assert run.errors == ["known-first"] and "param pin_d" in run.messages("known-first")[0]
    assert run.report["waiting"]["gaps"] == []  # a gap a param names is an open gap again
    assert check(proj_dir, "--no-build").errors == ["known-first"]


def test_known_first_project_with_no_part_settled_builds_nothing_and_ends_on_a_report(proj_dir):
    meta(proj_dir, known_first=True)
    write(proj_dir, "params.yaml", "params: {}\n")
    write(proj_dir, "checks.yaml", "checks: []\n")
    write(proj_dir, "gaps.yaml", "gaps:\n  - {id: G-link, question: 'How thick is the link?'}\n")
    write(proj_dir, "model.py", 'def build(p):\n    return {"parts": {}}\n')
    run = check(proj_dir)
    assert run.status == "VERIFIED" and run.rules == [] and run.report["exact"]
    assert "0/0 checks pass. Known first: 4 stated values wait. Report:" in run.out
    waiting = run.report["waiting"]
    assert [(v["evidence"], v["key"]) for v in waiting["values"]] == [
        ("T1-link", "L"),
        ("T1-link", "H"),
        ("T1-link", "W"),
        ("pitch", "pitch"),
    ]
    assert [g["gap"] for g in waiting["gaps"]] == ["G-link"]
