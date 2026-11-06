# FrameScout – Finished roadmap packages

Packages of [ROADMAP.md](../ROADMAP.md) in which every line is done, with their check-off
lines (date, pull request, open follow-up IDs). A package moves here unchanged when its
last line is checked off, at the next `/triage` run (rule: `CLAUDE.md` → "Triage"). The
items' reports are in [BACKLOG-DONE.md](BACKLOG-DONE.md).

### P0 – Foundation and correctness
- [x] Git repository + private GitHub repo (I1)
- [x] (0) PR workflow (`/roadmap` skill, briefs, permission settings, PR template, labels)
      + English docs incl. `CLAUDE.md` update (I6)
- [x] (1) `pytest` scaffold + shared module `framescout_core.py` (slug, `EXT`, profile
      loading/validation) with tests, no model download (A3, A9, part of I2)
      (done 2026-10-21)
- [x] (2) CI: GitHub Action running `pytest` on a Windows runner without torch/model
      download (part of I2) (done 2026-10-21)
- [x] (3) English UI and outputs, neutral example profiles (I7, I5) (done 2026-10-21)
- [x] (4) QuickGELU fix + `ENGINE` bump, cache rebuilt once (E1) (done 2026-10-21)
- [x] (5) Data-loss fixes: unique reference names (A1), robust `read_profiles` + `.bak`
      (A2), E6 (done 2026-10-21)

### P1 – Performance
- [x] Batching across images, parallel decoding, `Image.draft` (E2) (done 2026-10-21)
- [x] Installer option for CUDA torch, YOLO on GPU (A7, I3, E14) (done 2026-10-21; one
      GPU smoke run so far, I11)

### P2 – Robust runs
- [x] Engine writes a status/lock file (PID, phase, progress); the app reconnects after a
      reload and prevents parallel starts (A4, A5) (done 2026-10-21)
- [x] Persist settings in `settings.json` (A8) (done 2026-10-21; A8 itself is partly open)

### P3 – Search quality
- [x] Average the prompt ensemble, normalize scores per profile (E4, E5) (done 2026-10-23;
      evaluation limits: E20)
- [x] Solve the German-language problem: English search terms only, said in the app and
      the README (E3) (done 2026-10-23; multilingual CLIP or an "English search term"
      field were not chosen, multilingual model: E21)

Stronger and multilingual models moved to P4b (user decision in PR #13: evaluate them
on the user's home PC first).

### P3b – Agent context (before further features)
Smaller files to read per change, so implementer and reviewer agents keep less context
(added 2026-10-25 at the user's request, placed before the remaining P4 items); fresh
agents per workflow phase (I17, added 2026-10-26, placed before P4b).
- [x] Reflow `docs/ARCHITECTURE.md` into short lines and sub-sections (I14) (done 2026-10-26)
- [x] Split `framescout_core.py` into a package of modules per area, re-exporting the
      names; no behavior change (I15) (done 2026-10-26)
- [x] Fresh agents for review fixes and documentation updates instead of one growing
      implementer context (I17; workflow change decided by the user on 2026-10-26)
      (done 2026-10-26: `address-review` always a fresh implementer; code implementers
      hand docs to a fresh `docs-update` agent via a "Docs pending:" PR comment)
- [x] Split `BACKLOG.md` by state (open items, finished items, roadmap) so that one file
      is small enough to read (I22) (done 2026-10-27)

### P4 – UX
The item "Result gallery in the app, mark matches/copy them to a folder, "open folder",
ZIP export with thumbnails" is split into three pull requests, in this order (user
decision in PR #14):
- [x] (A) Result gallery in the app: the engine writes `results/results.json`; the app shows
      the last search as a thumbnail grid with "Open", "Folder", "Open gallery in
      browser" and "Open results folder", and marks profiles changed since (A12, part of A8)
      (done 2026-10-23; macOS/Linux untested: A19)
- [x] (B) Mark matches and copy them to a folder (A17) (done 2026-10-25; marks in
      `results/marks.json`, three states; feedback into the search: A20)
- [x] Cleanup of cache/thumbnails/orphaned HTML files and reference files (E7, E11, A14);
      never delete `results/marks.json` (A17) (done 2026-10-25; also E13, E23; HEIC/RAW
      split out into the next item by user decision)
- [x] Optional HEIC/RAW support (E25; new dependencies: a hold point) (done 2026-10-26 in
      PR #26; also AVIF; packages required by user decision, optional extras: E29)
- [x] Turn off Ultralytics' usage analytics and run-time package installs (E27, E28; own
      PR after E25, user decision at the PR #26 hold point) (done 2026-10-26; Hugging Face
      Hub requests per search: E31)
- [x] Several photo folders per search (A25; changes `results.json` and the CLI: a hold point)
      (done 2026-10-26 in PR #28; same folder by another path: A28, junctions: A29)

### P4b – Search models
- [x] Optional stronger models (ViT-B-16, ViT-L-14, SigLIP) with a CPU runtime note (E22;
      investigation, candidates and user decisions recorded there) (plumbing and three
      candidates marked "not evaluated" done 2026-10-26 in PR #31; evaluation: E32)

### P5 – Distribution
- [x] (A) Pinned dependencies (I12) (done 2026-10-26)
- [x] (B) Uninstall script (done 2026-10-27; follow-ups I19, I20, I21)
- [x] (C) Portable Python variant (done 2026-10-27; a private Python 3.14.9 in `.python\`
      for new installations, I20, I21 and I24 done; prebuilt movable bundle: I23)

### P5b – Workflow (added 2026-10-29, user decision in chat)
- [x] Review comments are verified on the PR and posted by the reviewer if the skill posted
      nothing; worktrees and `worktree-agent-*` branches are cleaned up as a fixed step of
      `/roadmap` (I26; open follow-ups: I27, I28, I29) (done 2026-10-29)

### P6 – Safety of user data (added 2026-10-27 from the open backlog)
- [x] (A) Concurrent profile edits no longer overwrite each other (A13) (done 2026-10-27;
      more than one backup generation: A30, deferred by user decision: single `.bak` kept)
- [x] (B) Deleting a profile: ask first, and decide what happens to its marks and copy
      folder (A8, A22; user decision, a stable profile id would be a `profiles.json`
      schema change = hold point) (done 2026-10-27, with A33 from its review; open
      follow-up: A34)
- [x] (C) Clean up unbound cache rows and marks (E8, A21; user decision 2026-10-28:
      renamed/moved photos count as new, no migration; open follow-ups: E37, A35)
      (done 2026-10-28)

### P7 – Offline and nothing outside the project folder
- [x] (A) No Hugging Face Hub request per search once the weights are cached, no symlink
      warning in `run.log` (E16 and E31 describe the same problem: close one as a
      duplicate; E33; check the behavior without internet, the first download must still
      work) (done 2026-10-28; open follow-up: E38)
- [x] (B) Model and config files stay under `.cache/`, also for manual runs (E9, I10; keeps
      the uninstall clean) (done 2026-10-29)

### P8 – Robust runs and galleries
- [x] (A) Skipped photos leave no gaps in the gallery (E12) (done 2026-10-30)
- [x] (B) Stopped runs leave no half-written galleries and temporary files (E24, E26)
      (done 2026-10-30; open follow-ups: E44, E45)
- [x] (C) A RAW file whose JPEG partner is broken is analyzed instead (E30)
      (done 2026-10-30; open follow-up: E46)
- [x] (D) The same photo folder by another path, and junctions inside a folder (A28, A29)
      (done 2026-10-30)

### P9 – App polish
- [x] (A) The photo folder is not scanned on every rerun (A6 and A27 are the same
      problem: close one as a duplicate; how stale a count may be is a UX decision)
      (done 2026-10-30)
- [x] (B) Raise the Streamlit minimum and switch to `width="stretch"` (A10)
      (done 2026-10-30)
- [x] (C) "Hide no match" keeps the pages stable, "Reset to defaults" for the AI settings
      (A24, A26) (done 2026-10-30)

### P11 – Safety of marks and cache (added 2026-11-02)
- [x] Backup of `marks.json` with a restore offer, and a cache health check (F1)
      (done 2026-11-02 in PR #60; follow-ups E50, A40)

### P12 – Lighter runs (added 2026-11-02)
- [x] (A) No person detector load when nothing needs analysis (F2)
      (done 2026-11-02 in PR #62)
- [x] (B) Free disk space check before installing and searching (F3)
      (done 2026-11-02 in PR #64; follow-ups I33, E51)
- [x] (C) "Keep the PC responsive" option, measured together with P10 (B) (F4)
      (done 2026-11-02 in PR #65; the effect is not measured yet: follow-up E52, with E17)

### P13 – Export (added 2026-11-02)
- [x] Export a result list as CSV / file list (F5)
      (done 2026-11-03 in PR #67; follow-ups A41, A42)

### P14 – Hygiene (`minor` items bundled per area, added 2026-11-02)
- [x] (A) Evaluation tool and workflow: E47, E48, I13, I28, I29
      (done 2026-11-03 in PR #68)
- [x] (B) App: A31, A32, A37, A39
      (done 2026-11-03 in PR #69)

### P15 – Orientation during runs (added 2026-11-03)
- [x] (A) Remaining-time estimate and a summary before the start (F12)
- [x] (B) "Check installation" self-test (F15)

### P16 – Hygiene (`minor` items bundled per area, added 2026-11-03)
- [x] (A) Evaluation tool: E36, E49, E51, I25 (done 2026-11-04 in PR #73)
- [x] (B) Engine and cache: E37, E39, E40, E44, E46, E50 (done 2026-11-04 in PR #74)
- [x] (C) App: A34, A38, A40, A41, A42, A43 (done 2026-11-04 in PR #77; A38 not verified in a browser, follow-up A45)
- [x] (D) Installer: I4, I16 (done 2026-11-05 in PR #78)

### P17 – Repository layout (added 2026-11-03)
- [x] Scoring module outside the package (I30) (done 2026-11-05 in PR #79)
