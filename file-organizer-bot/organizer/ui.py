"""
ui.py — Rich live dashboard for the File Organizer Bot.
Shows a real-time event feed, stats panel, and rule summary.
"""

import os
from datetime import datetime
from collections import deque
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.rule import Rule as RichRule
from rich.columns import Columns
from rich import box

from .config import OrganizerConfig
from .mover import MoveResult

console = Console()

MAX_EVENTS = 30   # how many events to keep in the live feed

BANNER = r"""
  ███████╗██╗██╗     ███████╗     ██████╗ ██████╗  ██████╗
  ██╔════╝██║██║     ██╔════╝    ██╔═══██╗██╔══██╗██╔════╝
  █████╗  ██║██║     █████╗      ██║   ██║██████╔╝██║  ███╗
  ██╔══╝  ██║██║     ██╔══╝      ██║   ██║██╔══██╗██║   ██║
  ██║     ██║███████╗███████╗    ╚██████╔╝██║  ██║╚██████╔╝
  ╚═╝     ╚═╝╚══════╝╚══════╝     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝
"""

def _escape(v) -> str:
    return str(v).replace("[", "\\[").replace("]", "\\]")

def _short_path(path: str, max_len: int = 48) -> str:
    p = path.replace("\\", "/")
    if len(p) > max_len:
        return "…" + p[-(max_len - 1):]
    return p


# ── Static banner ─────────────────────────────────────────────────────────────

def print_banner():
    console.print(BANNER, style="bold bright_cyan", highlight=False)
    console.print(
        Align.center(Text(
            "📁  File Organizer Bot  ·  Live Folder Watcher  ·  Custom Rules",
            style="bold white"
        ))
    )
    console.print(Align.center(Text("─" * 72, style="grey30")))
    console.print()


def print_config_summary(config: OrganizerConfig):
    console.print(RichRule("[bold white] Configuration [/bold white]", style="grey30"))
    console.print()

    grid = Table.grid(expand=False, padding=(0, 2))
    grid.add_column(style="dim", min_width=18)
    grid.add_column(style="bold white")

    grid.add_row("Watch folder",  _escape(config.watch_path))
    grid.add_row("Config file",   _escape(config.config_path))
    grid.add_row("Settle delay",  f"{config.settle_delay}s")
    grid.add_row("Recursive",     "Yes" if config.recursive else "No")
    grid.add_row("On conflict",   config.on_conflict)
    grid.add_row("Log file",      _escape(config.log_file) if config.log_file else "disabled")
    grid.add_row("Rules loaded",  str(len(config.rules)))

    console.print(grid)
    console.print()

    # Rules table
    tbl = Table(box=box.SIMPLE_HEAD, border_style="grey30", expand=True,
                header_style="bold white", show_edge=False)
    tbl.add_column("#",          justify="right", style="dim",         min_width=3)
    tbl.add_column("Rule Name",  style="bold cyan",                    min_width=18)
    tbl.add_column("Match",      style="dim",                          min_width=26)
    tbl.add_column("Destination",style="white")

    for i, rule in enumerate(config.rules, 1):
        match_parts = []
        if rule.extensions:
            match_parts.append(", ".join(rule.extensions[:5]) +
                               (f" +{len(rule.extensions)-5}" if len(rule.extensions) > 5 else ""))
        if rule.name_contains:
            match_parts.append(f"contains: {rule.name_contains}")
        if rule.name_regex:
            match_parts.append(f"regex: {rule.name_regex[:30]}")
        if rule.min_size_kb:
            match_parts.append(f">={rule.min_size_kb}KB")
        if rule.max_size_kb:
            match_parts.append(f"<={rule.max_size_kb}KB")
        match_str = " | ".join(match_parts) if match_parts else "(any)"
        tbl.add_row(str(i), rule.name, match_str, _short_path(rule.destination))

    console.print(tbl)
    console.print()


# ── Live dashboard ────────────────────────────────────────────────────────────

class LiveDashboard:
    """
    Renders a refreshing Rich Live panel showing:
      - Stats (moved / skipped / errors)
      - Recent event log
    """

    def __init__(self, config: OrganizerConfig):
        self._config      = config
        self._events: deque[dict] = deque(maxlen=MAX_EVENTS)
        self._moved       = 0
        self._skipped     = 0
        self._errors      = 0
        self._no_rule     = 0
        self._start_time  = datetime.now()
        self._live: Optional[Live] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def record_result(self, result: MoveResult):
        if result.success:
            self._moved += 1
            self._events.append({
                "ts":      datetime.now().strftime("%H:%M:%S"),
                "icon":    "[bold bright_green]✔[/bold bright_green]",
                "label":   "[bright_green]MOVED[/bright_green]",
                "file":    _escape(_short_path(result.src)),
                "detail":  _escape(f"→ {_short_path(result.dst_folder)}  [{result.rule_name}]"),
            })
        elif result.skipped:
            self._skipped += 1
            self._events.append({
                "ts":     datetime.now().strftime("%H:%M:%S"),
                "icon":   "[yellow]–[/yellow]",
                "label":  "[yellow]SKIP[/yellow]",
                "file":   _escape(_short_path(result.src)),
                "detail": _escape(result.skip_reason),
            })
        else:
            self._errors += 1
            self._events.append({
                "ts":     datetime.now().strftime("%H:%M:%S"),
                "icon":   "[bright_red]✘[/bright_red]",
                "label":  "[bright_red]ERROR[/bright_red]",
                "file":   _escape(_short_path(result.src)),
                "detail": _escape(result.error),
            })
        self._refresh()

    def record_no_rule(self, path: str):
        self._no_rule += 1
        self._events.append({
            "ts":     datetime.now().strftime("%H:%M:%S"),
            "icon":   "[dim]○[/dim]",
            "label":  "[dim]NO RULE[/dim]",
            "file":   _escape(_short_path(path)),
            "detail": "[dim]no matching rule — ignored[/dim]",
        })
        self._refresh()

    def record_undo(self, result: MoveResult):
        self._moved = max(0, self._moved - 1)
        self._events.append({
            "ts":     datetime.now().strftime("%H:%M:%S"),
            "icon":   "[cyan]↩[/cyan]",
            "label":  "[cyan]UNDO[/cyan]",
            "file":   _escape(_short_path(result.dst)),
            "detail": _escape(f"→ {_short_path(result.src)}"),
        })
        self._refresh()

    def start(self):
        self._live = Live(
            self._render(),
            console=console,
            refresh_per_second=4,
            screen=False,
        )
        self._live.start()

    def stop(self):
        if self._live:
            self._live.stop()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _refresh(self):
        if self._live:
            self._live.update(self._render())

    def _render(self):
        uptime = str(datetime.now() - self._start_time).split(".")[0]

        # ── Stats row ──────────────────────────────────────────
        stats = Table.grid(padding=(0, 3))
        stats.add_column()
        stats.add_column()
        stats.add_column()
        stats.add_column()
        stats.add_column()

        def stat_cell(value, label, color):
            t = Text()
            t.append(f" {value} ", style=f"bold black on {color}")
            t.append(f"  {label}", style="dim")
            return t

        stats.add_row(
            stat_cell(self._moved,   "moved",   "bright_green"),
            stat_cell(self._skipped, "skipped", "yellow"),
            stat_cell(self._errors,  "errors",  "bright_red"),
            stat_cell(self._no_rule, "no rule", "grey50"),
            Text(f"  uptime {uptime}", style="dim"),
        )

        stats_panel = Panel(
            stats,
            title="[bold white] Stats [/bold white]",
            border_style="grey30",
            padding=(0, 1),
        )

        # ── Event log ──────────────────────────────────────────
        if not self._events:
            log_content = Text("  Watching for files…", style="dim")
        else:
            log_tbl = Table(box=None, show_header=False, expand=True,
                            padding=(0, 1), show_edge=False)
            log_tbl.add_column(min_width=8,  no_wrap=True)   # time
            log_tbl.add_column(min_width=3,  no_wrap=True)   # icon
            log_tbl.add_column(min_width=8,  no_wrap=True)   # label
            log_tbl.add_column(min_width=30)                  # filename
            log_tbl.add_column()                              # detail

            for ev in reversed(self._events):
                log_tbl.add_row(
                    f"[dim]{ev['ts']}[/dim]",
                    ev["icon"],
                    ev["label"],
                    ev["file"],
                    ev["detail"],
                )
            log_content = log_tbl

        log_panel = Panel(
            log_content,
            title=f"[bold white] Event Log [/bold white][dim]  (last {MAX_EVENTS})[/dim]",
            border_style="bright_cyan",
            padding=(0, 1),
        )

        # ── Footer hint ────────────────────────────────────────
        footer = Text()
        footer.append("  Ctrl+C", style="bold white")
        footer.append(" to stop  ", style="dim")
        footer.append("  u + Enter", style="bold white")
        footer.append(" to undo last move  ", style="dim")
        footer.append("  Watching: ", style="dim")
        footer.append(_escape(self._config.watch_path), style="bold cyan")

        from rich.console import Group
        return Group(stats_panel, log_panel, footer)