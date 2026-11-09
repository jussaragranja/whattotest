"""Link production files to the tests that exercise them (no execution, no coverage data).

A test is linked to a production file when:
  - its name follows a convention (PaymentService <-> PaymentServiceTest, pricing.py <-> test_pricing.py,
    Cart.tsx <-> Cart.test.tsx), or
  - it imports the file (Python, Java/Kotlin, JS/TS), or references the class from the same package.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath


def _stem(path: str) -> str:
    name = PurePosixPath(path).name
    return name.split(".")[0]


def _test_subject(test_path: str) -> set[str]:
    """Names of the production units a test file is named after."""
    stem = _stem(test_path)
    out = {stem}
    for pattern in (r"^(.+?)(Tests?|IT|Spec)$", r"^Test(.+)$", r"^test_(.+)$", r"^(.+)_test$"):
        m = re.match(pattern, stem)
        if m:
            out.add(m.group(1))
    return {s.lower() for s in out}


def _python_module(path: str) -> str | None:
    p = PurePosixPath(path)
    if p.suffix != ".py":
        return None
    parts = list(p.with_suffix("").parts)
    if parts and parts[0] in ("src", "lib"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _jvm_fqcn(path: str) -> tuple[str, str] | None:
    m = re.search(r"src/\w+/(?:java|kotlin)/(.+)\.(?:java|kt)$", path)
    if not m:
        return None
    parts = m.group(1).split("/")
    return ".".join(parts[:-1]), parts[-1]


class LinkIndex:
    def __init__(self, tests: dict[str, str]):
        """tests: {test path: source}"""
        self.tests = tests
        self.by_subject: dict[str, set[str]] = {}
        for path in tests:
            for subject in _test_subject(path):
                self.by_subject.setdefault(subject, set()).add(path)
        self.packages = {}
        for path, src in tests.items():
            m = re.search(r"^\s*package\s+([\w.]+)", src, re.MULTILINE)
            self.packages[path] = m.group(1) if m else None

    def linked(self, prod_path: str) -> set[str]:
        out = set(self.by_subject.get(_stem(prod_path).lower(), set()))
        module = _python_module(prod_path)
        jvm = _jvm_fqcn(prod_path)
        stem = _stem(prod_path)
        for path, src in self.tests.items():
            if path in out:
                continue
            if module and re.search(rf"(?:from\s+{re.escape(module)}\s+import|import\s+{re.escape(module)}\b)", src):
                out.add(path)
            elif jvm:
                package, cls = jvm
                if re.search(rf"import\s+{re.escape(package)}\.{re.escape(cls)}\b", src) or (
                        self.packages.get(path) == package and re.search(rf"\b{re.escape(cls)}\b", src)):
                    out.add(path)
            elif PurePosixPath(prod_path).suffix in (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"):
                if re.search(rf"""from\s+['"][^'"]*/{re.escape(stem)}(?:\.\w+)?['"]""", src):
                    out.add(path)
        return out
