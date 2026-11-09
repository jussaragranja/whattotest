"""Changes that rarely show up in a PR description but often break things."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import PurePosixPath

from whattotest.files import kind


@dataclass
class Signal:
    type: str        # migration | dependency | env | flag
    severity: str    # high | medium | low
    file: str
    detail: str
    name: str = ""


# ---------------------------------------------------------------- migrations

def migrations(changes) -> list[Signal]:
    out = []
    for c in changes:
        if kind(c.path) != "migration":
            continue
        if c.status == "A":
            out.append(Signal("migration", "high", c.path, "new database migration",
                              PurePosixPath(c.path).name))
        elif c.status == "D":
            out.append(Signal("migration", "high", c.path, "database migration deleted",
                              PurePosixPath(c.path).name))
        else:
            out.append(Signal("migration", "high", c.path,
                              "existing migration edited (already-applied migrations should not change)",
                              PurePosixPath(c.path).name))
    return out


# ---------------------------------------------------------------- dependencies

def _maven(text: str) -> dict[str, str]:
    block = re.search(r"<properties>(.*?)</properties>", text, re.S)
    props = dict(re.findall(r"<([\w.\-]+)>([^<]+)</\1>", block.group(1))) if block else {}
    out = {}
    for block in re.findall(r"<(?:dependency|plugin)>(.*?)</(?:dependency|plugin)>", text, re.S):
        a = re.search(r"<artifactId>([^<]+)</artifactId>", block)
        g = re.search(r"<groupId>([^<]+)</groupId>", block)
        v = re.search(r"<version>([^<]+)</version>", block)
        if a and v:
            version = v.group(1).strip()
            ref = re.fullmatch(r"\$\{([^}]+)\}", version)
            if ref:
                version = props.get(ref.group(1), version)
            out[f"{g.group(1).strip() + ':' if g else ''}{a.group(1).strip()}"] = version
    parent = re.search(r"<parent>.*?<artifactId>([^<]+)</artifactId>.*?<version>([^<]+)</version>.*?</parent>",
                       text, re.S)
    if parent:
        out[f"parent:{parent.group(1)}"] = parent.group(2)
    return out


def _gradle(text: str) -> dict[str, str]:
    out = {}
    for g, a, v in re.findall(r"""["']([\w.\-]+):([\w.\-]+):([\w.\-+]+)["']""", text):
        out[f"{g}:{a}"] = v
    for a, v in re.findall(r"""id\s*\(?\s*["']([\w.\-]+)["']\s*\)?\s*version\s*["']([\w.\-+]+)["']""", text):
        out[f"plugin:{a}"] = v
    return out


def _version_catalog(text: str) -> dict[str, str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    versions = data.get("versions", {})
    out = {}
    for alias, lib in data.get("libraries", {}).items():
        if isinstance(lib, str):
            parts = lib.split(":")
            if len(parts) == 3:
                out[f"{parts[0]}:{parts[1]}"] = parts[2]
            continue
        module = lib.get("module") or f"{lib.get('group', '')}:{lib.get('name', alias)}"
        v = lib.get("version")
        if isinstance(v, dict):
            v = versions.get(v.get("ref", ""), "")
        if v:
            out[module] = str(v)
    for k, v in versions.items():
        out.setdefault(f"version:{k}", str(v))
    return out


def _npm(text: str) -> dict[str, str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    out = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for k, v in (data.get(section) or {}).items():
            out[k] = str(v)
    return out


def _pip(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        m = re.match(r"([A-Za-z0-9_.\-\[\]]+)\s*(==|>=|~=|<=|>|<)\s*([\w.\-*+]+)", line)
        if m:
            out[m.group(1).split("[")[0].lower()] = m.group(3)
    return out


def _pyproject(text: str) -> dict[str, str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    deps = list(data.get("project", {}).get("dependencies", []))
    for group in data.get("project", {}).get("optional-dependencies", {}).values():
        deps += group
    out = _pip("\n".join(deps))
    for k, v in data.get("tool", {}).get("poetry", {}).get("dependencies", {}).items():
        if isinstance(v, str):
            out[k.lower()] = v.lstrip("^~=>")
    return out


PARSERS = {"pom.xml": _maven, "build.gradle": _gradle, "build.gradle.kts": _gradle,
           "libs.versions.toml": _version_catalog, "package.json": _npm,
           "requirements.txt": _pip, "pyproject.toml": _pyproject}


def _numbers(version: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", version)[:3]]


def is_major(old: str, new: str) -> bool:
    a, b = _numbers(old), _numbers(new)
    if not a or not b:
        return False
    if a[0] != b[0]:
        return True
    return a[0] == 0 and len(a) > 1 and len(b) > 1 and a[1] != b[1]  # 0.x: minor is breaking


def dependencies(changes, read_base, read_head) -> list[Signal]:
    out = []
    for c in changes:
        name = PurePosixPath(c.path).name
        parser = PARSERS.get(name) or (_pip if re.fullmatch(r"requirements[\w.\-]*\.txt", name) else None)
        if not parser:
            continue
        before = parser(read_base(c.old_path) or "") if c.old_path else {}
        after = parser(read_head(c.path) or "") if c.status != "D" else {}
        for dep in sorted(set(before) | set(after)):
            old, new = before.get(dep), after.get(dep)
            if old == new:
                continue
            if old is None:
                out.append(Signal("dependency", "medium", c.path, f"added {dep} {new}", dep))
            elif new is None:
                out.append(Signal("dependency", "medium", c.path, f"removed {dep} {old}", dep))
            elif is_major(old, new):
                out.append(Signal("dependency", "high", c.path, f"{dep} {old} → {new} (major)", dep))
            else:
                out.append(Signal("dependency", "low", c.path, f"{dep} {old} → {new}", dep))
    return out


# ---------------------------------------------------------------- env vars and flags

ENV_IN_CODE = [
    re.compile(r"""System\.getenv\(\s*"([A-Z][A-Z0-9_]+)"\s*\)"""),
    re.compile(r"""os\.(?:environ\.get|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']"""),
    re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]"""),
    re.compile(r"""process\.env\.([A-Z][A-Z0-9_]+)"""),
    re.compile(r"""process\.env\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]"""),
    re.compile(r"""import\.meta\.env\.([A-Z][A-Z0-9_]+)"""),
]
ENV_IN_CONFIG = [
    re.compile(r"""\$\{([A-Z][A-Z0-9_]+)(?::[^}]*)?\}"""),       # Spring / compose placeholders
]
ENV_IN_DOTENV = [
    re.compile(r"""^\s*(?:export\s+)?([A-Z][A-Z0-9_]+)\s*=""", re.MULTILINE),
]


def _names(text: str | None, patterns) -> set[str]:
    out: set[str] = set()
    for p in patterns:
        out |= set(p.findall(text or ""))
    return out


def _diff_names(changes, read_base, read_head, pick_patterns, type_: str, label: str,
                removed_severity: str) -> list[Signal]:
    out = []
    for c in changes:
        patterns = pick_patterns(c.path)
        if not patterns:
            continue
        before = _names(read_base(c.old_path) if c.old_path else "", patterns)
        after = _names(read_head(c.path) if c.status != "D" else "", patterns)
        for name in sorted(after - before):
            out.append(Signal(type_, "medium", c.path, f"new {label} {name}", name))
        for name in sorted(before - after):
            out.append(Signal(type_, removed_severity, c.path, f"{label} {name} no longer used here", name))
    return out


def env_vars(changes, read_base, read_head) -> list[Signal]:
    def pick(path: str):
        if PurePosixPath(path).name.startswith(".env"):
            return ENV_IN_DOTENV
        return {"code": ENV_IN_CODE, "config": ENV_IN_CONFIG}.get(kind(path), [])
    return _diff_names(changes, read_base, read_head, pick, "env", "environment variable", "low")


def flags(changes, read_base, read_head, patterns) -> list[Signal]:
    if not patterns:
        return []
    pick = lambda path: patterns if kind(path) in ("code", "config") else []
    return _diff_names(changes, read_base, read_head, pick, "flag", "feature flag", "medium")
