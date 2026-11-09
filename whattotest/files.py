"""What kind of file is this, and which business area does it belong to?"""
from __future__ import annotations

import fnmatch
import re
from collections import Counter
from pathlib import PurePosixPath

from whattotest.config import Config

CODE_EXT = {".java", ".kt", ".kts", ".scala", ".groovy", ".py", ".js", ".jsx", ".ts", ".tsx",
            ".vue", ".svelte", ".go", ".rb", ".cs", ".swift", ".m", ".mm", ".dart", ".php", ".rs"}
CONFIG_EXT = {".yml", ".yaml", ".properties", ".json", ".toml", ".ini", ".conf", ".env", ".xml"}

TEST_PATTERNS = (
    "test_*.py", "*_test.py", "tests/**", "**/tests/**", "test/**", "**/test/**",
    "src/test/**", "**/src/test/**", "*Test.java", "*Tests.java", "*IT.java", "*Test.kt",
    "*.test.*", "*.spec.*", "**/__tests__/**", "e2e/**", "**/e2e/**", "cypress/**", "**/cypress/**",
    "*Tests.swift", "**/*Tests/**", "**/androidTest/**", "**/integrationTest/**",
)
MIGRATION_PATTERNS = (
    "**/db/migration/**", "**/db/migrations/**", "**/migrations/**", "migrations/**",
    "**/alembic/versions/**", "**/prisma/migrations/**", "**/db/changelog/**",
    "**/liquibase/**", "**/flyway/**", "db/migrate/**", "**/db/migrate/**",
)
DEPENDENCY_FILES = {"pom.xml", "build.gradle", "build.gradle.kts", "package.json",
                    "requirements.txt", "pyproject.toml", "Podfile", "libs.versions.toml",
                    "Gemfile", "go.mod", "Cargo.toml", "pubspec.yaml"}
LOCK_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Podfile.lock",
              "Gemfile.lock", "go.sum", "Cargo.lock", "gradle.lockfile", "uv.lock"}
I18N_PATTERNS = ("**/i18n/**", "**/locales/**", "**/locale/**", "**/strings.xml",
                 "**/*.strings", "**/messages*.properties", "**/translations/**")
INFRA_PATTERNS = ("Dockerfile", "**/Dockerfile", "docker-compose*.yml", "**/helm/**",
                  "**/*.tf", "**/k8s/**", "**/kubernetes/**", "Jenkinsfile", ".gitlab-ci.yml",
                  ".github/workflows/**")
DOC_EXT = {".md", ".rst", ".adoc", ".txt"}

GENERIC_DIRS = {"src", "main", "java", "kotlin", "scala", "python", "lib", "app", "apps", "pkg",
                "internal", "source", "sources", "core", "common", "shared", "com", "org", "net",
                "io", "br", "de", "dev", "test", "tests", "resources", "js", "ts", "packages",
                "features", "modules", "domain", "components", "pages", "screens", "services"}
FEATURE_PARENTS = {"features", "modules", "domains", "domain", "pages", "screens", "packages",
                   "apps", "services", "views", "routes", "components"}


def match(path: str, patterns) -> bool:
    """fnmatch on the path and file name; a leading '**/' also matches at the repo root."""
    name = PurePosixPath(path).name
    for p in patterns:
        if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p):
            return True
        if p.startswith("**/") and fnmatch.fnmatch(path, p[3:]):
            return True
    return False


def kind(path: str) -> str:
    """test | migration | dependency | lockfile | i18n | infra | config | code | docs | other"""
    p = PurePosixPath(path)
    if p.name in LOCK_FILES:
        return "lockfile"
    if p.name in ("package-info.java", "module-info.java", "__init__.pyi"):
        return "other"
    if p.name in DEPENDENCY_FILES:
        return "dependency"
    if match(path, MIGRATION_PATTERNS):
        return "migration"
    if match(path, INFRA_PATTERNS):
        return "infra"
    if p.suffix in CODE_EXT and match(path, TEST_PATTERNS):
        return "test"
    if match(path, I18N_PATTERNS):
        return "i18n"
    if p.suffix in CODE_EXT:
        return "code"
    if p.suffix in DOC_EXT:
        return "docs"
    if p.suffix in CONFIG_EXT or p.name.startswith(".env"):
        return "config"
    return "other"


def _humanize(name: str) -> str:
    name = re.sub(r"\.(py|java|kt|ts|tsx|js|jsx|go|rb|cs|swift|dart)$", "", name)
    name = re.sub(r"(Service|Controller|Repository|Impl|Handler|Manager|Test|Tests|Spec)$", "", name)
    name = name.strip("_-.").replace("_", " ").replace("-", " ")
    return (name[:1].upper() + name[1:]) if name else name


def _class_family(filename: str) -> str:
    stem = _humanize(filename)
    first = re.match(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", stem)
    word = first.group(0) if first else stem
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word[:1].upper() + word[1:]


class AreaMapper:
    """Assigns files to business areas: configured globs first, then inference."""

    def __init__(self, cfg: Config, repo_files: list[str]):
        self.cfg = cfg
        code = [f for f in repo_files if kind(f) in ("code", "test")]
        self.java_prefix = self._java_prefix(code)
        self.py_packages = {str(PurePosixPath(f).parent) for f in repo_files
                            if f.endswith("__init__.py")}

    @staticmethod
    def _java_prefix(code: list[str]) -> tuple[str, ...]:
        """Common package prefix of the main Java/Kotlin sources (e.g. com/shop)."""
        pkgs = []
        for f in code:
            m = re.search(r"src/(?:main|test)/(?:java|kotlin)/(.+)/[^/]+$", f)
            if m:
                pkgs.append(tuple(m.group(1).split("/")))
        if not pkgs:
            return ()
        prefix = []
        for parts in zip(*pkgs):
            if len(set(parts)) != 1:
                break
            prefix.append(parts[0])
        return tuple(prefix)

    def area(self, path: str) -> str:
        for name, globs in self.cfg.areas.items():
            if match(path, globs):
                return name
        return self.infer(path)

    def infer(self, path: str) -> str:
        p = PurePosixPath(path)
        parts = list(p.parts)

        # Java / Kotlin: first package level below the common prefix
        m = re.search(r"src/(?:main|test)/(?:java|kotlin)/(.+)$", path)
        if m:
            *dirs, filename = m.group(1).split("/")
            n = len(self.java_prefix)
            rest = dirs[n:] if tuple(dirs[:n]) == self.java_prefix else dirs
            # sub-package below the common prefix; in a single-package project, the class
            # family (Coupon, Coupons, CouponException -> Coupon)
            return _humanize(rest[0]) if rest else _class_family(filename)

        # feature folders: src/features/checkout/..., packages/payments/...
        for i, part in enumerate(parts[:-1]):
            if part in FEATURE_PARENTS and i + 1 < len(parts) - 1:
                return _humanize(parts[i + 1])

        # Python packages: subpackage, or module of a flat package
        if p.suffix == ".py":
            if kind(path) == "test":
                return _humanize(re.sub(r"^test_|_test$", "", p.stem))
            parent = str(p.parent)
            if parent in self.py_packages:
                pkg_parts = p.parent.parts
                top = next((i for i in range(len(pkg_parts))
                            if "/".join(pkg_parts[:i + 1]) in self.py_packages), None)
                below = pkg_parts[top + 1:] if top is not None else ()
                if below:
                    return _humanize(below[0])
                if p.stem != "__init__":
                    return _humanize(p.stem)

        # JS/TS tests named after the module: Checkout.test.tsx
        if kind(path) == "test" and re.search(r"\.(test|spec)\.\w+$", p.name):
            return _humanize(p.name.split(".")[0])

        # fallback: first meaningful directory
        for part in parts[:-1]:
            if part.lower() not in GENERIC_DIRS and not part.startswith("."):
                return _humanize(part)
        return "Root"


def popular_areas(mapper: AreaMapper, files: list[str]) -> Counter:
    return Counter(mapper.area(f) for f in files if kind(f) == "code")
