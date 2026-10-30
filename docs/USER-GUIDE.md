# FrameScout user guide

The [README](../README.md) covers installation and a quick start. This guide describes
every part of the app in detail. Development, the command line and the evaluation tool
are in [DEVELOPMENT.md](DEVELOPMENT.md).

## Installation details

`Install-FrameScout.bat` downloads python.org's Python 3.14.9 (about 33 MB, checked
against a fixed SHA-256) into the folder `.python`, creates an isolated `.venv` with it
and installs the dependencies in the fixed versions of `constraints.txt`. An installed
Python is not needed and not used. A working `.venv` is kept, also one from an earlier
installer (Python 3.12 to 3.14 installed on the PC). Running the installer again repairs
an environment that no longer starts or lacks pip, and downloads the private Python again
if it is incomplete or another version.

**Do not move or rename the FrameScout folder after the installation:** `.venv` refers to
`.python` by its absolute path. If you moved it anyway, run the installer again (it
downloads all packages again, several GB with CUDA). If the installation fails twice,
delete `.python` and run it once more.

When you update from a ZIP, extract it into a fresh folder instead of over an old one,
so no files of earlier versions stay behind.

### GPU support (NVIDIA, CUDA)

If the installer finds an NVIDIA graphics driver (`nvidia-smi`), it asks whether to
install GPU support (the CUDA build of PyTorch, about 2.5 GB more download); otherwise it
installs the CPU version without asking. CLIP and the person detection then run on the
GPU. You can also choose directly:

```powershell
.\Install-FrameScout.bat cuda   # PyTorch with CUDA support
.\Install-FrameScout.bat cpu    # PyTorch for the CPU only
```

Close FrameScout before you run the installer: pip cannot replace PyTorch's files while
the app uses them. Running it again without an option keeps the installed build.

The installer picks the build from what `nvidia-smi` reports: CUDA 13.0 for GeForce RTX 20
series or newer (compute capability 7.5+) with driver 580 or newer, otherwise CUDA 12.6
(GTX 900 series or newer, driver 528.33 or newer; RTX 50 series cards need CUDA 13.0).
With several GPUs it prefers a build that suits all of them. If no build fits, it says why
and installs the CPU version. These limits come from the CUDA and PyTorch documentation and
are **not verified**; the GPU path has had a single test run (GeForce RTX 4070, CUDA 13.0),
so treat it as experimental. Under "AI settings" the app shows whether PyTorch can use the
GPU and offers "cuda" only then.

## Using the app

Start `Start-FrameScout.bat`; the browser opens <http://127.0.0.1:8501>. The app has one
tab per step.

### Search profiles

A profile describes one motif: a name, optional context, distinctive features, custom
search texts and reference images. Write all texts in English (see
[Search terms in English](#search-terms-in-english)). On the first start the list holds a
few example profiles that you can edit or delete.

- Uploaded reference images are copied to `references/<profile name>/` (e.g.
  `references/red-car/`). Renaming a profile moves its images to the new folder.
- Removing reference images or deleting a profile does not delete the files;
  [Clean up storage](#cleaning-up-storage) can. "Delete profile" asks first and also
  deletes the profile's marks and its saved copy folder setting.
- Profiles are stored in `profiles.json`, which is not part of the repository: the app
  creates it from `profiles.example.json` on the first start and never overwrites it.
  Each save keeps the previous version as `profiles.json.bak` (one step only, so restore
  it right after a mistake). An unreadable `profiles.json` is shown as an error and left
  unchanged. If the file was changed elsewhere (by hand or in another tab) since the page
  loaded, the app refuses to save over it and shows the current profiles instead. Leave
  the empty `profiles.json.lock` alone.

### Photo source

Enter one or more local image folders, one per line (default: `photos` in the project
folder). Subfolders are searched too, and one search covers all listed folders. A folder
listed twice or inside another listed folder is searched once; a missing folder (e.g. a
disconnected drive) is left out with a note. The same folder reached by another path (another drive
letter, a UNC path, a junction) is recognized and searched once. Links to folders inside a
photo folder are followed, but each folder and each photo is searched once, even if it is
reachable through several links or by a hard link.

The tab shows how many photos each folder holds. To keep the app fast on large or network
folders, the count is made once per browser session and again only when you change the
folder list or the readable formats, or press **Recount**; "Counted at" shows when. Photos
added or removed since then appear after "Recount". A search always reads the folders
again, so it is never affected by an old count.

FrameScout does not download images: download and extract archives and online albums
yourself. A search sends nothing about your photos anywhere. It turns off Ultralytics'
usage analytics and automatic package installs (`YOLO_OFFLINE=true`,
`YOLO_AUTOINSTALL=false`), and once a model's files are in `.cache` it runs without
asking the Hugging Face Hub; missing files are downloaded with a note. Set
`HF_HUB_OFFLINE=0` or `1` for a manual run to decide this yourself.

### AI settings

- **Search model:** the default, OpenAI CLIP ViT-B/32, is the fastest and the one the
  settings are tuned for. Optional: ViT-B/16 and ViT-L/14 (DataComp-XL) and SigLIP B/16,
  roughly 4×, 18× and 4× slower on a CPU, with a first download of about 0.6, 1.7 and
  0.8 GB. They are marked "not evaluated", so treat them as an experiment. The first
  search with a new model analyzes every photo again; the cache keeps each model's
  analyses, so switching back is fast. Scores of different models are not comparable.
  SigLIP needs the package `transformers` (run the installer again on an older
  installation). The command line option is `--model`.
- **Compute device:** "auto" uses CUDA if PyTorch finds a compatible NVIDIA GPU,
  otherwise the CPU.
- **Batch size:** the number of image parts (whole photos and person crops) analyzed
  together; reduce it from 8 if memory runs short.
- **Person detection:** finds people with YOLO11n and compares each person separately,
  which helps with group photos. Turn it off for other motifs: JPEGs are then decoded
  at a reduced resolution, which is noticeably faster.
- **Weight of the reference images:** see [What the numbers mean](#what-the-numbers-mean).
- **Defaults:** the help text of each setting ends with its default, and a line below the
  settings lists the ones you changed. "Reset to defaults" (disabled while a search runs)
  sets all settings of this tab, the search model included, back to their defaults. Your
  photo folders are not reset.

Photo folders and AI settings are saved in `settings.json` as soon as you change them and
apply in every tab. Only values that differ from the defaults are stored; delete the file
to return to the defaults. An unreadable file is left unchanged, and an invalid value is
replaced by its default with a warning. If another tab changed the settings, "Start
search" first shows the new ones and asks you to start again.

### Search & results

Start the search; the page shows the current step and its progress. The search keeps
running when you reload or close the tab (as long as the `Start-FrameScout.bat` window
stays open), and opening the page again lets you stop it. Only one search runs at a time.

**Results** shows the last finished search per profile: thumbnails, best first, 48 per
page, with rank, score, the best-matching part ("Full image" or "Person 1", …) and the
file name. "Open" opens a photo, "Folder" shows it in its folder, and buttons open the
HTML gallery and the `results` folder. A profile changed, renamed or deleted since the
search is marked, since its results no longer fit it.

### Marking and copying matches

The results are candidates, not certain hits. Mark a photo you checked as **Match** or
**No match** (or leave it **Undecided**). Marks are kept per profile and photo across
later searches and in every tab. The selected option is colored (green for Match, red for
No match). "Hide photos marked as no match" hides the rejected ones within the page you
are looking at only, so the pages keep their photos and ranks; a caption tells how many
are hidden, and a page where every photo was rejected says so (see the next page).

"Copy N marked photos" copies all photos marked as match into the folder in "Copy to
folder" (default `Pictures\FrameScout\<profile>`, saved per profile). Copying never
moves, changes, deletes or overwrites anything: a different photo with the same name is
saved as `name (2).jpg`, an identical one counts as "already there". A target folder
inside a photo folder is refused, since the next search would find the copies again.

## Supported formats

JPG, JPEG, PNG, WebP, BMP, TIF, TIFF, AVIF, HEIC/HEIF and camera RAW (DNG, CR2, CR3, NEF,
ARW, ORF, RW2, RAF, PEF, SRW).

- For a RAW file FrameScout uses the camera's embedded JPEG preview if it is at least
  1024 pixels long, otherwise it decodes the RAW data at half size. Colors are the
  camera's, not your own RAW development.
- If a JPEG or HEIC of the same name is next to a RAW file ("RAW+JPEG" mode), only the
  JPEG/HEIC is searched. If that JPEG cannot be read, the RAW file is analyzed instead.
- The search log and the "Photo source" tab name skipped files and why.
- Browsers cannot show HEIC or RAW files: in the HTML gallery the thumbnail works, but a
  click downloads the file. "Open" in the app uses the program Windows has for it.
- HEIC needs `pillow-heif`, RAW needs `rawpy`; the installer adds both. An older
  installation skips these formats with a note until you run the installer again.

## Search terms in English

FrameScout supports **English search terms only**. All offered models were trained on
mostly English captions and understand practically only English. FrameScout puts the
name, context and features into English sentences (e.g. "A photograph of red car
(vehicles).") and translates nothing, so write "sword", not German "Schwert". The app
does not check the language.

Some words of other languages come close to their English counterparts, many do not, and
the results do not show which case you are in. In one local test with about 5,000 event
photos, an English profile "Sword" put 29 photos with a sword among its first 40 results;
the same profile in German found almost completely different photos. For 16 motifs, the
first 50 results of the German and the English word agreed by 0 % to 58 %. A multilingual
model may become an option later (E21 in [BACKLOG.md](../BACKLOG.md)).

## Results

Everything a search writes lands in `results/`:

| File | What it is |
|---|---|
| `<profile>.html` | One HTML gallery per profile, named in plain ASCII (e.g. "Red car" → `red-car.html`). Clicking a photo opens the original. |
| `thumbnails/` | The galleries' thumbnails. Keep the `results` folder together: a gallery copied on its own has no thumbnails, and links to originals work only on this computer. |
| `results.json` | What the galleries of the last finished search show; the app reads it. Replaced only when a search finishes, so a stopped search keeps the previous results. |
| `marks.json` | Your Match / No match marks. The search never changes it and the cleanup never deletes it. Marks belong to a photo's full path, so moving or renaming a photo drops them. |
| `cache.sqlite3` | Analyses of photos already seen. An interrupted search resumes from here, and new profiles reuse them. Updates that change the image analysis analyze every photo again; the old entries stay until you clean them up. |
| `run.lock`, `run-status.json` | Mark a running search and its progress. They stay after a run and can be deleted when no search runs. |

With several photo folders, galleries name each photo by its folder and path, e.g.
`Event2024\sub\img.jpg`. A photo deleted while a search runs is left out, and the next
one takes its place. At the end of each finished search FrameScout removes thumbnails no
gallery shows and temporary files a stopped search left behind.

### Cleaning up storage

Nothing is deleted silently. **Search & results → Clean up storage** lists what can go:
click **Scan** (it only looks), check the categories, click **Delete selected** and
confirm. Deleting is **permanent** (no Recycle Bin) and not possible while a search runs.

Renaming or moving photos counts as new photos: they are analyzed again, and the old
analyses and marks are listed as "unbound".

| Category | Selected after a scan | What it is |
|---|---|---|
| Temporary thumbnail files | yes | Left by a search stopped while writing the galleries |
| Galleries of renamed or deleted profiles | yes | HTML galleries that belong neither to a current profile nor to the last search |
| Thumbnails no gallery shows | yes | Thumbnails neither the last search nor a kept gallery shows |
| Cache entries of unbound photos | no | Analyses of photos no longer at their path. Unreachable drives are not checked; if a drive letter now belongs to another disk, its photos look unbound too |
| Marks of unbound photos | no | Your marks of photos no longer at their path (only these marks, never `marks.json` itself) |
| Cache entries of older versions or unknown settings | yes | Analyses of an earlier FrameScout version or of command-line-only settings |
| Cache entries of other AI settings | no | Analyses with other person detection settings; used again if you switch back |
| Cache entries of other search models | no | Analyses of another search model; used again if you switch back |
| Reference images no profile uses | no | Images in `references/` that neither `profiles.json` nor its backup names |

"Compact cache.sqlite3 afterwards" (on by default) shrinks the cache file. Only what the
scan listed and is still unused when deleting is deleted. Never deleted: `marks.json`,
`results.json`, `run.lock`, `run-status.json`, the cache file itself, `settings.json`,
`profiles.json` and its backup, and your photos.

### What the numbers mean

FrameScout compares every photo (and every person found in it) with the profile's search
texts and, if any, its reference images. The texts generated from name, context and
features form one search text; each custom search text counts on its own, and the best
one decides.

The main number on a card is the **Score**: how far the best part of the photo lies above
the average image part of this search, in standard deviations. Without reference images,
+2 means "clearly more similar than most image parts in this folder" and 0 means
"average". Text and reference scores are scaled separately before the **weight of the
reference images** mixes them: the default 0.3 means 30 % reference images and 70 % text.
The small numbers below are the raw similarities with the text and the reference images.
Scores depend on the folder searched, so the same photo can score differently elsewhere.
With fewer than ten image parts the gallery shows the raw weighted "Similarity" instead.

### How reliable are the matches?

The score is a relative ranking value, **not a probability and not an identification**.
FrameScout can miss matches or return false ones, especially with large group photos,
small or inconspicuous motifs, and when comparing drawings or artwork with real photos.
Person detection helps with people in group photos; turn it off for other motifs.

## Uninstalling details

`Uninstall-FrameScout.bat` (`--dry-run` only shows the lists) lists what it deletes and
keeps, and deletes only after you type `yes`. Close FrameScout first; the script refuses
while a search or the app runs, or when `settings.json` cannot be read.

- **Deleted:** `.venv`, `.python`, `.cache` (model weights and pip cache), `.tmp` (except
  `.tmp\eval`), `.pytest_cache` and the `__pycache__` folders.
- **Kept:** `photos\`, `references\`, `results\` (with `marks.json`), `profiles.json` and
  its backup, `settings.json`, `run.log`, the evaluation labels and the program files. A
  photo or copy folder from your settings is never deleted, also not when it lies inside
  the project folder.
- **Outside the project folder:** copied matches stay. Caches that FrameScout wrote into
  your user profile when it ran without the `.bat` files (PyTorch, Hugging Face,
  `%APPDATA%\Ultralytics`) are only listed, since other programs may use them.

Afterwards, delete the project folder yourself to remove FrameScout completely. A Python
you installed yourself stays in place.
