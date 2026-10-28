# FrameScout — architecture and runtime details

Reference for contributors and Claude Code. The rules (language, PR workflow, user data
protection, git) live in `CLAUDE.md`; this file describes what the code does. Read the
sections relevant to the files you touch before changing code, and keep this file current
when behavior changes.

## Verified status
One full end-to-end search run on Windows has been confirmed (I6): `run.log` from the
original checkout shows 4,997 photos, 6 search profiles, CLIP on CPU, YOLO person
detection enabled, 0 errors (2,609 new analyses + 2,388 from cache, i.e. a resumed run)
and 6 HTML galleries written. The project `.venv` used for that run is Python 3.14.8 with
torch 2.14.1+cpu (per `.venv/pyvenv.cfg` and the installed torch package; `run.log` itself
does not record versions). The log also shows the QuickGELU warning (E1, fixed since: that
run's embeddings came from the GELU variant). This is a single CPU-only run, not a test
suite: CUDA beyond one engine smoke run (the installer option and GPU use exist since PR #8; one run with `--device cuda` on an RTX 4070 with torch 2.14.1+cu130 and 300 synthetic
photos, embeddings matching the CPU run; the CUDA install itself, the app on a GPU, real
photos and other GPUs are untested, I11), other Python versions, a fresh install on
another machine and the edge cases in the backlog are **not** verified. Treat syntax
checks, unit tests and a real model run as distinct kinds of evidence, and do not call the
app production-ready. The installer's download, extraction and `venv` creation with the private
Python 3.14.9 (P5 part C) and the uninstall with it were run under `.tmp`; a full installation
with PyTorch on it is **not runtime-tested**.

Search models (E22, PR #31): CPU smoke runs of all four registered models (default,
ViT-B/16, ViT-L/14, SigLIP) with `--no-person-detection`, 3 synthetic images and `.tmp/`
output succeeded, the weights downloaded into the main checkout's `.cache/`. **Not
verified:** search quality of the three optional models (none is evaluated, E32), CUDA with
them, person detection with them, a run without `transformers` installed, and
`Install-FrameScout.bat` with the new requirement. The CPU factors in the registry were
measured once on a Core Ultra 9 285K.

Evaluation tooling (E32/E20, PR #32): `framescout_eval.py`, `framescout_core/evaluation.py`
and the engine's `--scores-file` are covered by unit tests, the engine change additionally by
its syntax tree and `py_compile`; the labelling page was rendered in headless Edge (again
after the review fixes, with fake scores), and the labelling server answered real HTTP
requests on Windows (a label POST, a negative `Content-Length`, a wrong token). **Not
run:** `framescout_eval.py run` with real models, the engine's `--scores-file` in a real
search, the page's keyboard and click handling in a real browser (E34), originals that a
browser cannot display (E35), macOS/Linux.

## Files and responsibilities

### `app.py`

`app.py`: Streamlit frontend. Tabs: Search profiles, Photo source, AI settings, Search &
results. Handles profile CRUD, reference uploads, settings saved in `settings.json` (A8),
hardware display, analysis process, progress/log UI, and the result gallery of the last
search from `results/results.json` (P4 (A), A12: thumbnail grid, 48 per page,
"Open"/"Folder" per photo, "Open gallery in browser", "Open results folder", HTML
download, a note for profiles changed since; results folders without the file list their
HTML files by name) with a three-state mark per photo (Undecided / Match / No match, saved
in `results/marks.json`), "Hide photos marked as no match" and copying of a profile's
matches to a folder (A17); below it the expander "Clean up storage" (E7).

### `framescout_engine.py`

`framescout_engine.py`: standalone CLI. Takes one or more photo folders (positional
`folder`, `nargs='+'`, A25). Parses arguments, loads models, embeds images,
optionally detects persons, caches embeddings, ranks and exports HTML galleries, then
removes temporary and unreferenced thumbnails (`auto_cleanup`, E7/E13). The optional
`--scores-file JSON` (E32, default off, never passed by the app) writes, after scoring and
before the galleries, every crop's text and reference scores per profile for the
evaluation tool (`framescout_core.evaluation.scores_document`; see "Model evaluation
tool"); it changes no cache, profile, settings or `results.json`.

### `framescout_core/`

The package `framescout_core/` is shared by app and engine and uses the **standard library
only** (importable without torch/Streamlit). It has one module per area (I15, split from
the former single file `framescout_core.py`); `__init__.py` re-exports every public name,
so callers write `import framescout_core` or `from framescout_core import <name>`. Put
logic here when both sides need it or it should be unit-tested without models; add it to
the module of its area and to the re-exports in `__init__.py`.

- `names.py`: `EXT` (supported image extensions, including `HEIF_EXT` and `RAW_EXT`,
  E25), `slugify`, `profile_slugs` (unique gallery file names, used by the engine).
- `photos.py` (E25): `available_decoders` (`Decoders`: whether AVIF, HEIC/HEIF and RAW
  can be read here), `supported_extensions` (`EXT` without the extensions of a missing
  decoder), `missing_decoder`, `scan_photos` (the photos of a search as a `PhotoScan`; app
  and engine use it), `skipped_lines` (the log lines about skipped files),
  `distinct_folders`/`output_folder_problem`/`missing_folders_message`/`folder_labels`/`photo_name`/`scan_folders`/`join_scans`
  (several photo folders per search, A25; see "Several photo folders"),
  `raw_preview_usable`/`RAW_PREVIEW_MIN_EDGE` and `raw_preview_transpose`/`RAW_FLIP_TRANSPOSE`
  (the engine's RAW decoding; see "Photo formats").
- `references.py`: `reference_folder` (one reference folder per profile, A1),
  `stage_reference_move`/`update_backup_references`/`finish_reference_move`/`undo_reference_move`
  (a renamed profile's references follow its name, A1), `write_new_file` (reference
  uploads without overwriting).
- `profiles.py`: `create_from_example` (first-start `profiles.json`), `generic_prompts`
  and `load_profiles` (profile loading/validation, used by the engine),
  `read_profiles`/`read_profiles_versioned`/`save_profiles` (the app's `profiles.json`:
  same validation, v3 conversion, atomic save with `profiles.json.bak`, A2; versioned
  read and checked save against concurrent edits, A13: `read_profiles_versioned` returns
  `(profiles, version)`, the version being the SHA-256 of the file's bytes or `None` for
  a missing file; `save_profiles(filename, profiles, expected=version)` takes a `RunLock`
  on `profiles.json.lock` (`PROFILES_LOCK_TIMEOUT` = 5 s, then `OSError`), compares the
  file's current version with `expected` and raises `ProfilesChangedError` (a
  `ValueError`) without writing if it differs, also for a file created or deleted since;
  without `expected` the save is unchecked; the lock file stays, empty; `save_profiles`
  returns the version of the file it wrote; both functions retry a read or replace that
  fails for a moment on Windows while another session reads or replaces the file, 5
  tries 0.05 s apart, like the settings and marks files); `require_profile(filename, name)`
  raises `UnknownProfileError` (a `ValueError`) unless `name` is a profile of the file now
  (an unreadable file: `ValueError` naming it), the check of `save_marks` and
  `save_copy_folder` (review of A22, A33).
- `thumbnails.py`: `thumbnail_name`/`ensure_thumbnail` (gallery thumbnails; a photo
  deleted before the export is skipped, E6), `crop_label`/`FULL_IMAGE_LABEL` (gallery crop
  labels).
- `pipeline.py`: `progress_line`/`progress_due` (the progress line the engine logs for
  people, A11), `prefetch`/`group_batches`/`store_group`/`draft_size`/`DRAFT_DECODING`
  (the engine's analysis pipeline: decoding ahead in threads, crops of several photos per
  CLIP batch, photo-by-photo fallback after a failed group, `Image.draft` size and its part
  of the cache signature, E2).
- `locks.py`: `RunLock`/`lock_held` (the operating-system file lock of a search run, A4,
  also used around the read-merge-write of `settings.json` and `marks.json`).
- `run_status.py`:
  `RUN_LOCK`/`RUN_STATUS`/`StatusReporter`/`read_status`/`write_status`/`run_active`/`started_in_time`/`final_status`/`status_text`/`status_fraction`/`stopped_status`/`PHASE_LABELS`/`FINAL_PHASES`
  (one search per output folder, its phase and progress, A4/A5).
- `devices.py`: `detection_options` (YOLO arguments on the CLIP device, E14),
  `device_choices`/`cuda_status`/`cuda_hint` (the app's device choice, CUDA status and the
  way to GPU support, A7), `ULTRALYTICS_ENV`/`import_detector_class` (the engine's only
  import of Ultralytics, without its analytics and run-time installs, E27/E28; see
  "Environment variables and caches").
- `torch_build.py`:
  `TORCH_VERSION`/`TORCHVISION_VERSION`/`CUDA_BUILDS`/`parse_gpu_query`/`cuda_build`/`unsupported_gpus`/`installed_build_matches`/`installed_cuda_build`/`torch_requirements`/`torch_index_url`
  (which PyTorch build the installer installs, A7/I3).
- `models.py`:
  `SearchModel`/`MODELS`/`DEFAULT_MODEL`/`MODEL_KEYS`/`model_label`/`results_model`/`missing_packages`/`model_problem`
  (the registry of the search models the engine's `--model` and the app's selectbox offer,
  E22; no imports beyond the standard library; fields: key, OpenCLIP name and pretrained
  weights, label, download size, CPU factor, image size, `requires`, `multilingual`
  (for E21; none is), `evaluated`; `results_model` reads the model key of a search from
  its `results.json` settings). The only place of the models' OpenCLIP names, the
  default's too.
- `signature.py`: `ENGINE_TEMPLATE`/`engine_id`/`ENGINE`/`MODEL_ENGINES`/`feature_signature`
  (the engine id per search model and the feature cache signature, E1/E22),
  `CACHE_FILE`/`DEFAULT_YOLO_MODEL`/`prepare_cache`/`known_signatures`/`SLIDER_NOISE_ULPS`/`classify_signatures`
  (the cache tables with the `signatures` side table, and which engine version and
  settings a cached row belongs to, E11).
- `settings.py`:
  `SETTINGS_FILE`/`SETTING_RANGES`/`SETTING_STEPS`/`DEFAULT_REFERENCE_WEIGHT`/`DEVICES`/`LEGACY_PHOTO_FOLDER`/`default_settings`/`folder_lines`/`read_settings`/`save_settings`/`reconcile_settings`
  (the app's `settings.json`, the ranges of its widgets, the engine's `--device` choices,
  and the sync of the widgets with the file, A8).
- `results.py`:
  `RESULTS_FILE`/`RESULTS_FORMAT`/`result_card`/`results_document`/`write_results`/`read_results`/`search_fingerprint`/`profile_fingerprints`/`profile_state`/`GALLERY_PAGE_SIZE`/`page_count`/`page_cards`/`openable_photo`/`open_command`/`reveal_command`
  (the result file of a search and the app's gallery: validation of the file (plain
  gallery and thumbnail file names only), whether a profile changed since the search,
  pages, and opening only existing image files, A12).
- `marks.py`: `MARKS_FILE`/`MARK_STATES`/`read_marks`/`save_marks`/`rename_marks`/`delete_marks`/`remove_marks`
  (the user's marks, A17; `delete_marks` removes all marks of a deleted profile, A22;
  `remove_marks(path, entries)` removes single `(profile, photo path)` marks for the cleanup, E8;
  `save_marks(..., profiles_file=...)` saves only for a name that is a profile now).
- `copying.py`:
  `COPY_FOLDERS_KEY`/`default_copy_folder`/`copy_target`/`copy_photos`/`copy_summary_text`/`read_copy_folders`/`save_copy_folder`/`rename_copy_folder`/`forget_copy_folder`
  (copying marked matches and their saved target folders in `settings.json`, A17;
  `forget_copy_folder` removes only the saved entry of a deleted profile, A22;
  `save_copy_folder(..., profiles_file=...)` like `save_marks`).
- `cleanup.py`:
  `THUMBNAILS_DIR`/`LEGACY_THUMBNAILS_DIR`/`GALLERY_MARKER`/`CLEANUP_CATEGORIES`/`CACHE_CATEGORIES`/`CLEANUP_DEFAULTS`/`NEVER_DELETED`/`ROOT_TIMEOUT`/`scan_cleanup`/`clean_up`/`auto_cleanup`/`cleanup_running`/`size_text`/`count_text`/`cleanup_summary_text`
  (the storage cleanup, E7/E11/E13/E23/A14/E8; the unbound-photo check is the private `_PathCheck`).
- `portable_python.py` (P5 part C):
  `PYTHON_VERSION`/`PYTHON_URL`/`PYTHON_SHA256`/`PRIVATE_PYTHON` (the private Python that
  the installer downloads into `.python`; constants only, checked against the `.bat` by
  `tests/test_installer.py`).
- `uninstall.py` (P5):
  `UNINSTALL_ITEMS`/`UNINSTALL_KEEP`/`UNINSTALL_FIRST`/`USER_DATA`/`ENVIRONMENT_PROGRAMS`/`UninstallItem`/`PRIVATE_PYTHON_EXIT_CODE`/`running_python`/`protected_folders`/`uninstall_plan`/`user_data`/`outside_leftovers`/`search_running`/`programs_in_use`/`remove_items`
  (what the uninstall script deletes, keeps and only reports; standard library only.
  `uninstall_plan(root, protected)` returns the existing items to delete and the skipped
  ones: an item that contains a photo or copy folder of `settings.json` (except inside a
  kept entry, `.tmp/eval`), that lies inside one (a photo folder that is the project
  folder or above it) or whose kept entries cannot be listed is skipped.
  `protected_folders` reads `settings.json` once and raises if it is unreadable or its
  `photo_folders`/`photo_folder`/`copy_folders` are not allowed values (the app would fall
  back to the default photo folder). Kept entries match case-insensitively where the file
  system does (`normcase` or `samefile`), like `_inside`. Links and junctions are removed
  as links, never followed. `remove_items` deletes the environment's
  `python.exe`/`pythonw.exe` first (`UNINSTALL_FIRST`), retries read-only files and
  folders after clearing the attribute (only those), continues after a failure (also an
  unlistable item) and returns the failures; a folder that is not empty because a file
  inside it failed is not reported again. `search_running` = the run lock of `results/`
  is held; `programs_in_use(root, clear_read_only=False)` = opening the environment's
  `python.exe`/`pythonw.exe` for writing fails with a sharing violation (Windows error
  32), i.e. a process runs or holds them; a read-only program gives "access denied"
  before that check, so it counts as not running unless `clear_read_only` clears its
  attribute first (done only after the user typed `yes`). `user_data` lists names only
  (no sizes: no walk of `photos/`, `results/`). `outside_leftovers` lists the PyTorch, Hugging Face
  and Ultralytics folders outside the project (from `TORCH_HOME`, `HF_HOME`,
  `YOLO_CONFIG_DIR`, `XDG_CACHE_HOME`, `APPDATA` or the user profile defaults), never
  deleted: they are shared with other programs, I10).
- `evaluation.py` (E32/E20):
  `SCORES_FORMAT`/`LABELS_FORMAT`/`EVAL_K`/`SCORE_DIGITS`/`collection_name_problem`/`write_document`/`read_document`/`scores_document`/`write_scores`/`read_scores`/`read_labels`/`save_labels`/`set_label`/`average_precision`/`build_pool`
  (the formats of the model evaluation tool: scores file of the engine's `--scores-file`,
  labels file, AP@k = mean of the precision at each hit in the top k divided by
  min(labelled hits, k), a labelled hit outside the top k counts as a miss, no hits ->
  `None`; `build_pool` = union of each ranking's first `depth`, shuffled reproducibly with
  the profile name as seed, independent of the model order; collection names 1-64 of
  `A-Za-z0-9_-`, no Windows device names).
- `_common.py` (internal, not re-exported): helpers several areas share, i.e. atomic
  writes (`_publish_via_temp`, `_publish_new`, `_replace_atomically`,
  `_replace_with_retry`), reading a file (`_read_with_retry`) or a JSON object file
  (`_read_json_object`) with retries, the save lock of a file on `<file>.lock`
  (`_file_lock`, used by `_update_locked` and `save_profiles`), the locked
  read-change-write of a JSON file (`_update_locked`) and `_path_key`.

Dependencies between the modules go one way (no import cycles): `cleanup` uses most of the
others, `_common` uses only `locks`. Private helpers (leading underscore) are not
re-exported (`tests/test_core_package.py` checks both directions: every public name of
an area module is on the package, no private one is). A test that monkeypatches a helper
patches the module that calls it, e.g.
`monkeypatch.setattr(framescout_core.cleanup, '_remove_file', …)`: a patch on the package
does not reach the calling code. For a private helper such a patch fails (the package has
no such attribute), but for a public name another module imports, e.g. `read_profiles` as
used by the cleanup, it succeeds silently and has no effect: patch
`framescout_core.cleanup.read_profiles`. Standard library functions are patched on their
own module (`monkeypatch.setattr(os, 'replace', …)`), which reaches every area.

### `framescout_scoring.py`

`framescout_scoring.py`: the engine's scoring, **numpy only** (no torch): `text_queries`
(the generated templates averaged into one query, custom prompts kept apart, E4),
`best_scores`, `spread`/`MIN_SCORES`/`MIN_SPREAD`, `rank_photos`/`Match` (per-profile
z-scores and their combination, E5) and `score_caption` (the numbers on a gallery card).

### `framescout_eval.py` and `framescout_eval_page.html`

Development tool (E32/E20, not part of the app, not on the install path): numpy,
`framescout_scoring` and `framescout_core`, no torch; `run` starts the engine as a
subprocess. See "Model evaluation tool" below.

### `tests/`, `pytest.ini`, `requirements-dev.txt`

`tests/`, `pytest.ini`, `requirements-dev.txt`: pytest suite for `framescout_core/`,
`framescout_scoring` and `install_torch.py` (no torch, no model download); dev
dependencies `pytest` and `numpy` (for `framescout_scoring`, user decision in PR #11).
`test_models.py` (E22) tests the registry, and its checks of every model's open_clip
config (weights known, image size, QuickGELU of the weights, E1; Hugging Face tokenizer)
read open_clip's config tables only where open_clip is installed and are skipped in CI.

### `profiles.example.json` and `profiles.json`

`profiles.example.json`: shipped, general-purpose English example profiles (I5).
`profiles.json`: the user's working profile list, **gitignored**; `app.py` creates it from
the example on the first start with `framescout_core.create_from_example`, which never
replaces an existing file. Every app save keeps the previous file as `profiles.json.bak`
(one generation, gitignored); a file the app cannot read stops the app instead of being
saved over (A2). Back it up before overwriting user changes. A save is refused if the
file changed since the page showed it (A13); the lock file `profiles.json.lock` is
gitignored and in `NEVER_DELETED`. More generations: A30.

### `requirements.txt`

`requirements.txt`: `torch==2.14.1` and `torchvision==0.29.1` pinned (same values as
`framescout_core.TORCH_VERSION`/`TORCHVISION_VERSION`, checked by a test; change them
together); Streamlit `>=1.40` (A10); `transformers>=5.21.0` (the SigLIP tokenizer, E22;
torch and huggingface-hub unchanged, `pip check` clean); numpy, Pillow, open_clip_torch, ultralytics and
psutil with the versions of the verified runs as minimum, no upper bounds (user decision);
the installer pins the versions of the verified runs with `constraints.txt` (I12). `pillow-heif` and `rawpy` (E25, required by user decision;
optional extras: E29) have the versions of the venv's smoke runs (PR #26) as minimum.

### `constraints.txt`

`constraints.txt` (I12): exact pins (`name==version`) of all 84 packages in the dependency
closure of `requirements.txt`, direct and transitive, taken from the project venv (Python
3.14, Windows); no hashes. torch and torchvision are pinned without a local label
(`torch==2.14.1`), so the `+cpu`, `+cu126` and `+cu130` builds all satisfy the pin. It is a
pip constraints file: it limits versions but installs nothing by itself, and
`requirements.txt` keeps its ranges (no upper bounds, I3). Only `Install-FrameScout.bat`
uses it: it sets `PIP_CONSTRAINT=constraints.txt` (after creating the venv, so `ensurepip`
is not affected) for the pip call of `install_torch.py` (I18) and passes `-c
constraints.txt` to the requirements install. The value is relative because pip splits
`PIP_CONSTRAINT` at whitespace and the install folder may contain a space; both pip calls
run in the install folder. A plain `pip install -r requirements.txt` or a manual
`install_torch.py` takes the newest releases. The file is sorted by package name.
Evidence: the pins are the venv of the verified runs (a CPU engine run on Python 3.14);
3.12 and 3.13 are only checked by the dry-run below; the CUDA wheels only by their
metadata (their Windows Requires-Dist is the same as that of the `+cpu` wheels and allows
every pin; PR #33 review). Refreshing is manual, in a PR of its own: update and test the
venv, write the closure into the file, then check with `pip install --dry-run
--ignore-installed --report r.json --python-version 3.12|3.13|3.14 --platform win_amd64
--only-binary=:all: -r requirements.txt -c constraints.txt` that every resolved package is
pinned and has a wheel, and compare the Requires-Dist lines of the CUDA wheels' metadata
on the PyTorch index (`<wheel>.metadata`, PEP 658) with the pins; a pip dry-run against
that index downloads the wheels (pip 25.2 downloads them even with `--dry-run`). The
header of the file says this. `tests/test_constraints.py` keeps the file consistent (see
"Test coverage").

### `Install-FrameScout.bat`

`Install-FrameScout.bat [cpu|cuda]` (P5 part C): needs no installed Python and has no
search for Python 3.14/3.13/3.12. A new installation downloads python.org's full package
`python-3.14.9-amd64.zip` (about 33 MB, about 117 MB extracted) with `curl.exe` to `.tmp`,
checks its SHA-256 with `Get-FileHash` (Windows PowerShell; `PSModulePath` is cleared for
this one call and restored right after it, because a PowerShell 7 parent breaks the
cmdlet lookup), extracts it with `tar.exe` to `.tmp\python-3.14.9`, moves it as a whole to
`.python\` (up to five tries about three seconds apart, waiting with `ping`, because a
virus scanner that checks the new files makes the move fail with "Access is denied"; then
it reports the move as failed) and creates `.venv` with
`.python\python.exe -I -m venv --clear .venv`. The pins are `PYTHON_VERSION`/`PYTHON_URL`/
`PYTHON_SHA256`/`PRIVATE_PYTHON` in `framescout_core/portable_python.py`; the `.bat` holds
the same values and `tests/test_installer.py` keeps them in sync. An existing `.venv` is kept
without a download or migration if `.venv\Scripts\python.exe -I -c "import pip"` works,
also one of an older installer (installed Python 3.12-3.14). Otherwise (its Python is
gone: `.python` deleted, the folder moved, an installed Python removed; or `venv` stopped
before pip) the installer gets the private Python, checks the `.venv` again (a `.venv` of
the private Python works again once `.python` is back, so its packages are kept) and else
creates it again with `--clear`. A `.python` is reused only if `python.exe` exists and
runs `import venv, ensurepip` and reports `PYTHON_VERSION` (`platform.python_version()`);
otherwise it is deleted and downloaded again (I24; a `.python` that cannot be deleted
stops with a message). If `venv` fails, the half-created `.venv` is removed and the message
says to delete `.python`. `.venv` refers to `.python` by absolute path, so the folder
cannot be moved afterwards without running the installer again, which then re-creates
`.venv` and downloads all packages again (prebuilt movable bundle: I23). The script uses no delayed expansion (a `!` in
the folder path would be dropped from `cd` and `%CD%`), `goto` instead of parenthesized
blocks and never the folder path inside parentheses (I21). Then it sets `PIP_CONSTRAINT=constraints.txt` (I18),
installs PyTorch with `install_torch.py` (passing the argument on; torch's dependencies
come in their pinned versions), then `pip install --no-cache-dir -r requirements.txt -c
constraints.txt` (on a re-run this moves installed packages to the pinned versions and may
downgrade newer ones; an installed CUDA build is kept), performs imports and prints the
PyTorch build and whether CUDA is available.

### `install_torch.py`

`install_torch.py [cpu|cuda] [--dry-run]`: installs the pinned PyTorch from the PyTorch
index (dependencies also from PyPI; in the versions of `constraints.txt` when run by
`Install-FrameScout.bat`, which sets `PIP_CONSTRAINT`) – the CPU build or the CUDA build that
`framescout_core.cuda_build` picks from `nvidia-smi` (`cu130`, otherwise `cu126`; a build
for every GPU, else for the most capable one). Without an argument an installed CUDA build
is kept and nothing is asked; otherwise it asks for GPU support only if `nvidia-smi` finds
an NVIDIA driver. If no CUDA build fits, an installed CUDA build is kept, otherwise the
CPU build is installed; **only an explicit `cpu` replaces a CUDA build** (PR #8 review). A
matching installed build is not downloaded again. Exit code 0 done, 1 failed. Standard
library only.

### `Uninstall-FrameScout.bat` and `framescout_uninstall.py`

`Uninstall-FrameScout.bat [--dry-run]` (P5 part B, I20 in part C) runs
`framescout_uninstall.py` with `.python\python.exe` if it exists, otherwise (installations
of older installers) with the first of Python 3.14/3.13/3.12 found through the `py`
launcher (neither: it prints the manual steps, which name `.venv`, `.python`, `.cache` and
`.tmp`), with `-B -E -s` and **not** with `.venv`'s Python, which
cannot delete itself while it runs. It sets no cache or `TMP` variables (`.tmp` is
deleted) and uses no delayed expansion, which would drop a `!` from the folder path and
the arguments (review: the `cd` then failed and the script of the current directory
ran); the folder path is never used inside parentheses. The script uses
`framescout_core.uninstall`: it refuses (deleting nothing) when `results/run.lock` is
held, the environment's `python.exe`/`pythonw.exe` is in use (checked again after `yes`,
then with read-only attributes cleared) or `settings.json` is unreadable or has invalid
photo/copy folders; otherwise it prints the items to delete with sizes, the skipped ones
with the reason, the kept user data (`USER_DATA`, listed without sizes, never deleted:
photos, references, results with `marks.json`, profiles and backup, settings, `run.log`,
`.tmp/eval`) and the caches outside the folder (listed only, with sizes), and deletes
after the answer `yes`. `--dry-run` stops after the lists. Exit code 0 done or listed, 1
refused, all items skipped, or failures, `PRIVATE_PYTHON_EXIT_CODE` = 3 everything was
deleted except the private Python the script runs with: `framescout_core.running_python`
finds the `.python` item when the interpreter is inside it (not for a link, which the
script removes itself); the item is listed as "deleted last, when this script has ended"
and left out of `remove_items`. Exit code 3 is returned only after `yes`, not in a dry run,
after failures or when `.python` was skipped. The `.bat` then deletes `python.exe`,
`pythonw.exe` and `.python` (`rmdir /s /q`) and reports a leftover with exit code 1,
otherwise exit code 0. The "FrameScout is running" check still looks at the `.venv`
programs. "Python itself was installed separately and stays" is printed only when there is
no `.python`. Not deleted: the program files themselves. Opt-in deletion of user data is
I19.

### `Start-FrameScout.bat`

`Start-FrameScout.bat`: launches app via that venv on `127.0.0.1:8501`.

### `README.md`

`README.md`: English user guide (GitHub start page).

### `ROADMAP.md`, `BACKLOG.md`, `docs/BACKLOG-DONE.md`

`ROADMAP.md`: the prioritized roadmap that drives the PR workflow (open items first, the
next item is the first `- [ ]` line; finished ones under "Done").
`BACKLOG.md`: open items (IDs E/A/I). `docs/BACKLOG-DONE.md`: finished items with their
reports; an item moves there unchanged when its PR is merged (I22).

### `.claude/skills/roadmap/` and `.claude/settings.json`

`.claude/skills/roadmap/`: the `/roadmap` orchestrator skill plus implementer/reviewer
briefs (the implementer brief also covers the fresh `docs-update` and `address-review`
agents, I17). `.claude/settings.json`: shared permission rules for the workflow.

### `.github/pull_request_template.md`

`.github/pull_request_template.md`: definition-of-done checklist for every PR.

### `.github/workflows/tests.yml`

`.github/workflows/tests.yml`: CI – runs `pytest` (plus a `compileall` syntax check of all
Python files outside dot-directories) on `windows-latest` for Python 3.12/3.13/3.14 on
every pull request and push to `main`. It installs only `requirements-dev.txt` and fails
if torch is installed, so tests must not need torch or model downloads. Green CI is
unit-test and syntax evidence only, not a model run.

### Runtime data

Runtime data (generated, not in the repo): `settings.json` and `settings.json.lock` (the
app's settings and the lock of their saves, A8), `photos/` (default input), `references/`,
`results/`, `results/cache.sqlite3`, `results/thumbnails/` (older runs:
`results/vorschaubilder/`), `results/run.lock` and `results/run-status.json` (A4/A5),
`results/results.json` (the last finished search, A12), `results/marks.json` and
`results/marks.json.lock` (the user's marks, A17: user data, never written by the engine
and never deleted by the cleanup, E7), `profiles.json`, `run.log`, `.cache/`, `.tmp/`,
`.venv/`, `yolo11n.pt`; `.tmp/eval/<collection>/` of the evaluation tool (below).

### Model evaluation tool

`framescout_eval.py {run,pool,label,metrics}` (E32/E20, PR #32) measures the search
models on the user's own labelled photos. Collection layout, default
`<project>/.tmp/eval/<collection>/` (gitignored; `--dir` elsewhere):
`collection.json` (folders and profiles file, remembered so a re-run may omit them; a file
without a folder list or profiles path is an error, exit code 2, and is left as it is),
`engine/<model>/` (one engine output folder per model: cache, galleries, thumbnails; separate
so one run's thumbnail cleanup never removes another model's), `scores/<model>.json`,
`pool.json`, `labels.json` (`{"format": 1, "labels": {profile: {absolute photo path:
true|false}}}`; an unreadable file is never saved over, the page refuses to start).

- Scores file (`{"format": 1, "model", "signature", "photos": [{"path", "mtime_ns", "crops"}],
  "profiles": [{"name", "prompts", "references", "text", "visual"}]}`): scores per photo and
  crop rounded to `SCORE_DIGITS` (6), so the tool's ranking can order near-ties within that
  rounding differently from the galleries; `visual` is null without reference images.
  `read_scores` accepts finite numbers only, and `write_document` refuses NaN/infinity
  (`allow_nan=False`); the engine cannot produce them (`photo_scores` skips such a photo).
- `run`: per model `framescout_engine.py <folders> --profiles P --output engine/<model>
  --model <model> --scores-file scores/<model>.json --device --batch-size --top 150
  [--no-person-detection]` with `TORCH_HOME`/`HF_HOME`/`YOLO_CONFIG_DIR`/`XDG_CACHE_HOME`
  under `<project>/.cache` (`--cache-dir`) and `PYTHONIOENCODING=utf-8`. A model with a
  missing package (`model_problem`) is skipped; exit 1 if any model was not scored. A
  model's `scores/<model>.json` is removed before its run and again after a failed one, so a
  skipped or failed model keeps no scores of an older run. A model not yet cached downloads
  its weights on first use.
- `pool`: ranks each model's scores with `rank_photos` (the engine's scoring) at
  `--weights` (default `0,0.3,0.6`, only for profiles with reference images), top `--depth`
  (100) per model and weight, prints pool size, labelled count and a time estimate (1.5 s
  per photo), and warns if a profile changed between model runs or the models scored
  different photos (path and `mtime_ns`). Re-running keeps all labels. Labels are keyed by
  profile name and photo path only, so they survive prompt edits; a new motif needs a new
  profile name (E36).
- `label`: `LabelServer` (a `ThreadingHTTPServer` without `SO_REUSEADDR` on Windows, where
  it would let a second page bind the same port silently) on `127.0.0.1:8765` (`--port`
  0-65535, `--no-browser`; a port in use is an error, exit code 2), every route behind a
  random token (`/<token>/`, compared with `secrets.compare_digest`); shows the profile and
  one photo (the gallery thumbnail of any model's run if present, else the original, E35;
  the state's `thumb` flag lets the page prefetch thumbnails only, never originals); each
  label is POSTed (`Content-Length` 0 to `MAX_BODY` = 10,000, else 400) and saved
  atomically at once, a failed save is shown and reverted; resumes at the first unlabelled
  photo.
- `metrics <collection>...`: AP@`--k` (40) per profile and model at `--weight` (default
  `DEFAULT_REFERENCE_WEIGHT`), warnings about labels no model run scored (another profile
  name, a moved or relative photo path: such a match counts as missed by every model,
  `label_warnings`), unlabelled photos in a top list count as no match, a
  reference-weight sweep (`--sweep`, best per model marked `*`), the mean over several
  collections; Markdown tables, `--json FILE`.

## Current search pipeline

### Model and prompts

The search model is chosen from the registry `framescout_core.MODELS` (E22; engine option
`--model <key>`, settings key `model`). The default `vit-b-32-openai` is OpenCLIP
`ViT-B-32-quickgelu`, `pretrained='openai'` (`MODELS[DEFAULT_MODEL]`; the OpenAI
weights need QuickGELU, plain `ViT-B-32` would run them with GELU, E1). Optional and **not
evaluated** (E32): `vit-b-16-datacomp` (`ViT-B-16`, `datacomp_xl_s13b_b90k`),
`vit-l-14-datacomp` (`ViT-L-14`, same weights) and `vit-b-16-siglip` (`ViT-B-16-SigLIP`,
`webli`; needs `transformers` for its tokenizer, `SearchModel.requires`). The engine
checks `model_problem` before the scan (`parser.error`), loads the model and the tokenizer
of that name, takes the draft size from `model.visual.image_size` (falling back to the
registry's `image_size`) and logs `search model: <label> (<name>/<pretrained>)`. Its
stdout/stderr escape characters they cannot encode (`errors='backslashreplace'`, e.g. the
"·" of a label on a redirected cp932 stdout; E22 review). The
embeddings are normalized text and image embeddings. The reference weight (E5) and all
other defaults are tuned for the default model; scores of different models are not
comparable (SigLIP's raw cosines are lower; the z-scores absorb this). No LLM is required. Four generic English prompt
templates are derived from each profile's name and optional context, plus two extra
templates if `features` is provided (`load_profiles` reports their number as `generated`);
user-defined `prompts` are appended.

### Search terms are English only

Search terms are **English only** (E3, user decision in PR #12): the model understands
practically only English and nothing is translated. The profile tab shows a hint and
labels the motif, context, features and custom search text fields "in English"; README
section "Search terms in English". Hint text only: do not add a language check, warning or
translation without a new user decision. A multilingual model is E21
(`xlm-roberta-base-ViT-B-32`: about 1.47 GB, `transformers`, re-analysis of every photo; a
hold point).

### Several photo folders

A search covers a list of photo folders (A25, user decisions at the hold point of PR #28).
The engine resolves the positional folders (parsed with `parse_intermixed_args`, so they
may stand between options); an output folder equal to one of them, or containing one
(whose files the scan would always leave out), is an error (`output_folder_problem`). `distinct_folders` drops a folder listed twice and one inside another listed
folder (compared by `os.path.normcase` of the resolved path; the notes go to the log).
Missing folders are left out with a log line ("Photo folder not found, searched without
it"); only if none exists is it an error (`missing_folders_message`, before the lock as
for one folder, see "Run lock and status"). `scan_folders` joins the `scan_photos` of the
folders. The gallery and `results.json` name a photo by `photo_name`: its path in its
folder, after the folder's label (`folder_labels`: none for one folder, so a one-folder
gallery is unchanged; otherwise the folder name, with more trailing path parts for
folders of the same name, compared case-insensitively, and for a label that starts
another label, e.g. `Event` and `Event\sub`, so no two photos get the same name; a drive
root is labeled by its drive, e.g. `D:`). Cache rows and marks stay keyed by absolute path, so neither the cache
signature (`ENGINE`) nor `marks.json` changes. Not recognized: the same folder by another
path (hard links, another drive letter or UNC path for the same share, A28) and junctions
inside a listed folder, which `Path.rglob` follows on Python 3.14 (checked on Windows
11: files under a junction are listed by their path through it, A29).

The app: the "Photo source" tab has a text area (`setting_photo_folders`, one folder per
line). `settings.json` stores the list `photo_folders`; `setting_of_widget` /
`widget_of_setting` in `app.py` convert between the text and the list (`folder_lines`:
the non-empty lines, stripped), so `reconcile_settings` and `save_settings` work on
lists. The tab shows the count per existing folder (each scanned once per page run, as
before: A6), the notes of `distinct_folders` and a warning per missing folder. "Start
search" needs one existing folder (from that scan, no second `is_dir`) and passes all
distinct folders. The copy target check takes the folders of `results.json` and the
current list; the cleanup does not depend on the list (E8, see "Storage cleanup").
Checked in PR #28 with one CPU engine smoke run on synthetic photos under `.tmp/` (two
folders of the same name, a nested and a missing one; one folder; none existing; output
equal to a folder; after the review folders between options and a folder inside the
output folder) and the app with Streamlit's `AppTest` (old `settings.json`, format 1
`results.json`, editing the list, the cleanup scan of that time with a missing folder listed twice),
not in a browser.

### Photo formats

The engine reads the files of the photo folders whose extension is in `EXT`
(`framescout_core.scan_photos` per folder, also used for the app's photo count), leaving
out the output folder. Pillow reads JPEG, PNG, WebP, BMP, TIFF and AVIF (if built with libavif,
as its wheels are); `pillow-heif` adds HEIC/HEIF (`register_heif_opener` at engine start)
and `rawpy` camera RAW (`RAW_EXT`, E25). `available_decoders` checks all three by
importing them (a package that is installed but cannot be loaded counts as missing); the
engine and the app (`st.cache_resource`, once per app process) call it, so both agree
(review). The extensions of a missing decoder are left out (`supported_extensions`); a
reference image of such a format fails with the reason (`missing_decoder`).

- **RAW decoding** (`open_raw`/`raw_preview` in the engine, user decision at the E25 hold
  point): the embedded JPEG or bitmap preview (`extract_thumb`) if its longer edge has at
  least `RAW_PREVIEW_MIN_EDGE` (1024) pixels – a JPEG preview is drafted like any JPEG –
  else the sensor data at half size (`postprocess(half_size=True, use_camera_wb=True)`,
  which LibRaw turns upright). A preview LibRaw cannot extract or Pillow cannot read also
  leads to the half-size decode (review). A preview is turned upright by its own EXIF
  orientation if it has one (2..8), else by LibRaw's `sizes.flip`
  (`raw_preview_transpose`), never by both.
- **RAW+JPEG pairs:** a RAW file is skipped if a supported `.jpg`/`.jpeg`/`.heic`/`.heif`
  file of the same name (ignoring case) is in the same folder (`RAW_PARTNER_EXT`). The
  rule looks at names only: if that JPEG/HEIC cannot be decoded, the engine logs it as an
  `ERROR` and the shot is missing from the search (falling back to the RAW file: E30).
- **Skipped files:** the log names the RAW files skipped for a partner (count and one
  example), the files of a missing decoder with the reason (only if the folder has such
  files), and the files of other extensions by extension (`skipped_lines`); the app's
  "Photo folder" tab shows the same lines. The app scans the folder on every rerun, as
  it counted the photos before E25 (A27).
- **Cache:** the new extensions only add rows, so the cache signature and `ENGINE` did not
  change. A change of the RAW decoding (e.g. `RAW_PREVIEW_MIN_EDGE`) changes the embeddings
  of RAW photos and needs an `ENGINE` bump.
- Browsers cannot show HEIC/RAW files: the gallery thumbnails are JPEG, but the photo link
  of such a card downloads the file or hands it to the OS.
- **Verified (PR #26):** CPU smoke runs with and without person detection on five CC0
  samples from raw.pixls.us (Canon CR2 and CR3, Nikon NEF, Sony ARW, Pentax DNG; all with a
  JPEG preview, 1616 px to full size; the forced half-size decode took 0.1–0.7 s each),
  two HEIC files made with pillow-heif (one stored sideways with EXIF orientation 6, decoded
  upright by libheif), a HEIC reference image, a RAW+JPEG pair and a `.mov`; a rerun took
  every photo from the cache. After the review: the fallback for a simulated broken preview
  (LibRaw error, unreadable JPEG, small bitmap), and engine runs with pillow-heif, rawpy and
  Pillow's AVIF support blocked (skipped-file lines, HEIC reference error). Not verified: a
  RAW file with a rotated `flip` or without a usable preview of its own (the fallback was
  only forced), HEIC from a real phone, other cameras.

### Person detection

Optional Ultralytics `yolo11n.pt` person detection (`classes=[0]`) extracts individual
person crops **in addition to the full original image**. Detection is deliberately
optional for non-person motifs; the detector runs on the CLIP device (E14), one photo per
call under a lock (several photos per call: E18).

### Analysis pipeline

Analysis pipeline (E2): uncached photos are stat-ed, decoded, searched for persons and
preprocessed in threads – up to four without person detection (`DECODE_THREADS`), two with
it (`DETECTION_DECODE_THREADS`, so at most two full-resolution photos are in memory while
the detector runs one photo at a time) – at most `max(2 × threads, --batch-size +
threads)` photos ahead (`framescout_core.prefetch`); the shared YOLO detector is called
under a lock. The crops of several photos are embedded in one CLIP forward pass of at most
`--batch-size` crops (`framescout_core.group_batches`; a photo with more crops is a group
of its own), and each group is committed to SQLite in one transaction; if that fails, its
photos are stored one by one, so only a failing photo is counted as an error
(`framescout_core.store_group`). Without person detection JPEGs are decoded at 1/2, 1/4 or
1/8 scale (`Image.draft`) down to twice the CLIP input size (`framescout_core.draft_size`,
448 px); with person detection they keep full resolution. Gallery thumbnails are drafted
the same way (to 760 px for 380 px thumbnails). Cache signature: with detection it is
unchanged (the features are identical); without detection it names the drafted decoding
(`DRAFT_DECODING`, user decision in the PR #7 review), so the first detection-off run
after E2 analyzes every photo once more and drafted and full-resolution embeddings never
mix (they agree to a cosine similarity ≥ 0.999 on a 202-photo sample).

### Scoring

Scoring (`framescout_scoring`, E4/E5): the generated templates of a profile are averaged
into one normalized query (prompt ensemble); each custom prompt stays a query of its own,
and a crop's text score is its best cosine similarity with one of these queries (user
decision in PR #11: custom prompts keep their "any of these" meaning). If reference images
exist, visual score = max over reference vectors. Per profile and run, the text and visual
scores are z-scored separately over all crops of the searched photos (mean and standard
deviation of this search), then combined as `(1-reference_weight)*z_text +
reference_weight*z_visual` (a channel with weight 0 needs no spread) (default reference
weight 0.3, `framescout_core.DEFAULT_REFERENCE_WEIGHT`, also the engine's
`--reference-weight` default; 0.35 before E5, changed after the local evaluation in PR #11, E20); with fewer than `MIN_SCORES` (10) crops or a spread below `MIN_SPREAD` in
either channel, both channels use the raw cosine scores as before E4/E5. The best
full-image/crop score represents a source photo. The gallery shows the normalized "Score"
("Similarity" for raw scores) with the raw text and image similarity of that crop in small
text. A cache row that is broken (labels and vectors do not match, scores not finite) is
logged as `CACHE ERROR` and skipped (`framescout_scoring.photo_scores`), and `spread`
ignores non-finite values. Scores depend on the folder searched; they are relative search
heuristics, not probabilities or guaranteed identification. Scoring needs no cache change:
it runs on the cached features at query time.

### Feature cache

Feature rows are stored in `results/cache.sqlite3` per resolved file path + engine/config
signature (`framescout_core.feature_signature`: the engine id of the search model, whether
person detection is on and, only if it is, the detector settings; pinned by golden values
of every model in `tests/test_signature.py`), checked against modification nanoseconds and size. Image
embeddings are serialized in float16; profile queries can reuse existing image features.
Changes to detector settings invalidate the cached feature signature. The engine id comes
from `ENGINE_TEMPLATE` (`v5-clip-{model}-{pretrained}-crop-features-1`, `engine_id(model)`;
`ENGINE = engine_id(DEFAULT_MODEL)`, the same string as before E22, so no default-model
cache row was invalidated): change the template whenever cached embeddings become
incompatible for all models (preprocessing, crops); another model or other weights is a new
`MODELS` entry and gets its own id and signature. Each model therefore has its own rows
next to the others (about 10–15 MB per model for 5,000 photos); switching back reuses
them. The engine creates the tables with `framescout_core.prepare_cache(..., model=)`,
which also records its signature with `engine_id(model)` and the settings in the side table `signatures(signature PK,
engine, settings)` (E11; the features table is unchanged, so older versions read the same
file). Rows of other signatures are never deleted automatically, only by "Clean up
storage" after the user's selection (E7, E11).

### Outputs and thumbnail cleanup

Outputs one ranked `.html` file per profile (`<slug>.html` from
`framescout_core.profile_slugs`: ASCII transliteration, `-2`, `-3`, … on collisions in
profile order, hash fallback), with separate JPEG thumbnails in `results/thumbnails/` and
`file://` links to originals. Keep the output folder intact; exporting an HTML file on its
own does **not** embed thumbnails. After `results.json` is written, still holding the run
lock, the engine calls `auto_cleanup`: it removes temporary thumbnails
(`<hash>.jpg.<random>.jpg`, left by a stop during the export, E13) and thumbnails (both
folders, `[0-9a-f]{24}.jpg` names only) that neither `results.json` nor any HTML file in
the output folder links; if one of them cannot be read, every thumbnail stays; a failure
is logged and never fails the run. Local paths may not work on another computer.

### Result file

After the galleries the engine writes `results/results.json`
(`framescout_core.write_results`, format 2 since A25): run start and end, the searched
photo folders (`photo_folders`, a list), settings (including `model`, the search model key
since E22; results without it count as the default, `results_model`, which the app's
results caption shows as "search model <label>"; results of another model than the one
chosen now get a note), number of photos and per profile its
name, `search_fingerprint` (hash of its search texts and reference paths, relative to the
profiles file's folder when inside it, so a moved project folder changes nothing),
gallery file name, `normalized` and the cards (rank, path, `relative` (the `photo_name`
the gallery shows), crop label, score, raw text/visual similarity, the two caption lines,
thumbnail name) in gallery order. `read_results` also reads format 1 (`photo_folder`, a
string) and returns it with `photo_folders` as a list of one (none for an empty value);
app versions before A25 reject format 2 ("not a FrameScout result file of format 1") and
show no results until they run a search themselves. Written only when the export completes, so a stopped
search leaves the previous file (galleries already rewritten: E24). The app reads it
(cached by mtime and size) instead of deriving file names from the current profile list
(A12). The gallery's "Open" uses `os.startfile` and only for an existing file with an
`EXT` suffix (`openable_photo`), "Folder" `SHOpenFolderAndSelectItems` via ctypes on
Windows (`explorer /select,` did not select a file with a comma in its name),
`open`/`xdg-open` elsewhere (untested, A19); they act on the computer the app runs on.

### Supported inputs

Supported inputs: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF, recursively. The engine excludes
the output folder if nested in the input root.

## Profiles schema
```json
{
  "profiles": [
    {
      "name": "Red car",
      "franchise": "Vehicles",
      "features": "red bodywork, four wheels",
      "reference_images": [],
      "prompts": []
    }
  ]
}
```
`franchise` is a legacy internal field name; in the UI it means optional **Context /
origin** (in English, E3), not necessarily a media franchise. Reference paths are
interpreted relative to the profile JSON file directory. `app.py` uploads references into
`references/<slug>/`, or `<slug>-2`, `-3`, … if that folder holds references of another
profile (`framescout_core.reference_folder`, A1). The folder follows the profile name
(user decision): on a rename, `app.py` gives the profile's own files under `references/` a
hard link (or copy) in the new folder, saves `profiles.json` with the new paths, rewrites
the moved paths in `profiles.json.bak` (`update_backup_references`, so restoring the
backup keeps working) and only then removes the old names and an emptied old folder; a
failed save removes only the new names, a failed backup rewrite keeps the old names. Files
of other profiles, leftovers, missing files and paths outside `references/` are never
moved; otherwise existing reference paths are left as they are. Uploads are named
`reference-<n>` with the next free number and never overwrite an existing file. Never
silently delete or overwrite user profiles/references. There is also a legacy CLI option
`--character`; consider backward compatibility before renaming it.

## Current UI / runtime details

### Settings (`settings.json`)

Settings are kept in `settings.json` in the project folder (gitignored, A8): the app reads
it on every rerun (so a reload, a restart, another tab or session, also during a running
search, shows them; a read failing while another session replaces the file is retried) and
saves the values changed in a page run, merged into the current file
(`framescout_core.save_settings`). The settings widgets have keys (`setting_<name>`) and
get the saved values through `st.session_state`; never pass them `value=`/`index=`, which
gives a widget a new identity after every save and drops the next change (PR #10 review).
Profile forms (A13): `app.py` reads `profiles.json` with `read_profiles_versioned` on every
rerun and keeps the version that the forms of the last complete run showed in
`st.session_state.profiles_shown` (set after the forms are drawn; an interrupted run keeps
the older version, so a save is refused, not lost). `store()` saves with
`expected=profiles_shown` and, on success, keeps the version `save_profiles` returns as
`profiles_shown`, so the session's own next save is never refused, also if the following
run is interrupted before the forms. On `ProfilesChangedError` it increments
`st.session_state.saves` (new keys for the edit forms: the form at the same place may now
show another profile, which must not get the edited profile's uploads or ticked "Remove"
checkbox), stores "Your changes were not saved" in `st.session_state.profile_error` and
reruns; the message is shown at the top of the profile tab (not in the form's expander,
which a changed profile name redraws closed), the new-profile form keeps its input.
Checked once with Streamlit's `AppTest` (refused save after another writer deleted a
profile above the edited one). A click on a form that no longer exists after
another session shortened the list is dropped by Streamlit without a message (A31).

`framescout_core.reconcile_settings` does the sync on every page run with two session
records: `settings_seen` (the saved value last taken from or written to the file, as
written, e.g. rounded) and `settings_shown` (the value the widget showed; they differ for
slider noise and for the device substitute). A widget that differs from `settings_shown`
was changed in this session and is saved; a saved value that differs from `settings_seen`
came from another session and is shown, so the latest action wins. A Start in a page run
that took over such values is refused once with a note. `save_settings` holds a `RunLock`
on `settings.json.lock` around its read-merge-write (sessions are threads of one process).
The widgets take their ranges from `SETTING_RANGES`; `system_info` (which imports torch)
runs in the AI settings tab, so the profile tab is drawn first. A read that still fails
with an `OSError` (file in use) gets a different message than a corrupt file
(`ValueError`). Only values that differ from the defaults are written, so the default
photo folder follows a moved project folder; unknown keys are kept. Keys follow the CLI
options; defaults (`default_settings`): `photo_folders` `[BASE/photos]` (a list of
strings, saved without empty or blank entries; an empty list is allowed and disables
the Start button; A25), `device`
`auto|cpu|cuda` ("cuda" is offered only if `torch.cuda.is_available()`, A7; a saved device
PyTorch cannot use is shown and used as "auto" but stays saved until another one or "Use
auto from now on" is chosen), `batch_size` 8, `top` 150, `person_detection` on,
`max_persons` 12, `person_confidence` .30, `reference_weight` 0.3
(`DEFAULT_REFERENCE_WEIGHT`; 0.35 before PR #11, a saved value is not migrated), `model`
(a registry key, `DEFAULT_MODEL`; not written when it is the default; a free-text name or a
key removed from the registry falls back to the default with the usual warning, E22).
`read_settings` checks each value against the range of its widget (an invalid one falls
back to its default with a warning, `save_settings` removes it with the next save; floats
are rounded, as sliders return values like 0.30000000000000004); an unreadable file is
never replaced (like `profiles.json`, A2) and the page keeps the settings it shows. The
single `photo_folder` (`LEGACY_PHOTO_FOLDER`) of versions before A25 is read as
`photo_folders`, a list of one (`photo_folders` wins if both are saved; a value that is not
a string is reported like an invalid value), and every save replaces it by
`photo_folders` (dropped if equal to the default); it is never written again. Older app
versions ignore `photo_folders` as an unknown key and use their default folder. The
copy target folders of A17 are kept in the same file under `copy_folders` ({profile name:
folder}, only folders that differ from the default), saved with `save_copy_folder` under
the same lock (`_update_locked`, shared with `save_settings`) and ignored by
`read_settings`.

### Marks and copying

Marks and copying (A17, user decisions 2026-10-25): `results/marks.json` (`{"format": 1,
"profiles": {name: {photo path: "match"|"no-match"}}}`; "open" is the absence of a mark)
is keyed by profile name and the photo path of `results.json` (absolute) and kept
across searches. `save_marks` merges a change into the current file under a `RunLock` on
`marks.json.lock` and replaces it atomically; an unreadable file is never replaced and the
app then shows no marks. The file is user data in the results folder: the engine never
writes it, and the cleanup never deletes the file (`NEVER_DELETED`); it removes single marks of
unbound photos only when the user selects that category (E8, `remove_marks`: under the
same marks lock as `save_marks`, a profile left without marks is dropped, an unreadable
file is never replaced). A21 (marks follow the absolute path) is closed as won't do: a
renamed or moved photo counts as a new photo, its old mark stays until cleaned up. The control on each
card is an `st.segmented_control` whose session state is set from the file before it is
drawn on every run of the gallery fragment (no `default=`), so the file is the truth also
for other tabs; its `on_change` saves. A rename in the profile tab calls `rename_marks`
and `rename_copy_folder` after the profile was saved (`carry_over`); galleries of profiles
that are no longer search profiles cannot be marked and their "Copy to folder" field is
disabled. A gallery drawn before its profile was renamed or deleted (another tab) still
has live controls, so the callbacks `set_mark`/`set_copy_folder` pass
`profiles_file=PROFILES` to `save_marks`/`save_copy_folder`: under their lock,
`require_profile` raises `UnknownProfileError` (a `ValueError`) for a name that is not in
`profiles.json` now, nothing is written and the gallery shows the message (the typed
folder is not kept for the session either). A rename or deletion saves `profiles.json`
first and then changes these files under the same locks, so a save in between is moved
or deleted with them (review of A22, A33). Rename and deletion run their two changes
through `change_name_data` and add a note with `add_notice`. Deleting a profile is a
two-step action (A22, user decisions 2026-10-27): "Delete profile" stores
`st.session_state.delete_pending = (name, saves)` and reruns at once (so a question still
open for a profile above is not drawn in the same run), then shows a warning below the
form (`deletion_consequences`: the number of marks with the match/no-match split or why
they cannot be deleted; the saved copy folder entry and a folder typed in this session
but not saved (`copy_folders_unsaved`) go, the folder and the copies stay; reference
images stay, since `profiles.json.bak` still names them) with "Delete for good" (disabled
while a search runs) and "Cancel"; any save since the click (also a refused one) or the
profile's disappearance ends the question. The warning is drawn into a container after
the buttons are handled, and the number of marks it names is kept in
`st.session_state.delete_marks_named`, so a click compares with the number the user saw.
After the deletion was saved, `forget_profile` calls `delete_marks` (under the marks lock;
returns how many it deleted; an unreadable file raises `ValueError` and is never
replaced) and `forget_copy_folder` (under the settings lock; writes nothing without an
entry) and drops the session's unsaved copy folder of that name; a different number of
deleted marks (marked or unmarked since the question was shown) and a part that fails
are named in the notice at the top of the profile tab. `marks.json` stays in
`NEVER_DELETED`. Marks that profiles deleted before A22 left behind stay (A34); marks of
photos that no longer exist at their path are removed only on request by the cleanup
category `marks_unbound` (`remove_marks`, see "Storage cleanup").
`marks.json` and the copy folders are read through `st.cache_data`, keyed by path, mtime,
size and file id (`version_key`). Copying (`copy_photos`): flat into the target,
`shutil.copy2` via a temporary file published with `_publish_new` (never replaces a file),
the same name and content under any `name (n).ext` counts as already there (`filecmp`),
otherwise the next free name (a taken name, also a dangling link, is skipped; at most
`COPY_MAX_NAMES`); `copy_target` refuses an empty or relative path, a file, and a folder
inside a photo folder of the shown search, of the current setting or the folder of a
photo to copy. The copy runs in the page run (not a callback) with a progress bar, so a reload
or another click stops it between photos. The default target is
`<Pictures>\FrameScout\<gallery slug>` (Pictures from `SHGetKnownFolderPath`, `~/Pictures`
elsewhere). Using marks as search feedback: A20.

### Storage cleanup

Cleanup (E7, E11, E13, E23, A14, E8; user decisions at the PR #18 hold point): the expander
"Clean up storage" at the end of the "Search & results" tab. "Scan" (disabled while a
search runs) calls `scan_cleanup(RESULTS, PROFILES, REFS, signature
of the current settings, `current_model=`)` and keeps the result in the session; each category of
`CLEANUP_CATEGORIES` is a checkbox (key `cleanup_<category>`, set from `CLEANUP_DEFAULTS`
at the scan, no `value=`) with count and size, or a caption with the reason it is not
offered. Categories: `temp_thumbnails`; `galleries` (`*.html` in `results/` with
`GALLERY_MARKER` in its first 4 KB, neither listed in `results.json` nor `profile_slugs`
of the current profiles; other HTML files are kept; its `thumbnails` are the thumbnails
only orphaned galleries link, deleted with them); `thumbnails` (linked by neither
`results.json` nor any HTML file, both thumbnail folders); `cache_missing` (UI label "Cache entries of unbound photos", default on; the internal
key kept its name: every cache row whose photo no longer exists at its path, in any folder
searched so far, E8; rows whose photo still exists are not offered, a path that is not
absolute is never gone; its `names` are the folders with their photo counts, fullest
first, so that e.g. the folders of an earlier disk whose drive letter another disk got are
seen before the deletion, A35); `marks_unbound` ("Marks of unbound photos", **default off**, after
`cache_missing` in `CLEANUP_CATEGORIES`; items are `(profile, photo path)` pairs, names
`"profile: path"`; it is one category checkbox, marks are not chosen one by one; not
offered with "Not offered: marks.json cannot be read (...)" if the file is unreadable);
`cache_old` and
`cache_other` and `cache_models` (`classify_signatures(..., current_engine=)`: the side
table decides, otherwise `known_signatures`, i.e. the signatures of the default engine id
of every `max_persons` and every
slider value of `person_confidence` (each step and its float neighbors up to
`SLIDER_NOISE_ULPS` = 8 ULPs either way, so slider noise of any arithmetic path counts)
with `DEFAULT_YOLO_MODEL`, plus the no-detection signature; the current signature is never
offered). `cache_models` ("Cache entries of other search models", default off, E22) holds
rows whose recorded engine is that of another registered model, and unrecorded
`known_signatures` rows when another model is current (those can only be the default's);
The existence check is `cleanup._PathCheck` (standard library only), shared by the
cache rows and the marks in **one** pass: one probe per drive or share root
(`os.path.splitdrive(path)[0] + os.sep`, `os.path.isdir`), all roots in parallel daemon
threads under one shared timeout `ROOT_TIMEOUT` = 5 s (`_reachable_roots`; a root whose
probe of an earlier call still hangs gets no second thread, that probe is waited for
again, `_PROBES`); a root that is
not reachable or does not answer in time is **not checked** (its photos are neither gone
nor offered) and each category gets a note per root ("<root> is not reachable now ... N
photos there were not checked"). Photos are grouped by folder (`_gone_in`): a folder with
more than `_STAT_UP_TO` = 4 photos is listed once (`os.listdir`, names compared
normcased); of the names missing from the listing the first 4 are confirmed by a `stat`,
and only if one of them exists (e.g. another Unicode normalization) every missing name
gets its own `stat`; a folder with at most 4 photos gets one `stat` per photo; a folder
that does not exist makes all its photos gone; a folder that cannot be listed (e.g. no
permission) keeps them. After the pass the gone photos are checked once more (a share
that dropped during the pass and is back shows them again), then their roots are probed
again, and a root that is still offline makes its photos count as not checked. Measured on Windows 11 with 30,000 files in 100 folders: stat
0.12-0.21 s vs listing 0.08-0.11 s locally; through the share `\\localhost\C$` (SMB) 13.8 s vs
0.19 s. `scan_cleanup(results, profiles_file, refs_root, current_signature, *,
current_model, progress=None)` has no photo folder parameter any more and calls
`progress(done, total)` per folder (about 100 calls at most; the app draws "Checking which
photos still exist ... n of m folders"); `clean_up(results, shown, selected, vacuum,
alive, profiles_file, refs_root, current_signature, lock_timeout=..., *, current_model)`
re-checks only the rows and marks the shown scan listed, with a `_PathCheck` of its own
in each of the two steps (an answer of the cache step, which can include `VACUUM`, may be
out of date), the photos before the marks lock is taken; its summary has a `marks` count.
`scan_cleanup` and `clean_up` require `current_model` (keyword-only: the signature, a
hash, does not tell the model), `CACHE_CATEGORIES` lists the cache categories. Before E22
rows of any other engine counted as `cache_old` (selected), and an older FrameScout still
does so with the rows of the optional models (documented in the README);
`references` (`EXT` files in `references/` that neither `profiles.json` nor
`profiles.json.bak` names). `galleries`/`thumbnails` are not offered if `results.json` (a
missing one counts as empty) or `profiles.json` (also missing) cannot be read,
`references` if `profiles.json` or the `.bak` cannot be read; an unreadable cache blocks
the cache categories. The cache is read with a read-only URI with an empty authority
(`_read_only_uri`; never created; `Path.as_uri()` would fail for a UNC path). A scan reads
`profiles.json` once and every gallery once (its marker and links). "Delete selected" asks
for a confirmation; `clean_up` takes `results/run.lock` (1 s; refused if held, or if a
`starting` status names a live engine, `engine_alive`), scans again under the lock and
deletes only items that the shown scan lists and the fresh scan still has: galleries first
(with the thumbnails only they showed), then thumbnails computed from the links of the
galleries left on disk (read once), cache rows in one transaction and an optional
`VACUUM`, unbound marks (`remove_marks`; a failure goes to "Marks were kept: ..."), then references (profiles read again) with emptied folders below `references/`;
an emptied `vorschaubilder/` is removed. `_remove_file` refuses every name of
`NEVER_DELETED` as a guard. All deletes are permanent (no Recycle Bin). Each step
(temporary thumbnails, galleries and thumbnails, cache rows, marks, references) ends on its own
`OSError`/`ValueError`/`sqlite3.Error`, which goes to `skipped`, so the summary always
counts what was deleted; `delete_storage` also catches what `clean_up` raises. The summary
(`cleanup_summary_text`: files, cache entries, marks, freed bytes, a note when rows were deleted
without `VACUUM`, failures, skipped steps) is shown after a rerun; a Start drops the scan,
and so does a change of what it was classified for (`cleanup_inputs`: the current
signature and the search model; the photo folders are not part of it any more, so editing
the folder list keeps the scan), with the note "The AI settings changed since the scan.
Scan again."; the scan runs only on the "Scan" click, never on a rerun or a search.
No migration: a renamed or moved photo is analyzed again as a new photo, and its old
cache row and mark stay until the user cleans them up (user decision 2026-10-28, E8).
Open: E37 (a hanging folder listing or `stat` is not guarded by a timeout), A35 (a drive
letter now used by another disk, or on POSIX the root `/` of an unmounted mount, counts as
reachable; only mitigated by naming the folders).
While `clean_up` holds the lock it registers the results folder in the process
(`cleanup_running`; app sessions are threads of one process), so other tabs show "The
storage is being cleaned up" instead of a running search and disable Stop (A23); other
temporary files: E26.

### Run state (lock and status file)

Run state (A4/A5): the engine holds an operating-system lock on `<output>/run.lock`
(`framescout_core.RunLock`: Windows byte-range lock, `flock` elsewhere; the OS releases it
when the process ends in any way, also after `kill()`) and writes
`<output>/run-status.json` (`StatusReporter`: format, pid, phase
`scanning`/`loading`/`analyzing`/`scoring`/`exporting` →
`finished`/`failed`/`interrupted`, done/total of the phase, new/cached/errors, exit code,
message; atomic, at most one write a second, best effort). It takes the lock after the
cheap argument checks (after `import torch`), waiting up to five seconds; if another
search holds it, it exits with code 3 (`EXIT_BUSY`). Photo folders none of which exists
are an error before the lock only if the output folder does not exist yet (no folder is
created for a mistyped call); otherwise it is reported in the status file. A missing
folder of several is left out with a log line (A25). The final phase comes from
the exit code (`final_status`: 0 finished, 130 interrupted, others failed).

### Starting a search from the app

The frontend spawns the engine via `subprocess.Popen` and redirects stdout/stderr to
`run.log`, with `PYTHONIOENCODING=utf-8` (`cache_env`), as it reads `run.log` as UTF-8;
it passes `--model` from the setting `model` (the AI settings tab starts with
the "Search model" selectbox, key `setting_model`, `format_func=model_label`, with a
caption per model and a warning from `model_problem`, E22; with such a problem Start is
disabled and the run tab shows the same warning). `start_run` takes the run lock (1 s timeout: every open tab probes it every two
seconds), truncates `run.log`, spawns the engine and writes the status `starting` with the
child's pid, then releases the lock to the engine; if that status cannot be written it
ends the child again. A start while the lock is held, or while a `starting` status names a
live engine process, is refused. "Running" is derived on every rerun and every two seconds
(fragment) from the lock and the status file (`run_active`, read once per page run;
`engine_alive` checks via `psutil` that the pid's command line contains
`framescout_engine.py` and that the process existed when the status was written,
`started_in_time`, so a reused pid does not count), not from the session's process handle,
so a reload, another tab or session shows the run and can stop it; the fragment reruns the
page when the state changes. On Windows the venv's `python.exe` is a launcher: `Popen.pid`
is the launcher, the pid in the status file the engine (its child); killing the launcher
also ends the engine (verified).

### Stopping a search

Stop (`stop_run`) reads the status again, terminates the session's process and the status
file's engine with their child processes (`psutil`), kills what is left after five seconds
and then waits up to ten seconds for the lock (Windows may release it a moment after the
process ended) and marks the status `interrupted` / "Stopped in the app." if its pid is
one of the ended processes (otherwise another start has replaced it); if it cannot, the
app says so. Each embedded group of photos (at most `--batch-size` crops, unless one photo
has more) is committed to SQLite, so a stop loses at most the group in progress. A
`KeyboardInterrupt` in the CLI cancels the queued decoding and exits with code 130. Not a
background job manager: the engine is a child of the Streamlit process, and closing the
`Start-FrameScout.bat` window is not tested with a running search.

### Hardware info

Hardware info is detected dynamically via `platform`, `os`, `psutil` and `torch.cuda`;
`auto` chooses CUDA if PyTorch detects it, otherwise CPU. Do not hardcode the CPU/GPU
model or the user's RAM. A GPU may exist without CUDA support; the app tells a CPU build
of PyTorch (`torch.version.cuda is None`) from a CUDA build that finds no usable GPU (e.g.
a driver too old for it); the hint says to close FrameScout, run `Install-FrameScout.bat
cuda` and start it again, since the running app keeps the loaded torch and the cached
`system_info`.

### Environment variables and caches

The Windows batch scripts set cache/temp environment variables under the project directory
(`TORCH_HOME`, `HF_HOME`, `YOLO_CONFIG_DIR`, `XDG_CACHE_HOME`, `TMP`, `TEMP`), aiming for
easy cleanup. Some dependencies may still leave user-level caches (e.g. Ultralytics writes
`%APPDATA%\Ultralytics\settings.json` when imported without `YOLO_CONFIG_DIR`, I10; the
uninstall script lists these folders but never deletes them); do
not promise perfect portability or no residual files.

**Ultralytics without analytics and run-time installs (E27, E28):** the engine imports
Ultralytics only through `framescout_core.import_detector_class` (a test checks there is
no direct import in `framescout_engine.py`), which first sets `ULTRALYTICS_ENV` in
`os.environ`, overriding values a user set, because Ultralytics reads them on import:
- `YOLO_OFFLINE=true` makes its `ONLINE` flag false, which turns off its usage analytics
  (`ultralytics/utils/events.py`: an anonymous event per prediction to Google Analytics
  while its setting `sync` is on, the default), its Sentry reports and PyPI update checks.
  Model downloads (`yolo11n.pt` on first use) do not check the flag and still work. The
  setting `sync` itself stays as it is: changing it would write Ultralytics' settings
  file, which is `%APPDATA%\Ultralytics\settings.json` for a manual run without
  `YOLO_CONFIG_DIR` and may be shared with other Ultralytics uses.
- `YOLO_AUTOINSTALL=false` stops `check_requirements` from pip-installing missing
  packages into the venv.
- Importing Ultralytics replaces `PIL.Image.open` for the whole process
  (`ultralytics/utils/patches.py`) with a version that installs and registers `pi-heif`
  for the first file Pillow cannot identify. `import_detector_class` puts the original
  back (also when the import fails): the engine hands the detector decoded images and
  registers `pillow-heif` itself, and a broken photo now fails with Pillow's own error
  with and without person detection.

Checked with Ultralytics 8.4.183 (a probe: `ONLINE`/`AUTOINSTALL` false, analytics
`events.enabled` false, `Image.open` restored, a broken `.jpg` raises
`UnidentifiedImageError` without importing `pi_heif`; plus a CPU smoke run with person
detection). The first-run weight download was not run (a download), but for the review a
probe with `safe_download` replaced by a recorder showed that with `ONLINE` false a
missing `yolo11n.pt` still reaches the download
(`attempt_download_asset` → `safe_download(.../releases/download/v8.4.0/yolo11n.pt)`;
neither checks `ONLINE`), and that `Image.open` is still the original after `YOLO()` and a
prediction (Ultralytics patches it once, when `ultralytics/utils/patches.py` is first
imported, which happens on `import ultralytics`). The variables stay set for the rest of
the engine process; the engine starts no subprocesses that would inherit them. A later Ultralytics version may rename these switches; check them when
raising its minimum version.

## Test coverage and known quirks

### Test coverage

Add focused tests without requiring full model downloads. Profile loading, reading/saving
the app's `profiles.json` and `settings.json`, reference folders, prompt generation, slug
handling, progress lines (A11), the run lock and status file (A4/A5), thumbnails of the
export (E6), the cache signature, the pipeline helpers for batching/prefetching (E2), the
scoring (E4/E5) the result file with the gallery helpers (A12) the marks, copying and copy
target folders (A17) with their deletion with a profile and no saves for a name that is no
profile (A22, A33, `test_marks.py`, `test_copy.py`, `require_profile` in
`test_profile_file.py`), the versioned read and checked, locked save of `profiles.json` (A13,
`test_profile_file.py`), the cleanup with the cache side table (E7, E11,
`test_cleanup.py` also for unbound rows and marks, unreachable roots simulated by patching
`_probe_root` and a real unused drive letter, the listing/stat choice, a share that drops and is back, the reused hanging probe and the per-step re-check of `clean_up`, E8;
`test_cache_signatures.py`, with real SQLite files) and the photo scan
with RAW+JPEG pairs, skipped files and the RAW preview decisions (E25, `test_photos.py`),
the several photo folders (A25: dedup, labels, joined scans, the `nargs='+'` of the engine
read from its syntax tree, settings migration, results format 1/2) are
covered by `tests/` (via `framescout_core` and `framescout_scoring`), as are the search
model registry, the per-model signatures and cleanup category and the `model` setting
(E22, `test_models.py`; the engine's `--model`, its `stdout.reconfigure` and the app's
`PYTHONIOENCODING` only from their syntax trees, `test_engine_defaults.py`; the app's
selectbox, its disabled Start, the results note and the dropped cleanup scan are not
unit-tested), and the evaluation tooling (E32: `test_evaluation.py` for the formats, AP@k
and the pool; `test_eval_tool.py` for the tool's commands, metrics and labelling server
with fake scores; the engine's `--scores-file` only from its syntax tree in
`test_engine_defaults.py`; no real-model run, no browser test), and the pinned
dependencies (I12, `test_constraints.py`: every line of `constraints.txt` is an exact pin
without local label, hash or duplicate, sorted by name; every requirement of
`requirements.txt` and the pinned numpy of `requirements-dev.txt` has an allowed pin; a
non-comment pip line of the installer passes `-r requirements.txt -c constraints.txt`, and
it sets `PIP_CONSTRAINT=constraints.txt` between the venv and `install_torch.py` (I18);
the torch pins of both files equal `TORCH_VERSION`/`TORCHVISION_VERSION` in
`test_torch_install.py`; completeness of the transitive pins is not checkable in CI), and
the installer (P5 part C, `test_installer.py`, text checks of `Install-FrameScout.bat`:
pins equal `framescout_core.portable_python`, the full package of python.org, no installed
Python needed, SHA-256 checked before extraction and use, `PSModulePath` cleared only for
that check, extracted in `.tmp` and moved as a whole with retries, a working `.venv` kept
without a download, a broken one checked again and else created again with `--clear`, a
failed `venv` removed, an existing `.python` checked for `venv`/`ensurepip` and the pinned
version (the check itself runs on the test Python), no delayed expansion, folder path
never inside a block; the real download, extraction and `venv` creation and the folder
`Fo!to (old)\fs` were run by hand under `.tmp`, as were the repair paths of the review
(`python.exe` of `.python` deleted, pip removed from `.venv`, a failed `venv`, `Lib\venv`
removed from `.python`, the folder renamed, the move blocked by an open file for 7 s and
for 25 s); a full install with PyTorch on the private Python was not), and the uninstall script (P5, `test_uninstall.py`, tests on `tmp_path` trees: plan, kept
entries (also in another case, Windows only), protected folders from settings (invalid
values, read once, photo folder around the project), links and junctions, read-only
files and folders, unlistable items, failures reported once, user-data and outside
listings, the run lock, read-only vs. running `python.exe` (Windows only), the dialog of
`framescout_uninstall.py`, no delayed expansion in the `.bat`; the real `.bat` was run by
hand on scratch copies, once with `!` and `)` in the folder path as a dry run, not
against a real installation, not while Streamlit was running and not on a PC without the
`py` launcher; the private Python's deletion (`running_python`, exit code 3, the `.bat`
removing `.python`) was run by hand under `.tmp` with the real private Python, not against a
full installation; the running check was tried by hand with a running read-only executable);
still missing: cache
reuse and the engine's decoding itself (`open_image`/`open_raw` need Pillow, pillow-heif
and rawpy, which CI does not install). Add a small integration smoke test for real models when feasible.

### Known quirks

Potential current quirks to investigate rather than assume solved (most are tracked in
`BACKLOG.md`): "Clean up storage" was checked with `AppTest` only (not in a browser), and
`auto_cleanup` in one CPU smoke run with synthetic photos under `.tmp/`; marks follow the
absolute photo path, a renamed or moved photo counts as new (A21 closed as won't do, E8); the app saves its whole profile list, so a save based on a
file that another session changed in between is refused and has to be made again (A13);
the engine still takes an empty folder
argument as its working directory (the app no longer passes one, A16); result file downloads do not contain thumbnails (ZIP export: P4
(C), A18); `app.py` itself has no automated tests (A4/A5 were checked once with
Streamlit's `AppTest` and real engine runs, and manually in a browser: start, reload,
second tab, Stop – successful, user report 2026-10-21; closing the `Start-FrameScout.bat`
window during a run is still not tested; A8's settings widgets were checked with `AppTest`
and in headless Edge driven over the DevTools protocol – `AppTest` alone is not enough
evidence for widget behavior, as it does not run the browser frontend; the marks and
copying of A17 and the deletion confirmation of A22 were checked with `AppTest` only (not
yet in a browser); the result gallery
of P4 (A) was checked with `AppTest` and in headless Edge, and its "Open"/"Folder" buttons
once on Windows 11 with synthetic photos under `.tmp/`); Python 3.14 has been verified for
one CPU run only; absolute paths/HTML link portability. The UI's dynamic system
information is informational, not a hardware benchmark.

## Workflow permissions
`.claude/settings.json` pre-approves the routine git/gh/pytest commands of this workflow.
Pushes are pre-approved only as `git push [-u] origin <type>/…`; a bare `git push`, `gh pr
merge`, force/reset variants of `git branch`/`git switch`, bulk staging (`git add -A`/`.`,
`git commit -a`, anything naming `profiles.json` or `settings.json`) and engine smoke runs
ask; force pushes, `--mirror`/`--all`/`--delete`, pushes naming `main` and `git reset
--hard` are denied. Rules are evaluated deny → ask → allow and match the command text with
`*` wildcards; they steer the agent but are **not** a security boundary (`git -C . push`,
`sh -c …` or an absolute path to `git` are not matched, and `main` cannot be
branch-protected on the current GitHub plan, see I8). Personal overrides go into
`.claude/settings.local.json` (gitignored).
