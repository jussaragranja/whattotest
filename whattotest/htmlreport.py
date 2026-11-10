"""HTML report: one self-contained file (no scripts, no external assets) to open, attach or share."""
from __future__ import annotations

from html import escape

from whattotest import __version__
from whattotest.engine import SCOPE, AreaImpact, Result

LEVEL_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}
SIGNAL_LABEL = {"migration": "Migration", "dependency": "Dependency", "env": "Env var", "flag": "Feature flag"}

CSS = """
:root {
  --bg: #f7f7f5; --surface: #ffffff; --text: #1d1d1b; --muted: #5f5f5a; --border: #e2e2dc;
  --code-bg: #f0f0eb;
  --high: #b42318; --high-bg: #fdecea; --medium: #9a6700; --medium-bg: #fff4d6;
  --low: #1a7f37; --low-bg: #e6f4ea; --none: #6e6e68; --none-bg: #efefea;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --surface: #1f1f1d; --text: #ecece8; --muted: #a3a39c; --border: #34342f;
    --code-bg: #2a2a27;
    --high: #ff8a80; --high-bg: #3a1d1b; --medium: #f2c14e; --medium-bg: #362e15;
    --low: #6fd08c; --low-bg: #17301f; --none: #a3a39c; --none-bg: #2a2a27;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 36px 0 12px; }
.meta { color: var(--muted); margin: 0; }
code { font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--code-bg); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-top: 20px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px;
  border-top: 4px solid var(--c); }
.tile b { display: block; font-size: 28px; line-height: 1.1; color: var(--c); }
.tile span { color: var(--muted); font-size: 13px; }
.high { --c: var(--high); --cb: var(--high-bg); } .medium { --c: var(--medium); --cb: var(--medium-bg); }
.low { --c: var(--low); --cb: var(--low-bg); } .none { --c: var(--none); --cb: var(--none-bg); }
.warn { margin-top: 12px; padding: 10px 14px; border-radius: 8px; background: var(--medium-bg); }
.scope { display: grid; gap: 8px; }
.scope div { display: grid; grid-template-columns: 220px 1fr; gap: 12px; background: var(--surface);
  border: 1px solid var(--border); border-left: 5px solid var(--c); border-radius: 8px; padding: 10px 14px; }
.scope b { color: var(--c); }
.scope small { display: block; color: var(--muted); font-weight: normal; }
.badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 99px;
  color: var(--c); background: var(--cb); white-space: nowrap; }
details.area { background: var(--surface); border: 1px solid var(--border); border-left: 5px solid var(--c);
  border-radius: 8px; margin-bottom: 10px; }
details.area > summary { cursor: pointer; padding: 12px 14px; display: flex; flex-wrap: wrap; gap: 6px 12px;
  align-items: baseline; }
details.area > summary .name { font-weight: 600; font-size: 16px; }
details.area > summary .why { flex-basis: 100%; color: var(--muted); font-size: 14px; }
.body { padding: 0 14px 14px; display: grid; gap: 14px; }
.body h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); margin: 0 0 4px; }
.body ul { margin: 0; padding-left: 20px; }
.stats { display: flex; flex-wrap: wrap; gap: 6px 18px; color: var(--muted); font-size: 14px; }
.table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 13px; }
tr:last-child td { border-bottom: 0; }
.plain { color: var(--muted); }
details.more { margin-top: 8px; }
details.more summary { cursor: pointer; color: var(--muted); }
footer { margin-top: 40px; color: var(--muted); font-size: 13px; }
@media (max-width: 640px) { .scope div { grid-template-columns: 1fr; gap: 2px; } h1 { font-size: 22px; } }
@media print { body { background: #fff; } details.area > summary { list-style: none; } }
"""


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _files(files, with_lines: bool = True) -> str:
    items = []
    for f in files:
        lines = f" <span class=plain>+{f.added} −{f.removed}</span>" if with_lines else ""
        items.append(f"<li><code>{_e(f.status)}</code> {_e(f.path)}{lines}</li>")
    return "<ul>" + "".join(items) + "</ul>"


def _area(a: AreaImpact) -> str:
    added = sum(f.added for f in a.code_files)
    removed = sum(f.removed for f in a.code_files)
    parts = [
        f'<details class="area {a.level}"{" open" if a.level == "high" else ""}>',
        "<summary>",
        f'<span class="name">{_e(a.name)}</span>',
        f'<span class="badge">{LEVEL_LABEL[a.level]} risk</span>',
        f'<span class="plain">{_e(SCOPE[a.level])}</span>',
        f'<span class="why">{_e("; ".join(a.reasons))}</span>',
        "</summary>",
        '<div class="body">',
        '<div class="stats">'
        f"<span>{len(a.code_files)} code files, +{added} −{removed}</span>"
        f"<span>{len(a.related_tests)} related tests</span>"
        f"<span>{len(a.changed_tests)} tests changed</span>"
        f"<span>{a.fix_commits} recent bug-fix commits</span>"
        f"<span>{len(a.authors)} authors</span>"
        "</div>",
    ]
    if a.signals:
        parts.append("<div><h3>Silent changes</h3><ul>" + "".join(
            f"<li>{_e(SIGNAL_LABEL[s.type])}: {_e(s.detail)} <code>{_e(s.file)}</code></li>"
            for s in a.signals) + "</ul></div>")
    if a.untested:
        parts.append("<div><h3>Changed code with no linked test</h3><ul>" + "".join(
            f"<li><code>{_e(u)}</code></li>" for u in a.untested) + "</ul></div>")
    if a.stories:
        parts.append(f"<div><h3>Stories</h3>{_e(', '.join(sorted(a.stories)))}</div>")
    if a.related_tests:
        tests = sorted(a.related_tests)
        parts.append(f'<div><h3>Related tests</h3><details class="more"><summary>{len(tests)} '
                     f'test file{"s" if len(tests) != 1 else ""}</summary><ul>'
                     + "".join(f"<li><code>{_e(t)}</code></li>" for t in tests) + "</ul></details></div>")
    parts.append(f'<div><h3>Changed files</h3><details class="more"><summary>{len(a.files)} '
                 f'file{"s" if len(a.files) != 1 else ""}</summary>{_files(a.files)}</details></div>')
    parts += ["</div>", "</details>"]
    return "".join(parts)


def to_html(r: Result) -> str:
    sigs = [(a.name, s) for a in r.areas for s in a.signals] + [("Release-wide", s) for s in r.release_signals]
    counts: dict[str, int] = {}
    for _, s in sigs:
        if s.severity != "low":
            counts[s.type] = counts.get(s.type, 0) + 1
    title = f"Release impact map: {r.base} → {r.head}"

    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_e(title)}</title>",
        f'<meta name="generator" content="whattotest {_e(__version__)}">',
        f"<style>{CSS}</style></head><body><main>",
        f"<h1>Release impact map</h1>",
        f'<p class="meta"><code>{_e(r.base)}</code> → <code>{_e(r.head)}</code> · {r.commits} commits · '
        f"{len(r.stories)} stories</p>",
        '<div class="tiles">',
    ]
    for level in ("high", "medium", "low"):
        out.append(f'<div class="tile {level}"><b>{len(r.by_level(level))}</b>'
                   f"<span>{LEVEL_LABEL[level]} risk areas</span></div>")
    out.append(f'<div class="tile none"><b>{len(r.not_impacted)}</b><span>Not changed</span></div>')
    out.append("</div>")
    if counts:
        out.append('<p class="warn"><b>Silent changes:</b> ' + _e(" · ".join(
            f"{n} {SIGNAL_LABEL[t].lower()}{'s' if n > 1 else ''}" for t, n in counts.items())) + "</p>")

    out += ["<h2>Suggested regression scope</h2>", '<div class="scope">']
    for level in ("high", "medium", "low"):
        names = [a.name for a in r.by_level(level)]
        if names:
            out.append(f'<div class="{level}"><b>{_e(SCOPE[level])}<small>{LEVEL_LABEL[level]} risk</small></b>'
                       f"<span>{_e(', '.join(names))}</span></div>")
    if r.not_impacted:
        out.append('<div class="none"><b>Lowest priority<small>Not changed in this release; '
                   f"old bugs can still exist</small></b><span>{_e(', '.join(r.not_impacted))}</span></div>")
    if not r.areas and not r.not_impacted:
        out.append('<div class="none"><b>Nothing to scope</b><span>No production code changed.</span></div>')
    out.append("</div>")

    out.append("<h2>Areas</h2>")
    if r.areas:
        out += [_area(a) for a in r.areas]
    else:
        out.append('<p class="plain">No production code changed.</p>')
    if r.test_only:
        out.append(f'<p class="plain">Tests changed only: {_e(", ".join(a.name for a in r.test_only))}</p>')

    if sigs:
        out += ["<h2>Silent changes</h2>", '<div class="table-wrap"><table>',
                "<tr><th>Type</th><th>Change</th><th>File</th><th>Area</th></tr>"]
        out += [f"<tr><td>{_e(SIGNAL_LABEL[s.type])}</td><td>{_e(s.detail)}</td>"
                f"<td><code>{_e(s.file)}</code></td><td>{_e(area)}</td></tr>" for area, s in sigs]
        out.append("</table></div>")

    if r.stories:
        out += ["<h2>Stories in this release</h2>", '<div class="table-wrap"><table>',
                "<tr><th>Story</th><th>Title</th><th>Areas</th><th>Commits</th></tr>"]
        out += [f"<tr><td><b>{_e(st.key)}</b></td><td>{_e(st.title)}</td>"
                f"<td>{_e(', '.join(sorted(st.areas)) or '—')}</td><td>{st.commits}</td></tr>"
                for st in r.stories]
        out.append("</table></div>")

    gaps = [(a.name, u) for a in r.areas for u in a.untested]
    if gaps:
        out += [f"<h2>Test gaps ({len(gaps)})</h2>", '<p class="plain">Changed code with no linked test '
                "(by name or import).</p>", '<div class="table-wrap"><table>',
                "<tr><th>Area</th><th>File</th></tr>"]
        out += [f"<tr><td>{_e(area)}</td><td><code>{_e(path)}</code></td></tr>" for area, path in gaps]
        out.append("</table></div>")

    if r.other_files:
        out += ["<h2>Other files</h2>", f'<details class="more"><summary>{len(r.other_files)} files outside '
                f"code areas (docs, build, assets)</summary>{_files(r.other_files, with_lines=False)}</details>"]

    out.append(f"<footer>base <code>{_e(r.base_sha[:8])}</code> · head <code>{_e(r.head_sha[:8])}</code> · "
               f"history {r.history_months} months · whattotest {_e(__version__)}. "
               "Risk is a prioritisation aid built from history, not a prediction of bugs.</footer>")
    out.append("</main></body></html>")
    return "\n".join(out)
