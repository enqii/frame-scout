# FrameScout – Local AI Image Search

FrameScout searches large local photo collections for motifs. You describe what you are
looking for (e.g. "red car", "golden retriever", "mountain landscape") and optionally add
example images. For each search profile, FrameScout creates a ranked list of the best
matching photos as an HTML gallery.

- **Local:** Your images never leave your computer. Only model weights and Python
  packages are downloaded during installation or the first run.
- **General-purpose:** People, objects, vehicles, animals, landscapes, scenes.
- **No language model:** Search is based on OpenAI CLIP (ViT-B/32), optionally combined with
  YOLO11n person detection for group photos.
- **English search terms:** CLIP understands practically only English, so describe your
  motifs in English (see [Search terms in English](#search-terms-in-english)).

> **Status:** Prototype (v1.1). Open issues and the roadmap are listed in
> [BACKLOG.md](BACKLOG.md).

## Requirements

- Windows 10/11
- Python **3.14, 3.13 or 3.12** with the `py` launcher (install from python.org)
- Internet connection for installation and the first search run
- A dedicated GPU is not required; search also runs on the CPU. An NVIDIA GPU with a
  current driver can be used through CUDA (see below).

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

### GPU support (NVIDIA, CUDA)

If the installer finds an NVIDIA graphics driver (`nvidia-smi`), it asks whether to
install GPU support; otherwise it installs the CPU version without asking. GPU support
means the CUDA build of PyTorch, about 2.5 GB more download. Both CLIP and the person
detection then run on the GPU. You can also choose directly:

```powershell
.\Install-FrameScout.bat cuda   # PyTorch with CUDA support
.\Install-FrameScout.bat cpu    # PyTorch for the CPU only
```

Close FrameScout (the `Start-FrameScout.bat` window) before you run the installer: pip
cannot replace PyTorch's files while the app uses them, and the app shows the new
build only after it is started again.

Running the installer again without an option (e.g. after an update) keeps an installed
CUDA build and asks nothing; `cpu` or `cuda` switches between the two. If the GPU cannot
be checked at that moment, an installed CUDA build is kept as well. For CUDA
the installer picks the PyTorch build from the GPU and driver that `nvidia-smi` reports:
CUDA 13.0 for GeForce RTX 20 series or newer (compute capability 7.5+) with driver 580 or
newer, otherwise CUDA 12.6 (GeForce GTX 900 series or newer, compute capability 5.0 up
to 9.x, driver 528.33 or newer; RTX 50 series cards need CUDA 13.0 and a current driver).
With several NVIDIA GPUs it prefers a build that suits all of them; otherwise it takes
the build for the most capable GPU and names the GPUs it cannot use. If no build suits the
GPU and driver, it explains why and installs the CPU version (or keeps an installed CUDA
build). These
limits come from the CUDA and PyTorch documentation as known when this was written and
are **not verified**. The GPU path has had a single test run so far (a GeForce RTX 4070
with the CUDA 13.0 build and synthetic test images; the results matched a CPU run), so
treat GPU support as experimental. Under "AI settings" the app shows whether PyTorch
can use the GPU; it offers "cuda" only then.

### Updating an existing installation

Your search profiles are stored in `profiles.json`, which is not part of the
repository: on the first start the app creates it from the shipped
`profiles.example.json` and never overwrites it afterwards. Each time the app saves your
profiles, it keeps the version from before that save as `profiles.json.bak`. Only this one
step is kept: the next save (any edit, new or deleted profile) replaces the backup, so
restore it right after a mistake, or copy `profiles.json` elsewhere for a lasting backup.
If `profiles.json` cannot be read (e.g. after editing it by hand), the app shows the error
and leaves the file unchanged; fix it in a text editor or restore the backup. The app also
reads the older format `{"name": ["search text", ...]}` and saves it in the current
format; the original stays in `profiles.json.bak` only until the second save.

Checkouts from before the English user interface still have a `profiles.json` that git
tracks.
**Copy it to a safe place before `git pull`** – the update removes it from the
repository, so git deletes an unchanged copy (or refuses to update if you edited it;
then move the file away first). Put your copy back afterwards; without it, the app
starts with the new example profiles.

## Starting and using FrameScout

1. Double-click `Start-FrameScout.bat`. Your browser opens
   <http://127.0.0.1:8501>.
2. **Search profiles:** name the motif and optionally add context, distinctive
   features, custom search texts and reference images. Write all of these texts in
   English (see [Search terms in English](#search-terms-in-english)). On the first start the
   list contains a few example profiles (red car, golden retriever, mountain landscape,
   …) that you can edit or delete. Uploaded reference images are copied to
   `references/<profile name>/` (e.g. `references/red-car/`); a profile whose name
   leads to a folder another profile already uses gets its own (`red-car-2`, …).
   When you rename a profile, its reference images move to the folder of the new name
   and the profile is updated accordingly; other files in the old folder (e.g. images
   you removed from the profile) stay there, and the old folder is deleted only if it is
   empty. The paths in `profiles.json.bak` are updated to the new folder as well, so
   restoring the backup after a rename still finds the images (if that update fails, the
   images also keep their old names and the app shows a note). Removing reference
   images from a profile or deleting a profile does not delete the files; "Clean up
   storage" can list and delete them (see [Cleaning up storage](#cleaning-up-storage)).
3. **Photo source:** choose a local image folder (default: `photos` in the
   project folder). Subfolders are searched as well. Download and extract archives and
   online albums yourself beforehand – FrameScout does not download images from the
   internet.
4. **AI settings:** with "auto", CUDA is used if PyTorch detects a
   compatible NVIDIA GPU, otherwise the CPU; "cuda" is offered only if PyTorch was
   installed with GPU support (see "GPU support" above). The batch size is the number of image
   parts (whole photos and person crops, also from several photos) that CLIP analyzes
   together; 8 is a conservative starting value, reduce it if memory runs short.
   Without person detection, JPEG photos are decoded at a reduced resolution, which
   makes the analysis noticeably faster; with person detection they keep their full
   resolution, so that small persons, e.g. in group photos, keep their detail.

   The photo folder and the AI settings are saved in `settings.json` in the project
   folder as soon as you change them, so they are kept after a reload or a restart and
   apply in every tab. Only values that differ from the defaults are stored; delete the
   file to return to the defaults. If it cannot be read (e.g. after editing it by hand),
   the app keeps the settings it shows (the defaults when the page is new) and leaves
   the file unchanged; a value that is not allowed is replaced by its default with a
   warning and removed from the file with the next saved change. A saved compute device
   that PyTorch cannot use (e.g. "cuda" after installing the CPU build) is shown and used
   as "auto" but stays saved, so it applies again once PyTorch can use it; choose another
   device or "Use auto from now on" to replace it. If another tab or window changed the
   settings since your page last updated, "Start search" first shows the new settings
   and asks you to start again, so a search never runs with settings you have not seen.
5. **Search & results:** start the analysis. The page shows the current step (looking
   for photos, loading the AI models, analyzing, scoring, writing the galleries) and its
   progress. The search keeps running when you reload the page or close the browser tab
   (as long as the `Start-FrameScout.bat` window stays open); opening the page again, also
   in another tab, shows it again and lets you stop it. Only one search runs at a time:
   while one runs, the controls are disabled in every tab, and a second start is refused.
   Below, **Results** shows the last finished search: choose a search profile to see its
   photos as thumbnails, best first, 48 per page, with rank, score, the best-matching part
   ("Full image" or "Person 1", …) and the file name. "Open" opens a photo in your image
   viewer, "Folder" shows it in its folder; "Open gallery in browser" and "Open results
   folder" open the HTML gallery and the `results` folder. These buttons use the programs
   of the computer FrameScout runs on. The date of the search is shown, and a profile you
   changed (search texts or reference images), renamed or deleted since is marked, since
   its results no longer fit it.
6. **Mark and copy matches:** the results are candidates, not certain hits. Below each
   thumbnail, mark a photo you have checked as **Match** or **No match** (or leave it
   **Undecided**; clicking the selected option again also makes it undecided). Marks are kept per
   search profile and photo across later searches and in every tab, and a renamed profile
   keeps them; "Hide photos marked as no match" hides the rejected ones. Below the
   gallery, "Copy N marked photos" copies all photos marked as match for that profile into
   the folder in "Copy to folder" (prefilled with `Pictures\FrameScout\red-car` for "Red car";
   a folder you type is saved per profile). Copying never moves, changes or deletes the
   originals and never overwrites a file in the target folder: all copies land directly
   in that folder (no subfolders) with their file date; a file with the same name and
   content counts as "already there", a different photo with the same name is saved as
   `name (2).jpg`. A folder inside the photo folder is refused, since the next search
   would analyze the copies again and show every photo twice. The summary reads e.g.
   "20 copied · 2 already there · 1 renamed · 0 failed"; "Open target folder" opens the
   folder.

Supported formats: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF. HEIC and camera RAW files are
not supported yet and are skipped ([BACKLOG.md](BACKLOG.md), E25).

### Search terms in English

FrameScout supports **English search terms only**. The CLIP model it uses (OpenAI
ViT-B/32) was trained on mostly English image captions and understands practically only
English. FrameScout puts the motif name, context and features into English sentences
(e.g. "A photograph of red car (vehicles).") and does not translate anything. So write
the motif name, the context, the features and your custom search texts in English, e.g.
"sword" instead of German "Schwert". The app does not check the language.

Some common words of other languages come close to their English counterparts, many
do not, and the results do not show which case you are in. In a local test with one
collection of about 5,000 event photos (so an observation, not a guarantee):

- A profile "Sword" (context "Prop", features "a blade with a hilt, held in the hand")
  put 29 photos with a sword among its first 40 results. The same profile in German
  ("Schwert", "Requisite", "eine Klinge mit Griff, in der Hand gehalten") ranked almost
  completely different photos first: none of its first 40 was one of the photos known
  to show a sword (most of them had not been checked, so it may have found a few). With
  the motif name alone, only 1 of the first 50 photos for "Schwert" was also among the
  first 50 for "Sword".
- For 16 motifs in that collection, the first 50 results of the German and the English
  word agreed by 0 % (Regenschirm/umbrella) to 58 % (Blumen/flowers).

A multilingual model may become an option later ([BACKLOG.md](BACKLOG.md), E21).

## Results

- `results/results.json` lists what the galleries of the last finished search show
  (date, photo folder, settings and, per profile, the ranked photos with their scores and
  thumbnails); the app reads it to show the results. It is replaced at the end of every
  search that finishes, so a stopped search keeps showing the previous results. Results
  folders of earlier versions have no such file: the app then lists their HTML files by
  name until the next search.
- `results/marks.json` holds your marks (Match / No match per profile and photo); the
  search never changes it, and "Clean up storage" never deletes it. It is your data:
  keep it when you clean up the `results` folder by hand (deleting it removes all marks). Marks belong to the full path of a photo, so
  they no longer apply after you move or rename the photo folder.
  Marks belong to the profile name: deleting a profile keeps its marks, and a new
  profile with the same name takes them over.
- One HTML gallery per search profile is written to `results/`; the thumbnails are
  stored in `results/thumbnails/`. Clicking a photo opens the original. (Versions
  before the English UI used `results/vorschaubilder/`; that folder is no longer
  written; galleries created before still link it. The cleanup removes its files once no
  kept gallery links them.)
- At the end of every finished search FrameScout removes, by itself, the thumbnails that
  neither the last search nor any HTML file in `results/` shows (e.g. of photos that
  dropped out of the results) and temporary thumbnail files a stopped search left behind.
- The gallery file is named after the profile in plain ASCII, e.g. "Red car" →
  `red-car.html`, "Bär" → `baer.html`; names that would collide get `-2`, `-3`, … in
  profile order, and names without Latin letters or digits (e.g. "猫") get a short hash.
- A photo that is deleted or moved while a search runs is left out of the galleries;
  the log names it ("Thumbnail not possible").
- Keep the `results` folder together: an HTML file exported on its own contains no
  thumbnails, and the links to the originals only work on this computer.
- While a search runs, `results/run.lock` marks it as running and
  `results/run-status.json` holds its step and progress; the app reads both. Both files
  stay after the run (the status file then describes the last run) and can be deleted
  when no search is running.
- Photos that have already been analyzed are stored in `results/cache.sqlite3`. An
  interrupted run resumes from there on the next start (the few photos that were being
  analyzed at the moment of the stop are analyzed again), and new search profiles reuse
  existing analyses. Updates that change the image analysis (e.g. the CLIP fix in
  2026-10) analyze every photo once more; the older entries stay in the file, which therefore
  grows (roughly doubles) until you delete them with "Clean up storage". The faster
  decoding without person detection (2026-10) is such a change for searches **without**
  person detection: the first such search after the update analyzes every photo once
  more; searches with person detection keep using their existing analyses.

### Cleaning up storage

Galleries of renamed or deleted profiles, thumbnails, old cache entries and reference
images you removed from profiles are never deleted silently. **Search & results →
Clean up storage** lists them: click **Scan** (it only looks), check the categories
you want to delete, click **Delete selected** and confirm. Deleting is **permanent**:
nothing goes to the Recycle Bin. Scanning and deleting are not possible while a search
runs, and no search can start while the cleanup deletes.

| Category | Selected after a scan | What it is |
|---|---|---|
| Temporary thumbnail files | yes | Left by a search stopped while it wrote the galleries |
| Galleries of renamed or deleted profiles | yes | FrameScout HTML galleries in `results/` that belong neither to a current profile nor to the last search (the file names are listed) |
| Thumbnails no gallery shows | yes | Thumbnails neither the last search nor a kept gallery shows, also in the old `vorschaubilder/` folder; those only the galleries above show go together with them |
| Cache entries of deleted photos | yes | Analyses of photos inside the **current** photo folder that no longer exist; only if that folder exists, so a disconnected drive is never cleaned |
| Cache entries of older versions or unknown settings | yes | Analyses of an earlier FrameScout version (never used again) or of settings only the command line offers (e.g. another `--yolo-model`) |
| Cache entries of other AI settings | no | Analyses with other person detection settings; they are used again when you switch back, so deleting them means analyzing those photos again then |
| Reference images no profile uses | no | Image files in `references/` that neither `profiles.json` nor `profiles.json.bak` names (the file names are listed) |

"Compact cache.sqlite3 afterwards" (on by default) shrinks the cache file after
entries were deleted; without it the file keeps its size and reuses the space. Only
what the scan listed and is still unused at the moment of deleting is deleted: e.g. a
reference image a profile uses since the scan stays. Galleries and thumbnails are not
offered while `results.json` or `profiles.json` cannot be read, reference images not
while `profiles.json` or `profiles.json.bak` cannot be read. Never deleted:
`results/marks.json` (your marks), `results.json`, `run.lock`, `run-status.json`, the
cache file itself, `settings.json`, `profiles.json` and `profiles.json.bak`, and of
course your photos. While the cleanup deletes, another open tab says so and cannot
start a search. If a step fails (e.g. a folder that cannot be read), the summary names
it and still counts what was deleted.

### What the numbers in a gallery mean

FrameScout compares every photo (and every person found in it) with the search texts
of a profile and, if the profile has any, with its reference images. The texts it
generates from the name, context and features are combined into one search text;
each custom search text counts on its own, and the best one decides.

The main number on a card is the **Score**: how far the best part of the photo lies
above the average image part of this search (every whole photo and every person crop
counts), measured in standard deviations of this search. For a profile without
reference images a score of +2 means "clearly more similar than most image parts in
this folder", 0 means "average". Text and reference images are scaled this way
separately before the **weight of the reference images** (AI settings) mixes them, so
the default weight of 0.3 really means 30 % reference images and 70 % text; the mixed
score is a weighted sum of the two scaled scores and therefore only roughly in
standard deviations. The weight only matters for profiles with
reference images; with a weight of 0 only the text and with 1 only the reference images
count. The small numbers below are the raw similarities of that part with
the text and with the reference images. Scores therefore depend on the folder searched:
the same photo can get a different score in another folder. With very few photos
(fewer than ten image parts), the gallery shows the raw weighted "Similarity" instead.

Changed in 2026-10: before, the best single generated search text decided and the raw
similarities were added up, so reference images weighed much more than their nominal
weight (the reference scores spread about twice as wide as the text scores). The
default weight changed from 0.35 to 0.3, the value that worked best in a local test
with about 5,000 event photos (a single collection, so treat it as a starting
point). `settings.json` stores only values that differ from the defaults, so a
saved weight other than 0.35 is kept as it is, and everyone else gets 0.3 – also if
you had deliberately set the slider to 0.35 (the old default was never saved). To keep
0.35, set the slider to 0.35 again; to use the new default, set it to 0.3. Rankings and numbers of
older galleries differ; no photo is analyzed again.

### How reliable are the matches?

The displayed score is a relative ranking value, **not a probability
and not a reliable identification**. FrameScout can miss matches or return false matches
– especially with large group photos, small or inconspicuous motifs, and when comparing
drawings/artwork with real photos. Person detection helps with people in group photos;
it can be turned off for other motifs.

## Uninstalling

1. Back up results, your search profiles (`profiles.json`, `references/`), your
   settings (`settings.json`), your marks (`results/marks.json`) and any photos you want
   to keep elsewhere. Copied matches are in `Pictures\FrameScout` (or the folders you
   chose), outside the project folder, and stay.
2. Close FrameScout and delete the project folder. This removes `.venv`, caches
   (`.cache`, `.tmp`), model weights (including `yolo11n.pt`) and results.

A system-wide Python installation remains in place. Individual dependencies may also
create their own caches in your user profile. For example, Ultralytics (person detection)
writes `%APPDATA%\Ultralytics\settings.json` when it is used outside the `.bat` files,
e.g. from a manual command line without `YOLO_CONFIG_DIR`.

## Development

Manual start after installation:

```powershell
# User interface
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501

# Engine directly (CLI)
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150
```

`profiles.json` exists once the app has been started; on a fresh clone use
`--profiles .\profiles.example.json` instead.

Only one search at a time can use an output folder: the engine holds a lock on
`<output>\run.lock` while it runs and writes its progress to `<output>\run-status.json`.
A second engine started on the same output folder (also while the app runs a search
into `results`) waits up to five seconds and then exits with code 3. The app shows a
search started from the command line into `results` as well, and its Stop button ends it.

All engine options: `.\.venv\Scripts\python.exe framescout_engine.py --help`

Tests (they need neither torch nor a model download; `requirements-dev.txt` adds pytest and numpy):

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
| `app.py` | Streamlit user interface (profiles, photo source, settings, search run, result gallery with marks and copying) |
| `framescout_engine.py` | Search engine as a standalone CLI |
| `framescout_core.py` | Shared helpers of app and engine (file names, supported formats, loading and saving profiles and settings, thumbnails, run lock and status file, result file, marks and copying, cleanup); standard library only |
| `framescout_scoring.py` | Scoring of the engine: prompt ensemble, scaling and weighting of text and reference scores; numpy only |
| `profiles.example.json` | Example search profiles; the app copies them to `profiles.json` on the first start |
| `requirements.txt` | Python dependencies (PyTorch pinned) |
| `install_torch.py` | Installs the CPU or CUDA build of PyTorch; called by `Install-FrameScout.bat` |
| `requirements-dev.txt`, `pytest.ini`, `tests/` | Development dependencies and the test suite |
| `.github/` | CI workflow (`workflows/tests.yml`) and pull request template |
| `Install-FrameScout.bat` / `Start-FrameScout.bat` | Installation and start on Windows |
| `BACKLOG.md` | Known weaknesses and roadmap |
| `CLAUDE.md` | Rules for Claude Code and the development workflow |
| `docs/ARCHITECTURE.md` | Architecture and runtime details for contributors |
| `.claude/` | Claude Code project settings and the `/roadmap` workflow skill |
| `profiles.json`, `settings.json`, `photos/`, `references/`, `results/`, `run.log` | User data and runtime output (not in the repo) |
| `.venv/`, `.cache/`, `.tmp/`, `yolo11n.pt` | Environment, caches and model weights (not in the repo) |
