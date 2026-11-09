# Retrospective validation

**Question:** when `whattotest` maps a release, do the areas it rates as risky
receive more bug fixes afterwards than the areas it rates as low risk or not
changed?

## Method

For each pair of consecutive releases A → B of an open-source project:

1. Build the impact map for A..B using only information available at B
   (the diff, and git history up to B). No configuration: areas are inferred.
2. Take the bug-fix commits made after B, up to the next release C
   (commit message matches fix/bug/hotfix/revert/regression/patch; bots excluded).
3. Map the files of those commits to areas and count, per risk level, how many
   areas received at least one later fix.

25 release pairs per project. Script: [`retrospective.py`](retrospective.py);
per-release data in [`results/`](results/).

## Results

### Rate: share of areas at each level that received a later bug fix

| Project | High | Medium | Low | Not changed |
|---|---|---|---|---|
| jsoup (Java), 1.12.1 … 1.23.2 | **96%** (24/25) | 73% (54/74) | 38% (32/85) | **8%** (12/160) |
| click (Python), 8.0.0 … 8.5.0 | **67%** (4/6) | 40% (26/65) | 27% (41/154) | **9%** (26/292) |
| requests (Python), 2.21.0 … 2.34.1 | — (0 areas) | 30% (9/30) | 12% (18/156) | **7%** (24/325) |

The rate falls monotonically with the risk level in all three projects.

### Concentration: share of all later fixes that landed at each level

| Project | High + medium: share of areas → share of later fixes | Not changed: share of areas → share of later fixes |
|---|---|---|
| jsoup | 29% → **79%** | 47% → **6%** |
| click | 14% → 37% | 56% → 21% |
| requests | 6% → 19% | 64% → **49%** |

## Interpretation

- **The ranking works.** Higher-risk areas receive bug fixes much more often,
  in every project. In jsoup, under a third of the areas concentrated almost
  four fifths of later fixes.
- **"Not changed" is not "bug-free".** In mature libraries many later fixes
  address long-standing bugs unrelated to the last release; in requests about
  half of them landed in areas the release did not touch. For this reason the
  report labels these areas *"Not changed: lowest priority"*, not *"skip"*.

## Limitations

- **A later fix is not necessarily a regression of that release.** We did not
  trace which commit introduced each bug. The study measures where fixes
  happened, which is a proxy for where problems were.
- **Activity bias.** Risk includes recent fix history and churn, so areas that
  are busy in general score high and also receive more fixes. The scores are
  useful for prioritising, but this is not evidence that each factor is causal.
- **Fix detection by commit message** misses fixes with other wording and
  counts some non-fixes (e.g. "fix typo").
- **Three libraries, no configuration.** Business applications (with
  migrations, flags and configured areas) were not part of this study.
- The tool and the study were written by the same people.
