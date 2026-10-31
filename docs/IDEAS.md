# FrameScout – Feature ideas

Raw feature ideas from the weekly brainstorming run. They are **not** planned work:
an idea becomes work only when the user moves it into `BACKLOG.md` (group F, with an ID)
and `ROADMAP.md`, which `/triage` does together with the user. Each run appends a dated
section; earlier sections are never edited, except that `/triage` adds one line under an
idea's heading: `Disposition: take over → F<n> | discarded: <reason> | parked: <reason>
(<date>)`. An idea without that line has not been triaged yet.
"Hold point" refers to the hold points in `CLAUDE.md` → "PR workflow".

## 2026-10-27

Checked against `ROADMAP.md`, `BACKLOG.md` and `docs/BACKLOG-DONE.md` (keywords:
negative, duplicate, burst, EXIF, date, re-rank, CSV, integrity, disk space, priority,
exclude, threshold). Closest existing items are named where they touch an idea.

### 1. "Not this" search texts per profile
- **Problem:** a profile "red car" also ranks toy cars, posters of cars or red buses
  high, and the user can only add more positive texts. A20 covers rejected *marks* as
  negative examples, but there is no way to say up front what a motif is *not*.
- **Solution sketch:** an optional "Exclude texts" field per profile (e.g. "a toy car",
  "a drawing"). In `framescout_scoring`, a crop's score is lowered by a weighted,
  z-scored similarity to the best exclude text (e.g. `z_text - λ·max(0, z_exclude)`),
  so only crops that clearly match an exclusion lose rank. The engine encodes the exclude
  texts like custom prompts; no cache change (scoring runs on cached features).
- **Affected:** `app.py` (profile form), `framescout_core` profile validation and
  `search_fingerprint`, `framescout_scoring.py`, `framescout_engine.py`, `profiles.example.json`,
  tests, user guide "What the numbers mean".
- **Effort:** M.
- **Risks:** CLIP handles negation poorly in a single text, so the exclusion must be a
  separate query, not "a car, not a toy"; a too-strong λ can bury real matches.
- **Hold point:** yes – `profiles.json` schema change (additive optional field) and a
  search-quality change (needs the local evaluation set; λ is tuned there).

### 2. Group near-duplicate and burst shots in the results
- **Problem:** event and burst photography produces 5–20 nearly identical frames; they
  fill whole result pages with the same moment, so the user scrolls past duplicates
  and finds fewer *different* matches per page.
- **Solution sketch:** after ranking, group result photos whose cached full-image
  embeddings have a cosine similarity above a threshold (e.g. ≥ 0.95) and that sit in
  the same folder, using the best-ranked photo as the group's card ("+6 similar",
  expandable). numpy only, on vectors already in the cache; an app toggle "Group similar
  photos" (default off at first). Marking a group card could offer "apply to all in group".
- **Affected:** `framescout_scoring.py` (grouping), `framescout_engine.py` /
  `framescout_core.write_results` (optional `group` per card in `results.json`), `app.py`
  gallery, HTML gallery, tests with synthetic vectors.
- **Effort:** M.
- **Risks:** threshold depends on the search model (SigLIP vs. CLIP); two different
  persons in the same pose and setting could be merged – the group must stay expandable
  and never hide a photo silently.
- **Hold point:** UX/product decision (gallery behavior, default on/off); `results.json`
  gets an additive field (check the format-version rule of A25). No new dependency.

### 3. Skip loading the person detector when nothing needs analysis
- **Problem:** a repeat search on an already analyzed folder (e.g. after editing only a
  profile text or the reference weight) still loads the YOLO model
  (`framescout_engine.py`, `detector = YOLO(...)` before the cache is consulted), which
  costs seconds to tens of seconds on a CPU and on first use even a download, although
  only text encoding and scoring are needed.
- **Solution sketch:** check the cache first (paths + `mtime_ns` + size against the
  signature), and create the detector lazily on the first uncached photo. The status
  file could report "Nothing new to analyze – ranking only". Same idea for the image
  half of CLIP is not possible (text encoder shares the model), so only YOLO is deferred.
- **Affected:** `framescout_engine.py`, possibly `framescout_core` (a helper that lists
  uncached photos, testable without torch), user guide "Search & results".
- **Effort:** S.
- **Risks:** the detector must still be created under the existing lock and environment
  (E27/E28 offline flags); a detector load error now appears mid-run instead of at start.
- **Hold point:** no (no schema, cache or quality change).

### 4. Exclude subfolders and filter by date
- **Problem:** large photo trees contain folders the user never wants searched
  (`_exports`, `edited`, `.thumbnails`, `Screenshots`), and users often know roughly
  *when* a motif was shot ("summer 2024") but today must search everything.
- **Solution sketch:** in the "Photo source" tab, an optional list of folder-name
  patterns to skip (glob, matched per path component) and an optional date range. The
  date is the EXIF `DateTimeOriginal` when Pillow can read it cheaply, else the file's
  modification time; filtering happens at scan time, so the cache is untouched and
  excluded photos simply are not ranked. New engine options `--exclude` and
  `--date-from/--date-to`; the skip counts appear in the log like the RAW skips.
- **Affected:** `framescout_core` (scan/filter, standard library), `framescout_engine.py`
  (CLI), `app.py` (settings widgets via `setting_<name>`), `settings.json` defaults,
  user guide, tests.
- **Effort:** M.
- **Risks:** reading EXIF for every photo slows the scan (cache the date next to the
  features or only read EXIF when a date filter is set); copies inside excluded folders
  interact with the "copy target inside a photo folder" check of A17.
- **Hold point:** CLI options are additive (not breaking) and `settings.json` gets new
  optional keys; a product decision on mtime vs. EXIF fallback is needed.

### 5. Export a result list (CSV / file list)
- **Problem:** the only way to take results elsewhere is copying files (A17) or the HTML
  gallery. Users who catalog photos in another program (Lightroom, digiKam, XnView,
  a spreadsheet) want a list of the matched paths, scores and marks.
- **Solution sketch:** a button "Export list" per profile in the results view writes
  `results/exports/<slug>-<date>.csv` (rank, path, score, crop, mark) and a plain `.txt`
  with one path per line (many viewers can open such a list). Options: all ranked photos,
  or only marked as match. Pure standard library (`csv`), never touches the photos and
  never writes XMP sidecars next to them.
- **Affected:** `framescout_core` (export function, tested), `app.py`, user guide "Results",
  storage cleanup (exports are user data: add them to `NEVER_DELETED` or leave them out of
  every category).
- **Effort:** S.
- **Risks:** CSV encoding on Windows (Excel expects UTF-8 with BOM for non-ASCII paths);
  paths are absolute and machine-specific (same limit as marks, A21).
- **Hold point:** no.

### 6. Backup of `marks.json` and a cache health check
- **Problem:** `results/marks.json` holds hours of manual review but has no backup
  (A30 is about `profiles.json` only); a broken write or a hand edit loses all marks. A
  damaged `cache.sqlite3` (disk full, power loss) currently surfaces only as errors in
  a search.
- **Solution sketch:** (a) `save_marks` keeps the previous file as `marks.json.bak`
  before the atomic replace, and an unreadable `marks.json` offers "Restore marks from
  backup" in the app (never automatic). (b) "Clean up storage" gets a "Check cache"
  action running SQLite `PRAGMA quick_check`; on failure the app explains it and offers
  to rename the file to `cache.sqlite3.broken-<date>` (never delete), so the next search
  rebuilds it.
- **Affected:** `framescout_core` (marks module, cleanup), `app.py`, `NEVER_DELETED`
  (add `marks.json.bak`), user guide "Results" and "Cleaning up storage", tests.
- **Effort:** S–M.
- **Risks:** `quick_check` on a large cache takes a few seconds and must not run while a
  search holds the run lock.
- **Hold point:** no (user-data safety, no schema change; the restore UX is a small
  product decision).

### 7. "Run in the background" (lower priority) option
- **Problem:** a CPU search on thousands of photos makes the PC sluggish for the whole
  run; users who keep working meanwhile would rather wait longer. E17 tunes thread
  counts for speed, not for staying usable.
- **Solution sketch:** an AI setting "Keep the PC responsive" that starts the engine with
  `subprocess.BELOW_NORMAL_PRIORITY_CLASS` on Windows (`os.nice` elsewhere) and, on the
  CPU, one or two fewer PyTorch threads. Standard library only; the CLI gets
  `--low-priority` for manual runs.
- **Affected:** `app.py` (`subprocess.Popen` creation flags, settings widget),
  `framescout_engine.py` (thread count), `settings.json`, user guide "AI settings".
- **Effort:** S.
- **Risks:** the effect on GPU runs is small; must not interact badly with the stop
  logic (process tree, PID in the status file).
- **Hold point:** no; measure the slowdown on the home PC together with E17 (P10 (B)).

### 8. Free disk space check before installing and searching
- **Problem:** the CUDA install downloads about 2.5 GB, optional search models up to
  1.7 GB, and a search writes cache rows and thumbnails. A full disk mid-way leaves a
  broken `.venv`, a half-downloaded model or failed cache commits with confusing errors.
- **Solution sketch:** `shutil.disk_usage` checks with a clear message: the installer
  (`install_torch.py`) before the PyTorch download (needed size per variant), the app
  before a search (estimate from uncached photos × bytes per cache row + top × profiles
  × thumbnail size + model weights not yet in `.cache/`) and before a first model use.
  A warning, not a hard block, with the free and the estimated space.
- **Affected:** `install_torch.py`, `framescout_core` (estimate, tested),
  `app.py`, README "Installation" and "Requirements", user guide "Installation details".
- **Effort:** S.
- **Risks:** estimates are rough; the drive of `results/` and of `.cache/` may differ
  (check both).
- **Hold point:** no.
