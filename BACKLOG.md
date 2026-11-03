# FrameScout – Backlog

Open work: known weaknesses and ideas, nothing is checked off here. Result of the code
analysis from 2026-10-20 (state v1.1), extended by every pull request since. IDs
(E = engine, A = app, I = installation/project, F = feature, taken over from
[docs/IDEAS.md](docs/IDEAS.md)) are referenced in commits, pull requests and discussions.

- **Finished items** move to [docs/BACKLOG-DONE.md](docs/BACKLOG-DONE.md) with their
  reports when their PR is merged; the ID stays valid (search both files for it).
- **The order of work** is in [ROADMAP.md](ROADMAP.md). An item in this file that the
  roadmap does not name is not scheduled.
- **A new ID** is the next free number of its group: search both files, e.g.
  `rg -o "\*\*E\d+ " BACKLOG.md docs/BACKLOG-DONE.md`, and take the highest plus one.
- **Status tags** are set by `/triage` (untagged = not triaged yet) and written in
  backticks before the ID, e.g. ``- [ ] `minor` **E39 – …**``:
  `ready` (clear scope, can be implemented now), `decision` (needs a user decision first;
  the item names the question), `hardware` (needs the home PC), `minor` (small or rare;
  bundled into a hygiene PR), `parked` (deliberately not planned now; the item gives the
  reason).
- **Ideas** (`docs/IDEAS.md`) become group F items only through `/triage`.

## Known weaknesses

### Engine (`framescout_engine.py`)

- [ ] `hardware` **E15 – No `Image.draft` with person detection:** since E2 photos are decoded at
      reduced scale only without person detection; with detection they keep full
      resolution, because a person crop in a group photo can be smaller than CLIP's
      224 px input after scaling. Drafting to a larger size (e.g. both edges ≥ 1280 px)
      would speed up the decoding of large photos (≥ ~10 MP), but changes the person crops
      and needs an evaluation with group photos (search quality) and possibly scaling the
      minimum crop size of 35×70 px with the draft factor.
- [ ] `hardware` **E17 – Thread counts are not tuned for small CPUs:** PyTorch uses up to 12 threads
      (`torch.set_num_threads(min(12, …))`, from the logical core count, also when the
      process may use fewer cores), and since E2 up to four decoding threads (two with
      person detection) preprocess crops with torch at the same time, YOLO included. On
      the 24-thread development PC pinned to 4 cores the E2 engine was still faster than
      before (200 photos: 33.5 s → 20.2 s without, 55.1 s → 45.6–47.7 s with person
      detection), but the gain with detection shrinks and timings are noisy (PR #7
      review). Fix idea: measure on a real 4–8 core machine; derive the torch threads from
      the cores the process may use and the decoding threads, or convert crops to tensors
      on the main thread. Measure E52 (the F4 low-priority option) in the same session.
- [ ] `hardware` **E18 – Person detection is still one photo per call:** since E14 YOLO runs on the
      CLIP device, but the decoding threads still call it one photo at a time under a lock,
      and with detection only two decoding threads run (`DETECTION_DECODE_THREADS`, chosen
      for the CPU and the memory of full-resolution photos). On a GPU, detection is fast
      and decoding may become the limit. Passing several photos per call is not a pure
      speed change: Ultralytics pads photos of different shapes in one call to a square
      (`LetterBox(auto=False)`) instead of the smallest rectangle, so the detected boxes
      and the person crops change → needs an evaluation of search quality first, and the
      gain can only be measured on a GPU. **Data (I11, PR #56, RTX 4070, ViT-B/32,
      4997 full-size camera JPEGs, 7 profiles, `--batch-size 16`):** with person detection
      348 s on CUDA (486 s on CPU), without 93 s on CUDA, so detection dominates a CUDA run
      and is the GPU bottleneck. Deferred from the roadmap item "YOLO on
      GPU" (PR #8, user decision).
- [ ] `parked` **E19 – The detection settings in the cache signature are listed by hand:**
      `feature_signature` hashes `max_persons`, `person_confidence` and `yolo_model`, but
      not the YOLO input size (`DETECTION_IMAGE_SIZE`, 640) or the other fixed
      `detection_options`; changing them needs a manual `ENGINE` bump (a comment and the
      golden test of `detection_options` ask for it). Deriving the signature from
      `detection_options` (without device and verbose) removes that step, but changes the
      signature value and so re-analyzes every photo once → do it with the next `ENGINE`
      bump. The device stays out on purpose: CPU and CUDA give slightly different numbers
      for CLIP as well, and the cache has always been shared between devices (PR #8 review).
- [ ] `hardware` **E20 – Search quality is measured on one collection only:** the evaluation of E4/E5
      (PR #11) used about 5,000 studio photos of cosplays from one convention, five
      text-only profiles (Joker, Harley Quinn, 2B, Group photo, Sword) and three with
      reference images, 12–47 hits each, so differences of a few hundredths are noise.
      The ensemble (E4) was not better for every profile (Harley Quinn: text-only AP@40
      0.515 → 0.472). Outdoor, object, animal or landscape photos are not measured; of
      the extra profiles, "Outdoor scene" could not have hits and "Group photo" was
      saturated, because the profiles were chosen without looking at the collection.
      Since 2026-10-26 (PR #32) the repository has reusable, documented tooling for such
      measurements (`framescout_eval.py`, E32) that supports several collections; the
      labels and scripts of PR #11 stay outside the repository. Keep this item open until
      a second, non-cosplay collection has been measured (choose its profiles after
      looking at a sample of the collection: profiles without hits or saturated ones say
      nothing).
      Next evaluation (e.g. for stronger models, E22, or a multilingual one, E21): look at
      a sample of the collection or ask the user first, and use a second, non-cosplay
      collection. The tooling (`evaluate.py`, labelling page, metrics) and the labels
      live outside the repo (now under `.tmp/eval-labels/` in the original checkout);
      consider a reusable, documented version.
- [ ] `decision` **E21 – No multilingual search:** FrameScout supports English search terms only
      (E3, user decision in PR #12: "consider a multilingual CLIP later"). Option: the
      OpenCLIP model `xlm-roberta-base-ViT-B-32` (`laion5b_s13b_b90k`) as an optional
      model choice next to OpenAI CLIP (default). Costs found in PR #12, not verified by a
      run: about 1.47 GB of weights plus about 10 MB of `xlm-roberta-base` config and
      tokenizer on the first use; a new dependency `transformers` (with `tokenizers`;
      Python 3.14 untested); its own image tower, so its own cache signature (`engine_id`, E22)
      and every photo analyzed once more (old rows stay, E11); roughly +1 GB RAM;
      analysis speed per photo about the same (same ViT-B/32 image tower); the default
      reference weight (0.3, E5) was tuned on OpenAI CLIP and must be evaluated again
      (E20). Model card: ImageNet 62.3 % (English), Italian ImageNet 43 % vs 21 % for an
      English B/32; no German figure. Other multilingual OpenCLIP models:
      `ViT-B-16-SigLIP-i18n-256` (about 1.48 GB), `nllb-clip-base` (about 2 GB). Builds
      on the model choice of the roadmap item "Optional stronger models" (E22): one more
      registry entry with `multilingual=True`, and the "in English" hint of the app and
      the user guide depends on the selected model. SigLIP 2 (a candidate of E22) has a
      multilingual tokenizer and training data and may cover this item as well; check
      it with German queries before adding `xlm-roberta-base-ViT-B-32`. A download and a
      new dependency are hold points. **Status after E22 (PR #31):** the registry and its
      `multilingual` flag exist, but all offered models are English-only and the "in
      English" hint does not depend on the model yet.
- [ ] `decision` **E29 – HEIC/RAW support as optional extras:** E25 made `pillow-heif` and `rawpy`
      required in `requirements.txt` (user decision at the PR #26 hold point; the user may
      want them optional later). Idea: a separate requirements file, a question in
      `Install-FrameScout.bat`, and the engine's existing fallback (formats without their
      package are skipped with a note). Roadmap candidate, not scheduled.
- [ ] `hardware` **E32 – The offered search models are not evaluated:** E22 offers ViT-B/16 and
      ViT-L/14 (DataComp-XL) and SigLIP B/16 next to the default, marked "not evaluated"
      (`SearchModel.evaluated`), because their search quality has not been measured.
      Follow-up PR of E22 (user decision: two PRs). **Tooling delivered 2026-10-26 in
      PR #32** (user decision: that PR builds only the tooling): `framescout_eval.py`
      (`run` / `pool` / `label` / `metrics`, `docs/DEVELOPMENT.md` "Evaluating the search models",
      ARCHITECTURE "Model evaluation tool") computes AP@40 per profile and model, a
      reference-weight sweep per model and supports several collections (E20); the engine
      got `--scores-file`. **Remaining (a later PR):** the user labels a pool on the home PC
      (Core i5-13600K, RTX 4070) for the cosplay collection and a second, non-cosplay one;
      then record the run metrics, choose the reference weight per model (0.3, E5), trim
      `MODELS`, set `evaluated`, and update the labels and the user guide. The tool itself was
      run with real models (E34, done). **First data (2026-11-01, PR #56, raw evidence,
      no conclusion drawn):** the user labelled 6 of 7 profiles of a local studio-event
      photo set (about 1600 pool photos; the profile "armor" was left unlabelled because it
      is very hard to judge). Mean AP@40 at reference weight 0.3: vit-b-32-openai 0.673,
      vit-b-16-datacomp 0.697, vit-l-14-datacomp 0.722, vit-b-16-siglip 0.739; the ranking
      of the models changes per profile, and the profile "group photo" had 146 of 146
      hits, so it is not informative. A second, non-specialized collection is still
      missing. A key trimmed from the registry falls back to the default with
      a warning in a user's `settings.json` (`read_settings`); its cache rows then count as
      "older version" in the cleanup. Search quality is a hold point.
- [ ] `minor` **E36 – Labels do not record the motif they were made for:** `labels.json` keys a
      label by profile name and photo path only. Editing the prompts under the same name
      keeps the labels (intended: prompt wordings can be compared on the same labels), but
      a profile whose motif changes under the same name (context, features, reference
      images) silently reuses labels made for the old motif, and the "profile has changed"
      warning of `pool`/`metrics` disappears once every model has been run again. Today
      `docs/DEVELOPMENT.md` asks for a new profile name instead. Fix idea: store each profile's
      context, features and reference images in `labels.json` when a label is set and warn
      in `pool`/`metrics` when they differ. Found in the review of PR #32 (E32).
- [ ] `minor` **E37 – The unbound check guards only the root probe with a timeout:** a folder
      listing or `stat` on a share that hangs during the pass stalls the scan (the page
      run) until the OS gives up; a junction or mount point inside a reachable root that
      leads to a disconnected volume can make its photos look gone (the deletion
      re-checks, but the volume would have to be back by then). Idea: run the pass in a
      worker thread with a per-folder timeout, or treat folders on other volumes than
      their root as their own root. Found in the PR of E8.
- [ ] `hardware` **E38 – The online fallback and the first download are not runtime-tested:**
      `framescout_core.model_cached` decides from the hub cache whether a model loads
      offline (E16, P7 A). An engine search ran with the default model only; SigLIP
      (`vit-b-16-siglip`) loaded offline with its tokenizer from a complete cache in a
      Python check (PR #41 review), and with an empty cache the offline errors of open_clip
      and of the SigLIP tokenizer were checked to take the fallback (`hub_file_error`). The
      fallback after an incomplete cache (`load_with_hub_fallback` going online and
      downloading what is missing) and the first download into an empty cache were covered
      by unit tests only, since a real run downloads at least 605 MB. Verify on the home PC
      (P10 A, next to E34) and fix what shows up. Found in the PR of E16.
- [ ] `minor` **E39 – open_clip's URL download path ignores the cache variables (minor):** a model
      without an `hf_hub` config would be fetched by `download_pretrained_from_url` into
      `~/.cache/clip` regardless of `TORCH_HOME`/`XDG_CACHE_HOME`. Not hit today: every
      `framescout_core.MODELS` entry downloads through the Hugging Face Hub. A future model
      without `hf_hub` would need `cache_dir=` passed to open_clip. Found in the PR of E9/I10.
- [ ] `minor` **E40 – A `yolo_weights` test only holds on Windows (minor):** `test_yolo_weights_paths_and_urls_are_used_as_given`
      passes `r'models\w.pt'` and expects it back unchanged; on Linux/macOS `Path(name).name`
      is the whole string, so `yolo_weights` treats it as a bare name and the test fails
      (CI runs on Windows only). Fix: check the backslash case with `PureWindowsPath` or skip
      it off Windows. Review of PR #42, finding 6.
- [ ] `decision` **E41 – A user's own `yolo11n.pt` in the working folder is ignored once a cached copy
      exists:** `yolo_weights` looks in the cache folder first and in the working folder only
      afterwards, so the "used as before" file of the working folder loses against any copy in
      `.cache/ultralytics/`. Decide which one should win (a copy the user put next to the run
      is arguably more deliberate) and document it. Review of PR #42, finding 7.
- [ ] `decision` **E42 – The engine sets the cache variables when it is imported:** `default_cache_env`
      runs at module level in `framescout_engine.py` (so it precedes the torch import), which
      changes `HF_HOME`, `TORCH_HOME` and `XDG_CACHE_HOME` for every importer of the module and
      means models cached in the user profile are no longer found by a manual run (documented
      consequence of E9/I10). Decide whether to move it into `main()` (the heavy imports are
      lazy or must be reordered; `tests/test_engine_defaults.py` pins the module-level call)
      and whether a note or an opt-out is needed for users who keep models elsewhere. Review of
      PR #42, findings 8 and 9.
- [ ] `hardware` **E43 – `yolo_weights` returns a path in `.cache/ultralytics/` without creating the folder
      (not verified):** Ultralytics should create the parent folder when it downloads to that
      path, but this was not run; if it does not, the first download fails. Check on the first
      download into an empty cache (P10 A, next to E38) or create the folder in
      `yolo_weights`/the engine. Review of PR #42, finding 10.
- [ ] `minor` **E44 – Temporary files of the app's atomic writes in the project folder stay after a
      kill (minor):** `profiles.json.<random>.tmp`, `settings.json.<random>.tmp` (and the
      write of `profiles.json.bak`) remain if the app process is killed during a write. No
      cleanup removes them: `auto_cleanup` only looks at `results/`. Small and rare. Found
      in PR #45.
- [ ] `parked` **E45 – `publish_export` is not one step across files (minor):** a kill between the
      renames (milliseconds) can still leave some galleries newer than `results.json`. A
      rename that fails every retry (a file held open for over 2 s; the run then fails)
      restores the files renamed before it, but if a restore fails too, they stay new.
      Idea, if it ever matters: a versioned gallery subfolder that `results.json` names.
      Found in PR #45.
- [ ] `minor` **E46 – A merely truncated JPEG partner does not trigger the RAW fallback:** the
      engine sets `ImageFile.LOAD_TRUNCATED_IMAGES = True`, so a JPEG with an intact header
      but missing data decodes without an error (the missing part gray) and the E30
      fallback never runs; only partners that fail to decode (corrupt header, unreadable
      file, broken HEIC) fall back. Idea: for partners of a RAW file, detect truncation
      (Pillow's truncation warning, or a decode with `LOAD_TRUNCATED_IMAGES` off) and
      prefer the RAW file then. Found in PR #46.
- [ ] `minor` **E47 – The best-weight mark of `framescout_eval.py metrics` is set on a tie at 0:**
      in the reference-weight sweep, every weight gets the `*` (best) mark when a model's
      best AP is 0 (all weights tie at 0). Fix: mark nothing then. Found in PR #56.
- [ ] `ready` **E48 – `framescout_eval.py run --cache-dir` follows the script folder, not the venv's checkout:**
      the default is the `.cache` next to the script, so running the tool from a git
      worktree downloads the models again unless the main checkout's `.cache` is passed
      with `--cache-dir`. Document it in `docs/DEVELOPMENT.md` (done in PR #56) and/or make
      the default follow the checkout of the Python environment in use. Found in PR #56.
- [ ] `minor` **E49 – `framescout_eval.py pool` imports the whole engine to render thumbnails:**
      `load_renderer` imports `framescout_engine` (torch, numpy, Pillow, a few seconds) for
      `render_thumbnail` alone, and the import sets the cache variables of the process
      (E42). Only when thumbnails are missing, once per pool run. Fix idea: move the image
      decoding (`open_image`, `open_raw`, `raw_preview`, `render_thumbnail`, the decoder
      registration) into a torch-free module that the engine and the evaluation tool both
      import; that also drops the fallback for a missing engine and the ast-based test. An
      engine refactor with its own smoke run. Review of PR #56, finding 2.
- [ ] `minor` **E50 – A search on a damaged `cache.sqlite3` fails with SQLite's raw error:**
      `run.log` shows "file is not a database" or "database disk image is malformed". The
      engine could catch `sqlite3.DatabaseError` when opening or reading the cache and point
      to "Clean up storage" -> "Check cache". Found in F1 (PR #60).
- [ ] `minor` **E51 – `framescout_eval.py` has no free disk space check:** it loads (and on
      first use downloads) search models without the F3 check; only app searches and the
      installer are covered. Found in F3 (PR #64).
- [ ] `hardware` **E52 – The effect of `--low-priority` is not measured:** F4 lowers the engine's
      process priority and keeps one or two cores out of the PyTorch threads (`torch_threads`,
      also for the person detector), but neither the
      slowdown of the search (CPU and GPU) nor the gain in responsiveness of other programs
      (e.g. a second CPU-heavy task running at the same time) was measured. Measure it on the
      home PC together with E17 (P10 B); from the results adjust how many cores
      `torch_threads` leaves free, or also lower the decoding threads (E2), which are not
      reduced now. Found in F4 (PR #65).

### App (`app.py`)

- [ ] `parked` **A15 – Reference folder and gallery file can get different suffixes:**
      `reference_folder` adds `-2`, `-3`, … when another profile's references occupy the
      folder, `profile_slugs` adds them by profile order. The same profile can therefore
      have `references/red-car-2/` but `red-car.html` (or the reverse). Nothing breaks,
      but the names are harder to explain. Fix idea: derive the folder from
      `profile_slugs` with a fallback for occupied folders – note that the order-based
      slugs change when profiles are deleted or reordered, which would then move folders
      (design decision, PR #6 review).
- [ ] `parked` **A18 – ZIP export (roadmap P4 (C)): open decision.** Asked in PR #14 and deferred to
      P4 (C). **Deferred by the user on 2026-10-25** ("skip this feature for now"): copying
      of P4 (B) already collects the photos; a ZIP only matters for sharing or archiving an
      overview. The Q6 decision below (content a/b/c, one vs. two buttons) is still pending
      and must be asked again when this item is picked up. Q6 – content: (a) the gallery HTML with its links rewritten to a
      `thumbnails/` folder in the ZIP, plus those thumbnails, about 3 MB per 150 cards, as
      a browser download; the links to the originals stay `file://` and work only on
      this computer (recommended); (b) as (a) plus larger previews (~1200 px, ~250 KB
      each, about 40 MB per 150 cards) so the ZIP can be viewed on another computer
      (Pillow in the app; it is already a dependency); (c) as (a) plus the originals
      (can be gigabytes, written to disk; copying of P4 (B) covers this). Scope: (a) two
      buttons, all cards and marked only (recommended); (b) all cards only. It replaces
      the app's "Download HTML (without thumbnails)". The HTML rendering would move from
      the engine to `framescout_core` so the app can write a gallery of the marked photos.
- [ ] `parked` **A19 – "Open" and "Folder" are checked on Windows only:** the gallery buttons of P4
      (A) open a photo with `os.startfile` and select it with the shell function
      `SHOpenFolderAndSelectItems` (checked on Windows 11 from the app in a browser,
      also with a space and a comma in the path; `explorer /select,` did not select a file
      with a comma). On macOS (`open`, `open -R`) and Linux (`xdg-open`, which opens the
      folder without selecting the file) they are untested. They act on the computer the
      app runs on, which is the user's own as long as the app listens on `127.0.0.1`.
      The same holds for "Open target folder" of A17, whose default target uses
      `~/Pictures` outside Windows (untested).
- [ ] `decision` **A20 – Marks do not feed back into the search:** marks (A17) are only used to copy
      matches. Photos marked as match could serve as extra reference images and photos
      marked as no match as "not this" examples of a profile, e.g. by lowering the score
      of photos similar to the rejects. This changes search quality, so it needs a local
      evaluation set first (hold point). Out of scope of P4 (B) (user decision on A17).

- [ ] `parked` **A30 – Only one backup generation of `profiles.json`:** the user chose a single
      `profiles.json.bak` in PR #6 and again in the PR of A13 (hold point), so the backup is
      the state before the last save only and the next save replaces it. Options if more
      are wanted: rotate N generations (`.bak` newest, then `.bak.1`, ...); timestamped
      backups; a one-time copy before the v3 conversion. Consequences to handle then:
      cleanup (E7, A14) must keep the reference images of all generations, and
      `update_backup_references` (rename of the photo/reference folder) must rewrite all
      of them. How many generations is a user decision. Split from A13.
- [ ] `minor` **A31 – A click on a profile form that no longer exists is dropped silently:** if
      another session shortened the profile list, a form submit or button of a form that
      the page no longer shows is not delivered by Streamlit, and the app shows no
      message (found in the PR of A13, not reproduced beyond the reading of the code).
      Fix idea: tell the user when the profile list changed under an open page.
- [ ] `minor` **A32 – `update_backup_references` runs outside the lock of `profiles.json`:** after
      a folder rename the paths in `profiles.json.bak` are rewritten without the
      `profiles.json.lock` that `save_profiles` holds (A13), so it could in theory
      rewrite a `.bak` that another session has just replaced with newer state. Probably
      harmless (it only rewrites paths of the moved folder); not analysed. Found in the
      PR of A13.
- [ ] `minor` **A34 – Marks left by profiles deleted before A22 stay in `marks.json`:** they still
      pass to a new profile of that name, and "Clean up storage" never offers them because
      `marks.json` is in `NEVER_DELETED`. No migration was done. Idea: offer to delete the
      marks of names that are no profile (asking first), or show them when such a profile
      is created. Found in the PR of A22.
- [ ] `decision` **A35 – A drive letter now used by another disk counts as reachable:** e.g. a USB
      disk that got the letter of an earlier disk, or a network drive mapped to another
      share; the photos of the earlier disk then look unbound and are offered by "Cache
      entries of unbound photos" and "Marks of unbound photos". The same on POSIX: the root
      of every path is `/`, which always exists, so the photos of an unmounted mount (e.g.
      `/mnt/nas`) look unbound (review of PR #40, findings 1 and 2). Mitigated in PR #40:
      the category lists its folders with their photo counts and its help asks to check
      them, and (user decision) neither category is selected by default any more. Idea:
      record the volume serial number (or mount) per root, which changes the cache or a
      side file (hold point). Found in the PR of E8.
- [ ] `decision` **A36 – The app overwrites cache variables a user set, the engine keeps them:**
      `cache_env()` in `app.py` assigns all of `cache_paths(BASE)` to the engine's environment,
      while `default_cache_env` keeps a value that is set. A search from the app therefore
      ignores e.g. a `HF_HOME` the user exported, a manual run honours it. Probably intended
      (the app keeps the install self-contained), but undecided and undocumented; decide and
      document, or use `default_cache_env` in the app too. Review of PR #42, finding 12.
- [ ] `minor` **A37 – Photos found through a second path are dropped silently:** since A28/A29
      `scan_each_folder` lists a photo reached through a link, another path or a hard link
      once, under the first path, and neither the engine log nor the app's per-folder
      count says how many were dropped, so the count can be lower than what a file manager
      shows. Idea: count the duplicates in the scan (e.g. a field of `PhotoScan`) and add a
      line like `skipped_lines` ("12 photos found again through another path, analyzed
      once"). Review of PR #50, finding 5.
- [ ] `minor` **A38 – The style block of the mark colors may take a layout slot:** the gallery
      writes the `<style>` block of `mark_style` (A24) with `st.markdown` on every run of the
      gallery fragment, outside the keyed card container, so it may add an empty element
      with the block gap above the cards. `st.html` with only style tags goes to Streamlit's
      event container and takes no space, but whether a fragment rerun then replaces the
      old block or keeps stale rules of earlier marks next to the new ones was not checked;
      `st.markdown` in the fragment is replaced on every run. Check both in a browser
      (light and dark theme) and switch if `st.html` is clean. One selector per card stays:
      the state of a mark is not in the DOM, and a page holds at most 48 cards. Review of
      PR #55, finding 6.
- [ ] `minor` **A39 – The model list shows a download size for cached models:** the app's
      model list shows "605 MB download" for a model even when its weights are already in
      the cache. Idea: look for the weights file in the cache folder and show "downloaded"
      instead. Found in PR #56.
- [ ] `minor` **A40 – `*.broken-*` files are not offered by "Clean up storage"; no restore for a missing `marks.json`:**
      `marks.json.broken-*` and `cache.sqlite3.broken-*` are never deleted by FrameScout, so
      the user deletes them by hand in the results folder (the notices say so); a cleanup
      category for them (default off) could be added. Also, when `marks.json` is missing (e.g.
      the user removed the damaged file as the old warning advised) but `marks.json.bak`
      exists, no restore is offered. Found in F1 (PR #60).
- [ ] `minor` **A41 – "Copy 1 marked photos" has no singular:** the copy button in `app.py`
      (`show_copy`) reads "Copy 1 marked photos" for a single photo, unlike the export button
      ("Export 1 photo"). Small wording fix. Found in F5 (PR #67).
- [ ] `minor` **A42 – The exported file list cannot hold a path with a line break:** the `.txt`
      of the result list export (F5, `export_file_list`) has one path per line, so a path that
      contains a line break (possible on Linux/macOS file systems, not on Windows) would be
      split; the CSV quotes it correctly. Only relevant for a later non-Windows build; then
      skip such paths with a notice or offer a NUL-separated list. Found in F5 (PR #67).

### Installation / project

- [ ] `parked` **I2 – Tests are incomplete (umbrella; parked: tests are added with each item):** (partly done 2026-10-21: `pytest` scaffold and tests for
      `framescout_core` – slugs, `EXT`, profile loading/validation, prompt generation.
      CI done 2026-10-21: `.github/workflows/tests.yml` runs `pytest` on Windows,
      Python 3.12–3.14, without torch.
      2026-10-21 (5): tests for reading/saving `profiles.json`, reference folders and
      export thumbnails.
      2026-10-21 (E2): tests for the analysis pipeline helpers (batching, prefetching,
      draft size, when progress lines are due); the engine's decoding with `Image.draft`
      is not unit-tested, since CI installs no Pillow.
      2026-10-21 (A7/I3/E14): tests for the choice of the PyTorch build, `install_torch.py`
      (nvidia-smi and pip replaced) and the device choice of the app; the `.bat` file
      itself is not tested in CI.
      2026-10-21 (A4/A5): tests for the run lock (also released when its process is
      killed), the status file and the app's run state.
      2026-10-21 (A8): tests for reading and saving `settings.json`; the app's use of it
      was checked with Streamlit's `AppTest` (not in CI) and, since `AppTest` does not run
      the browser frontend and missed the jumping-back controls, with a script that
      drives the real frontend in headless Microsoft Edge over the DevTools protocol
      (kept outside the repo; not in CI).
      Open: tests for cache signature/reuse and scoring; tests of `app.py` itself (e.g.
      Streamlit's `AppTest`, which needs Streamlit in CI); a smoke test with real models.)
- [ ] `minor` **I4 – Installer requires the `py` launcher;** without it, the misleading message
      "Python 3.12 to 3.14 not found." is shown.
- [ ] `decision` **I9 – CI action pins are updated by hand only:** `.github/workflows/tests.yml`
      pins `actions/checkout` and `actions/setup-python` to commit SHAs (with a version
      comment). That avoids moved tags, but security and runtime updates
      (e.g. a Node.js deprecation on the runners) only arrive when someone bumps
      the SHAs. Options: periodic manual bump, or Dependabot for `github-actions`.
      Dependabot opens its own PRs outside the one-PR-per-roadmap-item workflow, so
      this is a workflow decision → hold point.
- [ ] `hardware` **I11 – The CUDA path is untested on a fresh install and on other GPUs:**
      what remains: a fresh `Install-FrameScout.bat cuda` (about 2.5 GB download; the
      `.venv` already had `cu130`, and only a dry run of the torch step was done), `cu126`
      and the support limits in `framescout_core.CUDA_BUILDS` (not verified), other GPUs
      and several GPUs (check which one `cuda`, device 0 in CUDA's order, uses when the
      build cannot use all of them), and the app's device choice with a CUDA build on a
      real search (the settings tab was only seen in headless Edge).
      (partly done: user-approved runs on the home PC from the main checkout, NVIDIA GeForce
      RTX 4070 with 12 GB, driver 616.56, `.venv` with torch 2.14.1+cu130, Python 3.14.
      2026-10-21: 300 synthetic 1600×1200 JPEGs, `--device cuda` and `cpu`, both exit 0,
      embeddings identical up to float16. 2026-11-01, PR #56: 400 synthetic photos (JPEG,
      HEIC, PNG), CUDA 22 s vs CPU 34 s, without person detection 13 s vs 21 s, `--device
      auto` picks CUDA for CLIP and YOLO; then 4997 real full-size JPEGs (about 13 GB) with
      7 profiles: CUDA 348 s, CPU 486 s, CUDA without person detection 93 s. Full-image
      embeddings are identical (minimum cosine 1.000000); YOLO boxes differ slightly
      between devices, so person crops differ (9253 vs 9249 crops; best-matched crops mean
      cosine 0.99977) and the top 20 of a profile overlaps 19 to 20 of 20 between the
      devices. The installer's torch step was run dry (no argument keeps `cu130`, `cuda`
      recognises the RTX 4070 with compute capability 8.9, `cpu` would replace it); all four
      search models and the evaluation tool ran on CUDA with real models. The speed numbers
      feed E18 and P10 (B).)
- [ ] `minor` **I13 – Background runs die with the agent session:** a long engine run that an
      agent starts as a background command of Claude Code ends when that agent session
      ends; the first evaluation run of PR #11 stopped at 1,110 of 4,997 photos (stale
      `run-status.json` in phase "analyzing", the lock released by the OS). It completed
      when started detached through WMI (`Win32_Process.Create` with a `.cmd` file that
      sets the cache variables). Long smoke or evaluation runs in the PR workflow should be
      started detached (and the agent should wait for their end) — document it in the
      implementer brief or `CLAUDE.md`.
- [ ] `minor` **I16 – A ZIP update leaves the old `framescout_core.py` behind:** since I15 the
      shared code is the package `framescout_core/`. A user who extracts a new ZIP over an
      older folder (instead of a fresh folder or `git pull`) keeps the old single file next
      to the package. Python imports the package, which takes precedence over a module of
      the same name in the same folder (checked locally), so the new app runs correctly, but
      the stale file may be edited by mistake. The reverse case is not harmless: extracting
      an *older* ZIP over a newer folder (a rollback) restores `framescout_core.py` and the
      old `app.py`/`framescout_engine.py`, but the leftover package still wins, so the old
      frontend silently runs against the newer core (e.g. another `ENGINE` and cache
      signature). Bytecode in `__pycache__/` is not a problem: Python ignores a cached
      `.pyc` whose source is gone. Fix with the update/uninstall story of P5 (e.g. the
      installer removes known obsolete files, `Start-FrameScout.bat` warns when both
      `framescout_core.py` and `framescout_core/` exist, or the README says to extract into
      a fresh folder). Found on 2026-10-26 in I15 (rollback case: PR #25 review).
      (2026-10-27, P5 part B: the README now advises extracting a ZIP into a fresh folder,
      and the uninstall script removes `__pycache__`; the stale file itself is still not
      detected or removed, so this stays open.)
- [ ] `decision` **I19 – The uninstall script never deletes user data:** `Uninstall-FrameScout.bat`
      keeps photos, references, results (with `marks.json`), `profiles.json`,
      `settings.json`, `run.log` and the evaluation labels in `.tmp/eval`, and tells the
      user to delete the folder. Fix idea: opt-in deletion per category (results and
      marks, references, profiles and settings, `run.log`, evaluation labels) with its own
      confirmation; photos are never deleted. Needs a user decision (what is
      offered, how it is confirmed). Found on 2026-10-27 in P5 part B.
- [ ] `decision` **I23 – No prebuilt movable bundle:** a user still needs the internet and about
      3 GB (CPU) or 6 GB (CUDA) of downloads, and the FrameScout folder cannot be moved
      after the installation (`.venv` refers to `.python` by absolute path; running the
      installer again after a move downloads all packages again). Option (c) of
      P5 part C, not implemented by user decision: a ZIP with the private Python, `.venv`
      and all packages that runs from any folder (e.g. a relocatable environment without
      absolute paths in `pyvenv.cfg`, or the embeddable package with `._pth`). Notes for a
      decision: the size (a CPU build several hundred MB, a CUDA build several GB); the
      licenses of the redistributed binaries have to be checked and their texts shipped –
      the CUDA runtime libraries in the CUDA wheels of PyTorch (NVIDIA's terms for
      redistribution), codec libraries bundled in wheels such as x265 in `pillow-heif` (GPL)
      and LibRaw in `rawpy` (LGPL/CDDL); who builds and hosts the bundle. Needs a user
      decision. Found on 2026-10-27 in P5 part C.
- [ ] `minor` **I25 – `framescout_eval.py` builds the cache paths itself (minor):** `engine_env`
      derives the same four variables from `--cache-dir`; it takes a cache folder, not the
      project folder, so it was left alone in E9/I10. It could share
      `framescout_core.cache_paths`. Found in the PR of E9/I10.
- [ ] `minor` **I28 – The reviewer posts one comment for all findings (optional):** when
      `/code-review` posts nothing, the reviewer posts one numbered comment (I26), so
      `address-review` can only answer in one comment. One comment per finding (numbered,
      `file:line`) would allow a reply on each thread. Found in the PR of I26.
- [ ] `minor` **I29 – The briefs hard-code the commit trailer's model name:** `implementer-brief.md`
      prescribes `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`, which
      conflicts with the attribution the session gives a subagent (a Sonnet implementer
      noticed). Take the trailer from the session's attribution instead and drop the literal
      line. Found in the PR of I26.
- [ ] `ready` **I30 – Repository layout, step 1: scoring module outside the package (low risk):**
      `framescout_scoring.py` (numpy only) lies loose in the root next to the standard-library-only
      package `framescout_core/`. Move it into a package of its own (e.g. `framescout_scoring/`,
      or a sub-package that keeps the "core is standard library only" rule intact) and adjust the
      imports in the engine, the evaluation tool and the tests. No user-visible change. Found on
      2026-10-30 in a review of the folder structure.
- [ ] `decision` **I31 – Repository layout, step 2: group the loose root files (medium risk):** move
      `requirements*.txt`, `constraints.txt` and `pytest.ini` into `requirements/` (check
      whether `pytest.ini` may move), `profiles.example.json` and `framescout_eval_page.html`
      into a data folder (e.g. `assets/`), and `ROADMAP.md`/`BACKLOG.md` into `docs/`
      (`SECURITY.md` stays where GitHub finds it). Update `install_torch.py`, the `.bat` files,
      CI, the test that compares the torch pins, `framescout_core.create_from_example`, the
      skills and briefs in `.claude/` and every link in the docs and `CLAUDE.md`. `Install-`,
      `Start-` and `Uninstall-FrameScout.bat` stay in the root (double-click). Needs a user
      decision on the target names. Found on 2026-10-30 in a review of the folder structure.
- [ ] `decision` **I32 – Repository layout, step 3: entry points in a package (breaking):** move `app.py`,
      `framescout_engine.py`, `framescout_eval.py`, `framescout_uninstall.py` and
      `install_torch.py` into a package (e.g. `src/framescout/`, started with
      `python -m framescout.engine`). This changes the documented CLI call
      `python framescout_engine.py`, the Streamlit start command and the `.bat` files, so it is
      a hold point (breaking change, folder rename): decide first whether thin wrappers stay in
      the root for a transition period. Best done after I30 and I31. Found on 2026-10-30 in a
      review of the folder structure.
- [ ] `hardware` **I33 – Measure the CUDA install size for the disk space check:** the
      unpacked size of the CUDA build of PyTorch and pip's peak space use are not measured;
      `TORCH_INSTALL_SPACE['cuda']` (3 GB download, 6 GB installed) is an estimate. Measure on
      the home PC and correct it; could go into the rest of I11. Found in F3 (PR #64).

### Features (from [docs/IDEAS.md](docs/IDEAS.md))

- [ ] `decision` **F6 – "Not this" search texts per profile:** a profile "red car" also ranks
      toy cars or posters high; A20 covers rejected marks, but there is no way to say up front
      what a motif is not. Sketch: an optional "Exclude texts" field per profile; in
      `framescout_scoring` a crop's score drops by a weighted z-scored similarity to the best
      exclude text (`z_text - λ·max(0, z_exclude)`); the engine encodes them like custom
      prompts, no cache change. Affected: `app.py`, profile validation and `search_fingerprint`,
      `framescout_scoring.py`, `framescout_engine.py`, `profiles.example.json`, tests, user
      guide. Risks: CLIP handles negation poorly, so it must be a separate query; a too strong λ
      buries real matches. **Question:** additive optional `profiles.json` field (schema change)
      and search quality (λ tuned on a local evaluation set, E32/E20). Size M.
- [ ] `decision` **F7 – Group near-duplicate and burst shots in the results:** bursts fill
      result pages with the same moment. Sketch: group ranked photos of one folder whose cached
      full-image embeddings have cosine ≥ ~0.95, show the best as the card ("+6 similar",
      expandable); numpy only; toggle "Group similar photos"; marking a group card could offer
      "apply to all in group". Affected: `framescout_scoring.py`, engine and
      `framescout_core.write_results` (additive `group` field in `results.json`, check the
      format-version rule of A25), `app.py` gallery, HTML gallery, tests. Risks: the threshold
      depends on the model; different people in the same pose could merge, so a group must stay
      expandable and never hide a photo. **Question:** gallery behavior and the default on/off.
      Size M.
- [ ] `decision` **F8 – Exclude subfolders and filter by date:** large trees contain folders
      never wanted (`_exports`, `edited`, `Screenshots`), and the user often knows roughly when
      a motif was shot. Sketch: in the "Photo source" tab, folder-name glob patterns to skip and
      a date range (EXIF `DateTimeOriginal` when cheap, else mtime), applied at scan time; the
      cache is untouched; engine options `--exclude`, `--date-from/--date-to`; skip counts in
      the log. Affected: `framescout_core` (scan/filter), `framescout_engine.py`, `app.py`
      (`setting_<name>` widgets), `settings.json`, user guide, tests. Risks: reading EXIF for
      every photo slows the scan (only when a date filter is set); copies inside excluded
      folders vs. the A17 check. **Question:** mtime vs. EXIF as the date; additive CLI options
      and `settings.json` keys. Size M.
- [ ] `decision` **F9 – A CSV export that Excel opens in columns in every locale:** the result
      list export (F5) writes a comma-separated CSV (RFC 4180). Excel splits a double-clicked
      CSV at the list separator of the system locale, which is `;` in German and other
      comma-decimal locales, so there every row lands in one column; the user guide points to
      Data → From Text/CSV. Options: a "Separator: comma / semicolon" choice next to the export
      button (a `setting_<name>` widget in `settings.json`), or a `sep=,` first line (Excel
      only, breaks other CSV readers and RFC 4180). With `;` the decimal point stays `.`, so
      Excel may still read the scores as text there. Affected: `framescout_core/exporting.py`
      (`export_csv`), `app.py` (`show_export`), user guide, `tests/test_export.py`.
      **Question:** whether a second format is wanted at all, and which. Found in the review of
      F5 (PR #67). Size S.
