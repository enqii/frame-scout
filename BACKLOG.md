# FrameScout – Backlog

Result of the code analysis from 2026-10-20 (state v1.1). Work through the items one by
one and check them off here. IDs (E = engine, A = app, I = installation/project) are
referenced in commits, pull requests and discussions.

## Known weaknesses

### Engine (`framescout_engine.py`)

- [ ] **E1 – QuickGELU mismatch:** `create_model_and_transforms('ViT-B-32', pretrained='openai')`
      emits the warning `QuickGELU mismatch`; the OpenAI weights run with GELU instead of
      QuickGELU → worse embeddings. Fix: `ViT-B-32-quickgelu` or `force_quick_gelu=True`,
      bump the `ENGINE` signature (the cache is rebuilt once).
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
- [ ] **E7 – No cleanup:** `vorschaubilder/`, `cache.sqlite3` (deleted files, old
      signatures) and HTML files of renamed/deleted profiles grow without bound.
- [ ] **E8 – Cache key = absolute path:** moving the photo folder forces a complete
      recomputation.
- [ ] **E9 – `yolo11n.pt` ends up in the project root** instead of `.cache/`; not documented.
- [ ] **E10 – Duplicate check before `strip()`:** "Joker" and " Joker" are not recognized as
      equal.

### App (`app.py`)

- [ ] **A1 – Reference images get overwritten:** uploads are always named `reference-1…n`;
      a second upload overwrites the first ones. Profiles with the same slug
      (e.g. "Rotes Auto"/"rotes-auto") share the folder.
- [ ] **A2 – `profiles.json` data loss:** `read_profiles` does not know the v3 format
      (returns `[]`, the next save overwrites the file). A JSON list → `AttributeError`
      (not caught). No backup before saving.
- [ ] **A3 – Slugs app ≠ engine:** the engine appends `-2` on collisions and uses a hash
      fallback, the app uses `profile` without deduplication → downloads missing or
      mismatched. Umlauts are dropped ("Bär" → `b-r`).
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
- [ ] **A9 – Minor issues:** duplicate `import os`; `EXT` duplicated in app and engine;
      `use_container_width` possibly deprecated (Streamlit 1.66).

### Installation / project

- [x] **I1 – No git repository.** (done 2026-10-20)
- [ ] **I2 – No tests.**
- [ ] **I3 – `requirements.txt` unpinned;** no CUDA option in the installer.
- [ ] **I4 – Installer requires the `py` launcher;** without it, the misleading message
      "Python nicht gefunden" (Python not found) is shown.
- [ ] **I5 – Example profiles/placeholders lean towards cosplay** (Joker, Harley Quinn, 2B,
      "Batman / DC Comics") – contradicts the general-purpose product goal.
- [x] **I6 – Update `CLAUDE.md`:** record the successful end-to-end run (`run.log`: 4,997
      photos, 6 profiles, 0 errors; `.venv`: Python 3.14.8, torch 2.14.1+cpu).
      (done 2026-10-20)
- [ ] **I7 – Project language English:** translate the UI strings in `app.py`, the HTML
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

## Roadmap (priority)

Each unchecked item is implemented in its own pull request, strictly one after another
(see the PR workflow in `CLAUDE.md` and the `/roadmap` skill).

### P0 – Foundation and correctness
- [x] Git repository + private GitHub repo (I1)
- [x] (0) PR workflow (`/roadmap` skill, briefs, permission settings, PR template, labels)
      + English docs incl. `CLAUDE.md` update (I6)
- [ ] (1) `pytest` scaffold + shared module `framescout_core.py` (slug, `EXT`, profile
      loading/validation) with tests, no model download (A3, A9, part of I2)
- [ ] (2) CI: GitHub Action running `pytest` on a Windows runner without torch/model
      download (part of I2)
- [ ] (3) English UI and outputs, neutral example profiles (I7, I5)
- [ ] (4) QuickGELU fix + `ENGINE` bump, cache rebuilt once (E1)
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
