"""whattotest CLI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whattotest import __version__, config, engine, gitio, report

EXIT_OK, EXIT_ERROR = 0, 2
EXTENSIONS = {".txt": "text", ".md": "md", ".json": "json", ".html": "html", ".htm": "html"}


def output_formats(args: argparse.Namespace) -> list[tuple[str | None, str]]:
    """(path or None for stdout, format). With several --output files, or none given with
    --format, the format comes from each file's extension."""
    if not args.output:
        return [(None, args.format or "text")]
    if len(args.output) == 1 and args.format:
        return [(args.output[0], args.format)]
    out = []
    for path in args.output:
        fmt = EXTENSIONS.get(Path(path).suffix.lower())
        if fmt is None and len(args.output) == 1:
            fmt = "text"   # as in 0.1.0: a single --output without --format writes text
        if fmt is None:
            raise config.ConfigError(f"cannot tell the format of {path}: use one of "
                                     f"{', '.join(EXTENSIONS)} or a single --output with --format")
        out.append((path, fmt))
    return out


def parse_range(args: argparse.Namespace, repo: Path) -> tuple[str, str]:
    if args.range:
        if "..." in args.range:
            base, head = args.range.split("...", 1)
        elif ".." in args.range:
            base, head = args.range.split("..", 1)
        else:
            base, head = args.range, "HEAD"
        return base, head or "HEAD"
    if args.base:
        return args.base, args.head or "HEAD"
    head = args.head or "HEAD"
    tag = gitio.previous_tag(repo, head)
    if tag is None:
        raise config.ConfigError("no earlier tag found; give a range (v1.4.0..v1.5.0) or --base <ref>")
    return tag, head


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="whattotest",
        description="Release impact map for QA: what changed, what it can break, what to test, "
                    "and what was not impacted.")
    p.add_argument("range", nargs="?",
                   help="A..B (tags, branches or commits); A alone means A..HEAD; "
                        "omitted: from the previous tag to HEAD")
    p.add_argument("--base", help="base ref (alternative to RANGE); compares its merge base with --head")
    p.add_argument("--head", help="head ref (default: HEAD)")
    p.add_argument("--format", choices=report.FORMATS,
                   help="text (default), md, json or html; with --output files, taken from the extension")
    p.add_argument("--output", action="append",
                   help="write the report to a file; repeat to write several formats from one analysis "
                        "(--output map.html --output map.json)")
    p.add_argument("--max-chars", type=int,
                   help="md only: shorten the report to fit this size (65000 for a GitHub comment)")
    p.add_argument("--config", help=f"config file (default: <repo>/{config.CONFIG_FILE} at the head ref)")
    p.add_argument("--history-months", type=int, help="months of history used for risk (default: 6)")
    p.add_argument("--repo", default=".", help="repository path (default: current directory)")
    p.add_argument("--version", action="version", version=f"whattotest {__version__}")
    p.add_argument("--init", action="store_true", help=f"create {config.CONFIG_FILE} and exit")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    try:
        if args.init:
            target = repo / config.CONFIG_FILE
            if target.exists():
                print(f"{target} already exists", file=sys.stderr)
                return EXIT_ERROR
            target.write_text(config.DEFAULT_CONFIG)
            print(f"Created {target}")
            return EXIT_OK
        outputs = output_formats(args)
        if args.max_chars is not None and all(fmt != "md" for _, fmt in outputs):
            raise config.ConfigError("--max-chars applies to the md format only")
        base, head = parse_range(args, repo)
        if args.config:
            cfg = config.load(Path(args.config))
        else:
            head_sha = gitio.resolve(repo, head)
            cfg = config.from_text(gitio.read_at(repo, head_sha, config.CONFIG_FILE))
        if args.history_months:
            cfg.history_months = args.history_months
        result = engine.run(repo, base, head, cfg)
    except (gitio.GitError, config.ConfigError) as e:
        print(f"whattotest: error: {e}", file=sys.stderr)
        return EXIT_ERROR
    for path, fmt in outputs:
        if fmt == "md" and args.max_chars:
            text = report.to_markdown(result, max_chars=args.max_chars)
        else:
            text = report.FORMATS[fmt](result)
        if path:
            Path(path).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
