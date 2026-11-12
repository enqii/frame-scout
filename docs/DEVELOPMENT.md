# Developing FrameScout

How to run FrameScout by hand, test it and evaluate the search models. The internals
(pipeline, cache, scoring, file formats) are in [ARCHITECTURE.md](ARCHITECTURE.md); the
app itself is described in the [user guide](USER-GUIDE.md).

## Running by hand

After `Install-FrameScout.bat`:

```powershell
# User interface
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

# Engine directly (CLI)
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150

# Quick search of the photos already analyzed (no profile; result in .\results\quick\)
.\.venv\Scripts\python.exe framescout_engine.py .\photos --quick-query "red car" --output .\results --device cpu

# All engine options
.\.venv\Scripts\python.exe framescout_engine.py --help

# Installation self-test (read-only; Check-FrameScout.bat runs it)
.\.venv\Scripts\python.exe framescout_check.py
```

`framescout_check.py` (F15) prints one line per check and a "Fix:" line per problem. Exit
code 0: no problem found, 2: at least one problem; 1 (Python's code for an uncaught
exception) or any other: the check itself could not run. It is standard library only, so it
also runs with the private Python (`.python\python.exe`).

`profiles.json` exists once the app has been started; on a fresh clone use
`--profiles .\assets\profiles.example.json`.

- A manual run needs no environment variables: unless set, the engine puts model weights,
  the Ultralytics settings and `yolo11n.pt` under the project's `.cache\`, like the `.bat`
  files do. A variable you set (`TORCH_HOME`, `HF_HOME`, `YOLO_CONFIG_DIR`,
  `XDG_CACHE_HOME`) wins, in the app and the `.bat` files too; with your `XDG_CACHE_HOME`,
  `TORCH_HOME` and `HF_HOME` stay unset, so torch and huggingface_hub derive them from it. The defaults are set when
  `main()` runs, not when the module is imported. A `yolo11n.pt` in the working folder is
  used before the cached copy (the project folder's own `yolo11n.pt` counts as an older
  version's download).
- The engine takes one or more photo folders (also between or after the options), e.g.
  `framescout_engine.py D:\Event2024 E:\Holiday --profiles .\profiles.json --output .\results`.
  The output folder must neither be a listed folder nor contain one.
- `--low-priority` lowers the engine process's priority (Windows: below normal, an
  inherited idle or below normal class is kept; elsewhere `os.nice(10)`) and keeps one or two
  CPU cores out of the PyTorch threads (`framescout_core.torch_threads`, also for the person
  detector); the decoding threads are not reduced. The engine does it itself, so the app
  starts it the same way as a manual run. Its effect is not measured yet (E52).
- Only one search at a time can use an output folder: the engine holds `<output>\run.lock`
  and writes its progress to `<output>\run-status.json`. A second engine on the same folder
  waits five seconds and exits with code 3. The app shows a command-line search into
  `results` too, and its Stop button ends it.
- To install packages by hand, use `pip install -r requirements\requirements.txt -c requirements\constraints.txt`;
  without `-c requirements\constraints.txt` pip takes the newest releases.

## Tests

The tests need neither torch nor a model download:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

GitHub runs them on Windows with Python 3.12, 3.13 and 3.14 for every pull request and
every push to `main` (`.github/workflows/tests.yml`).

## Contributing

Changes go through pull requests with [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/);
roadmap items follow the workflow in [CLAUDE.md](../CLAUDE.md) (one pull request per
item). Open work is tracked in [docs/BACKLOG.md](BACKLOG.md), the order of work in
[docs/ROADMAP.md](ROADMAP.md). Report security issues privately (see
[SECURITY.md](../SECURITY.md)).

## Evaluating the search models

`framescout_eval.py` measures how well each search model ranks **your own** photos. It
runs every model on a collection, builds a pool of the photos the models rank highest,
lets you label them in the browser as match / no match, and reports the average
precision of the top 40 (AP@40) per profile and model. The numbers are a relative ranking
quality on your labels, not certainty, and say little for profiles with few hits.
Everything stays local; a model not yet in `.cache` is downloaded on its first use.

```powershell
# 1. once per collection: run all models (reference images are needed for the weight sweep)
.\.venv\Scripts\python.exe framescout_eval.py run events D:\Photos\Events --profiles .\eval-events.json
.\.venv\Scripts\python.exe framescout_eval.py run outdoor D:\Photos\Hiking --profiles .\eval-outdoor.json
# 2. build the pool of photos to label
.\.venv\Scripts\python.exe framescout_eval.py pool events
# 3. label them in the browser (Ctrl+C stops the page; run again to continue)
.\.venv\Scripts\python.exe framescout_eval.py label events
# 4. AP@40 per profile and model, and a reference-weight sweep
.\.venv\Scripts\python.exe framescout_eval.py metrics events outdoor --json .\.tmp\eval\metrics.json
```

- `run --models a,b` limits the models, `--no-person-detection` speeds the run up, and
  `pool --depth/--weights` widen the pool (labels are kept).
- In the labelling page `Y`/`1` marks a match, `N`/`2` no match, `U`/`Delete` clears,
  `Space`/`→` and `←` move, `Enter` jumps to the next unlabelled photo and `O` opens the
  original. If port 8765 is taken, use `label --port`.
- Labels belong to a profile **name**: editing the prompts keeps them. The labelling page
  records the profile's context, features and reference images (as the pool shows them) with
  its first label; if they change later, `pool` and `metrics` warn that the labels were made
  for another motif (E36). Give the profile a new name or clear its labels then. `label` also
  warns at its start when the profile changed after `pool`: run `pool` again before labelling.
  Labels made before E36, and those of a profile the profiles file does not have, have no
  recorded motif until the next label is set with a known one.
- `run` warns ("Little free disk space") before the model runs when the model outputs, the
  missing model downloads and the detector weights may not fit (E51); it only warns. It
  counts the photos for that first (one more scan of the folders, as long as the engine's).
- Files go to `.tmp/eval/<collection>/` (gitignored; `--dir` chooses another place).
- `pool` also renders a thumbnail for every pool photo that no gallery has and for every
  reference image into `<collection>/thumbnails/`, so the page can show HEIC/HEIF and RAW
  files (E35). It uses `framescout_images` for that (Pillow, no torch; E49); without Pillow it
  prints how many photos stay without one. A photo changed since its run gets no thumbnail
  (the page shows the original file).
- `run --cache-dir` defaults to the `.cache` of the checkout whose `.venv` runs the tool (so a
  git worktree started with the main checkout's `.venv` reuses the main checkout's models),
  otherwise to the `.cache` next to the script (E48). The venv's checkout counts only when the
  script lies in it (the checkout itself or a worktree inside it), never another clone's venv.
  `run` prints the folder it uses; pass `--cache-dir` to use another one.
- Status: runtime-tested on the home PC (E34, 2026-11-01): all four models on CUDA over
  4997 photos, then `pool`, the labelling page and `metrics` with the user's own labels.
  That collection used profiles chosen for its photos (a local studio-event photo set), not
  the shipped examples. Formats: `ARCHITECTURE.md` → "Model evaluation tool".

## Project structure

| File / folder | Purpose |
|---|---|
| `app.py` | Streamlit user interface |
| `framescout_engine.py` | Search engine as a standalone CLI |
| `framescout_core/` | Shared helpers of app and engine, one module per area; standard library only |
| `framescout_scoring/` | Scoring package (`ranking.py`, re-exported by `__init__.py`): prompt ensemble, scaling, weighting; numpy only |
| `framescout_images.py` | Image decoding and thumbnails (Pillow, optional HEIF/RAW); no torch; used by the engine and the evaluation tool |
| `framescout_eval.py`, `assets/framescout_eval_page.html` | Model evaluation tool (see above); not used by the app |
| `framescout_uninstall.py`, `Uninstall-FrameScout.bat` | Uninstaller |
| `framescout_check.py`, `Check-FrameScout.bat` | Read-only installation self-test (`framescout_core/install_check.py`) |
| `install_torch.py`, `Install-FrameScout.bat`, `Start-FrameScout.bat` | Installation (CPU or CUDA build of PyTorch) and start on Windows |
| `assets/profiles.example.json` | Example search profiles; copied to `profiles.json` on the first start |
| `requirements/requirements.txt`, `requirements/constraints.txt` | Dependencies (ranges, PyTorch pinned) and the exact versions of the verified runs |
| `requirements/requirements-dev.txt`, `pytest.ini`, `tests/` | Development dependencies and the test suite (`pytest.ini` stays in the root: pytest finds its configuration only there) |
| `.github/` | CI workflow and pull request template |
| `docs/ROADMAP.md`, `docs/BACKLOG.md`, `docs/BACKLOG-DONE.md`, `docs/ROADMAP-DONE.md` | Order of work, open items, finished items, finished roadmap packages |
| `docs/` | User guide, this file, architecture, feature ideas (`IDEAS.md`) |
| `CLAUDE.md`, `.claude/` | Rules for Claude Code and the `/roadmap` workflow skill |
| `profiles.json`, `settings.json`, `photos/`, `references/`, `results/`, `run.log` | User data and output (not in the repo) |
| `.python/`, `.venv/`, `.cache/`, `.tmp/` | Private Python, environment, caches and model weights (not in the repo) |

A new entry point (a root script that imports FrameScout code) must set `FRAMESCOUT_PACKAGES = True` before its first FrameScout import, so the import guards of `framescout_core` and `framescout_scoring` let it run next to the leftover single files of an older version (I35, I36); add it to `ENTRY_POINTS` in `tests/test_layout.py`, which enforces the order.
