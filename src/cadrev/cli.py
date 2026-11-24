"""cadrev: verifiable CAD reconstruction from papers."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

import yaml

from . import ledger, project, sources

TEMPLATE = Path(__file__).parent / "template"


def _print(findings, stream=None) -> None:
    for f in findings:
        print(f"{f.level}: [{f.rule}] {f.message}", file=stream or sys.stdout)


def cmd_init(args) -> int:
    root = Path(args.dir)
    if root.exists() and any(root.iterdir()):
        print(f"{root} is not empty", file=sys.stderr)
        return 1
    shutil.copytree(TEMPLATE, root, dirs_exist_ok=True)
    meta = root / "project.yaml"
    # Its directory's name, as text whatever YAML would read it as: `.` has a name, `yes` is one.
    name = json.dumps(root.resolve().name, ensure_ascii=False)
    meta.write_text(meta.read_text(encoding="utf8").replace("NAME", name), encoding="utf8")
    print(f"created {root}")
    return 0


def cmd_source(args) -> int:
    """Copy a file into sources/, and write its entry in project.yaml's sources, the last key:
    a new entry, or for an id already registered the same entry with what the command states."""
    root, src = Path(args.dir), Path(args.file)
    meta = root / "project.yaml"
    for path, hint in ((meta, "; run cadrev init first"), (src, "")):
        if not path.is_file():
            print(f"{path} not found{hint}", file=sys.stderr)
            return 1
    problems: list[project.Finding] = []
    entries = project.read_meta(root, problems).get("sources", [])
    if problems:
        _print(problems, sys.stderr)
        return 1
    target = root / "sources" / (args.rename or src.name)
    target.parent.mkdir(exist_ok=True)
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)
    stated = {
        "kind": args.kind,
        "path": f"sources/{target.name}",
        "sha256": sources.sha256(target),
        "citation": args.citation,
        "url": args.url,
    }
    stated = {key: value for key, value in stated.items() if value is not None}
    entry = next((e for e in entries if e["id"] == args.id), None)
    if entry is None:
        entries.append({"id": args.id} | stated)
    else:
        entry |= stated
    # Every other key stays as written; `sources`, however it was written, is cadrev's to write,
    # as the last key.
    text = meta.read_text(encoding="utf8")
    for key, value in yaml.compose(text).value:
        if key.value == "sources":
            old = text[key.start_mark.index : value.end_mark.index].splitlines(keepends=True)
            after = len(old)  # the blank and comment lines after it are not its own
            while after and (not old[after - 1].strip() or old[after - 1].startswith("#")):
                after -= 1
            text = (
                text[: key.start_mark.index] + "".join(old[after:]) + text[value.end_mark.index :]
            )
    block = yaml.safe_dump({"sources": entries}, sort_keys=False, allow_unicode=True, width=10**6)
    meta.write_text(text.rstrip("\n") + "\n" + block, encoding="utf8")
    print(f"{'registered' if entry is None else 'refreshed'} {args.id} -> {target}")
    return 0


def _open(args) -> project.Project | None:
    """The project for a read-only command, or None after printing why it cannot be used."""
    p = project.load(Path(args.dir))
    _print(p.findings, sys.stderr)
    source = getattr(args, "source", None)
    if not p.refused and source is not None and source not in p.sources:
        print(
            f"unknown source {source!r}; registered: {', '.join(p.sources) or 'none'}",
            file=sys.stderr,
        )
        return None
    return None if p.refused else p


def cmd_text(args) -> int:
    p = _open(args)
    if p is None:
        return 1
    if not p.is_text(args.source):
        print(
            f"{args.source} is not a text source: its file is {p.source_path(args.source).name}",
            file=sys.stderr,
        )
        return 1
    texts = sources.pages(p.source_path(args.source))
    if args.page is not None and not 1 <= args.page <= len(texts):
        print(f"{args.source} has {len(texts)} page{'s' * (len(texts) != 1)}", file=sys.stderr)
        return 1
    try:
        pattern = re.compile(args.grep or "", re.I)
    except re.error as exc:
        print(f"--grep {args.grep!r} is not a regex: {exc}", file=sys.stderr)
        return 1
    for n in [args.page] if args.page else range(1, len(texts) + 1):
        if args.grep:
            for line in texts[n - 1].splitlines():
                if pattern.search(line):
                    print(f"p{n}: {line.strip()}")
        else:
            print(f"===== {args.source} page {n}/{len(texts)} =====\n{texts[n - 1]}")
    return 0


def cmd_figures(args) -> int:
    p = _open(args)
    if p is None:
        return 1
    out = p.root / "figures" / args.source
    for path in sources.extract_figures(p.source_path(args.source), out):
        size = sources.pixel_size(path)
        print(f"{path.relative_to(p.root)}" + (f"  {size[0]} x {size[1]} px" if size else ""))
    return 0


def cmd_crop(args) -> int:
    from PIL import Image

    root = Path(args.dir)
    target = root / "figures" / "crops" / f"{args.name}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    box = (args.left, args.top, args.right, args.bottom)
    with Image.open(root / args.image) as image:
        width, height = image.size
        region = image.crop(box)
        if args.zoom != 1:
            region = region.resize(
                (region.width * args.zoom, region.height * args.zoom), Image.Resampling.LANCZOS
            )
        region.save(target)
    # The frame the box was read in, so a box placed on a downscaled view shows as one.
    print(f"cropped {' '.join(map(str, box))} of {args.image}, {width} x {height} px")
    print(f"image: {target.relative_to(root)}\nimage_sha256: {sources.sha256(target)}")
    return 0


def cmd_check(args) -> int:
    from . import checks, lint, report

    root, refused = Path(args.dir).resolve(), False
    try:
        p = project.load(root)
        refused = p.refused
    finally:
        # From here the last run's report is not this run's, even if reading the project dies. A
        # partial run writes nothing, so it stays, as it does in a project that is refused.
        if not (args.no_build or refused):
            report.withdraw(root)
    if refused:  # not a project, or one this cadrev cannot read: write nothing into it
        _print(p.findings)
        print(f"\n{report.NOT_VERIFIED}: the project was not read, so no report was written.")
        return 1
    ledger.check(p)
    incomparable = checks.comparable(p)
    modelled = lint.lint(p)
    ledger.coverage(p)
    results, drawn, model, coarsened, slowest = [], [], None, {}, None
    planned, holds = None, None
    read = {name for c in p.checks for name in ledger.named_by_checks(p, c)}
    if modelled and not args.no_build:
        from . import build, drawing, held, motion, plan

        # A build and its checks can take a minute: say what the wait is for as it starts.
        print("building model.py", flush=True)
        model = build.build(p)
        if model is not None:
            mechanism = motion.Mechanism(p, model) if model.joints else None
            print("evaluating checks.yaml", flush=True)
            results, read, slowest = checks.Checks(p, model, mechanism, incomparable).run()
            planned = plan.check(p, model)
            holds = held.check(p, model)
            coarsened = mechanism.coarsened if mechanism else {}
            written = build.export(p, model) + (mechanism.write() if mechanism else [])
            for path in written:
                print(f"wrote {path.relative_to(p.root)}")
            drawn = drawing.render(p, model, results, planned, holds)
            sheets = sum(path.parent.name == "drawings" for path in drawn)
            views = sum(path.parent.name == "steps" for path in drawn)
            if sheets:
                print(f"wrote build/drawings/: {sheets} part drawing{'s' * (sheets != 1)}")
            if len(drawn) > sheets + views:
                print("wrote build/isometric.png")
            if views:
                print(f"wrote build/steps/: {views} step view{'s' * (views != 1)}")
    if model is not None:
        read |= {thread.param for thread in model.threads}  # each held to its thread's sizes
    if not args.no_build:  # only a build can say what a check covers
        passed = {r.id for r in results if r.ok}
        ledger.unchecked(p, read, model.used if model else set(), passed)
    ledger.known_first(p)
    status = report.status(p, partial=args.no_build)
    headline = report.counts(p, results)
    _print(p.findings)
    if slowest:
        print(f"slowest check: {slowest[0]} {slowest[1]:.1f} s")
    found = f"{status}: {report.tally(headline)}"
    if args.no_build:  # a partial run makes no claim, so it writes nothing to build/
        print(f"\n{found}; skipped the build, so no claim is made and no report was written.")
        return 1
    path = report.write(p, status, results, drawn, model, coarsened, planned, holds)
    if planned is not None:
        print("wrote build/plan.md")
    known_first = f"Known first: {report.waiting_clause(p)}. " if p.known_first else ""
    print(
        f"\n{found}, {headline['checks_passed']}/{headline['checks']} checks pass. {known_first}"
        f"Report: {path.relative_to(p.root)}"
    )
    return 0 if status in report.PASSING else 1


def _writable(path: Path) -> bool:
    """Whether a file can be made in `path`, or in the nearest directory above it that exists. It
    makes one rather than ask os.access, which Linux's Landlock sandbox does not answer."""
    while not os.path.exists(path):
        path = path.parent
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".cadrev-probe"):
            return True
    except OSError:
        return False


def _redirect_caches() -> None:
    """A sandbox such as Codex's workspace-write lets cadrev write the workspace and TMPDIR, but
    not the plotting and font caches under HOME. Each that cannot be written moves to a directory
    of this user's under TMPDIR, before anything imports Matplotlib."""
    if os.name != "posix":
        return
    home = Path(os.path.expanduser("~"))
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    plots = home / ".matplotlib" if sys.platform == "darwin" else config / "matplotlib"
    caches = {
        # fontconfig's cache, and Matplotlib's on Linux
        "XDG_CACHE_HOME": ("cache", Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache")),
        "MPLCONFIGDIR": ("matplotlib", Path(os.environ.get("MPLCONFIGDIR") or plots)),
    }
    blocked = {var: name for var, (name, path) in caches.items() if not _writable(path)}
    if not blocked:
        return
    try:
        root = Path(tempfile.gettempdir()) / f"cadrev-{os.getuid()}"
        root.mkdir(mode=0o700, exist_ok=True)
        entry = root.lstat()
    except OSError:
        return
    # TMPDIR may be the shared /tmp, so the directory is used only when this user owns it.
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != os.getuid() or not _writable(root):
        return
    for var, name in blocked.items():
        with contextlib.suppress(OSError):
            (root / name).mkdir(exist_ok=True)
            os.environ[var] = str(root / name)


def main(argv: list[str] | None = None) -> int:
    _redirect_caches()
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["python"]:  # what follows is Python's to parse, and its exit is cadrev's
        os.execv(sys.executable, [sys.executable, *argv[1:]])
    parser = argparse.ArgumentParser(prog="cadrev", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, fn, help: str, *positional: str):
        s = sub.add_parser(name, help=help)
        for arg in ("dir", *positional):
            s.add_argument(arg)
        s.set_defaults(fn=fn)
        return s

    command("init", cmd_init, "scaffold a reconstruction project")
    s = command("source", cmd_source, "copy a source into the project and pin its sha256", "file")
    s.add_argument("--id", required=True)
    s.add_argument("--kind", required=True, choices=project.SOURCE_KINDS)
    s.add_argument("--citation", required=True)
    s.add_argument("--url")
    s.add_argument("--rename", help="file name inside sources/")
    s = command(
        "text", cmd_text, "print a source's extracted text, as the quote matcher sees it", "source"
    )
    s.add_argument("--page", type=int)
    s.add_argument("--grep", help="only lines matching this regex")
    command(
        "figures",
        cmd_figures,
        "render a PDF's pages and extract a source's images to figures/<source>/, with sizes",
        "source",
    )
    s = command(
        "crop", cmd_crop, "crop a figure region to figures/crops/ and print its sha256", "image"
    )
    for edge in ("left", "top", "right", "bottom"):
        s.add_argument(edge, type=int, metavar=edge.upper(), help="pixels of the image's file")
    s.add_argument("--name", required=True, help="the crop is written to figures/crops/<NAME>.png")
    s.add_argument(
        "--zoom", type=int, default=1, help="enlarge the crop by this whole-number factor"
    )
    s = command("check", cmd_check, "verify everything, build the model, write build/report.md")
    s.add_argument("--no-build", action="store_true", help="skip model build and geometry checks")
    sub.add_parser("python", help="run the Python cadrev runs on: a script of your own")

    try:
        args = parser.parse_args(argv)
        code = args.fn(args)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader closed stdout, as `head` does: stop quietly, and point stdout at devnull so
        # the interpreter's flush at exit has nowhere to fail.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 1
    return code


if __name__ == "__main__":
    sys.exit(main())
