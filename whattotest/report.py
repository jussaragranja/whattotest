"""Reports: text (terminal), md (release issue / PR / wiki), json (tools and agents),
html (a self-contained page to open or share)."""
from __future__ import annotations

import json

from whattotest import __version__
from whattotest.engine import SCOPE, Result
from whattotest.htmlreport import to_html

ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}
SIGNAL_LABEL = {"migration": "Migration", "dependency": "Dependency", "env": "Env var", "flag": "Feature flag"}


def _short(sha: str) -> str:
    return sha[:8]


def _counts(r: Result) -> str:
    parts = [f"{ICON[l]} {len(r.by_level(l))} {l}" for l in ("high", "medium", "low")]
    return " · ".join(parts) + f" · ⚪ {len(r.not_impacted)} not impacted"


def _signal_counts(r: Result) -> str:
    sigs = [s for a in r.areas for s in a.signals] + r.release_signals
    counts = {}
    for s in sigs:
        if s.severity == "low":
            continue
        counts[s.type] = counts.get(s.type, 0) + 1
    return " · ".join(f"{n} {SIGNAL_LABEL[t].lower()}{'s' if n > 1 else ''}" for t, n in counts.items())


def _all_signals(r: Result):
    for a in r.areas:
        for s in a.signals:
            yield a.name, s
    for s in r.release_signals:
        yield "Release-wide", s


# ---------------------------------------------------------------- text

def to_text(r: Result) -> str:
    out = [f"RELEASE IMPACT MAP · {r.base} → {r.head} · {r.commits} commits · {len(r.stories)} stories", ""]
    out += ["SUMMARY", f"  {_counts(r)}"]
    sc = _signal_counts(r)
    if sc:
        out.append(f"  ⚠ {sc}")

    out += ["", "AREAS"]
    if not r.areas:
        out.append("  no production code changed")
    for a in r.areas:
        out.append(f"  {ICON[a.level]} {a.name:<20} {a.level.upper():<7} {'; '.join(a.reasons)}")
    if r.test_only:
        out.append(f"  ·  tests changed only: {', '.join(a.name for a in r.test_only)}")
    if r.not_impacted:
        out.append(f"  ⚪ not impacted: {', '.join(r.not_impacted)}")

    sigs = [(n, s) for n, s in _all_signals(r)]
    if sigs:
        out += ["", "SILENT CHANGES"]
        for area, s in sigs:
            out.append(f"  {SIGNAL_LABEL[s.type]:<13} {s.detail:<55} {s.file}  → {area}")

    if r.stories:
        out += ["", "STORIES"]
        for st in r.stories:
            out.append(f"  {st.key:<12} {st.title[:50]:<50} {', '.join(sorted(st.areas)) or '—'}")

    out += ["", "SUGGESTED REGRESSION SCOPE"]
    for level in ("high", "medium", "low"):
        names = [a.name for a in r.by_level(level)]
        if names:
            out.append(f"  {SCOPE[level] + ':':<17} {', '.join(names)}")
    if r.not_impacted:
        out.append(f"  {'Not changed:':<17} {', '.join(r.not_impacted)}  (lowest priority: no code changes in this range, but old bugs can still exist)")

    gaps = [(a.name, u) for a in r.areas for u in a.untested]
    if gaps:
        out += ["", "TEST GAPS (changed code with no linked test)"]
        for area, path in gaps[:25]:
            out.append(f"  {area:<20} {path}")
        if len(gaps) > 25:
            out.append(f"  … and {len(gaps) - 25} more")

    out += ["", f"base {_short(r.base_sha)} · head {_short(r.head_sha)} · history {r.history_months} months · whattotest {__version__}"]
    return "\n".join(out)


# ---------------------------------------------------------------- markdown

SHORTENED = "_Shortened to fit the size limit. The HTML or JSON report has the full map._"


def to_markdown(r: Result, max_chars: int | None = None) -> str:
    """Markdown report. With max_chars, drop detail until it fits (GitHub comments: 65536)."""
    for level in range(3):
        text = _markdown(r, level)
        if max_chars is None or len(text) <= max_chars:
            return text
    cut = text[:max(0, max_chars - len(SHORTENED) - 2)]
    return cut[:cut.rfind("\n") + 1 if "\n" in cut else len(cut)] + "\n" + SHORTENED


def _markdown(r: Result, compact: int = 0) -> str:
    """compact 0: everything; 1: no changed-file list; 2: also cap test gaps and stories."""
    gap_cap, story_cap = (None, None) if compact < 2 else (20, 30)
    out = ["<!-- whattotest -->", f"## Release impact map: `{r.base}` → `{r.head}`", "",
           f"{r.commits} commits · {len(r.stories)} stories · {_counts(r)}"]
    sc = _signal_counts(r)
    if sc:
        out.append(f"\n⚠️ **Silent changes:** {sc}")

    out += ["", "### Suggested regression scope", "", "| Scope | Areas |", "|---|---|"]
    for level in ("high", "medium", "low"):
        names = [a.name for a in r.by_level(level)]
        if names:
            out.append(f"| {ICON[level]} **{SCOPE[level]}** | {', '.join(names)} |")
    if r.not_impacted:
        out.append(f"| ⚪ **Not changed: lowest priority** (no code changes; old bugs can still exist) | {', '.join(r.not_impacted)} |")

    out += ["", "### Areas", "", "| | Area | Risk | Why | Files | Tests |", "|---|---|---|---|---|---|"]
    for a in r.areas:
        tests = f"{len(a.related_tests)} related, {len(a.changed_tests)} changed"
        out.append(f"| {ICON[a.level]} | **{a.name}** | {a.level} | {'; '.join(a.reasons)} | "
                   f"{len(a.code_files)} (+{sum(f.added for f in a.code_files)} −{sum(f.removed for f in a.code_files)}) | {tests} |")
    if r.test_only:
        out.append(f"\nTests changed only: {', '.join(a.name for a in r.test_only)}")

    sigs = list(_all_signals(r))
    if sigs:
        out += ["", "### Silent changes", "", "| Type | Change | File | Area |", "|---|---|---|---|"]
        for area, s in sigs:
            out.append(f"| {SIGNAL_LABEL[s.type]} | {s.detail} | `{s.file}` | {area} |")

    if r.stories:
        out += ["", "### Stories in this release", "", "| Story | Title | Areas | Commits |", "|---|---|---|---|"]
        for st in r.stories[:story_cap]:
            out.append(f"| {st.key} | {st.title[:70]} | {', '.join(sorted(st.areas)) or '—'} | {st.commits} |")
        if story_cap and len(r.stories) > story_cap:
            out.append(f"| … | {len(r.stories) - story_cap} more | | |")

    gaps = [(a.name, u) for a in r.areas for u in a.untested]
    if gaps:
        out += ["", "<details><summary>Test gaps: changed code with no linked test "
                f"({len(gaps)})</summary>", ""]
        out += [f"- **{area}** `{path}`" for area, path in gaps[:gap_cap]]
        if gap_cap and len(gaps) > gap_cap:
            out.append(f"- … and {len(gaps) - gap_cap} more")
        out += ["", "</details>"]

    if compact == 0:
        out += ["", "<details><summary>Changed files by area</summary>", ""]
        for a in r.areas + r.test_only:
            out.append(f"**{a.name}**")
            out += [f"- `{f.status}` {f.path} (+{f.added} −{f.removed})" for f in a.files]
            out.append("")
        if r.other_files:
            out.append("**Other**")
            out += [f"- `{f.status}` {f.path}" for f in r.other_files]
        out.append("</details>")
    else:
        out += ["", SHORTENED]
    out += ["",
            f"<sub>base `{_short(r.base_sha)}` · head `{_short(r.head_sha)}` · history {r.history_months} months · whattotest {__version__}</sub>"]
    return "\n".join(out)


# ---------------------------------------------------------------- json

def to_json(r: Result) -> str:
    def area(a):
        return {
            "name": a.name, "risk": a.level, "score": a.score, "scope": SCOPE[a.level],
            "reasons": a.reasons, "lines": a.lines,
            "files": [{"path": f.path, "status": f.status, "added": f.added, "removed": f.removed}
                      for f in a.files],
            "signals": [vars(s) for s in a.signals], "stories": sorted(a.stories),
            "bug_fix_commits": a.fix_commits, "hotspots": a.hotspots, "authors": sorted(a.authors),
            "related_tests": sorted(a.related_tests), "changed_tests": a.changed_tests,
            "untested_files": a.untested,
        }
    return json.dumps({
        "tool": f"whattotest {__version__}", "base": r.base, "head": r.head,
        "base_sha": r.base_sha, "head_sha": r.head_sha, "commits": r.commits,
        "history_months": r.history_months,
        "areas": [area(a) for a in r.areas],
        "tests_only": [a.name for a in r.test_only],
        "not_impacted": r.not_impacted,
        "release_signals": [vars(s) for s in r.release_signals],
        "stories": [{"key": s.key, "title": s.title, "areas": sorted(s.areas), "commits": s.commits}
                    for s in r.stories],
        "other_files": [f.path for f in r.other_files],
    }, indent=2, ensure_ascii=False)


FORMATS = {"text": to_text, "md": to_markdown, "json": to_json, "html": to_html}
