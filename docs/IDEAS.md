# FrameScout – Feature ideas

Raw feature ideas from the weekly brainstorming run. They are **not** planned work:
an idea becomes work only when the user moves it into `docs/BACKLOG.md` (group F, with an ID)
and `docs/ROADMAP.md`, which `/triage` does together with the user. Each run appends a dated
section; earlier sections are never edited, except that `/triage` adds one line under an
idea's heading: `Disposition: take over → F<n> | discarded: <reason> | parked: <reason>
(<date>)`. An idea without that line has not been triaged yet.
"Hold point" refers to the hold points in `CLAUDE.md` → "PR workflow".

## 2026-10-27

Checked against `ROADMAP.md`, `BACKLOG.md` and `docs/BACKLOG-DONE.md` (keywords:
negative, duplicate, burst, EXIF, date, re-rank, CSV, integrity, disk space, priority,
exclude, threshold). Closest existing items are named where they touch an idea.

### 1. "Not this" search texts per profile
Disposition: take over → F6; tag decision (2026-11-02)
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
Disposition: take over → F7; tag decision (2026-11-02)
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
Disposition: take over → F2; roadmap P12 (A) (2026-11-02)
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
Disposition: take over → F8; tag decision (2026-11-02)
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
Disposition: take over → F5; roadmap P13 (2026-11-02)
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
Disposition: take over → F1; roadmap P11 (2026-11-02)
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
Disposition: take over → F4; roadmap P12 (C) (2026-11-02)
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
Disposition: take over → F3; roadmap P12 (B) (2026-11-02)
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

## 2026-11-02

Checked against `ROADMAP.md`, `BACKLOG.md`, `docs/BACKLOG-DONE.md` and the 2026-10-27
ideas (keywords: ad-hoc, quick search, similar, estimate, remaining time, history,
previous run, import, export, share, self-test, repair, verify, undo, manifest). Closest
existing items are named where they touch an idea.

### 1. Quick search over the analyzed photos, without a profile
Disposition: take over → F10; tag decision (2026-11-03)
- **Problem:** trying out a search text ("person with umbrella", "sunset over water")
  means creating a profile, saving it and starting a full run, which also analyzes every
  photo not in the cache yet. Exploring a folder that is already analyzed feels slow.
- **Solution sketch:** a "Quick search" text field in "Search & results". It starts the
  engine with a new option (e.g. `--quick-query "<text>"`) that skips the analysis phase,
  scores only photos that already have cache rows of the current signature, and writes
  its gallery and result to a separate `results/quick/` folder, so the profile results
  and `marks.json` stay as they are. The app says how many photos of the folders are not
  analyzed yet and therefore not searched.
- **Affected:** `framescout_engine.py` (option, analysis skip, export target),
  `framescout_core` (result path helpers, cleanup must know `results/quick/`), `app.py`,
  user guide "Search & results", `docs/ARCHITECTURE.md` (pipeline, outputs, cleanup).
- **Effort:** M.
- **Risks:** z-scoring over only the analyzed photos makes scores differ from a full run;
  must be labelled clearly. The text model still loads (a few seconds on CPU). Storage
  cleanup and the thumbnail cleanup must treat the second results folder correctly.
- **Hold point:** CLI option is additive (not breaking); `results/` layout gains a folder
  (UX/product decision).

### 2. "Find similar" from a result card
Disposition: take over → F11; tag decision (2026-11-03)
- **Problem:** a result shows exactly the kind of photo the user wants, but there is no
  way to ask for "more like this one" short of copying the photo into a profile's
  reference images and running the whole search again.
- **Solution sketch:** a "Find similar" button on each card in the app's gallery. The
  engine ranks all cached photos by cosine similarity to that photo's cached embedding
  (full image, or the crop the card shows) – no text, no new analysis, no change to any
  profile – and writes the result like idea 1. Closest existing item: A20 (marks feed back
  into the search), which changes profile scoring; this is a separate one-off query.
- **Affected:** `framescout_engine.py` (option such as `--like <path>`),
  `framescout_scoring.py` (rank by one vector, tested with numpy only), `app.py` (card
  button), user guide, `docs/ARCHITECTURE.md`.
- **Effort:** M (S if idea 1 exists, which provides the separate result target).
- **Risks:** a photo whose cache row belongs to another signature (model or detection
  setting changed) has no usable vector: the button must say so instead of analyzing
  silently. Near-duplicates (burst shots) will dominate the top (see the 2026-10-27 idea
  on grouping).
- **Hold point:** CLI option is additive; gallery UX is a product decision.

### 3. Remaining-time estimate and a pre-start summary
Disposition: take over → F12; roadmap P15 (A) (2026-11-03)
- **Problem:** a first CPU search on thousands of photos can take hours, and the app
  only shows a progress bar. Users cannot tell whether to wait, leave the PC on overnight
  or reduce the folder.
- **Solution sketch:** (a) the app derives a remaining-time estimate from the status
  file's progress and its timestamps (moving average over the last minutes; shown as
  "about 25 min left" only after enough samples). (b) Before "Start search", a short
  summary: photos found, photos already analyzed for the current model and detection
  setting (read-only SQLite query against `feature_signature`), photos to analyze, and –
  if an earlier run on this PC recorded a throughput in `run-status.json` – a rough
  duration.
- **Affected:** `framescout_core` (estimate and count helpers, tested), `app.py`
  (`show_status`, run tab), engine status writes (throughput at the end of the analysis
  phase), user guide "Search & results".
- **Effort:** S–M.
- **Risks:** the cached-photo count needs `stat` per photo (mtime/size check) and must not
  rescan on every rerun (A6/A27 cached the folder scan; reuse that). Estimates on a busy
  PC jump around; round generously and never show seconds.
- **Hold point:** no (no schema, cache or quality change; the status file gains an
  optional field).

### 4. Keep the previous search results
Disposition: take over → F13; tag decision (2026-11-03)
- **Problem:** every search replaces `results.json` and the galleries. A user who changes a
  profile or the search model and gets worse results cannot go back to the earlier
  ranking to compare or to copy matches from it.
- **Solution sketch:** before `publish_export` replaces them, move the previous
  `results.json` and galleries into `results/history/<run end timestamp>/` and keep the
  last N runs (N small, e.g. 3; a setting). The results view gets a "Run" selectbox
  (latest by default, older runs read-only). The thumbnail cleanup keeps thumbnails that a
  kept run links; "Clean up storage" lists old runs as a category.
- **Affected:** `framescout_core` (export/publish, cleanup, `read_results` for history
  folders, tested), `framescout_engine.py`, `app.py` (results view), user guide "Results"
  and "Cleaning up storage", `docs/ARCHITECTURE.md` (result file, outputs, cleanup).
- **Effort:** M.
- **Risks:** more disk use (galleries are small, thumbnails are shared). The move must be
  as safe as the E24 publish (a stop half way must not lose the current results). Marks
  are per photo and profile, not per run, so an old run shows today's marks.
- **Hold point:** UX/product decision (number of runs kept, default on/off); `results/`
  layout gains a folder.

### 5. Export and import a search profile as one file
Disposition: take over → F14; tag decision (2026-11-03)
- **Problem:** a good profile (search texts plus reference images) cannot be moved to
  another PC or a second FrameScout folder, or shared with someone else, except by copying
  parts of `profiles.json` and the `references/` folder by hand.
- **Solution sketch:** "Export profile" in the profile tab writes a ZIP with a small JSON
  (the profile's fields, format version) and its reference images. "Import profile" reads
  such a ZIP: validates it like `load_profiles`, gives the name a free suffix if it is
  taken, stores the references through `reference_folder` (never overwriting, A1) and
  saves `profiles.json` through the existing locked save (A13). Purely local files.
- **Affected:** `framescout_core` (bundle read/write and validation, standard library
  `zipfile`, tested incl. path traversal in member names), `app.py` (profile tab), user
  guide "Search profiles".
- **Effort:** M.
- **Risks:** an imported ZIP is untrusted input: reject absolute or `..` member names, cap
  sizes and the number of files, accept only `EXT` suffixes for references. Reference
  images may show people: the user guide should say the file contains them.
- **Hold point:** no `profiles.json` schema change; the bundle format is new (a small
  product decision on its contents).

### 6. "Check installation" self-test
Disposition: take over → F15; roadmap P15 (B) (2026-11-03)
- **Problem:** when the app or a search fails after a Windows update, a moved folder or
  an interrupted install, users see a Python traceback in `run.log` and do not know
  whether to re-run the installer, free disk space or reinstall the GPU build.
- **Solution sketch:** a `Check-FrameScout.bat` (and an expander in "AI settings") that
  runs a read-only check: `.python` and `.venv` belong to this folder (the folder was not
  moved), installed package versions equal `constraints.txt` (`importlib.metadata`), torch
  imports and reports CUDA availability for a CUDA install, `.cache/` and `results/` are
  writable, which model weights are cached, and free disk space. Each problem gets one
  plain sentence with the fix ("run Install-FrameScout.bat again").
- **Affected:** new small script or `framescout_core` module (standard library, tested
  with fake metadata), a `.bat`, `app.py`, user guide (troubleshooting), `docs/DEVELOPMENT.md`.
- **Effort:** S–M.
- **Risks:** must never write, download or "repair" anything by itself; importing torch
  takes seconds and can crash on a broken install, so run it in a subprocess.
- **Hold point:** no (no new dependency, no download).

### 7. A copy log and "Undo last copy" for copied matches
Disposition: parked: the app would delete files outside `results/` for the first time, a basic decision first (2026-11-03)
- **Problem:** "Copy marked matches" (A17) copies photos into a target folder that may
  already hold the user's own files. Copying into the wrong folder, or with the wrong
  marks, leaves a mix that is hard to clean up by hand.
- **Solution sketch:** `copy_photos` records every file it actually created (not the
  "already there" ones) with size and hash in `results/copies.json` (one entry per copy
  action, last few kept). "Undo last copy" deletes only files listed there that still have
  the recorded size and hash, never anything else, and reports files it left because they
  changed. Add `copies.json` to `NEVER_DELETED`.
- **Affected:** `framescout_core` (copying module, tested with `tmp_path`), `app.py`
  (results view), user guide "Marking and copying matches", `docs/ARCHITECTURE.md`
  (marks and copying, storage cleanup).
- **Effort:** S–M.
- **Risks:** deleting files is the riskiest action the app could take; the hash check and
  a confirmation dialog are mandatory, and copies into a folder that is also a photo
  source must be handled (the undo removes only the copies, never originals).
- **Hold point:** UX decision (whether the app should ever delete files outside
  `results/`; it does not today).

## 2026-11-09

Checked against `ROADMAP.md`, `BACKLOG.md`, `docs/BACKLOG-DONE.md` and the earlier ideas
(keywords: breakdown, per text, analyze only, prepare, review, keyboard, full size,
unreviewed, OneDrive, cloud, placeholder, offline, port, 8501, instance, shortcut,
desktop, Start menu). Closest existing items are named where they touch an idea.

### 1. Show which search text matched a result
- **Problem:** a profile with the generated templates and several custom search texts
  ranks a photo high, but the card only shows the raw text and image similarity. Users
  cannot tell which of their texts did the work, so they keep texts that never help or
  delete the one that finds most matches.
- **Solution sketch:** `framescout_scoring` already computes the best cosine per query;
  also return the index of the winning query (template ensemble or custom text n). The
  card caption names it ("best text: 'a red sports car'"), and the results view gets a
  small per-profile summary: how many of the top N photos each text won. No scoring or
  ranking change, the value is only reported.
- **Affected:** `framescout_scoring` (return the winning query, numpy-only tests),
  `framescout_engine.py` (card field), `framescout_core` result writing/reading
  (`results.json` card gains an optional `best_query`), `app.py` results view, HTML
  gallery caption, user guide "What the numbers mean", `docs/ARCHITECTURE.md` (scoring,
  result file).
- **Effort:** S–M.
- **Risks:** the winning text is a heuristic like the score; with z-scoring a text can
  win by a tiny margin, so the wording must not suggest the other texts "failed".
  Results without the field (older runs) show nothing.
- **Hold point:** no search-quality change; `results.json` gets an additive optional field
  (check the format-version rule of A25).

### 2. Analyze photos ahead of time, without a search
- **Problem:** the slow part of a first search is the analysis (hours on a CPU for a big
  folder), and it only starts once the profiles are ready. Users would like to let the
  PC prepare a new folder overnight and write their profiles later; F10 (quick search)
  also only searches photos that are already analyzed.
- **Solution sketch:** an "Analyze photos now" button in the "Photo source" tab and an
  engine option `--analyze-only` that runs the scan and the analysis phase with the
  current model and detection setting, fills `cache.sqlite3` and stops before scoring
  and export, so `results.json`, the galleries and the marks stay as they are. It uses
  the normal run lock, status file, stop button and "Keep the PC responsive" (F4); the
  pre-start summary (F12) then shows "already analyzed".
- **Affected:** `framescout_engine.py` (option, early exit, no profiles needed),
  `framescout_core` (status message, argument building), `app.py` (button, status
  text), user guide "Photo source" and "Search & results", `docs/DEVELOPMENT.md` (CLI),
  `docs/ARCHITECTURE.md` (pipeline, run state).
- **Effort:** S–M.
- **Risks:** a run that writes no `results.json` must not look like a failed search in the
  results view; the analysis is only useful for the model and detection setting chosen
  at that time (a later model change analyzes again), which the app should say.
- **Hold point:** CLI option is additive (not breaking); no schema or cache change.

### 3. One-photo review mode with a large preview
- **Problem:** marking matches (A17) happens on small gallery thumbnails. For subtle
  motifs or group photos the user opens each original with "Open" to decide, which is
  slow for a few hundred results.
- **Solution sketch:** a "Review" toggle in the results view shows one result at a time:
  a large preview (the original, decoded downscaled in memory with the existing image
  helpers, nothing written), the crop that scored best outlined if it is a person crop,
  the score lines and three buttons "Match", "No match", "Skip". Marking saves through
  `save_marks` and moves on to the next open photo of the profile. Optional later:
  keyboard keys, only if they work without a new dependency.
- **Affected:** `app.py` (review view, per-session position), `framescout_images.py`
  (preview decode, outline), `framescout_core` (next open photo helper, tested), user
  guide "Marking and copying matches".
- **Effort:** M.
- **Risks:** decoding a large RAW/HEIC original on every rerun is slow (cache the preview
  per path and mtime in the session, cap its size); the crop box must come from data the
  result already has, or this part is dropped.
- **Hold point:** UX/product decision (where the mode lives, keyboard support); a
  keyboard component would be a new dependency.

### 4. Review progress per profile and "jump to the first unmarked photo"
- **Problem:** after marking part of a long result list, users lose their place: the
  gallery always opens on page 1 and does not say how much of the list has been reviewed.
- **Solution sketch:** a caption per profile in the results view: "Top 150: 32 match,
  41 no match, 77 open; first open photo at rank 74", and a button that opens the page
  holding that rank. Read-only over `results.json` and `marks.json`; no new file.
- **Affected:** `framescout_core` (count and first-open helper, tested), `app.py`
  (caption, page jump through the existing page state), user guide "Results".
- **Effort:** S.
- **Risks:** "Hide photos marked as no match" (A24) changes which page holds a rank; the
  jump must use the same page computation as the gallery.
- **Hold point:** no.

### 5. Warn about cloud-only photos before a search
- **Problem:** a photo folder inside OneDrive (or another sync client with files on
  demand) can hold thousands of online-only placeholders. Reading them for the analysis
  makes Windows download every file: the search is slow, uses the internet connection,
  and can fill the disk – surprising for a tool that promises to work locally.
- **Solution sketch:** during the scan, `os.stat(...).st_file_attributes` (standard
  library on Windows; `stat` itself does not download) flags files with
  `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` or `FILE_ATTRIBUTE_OFFLINE`. The photo source
  tab and the pre-start summary show "N photos are only in the cloud (about X GB would be
  downloaded)" and offer "Skip cloud-only photos" (setting, engine option
  `--skip-cloud-only`); skipped photos are counted in the log like the RAW skips. Already
  cached photos need no download and are still ranked.
- **Affected:** `framescout_core` (scan attribute check, tested with fake stat results),
  `framescout_engine.py` (option, skip count), `app.py` (setting via `setting_<name>`,
  summary), `settings.json` defaults, user guide "Photo source", `docs/ARCHITECTURE.md`
  (several photo folders, photo formats).
- **Effort:** S–M.
- **Risks:** attributes differ between sync clients and Windows versions (needs a check
  on a real OneDrive folder, not runtime-testable in CI); thumbnails and "Open" of a
  skipped photo would still download it; non-Windows systems report nothing.
- **Hold point:** new optional setting and additive CLI option; the default (warn only
  or skip) is a product decision; real-world behavior needs the user's hardware.

### 6. Start: handle a busy port and an already running app
- **Problem:** `Start-FrameScout.bat` always uses port 8501. If another program uses it,
  or FrameScout already runs in a forgotten window, Streamlit stops with "Port 8501 is
  already in use" and users do not know what to do; a second instance of the same folder
  would also share `results/` with the first.
- **Solution sketch:** before starting Streamlit, a small standard-library check: if the
  port answers and it is this folder's FrameScout (e.g. a `results/app-instance.json`
  with PID and port written at app start, checked for a live process), just open the
  browser on it; if another program holds the port, pick the next free one of
  8502–8510 and open that; otherwise start as today. The app removes its instance file
  on a clean exit; a stale file (dead PID) is ignored.
- **Affected:** `Start-FrameScout.bat`, a small helper (new script or `framescout_core`
  function, tested with `tmp_path` and a local socket), `app.py` (instance file),
  `framescout_core.NEVER_DELETED`/cleanup patterns, user guide "Starting", `docs/ARCHITECTURE.md`.
- **Effort:** S–M.
- **Risks:** PID reuse on Windows can make a stale file look alive (also compare the
  process start time or the port); the browser must only ever open `127.0.0.1`, never a
  wider bind address.
- **Hold point:** no (no new dependency, no schema change).

### 7. Optional desktop and Start menu shortcut, removed by the uninstaller
- **Problem:** users start FrameScout by finding the project folder and double-clicking
  a `.bat` file, which is easy to lose and looks unlike a normal Windows application.
- **Solution sketch:** at the end of `Install-FrameScout.bat`, ask "Create a desktop
  shortcut? (y/N)" and, if yes, create a `.lnk` to `Start-FrameScout.bat` (working
  folder = the project folder, a FrameScout icon from `assets/`) with PowerShell's
  `WScript.Shell` COM object – no new dependency. The installer records the shortcut's
  path in a small file in the project folder; `framescout_uninstall.py` removes exactly
  that shortcut (only if it still points to this folder) and nothing else. A moved
  folder makes the check (F15) report a broken shortcut.
- **Affected:** `Install-FrameScout.bat`, `framescout_uninstall.py`, `framescout_check.py`,
  `assets/` (icon), README "Installation"/"Uninstalling", user guide, `docs/ARCHITECTURE.md`.
- **Effort:** S.
- **Risks:** it is the first file FrameScout writes outside its own folder, so the
  "clean uninstall" promise depends on the recorded path; OneDrive-redirected desktops
  and non-English Windows need `[Environment]::GetFolderPath('Desktop')`, not a fixed path.
- **Hold point:** product decision (writing outside the project folder, default answer);
  not runtime-testable in CI.
