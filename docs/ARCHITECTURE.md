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
app production-ready.

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
removes temporary and unreferenced thumbnails (`auto_cleanup`, E7/E13).

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
  `read_profiles`/`save_profiles` (the app's `profiles.json`: same validation, v3
  conversion, atomic save with `profiles.json.bak`, A2).
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
- `signature.py`: `CLIP_MODEL`/`CLIP_PRETRAINED`/`ENGINE`/`feature_signature` (CLIP model
  choice and the feature cache signature, E1),
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
- `marks.py`: `MARKS_FILE`/`MARK_STATES`/`read_marks`/`save_marks`/`rename_marks` (the
  user's marks, A17).
- `copying.py`:
  `COPY_FOLDERS_KEY`/`default_copy_folder`/`copy_target`/`copy_photos`/`copy_summary_text`/`read_copy_folders`/`save_copy_folder`/`rename_copy_folder`
  (copying marked matches and their saved target folders in `settings.json`, A17).
- `cleanup.py`:
  `THUMBNAILS_DIR`/`LEGACY_THUMBNAILS_DIR`/`GALLERY_MARKER`/`CLEANUP_CATEGORIES`/`CLEANUP_DEFAULTS`/`NEVER_DELETED`/`scan_cleanup`/`clean_up`/`auto_cleanup`/`cleanup_running`/`size_text`/`count_text`/`cleanup_summary_text`
  (the storage cleanup, E7/E11/E13/E23/A14).
- `_common.py` (internal, not re-exported): helpers several areas share, i.e. atomic
  writes (`_publish_via_temp`, `_publish_new`, `_replace_atomically`,
  `_replace_with_retry`), reading a JSON object file with retries (`_read_json_object`),
  the locked read-change-write of a JSON file (`_update_locked`) and `_path_key`.

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

### `tests/`, `pytest.ini`, `requirements-dev.txt`

`tests/`, `pytest.ini`, `requirements-dev.txt`: pytest suite for `framescout_core/`,
`framescout_scoring` and `install_torch.py` (no torch, no model download); dev
dependencies `pytest` and `numpy` (for `framescout_scoring`, user decision in PR #11). One
test (`test_signature.py`, QuickGELU config check, E1) also reads open_clip's config
tables where open_clip is installed and is skipped in CI.

### `profiles.example.json` and `profiles.json`

`profiles.example.json`: shipped, general-purpose English example profiles (I5).
`profiles.json`: the user's working profile list, **gitignored**; `app.py` creates it from
the example on the first start with `framescout_core.create_from_example`, which never
replaces an existing file. Every app save keeps the previous file as `profiles.json.bak`
(one generation, gitignored); a file the app cannot read stops the app instead of being
saved over (A2). Back it up before overwriting user changes.

### `requirements.txt`

`requirements.txt`: `torch==2.14.1` and `torchvision==0.29.1` pinned (same values as
`framescout_core.TORCH_VERSION`/`TORCHVISION_VERSION`, checked by a test; change them
together); Streamlit `>=1.40` (A10); numpy, Pillow, open_clip_torch, ultralytics and
psutil with the versions of the verified runs as minimum, no upper bounds (user decision;
untested newer majors: I12). `pillow-heif` and `rawpy` (E25, required by user decision;
optional extras: E29) have the versions of the venv's smoke runs (PR #26) as minimum. Full
locking is P5.

### `Install-FrameScout.bat`

`Install-FrameScout.bat [cpu|cuda]`: checks installed Python 3.14/3.13/3.12 (in that
order), creates project-local `.venv`, installs PyTorch with `install_torch.py` (passing
the argument on), then the requirements, performs imports and prints the PyTorch build and
whether CUDA is available.

### `install_torch.py`

`install_torch.py [cpu|cuda] [--dry-run]`: installs the pinned PyTorch from the PyTorch
index (dependencies also from PyPI) – the CPU build or the CUDA build that
`framescout_core.cuda_build` picks from `nvidia-smi` (`cu130`, otherwise `cu126`; a build
for every GPU, else for the most capable one). Without an argument an installed CUDA build
is kept and nothing is asked; otherwise it asks for GPU support only if `nvidia-smi` finds
an NVIDIA driver. If no CUDA build fits, an installed CUDA build is kept, otherwise the
CPU build is installed; **only an explicit `cpu` replaces a CUDA build** (PR #8 review). A
matching installed build is not downloaded again. Exit code 0 done, 1 failed. Standard
library only.

### `Start-FrameScout.bat`

`Start-FrameScout.bat`: launches app via that venv on `127.0.0.1:8501`.

### `README.md`

`README.md`: English user guide (GitHub start page).

### `BACKLOG.md`

`BACKLOG.md`: known weaknesses (IDs E/A/I) and the prioritized roadmap that drives the PR
workflow.

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
`.venv/`, `yolo11n.pt`.

## Current search pipeline

### Model and prompts

Uses OpenCLIP `ViT-B-32-quickgelu`, `pretrained='openai'` (`framescout_core.CLIP_MODEL`;
the OpenAI weights need QuickGELU, plain `ViT-B-32` would run them with GELU, E1), for
normalized text and image embeddings. No LLM is required. Four generic English prompt
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
current list; the cleanup takes the distinct resolved list (see "Storage cleanup").
Checked in PR #28 with one CPU engine smoke run on synthetic photos under `.tmp/` (two
folders of the same name, a nested and a missing one; one folder; none existing; output
equal to a folder; after the review folders between options and a folder inside the
output folder) and the app with Streamlit's `AppTest` (old `settings.json`, format 1
`results.json`, editing the list, the cleanup scan with a missing folder listed twice),
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
signature (`framescout_core.feature_signature`: `ENGINE`, whether person detection is on
and, only if it is, the detector settings; pinned by golden values in
`tests/test_signature.py`), checked against modification nanoseconds and size. Image
embeddings are serialized in float16; profile queries can reuse existing image features.
Changes to detector settings invalidate the cached feature signature; bump `ENGINE`
whenever cached embeddings become incompatible (model, weights, preprocessing, crops). The
engine creates the tables with `framescout_core.prepare_cache`, which also records its
signature with `ENGINE` and the settings in the side table `signatures(signature PK,
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
photo folders (`photo_folders`, a list), settings, number of photos and per profile its
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
(`DEFAULT_REFERENCE_WEIGHT`; 0.35 before PR #11, a saved value is not migrated).
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
is keyed by profile name and the photo path of `results.json` (absolute, A21) and kept
across searches. `save_marks` merges a change into the current file under a `RunLock` on
`marks.json.lock` and replaces it atomically; an unreadable file is never replaced and the
app then shows no marks. The file is user data in the results folder: the engine never
writes it, and a future cleanup (E7/E11/A14) must never delete it. The control on each
card is an `st.segmented_control` whose session state is set from the file before it is
drawn on every run of the gallery fragment (no `default=`), so the file is the truth also
for other tabs; its `on_change` saves. A rename in the profile tab calls `rename_marks`
and `rename_copy_folder` after the profile was saved (`carry_over`); galleries of profiles
that are no longer search profiles cannot be marked, so no marks are written under an old
name; a deleted profile's marks stay and pass to a later profile of the same name (A22).
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

Cleanup (E7, E11, E13, E23, A14; user decisions at the PR #18 hold point): the expander
"Clean up storage" at the end of the "Search & results" tab. "Scan" (disabled while a
search runs) calls `scan_cleanup(RESULTS, PROFILES, REFS, photo folders (a list), signature
of the current settings)` and keeps the result in the session; each category of
`CLEANUP_CATEGORIES` is a checkbox (key `cleanup_<category>`, set from `CLEANUP_DEFAULTS`
at the scan, no `value=`) with count and size, or a caption with the reason it is not
offered. Categories: `temp_thumbnails`; `galleries` (`*.html` in `results/` with
`GALLERY_MARKER` in its first 4 KB, neither listed in `results.json` nor `profile_slugs`
of the current profiles; other HTML files are kept; its `thumbnails` are the thumbnails
only orphaned galleries link, deleted with them); `thumbnails` (linked by neither
`results.json` nor any HTML file, both thumbnail folders); `cache_missing` (rows whose
path is inside one of the current photo folders that exist, compared normcased, and
certainly does not exist, each path checked once; a listed folder that does not exist is
left out with a note in the category's `notes`, shown as a caption, and its rows are never
offered (A25); not offered without an existing photo folder); `cache_old` and
`cache_other` (`classify_signatures`: the side table decides, otherwise
`known_signatures`, i.e. the current-`ENGINE` signatures of every `max_persons` and every
slider value of `person_confidence` (each step and its float neighbors up to
`SLIDER_NOISE_ULPS` = 8 ULPs either way, so slider noise of any arithmetic path counts)
with `DEFAULT_YOLO_MODEL`, plus the no-detection signature; the current signature is never
offered); `references` (`EXT` files in `references/` that neither `profiles.json` nor
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
`VACUUM`, then references (profiles read again) with emptied folders below `references/`;
an emptied `vorschaubilder/` is removed. `_remove_file` refuses every name of
`NEVER_DELETED` as a guard. All deletes are permanent (no Recycle Bin). Each step
(temporary thumbnails, galleries and thumbnails, cache rows, references) ends on its own
`OSError`/`ValueError`/`sqlite3.Error`, which goes to `skipped`, so the summary always
counts what was deleted; `delete_storage` also catches what `clean_up` raises. The summary
(`cleanup_summary_text`: files, cache entries, freed bytes, a note when rows were deleted
without `VACUUM`, failures, skipped steps) is shown after a rerun; a Start drops the scan.
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
`run.log`. `start_run` takes the run lock (1 s timeout: every open tab probes it every two
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
`%APPDATA%\Ultralytics\settings.json` when imported without `YOLO_CONFIG_DIR`, I10); do
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
target folders (A17), the cleanup with the cache side table (E7, E11,
`test_cleanup.py`, `test_cache_signatures.py`, with real SQLite files) and the photo scan
with RAW+JPEG pairs, skipped files and the RAW preview decisions (E25, `test_photos.py`),
the several photo folders (A25: dedup, labels, joined scans, the `nargs='+'` of the engine
read from its syntax tree, settings migration, results format 1/2, cleanup per folder) are
covered by `tests/` (via `framescout_core` and `framescout_scoring`); still missing: cache
reuse and the engine's decoding itself (`open_image`/`open_raw` need Pillow, pillow-heif
and rawpy, which CI does not install). Add a small integration smoke test for real models when feasible.

### Known quirks

Potential current quirks to investigate rather than assume solved (most are tracked in
`BACKLOG.md`): "Clean up storage" was checked with `AppTest` only (not in a browser), and
`auto_cleanup` in one CPU smoke run with synthetic photos under `.tmp/`; marks follow the
absolute photo path (A21); the app saves its whole profile list, so edits by another
session in between are overwritten (A13); the engine still takes an empty folder
argument as its working directory (the app no longer passes one, A16); result file downloads do not contain thumbnails (ZIP export: P4
(C), A18); `app.py` itself has no automated tests (A4/A5 were checked once with
Streamlit's `AppTest` and real engine runs, and manually in a browser: start, reload,
second tab, Stop – successful, user report 2026-10-21; closing the `Start-FrameScout.bat`
window during a run is still not tested; A8's settings widgets were checked with `AppTest`
and in headless Edge driven over the DevTools protocol – `AppTest` alone is not enough
evidence for widget behavior, as it does not run the browser frontend; the marks and
copying of A17 were checked with `AppTest` only (not yet in a browser); the result gallery
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
