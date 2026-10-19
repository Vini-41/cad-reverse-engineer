# Tools adjacent to cadrev

Researched 2026-10-19. Release and commit dates are as of that day.

**Bottom line.** Nothing found here should replace a part of cadrev's core, and none of it reopens a spec #1 decision. The best candidates are narrow. **pdfplumber** (MIT) could give ledger entries page and bounding-box locators and give table cells structure. **pint** is useful only as a *test-time* oracle for the unit table's conversion factors: as a runtime parser it reads several hardware-paper spellings silently wrong. That supports the decision to keep a built-in unit table. **bd_warehouse** is a good geometry generator for stock parts, but it cannot back a `standard` basis by itself. Its CSV tables name a standard but not its edition or clause, they take the maximum of each toleranced range, and they had transcription errors fixed as recently as 2026-10-16. If the `standard` basis comes back, the standard or the catalogue has to be the source and has to be quoted like any other source. OCR of figure text stays deferred: any engine can only *propose* a reading, which still awaits human confirmation (ADR-0002). Among published LLM-CAD work, none traces dimensions back to a source the way cadrev does. Its verification is either geometric similarity to a ground-truth model, which cadrev does not have, or VLM render-and-ask, which yields no number. CAD-bench's deterministic dimension, pose and thread checks in build123d are the closest relative.

---

## 1. Standard-part libraries for build123d

| Tool | What it does | License | Maintained? | Fit for cadrev |
|---|---|---|---|---|
| [bd_warehouse](https://github.com/gumyr/bd_warehouse) | build123d parts: fasteners, nuts, washers, threads (ISO, ACME, BSPP, bottle), bearings, gears, sprockets, pipes, flanges, O-rings, retaining rings, shaft keys, OpenBuilds | Apache-2.0 | Yes: 0.4.0 on [PyPI](https://pypi.org/project/bd_warehouse/) 2026-10-07, last commit 2026-10-17; pins `build123d>=0.12,<0.14` | Good for generating the geometry of a stock part. Weak as evidence (see below) |
| [cq_warehouse](https://github.com/gumyr/cq_warehouse) | The same author's CadQuery predecessor, sharing the data tables | Apache-2.0 | Commits through 2026-10-16; the README installs it from git | None: it targets CadQuery |
| [cq_gears](https://github.com/meadiode/cq_gears) | Involute gears for CadQuery | Apache-2.0 | Last push 2024-12-27 | None |
| [FreeCAD Fasteners WB](https://github.com/shaise/FreeCAD_FastenersWB) | FreeCAD fastener catalogue | GPL-2.0 | Last push 2026-09-10 | None: GPL and FreeCAD-bound |

**How bd_warehouse sources its dimensions.** Each table is a CSV in [`src/bd_warehouse/data/`](https://github.com/gumyr/bd_warehouse/tree/main/src/bd_warehouse/data). A table's columns are keyed by the standard's designation, for example `hex_head_parameters.csv` has columns `din931:k`, `iso4014:s`, … per size row `M2-0.4`, and `din471.csv` / `din472.csv` hold circlips. No row cites an edition, a table or a clause. The docs send the reader to "manufacture's websites or from the standard document itself" ([fastener.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/fastener.rst), [bearing.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/bearing.rst)). For bearings they point at an SKF catalogue PDF and label the type "SKT". The library "generally uses the maximum sizes when a range is available" ([fastener.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/fastener.rst)), so a modelled value is a reconstruction choice made from a toleranced range, not a value the standard states. Bearings have "accurate external dimensions but simplified internal structure" ([bearing.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/bearing.rst)). The tables are not error-free. [cq_warehouse PR #90](https://github.com/gumyr/cq_warehouse/pull/90), merged 2026-10-16, fixed three of them, M3 pitch `0.45` to `0.5` and the ISO 4035 M14 width across flats `22` to `21` among them, and its title says it aligns the data "with bd_warehouse main".

**Judgement.** A `standard` basis backed by bd_warehouse would let a param trace to an unpinned CSV row. That is exactly the untraced number the ledger exists to prevent. If the trigger fires, the honest shape is this:

1. Register the standard or the manufacturer catalogue as a source and quote its row or cell, as for any datasheet.
2. Use bd_warehouse only to *build* the part.
3. Let the checks compare the built solid with the quoted values.

ISO and DIN documents are sold, and their redistribution terms are *unconfirmed* here, because iso.org returned 403. Under ADR-0003 they would then stay out of git, so a `standard` basis probably depends on `cadrev fetch` or on a freely published manufacturer catalogue. This couples two deferred items. The dogfood run did not fire the `standard` trigger ([run log](../dogfood/legclaw-run-log.md#out-of-scope-triggers)).

## 2. Units libraries and quantity extraction

| Tool | What it does | License | Maintained? | Fit for cadrev |
|---|---|---|---|---|
| [pint](https://github.com/hgrecco/pint) | Unit registry and expression parser | BSD ([PyPI](https://pypi.org/project/Pint/)) | Yes: 0.26.1 on 2026-09-10 | Test-time oracle only. Wrong as a runtime parser (probe below) |
| [astropy.units](https://pypi.org/project/astropy/) | Units inside astropy | BSD-3-Clause | Yes: 8.0.2 on 2026-10-15 | No: it pulls in all of astropy, `1/4 in` and `kgf cm` fail, and the angle is typed as `angle` |
| [unyt](https://pypi.org/project/unyt/) | Units on numpy and sympy | BSD-3-Clause | 3.1.0 on 2026-01-15 | No: `from_string` rejects `1/4 in`, `g/cm3` and `40%` |
| [quantities](https://pypi.org/project/quantities/) | numpy-array units | BSD (per [repo](https://github.com/python-quantities/python-quantities)) | 0.16.4 on 2026-01-16 | Not probed. It has no free-text parser that I could find (*unconfirmed*) |
| [quantulum3](https://github.com/nielstron/quantulum3) | Extracts quantities from free text, with a classifier for ambiguous units | MIT | 0.10.0 on 2026-03-09 | No: silent misreadings (probe below) |
| [grobid-quantities](https://github.com/lfoppiano/grobid-quantities) | CRF/BERT tagging of measurements in scientific text, normalized to SI | Apache-2.0 | v0.8.2 on 2025-05-16, commits to 2026-09-13 | No: a Java service with modest accuracy (below) |

**Probe** (my run on 2026-10-19 with pint 0.26.1, `UnitRegistry().parse_expression`, and quantulum3 0.10.0 `parser.parse`). Unit definitions are from pint's [`default_en.txt`](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt).

- pint misreads hardware-paper spellings without raising:
  - `1 1/2 in` → **0.5 inch**: juxtaposition multiplies, 1 × 1/2.
  - `37×6.5×5 mm` → **1202.5 mm**: a registry preprocessor turns `×` into `*`.
  - `mil` is the angular mil (π/3200 rad), not a thou.
- pint raises on `3–5 mm`, `3-5 mm`, `1-1/2 in`, `M3`, `30◦` (the ring operator that papers print for °) and `4 in total`.
- pint's degree is *dimensionless*: `(1*degree).is_compatible_with(percent)` is `True`. So `[unit-quantity]` could not tell an angle from a fraction (ADR-0004).
- pint parses `4 cm`, `30°`, `1/4 in`, `40%`, `3300 mAh`, `g/cm³`, `g/cc` and `N·m` correctly. Its parser is Python's `tokenize` (`pint/pint_eval.py`), and it accepts custom `preprocessors`.
- Core install: pint plus `flexcache`, `flexparser`, `platformdirs` and `typing-extensions`, about 1.6 MB on disk as I measured it.
- quantulum3 reads `3–5 mm` as **one quantity of 4.0 mm**, the midpoint. Its own [README](https://github.com/nielstron/quantulum3) shows a range parsed as two quantities, so the behaviour differs from the documentation. It reads `an M3 screw` as **1.0 cubic metre** and `30◦` as a dimensionless 30. It returns nothing for `37×6.5×5 mm` and `1-1/2 in`.
- grobid-quantities scores end to end on MeasEval at F1 **57.52 strict / 70.23 soft** for quantities ([evaluation-scores.md](https://github.com/lfoppiano/grobid-quantities/blob/master/doc/evaluation-scores.md)).

**Judgement.** Every library here fails cadrev's central requirement, which is never to overclaim. Each reads some spelling silently wrong, and the extractors guess where cadrev must either match exactly or refuse. Spec #1's decision (a small built-in table, no units dependency; ADR-0001, ADR-0004) holds, and these results strengthen it. The cheap win is a test that cross-checks the SI factor of every `units.UNITS` entry against pint, kept as a test extra and never imported at runtime.

## 3. PDF text, table and figure extraction; OCR

| Tool | What it does | License | Maintained? | Fit for cadrev |
|---|---|---|---|---|
| [pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html) (current) | Text layer, with `extraction_mode="layout"`; image extraction | BSD-3-Clause | Yes: 6.21.1 on 2026-10-17 | Keep. "pypdf will also never be able to extract text from images" |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Per-character coordinates, `crop(bbox)`, table extraction, visual debugging. "Works best on machine-generated, rather than scanned, PDFs" | MIT; dependencies pdfminer.six (MIT) and [pypdfium2](https://pypi.org/project/pypdfium2/) (BSD-3 / Apache-2.0) | Yes: 0.11.10 on 2026-06-15 | **Best candidate**: page and bbox locators, table-cell structure, text labels in vector figures |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | The layout engine under pdfplumber | MIT | 20260107 | Only through pdfplumber |
| [PyMuPDF](https://pypi.org/project/PyMuPDF/) | Fast text, image and rendering | AGPL-3.0 or Artifex commercial | Yes: 2.0 on 2026-10-19 | **No**: AGPL is wrong for an MIT-licensed shipped skill |
| [GROBID](https://github.com/grobidOrg/grobid) | Java service that structures papers into TEI, with "PDF coordinates for extracted information". CRF by default, deep-learning models optional | Apache-2.0 | Yes: 0.9.1 on 2026-08-04 | Low: a heavy service. Its strength is metadata and references, not dimensions |
| [Nougat](https://github.com/facebookresearch/nougat) | Vision transformer that turns a PDF into markup | Code MIT, **weights CC-BY-NC** | Last release 0.1.17 in 2023-10, last push 2025-02 | **No**: on 1.5% of test pages it "degenerates into repeating the same sentence" ([paper](https://arxiv.org/html/2308.13418)). Generated text cannot be a verbatim quote |
| [Marker](https://github.com/datalab-to/marker) | ML PDF-to-Markdown | Code Apache-2.0, **weights modified OpenRAIL-M** (commercial limits) | Yes: 2.0.0 on 2026-07-20 | No, for the same reason, plus the weights license |
| [Docling](https://github.com/docling-project/docling) | Layout, reading order, table structure, OCR, chart-to-table | MIT code; models "refer to the model licenses" | Yes: 2.140.0 on 2026-10-16 | Possible for tables later; heavy, and its table text is model output |
| [Camelot](https://github.com/camelot-dev/camelot) | Table extraction (lattice, stream, network, hybrid, optional ML/OCR) | MIT | Yes: 2.0.0 on 2026-06-04 | Behind pdfplumber: more dependencies, for the same deterministic parsers |
| [tabula-py](https://github.com/chezou/tabula-py) | Wrapper for tabula-java | MIT | 2.10.0 on 2024-10-17 | No: needs Java 8+ |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | Classical OCR engine | Apache-2.0 | 5.5.3 on 2026-07-24 | The OCR candidate if the trigger fires: deterministic, but a system binary |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) / [docTR](https://github.com/mindee/doctr) | Deep-learning OCR | Apache-2.0 | v3.7.0 on 2026-06-11 / v1.1.0 on 2026-08-21 | Alternatives. Heavy frameworks |
| [EasyOCR](https://github.com/JaidedAI/EasyOCR) | Deep-learning OCR | Apache-2.0 | 1.7.2 on 2024-09-24 | No: stale |
| [eDOCr2](https://github.com/javvi51/edocr2) | Segmentation and OCR for mechanical drawings: dimensions, GD&T frames | MIT | Last push 2025-01-22 | Worth a look only when a source is an engineering drawing. Its predecessor eDOCr reports about 90% detection precision and recall and a character error rate under 8% ([Frontiers 2023](https://www.frontiersin.org/articles/10.3389/fmtec.2023.1154132/full)) |

**Judgement.** The ledger's quotes must match the text that `cadrev text` prints. That rules out every generative extractor (Nougat, Marker, Docling's VLM pipeline), because its output is not the document's text.

Of the deterministic tools, pdfplumber adds three things pypdf lacks. A quote can carry a page and a bbox, so the report could show the quote highlighted. A table cell can be ledgered with its row and column, which closes the "unitless cells of tables are yours" hole in the coverage sweep. And a dimension label printed as text inside a *vector* figure can be found without OCR. Switching extractors changes the text the matcher sees, so existing verbatim quotes would need migrating, or the extractor would need to be recorded per source.

OCR (spec #1, deferred) did not fire in the dogfood run. If it fires, an OCR result is a *suggested* reading: it may pre-fill `reading`, but the reading stays unconfirmed until a named human confirms it (ADR-0002).

## 4. Prior art: CAD from papers, drawings and images; LLM CAD and its verification

| Work | What it does | License / venue | Date | Verification it uses | Borrowable? |
|---|---|---|---|---|---|
| [Text2CAD](https://arxiv.org/abs/2409.17106) ([code](https://github.com/SadilKhan/Text2CAD)) | Text prompts from beginner to expert level → sketch-extrude sequences | NeurIPS 2024; code CC-BY-NC-SA | 2024-09 | Visual quality, parametric precision, geometric accuracy against ground truth | No: needs ground truth |
| [Text-to-CadQuery](https://arxiv.org/abs/2505.06507) | Fine-tuned LLMs → CadQuery, with 170K annotations | arXiv | 2025-05 | Exact match 69.3%, Chamfer distance down 48.6% | No |
| [CAD-Recode](https://arxiv.org/abs/2412.14042) ([code](https://github.com/filaPro/cad-recode)) | Point cloud → CadQuery Python | arXiv (ICCV mention *unconfirmed*); code CC-BY-NC-4.0 | 2024-12 / 2025-03 | Chamfer distance, IoU, invalidity ratio | Only if a source ships a scan or mesh |
| [CADCodeVerify](https://arxiv.org/abs/2410.05340) | VLM writes CAD code, renders it, asks and answers its own validation questions, then fixes | ICLR 2025 | 2024-10 / 2025-02 | Render plus VLM Q&A; point-cloud distance and compile rate on CADPrompt (200 prompts) | Render-and-ask as advice only, like overlays |
| [CAD2Program](https://arxiv.org/abs/2412.11892) | Raster 2D drawing → 3D parametric program through a ViT | AAAI 2025 | 2024-12 | Against a cabinet dataset | No |
| [MUSE](https://arxiv.org/abs/2605.28579) | Text-to-CAD benchmark (CadQuery): code check, geometric check, design-intent rubric | arXiv | 2026-05 | Rubric | No |
| [CAD-bench](https://icml.cc/virtual/2026/67851) ([repo](https://github.com/CAD-bench/cad-bench)) | 17 build123d tasks, from solids to threaded pairs and gear trains | ICML 2026; MIT | 2026 | "dimensional and pose verification, reference-geometry gates, thread-profile analysis, and Blender-based rigid-body simulation" | **Yes**: closest to cadrev checks |
| [Zoo Text-to-CAD / Zookeeper](https://github.com/KittyCAD/documentation/blob/main/content/research/zookeeper.mdx) | Commercial agent writing KCL against Zoo's B-rep engine | Proprietary service (clients MIT) | Text-to-CAD 2023-12, Zookeeper 2026-01 | Executes the model; multi-view snapshots; mass, centre of mass, area and volume tools | Ideas only. Its roadmap's "reverse engineering" means STEP/STL → KCL, not papers |

**Judgement.** I found no tool that reconstructs from a paper while tracing each dimension to a quote, or that separates stated values from chosen ones (this is the extent of my search, not proof of absence). The research line measures similarity to a ground-truth model (Chamfer distance, IoU), which cadrev does not have: its truth is the ledger. VLM render-and-ask (CADCodeVerify, Zookeeper snapshots) produces no number a check could compare, so at most it could produce a suggestion for a human, the role cadrev's overlays already fill. Two lessons do carry over. CAD-bench's deterministic, task-specific geometric checks support cadrev's design of comparing against the evidence rather than against an appearance. And its finding that agents "fail frequently on interfaces, standards-like details" is a reason to watch the `standard` trigger. Where a source does ship geometry, such as a supplementary STEP or STL, a mesh-distance check (Chamfer distance or IoU) would become a legitimate check kind.

---

## Recommendations (ranked by value)

1. **Cross-check the unit table against pint at test time.** It touches spec #1 (no external units dependency) and ADR-0001/0004, and keeps both: pint goes in the `test` extra only, and the runtime does not import it. A test asserts that each `units.UNITS` entry's `si` factor equals pint's conversion. Trigger: none needed; it is cheap now. This **reaffirms** the spec #1 decision: pint, quantulum3, unyt and astropy each misread or reject spellings that cadrev handles, and pint treats degrees as compatible with percent.
2. **pdfplumber for locators and table cells.** It touches ADR-0001 (the quote is the matcher's text) and the coverage sweep's blind spot for unitless table cells. Trigger: a project whose table pypdf flattens beyond quoting, or a review that needs a quote shown in place on the page. The cost is migrating existing quotes, or recording the extractor per source.
3. **If the `standard` basis comes back, quote the standard; do not cite bd_warehouse.** It touches spec #1 (`standard` deferred), ADR-0003 and `cadrev fetch`. Trigger, unchanged: proposed values that are really stock sizes. Shape: the catalogue or standard is a source, the param is `source`, bd_warehouse may build the part, and the checks confirm it. ISO/DIN copyright likely forces `cadrev fetch` or free manufacturer catalogues, which couples two deferred items. This does not argue to reopen the deferral.
4. **A mesh-distance check for sources that ship geometry.** It touches checks.yaml (a new check kind) and no ADR. Trigger: a project whose source includes a STEP, STL or scan of the object. Borrow Chamfer distance and IoU from CAD-Recode and Text-to-CadQuery.
5. **OCR stays deferred; when its trigger fires, Tesseract pre-fills readings that still await confirmation.** It touches spec #1 (OCR deferred) and ADR-0002. Trigger, unchanged: the dogfood run misses figure-only dimensions. Do not use generative extractors (Nougat, Marker) for anything that becomes a quote. Consider eDOCr2 only for engineering-drawing sources.
6. **Do not adopt** PyMuPDF (AGPL), quantulum3 or grobid-quantities (both misread), Nougat or Marker (generated text, weights licenses), or tabula-py (Java).

No finding argues to reopen runtime parameter trace or multi-object subassemblies.

## Sources

- bd_warehouse: [repo](https://github.com/gumyr/bd_warehouse), [data tables](https://github.com/gumyr/bd_warehouse/tree/main/src/bd_warehouse/data), [fastener.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/fastener.rst), [bearing.rst](https://github.com/gumyr/bd_warehouse/blob/main/docs/bearing.rst), [PyPI](https://pypi.org/project/bd_warehouse/)
- cq_warehouse: [repo](https://github.com/gumyr/cq_warehouse), [PR #90](https://github.com/gumyr/cq_warehouse/pull/90); [cq_gears](https://github.com/meadiode/cq_gears); [FreeCAD_FastenersWB](https://github.com/shaise/FreeCAD_FastenersWB)
- pint: [repo](https://github.com/hgrecco/pint), [default_en.txt](https://github.com/hgrecco/pint/blob/master/pint/default_en.txt), [PyPI](https://pypi.org/project/Pint/); [astropy](https://pypi.org/project/astropy/); [unyt](https://pypi.org/project/unyt/); [quantities](https://github.com/python-quantities/python-quantities)
- [quantulum3](https://github.com/nielstron/quantulum3); grobid-quantities: [repo](https://github.com/lfoppiano/grobid-quantities), [evaluation scores](https://github.com/lfoppiano/grobid-quantities/blob/master/doc/evaluation-scores.md)
- [pypdf text extraction docs](https://pypdf.readthedocs.io/en/stable/user/extract-text.html); [pdfplumber](https://github.com/jsvine/pdfplumber); [pdfminer.six](https://github.com/pdfminer/pdfminer.six); [pypdfium2](https://pypi.org/project/pypdfium2/); [PyMuPDF](https://pypi.org/project/PyMuPDF/); [GROBID](https://github.com/grobidOrg/grobid)
- Nougat: [repo](https://github.com/facebookresearch/nougat), [paper](https://arxiv.org/abs/2308.13418) ([HTML](https://arxiv.org/html/2308.13418)); [Marker](https://github.com/datalab-to/marker); [Docling](https://github.com/docling-project/docling); [Camelot](https://github.com/camelot-dev/camelot); [tabula-py](https://github.com/chezou/tabula-py)
- OCR: [Tesseract](https://github.com/tesseract-ocr/tesseract), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [docTR](https://github.com/mindee/doctr), [EasyOCR](https://github.com/JaidedAI/EasyOCR), [eDOCr2](https://github.com/javvi51/edocr2), [eDOCr paper](https://www.frontiersin.org/articles/10.3389/fmtec.2023.1154132/full)
- Prior art: [Text2CAD](https://arxiv.org/abs/2409.17106), [Text-to-CadQuery](https://arxiv.org/abs/2505.06507), [CAD-Recode](https://arxiv.org/abs/2412.14042) ([HTML](https://arxiv.org/html/2412.14042v2), [code](https://github.com/filaPro/cad-recode)), [CADCodeVerify](https://arxiv.org/abs/2410.05340), [CAD2Program](https://arxiv.org/abs/2412.11892), [MUSE](https://arxiv.org/abs/2605.28579), [CAD-bench](https://icml.cc/virtual/2026/67851) ([repo](https://github.com/CAD-bench/cad-bench)), [Zookeeper](https://github.com/KittyCAD/documentation/blob/main/content/research/zookeeper.mdx), [Introducing Text-to-CAD](https://github.com/KittyCAD/documentation/blob/main/content/posts/introducing-text-to-cad.mdx)
- In-repo: [GLOSSARY.md](../../GLOSSARY.md), [docs/adr/](../adr/), [legclaw run log](../dogfood/legclaw-run-log.md), `gh issue view 1` (spec #1, Out of Scope)
