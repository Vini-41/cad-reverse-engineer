"""cadrev: verifiable CAD reconstruction from papers."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from . import project as proj
from . import sources

TEMPLATE = Path(__file__).parent / "template"


def cmd_init(args) -> int:
    root = Path(args.dir)
    if root.exists() and any(root.iterdir()):
        print(f"{root} is not empty", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATE, root, dirs_exist_ok=True)
    meta = root / "project.yaml"
    meta.write_text(meta.read_text().replace("NAME", args.name or root.name))
    print(f"created {root}")
    return 0


def cmd_source(args) -> int:
    root = Path(args.dir)
    src = Path(args.file)
    target = root / "sources" / (args.rename or src.name)
    target.parent.mkdir(exist_ok=True)
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)
    entry = [f"  - id: {args.id}", f"    kind: {args.kind}",
             f"    path: sources/{target.name}", f"    sha256: {sources.sha256(target)}",
             f"    citation: {args.citation!r}"]
    entry += [f"    url: {args.url}"] if args.url else []
    entry += [f"    license: {args.license}"] if args.license else []
    meta = root / "project.yaml"
    text = meta.read_text()
    if re.search(rf"^\s*- id: {re.escape(args.id)}\s*$", text, re.M):
        print(f"source {args.id} already registered", file=sys.stderr)
        return 1
    text = re.sub(r"^sources: \[\]\s*$", "sources:", text, flags=re.M)
    meta.write_text(text.rstrip("\n") + "\n" + "\n".join(entry) + "\n")
    print(f"registered {args.id} -> {target}")
    return 0


def cmd_text(args) -> int:
    p = proj.load(Path(args.dir))
    texts = sources.pages(p.source_path(args.source))
    wanted = [args.page] if args.page else range(1, len(texts) + 1)
    for n in wanted:
        text = texts[n - 1]
        if args.grep:
            for line in text.splitlines():
                if re.search(args.grep, line, re.I):
                    print(f"p{n}: {line.strip()}")
        else:
            print(f"===== {args.source} page {n}/{len(texts)} =====\n{text}")
    return 0


def cmd_figures(args) -> int:
    p = proj.load(Path(args.dir))
    out = p.root / "figures" / args.source
    for path in sources.extract_figures(p.source_path(args.source), out):
        print(path.relative_to(p.root))
    return 0


def cmd_crop(args) -> int:
    from PIL import Image

    root = Path(args.dir)
    target = root / "figures" / "crops" / f"{args.name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(root / args.image) as image:
        region = image.crop(tuple(args.box))
        if args.zoom != 1:
            region = region.resize((region.width * args.zoom, region.height * args.zoom),
                                   Image.Resampling.LANCZOS)
        region.save(target)
    print(f"image: {target.relative_to(root)}\nimage_sha256: {sources.sha256(target)}")
    return 0


def cmd_coverage(args) -> int:
    p = proj.load(Path(args.dir))
    missing = proj.check_coverage(p)
    for sid, page, line in missing:
        print(f"{sid} p{page}: {line}")
    print(f"{len(missing)} unledgered dimension candidates")
    return 1 if missing else 0


def cmd_check(args) -> int:
    from . import report

    p = proj.load(Path(args.dir))
    proj.check_static(p)
    if not args.no_coverage:
        proj.check_coverage(p)
    results, images = [], []
    if not args.no_build and not any(f.rule == "model-missing" for f in p.findings):
        from . import geometry, overlay

        built = geometry.build(p)
        if built is not None:
            for path in geometry.export(p, built):
                print(f"wrote {path.relative_to(p.root)}")
            results = geometry.run_checks(p, built)
            images = overlay.render(p, built)
    path = report.write(p, results, images)
    errors = [f for f in p.findings if f.level == "error"]
    for f in p.findings:
        print(f"{f.level}: [{f.rule}] {f.message}")
    print(f"\n{'VERIFIED' if not errors else 'NOT VERIFIED'}: {len(errors)} errors, "
          f"{len(p.findings) - len(errors)} warnings, "
          f"{sum(r.ok for r in results)}/{len(results)} checks pass. Report: {path.relative_to(p.root)}")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cadrev", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="scaffold a reconstruction project")
    s.add_argument("dir")
    s.add_argument("--name")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("source", help="copy a source into the project and pin its sha256")
    s.add_argument("dir")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--kind", required=True, choices=proj.SOURCE_KINDS)
    s.add_argument("--citation", required=True)
    s.add_argument("--url")
    s.add_argument("--license")
    s.add_argument("--rename", help="file name inside sources/")
    s.set_defaults(fn=cmd_source)

    s = sub.add_parser("text", help="print a source's extracted text, as the quote matcher sees it")
    s.add_argument("dir")
    s.add_argument("source")
    s.add_argument("--page", type=int)
    s.add_argument("--grep", help="only lines matching this regex")
    s.set_defaults(fn=cmd_text)

    s = sub.add_parser("figures", help="extract a source's embedded images to figures/<source>/")
    s.add_argument("dir")
    s.add_argument("source")
    s.set_defaults(fn=cmd_figures)

    s = sub.add_parser("crop", help="crop a figure region to figures/crops/ and print its sha256")
    s.add_argument("dir")
    s.add_argument("image", help="path relative to the project")
    s.add_argument("box", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    s.add_argument("--name", required=True)
    s.add_argument("--zoom", type=int, default=1)
    s.set_defaults(fn=cmd_crop)

    s = sub.add_parser("coverage", help="list dimension-like text no evidence or skip covers")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_coverage)

    s = sub.add_parser("check", help="verify everything, build the model, write build/report.md")
    s.add_argument("dir")
    s.add_argument("--no-build", action="store_true", help="skip model build and geometry checks")
    s.add_argument("--no-coverage", action="store_true", help="skip the coverage sweep")
    s.set_defaults(fn=cmd_check)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
