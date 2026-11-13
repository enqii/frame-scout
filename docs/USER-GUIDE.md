# FrameScout user guide

The [README](../README.md) covers installation and a quick start. This guide describes
every part of the app in detail. Development, the command line and the evaluation tool
are in [DEVELOPMENT.md](DEVELOPMENT.md).

## Installation details

`Install-FrameScout.bat` downloads python.org's Python 3.14.9 (about 33 MB, checked
against a fixed SHA-256) into the folder `.python`, creates an isolated `.venv` with it
and installs the dependencies in the fixed versions of `requirements/constraints.txt`. An installed
Python is not needed and not used. A working `.venv` is kept, also one from an earlier
installer (Python 3.12 to 3.14 installed on the PC). Running the installer again repairs
an environment that no longer starts or lacks pip, and downloads the private Python again
if it is incomplete or another version.

**Do not move or rename the FrameScout folder after the installation:** `.venv` refers to
`.python` by its absolute path. If you moved it anyway, run the installer again (it
downloads all packages again, several GB with CUDA). If the installation fails twice,
delete `.python` and run it once more.

When you update from a ZIP, extract it into a fresh folder instead of over an old one,
so no files of earlier versions stay behind. If you extracted over an old folder anyway,
`Install-FrameScout.bat` and `Start-FrameScout.bat` delete the leftover `framescout_core.py`
and `framescout_scoring.py` of the older version (if another program holds one open, they stop and ask you to close it).
`Uninstall-FrameScout.bat` and the engine, evaluation tool and `install_torch.py` of this version work in such a folder too.
If you went back to an older version this way, FrameScout stops with an
error that names the file and the folder (`framescout_core` or `framescout_scoring`) to delete.

### Checking the installation

If the app does not start or a search fails after a Windows update, a moved or copied
folder or an interrupted installation, double-click `Check-FrameScout.bat`, or open
AI settings → "Check installation" when the app runs. The check changes nothing, installs
nothing and downloads nothing (it only creates and deletes a small temporary file in
`.cache` and `results` to see whether they can be written). It reports, with one sentence
of what to do for each problem:

- **Program files:** no files of two FrameScout versions in the folder (for example
  `framescout_core.py` next to the folder `framescout_core` after extracting a ZIP over an old
  folder). The fix: delete the file after an update, or the folder after going back to an
  older version.
- **Python environment:** `.venv` belongs to this folder and its Python still exists. After
  a moved or copied folder, delete `.venv` and run `Install-FrameScout.bat`; if the Python is
  missing, run the installer, which repairs it.
- **Packages:** all packages of `requirements/requirements.txt` are installed, in the versions of
  `requirements/constraints.txt` (PyTorch in any build).
- **PyTorch:** it imports (this can take several seconds); an installation with GPU support
  that finds no usable GPU is reported with the hint to update the driver or to run
  `Install-FrameScout.bat cpu`.
- **Writable folders:** `.cache` and `results`.
- **Downloaded files (information only):** the search models and the person detection
  weights that are already downloaded.
- **Free disk space:** a problem below 1 GB on the drive of the FrameScout folder.

`Check-FrameScout.bat` uses the Python of `.venv`, or the private Python in `.python` if
`.venv` does not work, so it can also say why the environment is broken. If neither exists,
or the check cannot run with either, it tells you to run `Install-FrameScout.bat`. In the app,
the results stay until you click the button again; a line above them says when they were
found. A package version that differs from
`requirements/constraints.txt` is a problem only because the verified versions are the tested ones; the
app may still work.

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

Before it downloads PyTorch, the installer checks the free disk space of the drives it
writes to (`.venv` and the temporary folder `.tmp`). It estimates about 0.3 GB download
and 1.2 GB installed for the CPU version, and about 3 GB download and 6 GB installed for
the CUDA version (an estimate). If a drive would keep less than 1 GB free, it lists the
drives and asks `Install anyway? [Y/N]`: a full disk during the installation leaves a
broken installation. `N` stops the installer ("Installation stopped. Free some disk space,
then run Install-FrameScout.bat again."). If PyTorch is installed already but other packages
are missing (e.g. a full disk stopped the previous run), it checks the space they need
(about 0.2 GB download and 0.4 GB installed) the same way. Sizes are in the units Windows
Explorer shows (1 GB = 1024 MB).

The installer picks the build from what `nvidia-smi` reports: CUDA 13.0 for GeForce RTX 20
series or newer (compute capability 7.5+) with driver 580 or newer, otherwise CUDA 12.6
(GTX 900 series or newer, driver 528.33 or newer; RTX 50 series cards need CUDA 13.0).
With several GPUs it prefers a build that suits all of them. If no build fits, it says why
and installs the CPU version. These limits come from the CUDA and PyTorch documentation and
are **not verified**; the GPU path has only been tested on one machine (GeForce RTX 4070, CUDA 13.0),
so treat it as experimental. Person detection can find slightly different boxes on a GPU
than on the CPU, so the order of near-equal matches may differ a little between devices. Under "AI settings" the app shows whether PyTorch can use the
GPU and offers "cuda" only then.

## Using the app

Start `Start-FrameScout.bat`; the browser opens <http://127.0.0.1:8501>. The app has one
tab per step.

If another program already uses port 8501, FrameScout takes the next free port up to 8510
and prints a note; the address in the start window is the one to use. If FrameScout of this
folder already runs (for example in a forgotten window), a second start opens the browser on
that app instead of starting another one. If that app does not answer within 30 seconds, the
start window asks you to close the other window and start again. If no FrameScout window of
this folder is open and the start still says so, delete the file `.tmp\app-instance.lock` in
the FrameScout folder and start again (Windows does not let you delete it while the app
runs). Close the start window or press Ctrl+C in it to stop the app.

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
  creates it from `assets/profiles.example.json` on the first start and never overwrites it.
  Each save keeps the previous version as `profiles.json.bak` (one step only, so restore
  it right after a mistake). An unreadable `profiles.json` is shown as an error and left
  unchanged. If the file was changed elsewhere (by hand or in another tab) since the page
  loaded, the app refuses to save over it and shows the current profiles instead; a page
  left open while the file changed warns you that a click may not have been carried out. Leave
  the empty `profiles.json.lock` alone.

### Photo source

Enter one or more local image folders, one per line (default: `photos` in the project
folder). Subfolders are searched too, and one search covers all listed folders. A folder
listed twice or inside another listed folder is searched once; a missing folder (e.g. a
disconnected drive) is left out with a note. The same folder reached by another path (another drive
letter, a UNC path, a junction) is recognized and searched once. Links to folders inside a
photo folder are followed, but each folder and each photo is searched once, even if it is
reachable through several links or by a hard link. The log and the "Photo source" tab say how many photos and folders were found again that way and searched once.

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

Model downloads go to `.cache` unless you have set `TORCH_HOME`, `HF_HOME`,
`YOLO_CONFIG_DIR` or `XDG_CACHE_HOME` in Windows: the app, the start script and a manual
run then use your folder instead (with only `XDG_CACHE_HOME` set, the model weights go to
its `torch` and `huggingface` folders, as PyTorch and Hugging Face use it themselves; the
person detection model still goes to `.cache`). If you set one after models were downloaded, the first
search downloads them again there (about 600 MB for the default model). The uninstall
script lists such folders outside the project but does not delete them. A `yolo11n.pt` in
the folder of a manual run is used instead of the cached copy.

**Analyze ahead** (end of the tab) analyzes the photos without a search, for example overnight, so
that a later search only has to rank them. The section shows the current search model and
person detection setting, how many photos are analyzed with them already and, if an earlier
search measured a speed, a rough duration. A JPEG or HEIC whose shot is analyzed through its RAW
file (or another file of the shot) counts as analyzed. Press **Analyze photos now** to start; the
button is disabled while a search, an analysis or a cleanup runs and when the model package is
missing. It stays available when the count says all photos are analyzed: the count is the one
from the last "Recount", while the analysis reads the folders again and also finds photos added
since. If the drive of the results may run short of space, a warning is shown here too.
Analyses only help a search with
the same search model and person detection settings: after a change of these, the photos are
analyzed again. An analysis changes no results: the galleries, `results.json`, marks and the
last quick search stay as they are. Progress, "time left" and **Stop** are in "Search & results";
"Keep the PC responsive" applies as for a search. A photo edited after its analysis counts as
not analyzed.

### AI settings

- **Search model:** the default, OpenAI CLIP ViT-B/32, is the fastest and the one the
  settings are tuned for. Optional: ViT-B/16 and ViT-L/14 (DataComp-XL) and SigLIP B/16,
  roughly 4×, 18× and 4× slower on a CPU, with a first download of about 0.6, 1.7 and
  0.8 GB (the list says "downloaded" for a model whose files are already there). They are marked "not evaluated", so treat them as an experiment. The first
  search with a new model analyzes every photo again; the cache keeps each model's
  analyses, so switching back is fast. Scores of different models are not comparable.
  SigLIP needs the package `transformers` (run the installer again on an older
  installation). The command line option is `--model`.
- **Compute device:** "auto" uses CUDA if PyTorch finds a compatible NVIDIA GPU,
  otherwise the CPU.
- **Batch size:** the number of image parts (whole photos and person crops) analyzed
  together; reduce it from 8 if memory runs short.
- **Keep the PC responsive during a search:** off by default. When on, the search runs at
  a lower priority, so other programs get the CPU first, and with fewer CPU threads for the
  AI models; the search may take longer. It does not reserve CPU cores: photo decoding still
  uses its own threads. It helps little when the graphics card does the work. How much it
  slows the search and how much it helps has not been measured yet. The command line option
  is `--low-priority`.
- **Person detection:** finds people with YOLO11n and compares each person separately,
  which helps with group photos. Turn it off for other motifs: JPEGs are then decoded
  at a reduced resolution, which is noticeably faster.
- **Check installation:** an expander at the end of the tab that runs the check of
  [Checking the installation](#checking-the-installation) and shows each result.
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
A repeat search on a folder that is already analyzed (e.g. after changing only a search
text or the reference weight) skips loading the person detector and shows "Nothing new to
analyze – ranking only"; the detector is loaded only when a photo has to be analyzed.

An analysis started in "Photo source" (see "Analyze ahead") is shown here too: "Analysis running
…" with its progress and **Stop**, "about N min left" for the analysis alone (there is no scoring
or gallery step) and afterwards "The last analysis finished successfully" with the number of
newly analyzed photos and those already in the cache. An interrupted or failed analysis is
described as such, not as a search run. If no photo needed a new analysis, the progress line says
"All photos are analyzed already", or, if some photos could not be read, "No photo newly analyzed –
some could not be analyzed, see the log". Only one search or analysis runs at a time.

Before a search the run tab summarizes what it will do: how many photos were found, how many
are already analyzed with the current settings and how many remain to analyze. If an earlier
search with the same settings (search model, person detection) ran on the same device, it also
gives a rough duration for the analysis, plus an upper bound for scoring and writing the
galleries if earlier searches measured those; otherwise it says the search shows how long it
takes after its first minutes. While the search analyzes photos, the progress line adds "about 25 min
left" once about a minute of analysis has been measured (during the analysis it includes
scoring and the galleries once earlier searches measured them; otherwise the line says "left for
the analysis"; after the analysis, also on a repeat search whose photos were all analyzed
before, it names the time left for scoring and the galleries at those speeds); if no photo is finished for five
minutes (e.g. a very large file), it leaves the time out until the search moves on again. The
duration before the start comes from the last search with these settings that measured at
least five minutes (or from a shorter one if there was none). These times are rough: they are
rounded generously (never to seconds) and change with what else the PC is doing. The gallery
part assumes that every thumbnail is new, so on a repeat search it is an overestimate. A photo
that you edited after its analysis counts as not yet analyzed; one edited while the page is open
counts as analyzed until you press "Recount".

Before a search the run tab warns when a drive would keep less than 1 GB free after the
search: it lists the drives with the space needed and the space free, and what the search
writes (cache, thumbnails, and the search model or person detector if they still have to
be downloaded). Only photos not yet analyzed with the current AI settings count for the
cache, so a repeat search of an analyzed collection needs little. The figure is an
estimate, checked again at most every 30 seconds; a drive that does not answer within a
second (e.g. a disconnected network share) is left out. The warning does not block "Start
search"; free some space or lower "Maximum matches per search profile" to reduce the
thumbnails.

**Quick search** (between the search status and **Results**) tries a motif without creating a
profile: type a search text in English (up to 300 characters) and press "Quick search". It
searches only the photos already analyzed with the current AI settings (the caption says
"N of M photos analyzed and searched"; a photo whose same picture in another format, such as the RAW file, is searched is not counted as missing), so it is fast and loads no person detector or analysis;
it is not available while no photo is analyzed, while a search runs or without photo folders.
The result goes to `results/quick/` and appears under "Results of the last quick search"
(thumbnails, 48 per page, "Open"/"Folder" per photo, the gallery and the folder), with the
photo folders it searched and a note if you have chosen other folders since. A new quick
search replaces the last one. The scores are scaled over the photos searched, so they differ
from a search with profiles; a quick search has no marks, copying or export, and it never
changes your profile galleries, `results.json` or marks.

**Find similar** (button on every result card, in "Results" and in the quick results) shows
more photos that look like that one. It compares the photo (or the part named on the card,
e.g. "Person 1") with all other photos already analyzed with the current AI settings; no search
text is used, nothing is analyzed and no model is loaded. The photo itself and the other files
of its shot (a JPEG and the RAW file of the same name) are not part of the result. The result
replaces the last quick
search in `results/quick/` and is shown under "Results of the last quick search or "Find
similar"" (title "Similar to <file>"). The scores are relative to the photos compared, and
shots of a burst may take the top places. If the photo is not analyzed with the current
settings (or changed since), the search stops with a message; start a search with profiles
over its folder first. The button is disabled while a search runs. The HTML galleries have
no button.

**Results** shows the last finished search per profile: thumbnails, best first, 48 per
page, with rank, score, the best-matching part ("Full image" or "Person 1", …) and the
file name. "Open" opens a photo, "Folder" shows it in its folder, and buttons open the
HTML gallery and the `results` folder. A profile changed, renamed or deleted since the
search is marked, since its results no longer fit it.

### Which search text matched

With two or more search texts in a profile (the generated motif texts count as one), each result card
also says **Closest search text: …**: the text that the photo's best-scoring part (the "Full image" or
"Person" the card names) is most similar to. With reference images that part is chosen by text and image
similarity together, so another part of the same photo can be closer to another text. A caption under the
run summary counts how many of the listed photos were closest to each text. This is only a hint: a text often
wins by a small margin and the others can be nearly as close, so a text with a low count did not fail. The HTML
gallery shows the same line per card. Nothing is shown for a single text, for "Find similar" or for results of
an earlier version.

### Marking and copying matches

The results are candidates, not certain hits. Mark a photo you checked as **Match** or
**No match** (or leave it **Undecided**). Marks are kept per profile and photo across
later searches and in every tab. The selected option is colored (green for Match, red for
No match). "Hide photos marked as no match" hides the rejected ones within the page you
are looking at only, so the pages keep their photos and ranks; a caption tells how many
are hidden, and a page where every photo was rejected says so (see the next page).

Above the page box a caption per profile shows your progress, e.g. "100 photos: 30 match,
30 no match, 40 undecided. The first undecided photo is #61 on page 2." (or "Every photo
is marked."). With more than one page, **Go to the first undecided photo** opens that page;
it is disabled while you are on it. Both appear only where marks can be set.

Before each change of a mark FrameScout keeps the previous `marks.json` as `marks.json.bak`
(one generation). If `marks.json` is damaged, the gallery warns that no marks are shown
and, when the backup is readable, offers **Restore marks from backup** with the backup's
date and number of marks. The same offer appears, below the marks, when `marks.json` is
missing but the backup holds at least one mark (e.g. after deleting the file by mistake).
Nothing is restored on its own; until you restore, the next mark you set starts a new
`marks.json` and the backup is kept. The damaged file is kept as `marks.json.broken-<date>`
in the `results` folder; **Clean up storage → Damaged files set aside** offers to delete
it when you no longer need it.

"Copy N marked photos" copies all photos marked as match into the folder in "Copy to
folder" (default `Pictures\FrameScout\<profile>`, saved per profile). Copying never
moves, changes, deletes or overwrites anything: a different photo with the same name is
saved as `name (2).jpg`, an identical one counts as "already there". A target folder
inside a photo folder is refused, since the next search would find the copies again.

### Exporting a result list

Below each gallery, **Export list** writes the ranked photos of the profile to the
`exports` folder inside `results`, e.g. for a program you catalog photos with. Each
export makes two files with the same name, `<profile>-<date>-<time>.csv` and `.txt` (with
"-matches" in the name if you export only matches):

- the **CSV table** has the columns rank, path, score, text similarity, image similarity
  (empty for searches by text only), crop and mark (match, no match or empty);
- the **text file** has one full photo path per line, in rank order.

A photo whose path contains a line break is left out of the text file, since it would
split into two lines; the CSV keeps it, and the notice after the export says how many paths
only the CSV lists.

Tick **Only photos marked as match** to export just the photos of this list you marked as
Match. Photos marked in an earlier search that are not in this list are not exported, since
they have no rank or score here (use "Copy N marked photos" for those). If the marks cannot
be read, only the full list can be exported, with an empty mark column.

An export never replaces a file: if the name is taken, `-2`, `-3`, ... is added. The paths
are those of this computer, so a list may not fit after moving photos or on another PC. The
CSV is comma-separated UTF-8 with a decimal point. Excel with a German (or other `;`) locale
may show everything in one column when you double-click it: use **Data → From Text/CSV**
instead. **Clean up storage** never deletes exports; delete them yourself.

## Supported formats

JPG, JPEG, PNG, WebP, BMP, TIF, TIFF, AVIF, HEIC/HEIF and camera RAW (DNG, CR2, CR3, NEF,
ARW, ORF, RW2, RAF, PEF, SRW).

- For a RAW file FrameScout uses the camera's embedded JPEG preview if it is at least
  1024 pixels long, otherwise it decodes the RAW data at half size. Colors are the
  camera's, not your own RAW development.
- If a JPEG or HEIC of the same name is next to a RAW file ("RAW+JPEG" mode), only the
  JPEG/HEIC is searched. If that JPEG cannot be read, or is cut off or damaged in the middle, the RAW file is analyzed instead. A JPEG that lacks only its end marker is searched itself. A HEIC that is cut off fails (it is counted as a failed photo) instead of being searched as a black image.
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
model may become an option later (E21 in [docs/BACKLOG.md](BACKLOG.md)).

## Results

Everything a search writes lands in `results/`:

| File | What it is |
|---|---|
| `<profile>.html` | One HTML gallery per profile, named in plain ASCII (e.g. "Red car" → `red-car.html`). Clicking a photo opens the original. |
| `thumbnails/` | The galleries' thumbnails. Keep the `results` folder together: a gallery copied on its own has no thumbnails, and links to originals work only on this computer. |
| `results.json` | What the galleries of the last finished search show; the app reads it. Replaced only when a search finishes, so a stopped search keeps the previous results. |
| `quick/` | The last quick search: `quick.html`, `results.json` and `thumbnails/`. A new quick search replaces it; **Clean up storage** does not look into it. |
| `marks.json` | Your Match / No match marks. The search never changes it and the cleanup never deletes it. Marks belong to a photo's full path, so moving or renaming a photo drops them. |
| `marks.json.bak` | The state of `marks.json` before your last change of a mark (one generation). If `marks.json` is damaged, the gallery offers to restore it. The cleanup never deletes it. |
| `marks.json.broken-<date>`, `cache.sqlite3.broken-<date>` | Damaged files FrameScout set aside when you restored the marks or renamed the cache. They are never deleted on their own: **Clean up storage → Damaged files set aside** lists them (unselected). |
| `cache.sqlite3` | Analyses of photos already seen. An interrupted search resumes from here, and new profiles reuse them. Updates that change the image analysis analyze every photo again; the old entries stay until you clean them up. |
| `exports/` | Result lists you exported (CSV and text files, see above). Created on the first export; the cleanup never deletes them. |
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
| Cache entries of unbound photos | no | Analyses of photos no longer at their path. Unreachable drives, folders that do not answer within 30 seconds and links (junctions, mounted drives) whose target cannot be reached are not checked (a note names them); on Linux/macOS an empty folder at a mount point (e.g. under `/media` or `/mnt`) counts as an unmounted drive and is not checked either (mount it and scan again, or delete the empty folder first if the photos are gone for good), and so does a drive folder that is missing right in `/media/<user>`, `/run/media/<user>`, `/Volumes` or `/mnt` (removed on unmount; mount it and scan again); if a drive letter now belongs to another disk, its photos look unbound too |
| Marks of unbound photos | no | Your marks of photos no longer at their path (only these marks, never `marks.json` itself) |
| Cache entries of older versions or unknown settings | yes | Analyses of an earlier FrameScout version or of command-line-only settings |
| Cache entries of other AI settings | no | Analyses with other person detection settings; used again if you switch back |
| Cache entries of other search models | no | Analyses of another search model; used again if you switch back |
| Marks of deleted profiles | no | Your marks saved under a profile name that no profile in `profiles.json` has now, listed as "<profile>: N marks" (only these marks, never `marks.json` itself; not offered if `profiles.json` or `marks.json` cannot be read). If you create a profile of that name before deleting, its marks are kept |
| Reference images no profile uses | no | Images in `references/` that neither `profiles.json` nor its backup names. After a rename whose backup rewrite failed, the old names are offered after the next save of the profiles |
| Damaged files set aside | no | `marks.json.broken-<date>` and `cache.sqlite3.broken-<date>` (with their `-journal`/`-wal`/`-shm` files) in `results` |

"Compact cache.sqlite3 afterwards" (on by default) shrinks the cache file. Only what the
scan listed and is still unused when deleting is deleted. Never deleted: `marks.json`,
`results.json`, `run.lock`, `run-status.json`, the cache file itself, `settings.json`,
`profiles.json` and its backup, and your photos.

**Check cache** (below the cleanup) tests `cache.sqlite3` for damage, e.g. after a full
disk or a power loss. It changes nothing in the cache, except that the unfinished changes
of a stopped search (a leftover `cache.sqlite3-journal`) are rolled back first, as the next
search would do. It is refused while a search runs or is being started. The result is one
of: no cache yet, no damage found, could not be checked (e.g. the file is locked by another
program; nothing is offered), could not be read (a disk I/O error: a damaged spot on the
disk, or a drive or network share that is not reachable now), or damaged. For a damaged or
unreadable cache, **Rename the damaged cache.sqlite3** renames it (and its
`-journal`/`-wal`/`-shm` files) to `cache.sqlite3.broken-<date>`; nothing is deleted. For
an unreadable cache, check again first if the drive may just have been unreachable. The
next search then analyzes all photos again. Delete the `.broken-` file when you do not need it:
**Damaged files set aside** in the cleanup lists it. A shown result disappears once the cache changes (e.g. after a cleanup or a
search); check again then. A search on a cache that cannot be opened or written stops with a
message that points here; if only some photos cannot be read from it, the search leaves them
out, finishes, and the app shows a warning that names their number and points here.

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
while a search or the app runs, or when `settings.json` cannot be read. It runs with the
private Python in `.python`; for an installation of an older installer it uses the Python
that created `.venv` or the `py` launcher, and says so if it finds none.

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
