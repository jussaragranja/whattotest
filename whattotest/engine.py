"""Build the release impact map between two refs."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from whattotest import gitio, signals
from whattotest.config import CONFIG_FILE, Config
from whattotest.files import AreaMapper, kind, match
from whattotest.gitio import FileChange
from whattotest.signals import Signal
from whattotest.testlink import LinkIndex

LEVELS = ("high", "medium", "low")
NOT_TICKETS = ("CVE-", "GHSA-", "CWE-", "UTF-", "ISO-", "RFC-", "SHA-", "TLS-", "HTTP-", "JDK-",
               "JEP-", "PEP-", "ES-", "X-")
BOTS = ("dependabot", "renovate", "github-actions", "snyk-bot", "greenkeeper")


def is_bot(author: str) -> bool:
    a = author.lower()
    return "[bot]" in a or a.startswith(BOTS)
SCOPE = {"high": "Full regression", "medium": "Focused tests", "low": "Smoke test"}


@dataclass
class AreaImpact:
    name: str
    files: list[FileChange] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    stories: set[str] = field(default_factory=set)
    fix_commits: int = 0
    hotspots: list[str] = field(default_factory=list)
    authors: set[str] = field(default_factory=set)
    related_tests: set[str] = field(default_factory=set)
    changed_tests: list[str] = field(default_factory=list)
    untested: list[str] = field(default_factory=list)
    score: int = 0
    level: str = "low"
    reasons: list[str] = field(default_factory=list)

    @property
    def code_files(self) -> list[FileChange]:
        return [f for f in self.files if kind(f.path) != "test"]

    @property
    def lines(self) -> int:
        return sum(f.added + f.removed for f in self.code_files)


@dataclass
class Story:
    key: str
    commits: int = 0
    areas: set[str] = field(default_factory=set)
    title: str = ""


@dataclass
class Result:
    base: str
    head: str
    base_sha: str
    head_sha: str
    commits: int
    areas: list[AreaImpact]
    test_only: list[AreaImpact]
    not_impacted: list[str]
    release_signals: list[Signal]
    stories: list[Story]
    other_files: list[FileChange]
    history_months: int

    def by_level(self, level: str) -> list[AreaImpact]:
        return [a for a in self.areas if a.level == level]


# ---------------------------------------------------------------- scoring

def score(area: AreaImpact) -> None:
    points, reasons = 0, []
    n, lines = len(area.code_files), area.lines

    if lines > 300 or n > 10:
        points += 2
        reasons.append(f"large change ({n} files, {lines} lines)")
    elif lines > 60 or n > 3:
        points += 1
        reasons.append(f"{n} files, {lines} lines changed")

    if area.fix_commits >= 5:
        points += 2
        reasons.append(f"{area.fix_commits} bug-fix commits in these files recently")
    elif area.fix_commits >= 2:
        points += 1
        reasons.append(f"{area.fix_commits} bug-fix commits in these files recently")

    if area.hotspots:
        points += 1
        reasons.append(f"hotspot: {', '.join(Path(h).name for h in area.hotspots[:3])} change often")

    for s in area.signals:
        points += {"high": 2, "medium": 1, "low": 0}[s.severity]
        if s.severity != "low":
            reasons.append(s.detail + f" ({Path(s.file).name})")

    if area.untested:
        points += 1
        reasons.append(f"no linked tests for {', '.join(Path(u).name for u in area.untested[:3])}"
                       + (f" and {len(area.untested) - 3} more" if len(area.untested) > 3 else ""))
    if area.code_files and not area.changed_tests and n > 1:
        reasons.append("no tests changed in this area")

    if len(area.authors) >= 4:
        points += 1
        reasons.append(f"{len(area.authors)} different authors in this release")

    area.score = points
    area.level = "high" if points >= 5 else "medium" if points >= 2 else "low"
    if not reasons:
        reasons.append(f"small change ({n} file{'s' if n != 1 else ''}, {lines} lines)")
    area.reasons = reasons


# ---------------------------------------------------------------- main

def run(repo: Path, base_ref: str, head_ref: str, cfg: Config) -> Result:
    head = gitio.resolve(repo, head_ref)
    base = gitio.merge_base(repo, base_ref, head)
    changes = [c for c in gitio.changes(repo, base, head)
               if not match(c.path, cfg.ignore) and c.path != CONFIG_FILE]
    repo_files = [f for f in gitio.files_at(repo, head) if not match(f, cfg.ignore)]
    mapper = AreaMapper(cfg, repo_files)

    base_cache: dict[str, str | None] = {}
    head_cache: dict[str, str | None] = {}

    def read_base(path: str | None) -> str | None:
        if path is None:
            return None
        if path not in base_cache:
            base_cache[path] = gitio.read_at(repo, base, path)
        return base_cache[path]

    def read_head(path: str | None) -> str | None:
        if path is None:
            return None
        if path not in head_cache:
            head_cache[path] = gitio.read_at(repo, head, path)
        return head_cache[path]

    # ---- signals
    sigs = (signals.migrations(changes) + signals.dependencies(changes, read_base, read_head)
            + signals.env_vars(changes, read_base, read_head)
            + signals.flags(changes, read_base, read_head, cfg.flag_patterns))

    # ---- areas
    areas: dict[str, AreaImpact] = {}
    other: list[FileChange] = []
    release_signals: list[Signal] = []

    def area_for(path: str) -> str | None:
        k = kind(path)
        if any(match(path, g) for g in cfg.areas.values()):
            return mapper.area(path)
        if k in ("code", "test"):
            return mapper.area(path)
        if k == "migration":
            return "Database"
        if k == "config":
            return "Configuration"
        if k == "i18n":
            return "UI text"
        return None

    for c in changes:
        name = area_for(c.path)
        if name is None:
            other.append(c)
            continue
        areas.setdefault(name, AreaImpact(name)).files.append(c)
    for s in sigs:
        name = area_for(s.file)
        if name and name in areas and s.type != "dependency":
            areas[name].signals.append(s)
        else:
            release_signals.append(s)

    # ---- release commits: stories and authors
    commits = gitio.log(repo, f"{base}..{head}")
    stories: dict[str, Story] = {}
    file_area = {c.path: area_for(c.path) for c in changes}
    for commit in commits:
        if is_bot(commit.author):
            continue  # dependency bots quote upstream issue keys and inflate author counts
        keys = {k for k in cfg.ticket_pattern.findall(f"{commit.subject}\n{commit.body}")
                if not k.upper().startswith(NOT_TICKETS)}
        touched = {file_area.get(f) for f in commit.files} - {None}
        for a in touched:
            areas[a].authors.add(commit.author)
            areas[a].stories |= keys
        for key in keys:
            st = stories.setdefault(key, Story(key))
            st.commits += 1
            st.areas |= touched
            if not st.title:
                st.title = re.sub(rf"[\[(]?{re.escape(key)}[\])]?[:\s-]*", "", commit.subject).strip()

    # ---- history: bug-fix commits and hotspots before/at head
    since = datetime.fromtimestamp(gitio.commit_time(repo, head) - cfg.history_months * 30 * 86400,
                                   tz=timezone.utc).isoformat()
    history = gitio.log(repo, head, since=since)
    touches: Counter = Counter()
    fixes: dict[str, set[str]] = defaultdict(set)
    for commit in history:
        is_fix = bool(cfg.fix_pattern.search(f"{commit.subject}\n{commit.body}"))
        for f in commit.files:
            touches[f] += 1
            if is_fix:
                fixes[f].add(commit.sha)
    ranked = [f for f, n in touches.most_common() if n >= 3 and kind(f) == "code"]
    hotspots = set(ranked[:max(1, len(ranked) // 10)]) if ranked else set()

    # ---- tests
    test_paths = [f for f in repo_files if kind(f) == "test"]
    index = LinkIndex(gitio.read_many(repo, head, test_paths))
    configured_tests = {name: [t for t in test_paths if match(t, globs)]
                        for name, globs in cfg.tests.items()}

    for area in areas.values():
        fix_shas: set[str] = set()
        for f in area.files:
            path = f.path
            if kind(path) == "test":
                area.changed_tests.append(path)
                continue
            fix_shas |= fixes.get(path, set()) | fixes.get(f.old_path or "", set())
            if path in hotspots:
                area.hotspots.append(path)
            if kind(path) == "code" and f.status != "D":
                linked = index.linked(path)
                area.related_tests |= linked
                if not linked:
                    area.untested.append(path)
        area.fix_commits = len(fix_shas)
        area.related_tests |= set(configured_tests.get(area.name, []))
        area.related_tests |= {t for t in test_paths if mapper.area(t) == area.name}
        if area.code_files:
            score(area)

    impacted = sorted((a for a in areas.values() if a.code_files),
                      key=lambda a: (-a.score, a.name))
    test_only = sorted((a for a in areas.values() if not a.code_files), key=lambda a: a.name)

    known = {mapper.area(f) for f in repo_files if kind(f) == "code"} | set(cfg.areas)
    not_impacted = sorted(known - {a.name for a in impacted} - {a.name for a in test_only})

    return Result(base=base_ref, head=head_ref, base_sha=base, head_sha=head,
                  commits=len(commits), areas=impacted, test_only=test_only,
                  not_impacted=not_impacted, release_signals=release_signals,
                  stories=sorted(stories.values(), key=lambda s: s.key), other_files=other,
                  history_months=cfg.history_months)
