"""Optional configuration: .whattotest.toml (stdlib tomllib)."""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE = ".whattotest.toml"

DEFAULT_CONFIG = """\
# whattotest configuration (everything is optional)

# Business areas: name -> path globs. Without this, areas are inferred from
# the project structure (Java packages, Python packages, src/features/*, ...).
[areas]
# Checkout  = ["src/main/java/**/checkout/**", "web/src/features/checkout/**"]
# Payments  = ["src/main/java/**/payment/**", "db/migration/**"]

# Extra test locations per area (naming conventions and imports are used anyway)
[tests]
# Checkout = ["e2e/checkout/**"]

[signals]
# Regexes with one capture group for the flag name
flags = []
# flags = ['isEnabled\\("([\\w.-]+)"\\)', 'featureFlags\\.(\\w+)']
tickets = '\\b[A-Z][A-Z0-9]+-\\d+\\b'

[risk]
history_months = 6
fix_patterns = ["fix", "bug", "hotfix", "revert", "regression", "patch"]

# Paths to leave out of the analysis
ignore = ["docs/**", "**/*.md", ".github/**"]
"""


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    areas: dict[str, list[str]] = field(default_factory=dict)
    tests: dict[str, list[str]] = field(default_factory=dict)
    flag_patterns: list[re.Pattern] = field(default_factory=list)
    ticket_pattern: re.Pattern = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
    history_months: int = 6
    fix_pattern: re.Pattern = re.compile(r"\b(fix|fixes|fixed|bug|hotfix|revert|regression|patch)\b",
                                         re.IGNORECASE)
    ignore: list[str] = field(default_factory=list)


def from_text(text: str | None, origin: str = CONFIG_FILE) -> Config:
    if text is None:
        return Config()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{origin}: {e}") from e
    cfg = Config()
    cfg.areas = {k: list(v) for k, v in data.get("areas", {}).items()}
    cfg.tests = {k: list(v) for k, v in data.get("tests", {}).items()}
    signals = data.get("signals", {})
    try:
        cfg.flag_patterns = [re.compile(p) for p in signals.get("flags", [])]
        if "tickets" in signals:
            cfg.ticket_pattern = re.compile(signals["tickets"])
        risk = data.get("risk", {})
        cfg.history_months = int(risk.get("history_months", 6))
        if "fix_patterns" in risk:
            words = "|".join(re.escape(w) for w in risk["fix_patterns"])
            cfg.fix_pattern = re.compile(rf"\b({words})\w*\b", re.IGNORECASE)
    except (re.error, ValueError) as e:
        raise ConfigError(f"{origin}: {e}") from e
    cfg.ignore = list(data.get("ignore", []))
    return cfg


def load(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"{path}: file not found")
    return from_text(path.read_text(), str(path))
