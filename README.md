# 📁 File Organizer Bot

> A live folder watcher that auto-sorts files using **custom rules defined in a YAML config**. Drop a file into your watched folder and it moves instantly — no manual sorting ever again.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Rich](https://img.shields.io/badge/Rich-TUI-brightgreen?style=flat-square)
![Watchdog](https://img.shields.io/badge/Watchdog-live%20watcher-orange?style=flat-square)
![YAML](https://img.shields.io/badge/Config-YAML-red?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

---

## ✨ What It Does

- **Watches** a folder (e.g. `~/Downloads`) in real time using `watchdog`
- **Matches** every new file against your custom YAML rules (extension, name pattern, regex, file size)
- **Moves** matching files to the right destination — with `{year}` / `{month}` / `{ext}` tokens supported in paths
- **Debounces** events so partially-written files are never touched prematurely
- **Resolves conflicts** automatically (rename / skip / replace)
- **Undo** the last move anytime by typing `u` + Enter
- **Logs** every action to a file for auditing
- **Live Rich dashboard** shows a real-time event feed and stats

---

## 🖥️ Demo

```
  ┌─ Stats ──────────────────────────────────────────────────────────────────┐
  │  ✔ 12  moved     –  2  skipped    ✘  0  errors    ○  3  no rule         │
  │  uptime 0:04:22                                                           │
  └───────────────────────────────────────────────────────────────────────────┘
  ┌─ Event Log (last 30) ─────────────────────────────────────────────────────┐
  │  14:22:01  ✔  MOVED    invoice_march.pdf   → ~/Documents/PDFs  [PDFs]    │
  │  14:21:58  ✔  MOVED    vacation.jpg        → ~/Pictures/2025/03 [Images] │
  │  14:21:44  –  SKIP     report.pdf          destination exists             │
  │  14:21:30  ○  NO RULE  random_file.xyz     no matching rule — ignored     │
  └───────────────────────────────────────────────────────────────────────────┘
  Ctrl+C to stop    u + Enter to undo last move    Watching: ~/Downloads
```

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/file-organizer-bot.git
cd file-organizer-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit the config to match your folders & rules
nano organizer.yml   # or open in VS Code

# 4. Run
python main.py

# 5. Use a custom config path
python main.py --config ~/my-rules.yml
```

---

## ⚙️ Configuring Rules (`organizer.yml`)

```yaml
watch_folder: "~/Downloads"
settle_delay: 2          # seconds to wait before acting (prevents partial files)
recursive: false         # watch subfolders too?
on_conflict: "rename"    # rename | skip | replace
log_file: "organizer.log"

rules:
  - name: "PDFs"
    extensions: [".pdf"]
    destination: "~/Documents/PDFs"

  - name: "Images by month"
    extensions: [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    destination: "~/Pictures/{year}/{month}"   # ← date tokens!

  - name: "Screenshots"
    name_regex: "^screenshot.*\\.png$"
    destination: "~/Pictures/Screenshots"

  - name: "Large files"
    min_size_kb: 512000    # >= 500 MB
    destination: "~/Downloads/LargeFiles"

  - name: "Work invoices"
    name_contains: "invoice"
    extensions: [".pdf"]
    destination: "~/Documents/Work/Invoices"
```

### Rule match fields

| Field | Type | Description |
|---|---|---|
| `extensions` | list | File extensions e.g. `[".pdf", ".docx"]` |
| `name_contains` | string | Substring in filename (case-insensitive) |
| `name_regex` | string | Python regex matched against filename |
| `min_size_kb` | number | File must be >= N KB |
| `max_size_kb` | number | File must be <= N KB |
| `older_than_days` | number | File's modified date must be older than N days |

### Destination tokens

| Token | Expands to |
|---|---|
| `{year}` | 4-digit year of file's modified date |
| `{month}` | 2-digit month (01–12) |
| `{ext}` | Extension without dot e.g. `pdf` |

---

## 📁 Project Structure

```
file-organizer-bot/
├── main.py               ← Entry point
├── organizer.yml         ← Your rules config (edit this!)
├── requirements.txt
└── organizer/
    ├── __init__.py
    ├── config.py         ← YAML loader + Rule dataclass + matcher
    ├── mover.py          ← Safe file mover + conflict resolution + undo log
    ├── watcher.py        ← Watchdog event handler + debouncer
    ├── ui.py             ← Rich live dashboard
    └── bot.py            ← Main orchestrator
```

---

## 🗺️ Roadmap

- [ ] `--dry-run` flag — preview moves without executing them
- [ ] `--sort-existing` — one-shot sort of all files currently in the folder
- [ ] System tray icon (Windows/macOS)
- [ ] Web UI for editing rules without touching YAML
- [ ] Desktop notification on each move

---

## 📄 License

MIT © Shuaib S. Agaka

---

> Part of my [30-Day GitHub Build Roadmap](https://github.com/ShuaibSAgaka) — building and shipping one project every day.
