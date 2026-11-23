# FrameScout – Feature ideas

Raw feature ideas from the weekly brainstorming run. They are **not** planned work:
an idea becomes work only when the user moves it into `docs/BACKLOG.md` (group F, with an ID)
and `docs/ROADMAP.md`, which `/triage` does together with the user. Each run appends a dated
section; earlier sections are edited only by `/triage`, which adds one line under an
idea's heading: `Disposition: take over → F<n> | discarded: <reason> | parked: <reason>
(<date>)`. An idea without that line has not been triaged yet. A taken-over or discarded
idea is cut to its heading and that line (its text lives in the backlog item; git history
keeps the original); a parked idea keeps its full text.
"Hold point" refers to the hold points in `CLAUDE.md` → "PR workflow".

## 2026-10-27

Checked against `ROADMAP.md`, `BACKLOG.md` and `docs/BACKLOG-DONE.md` (keywords:
negative, duplicate, burst, EXIF, date, re-rank, CSV, integrity, disk space, priority,
exclude, threshold). Closest existing items are named where they touch an idea.

### 1. "Not this" search texts per profile
Disposition: take over → F6; tag decision (2026-11-02)

### 2. Group near-duplicate and burst shots in the results
Disposition: take over → F7; tag decision (2026-11-02)

### 3. Skip loading the person detector when nothing needs analysis
Disposition: take over → F2; roadmap P12 (A) (2026-11-02)

### 4. Exclude subfolders and filter by date
Disposition: take over → F8; tag decision (2026-11-02)

### 5. Export a result list (CSV / file list)
Disposition: take over → F5; roadmap P13 (2026-11-02)

### 6. Backup of `marks.json` and a cache health check
Disposition: take over → F1; roadmap P11 (2026-11-02)

### 7. "Run in the background" (lower priority) option
Disposition: take over → F4; roadmap P12 (C) (2026-11-02)

### 8. Free disk space check before installing and searching
Disposition: take over → F3; roadmap P12 (B) (2026-11-02)

## 2026-11-02

Checked against `ROADMAP.md`, `BACKLOG.md`, `docs/BACKLOG-DONE.md` and the 2026-10-27
ideas (keywords: ad-hoc, quick search, similar, estimate, remaining time, history,
previous run, import, export, share, self-test, repair, verify, undo, manifest). Closest
existing items are named where they touch an idea.

### 1. Quick search over the analyzed photos, without a profile
Disposition: take over → F10; tag decision (2026-11-03)

### 2. "Find similar" from a result card
Disposition: take over → F11; tag decision (2026-11-03)

### 3. Remaining-time estimate and a pre-start summary
Disposition: take over → F12; roadmap P15 (A) (2026-11-03)

### 4. Keep the previous search results
Disposition: take over → F13; tag decision (2026-11-03)

### 5. Export and import a search profile as one file
Disposition: take over → F14; tag decision (2026-11-03)

### 6. "Check installation" self-test
Disposition: take over → F15; roadmap P15 (B) (2026-11-03)

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
Disposition: take over → F17; roadmap P25 (B) (2026-11-12)

### 2. Analyze photos ahead of time, without a search
Disposition: take over → F18; roadmap P26 (2026-11-12)

### 3. One-photo review mode with a large preview
Disposition: take over → F19; tag decision, after F24 (2026-11-12)

### 4. Review progress per profile and "jump to the first unmarked photo"
Disposition: take over → F20; roadmap P25 (A) (2026-11-12)

### 5. Warn about cloud-only photos before a search
Disposition: discarded: was F21, closed in the triage; default open, needs real OneDrive (2026-11-16)

### 6. Start: handle a busy port and an already running app
Disposition: take over → F22; roadmap P27 (2026-11-12)

### 7. Optional desktop and Start menu shortcut, removed by the uninstaller
Disposition: discarded: was F23, closed in the triage; first file outside the project folder (2026-11-16)

## 2026-11-12

Single idea added by hand (no brainstorming run); not checked against the earlier ideas.

### 1. UI/UX overall review
Disposition: take over → F24; roadmap P28 (2026-11-12)

## 2026-11-14

Single idea added by hand (no brainstorming run); not checked against the earlier ideas.

### 1. Linux support
Disposition: take over → F47 (and F48); roadmap P47 (2026-11-16)

## 2026-11-16

Checked against `docs/ROADMAP.md`, `docs/BACKLOG.md`, `docs/BACKLOG-DONE.md` and the earlier
ideas (keywords: selected profiles, include, upload, example image, history, recent, moved,
relink, rename, orientation, resolution, screenshot, histogram, distribution, archive, backup,
move to another PC).

### 1. Choose which profiles a search runs
Disposition: take over → F49; tag decision (2026-11-16)

### 2. Quick search with an example image
Disposition: take over → F50; tag ready, not on the roadmap (2026-11-16)

### 3. Recent quick search texts
Disposition: take over → F51; tag ready, not on the roadmap (2026-11-16)

### 4. Reuse analyses after the photo library moved
Disposition: take over → F52; tag decision (2026-11-16)

### 5. Filter results by photo size and orientation
Disposition: parked: new cache columns and reflowing pages for a rare need (I47) (2026-11-16)
- **Problem:** large folders contain thumbnails, icons, screenshots and low-resolution web
  images that can rank high but are useless, and users looking for a cover or a print often
  want only portrait or only landscape photos. The results cannot be filtered by either.
- **Solution sketch:** store the decoded width and height (after EXIF orientation) in the
  cache row when a photo is analyzed (new nullable columns; old rows have none and pass every
  filter until they are analyzed again). The results toolbar gets "Orientation: any /
  portrait / landscape / square" and "Smallest edge at least: any / 800 / 1600 / 3000 px";
  filtering happens at display time, like "Hide photos marked as no match".
- **Affected:** `framescout_engine.py` (store dimensions), `results.json` (dimensions per
  result) or a cache lookup in the app, `framescout_ui/results.py`, user guide "Results",
  `docs/ARCHITECTURE.md` (cache, result file).
- **Effort:** M.
- **Risks:** filtered pages reflow like the A24 case; draft decoding (E2) gives the reduced
  size, so the original size must be read from the header, not the decoded image; HTML
  gallery parity (F33).
- **Hold point:** cache/result format change (added columns and fields, no invalidation).

### 6. Score distribution per profile
Disposition: take over → F53; tag decision (2026-11-16)

### 7. Archive all user data for a move or before uninstalling
Disposition: parked: overlaps I19 and F14, decide those first (2026-11-16)
- **Problem:** the uninstaller keeps user data (I19) but leaves it in the FrameScout folder.
  To move to a new PC or a fresh install, a user has to know which files matter
  (`profiles.json`, `references/`, `settings.json`, `results/marks.json`, `results/exports/`)
  and copy them by hand; F14 covers a single profile only.
- **Solution sketch:** "Save my data" in the cleanup/maintenance area writes one ZIP (standard
  library `zipfile`) with these files and a small manifest (format version, FrameScout
  version) to a folder the user chooses, never inside a photo folder and never replacing a
  file. "Restore" reads such a ZIP into an empty install only (refuses when `profiles.json`
  already has profiles), validates profiles like `load_profiles` and rejects path traversal.
  The cache and thumbnails are left out (they can be rebuilt; mention it). The uninstaller's
  final message points to "Save my data".
- **Affected:** new `framescout_core` module (tested with `tmp_path`), `framescout_ui/cleanup.py`
  or a small maintenance section, `framescout_uninstall.py` (message), user guide,
  `docs/ARCHITECTURE.md`.
- **Effort:** M.
- **Risks:** marks follow absolute photo paths (A21), so they only fit if the photos have the
  same paths on the new PC (say so); restore must never overwrite user files; overlaps with
  F14 (shared ZIP code) and A30 (backups).
- **Hold point:** product decision (scope of restore); no new dependency.

## 2026-11-17

Not from a brainstorming run: a size review after I44 (application code 13,139 lines, of
which about 7,900 executable, 2,400 docstrings; tests 15,360). I44 removed about 1,050 lines
(code and tests); the remaining size comes less from rare-case handling than from chains
of follow-up fixes, the breadth of features and the verbosity of docstrings.

### 1. Second simplification round: follow-up chains and leftovers (after I44)
Disposition: take over → F57; tag decision, assessed after F56 (2026-11-17)

### 2. Feature and style review: what FrameScout really needs
Disposition: take over → F56; tag decision, roadmap P54 (2026-11-17)

### 3. Remove the project history from the code and keep it out (rule)
Disposition: take over → F54; roadmap P53 (2026-11-17)

### 4. Test scope: only what is necessary (rule)
Disposition: take over → F55; roadmap P53 (2026-11-17)

## 2026-11-23

Checked against `docs/ROADMAP.md`, `docs/BACKLOG.md`, `docs/BACKLOG-DONE.md` and the earlier
ideas (keywords: diagnostic, bug report, redact, template, generated, duplicate profile, copy
profile, small files, file size, AND, must also, new since, newly analyzed, timing, elapsed,
long path, MAX_PATH). The project is in a simplification phase (F56/F57), so the ideas are kept
small; closest existing items are named where they touch an idea.

### 1. Copy a diagnostic summary for a bug report, with personal paths removed
- **Problem:** to report a problem, a user has to collect the FrameScout version, Python and
  torch versions, device, model and the end of `run.log` by hand. `run.log` holds absolute photo
  paths and the user name; pasted into a public issue it leaks personal data.
- **Solution sketch:** "Copy diagnostic summary" next to "Check installation" (F15) builds a
  short text: version file, Python/torch/torchvision versions, CUDA yes/no and GPU name, model,
  person detection on/off, photo count, and the last ~50 lines of `run.log`. Before it is shown,
  the home folder, the photo folders and the project folder are replaced by `%USERPROFILE%`,
  `<photos-1>`, `<project>`. The text is shown in a code box for the user to copy; nothing is
  sent anywhere.
- **Affected:** a small function in `framescout_core/install_check.py` (redaction tested with
  `tmp_path`-style strings), `framescout_ui/settings.py` or the check area, user guide
  "Checking the installation".
- **Effort:** S.
- **Risks:** redaction cannot catch every personal string (e.g. a profile name or a file name
  that contains a person's name); the UI must say "check the text before posting it".
- **Hold point:** none.

### 2. Show the generated search texts of a profile
- **Problem:** name and context are turned into four generic English templates, features into two
  more (`docs/ARCHITECTURE.md` → "Models and prompts"), but the user never sees them. An odd
  ranking (e.g. "Jaguar" with context "car" still ranking animals) is hard to understand, and
  users do not know whether a custom prompt adds anything the templates do not already say.
- **Solution sketch:** a collapsed "Search texts used" area in the profile form lists the
  generated templates and the custom prompts exactly as the engine encodes them, using the same
  function the engine uses (moved to `framescout_core.profiles` if it is not there already). It
  updates while the user types; read-only, no new setting.
- **Affected:** `framescout_core/profiles.py`, `framescout_engine.py` (call the shared function),
  `framescout_ui/profiles.py`, user guide "Search profiles".
- **Effort:** S.
- **Risks:** the engine and the preview must never drift apart (one function, a test that the
  engine's prompt list equals the preview's); keep the area collapsed so the profile tab does not
  get longer (A50).
- **Hold point:** none (no change to the texts themselves).

### 3. Duplicate a profile
- **Problem:** trying a variant of a profile (another context, one more custom prompt, without
  the reference images) means creating a new profile and retyping everything; editing the
  original instead loses the comparison and moves its marks' meaning.
- **Solution sketch:** "Duplicate" in the profile list creates "<name> (copy)" (next free
  suffix) with the same fields; reference images are copied under new unique names like an
  upload (A1), never shared, so deleting one profile's images cannot touch the other's. Marks are
  not copied (they belong to the original profile).
- **Affected:** `framescout_ui/profiles.py`, `framescout_core/profiles.py` and
  `framescout_core/references.py` (copy with a unique name, tested with `tmp_path`), user guide
  "Search profiles".
- **Effort:** S.
- **Risks:** the write must go through the same lock and backup path as every profile save
  (A13, A30); a failed reference copy must not leave a half-created profile.
- **Hold point:** none.

### 4. Skip very small image files when scanning
- **Problem:** large folders contain icons, web thumbnails and app caches (a few KB each) that
  cost analysis time and can rank high, but are never what the user looks for. The parked idea
  "Filter results by photo size and orientation" (2026-11-16, 5) was parked because it needs new
  cache columns.
- **Solution sketch:** a setting "Skip image files smaller than: off / 20 KB / 100 KB" (default
  off). The scan compares the file size it already reads with `stat()` and leaves those files
  out, with one log line ("N small files skipped") and a count in the photo source tab. No
  decoding, no cache change, no result format change.
- **Affected:** `framescout_engine.py` / `framescout_core/photos.py` (scan filter), engine CLI
  option, `framescout_core/settings.py`, `framescout_ui/settings.py`, user guide "Photo source".
- **Effort:** S–M.
- **Risks:** file size is a crude stand-in for resolution (a small, heavily compressed photo is
  skipped; a large PNG icon is not); a skipped photo's existing marks stay but it no longer appears.
- **Hold point:** CLI option added (not breaking); arguably a search-result change, so the
  default stays off.

### 5. A "must also match" text per profile
- **Problem:** custom prompts are combined with OR (the best of the queries counts), so
  "dog on a beach" cannot be written as "dog" and "beach" both required; one strong part is
  enough to rank a photo high (a beach without a dog). F6 covers what a motif is *not*; nothing
  covers what it must *also* be.
- **Solution sketch:** an optional "Must also match" text per profile. In `framescout_scoring` a
  crop's text score becomes the minimum of its z-scored main text score and its z-scored score
  for that text, so both must be high; the engine encodes it like a custom prompt, no cache
  change. The "which text matched" line (F17) names the weaker of the two.
- **Affected:** `framescout_scoring/__init__.py`, `framescout_engine.py`, profile validation and
  `search_fingerprint` in `framescout_core/profiles.py`, `framescout_ui/profiles.py`,
  `assets/profiles.example.json`, tests, user guide.
- **Effort:** M.
- **Risks:** CLIP's sense of a second concept on a person crop is weak (the best crop may be a
  person crop without the beach), so the minimum may need the full-image score for the second
  text; overlaps F6 in shape (both should share one design).
- **Hold point:** yes – search-quality change (evaluation set first) and a `profiles.json`
  schema addition.

### 6. "Only new photos" in the results
- **Problem:** users who add photos to the same folder after each event re-run the same profile
  and want to look only at the photos that were not there before; today the new ones are mixed
  into the ranking with everything they already reviewed. Marks help only once every old photo
  is marked.
- **Solution sketch:** the engine already knows which photos it analyzed in this run versus took
  from the cache. It writes that as a boolean per result in `results.json`; the results toolbar
  gets "Only new photos" (display-time filter like "Hide no match", ranks unchanged) and the
  progress caption counts them.
- **Affected:** `framescout_engine.py`, `framescout_core/results.py` (one optional field; old
  files read as "not new"), `framescout_ui/results.py`, user guide "Results",
  `docs/ARCHITECTURE.md` (result file).
- **Effort:** M.
- **Risks:** "new" means "analyzed in this run", so a cache cleanup or a model change marks every
  photo new, and a renamed photo counts as new (say so in the hint); filtered pages reflow (A24
  case); HTML gallery parity (F33); overlaps F13 (previous results).
- **Hold point:** result file format change (added field, no invalidation).

### 7. Time per phase at the end of a run
- **Problem:** the measurements open in P10 (B) (E17 thread counts, E18 YOLO batches) and
  any user complaint "the search is slow" need to know where the time goes – decoding, person
  detection, embedding, scoring or gallery export – but the log shows only progress.
- **Solution sketch:** the engine sums the wall time of each phase (decode/preprocess threads,
  detection, forward passes, SQLite commits, scoring, export) with `time.perf_counter` and
  writes one line at the end of `run.log`, e.g. "Time: decode 41 s, detection 63 s, embedding
  22 s, cache 3 s, scoring 1 s, export 9 s (412 photos analyzed)". Not shown in the UI.
- **Affected:** `framescout_engine.py`, `docs/DEVELOPMENT.md` (how to read it).
- **Effort:** S.
- **Risks:** decode and detection run in threads, so phase sums can exceed the wall time; label
  them as summed thread time. No behavior change.
- **Hold point:** none.

### 8. Warn about an install folder with a long path on Windows
- **Problem:** torch and CUDA wheels install files deep below `.venv\Lib\site-packages`; in a
  folder with a long path (e.g. inside a nested Downloads or synced folder) the install can fail
  on Windows with long path support off, with a pip error that does not name the cause.
- **Solution sketch:** `Install-FrameScout.bat` checks the length of the project path before
  creating `.venv`; above a threshold (e.g. 80 characters) it prints that the install may fail
  and suggests a shorter folder such as `C:\FrameScout`, then continues. The `.sh` script needs
  no such check (Linux has no such limit); the `.bat`/`.sh` parity rule (`CLAUDE.md`) gets a
  stated exception for it.
- **Affected:** `Install-FrameScout.bat`, user guide "Installation details".
- **Effort:** S.
- **Risks:** not observed in this project yet (I47): measure the deepest path of the pinned torch
  build first; if no realistic folder reaches 260 characters, document it as a known limit
  instead.
- **Hold point:** none (warning only, no download).
