#!/usr/bin/env python3
"""
File Organizer Bot — Day 3 of 30
Watches a folder and auto-sorts files using custom rules
defined in organizer.yml. Rich TUI with live event log.
"""

from organizer.bot import run_bot

if __name__ == "__main__":
    run_bot()