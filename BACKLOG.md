# FrameScout – Backlog

Open work: known weaknesses and ideas, nothing is checked off here. Result of the code
analysis from 2026-10-20 (state v1.1), extended by every pull request since. IDs
(E = engine, A = app, I = installation/project) are referenced in commits, pull requests
and discussions.

- **Finished items** move to [docs/BACKLOG-DONE.md](docs/BACKLOG-DONE.md) with their
  reports when their PR is merged; the ID stays valid (search both files for it).
- **The order of work** is in [ROADMAP.md](ROADMAP.md). An item in this file that the
  roadmap does not name is not scheduled.
- **A new ID** is the next free number of its group: search both files, e.g.
  `rg -o "\*\*E\d+ " BACKLOG.md docs/BACKLOG-DONE.md`, and take the highest plus one.

## Known weaknesses

### Engine (`framescout_engine.py`)

- [ ] **E15 – No `Image.draft` with person detection:** since E2 photos are decoded at
      reduced scale only without person detection; with detection they keep full
      resolution, because a person crop in a group photo can be smaller than CLIP's
      224 px input after scaling. Drafting to a larger size (e.g. both edges ≥ 1280 px)
      would speed up the decoding of large photos (≥ ~10 MP), but changes the person crops
      and needs an evaluation with group photos (search quality) and possibly scaling the
      minimum crop size of 35×70 px with the draft factor.
- [ ] **E17 – Thread counts are not tuned for small CPUs:** PyTorch uses up to 12 threads
      (`torch.set_num_threads(min(12, …))`, from the logical core count, also when the
      process may use fewer cores), and since E2 up to four decoding threads (two with
      person detection) preprocess crops with torch at the same time, YOLO included. On
      the 24-thread development PC pinned to 4 cores the E2 engine was still faster than
      before (200 photos: 33.5 s → 20.2 s without, 55.1 s → 45.6–47.7 s with person
      detection), but the gain with detection shrinks and timings are noisy (PR #7
      review). Fix idea: measure on a real 4–8 core machine; derive the torch threads from
      the cores the process may use and the decoding threads, or convert crops to tensors
      on the main thread.
- [ ] **E18 – Person detection is still one photo per call:** since E14 YOLO runs on the
      CLIP device, but the decoding threads still call it one photo at a time under a lock,
      and with detection only two decoding threads run (`DETECTION_DECODE_THREADS`, chosen
      for the CPU and the memory of full-resolution photos). On a GPU, detection is fast
      and decoding may become the limit. Passing several photos per call is not a pure
      speed change: Ultralytics pads photos of different shapes in one call to a square
      (`LetterBox(auto=False)`) instead of the smallest rectangle, so the detected boxes
      and the person crops change → needs an evaluation of search quality first, and the
      gain can only be measured on a GPU (I11). Deferred from the roadmap item "YOLO on
      GPU" (PR #8, user decision).
- [ ] **E19 – The detection settings in the cache signature are listed by hand:**
      `feature_signature` hashes `max_persons`, `person_confidence` and `yolo_model`, but
      not the YOLO input size (`DETECTION_IMAGE_SIZE`, 640) or the other fixed
      `detection_options`; changing them needs a manual `ENGINE` bump (a comment and the
      golden test of `detection_options` ask for it). Deriving the signature from
      `detection_options` (without device and verbose) removes that step, but changes the
      signature value and so re-analyzes every photo once → do it with the next `ENGINE`
      bump. The device stays out on purpose: CPU and CUDA give slightly different numbers
      for CLIP as well, and the cache has always been shared between devices (PR #8 review).
- [ ] **E20 – Search quality is measured on one collection only:** the evaluation of E4/E5
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
- [ ] **E21 – No multilingual search:** FrameScout supports English search terms only
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
- [ ] **E29 – HEIC/RAW support as optional extras:** E25 made `pillow-heif` and `rawpy`
      required in `requirements.txt` (user decision at the PR #26 hold point; the user may
      want them optional later). Idea: a separate requirements file, a question in
      `Install-FrameScout.bat`, and the engine's existing fallback (formats without their
      package are skipped with a note). Roadmap candidate, not scheduled.
- [ ] **E32 – The offered search models are not evaluated:** E22 offers ViT-B/16 and
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
      not run with real models yet (E34). A key trimmed from the registry falls back to the default with
      a warning in a user's `settings.json` (`read_settings`); its cache rows then count as
      "older version" in the cleanup. Search quality is a hold point.
- [ ] **E34 – The evaluation tool is not runtime-tested with real models:**
      `framescout_eval.py run` and the engine's `--scores-file` (E32, PR #32) were checked
      by unit tests, the syntax tree and `py_compile` only (no real-model run without
      approval); the labelling page was rendered in headless Edge, but its keyboard and
      click handling was not tried in a real browser. Verify on the first real use (the
      user's home PC) and fix what shows up.
- [ ] **E35 – The labelling page may show originals a browser cannot display:** thumbnails
      exist only for each model's top `--top` (150) at the run's reference weight; pool
      photos from the other pool weights may lack one and are then shown as the original
      file, which a browser cannot display for HEIC/HEIF and RAW. Fix idea: render the
      missing thumbnails with the engine's decoders (needs Pillow/rawpy in the tool) or
      raise `run --top`. Found in E32 (PR #32). Since the review of PR #32 the page names
      such a photo "original file" and prefetches only thumbnails, so large originals are
      loaded only when shown.
- [ ] **E36 – Labels do not record the motif they were made for:** `labels.json` keys a
      label by profile name and photo path only. Editing the prompts under the same name
      keeps the labels (intended: prompt wordings can be compared on the same labels), but
      a profile whose motif changes under the same name (context, features, reference
      images) silently reuses labels made for the old motif, and the "profile has changed"
      warning of `pool`/`metrics` disappears once every model has been run again. Today
      `docs/DEVELOPMENT.md` asks for a new profile name instead. Fix idea: store each profile's
      context, features and reference images in `labels.json` when a label is set and warn
      in `pool`/`metrics` when they differ. Found in the review of PR #32 (E32).
- [ ] **E37 – The unbound check guards only the root probe with a timeout:** a folder
      listing or `stat` on a share that hangs during the pass stalls the scan (the page
      run) until the OS gives up; a junction or mount point inside a reachable root that
      leads to a disconnected volume can make its photos look gone (the deletion
      re-checks, but the volume would have to be back by then). Idea: run the pass in a
      worker thread with a per-folder timeout, or treat folders on other volumes than
      their root as their own root. Found in the PR of E8.
- [ ] **E38 – The online fallback and the first download are not runtime-tested:**
      `framescout_core.model_cached` decides from the hub cache whether a model loads
      offline (E16, P7 A). An engine search ran with the default model only; SigLIP
      (`vit-b-16-siglip`) loaded offline with its tokenizer from a complete cache in a
      Python check (PR #41 review), and with an empty cache the offline errors of open_clip
      and of the SigLIP tokenizer were checked to take the fallback (`hub_file_error`). The
      fallback after an incomplete cache (`load_with_hub_fallback` going online and
      downloading what is missing) and the first download into an empty cache were covered
      by unit tests only, since a real run downloads at least 605 MB. Verify on the home PC
      (P10 A, next to E34) and fix what shows up. Found in the PR of E16.
- [ ] **E39 – open_clip's URL download path ignores the cache variables (minor):** a model
      without an `hf_hub` config would be fetched by `download_pretrained_from_url` into
      `~/.cache/clip` regardless of `TORCH_HOME`/`XDG_CACHE_HOME`. Not hit today: every
      `framescout_core.MODELS` entry downloads through the Hugging Face Hub. A future model
      without `hf_hub` would need `cache_dir=` passed to open_clip. Found in the PR of E9/I10.
- [ ] **E40 – A `yolo_weights` test only holds on Windows (minor):** `test_yolo_weights_paths_and_urls_are_used_as_given`
      passes `r'models\w.pt'` and expects it back unchanged; on Linux/macOS `Path(name).name`
      is the whole string, so `yolo_weights` treats it as a bare name and the test fails
      (CI runs on Windows only). Fix: check the backslash case with `PureWindowsPath` or skip
      it off Windows. Review of PR #42, finding 6.
- [ ] **E41 – A user's own `yolo11n.pt` in the working folder is ignored once a cached copy
      exists:** `yolo_weights` looks in the cache folder first and in the working folder only
      afterwards, so the "used as before" file of the working folder loses against any copy in
      `.cache/ultralytics/`. Decide which one should win (a copy the user put next to the run
      is arguably more deliberate) and document it. Review of PR #42, finding 7.
- [ ] **E42 – The engine sets the cache variables when it is imported:** `default_cache_env`
      runs at module level in `framescout_engine.py` (so it precedes the torch import), which
      changes `HF_HOME`, `TORCH_HOME` and `XDG_CACHE_HOME` for every importer of the module and
      means models cached in the user profile are no longer found by a manual run (documented
      consequence of E9/I10). Decide whether to move it into `main()` (the heavy imports are
      lazy or must be reordered; `tests/test_engine_defaults.py` pins the module-level call)
      and whether a note or an opt-out is needed for users who keep models elsewhere. Review of
      PR #42, findings 8 and 9.
- [ ] **E43 – `yolo_weights` returns a path in `.cache/ultralytics/` without creating the folder
      (not verified):** Ultralytics should create the parent folder when it downloads to that
      path, but this was not run; if it does not, the first download fails. Check on the first
      download into an empty cache (P10 A, next to E38) or create the folder in
      `yolo_weights`/the engine. Review of PR #42, finding 10.
- [ ] **E44 – Temporary files of the app's atomic writes in the project folder stay after a
      kill (minor):** `profiles.json.<random>.tmp`, `settings.json.<random>.tmp` (and the
      write of `profiles.json.bak`) remain if the app process is killed during a write. No
      cleanup removes them: `auto_cleanup` only looks at `results/`. Small and rare. Found
      in PR #45.
- [ ] **E45 – `publish_export` is not one step across files (minor):** a kill between the
      renames (milliseconds) can still leave some galleries newer than `results.json`. A
      rename that fails every retry (a file held open for over 2 s; the run then fails)
      restores the files renamed before it, but if a restore fails too, they stay new.
      Idea, if it ever matters: a versioned gallery subfolder that `results.json` names.
      Found in PR #45.
- [ ] **E46 – A merely truncated JPEG partner does not trigger the RAW fallback:** the
      engine sets `ImageFile.LOAD_TRUNCATED_IMAGES = True`, so a JPEG with an intact header
      but missing data decodes without an error (the missing part gray) and the E30
      fallback never runs; only partners that fail to decode (corrupt header, unreadable
      file, broken HEIC) fall back. Idea: for partners of a RAW file, detect truncation
      (Pillow's truncation warning, or a decode with `LOAD_TRUNCATED_IMAGES` off) and
      prefer the RAW file then. Found in PR #46.

### App (`app.py`)

- [ ] **A6 – Folder count on every rerun:** `rglob` over the whole photo folder on every
      interaction; slow for large folders/network drives.
- [ ] **A10 – `use_container_width` is deprecated:** in Streamlit 1.66 the `st.button`
      docstring marks it as deprecated in favor of `width="stretch"` (no runtime warning
      yet; it still works). `width` for buttons is newer than the current floor
      `streamlit>=1.40` (the release notes name 1.48 – not verified), so switching needs
      a raised minimum version → do it together with I3.
      (I3 is done, but the user kept the Streamlit floor at `>=1.40` in PR #8: raising
      it and switching to `width` belong together in this item. The result gallery of P4
      (A) uses `use_container_width` for its buttons as well.)
- [ ] **A15 – Reference folder and gallery file can get different suffixes:**
      `reference_folder` adds `-2`, `-3`, … when another profile's references occupy the
      folder, `profile_slugs` adds them by profile order. The same profile can therefore
      have `references/red-car-2/` but `red-car.html` (or the reverse). Nothing breaks,
      but the names are harder to explain. Fix idea: derive the folder from
      `profile_slugs` with a fallback for occupied folders – note that the order-based
      slugs change when profiles are deleted or reordered, which would then move folders
      (design decision, PR #6 review).
- [ ] **A18 – ZIP export (roadmap P4 (C)): open decision.** Asked in PR #14 and deferred to
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
- [ ] **A19 – "Open" and "Folder" are checked on Windows only:** the gallery buttons of P4
      (A) open a photo with `os.startfile` and select it with the shell function
      `SHOpenFolderAndSelectItems` (checked on Windows 11 from the app in a browser,
      also with a space and a comma in the path; `explorer /select,` did not select a file
      with a comma). On macOS (`open`, `open -R`) and Linux (`xdg-open`, which opens the
      folder without selecting the file) they are untested. They act on the computer the
      app runs on, which is the user's own as long as the app listens on `127.0.0.1`.
      The same holds for "Open target folder" of A17, whose default target uses
      `~/Pictures` outside Windows (untested).
- [ ] **A20 – Marks do not feed back into the search:** marks (A17) are only used to copy
      matches. Photos marked as match could serve as extra reference images and photos
      marked as no match as "not this" examples of a profile, e.g. by lowering the score
      of photos similar to the rejects. This changes search quality, so it needs a local
      evaluation set first (hold point). Out of scope of P4 (B) (user decision on A17).
- [ ] **A24 – "Hide photos marked as no match" reflows the pages; mark buttons look
      alike:** user report on 2026-10-25 after A17. Marking the photos of page 1 and then
      ticking the checkbox shows undecided photos of the following pages on page 1.
      Cause (`app.py`, the result gallery): the cards are filtered first and paginated
      afterwards (`cards` → `page_count` → `page_cards`), so hiding the rejects of page 1
      pulls the next undecided photos up into it, and every page after it shifts too. The
      page selector then no longer matches the ranks the user just worked through. Fix
      idea: paginate the full ranked list and hide the no-match photos only within the
      shown page (caption "N photos of this page marked as no match are hidden"); the
      drawback is a page that is empty when everything on it was rejected. Alternative
      (user decision): a filter "Show: all / undecided only / matches" over the whole list
      with its own pages, which also serves "what is left to check". Second request: a
      different color per state. `st.segmented_control` has no per-option colors; idea
      (not run in a browser): wrap the control in a container with a key naming the state
      (`markstate_match`, `markstate_nomatch`, `markstate_open`) and color the selected
      segment from the global `<style>` block through `.st-key-markstate_…` and
      `[data-testid="stBaseButton-segmented_controlActive"]` (Streamlit 1.66.1 internals,
      so check it after upgrades; keep contrast in the dark theme). The marks and
      `marks.json` stay unchanged. Found after PR #16.
- [ ] **A26 – No way back to the default AI settings:** user request on 2026-10-25. Once a
      value of the AI settings tab is changed (compute device, batch size, maximum matches,
      person detection, maximum persons, minimum confidence, reference weight), nothing
      shows what the default was or restores it; only the saved device has "Use auto from
      now on". The defaults live in `framescout_core.default_settings` and are not shown
      anywhere except the reference weight's help text. Fix idea: a "Reset to defaults"
      button (disabled while a search runs) that sets the widgets' `setting_<name>` session
      state to `DEFAULT_SETTINGS` for these settings only, not the photo folder, which is
      the user's data location and sits in the other tab (user decision whether it
      belongs in). `save_settings` already writes only values that differ from the
      defaults, so the next save drops them from `settings.json`. The values are set before
      the widgets are drawn, never as `value=` (CLAUDE.md gotcha, PR #10), and
      `reconcile_settings` must treat the reset as a change made in this session, so
      another session's saved values do not win. Also show the default next to each
      setting (e.g. in its help text, built from `DEFAULT_SETTINGS` so it cannot drift) and
      mark a changed value. Not a search-quality change, since the defaults stay as they
      are.
- [ ] **A27 – The photo folder is scanned on every rerun:** the "Photo folder" tab counts
      the photos with `scan_photos` (since E25; before with the same `rglob`) at module
      level, so every widget interaction anywhere in the app walks the whole photo tree
      again – slow for tens of thousands of files on a network drive or HDD. Fix idea:
      cache the scan (e.g. `st.cache_data` keyed on folder, extensions and the results
      folder, with a short TTL and a "Rescan" button), or scan only when the folder setting
      changes; how stale a count may be is a UX decision. Found in the PR #26 review.
      Since A25 (PR #28) every listed folder is scanned once per rerun.

- [ ] **A30 – Only one backup generation of `profiles.json`:** the user chose a single
      `profiles.json.bak` in PR #6 and again in the PR of A13 (hold point), so the backup is
      the state before the last save only and the next save replaces it. Options if more
      are wanted: rotate N generations (`.bak` newest, then `.bak.1`, ...); timestamped
      backups; a one-time copy before the v3 conversion. Consequences to handle then:
      cleanup (E7, A14) must keep the reference images of all generations, and
      `update_backup_references` (rename of the photo/reference folder) must rewrite all
      of them. How many generations is a user decision. Split from A13.
- [ ] **A31 – A click on a profile form that no longer exists is dropped silently:** if
      another session shortened the profile list, a form submit or button of a form that
      the page no longer shows is not delivered by Streamlit, and the app shows no
      message (found in the PR of A13, not reproduced beyond the reading of the code).
      Fix idea: tell the user when the profile list changed under an open page.
- [ ] **A32 – `update_backup_references` runs outside the lock of `profiles.json`:** after
      a folder rename the paths in `profiles.json.bak` are rewritten without the
      `profiles.json.lock` that `save_profiles` holds (A13), so it could in theory
      rewrite a `.bak` that another session has just replaced with newer state. Probably
      harmless (it only rewrites paths of the moved folder); not analysed. Found in the
      PR of A13.
- [ ] **A34 – Marks left by profiles deleted before A22 stay in `marks.json`:** they still
      pass to a new profile of that name, and "Clean up storage" never offers them because
      `marks.json` is in `NEVER_DELETED`. No migration was done. Idea: offer to delete the
      marks of names that are no profile (asking first), or show them when such a profile
      is created. Found in the PR of A22.
- [ ] **A35 – A drive letter now used by another disk counts as reachable:** e.g. a USB
      disk that got the letter of an earlier disk, or a network drive mapped to another
      share; the photos of the earlier disk then look unbound and are offered by "Cache
      entries of unbound photos" and "Marks of unbound photos". The same on POSIX: the root
      of every path is `/`, which always exists, so the photos of an unmounted mount (e.g.
      `/mnt/nas`) look unbound (review of PR #40, findings 1 and 2). Mitigated in PR #40:
      the category lists its folders with their photo counts and its help asks to check
      them, and (user decision) neither category is selected by default any more. Idea:
      record the volume serial number (or mount) per root, which changes the cache or a
      side file (hold point). Found in the PR of E8.
- [ ] **A36 – The app overwrites cache variables a user set, the engine keeps them:**
      `cache_env()` in `app.py` assigns all of `cache_paths(BASE)` to the engine's environment,
      while `default_cache_env` keeps a value that is set. A search from the app therefore
      ignores e.g. a `HF_HOME` the user exported, a manual run honours it. Probably intended
      (the app keeps the install self-contained), but undecided and undocumented; decide and
      document, or use `default_cache_env` in the app too. Review of PR #42, finding 12.

### Installation / project

- [ ] **I2 – No tests.** (partly done 2026-10-21: `pytest` scaffold and tests for
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
- [ ] **I4 – Installer requires the `py` launcher;** without it, the misleading message
      "Python 3.12 to 3.14 not found." is shown.
- [ ] **I9 – CI action pins are updated by hand only:** `.github/workflows/tests.yml`
      pins `actions/checkout` and `actions/setup-python` to commit SHAs (with a version
      comment). That avoids moved tags, but security and runtime updates
      (e.g. a Node.js deprecation on the runners) only arrive when someone bumps
      the SHAs. Options: periodic manual bump, or Dependabot for `github-actions`.
      Dependabot opens its own PRs outside the one-PR-per-roadmap-item workflow, so
      this is a workflow decision → hold point.
- [ ] **I11 – The CUDA path has run on a GPU only once:** the development PC had no NVIDIA GPU,
      so the CUDA install (`cu130`/`cu126` choice, about 2.5 GB), CLIP and YOLO on CUDA
      (E14), the app's device choice with a CUDA build (A7) and the speed gain are
      untested; the support limits in `framescout_core.CUDA_BUILDS` are not verified either.
      To do on an NVIDIA machine: `Install-FrameScout.bat cuda`, a search run with
      `--device cuda` with and without person detection, compare scores with a CPU run,
      and measure the time (also for E18); re-run the installer without an argument and
      check that the CUDA build is kept. With several GPUs, check which one `cuda`
      (device 0 in CUDA's order) uses when the build cannot use all of them.
      (partly done 2026-10-21, user-approved smoke run from the main checkout: NVIDIA
      GeForce RTX 4070 with 12 GB, driver 616.56, `.venv` with torch 2.14.1+cu130 and
      Python 3.14, `torch.cuda.is_available()` True. 300 synthetic 1600×1200 JPEGs
      (coloured shapes, no real photos), `profiles.example.json` (6 profiles),
      `--batch-size 16`, person detection on, nothing downloaded. `--device cuda`: the log
      says "CLIP: cuda; person detection (YOLO): cuda", exit code 0, 300 new analyses,
      0 errors, 6 galleries, 17 s wall time including model load; `--device cpu` on the
      same input: exit code 0, 0 errors, 26 s – small-set timings, not a benchmark. Both
      caches have 300 rows with the same paths and identical signatures; the 301
      comparable crops have embeddings with cosine similarity ≥ 0.99999 (float16 storage).
      One synthetic photo got one extra YOLO "person" crop on CUDA (303 vs 302 crops), a
      borderline false detection near the confidence threshold. Still open: a fresh
      install with `Install-FrameScout.bat cuda` (the `.venv` already had `cu130`) and the
      installer re-run, `cu126`, other GPUs and several GPUs, a run without person
      detection, real photos and scores compared on them, the app's device choice in the
      browser, and the speed on a large folder (also for E18).)
- [ ] **I13 – Background runs die with the agent session:** a long engine run that an
      agent starts as a background command of Claude Code ends when that agent session
      ends; the first evaluation run of PR #11 stopped at 1,110 of 4,997 photos (stale
      `run-status.json` in phase "analyzing", the lock released by the OS). It completed
      when started detached through WMI (`Win32_Process.Create` with a `.cmd` file that
      sets the cache variables). Long smoke or evaluation runs in the PR workflow should be
      started detached (and the agent should wait for their end) — document it in the
      implementer brief or `CLAUDE.md`.
- [ ] **I16 – A ZIP update leaves the old `framescout_core.py` behind:** since I15 the
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
- [ ] **I19 – The uninstall script never deletes user data:** `Uninstall-FrameScout.bat`
      keeps photos, references, results (with `marks.json`), `profiles.json`,
      `settings.json`, `run.log` and the evaluation labels in `.tmp/eval`, and tells the
      user to delete the folder. Fix idea: opt-in deletion per category (results and
      marks, references, profiles and settings, `run.log`, evaluation labels) with its own
      confirmation; photos are never deleted. Needs a user decision (what is
      offered, how it is confirmed). Found on 2026-10-27 in P5 part B.
- [ ] **I23 – No prebuilt movable bundle:** a user still needs the internet and about
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
- [ ] **I25 – `framescout_eval.py` builds the cache paths itself (minor):** `engine_env`
      derives the same four variables from `--cache-dir`; it takes a cache folder, not the
      project folder, so it was left alone in E9/I10. It could share
      `framescout_core.cache_paths`. Found in the PR of E9/I10.
- [ ] **I27 – Routine worktree commands still ask for approval:** `/roadmap` cleans up
      worktrees and `worktree-agent-*` branches as a fixed step (I26), but
      `.claude/settings.json` does not pre-approve `git worktree unlock *`,
      `git branch -d worktree-agent-*` and `git worktree remove .claude/worktrees/*`. Proposal:
      allow these three and keep `-f`/`--force` removals and `git branch -D` on "ask". Needs the
      user's explicit decision (a permission change). Found in the PR of I26.
- [ ] **I28 – The reviewer posts one comment for all findings (optional):** when
      `/code-review` posts nothing, the reviewer posts one numbered comment (I26), so
      `address-review` can only answer in one comment. One comment per finding (numbered,
      `file:line`) would allow a reply on each thread. Found in the PR of I26.
- [ ] **I29 – The briefs hard-code the commit trailer's model name:** `implementer-brief.md`
      prescribes `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`, which
      conflicts with the attribution the session gives a subagent (a Sonnet implementer
      noticed). Take the trailer from the session's attribution instead and drop the literal
      line. Found in the PR of I26.
