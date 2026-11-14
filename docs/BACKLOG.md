# FrameScout – Backlog

Open work: known weaknesses and ideas, nothing is checked off here. Result of the code
analysis from 2026-10-20 (state v1.1), extended by every pull request since. IDs
(E = engine, A = app, I = installation/project, F = feature, taken over from
[docs/IDEAS.md](IDEAS.md)) are referenced in commits, pull requests and discussions.

- **Finished items** move to [docs/BACKLOG-DONE.md](BACKLOG-DONE.md) with their
  reports when their PR is merged; the ID stays valid (search both files for it).
- **The order of work** is in [docs/ROADMAP.md](ROADMAP.md). An item in this file that the
  roadmap does not name is not scheduled.
- **A new ID** is the next free number of its group: search both files, e.g.
  `rg -o "\*\*E\d+ " docs/BACKLOG.md docs/BACKLOG-DONE.md`, and take the highest plus one.
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
      required in `requirements/requirements.txt` (user decision at the PR #26 hold point; the user may
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
- [ ] `hardware` **E43 – `yolo_weights` returns a path in `.cache/ultralytics/` without creating the folder
      (not verified):** Ultralytics should create the parent folder when it downloads to that
      path, but this was not run; if it does not, the first download fails. Check on the first
      download into an empty cache (P10 A, next to E38) or create the folder in
      `yolo_weights`/the engine. Review of PR #42, finding 10. Since PR #89 (P20) the app still
      pre-creates `.cache/ultralytics` when it sets `YOLO_CONFIG_DIR` itself; a user's own
      `YOLO_CONFIG_DIR` is not pre-created by the app (Ultralytics creates its config folder on import).
- [ ] `parked` **E45 – `publish_export` is not one step across files (minor):** a kill between the
      renames (milliseconds) can still leave some galleries newer than `results.json`. A
      rename that fails every retry (a file held open for over 2 s; the run then fails)
      restores the files renamed before it, but if a restore fails too, they stay new.
      Idea, if it ever matters: a versioned gallery subfolder that `results.json` names.
      Found in PR #45.
- [ ] `hardware` **E52 – The effect of `--low-priority` is not measured:** F4 lowers the engine's
      process priority and keeps one or two cores out of the PyTorch threads (`torch_threads`,
      also for the person detector), but neither the
      slowdown of the search (CPU and GPU) nor the gain in responsiveness of other programs
      (e.g. a second CPU-heavy task running at the same time) was measured. Measure it on the
      home PC together with E17 (P10 B); from the results adjust how many cores
      `torch_threads` leaves free, or also lower the decoding threads (E2), which are not
      reduced now. Found in F4 (PR #65).
- [ ] `minor` **E55 – A model without `weights_repo` needs more than E39's download folder:**
      such a model would also fail `test_every_model_names_its_hub_repositories`, and
      `model_cached`/the offline import (E16), the disk space estimate and "Check
      installation" assume Hub files. Only needed when such a model is ever added. Found in
      the PR of E39 (PR #74).
- [ ] `hardware` **E58 – `FOLDER_TIMEOUT` is not measured on a slow folder:** the 30 s limit of
      the unbound check (E37) is not tested on a legitimately slow folder (e.g. many absent
      names, each confirmed by a `stat` on a slow share); such a folder is not checked (the safe
      side). Measure it on the home PC or NAS and adjust the limit. Split off from E54 (PR #84).
- [ ] `decision` **E64 – The feature cache signature still names the detector weights only by
      the name given:** `feature_signature` records `--yolo-model` as given, not which file
      `yolo_weights` loaded (see E60, which only logs the file). A run with fine-tuned weights
      of the same name, or a relative path from another working folder, reuses the person crop
      embeddings of another detector. Option: put the resolved path or a hash of non-cache
      weights into the signature (cache invalidation for those runs: a hold point,
      `ENGINE_TEMPLATE`/`tests/test_signature.py` untouched until decided). Split off from E60.
- [ ] `minor` **E62 – Rows cached as black images for a truncated HEIC stay valid after E59:**
      before E59 a truncated HEIC/HEIF that is not a RAW partner was analyzed as an all-black
      image; its cache row has the file's modification time and size, so it stays current and
      keeps being ranked (and searched by a quick search) until the file changes; "Clean up
      storage" deletes it only with other settings than the current ones (`cache_old`,
      `cache_other`, `cache_models`), never as a row of the current settings for a photo that
      still exists. Options: leave it (rare: needs a truncated HEIC analyzed before E59),
      detect black rows (e.g. compare with the embedding of a black image per model) and
      analyze those photos again, or invalidate HEIF rows only
      (cache invalidation: a hold point, `ENGINE_TEMPLATE`/`tests/test_signature.py` untouched
      until decided). Review of PR #96, finding 2.

### App (`app.py`)

- [ ] `parked` **A15 – Reference folder and gallery file can get different suffixes:**
      `reference_folder` adds `-2`, `-3`, … when another profile's references occupy the
      folder, `profile_slugs` adds them by profile order. The same profile can therefore
      have `references/red-car-2/` but `red-car.html` (or the reverse). Nothing breaks,
      but the names are harder to explain. Fix idea: derive the folder from
      `profile_slugs` with a fallback for occupied folders – note that the order-based
      slugs change when profiles are deleted or reordered, which would then move folders
      (design decision, PR #6 review).
- [ ] `parked` **A18 – ZIP export (formerly roadmap P4 (C)): open decision.** Asked in PR #14 and deferred to
      P4 (C); removed from the roadmap on 2026-11-03 at the user's request, to be planned again later. **Deferred by the user on 2026-10-25** ("skip this feature for now"): copying
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
- [ ] `decision` **A47 – Decide the frontend framework before distribution (simplification):** a large
      part of `app.py` works around Streamlit's rerun model (session-state keys for every
      widget, fragments, `cached_*` functions keyed by mtime/size, notices carried over
      reruns). Before P5 (distribution) decide once whether Streamlit stays or a small local
      server with a static HTML frontend replaces it (the galleries are HTML already). Notes
      for the decision: size and start time of the bundle, the effort of a rewrite against the
      code that would go away, and what the tests can check then. Product decision and new
      dependency (hold point). Found on 2026-11-12 in a simplification review.
      Triage 2026-11-13: decided separately and later; the UI rebuild P32–P37 stays within
      Streamlit. **Question:** Streamlit or a local server with an HTML frontend.
- [ ] `minor` **A48 – The summary before a search counts photos that never get a cache row as "to analyze":**
      `start_summary` of a search takes the photos with a cache row of their own
      (`quick_scope`'s first count). A JPEG/HEIC searched through its RAW file or another
      partner of its shot (E30, E53) never gets a row of its own, so "N to analyze" (and its
      duration) stays above zero after every search; the summary of "Analyze photos now"
      counts these partners as analyzed since the review of PR #100. A photo that fails to
      decode every time has no row either and is counted as "to analyze" in both summaries;
      the app cannot know that without a record of failed photos. Options: count the partners
      as analyzed for the search's summary too (the disk space estimate then follows), and
      name failed photos of the last run, e.g. from its status counts. Found in the review of
      PR #100, finding 6.
- [ ] `minor` **A50 – The profile tab is long:** "New search profile" sits below the list, and
      every profile opens to a full form (four text fields, an uploader, a checkbox, two
      buttons). Sketch: the new-profile form first or behind a button, compact profile rows.
      Affected: `app.py`, user guide. `docs/UI-REVIEW.md` §3. Size S.
- [ ] `minor` **A51 – Long explanatory captions:** "Analyze ahead" (about 100 words), the quick
      search and the AI settings explain everything in one grey block. Sketch: one short
      sentence, the rest behind a help tooltip or a "More" expander; the required English-only
      hint (E3) stays. Affected: `app.py`, user guide. `docs/UI-REVIEW.md` §4. Size S.
- [ ] `ready` **A52 – Second browser pass for the parts not looked at:** the pass of 2026-11-13
      did not cover the dark theme, narrow windows, "Find similar", the contents of "Clean up
      storage", profiles with reference images and real photos (person crops, long runs), and
      the F27 state line next to the title at narrow widths (does it wrap, and does the header
      jump when the 2 s update changes its length; PR #108 review). Do it
      after P35, when the cards have changed, and add the findings as backlog items. Kind
      `docs`. Size S.

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
      2026-11-13 (A49): the mark colors were checked with such a script too (outside the
      repo); their selector names are checked against the installed Streamlit bundle where
      Streamlit is installed. A repeatable, committed browser check (script or a tool such
      as Playwright, a new dependency) is still open.
      Open: tests for cache signature/reuse and scoring; tests of `app.py` itself (e.g.
      Streamlit's `AppTest`, which needs Streamlit in CI); a smoke test with real models.)
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
- [ ] `decision` **I32 – Repository layout, step 3: entry points in a package (breaking):** move `app.py`,
      `framescout_engine.py`, `framescout_eval.py`, `framescout_uninstall.py` and
      `install_torch.py` into a package (e.g. `src/framescout/`, started with
      `python -m framescout.engine`). This changes the documented CLI call
      `python framescout_engine.py`, the Streamlit start command and the `.bat` files, so it is
      a hold point (breaking change, folder rename): decide first whether thin wrappers stay in
      the root for a transition period. Best done after I30 and I31 (both done). Found on 2026-10-30 in a
      review of the folder structure.
- [ ] `hardware` **I33 – Measure the CUDA install size for the disk space check:** the
      unpacked size of the CUDA build of PyTorch and pip's peak space use are not measured;
      `TORCH_INSTALL_SPACE['cuda']` (3 GB download, 6 GB installed) is an estimate. Measure on
      the home PC and correct it; could go into the rest of I11. Found in F3 (PR #64).
- [ ] **I39 – Shrink `docs/ARCHITECTURE.md` to what the code cannot say (simplification):**
      the file has about 177 KB and retells the code function by function, so every PR has to
      update it and the workflow needs a separate `docs-update` agent for that (I17). Cut it to
      roughly 20–30 KB: the search pipeline, cache signature, data formats (`profiles.json`,
      `settings.json`, result file, marks), invariants and the verified status. Per-function
      descriptions go into docstrings (most exist already), the per-file test list is dropped
      (the test files are the list). Then check whether the separate docs step is still needed
      (I41). Found on 2026-11-12 in a simplification review of the whole project: the search
      core (engine, scoring, image loading) has about 1,300 lines, against about 7,500 lines
      of `framescout_core`, 13,800 lines of tests and 530 KB of Markdown.
- [ ] **I40 – Reduce `docs/BACKLOG-DONE.md` to one line per ID (simplification):** the file
      has about 170 KB of reports that repeat the PR descriptions and the git history. Keep
      one line per finished item (ID, title, date, PR link); the report stays in the PR.
      Change the rule "moved with its report" in `CLAUDE.md`, the roadmap skill and the briefs
      accordingly. Items finished without a PR keep a short report. Found on 2026-11-12 in a
      simplification review.
- [ ] **I41 – Lighter PR workflow (simplification):** four state labels, fresh agents per
      phase and a separate docs agent are heavy for a one-person project. After I39/I40
      decide: fold the docs update back into the implementer (the reason for I17 was the
      context size, mostly caused by the docs), reduce the labels to two (`fs:in-progress`,
      `fs:ready`), and shorten `CLAUDE.md` → "PR workflow", `.claude/skills/roadmap/SKILL.md`
      and the briefs (together about 50 KB). Keep: one PR per item, one review round, merge
      only after approval, user data protection. Workflow rule change, so a user decision.
      Found on 2026-11-12 in a simplification review.
- [ ] **I42 – Replace the mixed-versions guard by something simpler (simplification):**
      `framescout_core/layout.py`, `framescout_scoring/layout.py`, the `FRAMESCOUT_PACKAGES`
      marker in six entry points and about 500 lines of `tests/test_layout.py` (I16, I35, I36)
      only protect against extracting a ZIP over another version's folder. Options: the
      installer and the start script refuse a folder that holds files of another version (one
      version file); or the user guide says "extract into an empty folder" and the `.bat`
      files keep deleting the two known leftover files. Removes a gotcha from `CLAUDE.md`.
      Decide which protection stays. Found on 2026-11-12 in a simplification review.
- [ ] **I43 – Drop legacy names with one migration (simplification, breaking):** the prototype
      has no release yet but carries compatibility code for its own earlier states: the crop
      label `Gesamtbild` in old cache rows, the thumbnail folder `results/vorschaubilder/`,
      the profile field `franchise` (meaning "Context / origin"), the CLI option
      `--character` and `LEGACY_PHOTO_FOLDER` in the settings. Migrate the user's files once
      (with a backup, as the profile conversion does), rename, and remove the compatibility
      paths; best together with the first release `v1.1.0` as the cut. Breaking change of the
      `profiles.json` schema and the CLI (hold point): decide per name. Found on 2026-11-12 in
      a simplification review.
- [ ] **I44 – Reduce defensive handling of rare cases, starting with the storage cleanup
      (simplification):** `framescout_core/cleanup.py` has about 1,300 lines and
      `tests/test_cleanup.py` about 1,500, more than the whole engine: reachability probes of
      drive roots in threads, hanging network shares, fstab mount points, dead links. A
      simpler rule ("a root that does not answer → offer nothing of that category") would
      probably need a third of the code. Review `uninstall.py`, `install_check.py` and
      `disk_space.py` in the same way. Each removal gives up protection against a rare case,
      so list per module what would go and let the user decide (the deletion rules for user
      data and `NEVER_DELETED` stay). Found on 2026-11-12 in a simplification review, by
      sampling, not by reading every module.
- [ ] **I45 – Flatten the package structure (simplification):** `framescout_core/__init__.py`
      re-exports about 200 names by hand, and every new function has to be added there; import
      from the modules instead (`from framescout_core.settings import …`) and keep
      `__init__.py` nearly empty (the mixed-versions guard depends on I42).
      `framescout_scoring` (about 190 lines, numpy only) is an own package with an own guard:
      make it one module or a subpackage, keeping the rule "core is standard library only" as
      a test. Do it together with I32 (entry points into a package), so the imports change
      once. Found on 2026-11-12 in a simplification review.
- [ ] **I46 – One place for dependencies: `pyproject.toml` with a lock file (simplification):**
      versions live in `requirements/requirements.txt`, `requirements-dev.txt`,
      `constraints.txt`, as constants in `framescout_core/torch_build.py` and
      `portable_python.py`, with tests that compare them. A `pyproject.toml` with a lock file
      (e.g. `uv.lock`) would be one source; `uv` could also download the private Python and
      choose the CPU/CUDA index, replacing parts of `Install-FrameScout.bat`,
      `install_torch.py` and `portable_python.py`. New tool and download in the installer
      (hold point); check the offline behavior, the checksum of the `uv` download and the
      clean uninstall first. Found on 2026-11-12 in a simplification review.
- [ ] **I47 – Keep unneeded complexity out from the start (workflow):** the items I39–I46,
      A46 and A47 remove complexity that entered one reasonable PR at a time, mostly through
      review findings about rare cases, compatibility with earlier prototype states and docs
      that retell the code. Rules to introduce:
      (a) a rule in `CLAUDE.md` → "Engineering principles": handle a failure case in code only
      if it was observed or would lose user data; otherwise document it as a known limit;
      (b) no compatibility code for states that were never released; a format change gets one
      migration and the old path is removed in the same PR;
      (c) review findings about hypothetical cases default to "declined, known limit" instead
      of a fix or a backlog item, unless user data is at risk; the reviewer brief asks for
      simplification findings too ("what could this PR delete?");
      (d) every PR states its net line change (code, tests, docs) in the template; a PR that
      adds more than about 300 lines of non-test code explains why a smaller solution was not
      enough;
      (e) every `/triage` round schedules at least one item that only removes code or docs.
      The user agreed to (a)–(e) in chat on 2026-11-12 and declined a further proposal (a
      `/triage` question "what observed problem does this solve, and what is the smallest
      change?" for every new item). Open: write the rules into `CLAUDE.md`, the PR template,
      the reviewer brief and the triage skill. Found on 2026-11-12 in a simplification review.

### Features (from [docs/IDEAS.md](IDEAS.md))

- [ ] `decision` **F6 – "Not this" search texts per profile:** a profile "red car" also ranks
      toy cars or posters high; A20 covers rejected marks, but there is no way to say up front
      what a motif is not. Sketch: an optional "Exclude texts" field per profile; in
      `framescout_scoring` a crop's score drops by a weighted z-scored similarity to the best
      exclude text (`z_text - λ·max(0, z_exclude)`); the engine encodes them like custom
      prompts, no cache change. Affected: `app.py`, profile validation and `search_fingerprint`,
      `framescout_scoring.py`, `framescout_engine.py`, `assets/profiles.example.json`, tests, user
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
- [ ] `decision` **F13 – Keep the previous search results:** every search replaces `results.json`
      and the galleries, so a worse result cannot be compared with the earlier ranking. Sketch:
      before `publish_export` replaces them, move the previous `results.json` and galleries to
      `results/history/<run end timestamp>/`, keep the last N runs (setting); the results view
      gets a "Run" selectbox (latest by default, older runs read-only); thumbnail cleanup keeps
      what a kept run links, "Clean up storage" lists old runs. Affected: `framescout_core`
      (export/publish, cleanup, `read_results`), `framescout_engine.py`, `app.py`, user guide,
      `docs/ARCHITECTURE.md`. Risks: disk use; the move must be as safe as the E24 publish; marks
      are per photo and profile, not per run. **Question:** number of runs kept, default on/off;
      new `results/` folder. Size M.
- [ ] `decision` **F14 – Export and import a search profile as one file:** a profile (texts plus
      reference images) cannot be moved to another PC or shared except by copying parts of
      `profiles.json` and `references/` by hand. Sketch: "Export profile" writes a ZIP with a small
      JSON (fields, format version) and the reference images; "Import profile" validates like
      `load_profiles`, gives a taken name a free suffix, stores references through
      `reference_folder` (never overwriting, A1) and saves through the locked save (A13).
      Affected: `framescout_core` (bundle read/write, `zipfile`, tested incl. path traversal),
      `app.py` (profile tab), user guide. Risks: an imported ZIP is untrusted: reject absolute or
      `..` member names, cap sizes and file counts, accept only `EXT` suffixes; reference images
      may show people (say so in the guide). **Question:** the contents of the new bundle format
      (no `profiles.json` schema change). Size M.
- [ ] `ready` **F19 – One-photo review in a dialog with a large preview:** marking (A17) happens
      on small thumbnails. Decided 2026-11-13 (replaces F31): a dialog (`st.dialog`) opened by
      "Review one by one" in the results toolbar and by a click on a card's photo. It shows one
      result with a large preview (decoded downscaled in memory), the best crop outlined if the
      result has the data, rank, score and path, and the buttons "Match", "No match" and "Skip";
      each choice saves through `save_marks` and shows the next undecided photo; "Previous",
      "Next", "Open photo" and "Find similar" below. Keyboard keys only without a new
      dependency. Affected: `app.py` (its modules after A46), `framescout_images.py`,
      `framescout_core`, user guide. Risks: decoding large RAW/HEIC on every rerun is slow
      (cache the preview per path and mtime). Builds on F30 and F29. Size M. Roadmap P37.
- [ ] `parked` **F21 – Warn about cloud-only photos before a search:** photos in OneDrive-style
      folders with files on demand are downloaded when read. Sketch: flag files with
      `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`/`FILE_ATTRIBUTE_OFFLINE` during the scan, show a
      count in the photo source tab and offer "Skip cloud-only photos" (`--skip-cloud-only`).
      Affected: `framescout_core`, `framescout_engine.py`, `app.py`, `settings.json`, user
      guide. Parked 2026-11-12: the default (warn or skip) is open and the behavior needs a
      real OneDrive folder. Size S–M.
- [ ] `parked` **F23 – Optional desktop and Start menu shortcut, removed by the uninstaller:**
      the installer would ask and create a `.lnk` to `Start-FrameScout.bat` (PowerShell
      `WScript.Shell`), record its path, and `framescout_uninstall.py` removes exactly that
      one; `framescout_check.py` reports a broken one. Affected: `Install-FrameScout.bat`,
      `framescout_uninstall.py`, `framescout_check.py`, `assets/`, README, user guide,
      `docs/ARCHITECTURE.md`. Parked 2026-11-12: it would be the first file written outside
      the project folder. Risks: redirected desktops need
      `[Environment]::GetFolderPath('Desktop')`. Size S.
- [ ] `minor` **F25 – Closest search text in the result list export:** the CSV of F5
      (`EXPORT_COLUMNS`) has no column for the closest search text of F17 (`best_query` of a card).
      Add an optional `closest_text` column, empty for a single text or older results. Affected:
      `framescout_core` export, `app.py`, user guide. Found in F17. Size S.
- [ ] `minor` **F26 – The app itself takes the instance lock of F22:** an app started with the
      manual Streamlit command or by an older version holds no lock, so a later
      `Start-FrameScout.bat` starts a second app of the same folder on the next free port. The app
      could take the lock itself (e.g. via `st.cache_resource`). Affected: `app.py`,
      `framescout_core/app_instance.py`, `docs/ARCHITECTURE.md`. Found in F22. Size S.
- [ ] `ready` **F29 – One-row results toolbar and a pager below the grid:** the first photo
      starts 520 px below the "Results" heading (profile selector, captions, info boxes,
      buttons, a checkbox, a pager); copy and export are below the 48 cards; no pager below the
      grid. Decided 2026-11-13: one toolbar row (profile selector, the counts of match, no
      match and undecided, "Hide no match", pager, "Review one by one" once F19 exists, and a
      popover "Export and copy" with copy, list export, gallery and results folder); the notes
      for exceptional states (other model, changed profile, missing profile) only when they
      apply; a second pager and "Go to first undecided" below the grid. Affected: `app.py`
      (its modules after A46), user guide. `docs/UI-REVIEW.md` §1. Size M. Roadmap P36.
- [ ] `ready` **F30 – A new result card, drawn by one function:** `show_results` and
      `show_quick_results` repeat the card code; cards of portrait and landscape photos have
      different heights, so the rows are ragged; five equal buttons per card; a marked card
      looks like an unmarked one; the page is limited to 1,300 px, which leaves a third of a
      1920 px window empty and the thumbnails 253 px wide. Decided 2026-11-13: one function
      for both views; cells of one size (the photo fitted into a square, as in the HTML
      gallery; by padded thumbnails or CSS, without changing the cache signature); the two
      main buttons "Match" and "No" (neither pressed = undecided, a second click takes the mark
      back); "Open photo", "Show in folder" and "Find similar" in a popover; the card shows its
      state (match: blue frame, no match: photo dimmed; blue and orange, told apart without
      red/green); the grid uses the window width with a fixed cell size of about 250 px.
      Affected: `app.py` (its modules after A46), `framescout_core/marks.py` (`mark_style`),
      user guide. Risks: CSS on Streamlit internals, see A49; `marks.json` unchanged.
      `docs/UI-REVIEW.md` §2 and §5. Size M. Roadmap P35.
- [ ] `decision` **F33 – HTML gallery parity with the app:** the gallery has a fixed dark theme,
      no marks, no paging and no way back to the navigation. **Options:** (a) light/dark by
      `prefers-color-scheme`, file name first, link to the top; (b) also show marks (baked in at
      export, stale afterwards); (c) leave it a plain export. Affected:
      `framescout_engine.py`, user guide. F24 review §5. Size S–M.
      Triage 2026-11-13: not decided; assess again after F30, because in the browser pass the
      gallery (seven equal columns over the full width) was easier to scan than the app.
- [ ] `parked` **F35 – Thumbnail size as a setting:** F30 fixes the cell size at about 250 px.
      A setting (e.g. small, medium, large) would let the user trade overview for detail.
      Parked 2026-11-13 by the user: a feature for later. Affected: `app.py`, `settings.json`
      (a new key with a default), user guide. Size S.
- [ ] `decision` **F36 – A folder dialog for the photo source:** the photo folders are a text
      area; the path has to be typed or pasted. Streamlit has no folder dialog. Sketch: a
      "Choose folder" button that opens the system dialog on the PC the app runs on.
      **Question:** how, without a new dependency (e.g. `tkinter`, if the private Python of
      the installer ships it; check first) and whether a dialog opened by the server process
      is acceptable. Affected: `app.py`, user guide. Found in the browser pass of 2026-11-13.
      Size S.
- [ ] `ready` **F37 – Reasons for the other disabled run buttons:** F27 explains only why
      Start is disabled. "Analyze photos now" (tab "Photo source") says why only while a run
      is active or the model package is missing, not when no listed folder exists; the
      "Quick search" button is disabled without a word when no folder exists or the model is
      missing (its scope line explains only "nothing analyzed yet"). Sketch: reuse
      `start_needs`/`start_blocked_text` of `framescout_core/app_state.py` without the
      profile need. Affected: `app.py`, `framescout_core/app_state.py`, user guide. Found in
      the PR #108 review. Size S.
