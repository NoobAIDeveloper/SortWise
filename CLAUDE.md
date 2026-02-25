# CLAUDE.md - SortWise Project Context

## What this app is

SortWise is a free macOS desktop app that sorts photos and videos into folders by metadata. Built with Electron + React (frontend) and Python (backend). The Python backend is spawned as a subprocess by Electron and communicates via stdout JSON lines.

GitHub repo: https://github.com/NoobAIDeveloper/SortWise
Current version: 1.0.1

---

## Project structure

```
photo_organizer/
├── backend/
│   ├── main.py           # All sorting and undo logic
│   ├── test_main.py      # 35 unit tests (mocked, fast)
│   ├── test_e2e.py       # 27 e2e tests (real files on disk)
│   └── __init__.py       # Makes backend a package (required for test imports)
├── frontend/
│   ├── src/
│   │   ├── App.js        # React UI
│   │   └── App.css       # macOS Settings-style CSS
│   ├── main.js           # Electron main process + IPC handlers
│   ├── preload.js        # contextBridge exposing window.electronAPI
│   └── package.json      # electron-builder config lives here under "build"
├── build_backend.sh      # PyInstaller → frontend/resources/main
├── build_app.sh          # Full build: backend + electron-pack → DMG
├── venv/                 # Python venv (Python 3.13)
└── screenshots/
    └── sortwise-main.png
```

---

## How to run and test

**Run in dev mode:**
```bash
cd frontend && npm run dev
```
Starts React on port 3000 and Electron simultaneously.

**Run tests:**
```bash
source venv/bin/activate && python -m pytest backend/test_main.py backend/test_e2e.py -v
```
62 tests total, all should pass.

**Build distributable DMG:**
```bash
bash build_app.sh
# Output: frontend/dist/SortWise-1.0.0-arm64.dmg
```

---

## Architecture

- Electron detects dev vs prod with `const isDev = !app.isPackaged`
- Dev: spawns `venv/bin/python backend/main.py <JSON>`
- Prod: spawns `process.resourcesPath/main <JSON>` (PyInstaller binary)
- Backend writes progress lines `{"type":"progress","value":0-100}` to stdout
- Backend writes final result as a single JSON line: `{"status":..,"message":..,"logFile":..}`
- Electron's main.js filters lines starting with `{` — progress lines are sent to renderer via `win.webContents.send('sort:progress', ...)`, final JSON is resolved from the promise
- Undo: `python main.py undo <logFilePath>` — reads CSV log and moves files back

---

## IPC flow

```
React UI
  → window.electronAPI.sortFiles(options)   (preload.js contextBridge)
    → ipcMain.handle('sort:files', ...)     (main.js)
      → spawn Python subprocess
        → stdout JSON progress lines → ipcMain sends 'sort:progress' to renderer
        → stdout final JSON → promise resolves
  → window.electronAPI.undoSort(logFile)
    → ipcMain.handle('undo:sort', ...)
      → spawn Python subprocess with 'undo' arg
```

---

## CSV log format

File: `~/sortwise_log.csv`

Columns: `Original Filename, Source Path, Destination Folder, Status, Destination Filename`

Status values: `Moved`, `Copied`, `Skipped (Duplicate)`, `Skipped (Unsupported File Type: .ext)`, `Error: <msg>`

The 5th column (Destination Filename) tracks the actual name after any conflict rename (e.g. `photo_1.jpg`). Undo uses this column to find the file. Old 4-column logs are still supported — undo falls back to original filename.

---

## Bugs fixed (Claude sessions)

1. **`date_sort_option` NameError** — undefined variable on line 116. Fixed: `date_sort_option = options.get('dateSortOption', 'yearMonth')` at top of `sort_files()`.

2. **GIF sorted into Photos** — `gif` extension matched the `['jpg','jpeg','png','gif']` Photos branch before reaching the dedicated GIFs branch. Fixed: moved `elif file_type == 'gif'` before the Photos branch.

3. **Undo broken for renamed files** — CSV only logged original filename, not the renamed destination. Fixed: added 5th CSV column `Destination Filename`; undo uses `row[4]` if present.

4. **Live photos always moved in copy mode** — used `shutil.move` unconditionally. Fixed: check `file_operation` and use `shutil.copy2` for copy mode. Also fixed relative path in log to absolute.

5. **Geocoding crash/hang** — no timeout, no error handling, new instance created per call. Fixed: module-level `geolocator = Nominatim(user_agent="sortwise/1.0", timeout=5)` with `try/except`.

6. **Image.open() failure skipped entire file** — outer try/except caught PIL errors and skipped the whole file. Fixed: targeted inner `try/except` around orientation block only.

7. **Files re-processed during sort** (v1.0.1) — the sort loop used a second lazy `os.walk` generator separate from the one used to count files. Files moved into destination subdirs were picked up again and sorted a second time. Progress could exceed 100%. Fixed: collect all files into `all_files = [(folder, path), ...]` list upfront, iterate that list for sorting too.

---

## UI design

- macOS Settings-style: sidebar (220px) + scrollable content area
- `titleBarStyle: 'hiddenInset'` in main.js — native traffic lights inset into app
- `-webkit-app-region: drag` on `.titlebar`; `no-drag` on all interactive elements
- Custom pill toggle switches (green when on) replacing checkboxes
- Segmented control for radio options (Operation, Conflicts)
- Section labels in ALL CAPS gray, white cards with rounded corners and shadow
- No `alert()` calls — all feedback via inline `.status-message` state
- Folders are additive — new selections merge, no duplicates
- Progress bar only visible while `isSorting === true`
- Window: `width: 820, height: 680, minWidth: 680, minHeight: 680`
- `.card { flex-shrink: 0 }` — prevents card rows being clipped on resize
- `.actions { margin-top: 16px }` — NOT `margin-top: auto` (breaks scroll context)

---

## Packaging notes

- PyInstaller flags: `--onefile --name main` (no `--windowed` — stdout IPC requires it)
- Hidden imports needed: `exifread`, `PIL`, `PIL.Image`, `geopy`, `geopy.geocoders`, `geopy.geocoders.nominatim`
- Binary copied to `frontend/resources/main` then `chmod +x`
- electron-builder `extraResources`: `{ from: "resources/main", to: "main" }`
- `frontend/package.json` must have `"homepage": "./"` for correct asset paths in packaged app
- `frontend/resources/` is in `.gitignore` (binary is too large)

---

## GitHub

- Logged in as `NoobAIDeveloper` via `gh auth login`
- Releases: `gh release create vX.Y.Z "path/to/file#display-name.dmg" --title "..." --notes "..."`
- Latest release: v1.0.1 (bug fix for file re-processing)
- The repo moved to `https://github.com/NoobAIDeveloper/SortWise.git` — git remote still works but shows a redirect warning on push

---

## User preferences

- Commit messages: no "Co-Authored-By" line
- README style: human-written, no em dashes, no AI mannerisms
- Releases: rebuild DMG from scratch before each release upload
