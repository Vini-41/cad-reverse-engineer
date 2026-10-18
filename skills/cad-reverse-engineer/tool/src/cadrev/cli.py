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
# SPDX ids whose terms let anyone redistribute the file unchanged and for any purpose.
REDISTRIBUTABLE = re.compile(r"CC0-1\.0|CC-BY(-SA)?-\d\.\d", re.I)


def _print_findings(findings, stream=None) -> None:
    for f in findings:
        print(f"{f.level}: [{f.rule}] {f.message}", file=stream or sys.stdout)


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


def _rewrite_source_entry(text: str, source_id: str, fields: dict[str, str]) -> str | None:
    """text with the block-style entry for source_id given these fields, or None if not found."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(rf"^(\s*)- id: ['\"]?{re.escape(source_id)}['\"]?\s*$", line)
        if not m:
            continue
        indent = len(m.group(1)) + 2
        end = i + 1
        while end < len(lines) and (
            not lines[end].strip()
            or len(lines[end]) - len(lines[end].lstrip()) >= indent
            and not lines[end].lstrip().startswith("- ")
        ):
            end += 1
        block = lines[i + 1 : end]
        for key, value in fields.items():
            new = f"{' ' * indent}{key}: {value}"
            at = [j for j, b in enumerate(block) if re.match(rf"^\s*{key}:", b)]
            if at:
                block[at[0]] = new
            else:
                block.insert(0, new)
        return "\n".join(lines[: i + 1] + block + lines[end:]) + "\n"
    return None


def _unignore_if_redistributable(root: Path, path: str, license_id: object) -> None:
    """Un-ignore a source in the project's .gitignore when its license allows redistribution."""
    gitignore = root / ".gitignore"
    if (
        not isinstance(license_id, str)
        or not gitignore.is_file()
        or not REDISTRIBUTABLE.fullmatch(re.sub(r"\s+", "-", license_id.strip()))
    ):
        return
    # git cannot re-include a file inside an ignored directory, so ignore its contents instead.
    lines = [
        "sources/*" if line.strip() in ("sources/", "sources") else line
        for line in gitignore.read_text().splitlines()
    ]
    pattern = "!" + re.sub(r"([\\*?\[!#])", r"\\\1", path)
    if pattern not in lines:
        lines.append(pattern)
    gitignore.write_text("\n".join(lines) + "\n")


def cmd_source(args) -> int:
    root = Path(args.dir)
    src = Path(args.file)
    meta = root / "project.yaml"
    if not meta.is_file():
        print(f"{meta} not found; run cadrev init first", file=sys.stderr)
        return 1
    if not src.is_file():
        print(f"{src} not found", file=sys.stderr)
        return 1
    problems: list[proj.Finding] = []
    registered = {s["id"]: s for s in proj.read_meta(root, problems).get("sources", [])}
    if problems:
        _print_findings(problems, sys.stderr)
        return 1
    target = root / "sources" / (args.rename or src.name)
    target.parent.mkdir(exist_ok=True)
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)
    path, digest = f"sources/{target.name}", sources.sha256(target)
    text = meta.read_text()
    if args.id in registered:
        # Restoring a source into a clone, or a fresh download: keep the entry, refresh the file.
        refreshed = _rewrite_source_entry(text, args.id, {"path": path, "sha256": digest})
        if refreshed is None:
            print(
                f"source {args.id} is registered in a form cadrev cannot edit; set its path to "
                f"{path} and sha256 to {digest} in project.yaml",
                file=sys.stderr,
            )
            return 1
        meta.write_text(refreshed)
        _unignore_if_redistributable(root, path, registered[args.id].get("license"))
        print(f"refreshed {args.id} -> {target}")
        return 0
    entry = [
        f"  - id: {args.id}",
        f"    kind: {args.kind}",
        f"    path: {path}",
        f"    sha256: {digest}",
        f"    citation: {args.citation!r}",
    ]
    entry += [f"    url: {args.url}"] if args.url else []
    entry += [f"    license: {args.license}"] if args.license else []
    text = re.sub(r"^sources: \[\]\s*$", "sources:", text, flags=re.M)
    meta.write_text(text.rstrip("\n") + "\n" + "\n".join(entry) + "\n")
    _unignore_if_redistributable(root, path, args.license)
    print(f"registered {args.id} -> {target}")
    return 0


def _open(args, source: str | None = None) -> proj.Project | None:
    """The project for a read-only command, or None after printing why it cannot be used."""
    p = proj.load(Path(args.dir))
    _print_findings(p.findings, sys.stderr)
    if p.refused:
        return None
    if source is not None and source not in p.sources:
        print(
            f"unknown source {source!r}; registered: {', '.join(p.sources) or 'none'}",
            file=sys.stderr,
        )
        return None
    return p


def cmd_text(args) -> int:
    p = _open(args, args.source)
    if p is None:
        return 1
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
    p = _open(args, args.source)
    if p is None:
        return 1
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
            region = region.resize(
                (region.width * args.zoom, region.height * args.zoom), Image.Resampling.LANCZOS
            )
        region.save(target)
    print(f"image: {target.relative_to(root)}\nimage_sha256: {sources.sha256(target)}")
    return 0


def cmd_coverage(args) -> int:
    p = _open(args)
    if p is None:
        return 1
    missing = proj.check_coverage(p)
    for sid, page, line in missing:
        print(f"{sid} p{page}: {line}")
    print(f"{len(missing)} unledgered stated quantities")
    return 1 if missing else 0


def cmd_check(args) -> int:
    from . import report

    p = proj.load(Path(args.dir))
    if p.refused:
        # Not a project, or one this cadrev cannot read: write nothing into it.
        _print_findings(p.findings)
        print(f"\n{report.status(p)}: the project was not read, so no report was written.")
        return 1
    proj.check_static(p)
    if not args.no_coverage:
        proj.check_coverage(p)
    # A partial run makes no claim, so it writes nothing to build/.
    partial = args.no_build or args.no_coverage
    results, images = [], []
    if not args.no_build and not any(
        f.rule in ("model-missing", "model-syntax") for f in p.findings
    ):
        from . import geometry, overlay

        built = geometry.build(p)
        if built is not None:
            results = geometry.run_checks(p, built)
            if not partial:
                for path in geometry.export(p, built):
                    print(f"wrote {path.relative_to(p.root)}")
                images = overlay.render(p, built)
    status = report.status(p, partial)
    headline = report.counts(p, results)
    _print_findings(p.findings)
    if partial:
        skipped = " and ".join(
            s
            for s, on in (("the build", args.no_build), ("the coverage sweep", args.no_coverage))
            if on
        )
        print(
            f"\n{status}: {headline['errors']} errors, {headline['warnings']} warnings; skipped {skipped}, "
            "so no claim is made and no report was written."
        )
        return 1
    path = report.write(p, status, results, images)
    print(
        f"\n{status}: {headline['errors']} errors, {headline['warnings']} warnings, "
        f"{headline['checks_passed']}/{headline['checks']} checks pass. Report: {path.relative_to(p.root)}"
    )
    return 0 if status in report.PASSING else 1


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

    s = sub.add_parser("coverage", help="list stated quantities no evidence or skip covers")
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
