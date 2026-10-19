"""cadrev: verifiable CAD reconstruction from papers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

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


def _quoted(text: str) -> str:
    """text as a double-quoted YAML scalar, whatever quotes, colons or # it holds."""
    return json.dumps(text, ensure_ascii=False)  # a JSON string is a YAML double-quoted scalar


class _SourcesBlock(NamedTuple):
    start: int  # the first line after `sources:`
    end: int  # just past the last line of its last entry
    indent: int  # the column of each entry's "- "


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _sources_block(lines: list[str]) -> _SourcesBlock | None:
    """Where the block-style `sources:` list sits in project.yaml's lines, or None if absent.

    However project.yaml was last written: entries indented or not (PyYAML writes them flush),
    and other keys after `sources:` (PyYAML sorts them)."""
    head = next(
        (i for i, line in enumerate(lines) if re.match(r"^sources:(\s*\[\])?(\s+#.*)?\s*$", line)),
        None,
    )
    if head is None:
        return None
    end = start = head + 1
    for i in range(start, len(lines)):
        line = lines[i]
        if line[:1] not in ("", " ", "-", "#"):
            break  # the next top-level key
        if line.strip() and not line.lstrip().startswith("#"):
            end = i + 1
    items = [line for line in lines[start:end] if line.lstrip().startswith("- ")]
    return _SourcesBlock(start, end, _indent(items[0]) if items else 2)


def _rewrite_source_entry(text: str, source_id: str, fields: dict[str, str]) -> str | None:
    """text with the block-style entry for source_id given these fields, or None if not found."""
    lines = text.splitlines()
    block = _sources_block(lines)
    if block is None:
        return None
    key_col = block.indent + 2  # where an entry's keys start, the first one just after its "- "

    def key_line(entry: list[str], key: str) -> int | None:
        return next(
            (
                j
                for j, line in enumerate(entry)
                if (j == 0 or line[:key_col].isspace())
                and re.match(rf"{key}:(\s|$)", line[key_col:])
            ),
            None,
        )

    heads = [
        i for i in range(block.start, block.end) if re.match(rf"^ {{{block.indent}}}- ", lines[i])
    ]
    for head, next_head in zip(heads, heads[1:] + [block.end]):
        entry = lines[head:next_head]
        id_line = key_line(entry, "id")
        escaped = re.escape(source_id)
        if id_line is None or not re.fullmatch(
            rf"id: ({escaped}|'{escaped}'|\"{escaped}\")(\s+#.*)?\s*", entry[id_line][key_col:]
        ):
            continue
        for key, value in fields.items():
            first = key_line(entry, key)
            if first is None:
                entry.append(f"{' ' * key_col}{key}: {value}")
                continue
            # A value over several lines (wrapped, quoted with a newline, or a block scalar)
            # continues on more deeply indented lines, blank lines among them.
            last = first
            for j in range(first + 1, len(entry)):
                if entry[j].strip() and _indent(entry[j]) <= key_col:
                    break
                if entry[j].strip():
                    last = j
            entry[first : last + 1] = [f"{entry[first][:key_col]}{key}: {value}"]
        return "\n".join(lines[:head] + entry + lines[next_head:]) + "\n"
    return None


def _read_keeping_newline(path: Path) -> tuple[str, str]:
    """path's text with "\n" line ends, and the line end its first line uses, to write it back with."""
    with path.open(newline="") as f:
        text = f.read()
    newline = "\r\n" if re.match(r"[^\n]*\r\n", text) else "\n"
    return text.replace("\r\n", "\n"), newline


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
    text, newline = _read_keeping_newline(gitignore)
    lines = [
        "sources/*" if line.strip() in ("sources/", "sources") else line
        for line in text.splitlines()
    ]
    pattern = "!" + re.sub(r"([\\*?\[!#])", r"\\\1", path)
    if pattern not in lines:
        lines.append(pattern)
    gitignore.write_text("\n".join(lines) + "\n", newline=newline)


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
    fields = {"kind": args.kind, "path": path, "sha256": digest}
    fields |= {"citation": _quoted(args.citation)}
    fields |= {"url": args.url} if args.url else {}
    fields |= {"license": args.license} if args.license else {}
    text, newline = _read_keeping_newline(meta)
    if args.id in registered:
        # Restoring a source into a clone, or a fresh download: keep the entry, refresh the file
        # and whatever the command states about it.
        refreshed = _rewrite_source_entry(text, args.id, fields)
        if refreshed is None:
            print(
                f"source {args.id} is registered in a form cadrev cannot edit; set its path to "
                f"{path} and sha256 to {digest} in project.yaml",
                file=sys.stderr,
            )
            return 1
        meta.write_text(refreshed, newline=newline)
        license_id = args.license or registered[args.id].get("license")
        _unignore_if_redistributable(root, path, license_id)
        print(f"refreshed {args.id} -> {target}")
        return 0
    lines = re.sub(r"^sources:\s*\[\](\s+#.*)?\s*$", r"sources:\1", text, flags=re.M).splitlines()
    block = _sources_block(lines)
    if block is None:
        print(f"project.yaml has no block-style sources list for {args.id}", file=sys.stderr)
        return 1
    pad = " " * (block.indent + 2)
    entry = [f"{' ' * block.indent}- id: {args.id}"]
    entry += [f"{pad}{key}: {value}" for key, value in fields.items()]
    meta.write_text(
        "\n".join(lines[: block.end] + entry + lines[block.end :]) + "\n", newline=newline
    )
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
