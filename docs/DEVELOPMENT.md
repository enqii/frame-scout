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

# All engine options
.\.venv\Scripts\python.exe framescout_engine.py --help
```

`profiles.json` exists once the app has been started; on a fresh clone use
`--profiles .\profiles.example.json`.

- A manual run needs no environment variables: unless set, the engine puts model weights,
  the Ultralytics settings and `yolo11n.pt` under the project's `.cache\`, like the `.bat`
  files do.
- The engine takes one or more photo folders (also between or after the options), e.g.
  `framescout_engine.py D:\Event2024 E:\Holiday --profiles .\profiles.json --output .\results`.
  The output folder must neither be a listed folder nor contain one.
- Only one search at a time can use an output folder: the engine holds `<output>\run.lock`
  and writes its progress to `<output>\run-status.json`. A second engine on the same folder
  waits five seconds and exits with code 3. The app shows a command-line search into
  `results` too, and its Stop button ends it.
- To install packages by hand, use `pip install -r requirements.txt -c constraints.txt`;
  without `-c constraints.txt` pip takes the newest releases.

## Tests

The tests need neither torch nor a model download:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

GitHub runs them on Windows with Python 3.12, 3.13 and 3.14 for every pull request and
every push to `main` (`.github/workflows/tests.yml`).

## Contributing

Changes go through pull requests with [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/);
roadmap items follow the workflow in [CLAUDE.md](../CLAUDE.md) (one pull request per
item). Open work is tracked in [BACKLOG.md](../BACKLOG.md), the order of work in
[ROADMAP.md](../ROADMAP.md). Report security issues privately (see
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
- Labels belong to a profile **name**: editing the prompts keeps them, so give a profile
  a new name when its motif changes.
- Files go to `.tmp/eval/<collection>/` (gitignored; `--dir` chooses another place).
- Status: not yet run with real models (E34). Formats: `ARCHITECTURE.md` → "Model
  evaluation tool".

## Project structure

| File / folder | Purpose |
|---|---|
| `app.py` | Streamlit user interface |
| `framescout_engine.py` | Search engine as a standalone CLI |
| `framescout_core/` | Shared helpers of app and engine, one module per area; standard library only |
| `framescout_scoring.py` | Scoring (prompt ensemble, scaling, weighting); numpy only |
| `framescout_eval.py`, `framescout_eval_page.html` | Model evaluation tool (see above); not used by the app |
| `framescout_uninstall.py`, `Uninstall-FrameScout.bat` | Uninstaller |
| `install_torch.py`, `Install-FrameScout.bat`, `Start-FrameScout.bat` | Installation (CPU or CUDA build of PyTorch) and start on Windows |
| `profiles.example.json` | Example search profiles; copied to `profiles.json` on the first start |
| `requirements.txt`, `constraints.txt` | Dependencies (ranges, PyTorch pinned) and the exact versions of the verified runs |
| `requirements-dev.txt`, `pytest.ini`, `tests/` | Development dependencies and the test suite |
| `.github/` | CI workflow and pull request template |
| `ROADMAP.md`, `BACKLOG.md`, `docs/BACKLOG-DONE.md` | Order of work, open items, finished items |
| `docs/` | User guide, this file, architecture, feature ideas (`IDEAS.md`) |
| `CLAUDE.md`, `.claude/` | Rules for Claude Code and the `/roadmap` workflow skill |
| `profiles.json`, `settings.json`, `photos/`, `references/`, `results/`, `run.log` | User data and output (not in the repo) |
| `.python/`, `.venv/`, `.cache/`, `.tmp/` | Private Python, environment, caches and model weights (not in the repo) |
