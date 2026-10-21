# FrameScout – Local AI Image Search

FrameScout searches large local photo collections for motifs. You describe what you are
looking for (e.g. "red car", "golden retriever", "mountain landscape") and optionally add
example images. For each search profile, FrameScout creates a ranked list of the best
matching photos as an HTML gallery.

- **Local:** Your images never leave your computer. Only model weights and Python
  packages are downloaded during installation or the first run.
- **General-purpose:** People, objects, vehicles, animals, landscapes, scenes.
- **No language model:** Search is based on CLIP (ViT-B/32), optionally combined with
  YOLO11n person detection for group photos.

> **Status:** Prototype (v1.1). Open issues and the roadmap are listed in
> [BACKLOG.md](BACKLOG.md).
>
> **Note:** The user interface is currently still in German. Translating it to English is
> planned (backlog item I7). UI labels below are quoted as they currently appear, with an
> English gloss.

## Requirements

- Windows 10/11
- Python **3.14, 3.13 or 3.12** with the `py` launcher (install from python.org)
- Internet connection for installation and the first search run
- A dedicated GPU is not required; search also runs on the CPU.

## Installation

1. Get the project into a folder of its own, e.g. `C:\FrameScout`:
   ```powershell
   git clone https://github.com/enqii/frame-scout.git C:\FrameScout
   ```
   (alternatively download the ZIP and extract it)
2. Double-click `Install-FrameScout.bat`. The installer looks for Python 3.14, 3.13 or
   3.12 (in that order), creates an isolated `.venv` in the project folder and installs
   the dependencies.

If package installation fails with one Python version: delete `.venv`, install another
supported Python version and run the installer again.

## Starting and using FrameScout

1. Double-click `Start-FrameScout.bat`. Your browser opens
   <http://127.0.0.1:8501>.
2. **Suchprofile** (search profiles): name the motif and optionally add context,
   features (preferably in English), custom search texts and reference images.
3. **Fotoquelle** (photo source): choose a local image folder (default: `photos` in the
   project folder). Subfolders are searched as well. Download and extract archives and
   online albums yourself beforehand – FrameScout does not download images from the
   internet.
4. **KI-Einstellungen** (AI settings): with "auto", CUDA is used if PyTorch detects a
   compatible NVIDIA GPU, otherwise the CPU. A batch size of 8 is a conservative
   starting value.
5. **Suche & Ergebnisse** (search & results): start the analysis. Keep the browser open
   during the search run if possible – start/stop is tied to the running Streamlit
   session.

Supported formats: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF.

## Results

- One HTML gallery per search profile is written to `results/`; the thumbnails are
  stored in `results/vorschaubilder/`. Clicking a photo opens the original.
- The gallery file is named after the profile in plain ASCII, e.g. "Red car" →
  `red-car.html`, "Bär" → `baer.html`; names that would collide get `-2`, `-3`, … in
  profile order, and names without Latin letters or digits (e.g. "猫") get a short hash.
- Keep the `results` folder together: an HTML file exported on its own contains no
  thumbnails, and the links to the originals only work on this computer.
- Photos that have already been analyzed are stored in `results/cache.sqlite3`. An
  interrupted run resumes from there on the next start, and new search profiles reuse
  existing analyses.

### How reliable are the matches?

The displayed "Ähnlichkeit" (similarity) is a relative ranking value, **not a probability
and not a reliable identification**. FrameScout can miss matches or return false matches
– especially with large group photos, small or inconspicuous motifs, and when comparing
drawings/artwork with real photos. Person detection helps with people in group photos;
it can be turned off for other motifs.

## Uninstalling

1. Back up results and any photos you want to keep elsewhere.
2. Close FrameScout and delete the project folder. This removes `.venv`, caches
   (`.cache`, `.tmp`), model weights (including `yolo11n.pt`) and results.

A system-wide Python installation remains in place. Individual dependencies may also
create their own caches in your user profile.

## Development

Manual start after installation:

```powershell
# User interface
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

# Engine directly (CLI)
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150
```

All engine options: `.\.venv\Scripts\python.exe framescout_engine.py --help`

Tests (they need neither torch nor a model download):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

The same tests run automatically on GitHub (Windows, Python 3.12, 3.13 and 3.14) for
every pull request and every push to `main` – see `.github/workflows/tests.yml`.

Contributions follow the PR workflow described in [CLAUDE.md](CLAUDE.md) (Conventional
Commits, one pull request per roadmap item).

### Project structure

| File / folder | Purpose |
|---|---|
| `app.py` | Streamlit user interface (profiles, photo source, settings, search run) |
| `framescout_engine.py` | Search engine as a standalone CLI |
| `framescout_core.py` | Shared helpers of app and engine (file names, supported formats, profile loading); standard library only |
| `profiles.json` | Saved search profiles |
| `requirements.txt` | Python dependencies |
| `requirements-dev.txt`, `pytest.ini`, `tests/` | Development dependencies and the test suite |
| `.github/` | CI workflow (`workflows/tests.yml`) and pull request template |
| `Install-FrameScout.bat` / `Start-FrameScout.bat` | Installation and start on Windows |
| `BACKLOG.md` | Known weaknesses and roadmap |
| `CLAUDE.md` | Project onboarding and development workflow |
| `.claude/` | Claude Code project settings and the `/roadmap` workflow skill |
| `photos/`, `references/`, `results/`, `run.log` | User data and runtime output (not in the repo) |
| `.venv/`, `.cache/`, `.tmp/`, `yolo11n.pt` | Environment, caches and model weights (not in the repo) |
