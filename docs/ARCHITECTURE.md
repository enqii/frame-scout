# FrameScout — architecture

What the code cannot say by itself: the shape of the system, the search pipeline, the data
formats, the invariants that are easy to break and what has actually been run. Function-level
behavior lives in the docstrings (search the code, e.g. `grep -rn "def name" framescout_core`),
the list of tests is `tests/` (one file per area), the commands are in `docs/DEVELOPMENT.md`
and the rules in `CLAUDE.md`. Review-round details and old PR reports are in the git history
and the PR descriptions (`docs/BACKLOG-DONE.md` links them); this file keeps only what is
true now. Keep it current when a data format, an invariant or the verified status changes.

## Verified status

Treat syntax checks, unit tests and a real model run as distinct kinds of evidence. Do not
call the app production-ready.

**Run for real**
- One full CPU-only search on Windows (I6): 4,997 photos, 6 profiles, CLIP on CPU, YOLO person
  detection, 0 errors, Python 3.14, torch 2.14.1+cpu.
- CUDA on one home PC (RTX 4070, torch 2.14.1+cu130, Python 3.14; I11, PR #56): CLIP and YOLO on
  CUDA, `--device auto`, the app's device choice (headless Edge), 400 synthetic and 4,997 real
  photos on CUDA and CPU (348 s CUDA with person detection, 486 s CPU, 93 s CUDA without
  detection; person detection is the GPU bottleneck, E18).
- All four registered search models on CPU (E22, synthetic photos) and on CUDA (E34).
- The evaluation tool (E32/E20, E34/E35) with real models, 4,997 photos and about 1,600 labels
  made in the user's browser; the labelling page was driven by CDP input in headless Edge.
- Offline loading of a cached model with the network blocked (E16/E31/E33, default model and
  SigLIP).
- Publishing the export (E24/E26) in one CPU smoke run; RAW, HEIC and RAW+JPEG pairs in CPU
  smoke runs (PR #26).
- Installer download of the private Python (P5 part C) and the uninstall, both under `.tmp`.
- The four `.sh` scripts (F47) in WSL2 (Ubuntu, x86_64) in a folder with blanks, `!`, `&` and
  parentheses, with a stand-in `install_torch.py`: the Python download with its checksum (and a
  wrong one), `.venv`, a repaired `.python`, the check, the start up to the missing Streamlit, the
  uninstall with its exit code 3; and the test suite with that private Python.
- Stop, reload and a second browser tab during a search (A4/A5), once by hand.
- The app with Streamlit `AppTest` (settings, profile forms, marks, cleanup, quick search,
  find similar) and in headless Edge (settings widgets, gallery, mark colors A49).

**Not runtime-tested**
- A fresh `Install-FrameScout.bat` with PyTorch on it, `cuda`/`cu126` installs, other or several
  GPUs, other Python versions, macOS, a second machine; on Linux CUDA and the uninstall (F48;
  one full CPU search through the app ran in WSL2 on 2026-11-16: 4997 photos, no errors).
- The first download of a model into an empty cache and the fallback after an incomplete cache
  (E38); the time estimate (F12) of a live search; "Find similar" (F11) with real CLIP vectors
  and in a real browser; an export stopped during its writes; closing the
  `Start-FrameScout.bat` window during a search; the unbound-photo check with a real
  disconnected drive or unmounted share (I44); HEIC from a real phone; RAW files without a usable preview.
- The search quality of the three optional models (none is evaluated beyond the first AP@40
  values, E32).

CI (`.github/workflows/tests.yml`, Windows, Python 3.14 only, I50) runs `pytest` and a
`compileall` check from `requirements/requirements-dev.txt` only and fails if torch is
installed: tests must not need torch, Pillow or model downloads. Tests that need Pillow
(`tests/test_images.py`) or Streamlit's frontend bundle run only locally. `app.py` and
`framescout_ui/` have no behavior tests, only source checks (`tests/test_app_source.py`,
`tests/app_source.py`); widget behavior needs `AppTest` plus a real browser (`AppTest` does
not run the frontend and cannot see CSS).

## Layout

| Area | Files | Notes |
|---|---|---|
| Frontend | `app.py`, `framescout_ui/` | Streamlit; `app.py` is page layout, the areas live in `framescout_ui/` (imported only by `app.py`) |
| Engine | `framescout_engine.py`, `framescout_images.py` | CLI; models, decoding, person detection, cache, ranking, export; `framescout_images` is Pillow/HEIC/RAW decoding and thumbnails (no torch) |
| Shared logic | `framescout_core/` | one module per area, imported from the defining module (`__init__.py` is empty, I45); **standard library only** |
| Scoring | `framescout_scoring/` | one file, `__init__.py` (a package, not a module, so that a leftover package folder of an older version cannot shadow it); **numpy only** |
| Evaluation | `framescout_eval.py`, `assets/framescout_eval_page.html` | labelling and AP@k measurement of the search models |
| Install and run | `Install-FrameScout.bat`, `install_torch.py`, `Start-FrameScout.bat`, `framescout_start.py`, `Check-FrameScout.bat`, `framescout_check.py`, `Uninstall-FrameScout.bat`, `framescout_uninstall.py`; the `.sh` scripts of the same names on Linux | see "Install, start, uninstall" |
| Data | `requirements/`, `assets/profiles.example.json` | pins, examples |
| Workflow | `.claude/skills/`, `.claude/settings.json`, `.github/` | see "Workflow permissions" |

Frontend and engine are separate processes: the app spawns the engine with
`framescout_core.settings.engine_command`, redirects its output to `run.log` and only reads files the
engine writes. Only the engine imports torch (`system_info` in the Settings tab is the app's
one exception).

Each version ships one `framescout-version-<X.Y.0>.txt` in the root (I42; the triage PR names it
after the release the user chose for the round). A ZIP extracted over another version's folder leaves both files:
`Install-FrameScout.bat` and `Start-FrameScout.bat` stop before any Python runs when they find
more than one, and the installation check reports it ("Program files"); the message names the
user data to copy into the new folder. Known limits: the name changes once per release round,
so a release and the snapshots of `main` until the next release carry the same file and are not
told apart. The `.bat` files skip a hidden version file, the check counts it. Versions before
I42 have neither the file nor the check. After an update over such a folder its leftover
files stay (harmless: a package wins over a leftover `framescout_core.py`/`framescout_scoring.py`
of the same name, and a leftover `framescout_scoring/ranking.py` from before I45 is an old copy
that nothing imports), and going back to such a version over a newer folder is not detected.

The engine and the evaluation tool import open_clip and Ultralytics only through
`framescout_core.hub.import_open_clip` / `import_detector_class` (tests check there is no direct
import), because both set environment variables that must precede the import (see
"Environment variables, caches and offline loading").

## Search pipeline

### Models and prompts

The search model comes from the registry `framescout_core.models.MODELS` (engine option `--model`,
setting `model`). The default `vit-b-32-openai` is OpenCLIP `ViT-B-32-quickgelu` with the
OpenAI weights (plain `ViT-B-32` would run them with GELU, E1). Optional and **not
evaluated**: `vit-b-16-datacomp`, `vit-l-14-datacomp`, `vit-b-16-siglip` (needs
`transformers` for its tokenizer; `model_problem` checks this before the scan). Defaults such as
the reference weight are tuned for the default model; scores of different models are not
comparable. Per profile, four generic English templates are derived from name and context,
two more from `features`, and user `prompts` are appended. Search terms are **English only**
(E3, user decision): hint text only; no language check, warning or translation without a new
user decision (a multilingual model is E21, a hold point).

### Photo folders and formats

- A search covers a list of photo folders (A25). `distinct_folders` drops duplicates and
  folders inside another listed folder (by normalized path and file identity); missing folders
  are left out with a log line, it is an error only if none exists. An output folder equal to
  or containing a photo folder is an error. `scan_each_folder` walks each real folder once by
  identity (links into walked folders and loops add nothing; A28/A29), de-duplicates hard
  links and file symlinks, and leaves out the output folder wherever it is reached. A photo is
  named in galleries and `results.json` by `photo_name` (folder label plus relative path).
  Cache rows and marks are keyed by the absolute path.
- Extensions come from `EXT`; Pillow reads JPEG, PNG, WebP, BMP, TIFF, AVIF, `pillow-heif` adds
  HEIC/HEIF and `rawpy` camera RAW. `available_decoders` imports all three; the extensions of a
  missing decoder are skipped (named in the log and in the app's photo source tab).
- RAW (E25): the embedded preview if its longer edge is at least `RAW_PREVIEW_MIN_EDGE` (1024),
  else a half-size sensor decode. A RAW file next to a same-named `.jpg/.jpeg/.heic/.heif`
  partner is skipped; if the partner cannot be analyzed, `RawFallback` analyzes the RAW file in
  its place (E30). A truncated JPEG partner counts as failed when a RAW file exists (strict
  decode, E46/E53/E57); truncated HEIF/AVIF always fail strictly (E59). Details are in the
  docstrings of `framescout_images` and `RawFallback`.
- Changing the RAW decoding needs an `ENGINE_TEMPLATE` bump (it changes embeddings).
- Cache damage (E50): an error of the cache file itself while opening or storing stops the
  search (exit 1, `cache_error_message`, nothing partial published); an unreadable row only
  leaves out that photo and the finished search ends with `cache_read_warning`. The app offers
  "Check cache" (read-only `quick_check`) and "Set cache aside" (rename, never delete).

### Person detection

Optional Ultralytics `yolo11n.pt` (`classes=[0]`) adds person crops **in addition to the full
image**; it is optional because it is meaningless for non-person motifs. It runs on the CLIP
device, one photo per call under a lock. The detector is created lazily (`Lazy`, F2) on the
first photo that needs analysis, so a fully cached repeat search never loads YOLO. Weights are
found by `yolo_weights`/`find_yolo_weights` (E9, E41: a bare name in the working folder, then
`YOLO_CONFIG_DIR`; an older `yolo11n.pt` in the project folder is moved into the cache folder
once). Person boxes differ slightly between CUDA and CPU (I11, 9253 vs 9249 crops on 4,997
photos); the cache signature ignores the device on purpose, so a cache built on one device is
reused on the other. This is not a bug.

### Analysis

Uncached photos are decoded, searched for persons and preprocessed in threads (`DECODE_THREADS`
4, `DETECTION_DECODE_THREADS` 2 with detection; `framescout_core.pipeline.prefetch` bounds the photos in
memory), the crops of several photos are embedded in one forward pass of at most `--batch-size`
crops (`group_batches`), and each group is committed to SQLite in one transaction
(`store_group`; a failing group is stored photo by photo so only a failing photo counts as an
error). A stop loses at most the group in progress; `KeyboardInterrupt` exits with 130.
Without person detection JPEGs are decoded at reduced scale down to twice the CLIP input size
(`draft_size`), which is part of the cache signature (`DRAFT_DECODING`). `--analyze-only` (F18)
ends after this phase and writes nothing but the cache. The cache is opened right after the
device setup, before the model loads, so a damaged cache is reported at once (E56).

### Scoring

`framescout_scoring` (E4/E5), on the cached features at query time (no cache change). The
generated templates of a profile are averaged into one normalized query; each custom prompt
stays a query of its own, and a crop's text score is its best cosine over these queries (user
decision, PR #11). With reference images the visual score is the maximum over the reference
vectors. Per profile and run the text and visual scores are z-scored separately over all crops
of the searched photos and combined as `(1-w)*z_text + w*z_visual` (`DEFAULT_REFERENCE_WEIGHT`
0.3, also the engine's `--reference-weight` default). With fewer than `MIN_SCORES` (10) crops or
a spread below `MIN_SPREAD` the raw cosines are used ("Similarity" instead of "Score"). The best
crop represents its photo. A broken cache row is logged as `CACHE ERROR` and skipped. Scores
depend on the folder searched and are relative search heuristics, never probabilities or
identification.

### Feature cache

`results/cache.sqlite3`, one row per resolved file path and signature, checked against
modification nanoseconds and size; embeddings are float16. The signature
(`framescout_core.signature.feature_signature`) is made from the engine id of the model, whether person
detection is on and, only then, the detector settings (`max_persons`, `person_confidence`,
`--yolo-model`; open: E64) or, without detection, `DRAFT_DECODING`. Golden values for every model
are pinned in `tests/test_signature.py`.

- `ENGINE_TEMPLATE` (`v5-clip-{model}-{pretrained}-crop-features-1`): change it whenever cached
  embeddings become incompatible for all models (preprocessing, crops). Another model or other
  weights is a new `MODELS` entry with its own `engine_id`. The default model's id is unchanged
  since before E22.
- Each model has its own rows next to the others (about 10–15 MB per 5,000 photos).
- The side table `signatures(signature PK, engine, settings)` (E11) records what each signature
  means so "Clean up storage" can tell old settings from other models. The features table is
  unchanged, so older versions read the same file.
- Rows of other signatures are **never deleted automatically**, only by the user's cleanup (E7/E11).
  A renamed or moved photo is a new photo; its old row and mark stay until cleaned up (E8).

### Outputs

One ranked gallery `<slug>.html` per profile (`profile_slugs`: ASCII transliteration, `-2`, `-3` on
collisions), JPEG thumbnails in `results/thumbnails/` (older runs: `results/vorschaubilder/`, no
longer written) and `file://` links to the originals. A photo whose thumbnail fails is skipped and
lower ranks fill up to `--top`, so ranks are contiguous (E6/E12). An exported HTML file alone
embeds no thumbnails: keep the output folder intact.

**Publishing (E24):** the engine keeps the galleries in memory and calls
`publish_export(output, pages, document)`: every file is written in full to
`<name>.<random>.tmp` (fsync) and only then renamed, `results.json` last; a failing rename
restores the previous content. A stop or failure while writing leaves the previous galleries and
`results.json`. A kill between the renames can still leave galleries newer than `results.json`
(E45).

**Auto cleanup:** after publishing, still under the run lock, `auto_cleanup` removes stale
temporary files (random 8-char suffix, at least `STALE_TEMP_AGE` = 60 s old by the results
folder's file-system clock; the list is `cleanup._TEMP_FILE`) and thumbnails that neither
`results.json` nor any HTML in the output folder links (nothing is removed if one of them cannot
be read). A failure is logged and never fails the run. `results/quick/` has its own cleanup after
a quick search and is not touched by the cleanup of `results/`.

### Result file (`results/results.json`, format 2 since A25)

Run start and end, `photo_folders` (list), settings (including `model`; absent means the default),
the photo count, and per profile: name, `search_fingerprint` (hash of the search texts and
reference paths, relative to the profiles file's folder when inside it), gallery file name,
`normalized`, optional `queries` (F17), and the cards in gallery order (rank, absolute `path`,
`relative` name, crop label, score, raw text and visual similarity, caption lines, thumbnail name,
optional `best_query`). Optional keys are additive: the format stays 2 and older apps ignore them
(A25 rule). `read_results` also reads format 1 (single `photo_folder`); app versions before A25
reject format 2. The app reads the file (cached by mtime and size) instead of deriving names from
the current profile list (A12).

The quick search (F10, and "Find similar", F11) writes its own set to `results/quick/`
(`quick.html`, `results.json` of format 2 plus a `quick` key, `thumbnails/`) and never touches the
profile galleries, `results/results.json` or `marks.json`; its scores are scaled over the photos
searched and differ from a search with profiles.

## Data formats and user files

All of these are user data: never replace an unreadable file, never commit them.

### `profiles.json`

```json
{"profiles": [{"name": "Red car", "franchise": "Vehicles",
               "features": "red bodywork, four wheels", "reference_images": [], "prompts": []}]}
```

`franchise` is a legacy field name for the optional **Context / origin** (the CLI option
`--character` is legacy too: keep backward compatibility). Reference paths are relative to the
profile file's folder. The file is gitignored; the app creates it from `assets/profiles.example.json`
with `create_from_example`, which never overwrites. Every save keeps the previous file as
`profiles.json.bak` (one generation; more: A30) under `profiles.json.lock`. The app reads it
with its version on every rerun and a save is refused (`ProfilesChangedError`) if the file
changed since the page showed it (A13); the page then warns (A31). An unreadable file stops the
app (A2). Uploaded references go to `references/<slug>/` (`reference_folder`, A1), are named
`reference-<n>` and never overwrite; a profile rename gives its files a hard link or copy in the
new folder, saves the profile, rewrites the backup (`update_backup_references`) and only then
removes the old names.

### `settings.json` (A8)

In the project folder, gitignored. Only values that differ from the defaults are written
(`default_settings`; the default photo folder therefore follows a moved project); unknown keys
are kept; keys follow the CLI options: `photo_folders` (list; the legacy single `photo_folder` is
read as a list of one and never written again), `device` (`auto|cpu|cuda`), `batch_size`,
`low_priority`, `top`, `person_detection`, `max_persons`, `person_confidence`,
`reference_weight`, `model`, and `copy_folders` ({profile name: folder}, A17). `read_settings`
checks every value against its widget range and falls back to the default with a warning; an
unreadable file is never replaced. Saves merge into the current file under
`settings.json.lock`.

Sync (`reconcile_settings`): the widgets (keys `setting_<name>`, filled through
`st.session_state`, **never `value=`/`index=`**, PR #10) are compared with two session records,
`settings_seen` (last value taken from or written to the file) and `settings_shown` (what the
widget showed). A widget that differs from `settings_shown` was changed here and is saved; a
saved value that differs from `settings_seen` came from another session and is shown, so the
latest action wins. "Reset to defaults" (A26) goes through the same mechanism.

### `results/marks.json` (A17)

`{"format": 1, "profiles": {name: {absolute photo path: "match"|"no-match"}}}`; "open" is no
entry. Keyed by profile name and the photo path of `results.json`, kept across searches. The
engine never writes it and the cleanup never deletes it (`NEVER_DELETED`). Writers merge under
`marks.json.lock` and replace atomically; every write first copies the previous valid content to
`marks.json.bak` (F1, one generation). `restore_marks` keeps a damaged file as
`marks.json.broken-<date>` and restores the backup, only on the user's click. Marks of unbound
photos or of deleted profiles are removed only by the cleanup categories the user ticks.
`require_profile` refuses a mark or copy-folder save for a name that is no longer in
`profiles.json` (A33); rename and deletion of a profile move or delete its marks and copy folder
under the same locks after `profiles.json` was saved (A22). Copying (`copy_photos`) is flat,
never replaces a file and refuses targets inside a photo folder. The mark colors rely on
Streamlit internals (`MARK_STYLE_STREAMLIT`: `tests/test_marks.py` fails when
`requirements/constraints.txt` pins another Streamlit; re-check the selectors then).

### `results/` contents

`cache.sqlite3`, `thumbnails/`, `quick/`, `results.json`, galleries, `marks.json*`, `exports/`
(F5 result lists: user data, no cleanup category touches it), `run.lock`, `run-status.json`,
`*.broken-*` (damaged files set aside, deleted only by the cleanup category `broken_files`). In
the project folder: `settings.json`, `profiles.json`, `photos/`, `references/`, `run.log`,
`.cache/`, `.tmp/` (including `.tmp/eval/` of the evaluation tool), `.venv/`, `.python/`.
`NEVER_DELETED` lists the files of the results folder that no cleanup may remove (e.g.
`marks.json`, its `.bak` and lock files, `profiles.json.lock`).

### Run lock and status file (A4/A5)

The engine holds an OS lock on `<output>/run.lock` (`RunLock`: Windows byte-range lock, `flock`
elsewhere; released by the OS when the process ends in any way) and writes
`<output>/run-status.json` (`StatusReporter`: format 1, pid, phase `scanning`, `loading`,
`analyzing`, `scoring`, `exporting`, then `finished`/`failed`/`interrupted`, done/total, counts,
exit code, message; atomic, at most one write a second, best effort). It takes the lock after
the cheap argument checks and exits with code 3 (`EXIT_BUSY`) if another search holds it for five
seconds. Additive fields keep `STATUS_FORMAT` 1 and older apps ignore them: `analyze_only` (F18),
`rate`, `throughput`, `thumbnails`, `finishing` (F12/F16).

"Running" is derived on every rerun and every two seconds from the lock and the status file, not
from the session's process handle, so a reload, another tab or another session shows the run and
can stop it. `start_run` takes the lock, truncates `run.log`, spawns the engine, writes the
`starting` status with the child's pid and releases the lock to the engine; a start while the
lock is held or a `starting` status names a live engine (`engine_alive`: `psutil` command line
and process creation time) is refused. On Windows the venv's `python.exe` is a launcher:
`Popen.pid` is the launcher, the pid in the status file the engine. Stop (`stop_run`) terminates
both process trees, kills what is left after five seconds, waits for the lock and marks the status
`interrupted`. The cleanup holds the same lock (`clean_up`, `check_cache`), so it is refused
during a search and the app shows "The storage is being cleaned up" meanwhile (A23).

## Storage cleanup

"Clean up storage" (Settings tab; E7/E11/E8, A14, A34, A35, A40) is the only code that deletes
cache rows, marks, references and galleries. All deletes are permanent. Rules to keep:

- The user scans first; `clean_up` takes `run.lock`, scans again under the lock and deletes only
  items the shown scan listed and the fresh scan still has. A change of the AI settings or the
  model drops the shown scan.
- Categories (`CLEANUP_CATEGORIES`): temporary thumbnails, orphaned galleries (identified by
  `GALLERY_MARKER`; other HTML stays), unlinked thumbnails, cache rows of old settings, other
  settings and other models, references no profile uses, and the opt-in ones (default off):
  cache rows and marks of unbound photos, marks of deleted profiles, damaged files set aside.
  `results/quick/` and `results/exports/` are in no category.
- "Unbound" means the photo no longer exists at its path, anywhere. The existence check
  (`cleanup._PathCheck`, simple rule since I44) probes each drive or share root once in a thread
  with a timeout (`ROOT_TIMEOUT`). A photo is checked by one `stat` only if its root answers and
  its folder exists and is not empty. Every other photo is **not checked**: it is neither gone nor
  offered, and one note counts these photos. Known limits: a renamed, deleted or emptied folder
  looks like an unmounted drive, so its photos are never offered (the note's way out: put any file
  into the folder and scan again). A share that hangs during the scan stalls it until the OS gives
  up, and a large folder on a slow share costs one `stat` per photo. A drive letter reused by
  another disk counts as reachable, and so does an unmounted POSIX mount point that still holds
  any entry, or that another disk is mounted on (A35, open); the scan therefore names folders with
  counts.
- Categories that need an unreadable file (`results.json`, `profiles.json`, `marks.json`, the
  cache) are not offered with the reason. `_remove_file` refuses every `NEVER_DELETED` name.
  Each step ends on its own error and goes to the summary's `skipped`.
- The app's own temporary files in the project folder are removed once per start
  (`project_temp_cleanup`, E44).

## Install, start, uninstall

- **Install** (`Install-FrameScout.bat [cpu|cuda]`): downloads python.org's full package of the
  pinned Python (`framescout_core/portable_python.py` holds version, URL and SHA-256; the `.bat`
  holds the same values and `tests/test_installer.py` keeps them in sync), checks the hash,
  extracts it to `.python\` and creates `.venv` with it. An existing working `.venv` is kept. The
  venv refers to `.python` by absolute path, so the folder cannot be moved afterwards. It then
  installs PyTorch with `install_torch.py` and the other packages with `-c
  requirements\constraints.txt` (relative, because pip splits `PIP_CONSTRAINT` at whitespace). The
  script uses no delayed expansion and no folder path inside parentheses (I21). `install_torch.py`
  keeps an installed CUDA build unless `cpu` is given explicitly, checks free disk space first
  (F3; exit code 3 = stopped by the user) and uses the standard library only.
- **Pins:** `requirements/requirements.txt` has ranges without upper bounds, `torch`/`torchvision`
  pinned to `framescout_core.torch_build.TORCH_VERSION`/`TORCHVISION_VERSION` (a test checks both files).
  `requirements/constraints.txt` (I12) pins the whole dependency closure of the verified venv
  (sorted, no hashes, torch without a local label so `+cpu`/`+cu*` builds all satisfy it); only the
  installer uses it. Refreshing is manual, in a PR of its own (the file header explains the dry-run
  check); `tests/test_constraints.py` keeps it consistent.
- **Start** (`Start-FrameScout.bat` → `framescout_start.py` → `framescout_core.app_instance.launch`): sets the
  cache variables, runs Streamlit **in its own process** so the app-instance lock
  (`.tmp/app-instance.lock`, an OS lock, never a pid) lives exactly as long as the app. A second
  start of the same folder opens the browser on the running app's port (`.tmp/app-instance.json`).
  Port 8501, else the next free up to 8510 (`port_free` makes the same bind Streamlit makes). Gap:
  an app started by hand holds no lock (F26).
- **Check** (`Check-FrameScout.bat`, F15): read-only; exit 0 no problem, 2 problems found, anything
  else means it could not run.
- **Uninstall** (`Uninstall-FrameScout.bat [--dry-run]`, on Linux `.sh`, P5 part B): runs with the private
  `.python` (not with `.venv`'s Python, which cannot delete itself; without `.python` it only
  names the folders to delete by hand), refuses while a search runs, the app holds its start lock
  or `settings.json` is unreadable, lists what it deletes and what it keeps (`USER_DATA`: photos,
  references, results with marks, profiles and backup, settings, `run.log`, `.tmp/eval`), and
  deletes after the answer `yes`. Caches outside the folder are neither listed nor deleted. A
  program running without these locks is not detected beforehand (I44): deleting goes on, a
  file it holds open (Windows) or a read-only file ends in the failure list, the rest of
  that folder is already gone (exit code 1, the private Python stays for another try). Exit
  code 3: everything deleted except the private Python the script runs with; the `.bat`
  removes it last. Program files themselves are not deleted.
- **Linux** (F47): `Install-`, `Start-`, `Check-` and `Uninstall-FrameScout.sh` (bash, LF
  endings by `.gitattributes`, mode 100755 in git) do what their `.bat` files do, with the same
  exit codes; `tests/test_linux_scripts.py` checks the shared lines and runs them on Linux.
  The private Python is python-build-standalone's `install_only_stripped` build of the same
  version for x86_64 glibc Linux (`LINUX_PYTHON_URL`/`LINUX_PYTHON_SHA256` in
  `framescout_core/portable_python.py`, checksum from the release's `SHA256SUMS`); its
  interpreter is `.python/bin/python3`, the environment's `.venv/bin/python`. Temporary files go
  to `TMPDIR=.tmp`. Differences: no `pause`, no retry of the move (no virus scanner holds the
  files), the architecture and `curl` are checked before an old `.python` is deleted, and only
  exit code 3 of `install_torch.py` means low disk space (a signal kill exits with 128 + n).
  Known limits: x86_64 with glibc only; in a folder installed on the other system, the installer
  replaces its `.python` and `.venv` without a warning; a browser that `framescout_start.py`
  starts inherits `XDG_CACHE_HOME`/`TMPDIR` (as on Windows `TMP`/`TEMP`). The Python code
  names the script of the system (`framescout_core.paths.script`: `.bat` on Windows, `.sh`
  elsewhere; `paths.WINDOWS` is the one platform test of these decisions) and shows paths in
  the system's form; `CUDA_BUILDS` holds a Windows and a Linux driver minimum per build, and
  WSL (a kernel release with `microsoft`) uses the Windows ones, since its nvidia-smi reports the
  Windows host's driver (`reports_windows_driver`; not verified on a GPU, F48); the uninstall
  deletes `.venv/bin/python` and `.python/bin/python3` first and tells a running app only by
  its start lock (`app_running`, on Windows too; a lock that only looks held gets the start
  script's way out, `stale_lock_hint`): Linux deletes files in use, so a Python of the
  environment running without that lock is not reported at all; the check takes a `home` of `.python/bin` for the private Python `.python`.

## Environment variables, caches and offline loading

- The `.bat` files (and the `.sh` scripts, with `TMPDIR` for `TMP`/`TEMP`) set `TORCH_HOME`, `HF_HOME`, `YOLO_CONFIG_DIR`, `XDG_CACHE_HOME` (only if not
  defined: a user's value wins and the models are then downloaded there, A36) and `TMP`/`TEMP`/
  `PIP_CACHE_DIR` under the project folder, for an easy cleanup. A user's `XDG_CACHE_HOME` alone
  keeps `TORCH_HOME` and `HF_HOME` unset (torch and huggingface_hub derive them from it). The
  engine fills unset ones itself as the first statement of `main()` (`default_cache_env`, E9/I10,
  E42), the app's `cache_env` and `engine_cache_env` build the same environment. A worktree
  engine therefore uses the worktree's own `.cache/`: smoke runs point the variables at the main
  checkout's `.cache/` to avoid a download.
- Do not promise perfect portability or no residual files: some dependencies may write
  user-level caches (the uninstall neither lists nor deletes them). Open: E39 (open_clip's URL
  download ignores the variables), I25 (`framescout_eval.py` builds its own paths).
- **Ultralytics (E27/E28):** `import_detector_class` sets `YOLO_OFFLINE=true` (turns off its
  analytics, Sentry and update checks; model downloads still work) and `YOLO_AUTOINSTALL=false`
  (no run-time pip installs) before the import, overriding a user's values, and restores the
  original `PIL.Image.open` that Ultralytics replaces. Check these switches when raising the
  Ultralytics minimum version.
- **Hub requests (E16/E31/E33):** `import_open_clip` sets `HF_HUB_DISABLE_SYMLINKS_WARNING` and
  `HF_HUB_DISABLE_TELEMETRY` (with `setdefault`) and `HF_HUB_OFFLINE=1` when `model_cached` finds
  every Hub file of the model in the cache (unless the user set an offline variable), so a cached
  model starts without Hub requests. If an offline load fails because a file is missing
  (`hub_file_error`), `load_with_hub_fallback` goes online and loads again; any other error is
  raised as it is. The variables stay set for the rest of the engine process.
- Hardware info is detected dynamically (`platform`, `psutil`, `torch.cuda`); `auto` is CUDA if
  PyTorch finds it, else CPU. Never hardcode a CPU, GPU or RAM size. The app tells a CPU build
  of PyTorch from a CUDA build that finds no usable GPU.
- Low priority (F4) is applied by the engine itself (`--low-priority`), not by the app, so manual
  CLI runs behave the same; its effect is not measured (E52).

## Model evaluation tool

`framescout_eval.py {run,pool,label,metrics}` (E32/E20) measures the search models on the user's
own labelled photos. Collection folder `<project>/.tmp/eval/<collection>/` (gitignored):
`collection.json` (photo folders and profiles file), `engine/<model>/` (one engine output per
model so one run's cleanup never removes another's), `scores/<model>.json`, `pool.json`,
`labels.json`, `thumbnails/`.

- `labels.json`: `{"format": 1, "labels": {profile: {absolute photo path: true|false}}}` plus the
  optional `motifs` (E36: the profile's context, features and references when its first label was
  set; `pool` and `metrics` warn when the profile's motif has changed since). An unreadable file
  is never saved over. Labels are keyed by profile name and path, so they survive prompt edits.
- Scores file (engine `--scores-file`, format 1): per photo and crop text and visual scores
  rounded to `SCORE_DIGITS`; finite numbers only.
- `run` calls the engine once per model (cache variables under `--cache-dir`, default
  `default_cache_dir()`, E48); a model with a missing package is skipped; exit 1 if any model was
  not scored. `pool` ranks each model's scores with the engine's `rank_photos` at several
  reference weights and renders thumbnails (Pillow only, E49). `label` serves the labelling page
  on `127.0.0.1:8765` behind a random token (`LabelServer`, every route; a port in use is an error)
  and saves each label atomically at once. `metrics` computes AP@`--k` (default 40) per profile and
  model, optionally a reference-weight sweep, and warns about labels no model run scored.
- `framescout_eval.py run` warns about low disk space like the app (E51) but never blocks.

## Workflow permissions

`.claude/settings.json` pre-approves the routine git/gh/pytest commands of the PR workflow
(`CLAUDE.md` → "PR workflow"). Pushes are pre-approved only as `git push [-u] origin <type>/…`; a
bare `git push`, `gh pr merge`, bulk staging (`git add -A`/`.`, `git commit -a`, anything naming
`profiles.json` or `settings.json`) and engine smoke runs ask; force pushes,
`--mirror`/`--all`/`--delete`, pushes naming `main` and `git reset --hard` are denied. Rules are
evaluated deny, ask, allow and match the command text with `*` wildcards; they steer the agent but
are **not** a security boundary (`git -C . push`, `sh -c …` or an absolute path to `git` are not
matched). Personal overrides go into `.claude/settings.local.json` (gitignored).

On GitHub (I8) the ruleset `protect main` blocks deleting and force-pushing the default branch,
needs linear history and a pull request (rebase merges only, no approval required) and the
`pytest (Windows, Python 3.14)` check (the job name in `tests.yml`, built from the matrix label
`Windows`: renaming the job or that label means changing the ruleset by hand too); the
`pytest (Linux, Python 3.14)` check (F47) is not required by the ruleset, so GitHub would merge
with it red, but the PR workflow merges only with all checks green. Admins may bypass it only when merging a pull request
(`gh pr merge --admin`, denied in `.claude/settings.json`), never with a direct push. Actions are
limited to GitHub-owned actions pinned to a SHA, and workflows of outside contributors' pull
requests need approval. Secret scanning with push protection, Dependabot alerts and private
vulnerability reporting are on.

## Known quirks

- Person crops and the ranking of near-ties differ slightly between CUDA and CPU (see "Person
  detection"); the cache is shared on purpose.
- Marks follow the absolute photo path; a renamed or moved photo counts as new (A21 closed as won't
  do, E8).
- The app saves its whole profile list, so a save based on a file another session changed is
  refused and has to be made again (A13).
- The engine still takes an empty folder argument as its working directory (the app does not pass
  one, A16). HTML files exported alone contain no thumbnails (ZIP export: A18).
- Absolute paths in galleries and links work only on the computer that made them.
- Python 3.14 has been verified for one CPU run (and the CUDA runs above) only.
- The system information in the UI is informational, not a hardware benchmark.
