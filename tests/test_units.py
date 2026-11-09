from whattotest.config import Config, ConfigError, from_text
from whattotest.files import AreaMapper, kind
from whattotest.signals import (Signal, _gradle, _maven, _npm, _pip, _pyproject, _version_catalog,
                                dependencies, env_vars, flags, is_major, migrations)
from whattotest.gitio import FileChange
from whattotest.testlink import LinkIndex

import pytest
import re


# ---------------------------------------------------------------- kinds

@pytest.mark.parametrize("path, expected", [
    ("src/main/java/com/shop/Pay.java", "code"),
    ("src/test/java/com/shop/PayTest.java", "test"),
    ("tests/test_pricing.py", "test"),
    ("web/src/Cart.test.tsx", "test"),
    ("db/migration/V2__add.sql", "migration"),
    ("app/alembic/versions/abc_add.py", "migration"),
    ("pom.xml", "dependency"),
    ("package-lock.json", "lockfile"),
    ("src/main/resources/application.yml", "config"),
    ("app/src/main/res/values/strings.xml", "i18n"),
    ("Dockerfile", "infra"),
    ("README.md", "docs"),
    ("src/main/java/com/shop/package-info.java", "other"),
])
def test_kind(path, expected):
    assert kind(path) == expected


# ---------------------------------------------------------------- areas

def test_java_areas_below_common_package():
    files = ["src/main/java/com/shop/checkout/CheckoutService.java",
             "src/main/java/com/shop/payment/PaymentService.java",
             "src/main/java/com/shop/payment/gateway/Stripe.java",
             "src/test/java/com/shop/payment/PaymentServiceTest.java"]
    m = AreaMapper(Config(), files)
    assert [m.area(f) for f in files] == ["Checkout", "Payment", "Payment", "Payment"]


def test_single_package_java_groups_class_families():
    files = ["src/main/java/shop/Coupon.java", "src/main/java/shop/Coupons.java",
             "src/main/java/shop/CouponException.java", "src/test/java/shop/CouponsTest.java",
             "src/main/java/shop/ShippingMethod.java"]
    m = AreaMapper(Config(), files)
    assert [m.area(f) for f in files] == ["Coupon", "Coupon", "Coupon", "Coupon", "Shipping"]


def test_python_flat_package_and_subpackages():
    files = ["shop/__init__.py", "shop/pricing.py", "tests/test_pricing.py",
             "app/__init__.py", "app/checkout/__init__.py", "app/checkout/service.py"]
    m = AreaMapper(Config(), files)
    assert m.area("shop/pricing.py") == "Pricing"
    assert m.area("tests/test_pricing.py") == "Pricing"
    assert m.area("app/checkout/service.py") == "Checkout"


def test_js_feature_folders():
    m = AreaMapper(Config(), [])
    assert m.area("web/src/features/cart/Cart.tsx") == "Cart"
    assert m.area("packages/payments/src/index.ts") == "Payments"


def test_configured_areas_win():
    cfg = from_text('[areas]\nCheckout = ["web/**/checkout/**", "src/**/cart/**"]\n')
    m = AreaMapper(cfg, [])
    assert m.area("src/main/java/com/shop/cart/Cart.java") == "Checkout"


def test_bad_config_is_an_error():
    with pytest.raises(ConfigError):
        from_text("[signals]\nflags = ['(unclosed']\n")


# ---------------------------------------------------------------- signals

def fc(path, status="M", old=None):
    return FileChange(path, old if old is not None else (None if status == "A" else path), status)


def test_migrations():
    sigs = migrations([fc("db/migration/V3__x.sql", "A"), fc("db/migration/V1__init.sql", "M"),
                       fc("src/A.java")])
    assert [s.detail for s in sigs] == ["new database migration",
                                        "existing migration edited (already-applied migrations should not change)"]


def test_major_versions():
    assert is_major("2.7.18", "3.0.0")
    assert is_major("0.11.0", "0.12.0")
    assert not is_major("3.5.6", "3.6.0")
    assert not is_major("1.0", "x")


def test_maven_with_properties():
    pom = """<project><parent><artifactId>spring-boot-starter-parent</artifactId><version>2.7.18</version></parent>
    <properties><stripe.version>22.1.0</stripe.version></properties>
    <dependencies><dependency><groupId>com.stripe</groupId><artifactId>stripe-java</artifactId>
    <version>${stripe.version}</version></dependency></dependencies></project>"""
    deps = _maven(pom)
    assert deps["com.stripe:stripe-java"] == "22.1.0"
    assert deps["parent:spring-boot-starter-parent"] == "2.7.18"


def test_other_manifests():
    assert _gradle('implementation "com.squareup.okhttp3:okhttp:4.12.0"') == {"com.squareup.okhttp3:okhttp": "4.12.0"}
    assert _npm('{"dependencies": {"react": "^18.3.1"}}') == {"react": "^18.3.1"}
    assert _pip("requests==2.31.0  # http\nflask>=3.0") == {"requests": "2.31.0", "flask": "3.0"}
    assert _pyproject('[project]\ndependencies = ["httpx>=0.27"]\n') == {"httpx": "0.27"}
    assert _version_catalog('[versions]\nktor="2.3.0"\n[libraries]\nktor-core={module="io.ktor:ktor-core",version.ref="ktor"}\n')["io.ktor:ktor-core"] == "2.3.0"


def test_dependency_signals():
    base = {"pom.xml": "<dependency><groupId>g</groupId><artifactId>a</artifactId><version>1.0.0</version></dependency>"
                       "<dependency><groupId>g</groupId><artifactId>b</artifactId><version>1.0.0</version></dependency>"}
    head = {"pom.xml": "<dependency><groupId>g</groupId><artifactId>a</artifactId><version>2.0.0</version></dependency>"
                       "<dependency><groupId>g</groupId><artifactId>c</artifactId><version>1.0.0</version></dependency>"}
    sigs = dependencies([fc("pom.xml")], base.get, head.get)
    assert {(s.severity, s.detail) for s in sigs} == {
        ("high", "g:a 1.0.0 → 2.0.0 (major)"), ("medium", "removed g:b 1.0.0"), ("medium", "added g:c 1.0.0")}


def test_env_vars_in_code_config_and_dotenv():
    base = {"src/Pay.java": 'String k = System.getenv("API_KEY");',
            "app/settings.py": "x = os.getenv('DB_URL')",
            "src/main/resources/application.yml": "url: ${DB_URL}",
            ".env.example": "DB_URL=\n"}
    head = {"src/Pay.java": 'String k = System.getenv("API_KEY"); int t = Integer.parseInt(System.getenv("PAY_TIMEOUT"));',
            "app/settings.py": "x = os.environ['DB_URL']",
            "src/main/resources/application.yml": "url: ${DB_URL}\ntimeout: ${PAY_TIMEOUT:30}",
            ".env.example": "DB_URL=\nPAY_TIMEOUT=30\n"}
    sigs = env_vars([fc(p) for p in base], base.get, head.get)
    assert sorted((s.file, s.name) for s in sigs) == [
        (".env.example", "PAY_TIMEOUT"), ("src/Pay.java", "PAY_TIMEOUT"),
        ("src/main/resources/application.yml", "PAY_TIMEOUT")]


def test_flags_need_patterns():
    base = {"src/A.java": 'if (flags.isEnabled("old")) {}'}
    head = {"src/A.java": 'if (flags.isEnabled("new_checkout")) {}'}
    assert flags([fc("src/A.java")], base.get, head.get, []) == []
    sigs = flags([fc("src/A.java")], base.get, head.get, [re.compile(r'isEnabled\("([\w.-]+)"\)')])
    assert {(s.name, s.detail.split()[0]) for s in sigs} == {("new_checkout", "new"), ("old", "feature")}


# ---------------------------------------------------------------- test links

def test_test_links():
    index = LinkIndex({
        "src/test/java/com/shop/payment/PaymentServiceTest.java": "package com.shop.payment;",
        "src/test/java/com/shop/payment/RefundFlowTest.java": "package com.shop.payment;\n new Refunds();",
        "tests/test_checkout.py": "from shop.pricing import apply_discount",
        "web/src/Cart.test.tsx": "import { Cart } from './Cart'",
        "web/src/flows/checkout.spec.ts": "import { Cart } from '../Cart'",
    })
    assert index.linked("src/main/java/com/shop/payment/PaymentService.java") == {
        "src/test/java/com/shop/payment/PaymentServiceTest.java"}
    assert index.linked("src/main/java/com/shop/payment/Refunds.java") == {
        "src/test/java/com/shop/payment/RefundFlowTest.java"}
    assert index.linked("shop/pricing.py") == {"tests/test_checkout.py"}
    assert index.linked("web/src/Cart.tsx") == {"web/src/Cart.test.tsx", "web/src/flows/checkout.spec.ts"}
    assert index.linked("shop/unrelated.py") == set()
