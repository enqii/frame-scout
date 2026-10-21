# FrameScout – Backlog

Result of the code analysis from 2026-10-20 (state v1.1). Work through the items one by
one and check them off here. IDs (E = engine, A = app, I = installation/project) are
referenced in commits, pull requests and discussions.

## Known weaknesses

### Engine (`framescout_engine.py`)

- [x] **E1 – QuickGELU mismatch:** `create_model_and_transforms('ViT-B-32', pretrained='openai')`
      emits the warning `QuickGELU mismatch`; the OpenAI weights run with GELU instead of
      QuickGELU → worse embeddings. Fix: `ViT-B-32-quickgelu` or `force_quick_gelu=True`,
      bump the `ENGINE` signature (the cache is rebuilt once).
      (done 2026-10-21: `ViT-B-32-quickgelu`, same weights file; model name, `ENGINE` (v5)
      and `feature_signature` live in `framescout_core` with tests. Every photo is
      analyzed once more after the update; the v4 rows stay in `cache.sqlite3` (E7).)
- [ ] **E2 – No batching across images:** `embed_images` only receives the crops of a single
      photo, so the batch size has almost no effect. Also: no parallel decoding, full
      resolution (no `Image.draft`), YOLO hard-coded to `device='cpu'`.
- [ ] **E3 – German motif names in English prompts:** e.g. "A photograph of Rotes Auto
      (Fahrzeuge)." – OpenAI CLIP practically only understands English, while the UI
      placeholders are German.
- [ ] **E4 – Maximum instead of mean over prompts:** prone to noise; a generic prompt can
      dominate. An averaged prompt ensemble is common practice.
- [ ] **E5 – Mixed score scales:** text cosine ≈ 0.2–0.35, image-to-image ≈ 0.5–0.9; the
      reference weight therefore has a much stronger effect than its nominal value.
- [ ] **E6 – `path.stat()` outside `try`** in the export (line ~264): a file deleted in the
      meantime aborts the entire HTML export.
- [ ] **E7 – No cleanup:** `thumbnails/`, `cache.sqlite3` (deleted files, old
      signatures) and HTML files of renamed/deleted profiles grow without bound. Since
      I7 the thumbnail folder of older versions, `vorschaubilder/`, is no longer written
      but stays in `results/` (galleries of profiles that were not regenerated still
      link it).
- [ ] **E8 – Cache key = absolute path:** moving the photo folder forces a complete
      recomputation.
- [ ] **E9 – `yolo11n.pt` ends up in the project root** instead of `.cache/`; not documented.
- [x] **E10 – Duplicate check before `strip()`:** "Joker" and " Joker" are not recognized as
      equal. (done 2026-10-21 in `framescout_core.load_profiles`; such a hand-edited
      `profiles.json` is now rejected instead of merging both profiles into one gallery.)

### App (`app.py`)

- [ ] **A1 – Reference images get overwritten:** uploads are always named `reference-1…n`;
      a second upload overwrites the first ones. Profiles with the same slug
      (e.g. "Rotes Auto"/"rotes-auto") share the folder.
      (partly done 2026-10-21: uploads take the next free `reference-<n>` name and never
      overwrite a file – needed because transliteration made more names share a folder,
      e.g. "Bär"/"Baer" → `references/baer/`. Still open: one folder per profile.)
- [ ] **A2 – `profiles.json` data loss:** `read_profiles` does not know the v3 format
      (returns `[]`, the next save overwrites the file). A JSON list → `AttributeError`
      (not caught). No backup before saving.
- [x] **A3 – Slugs app ≠ engine:** the engine appends `-2` on collisions and uses a hash
      fallback, the app uses `profile` without deduplication → downloads missing or
      mismatched. Umlauts are dropped ("Bär" → `b-r`).
      (done 2026-10-21: app and engine use `framescout_core.slugify`/`profile_slugs`;
      "Bär" → `baer`, "Café" → `cafe`, hash fallback for names such as "猫", Windows
      device names get `-profile`, at most 60 characters. Galleries under the old slugs
      (e.g. `b-r.html`) stay in `results/` until cleanup exists (E7).)
- [ ] **A4 – Process handle only in the session:** browser reload → the run is orphaned,
      stopping is impossible, a second start is possible → two processes write to the
      same `run.log` (which gets truncated) and the same SQLite file ("database is
      locked"). Also applies to multiple tabs.
- [ ] **A5 – Progress only for the analysis phase:** scoring, thumbnails and HTML export run
      afterwards without any indication while the bar is already full.
- [ ] **A6 – Folder count on every rerun:** `rglob` over the whole photo folder on every
      interaction; slow for large folders/network drives.
- [ ] **A7 – CUDA never available:** pip installs torch `+cpu`; "cuda" can still be selected.
- [ ] **A8 – UX gaps:** deleting a profile without confirmation; settings only per session;
      results without timestamp/reference to the profile state.
- [x] **A9 – Minor issues:** duplicate `import os`; `EXT` duplicated in app and engine;
      `use_container_width` possibly deprecated (Streamlit 1.66).
      (done 2026-10-21: duplicate import removed, `EXT` lives in `framescout_core`;
      `use_container_width` moved to A10.)
- [ ] **A10 – `use_container_width` is deprecated:** in Streamlit 1.66 the `st.button`
      docstring marks it as deprecated in favor of `width="stretch"` (no runtime warning
      yet; it still works). `width` for buttons is newer than the current floor
      `streamlit>=1.40` (the release notes name 1.48 – not verified), so switching needs
      a raised minimum version → do it together with I3.
- [ ] **A11 – Progress bar parses German log text:** the app reads progress from `run.log`
      with a regex on `Neu:`/`Cache:`/`Fehler:`. Translating the engine log (I7) breaks
      the progress bar unless both change together; a machine-readable progress line or
      status file (see P2) plus a test for the progress interpretation would decouple it.
      (partly done 2026-10-21: the line format lives in `framescout_core.progress_line`,
      the app parses it with `parse_progress`, both tested; the line is English now.
      Still open: a machine-readable status file (P2).)
- [ ] **A12 – Gallery downloads are re-derived from the current profile list:** the app
      maps profiles to `<slug>.html` with `profile_slugs` on the *current*
      `profiles.json`. After deleting, renaming or reordering profiles with colliding
      slugs, a button can serve another (deleted) profile's stale gallery, e.g. delete
      "Rotes Auto" → "rotes auto!" now maps to the old `rotes-auto.html`. Fix: the engine
      writes a manifest (profile name → file, run timestamp) that the app reads – a new
      output format, so a design decision; fits the status file of P2 and A8 ("results
      without reference to the profile state").

### Installation / project

- [x] **I1 – No git repository.** (done 2026-10-20)
- [ ] **I2 – No tests.** (partly done 2026-10-21: `pytest` scaffold and tests for
      `framescout_core` – slugs, `EXT`, profile loading/validation, prompt generation.
      CI done 2026-10-21: `.github/workflows/tests.yml` runs `pytest` on Windows,
      Python 3.12–3.14, without torch.
      Open: tests for cache signature/reuse, scoring and progress interpretation; a smoke
      test with real models.)
- [ ] **I3 – `requirements.txt` unpinned;** no CUDA option in the installer.
- [ ] **I4 – Installer requires the `py` launcher;** without it, the misleading message
      "Python 3.12 to 3.14 not found." is shown.
- [x] **I5 – Example profiles/placeholders lean towards cosplay** (Joker, Harley Quinn, 2B,
      "Batman / DC Comics") – contradicts the general-purpose product goal.
      (done 2026-10-21: `profiles.example.json` ships Red car, Golden retriever, Mountain
      landscape, Bicycle, Birthday cake and Person with umbrella; the context
      placeholder is "e.g. vehicles, pets, nature".)
- [x] **I6 – Update `CLAUDE.md`:** record the successful end-to-end run (`run.log`: 4,997
      photos, 6 profiles, 0 errors; `.venv`: Python 3.14.8, torch 2.14.1+cpu).
      (done 2026-10-20)
- [x] **I7 – Project language English:** translate the UI strings in `app.py`, the HTML
      gallery and log/error messages in `framescout_engine.py`, the `.bat` messages, code
      comments (including `.gitattributes`). Open decisions to resolve in that PR:
      - Rename `results/vorschaubilder/` → `results/thumbnails/`? Existing HTML results
        link the old folder → needs a migration (or keep reading the old folder).
      - `profiles.json` is both the shipped example and the user's working file. Proposal:
        ship `profiles.example.json` (English, neutral examples; I5), gitignore
        `profiles.json` and create it from the example on first start without ever
        touching an existing file.
      - E3 stays relevant: translating the UI does not make users enter English motif
        names.
      - The legacy `franchise` field and the `--character` CLI option stay for
        compatibility.
      (done 2026-10-21: UI, HTML gallery, engine log/error messages and `--help`,
      profile validation messages, `.bat` messages and the `.gitattributes` comment are
      English. The crop label is "Full image"; old cache rows with "Gesamtbild" are
      shown as "Full image", so the cache stays valid. Decisions: new runs write
      thumbnails to `results/thumbnails/`, the old `vorschaubilder/` is left alone (E7);
      `profiles.example.json` is shipped, `profiles.json` is gitignored and created by
      the app on the first start without ever replacing an existing file (breaking for
      existing checkouts: back up `profiles.json` before pulling). The UI placeholders
      are English now, which nudges users towards English motif names (E3), but does
      not enforce it.)
- [ ] **I8 – No branch protection for `main`:** GitHub returns HTTP 403 "Upgrade to GitHub
      Pro or make this repository public to enable this feature" for the private repo, so
      `main` is protected only by the workflow rule (merge only on explicit user approval)
      and the deny rules in `.claude/settings.json`, which are not a security boundary.
      Options: GitHub Pro, making the repository public, or accepting the workflow rule.
      User decision → hold point.
- [ ] **I9 – CI action pins are updated by hand only:** `.github/workflows/tests.yml`
      pins `actions/checkout` and `actions/setup-python` to commit SHAs (with a version
      comment). That avoids moved tags, but security and runtime updates
      (e.g. a Node.js deprecation on the runners) only arrive when someone bumps
      the SHAs. Options: periodic manual bump, or Dependabot for `github-actions`.
      Dependabot opens its own PRs outside the one-PR-per-roadmap-item workflow, so
      this is a workflow decision → hold point.

## Roadmap (priority)

Each unchecked item is implemented in its own pull request, strictly one after another
(see the PR workflow in `CLAUDE.md` and the `/roadmap` skill).

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
- [ ] (5) Data-loss fixes: unique reference names (A1), robust `read_profiles` + `.bak`
      (A2), E6

### P1 – Performance
- [ ] Batching across images, parallel decoding, `Image.draft` (E2)
- [ ] Installer option for CUDA torch, YOLO on GPU (A7, I3)

### P2 – Robust runs
- [ ] Engine writes a status/lock file (PID, phase, progress); the app reconnects after a
      reload and prevents parallel starts (A4, A5)
- [ ] Persist settings in `settings.json` (A8)

### P3 – Search quality
- [ ] Average the prompt ensemble, normalize scores per profile (E4, E5)
- [ ] Solve the German-language problem: multilingual CLIP (`xlm-roberta-base-ViT-B-32`) or
      an explicit "English search term" field (E3)
- [ ] Optional stronger models (ViT-B-16, ViT-L-14, SigLIP) with a CPU runtime note

### P4 – UX
- [ ] Result gallery in the app, mark matches/copy them to a folder, "open folder",
      ZIP export with thumbnails
- [ ] Cleanup of cache/thumbnails/orphaned HTML files (E7); optional HEIC/RAW support

### P5 – Distribution
- [ ] Pinned dependencies, portable Python variant, uninstall script
