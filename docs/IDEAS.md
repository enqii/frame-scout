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
