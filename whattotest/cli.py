"""whattotest CLI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from whattotest import __version__, config, engine, gitio, report

EXIT_OK, EXIT_ERROR = 0, 2


def parse_range(args: argparse.Namespace) -> tuple[str, str]:
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
    raise config.ConfigError("give a range (v1.4.0..v1.5.0) or --base <ref>")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="whattotest",
        description="Release impact map for QA: what changed, what it can break, what to test, "
                    "and what was not impacted.")
    p.add_argument("range", nargs="?", help="A..B (tags, branches or commits); A alone means A..HEAD")
    p.add_argument("--base", help="base ref (alternative to RANGE); compares its merge base with --head")
    p.add_argument("--head", help="head ref (default: HEAD)")
    p.add_argument("--format", choices=report.FORMATS, default="text")
    p.add_argument("--output", help="write the report to a file")
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
        base, head = parse_range(args)
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
    text = report.FORMATS[args.format](result)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
