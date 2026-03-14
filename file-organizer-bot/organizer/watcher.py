"""
watcher.py — Watchdog-based folder monitor.
Debounces rapid events and delegates to FileMover + RichUI.
"""

import os
import time
import threading
from typing import Callable

try:
    from watchdog.observers import Observer
    from watchdog.events import (
        FileSystemEventHandler,
        FileCreatedEvent,
        FileMovedEvent,
        FileModifiedEvent,
    )
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from .config import OrganizerConfig, find_matching_rule
from .mover import FileMover, MoveResult


# ── Debounce helper ───────────────────────────────────────────────────────────

class _Debouncer:
    """
    Holds a pending timer per file path.
    Resets the timer if the same file fires again within the settle window.
    """
    def __init__(self, delay: float, callback: Callable[[str], None]):
        self._delay    = delay
        self._callback = callback
        self._timers: dict[str, threading.Timer] = {}
        self._lock     = threading.Lock()

    def trigger(self, path: str):
        with self._lock:
            existing = self._timers.pop(path, None)
            if existing:
                existing.cancel()
            t = threading.Timer(self._delay, self._fire, args=(path,))
            self._timers[path] = t
            t.start()

    def _fire(self, path: str):
        with self._lock:
            self._timers.pop(path, None)
        self._callback(path)

    def cancel_all(self):
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()


# ── Event handler ─────────────────────────────────────────────────────────────

class OrganizerHandler(FileSystemEventHandler):
    def __init__(
        self,
        config: OrganizerConfig,
        mover: FileMover,
        on_result: Callable[[MoveResult], None],
        on_skipped_noRule: Callable[[str], None],
    ):
        super().__init__()
        self._config          = config
        self._mover           = mover
        self._on_result       = on_result
        self._on_skipped      = on_skipped_noRule
        self._debouncer       = _Debouncer(config.settle_delay, self._process)
        self._watch_path      = os.path.abspath(config.watch_path)

    # Watchdog callbacks
    def on_created(self, event):
        if not event.is_directory:
            self._debouncer.trigger(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._debouncer.trigger(event.dest_path)

    def on_modified(self, event):
        # Only handle modifications for files in the watch root (not subdirs
        # unless recursive=True) to avoid thrash.
        if not event.is_directory:
            parent = os.path.dirname(os.path.abspath(event.src_path))
            if parent == self._watch_path or self._config.recursive:
                self._debouncer.trigger(event.src_path)

    # Core processing
    def _process(self, path: str):
        if not os.path.isfile(path):
            return

        # Don't move files already inside a destination folder
        # (only act on files directly dropped in the watch root,
        #  unless recursive is True)
        if not self._config.recursive:
            parent = os.path.dirname(os.path.abspath(path))
            if parent != self._watch_path:
                return

        rule = find_matching_rule(path, self._config.rules)
        if rule is None:
            self._on_skipped(path)
            return

        result = self._mover.move(path, rule)
        self._on_result(result)

    def stop(self):
        self._debouncer.cancel_all()


# ── Watcher ───────────────────────────────────────────────────────────────────

class FolderWatcher:
    def __init__(
        self,
        config: OrganizerConfig,
        mover: FileMover,
        on_result: Callable[[MoveResult], None],
        on_skipped_noRule: Callable[[str], None],
    ):
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError(
                "watchdog is not installed. Run:  pip install pyyaml watchdog rich"
            )
        self._config   = config
        self._handler  = OrganizerHandler(config, mover, on_result, on_skipped_noRule)
        self._observer = Observer()

    def start(self):
        watch_path = self._config.watch_path
        os.makedirs(watch_path, exist_ok=True)
        self._observer.schedule(
            self._handler,
            watch_path,
            recursive=self._config.recursive,
        )
        self._observer.start()

    def stop(self):
        self._handler.stop()
        self._observer.stop()
        self._observer.join()

    @property
    def is_alive(self) -> bool:
        return self._observer.is_alive()