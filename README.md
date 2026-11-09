# whattotest: Release Impact Map for QA

**Between version A and version B: what changed, what it can break, what to
test, and what was not changed.**

Every release, QA gets a list of commits and has to decide what goes into the
regression. `whattotest` turns the git history into an impact map, explained
in business areas, with the changes that rarely show up in a PR description:
database migrations, new environment variables, feature flags, major
dependency upgrades.

- **No AI, no API key, no dependencies.** Python standard library and git.
- **Zero configuration** to start; areas are inferred from the project
  structure. A small optional file makes them match your business language.
- **Every risk rating explains why.**

Illustrative output for a typical shop application:

```text
$ whattotest v1.4.0..v1.5.0

RELEASE IMPACT MAP · v1.4.0 → v1.5.0 · 47 commits · 6 stories

SUMMARY
  🔴 2 high · 🟡 3 medium · 🟢 4 low · ⚪ 5 not impacted
  ⚠ 1 migration · 2 env vars · 1 dependency

AREAS
  🔴 Payments   HIGH    large change (14 files, 612 lines); 9 bug-fix commits in these files
                        recently; new database migration (V42__add_installments.sql);
                        no linked tests for InstallmentService.java
  🔴 Checkout   HIGH    hotspot: CheckoutController.java change often; new environment variable
                        PAYMENT_PROVIDER_TIMEOUT; 4 different authors in this release
  🟡 Coupons    MEDIUM  6 files, 140 lines changed; 3 bug-fix commits in these files recently
  🟢 Profile    LOW     small change (1 file, 4 lines)
  ⚪ not impacted: Login, Search, Catalog, Notifications, Admin

SILENT CHANGES
  Migration     new database migration          db/migration/V42__add_installments.sql
  Env var       new environment variable PAYMENT_PROVIDER_TIMEOUT   application.yml
  Dependency    com.stripe:stripe-java 22.1.0 → 24.0.0 (major)      pom.xml

STORIES
  SHOP-123   Free shipping coupon     Coupons, Checkout
  SHOP-130   Installments             Payments

SUGGESTED REGRESSION SCOPE
  Full regression:  Payments, Checkout
  Focused tests:    Coupons
  Smoke test:       Profile
  Not changed:      Login, Search, Catalog, Notifications, Admin  (lowest priority)

TEST GAPS (changed code with no linked test)
  Payments             src/main/java/com/shop/payment/InstallmentService.java
```

## Install

```bash
pip install whattotest      # or: pip install git+<this repository>
```

Requires Python 3.11+ and git.

## Usage

```bash
whattotest v1.4.0..v1.5.0              # between two tags
whattotest main..release/2.8           # between branches
whattotest --base main                 # current branch vs main (a PR)
whattotest v1.4.0 --format md          # markdown for the release issue / wiki
whattotest v1.4.0 --format json        # for tools and AI agents
whattotest v1.4.0 --history-months 12  # longer history for risk
whattotest --init                      # create .whattotest.toml
```

## What it analyses

| Analysis | How |
|---|---|
| **Areas** | Files grouped into business areas: Java/Kotlin packages below the common prefix, Python packages and modules, `features/`, `modules/`, `packages/` folders; or your own mapping |
| **Risk per area, with reasons** | Size of the change, bug-fix commits on those files in recent history, hotspots (files that change often), silent changes, changed code with no linked test, number of authors |
| **Silent changes** | Database migrations (Flyway, Liquibase, Alembic, Rails, Prisma, Django; editing an old migration is flagged), dependency changes in Maven, Gradle, version catalogs, npm, pip and pyproject (major upgrades flagged), new environment variables in Java/Python/JS code, Spring/compose placeholders and `.env` files, feature flags (with your patterns) |
| **Tests** | Tests linked to changed code by naming convention (`PaymentService` ↔ `PaymentServiceTest`, `pricing.py` ↔ `test_pricing.py`, `Cart.tsx` ↔ `Cart.test.tsx`) and by imports; test gaps |
| **Stories** | Issue keys (`SHOP-123`) from commit messages, mapped to the areas they touched. Dependency bots and non-ticket keys (CVE-, GHSA-…) are ignored |
| **Scope** | High → full regression, medium → focused tests, low → smoke, not changed → lowest priority |

## Configuration (optional): `.whattotest.toml`

```toml
[areas]
Checkout = ["src/main/java/**/checkout/**", "web/src/features/checkout/**"]
Payments = ["src/main/java/**/payment/**", "db/migration/**"]

[tests]
Checkout = ["e2e/checkout/**"]

[signals]
flags   = ['isEnabled\("([\w.-]+)"\)', 'featureFlags\.(\w+)']
tickets = '\b[A-Z][A-Z0-9]+-\d+\b'

[risk]
history_months = 6
fix_patterns   = ["fix", "bug", "hotfix", "revert"]

ignore = ["docs/**", "**/*.md"]
```

The configuration is read from the head ref of the range.

## Does it work? Retrospective validation

We mapped 25 consecutive releases of three open-source projects with no
configuration, then looked at the bug fixes made after each release.

| Project | Areas rated high that got a later bug fix | Medium | Low | Not changed |
|---|---|---|---|---|
| jsoup (Java) | **96%** | 73% | 38% | **8%** |
| click (Python) | **67%** | 40% | 27% | **9%** |
| requests (Python) | — | 30% | 12% | **7%** |

In jsoup, the 29% of areas rated high or medium concentrated 79% of later
fixes. But "not changed" is not "bug-free": in requests, half of later fixes
landed in areas the release did not touch (old bugs, not regressions). Details
and limitations: [research/RESULTS.md](research/RESULTS.md).

## For AI coding agents

`skills/impact-to-test-plan/SKILL.md` lets the assistant you already use
(Claude Code, Copilot, Codex, Cursor…) turn the JSON map into exploratory test
charters per risky area. Copy it to `.agents/skills/` and/or `.claude/skills/`.

## Limitations

- Areas inferred without configuration follow the code structure, which is
  not always the business structure. Configure `[areas]` for best results.
- Risk is a prioritisation aid built from history, not a prediction of bugs.
- Test links are static (names and imports), not coverage data.
- One repository per run; a release spanning backend, web and mobile
  repositories is planned.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

## License

MIT
