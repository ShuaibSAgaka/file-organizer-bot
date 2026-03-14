"""
mover.py — Safe file-moving logic with conflict resolution and an undo log.
"""

import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from .config import OrganizerConfig, Rule


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class MoveResult:
    src: str
    dst: str
    rule_name: str
    success: bool
    skipped: bool         = False
    skip_reason: str      = ""
    error: str            = ""
    timestamp: datetime   = field(default_factory=datetime.now)

    @property
    def filename(self) -> str:
        return os.path.basename(self.src)

    @property
    def dst_folder(self) -> str:
        return os.path.dirname(self.dst)


# ── Undo log ──────────────────────────────────────────────────────────────────

class UndoLog:
    """In-memory log of completed moves so the user can undo them."""

    def __init__(self, max_entries: int = 200):
        self._entries: list[MoveResult] = []
        self._max = max_entries

    def record(self, result: MoveResult):
        if result.success:
            self._entries.append(result)
            if len(self._entries) > self._max:
                self._entries.pop(0)

    def undo_last(self) -> Optional[MoveResult]:
        """Move the last file back to its original location. Returns the result or None."""
        if not self._entries:
            return None
        last = self._entries.pop()
        try:
            os.makedirs(os.path.dirname(last.src), exist_ok=True)
            shutil.move(last.dst, last.src)
            return last
        except OSError:
            # Put it back in the log — undo failed
            self._entries.append(last)
            return None

    def recent(self, n: int = 10) -> list[MoveResult]:
        return list(reversed(self._entries[-n:]))

    def __len__(self):
        return len(self._entries)


# ── File logger ───────────────────────────────────────────────────────────────

def _setup_file_logger(log_path: Optional[str]) -> Optional[logging.Logger]:
    if not log_path:
        return None
    logger = logging.getLogger("organizer.file")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
    return logger


# ── Conflict helpers ──────────────────────────────────────────────────────────

def _resolve_conflict(dst: str, strategy: str) -> tuple[Optional[str], str]:
    """
    Returns (final_dst, reason).
    final_dst is None when the file should be skipped.
    """
    if not os.path.exists(dst):
        return dst, ""

    if strategy == "skip":
        return None, "destination exists (skip)"

    if strategy == "replace":
        return dst, ""

    # "rename" — append _1, _2, …
    base, ext = os.path.splitext(dst)
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate, f"renamed to avoid conflict (_{counter})"
        counter += 1


# ── Core mover ────────────────────────────────────────────────────────────────

class FileMover:
    def __init__(self, config: OrganizerConfig):
        self.config      = config
        self.undo_log    = UndoLog()
        self._file_log   = _setup_file_logger(config.log_file)
        self.total_moved = 0
        self.total_skip  = 0
        self.total_error = 0

    def move(self, src: str, rule: Rule) -> MoveResult:
        """
        Move *src* to the destination defined by *rule*.
        Handles conflict resolution, directory creation, and logging.
        """
        src = os.path.abspath(src)

        if not os.path.isfile(src):
            result = MoveResult(src=src, dst="", rule_name=rule.name,
                                success=False, error="Source file not found")
            self._log(result)
            self.total_error += 1
            return result

        dest_dir = rule.resolve_destination(src)
        dst      = os.path.join(dest_dir, os.path.basename(src))

        # Prevent moving a file to itself
        if os.path.abspath(dst) == src:
            result = MoveResult(src=src, dst=dst, rule_name=rule.name,
                                success=False, skipped=True,
                                skip_reason="source == destination")
            self.total_skip += 1
            return result

        # Conflict resolution
        final_dst, conflict_note = _resolve_conflict(dst, self.config.on_conflict)
        if final_dst is None:
            result = MoveResult(src=src, dst=dst, rule_name=rule.name,
                                success=False, skipped=True,
                                skip_reason=conflict_note)
            self._log(result)
            self.total_skip += 1
            return result

        # Create destination directory
        try:
            os.makedirs(os.path.dirname(final_dst), exist_ok=True)
        except OSError as e:
            result = MoveResult(src=src, dst=final_dst, rule_name=rule.name,
                                success=False, error=f"mkdir failed: {e}")
            self._log(result)
            self.total_error += 1
            return result

        # Move
        try:
            shutil.move(src, final_dst)
            result = MoveResult(src=src, dst=final_dst, rule_name=rule.name,
                                success=True,
                                skip_reason=conflict_note)
            self.undo_log.record(result)
            self._log(result)
            self.total_moved += 1
            return result
        except OSError as e:
            result = MoveResult(src=src, dst=final_dst, rule_name=rule.name,
                                success=False, error=str(e))
            self._log(result)
            self.total_error += 1
            return result

    def _log(self, result: MoveResult):
        if not self._file_log:
            return
        if result.success:
            self._file_log.info(f"MOVED   {result.src!r}  →  {result.dst!r}  [{result.rule_name}]")
        elif result.skipped:
            self._file_log.info(f"SKIPPED {result.src!r}  ({result.skip_reason})")
        else:
            self._file_log.warning(f"ERROR   {result.src!r}  ({result.error})")