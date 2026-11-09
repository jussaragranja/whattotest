import json

import pytest

from whattotest import cli

PAY = "src/main/java/com/shop/payment/PaymentService.java"
PAY_TEST = "src/test/java/com/shop/payment/PaymentServiceTest.java"
CHECKOUT = "src/main/java/com/shop/checkout/CheckoutService.java"
LOGIN = "src/main/java/com/shop/login/LoginService.java"
SEARCH = "src/main/java/com/shop/search/SearchService.java"
POM = """<project><dependencies>
<dependency><groupId>com.stripe</groupId><artifactId>stripe-java</artifactId><version>22.0.0</version></dependency>
</dependencies></project>"""


def java(cls, body=""):
    pkg = {"PaymentService": "payment", "CheckoutService": "checkout", "LoginService": "login",
           "SearchService": "search", "PaymentServiceTest": "payment"}[cls]
    return f"package com.shop.{pkg};\npublic class {cls} {{\n{body}\n}}\n"


@pytest.fixture
def release(repo):
    """v1.0 -> v1.1: payments heavily changed (with history of fixes), checkout touched,
    login and search untouched."""
    repo.commit({PAY: java("PaymentService"), PAY_TEST: java("PaymentServiceTest"),
                 CHECKOUT: java("CheckoutService"), LOGIN: java("LoginService"),
                 SEARCH: java("SearchService"), "pom.xml": POM}, "initial")
    for i in range(3):
        repo.commit({PAY: java("PaymentService", f"// fix {i}")}, f"fix: payment rounding bug {i}")
    repo.tag("v1.0")
    body = "\n".join(f"    int f{i}() {{ return {i}; }}" for i in range(80))
    repo.commit({PAY: java("PaymentService", body + '\n String t = System.getenv("PAY_TIMEOUT");'),
                 "db/migration/V2__installments.sql": "alter table payment add installments int;"},
                "SHOP-130: installments", author="Ana <ana@example.invalid>")
    repo.commit({CHECKOUT: java("CheckoutService", "int total() { return 1; }")},
                "SHOP-123 free shipping coupon", author="Bia <bia@example.invalid>")
    repo.commit({"pom.xml": POM.replace("22.0.0", "24.1.0")},
                "Bump stripe-java. Fixes SUREFIRE-123 upstream, CVE-2026-1",
                author="dependabot[bot] <bot@example.invalid>")
    repo.commit({"docs/notes.md": "release notes"}, "docs")
    repo.tag("v1.1")
    return repo


def run(repo, capsys, *args):
    code = cli.main(["--repo", str(repo.path), *args])
    return code, capsys.readouterr().out


def test_full_report_json(release, capsys):
    code, out = run(release, capsys, "v1.0..v1.1", "--format", "json")
    data = json.loads(out)
    assert code == 0
    areas = {a["name"]: a for a in data["areas"]}
    assert set(areas) == {"Payment", "Checkout", "Database"}
    pay = areas["Payment"]
    # 3 bug-fix commits + hotspot + new env var + 80-line change; the migration belongs to
    # "Database" without configuration (see test_config_from_head_defines_areas)
    assert pay["risk"] == "medium" and pay["score"] == 4
    assert pay["bug_fix_commits"] == 3
    assert areas["Database"]["risk"] == "medium"
    assert any("PAY_TIMEOUT" in s["detail"] for s in pay["signals"])
    assert PAY_TEST in pay["related_tests"]
    assert areas["Checkout"]["untested_files"] == [CHECKOUT]
    assert data["not_impacted"] == ["Login", "Search"]
    assert [s["key"] for s in data["stories"]] == ["SHOP-123", "SHOP-130"]   # no CVE/SUREFIRE, no bot
    assert any("(major)" in s["detail"] for s in data["release_signals"])
    assert "docs/notes.md" in data["other_files"]


def test_text_and_markdown(release, capsys):
    _, text = run(release, capsys, "v1.0..v1.1")
    assert "SUGGESTED REGRESSION SCOPE" in text and "Not changed:" in text and "Login, Search" in text
    _, md = run(release, capsys, "v1.0..v1.1", "--format", "md")
    for section in ("### Suggested regression scope", "### Areas", "### Silent changes",
                    "### Stories in this release", "Test gaps"):
        assert section in md


def test_base_option_and_single_ref(release, capsys):
    code, out = run(release, capsys, "--base", "v1.0", "--format", "json")
    assert code == 0 and json.loads(out)["commits"] == 4
    code, out = run(release, capsys, "v1.0", "--format", "json")
    assert json.loads(out)["head"] == "HEAD"


def test_config_from_head_defines_areas(release, capsys):
    release.commit({".whattotest.toml": '[areas]\nMoney = ["**/payment/**", "db/migration/**"]\n'})
    _, out = run(release, capsys, "v1.0..HEAD", "--format", "json")
    areas = {a["name"]: a for a in json.loads(out)["areas"]}
    assert "Money" in areas and "Payment" not in areas and "Database" not in areas
    # with the migration in the same area, the risk adds up to high
    assert areas["Money"]["risk"] == "high"
    assert any("migration" in r for r in areas["Money"]["reasons"])


def test_tests_only_area(repo, capsys):
    repo.commit({PAY: java("PaymentService"), PAY_TEST: java("PaymentServiceTest")})
    repo.tag("a")
    repo.commit({PAY_TEST: java("PaymentServiceTest", "void t() {}")})
    _, out = run(repo, capsys, "a..HEAD", "--format", "json")
    data = json.loads(out)
    assert data["areas"] == [] and data["tests_only"] == ["Payment"]
    assert "Payment" not in data["not_impacted"]


def test_errors(repo, capsys):
    repo.commit({"a.txt": "x"})
    assert run(repo, capsys, "nope..HEAD")[0] == 2
    assert run(repo, capsys)[0] == 2


def test_init(repo, capsys):
    assert run(repo, capsys, "--init")[0] == 0
    assert (repo.path / ".whattotest.toml").exists()
    assert run(repo, capsys, "--init")[0] == 2
