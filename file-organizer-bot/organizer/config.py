"""
config.py — Load organizer.yml and expose typed config + rule matching.
"""

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # handled gracefully at load time

DEFAULT_CONFIG_NAME = "organizer.yml"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Rule:
    name: str
    destination: str
    extensions: list[str]         = field(default_factory=list)
    name_contains: Optional[str]  = None
    name_regex: Optional[str]     = None
    min_size_kb: Optional[float]  = None
    max_size_kb: Optional[float]  = None
    older_than_days: Optional[int]= None
    _regex: Optional[re.Pattern]  = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # Normalise extensions to lowercase with leading dot
        self.extensions = [
            e.lower() if e.startswith(".") else f".{e.lower()}"
            for e in (self.extensions or [])
        ]
        if self.name_regex:
            try:
                self._regex = re.compile(self.name_regex, re.IGNORECASE)
            except re.error:
                self._regex = None

    def matches(self, path: str) -> bool:
        """Return True if *all* specified criteria match this file."""
        p    = Path(path)
        name = p.name
        ext  = p.suffix.lower()

        # Extension check
        if self.extensions and ext not in self.extensions:
            return False

        # Name contains
        if self.name_contains and self.name_contains.lower() not in name.lower():
            return False

        # Name regex
        if self._regex and not self._regex.match(name):
            return False

        # Size checks
        try:
            size_kb = p.stat().st_size / 1024
        except OSError:
            size_kb = 0

        if self.min_size_kb is not None and size_kb < self.min_size_kb:
            return False
        if self.max_size_kb is not None and size_kb > self.max_size_kb:
            return False

        # Age check
        if self.older_than_days is not None:
            try:
                mtime    = p.stat().st_mtime
                age_days = (time.time() - mtime) / 86400
                if age_days < self.older_than_days:
                    return False
            except OSError:
                return False

        return True

    def resolve_destination(self, path: str) -> str:
        """Expand {year}, {month}, {ext} tokens in the destination path."""
        p    = Path(path)
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            mtime = datetime.now()

        dest = self.destination
        dest = dest.replace("{year}",  mtime.strftime("%Y"))
        dest = dest.replace("{month}", mtime.strftime("%m"))
        dest = dest.replace("{ext}",   p.suffix.lstrip(".").lower())
        return os.path.expanduser(dest)


@dataclass
class OrganizerConfig:
    watch_folder: str
    rules: list[Rule]
    settle_delay: float   = 2.0
    recursive: bool       = False
    on_conflict: str      = "rename"     # rename | skip | replace
    log_file: Optional[str] = "organizer.log"
    config_path: str      = ""

    @property
    def watch_path(self) -> str:
        return os.path.expanduser(self.watch_folder)


# ── Loader ────────────────────────────────────────────────────────────────────

class ConfigError(Exception):
    pass


def load_config(config_path: Optional[str] = None) -> OrganizerConfig:
    if yaml is None:
        raise ConfigError(
            "PyYAML is not installed. Run:  pip install pyyaml watchdog rich"
        )

    if config_path is None:
        config_path = os.path.join(os.getcwd(), DEFAULT_CONFIG_NAME)

    config_path = os.path.abspath(os.path.expanduser(config_path))

    if not os.path.exists(config_path):
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"YAML parse error in {config_path}: {e}")

    if not isinstance(raw, dict):
        raise ConfigError("Config file must be a YAML mapping.")

    watch_folder = raw.get("watch_folder", "~/Downloads")
    settle_delay = float(raw.get("settle_delay", 2))
    recursive    = bool(raw.get("recursive", False))
    on_conflict  = raw.get("on_conflict", "rename")
    log_file_raw = raw.get("log_file", "organizer.log")

    # Resolve log_file relative to the config file's directory
    if log_file_raw:
        log_file = os.path.join(os.path.dirname(config_path), log_file_raw)
    else:
        log_file = None

    if on_conflict not in ("rename", "skip", "replace"):
        raise ConfigError(f"on_conflict must be 'rename', 'skip', or 'replace'. Got: {on_conflict!r}")

    raw_rules = raw.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ConfigError("'rules' must be a list.")

    rules: list[Rule] = []
    for i, r in enumerate(raw_rules):
        if not isinstance(r, dict):
            raise ConfigError(f"Rule #{i+1} must be a mapping.")
        dest = r.get("destination")
        if not dest:
            raise ConfigError(f"Rule #{i+1} is missing 'destination'.")
        rule = Rule(
            name           = r.get("name", f"Rule {i+1}"),
            destination    = dest,
            extensions     = r.get("extensions", []),
            name_contains  = r.get("name_contains"),
            name_regex     = r.get("name_regex"),
            min_size_kb    = r.get("min_size_kb"),
            max_size_kb    = r.get("max_size_kb"),
            older_than_days= r.get("older_than_days"),
        )
        rules.append(rule)

    return OrganizerConfig(
        watch_folder = watch_folder,
        rules        = rules,
        settle_delay = settle_delay,
        recursive    = recursive,
        on_conflict  = on_conflict,
        log_file     = log_file,
        config_path  = config_path,
    )


def find_matching_rule(path: str, rules: list[Rule]) -> Optional[Rule]:
    """Return the first rule that matches the file, or None."""
    for rule in rules:
        if rule.matches(path):
            return rule
    return None