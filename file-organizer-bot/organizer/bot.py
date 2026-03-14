"""
bot.py — Orchestrates config loading, watcher, mover, and Rich TUI.
"""

import os
import sys
import threading
import argparse

from .config import load_config, ConfigError
from .mover import FileMover
from .watcher import FolderWatcher, WATCHDOG_AVAILABLE
from .ui import console, print_banner, print_config_summary, LiveDashboard


def _parse_args():
    parser = argparse.ArgumentParser(
        description="File Organizer Bot — watches a folder and auto-sorts files"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to organizer.yml (default: ./organizer.yml)"
    )
    return parser.parse_args()


def _check_deps():
    missing = []
    try:
        import yaml
    except ImportError:
        missing.append("pyyaml")
    if not WATCHDOG_AVAILABLE:
        missing.append("watchdog")
    try:
        import rich
    except ImportError:
        missing.append("rich")
    if missing:
        print(f"\n  Missing dependencies: {', '.join(missing)}")
        print(f"  Run:  pip install {' '.join(missing)}\n")
        sys.exit(1)


def run_bot():
    _check_deps()
    args = _parse_args()

    print_banner()

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        config = load_config(args.config)
    except ConfigError as e:
        console.print(f"\n  [bold bright_red]Config error:[/bold bright_red]  {e}\n")
        sys.exit(1)

    print_config_summary(config)

    # ── Validate watch folder ─────────────────────────────────────────────────
    watch_path = config.watch_path
    if not os.path.exists(watch_path):
        console.print(f"  [yellow]Watch folder does not exist — creating it:[/yellow]  {watch_path}")
        try:
            os.makedirs(watch_path, exist_ok=True)
        except OSError as e:
            console.print(f"  [bright_red]Cannot create watch folder: {e}[/bright_red]")
            sys.exit(1)

    # ── Wire up components ────────────────────────────────────────────────────
    mover     = FileMover(config)
    dashboard = LiveDashboard(config)

    watcher = FolderWatcher(
        config             = config,
        mover              = mover,
        on_result          = dashboard.record_result,
        on_skipped_noRule  = dashboard.record_no_rule,
    )

    # ── Undo input thread (reads 'u' from stdin while live dashboard runs) ────
    stop_event = threading.Event()

    def _undo_listener():
        while not stop_event.is_set():
            try:
                line = input()
            except (EOFError, OSError):
                break
            if line.strip().lower() == "u":
                result = mover.undo_log.undo_last()
                if result:
                    dashboard.record_undo(result)
                else:
                    pass  # nothing to undo — silently ignore

    undo_thread = threading.Thread(target=_undo_listener, daemon=True)

    # ── Start ─────────────────────────────────────────────────────────────────
    console.print(f"  [bold bright_green]✔[/bold bright_green]  Starting watcher on [bold cyan]{watch_path}[/bold cyan]")
    console.print("  [dim]Press[/dim] [bold]Ctrl+C[/bold] [dim]to stop.[/dim]")
    console.print("  [dim]Type[/dim]  [bold]u[/bold] [dim]+ Enter to undo the last move.[/dim]")
    console.print()

    watcher.start()
    dashboard.start()
    undo_thread.start()

    try:
        while watcher.is_alive:
            import time
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        watcher.stop()
        dashboard.stop()

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print("  [bold white]Session summary[/bold white]")
    console.print(f"    [bright_green]Moved  :[/bright_green]  {mover.total_moved}")
    console.print(f"    [yellow]Skipped:[/yellow]  {mover.total_skip}")
    console.print(f"    [bright_red]Errors :[/bright_red]  {mover.total_error}")
    if config.log_file:
        console.print(f"    [dim]Log    :[/dim]  {config.log_file}")
    console.print()
    console.print("  [dim]Goodbye![/dim]")
    console.print()