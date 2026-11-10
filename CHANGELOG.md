# Changelog

## 0.2.0

- **HTML report** (`--format html`): one self-contained page (no scripts, no
  external assets, light and dark themes) to open, attach to a release or share.
- **GitHub Action** (`uses: jussaragranja/whattotest@v0`): maps pull requests
  and tagged releases, writes the job summary, keeps a single updated pull
  request comment and uploads the HTML, Markdown and JSON reports as an artifact.
  Outputs the number of high, medium and low-risk areas.
- **No range means "since the previous tag"**: `whattotest` alone maps the
  previous tag to HEAD (or, when HEAD is tagged, the tag before it).
- **Several formats from one analysis**: repeat `--output`; the format comes
  from the extension (`--output map.html --output map.json`).
- `--max-chars` shortens the Markdown report to a size limit (65000 fits a
  GitHub comment) by dropping the file list first.
- Python tests that import a module as `from package import module` are now
  linked to it (before, these modules were reported as test gaps).
- Fixed "1 files" in risk reasons.

## 0.1.0

First release: release impact map with risk per area and reasons, silent
changes, test links and gaps, stories, and text, Markdown and JSON reports.
