# FrameScout – Roadmap

Order of work. Each unchecked item is implemented in its own pull request, strictly one
after another (see the PR workflow in `CLAUDE.md` and the `/roadmap` skill). The open
items come first, in priority order; the next item is the first `- [ ]` line.
The items' IDs (E/A/I) are described in [BACKLOG.md](BACKLOG.md) (open) and
[docs/BACKLOG-DONE.md](docs/BACKLOG-DONE.md) (finished).

## Open (priority order)

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
- [ ] (A) No Hugging Face Hub request per search once the weights are cached, no symlink
      warning in `run.log` (E16 and E31 describe the same problem: close one as a
      duplicate; E33; check the behavior without internet, the first download must still
      work)
- [ ] (B) Model and config files stay under `.cache/`, also for manual runs (E9, I10; keeps
      the uninstall clean)

### P8 – Robust runs and galleries
- [ ] (A) Skipped photos leave no gaps in the gallery (E12)
- [ ] (B) Stopped runs leave no half-written galleries and temporary files (E24, E26)
- [ ] (C) A RAW file whose JPEG partner is broken is analyzed instead (E30)
- [ ] (D) The same photo folder by another path, and junctions inside a folder (A28, A29)

### P9 – App polish
- [ ] (A) The photo folder is not scanned on every rerun (A6 and A27 are the same
      problem: close one as a duplicate; how stale a count may be is a UX decision)
- [ ] (B) Raise the Streamlit minimum and switch to `width="stretch"` (A10)
- [ ] (C) "Hide no match" keeps the pages stable, "Reset to defaults" for the AI settings
      (A24, A26)

### P10 – Checks on the home PC (needs the user's hardware; before P4b)
- [ ] (A) Run the CUDA path and the evaluation tool with real models and fix what shows up
      (I11, E34, E35; a PR "runtime-tested on the home PC")
- [ ] (B) Measure thread counts and YOLO batches on a real CPU and GPU (E17, E18; changing
      detection results is a hold point)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)

### P4 – UX (deferred)
- [~] (C) ZIP export with thumbnails (open decision: A18) – deferred by user decision
      2026-10-25, skipped by `/roadmap`

## Done

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
