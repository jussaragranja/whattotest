#!/usr/bin/env python3
"""Retrospective validation: did the impact map point at the areas that needed bug fixes later?

For each pair of consecutive releases (A -> B) the map is built with information
available at B only. Then the bug-fix commits made after B, up to the next release C,
are mapped to areas. If the map is useful, areas rated high should receive fixes more
often than medium, low, and especially "not impacted" areas.

Usage: python research/retrospective.py <repo> <tag regex> [--max N]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whattotest import config, gitio  # noqa: E402
from whattotest.engine import is_bot, run  # noqa: E402
from whattotest.files import AreaMapper, kind  # noqa: E402


def release_tags(repo: Path, pattern: str) -> list[str]:
    tags = gitio.git(repo, "tag", "--sort=creatordate").split()
    rx = re.compile(pattern)
    return [t for t in tags if rx.fullmatch(t)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("tags", help="regex for final release tags, e.g. 'jsoup-1\\.\\d+\\.\\d+'")
    ap.add_argument("--max", type=int, default=20, help="number of most recent release pairs")
    ap.add_argument("--json", help="write per-release data here")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    tags = release_tags(repo, args.tags)[-(args.max + 2):]
    cfg = config.Config()

    stats = defaultdict(lambda: [0, 0])     # level -> [areas, areas with later fixes]
    fix_hits = defaultdict(int)             # level -> later fix commits touching those areas
    rows = []
    for a, b, c in zip(tags, tags[1:], tags[2:]):
        result = run(repo, a, b, cfg)
        mapper = AreaMapper(cfg, gitio.files_at(repo, b))
        level = {x.name: x.level for x in result.areas}
        level.update({n: "not impacted" for n in result.not_impacted})

        later_fix_areas = defaultdict(int)
        n_fixes = 0
        for commit in gitio.log(repo, f"{b}..{c}"):
            if is_bot(commit.author) or not cfg.fix_pattern.search(f"{commit.subject}\n{commit.body}"):
                continue
            touched = {mapper.area(f) for f in commit.files if kind(f) == "code"}
            if touched:
                n_fixes += 1
            for t in touched:
                later_fix_areas[t] += 1

        for name, lvl in level.items():
            stats[lvl][0] += 1
            if later_fix_areas.get(name):
                stats[lvl][1] += 1
                fix_hits[lvl] += later_fix_areas[name]
        unseen = {n for n in later_fix_areas if n not in level}  # areas created later
        rows.append({"release": f"{a}..{b}", "next": c, "later_fix_commits": n_fixes,
                     "levels": level, "later_fix_areas": dict(later_fix_areas),
                     "fixes_in_new_areas": sorted(unseen)})

    print(f"{repo.name}: {len(rows)} releases ({tags[1]} … {tags[-2]})")
    print(f"  {'level':<14} {'areas':>6} {'with later fixes':>17} {'rate':>6} {'fix commits':>12}")
    for lvl in ("high", "medium", "low", "not impacted"):
        n, hit = stats[lvl]
        rate = f"{hit / n:.0%}" if n else "—"
        print(f"  {lvl:<14} {n:>6} {hit:>17} {rate:>6} {fix_hits[lvl]:>12}")
    if args.json:
        Path(args.json).write_text(json.dumps({"stats": {k: v for k, v in stats.items()},
                                               "fix_hits": fix_hits, "releases": rows}, indent=2))


if __name__ == "__main__":
    main()
