---
name: impact-to-test-plan
description: Turn a release impact map into a prioritised test plan with
  exploratory test charters. Use when the user asks what to test for a release,
  a sprint or a large pull request, or wants a regression plan between two
  versions, tags or branches.
---

# Impact to Test Plan

## Goal
Give the QA a concrete, prioritised plan for the release, grounded in what
actually changed, and say plainly what was not changed.

## Steps
1. Find the range. Ask the user if unclear; otherwise use the last release tag
   and `HEAD` (`git describe --tags --abbrev=0`).
2. Run:
   ```bash
   whattotest <base>..<head> --format json
   ```
   If `whattotest` is not installed, run `pip install whattotest` and retry; if
   that is not possible, stop and tell the user.
3. For each area, in the order given (high risk first), read `reasons`,
   `signals`, `files`, `stories`, `related_tests` and `untested_files`. Open the
   changed files when the reasons are not enough to understand the behaviour change.
4. Write one test charter per high and medium area:
   ```
   Charter: Explore <area> with <data/conditions> to discover <risk>
   Why: <the reasons from the map, in one line>
   Focus: <3–6 concrete scenarios, including the silent changes>
   Existing automated tests: <related_tests, or "none linked">
   ```
   - Migrations: test existing data, not only new data.
   - New environment variables: test missing and invalid values per environment.
   - Major dependency upgrades: test the features that use the library.
   - Test gaps: suggest the automated test that is missing.
5. For low areas, list smoke checks only.
6. List the not changed areas as lowest priority. Do not call them safe: old
   bugs can still exist there.

## Output
A short plan the QA can paste into the release issue: scope table, charters
for high/medium areas, smoke list, test gaps, and the not changed areas.

## Do not
- Do not invent areas or risks that are not in the map.
- Do not drop the reasons: every charter must say why the area matters.
