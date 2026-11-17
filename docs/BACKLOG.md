# FrameScout – Backlog

Open work: known weaknesses and ideas, nothing is checked off here. Result of the code
analysis from 2026-10-20 (state v1.1), extended by every pull request since. IDs
(E = engine, A = app, I = installation/project, F = feature, taken over from
[docs/IDEAS.md](IDEAS.md)) are referenced in commits, pull requests and discussions.

- **Finished items** move to [docs/BACKLOG-DONE.md](BACKLOG-DONE.md) as one line
  (ID, title, date, PR link) when their PR is merged; the report is the PR description. An
  item finished without a PR keeps a short report. The ID stays valid (search both files).
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
      `framescout_core.hub.model_cached` decides from the hub cache whether a model loads
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
- [ ] `hardware` **E52 – The effect of `--low-priority` is not measured:** F4 lowers the engine's
      process priority and keeps one or two cores out of the PyTorch threads (`torch_threads`,
      also for the person detector), but neither the
      slowdown of the search (CPU and GPU) nor the gain in responsiveness of other programs
      (e.g. a second CPU-heavy task running at the same time) was measured. Measure it on the
      home PC together with E17 (P10 B); from the results adjust how many cores
      `torch_threads` leaves free, or also lower the decoding threads (E2), which are not
      reduced now. Found in F4 (PR #65).
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

### App (`app.py`)

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
- [ ] `ready` **A53 – The tooltips of the results toolbar stay open:** after "Review one by one" is
      closed with Esc, and after the popover "Export and copy" is closed with Esc, the
      tooltips of both buttons stay visible, overlapping each other, and more tooltips pile up
      while the user works (one for "Scan" in the Settings tab). They also float over other
      tabs (top left of the Settings tab) until the page is reloaded. Reproduced in the light
      and the dark theme, Streamlit 1.66.1, Chrome. Cause not examined (focus returns to the
      button after the dialog or popover closes). Found in the pass of A52.
- [ ] `ready` **A54 – The header is squeezed at window widths of about 680–1100 px:** the F27 state
      line sits next to the title, so the title column gets only about 200–300 px: at 680–800
      px the title breaks inside the word ("FrameSco" / "ut"), up to about 1100 px the icon
      wraps onto its own line above the title, and the header is 50–100 px taller than at
      1200 px and wider (one line) and at 640 px and narrower (state line below the title).
      A half-screen window is typical for this. Whether the header jumps when the 2 s update
      changes the length of the state text was not measured (no search was running at those
      widths). Found in the pass of A52 (the open question of PR #108).
- [ ] `ready` **A55 – Notices of "Export and copy" appear behind the open popover:** "N copied …"
      and "Exported to …" are written above the result grid, the popover stays open and covers
      them, and the grid moves down by one notice per click. The user sees the outcome only
      after closing the popover (the popover also scrolls inside itself at 726 px window
      height). Options: write the notice inside the popover, or close it after the action as
      the popover "More" does (F41). Found in the pass of A52.
- [ ] `minor` **A56 – The title of a profile without context ends with a dangling " · ":** the saved
      profile "purple picture" is listed as "purple picture ·" (Search profiles tab); the
      separator belongs only between motif and context. Found in the pass of A52.
- [ ] `minor` **A57 – Result cards use only half of the width in a narrow window:** at 420 px the
      grid shows one card of about 200 px per row and the right half stays empty; the toolbar
      wraps into three rows (usable). The popover "Export and copy" fits. Found in the pass
      of A52.
- [ ] `minor` **A58 – Parts of A52 that the second pass could not check:** open are the page change
      of the results (12 generated photos fit on one page), the contents of "Clean up
      storage" with entries (the scan listed eleven times "nothing to clean up"), person
      crops, a long run, and the state line while a search runs at the widths of A54.
      Checked without findings: marking (Match, No, take back, reload keeps the marks), the
      dialog (Esc, M, N, S, Left; M and N move to the next undecided photo), "Find similar",
      a profile with a reference image (the reference photo scores 1.000), the dark theme
      (cards, marks, dialog, popover), the popover "Export and copy" at 420 px, copy and
      export notices. Photo set: 12 generated images, not real photos; the narrow widths
      were an iframe of that width in Chrome. Kind `docs`.
- [ ] `minor` **A59 – The popover button "More" of a result card is taller than "Match" and "No
      match":** the three buttons of a card's action row differ in height; the same height
      would look tidier. Reported by the user in chat, not measured in the browser. Found
      after the pass of A52.

### Installation / project

- [ ] `parked` **I2 – Tests are incomplete (umbrella; parked: tests are added with each item):**
      open are tests for cache signature reuse and scoring, tests of `app.py` itself (e.g.
      Streamlit's `AppTest`, which needs Streamlit in CI), a repeatable, committed browser
      check (a script or a tool such as Playwright, a new dependency), a test of the `.bat`
      files and a smoke test with real models.
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
      and the support limits in `framescout_core.torch_build.CUDA_BUILDS` (not verified), other GPUs
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
- [ ] `decision` **I43 – Drop legacy names with one migration (simplification, breaking):** the prototype
      has no release yet but carries compatibility code for its own earlier states: the crop
      label `Gesamtbild` in old cache rows, the thumbnail folder `results/vorschaubilder/`,
      the profile field `franchise` (meaning "Context / origin"), the CLI option
      `--character` and `LEGACY_PHOTO_FOLDER` in the settings. Migrate the user's files once
      (with a backup, as the profile conversion does), rename, and remove the compatibility
      paths; best together with the first release `v1.1.0` as the cut. Breaking change of the
      `profiles.json` schema and the CLI (hold point): decide per name. Found on 2026-11-12 in
      a simplification review.
      Triage 2026-11-15: stays open; better together with the release v1.1.0. **Question:** per name, migrate or keep.
- [ ] `decision` **I44 – Reduce defensive handling of rare cases, starting with the storage cleanup
      (simplification):** `framescout_core/cleanup.py` has about 1,300 lines and
      `tests/test_cleanup.py` about 1,500, more than the whole engine: reachability probes of
      drive roots in threads, hanging network shares, fstab mount points, dead links. A
      simpler rule ("a root that does not answer → offer nothing of that category") would
      probably need a third of the code. Review `uninstall.py`, `install_check.py` and
      `disk_space.py` in the same way. Each removal gives up protection against a rare case,
      so list per module what would go and let the user decide (the deletion rules for user
      data and `NEVER_DELETED` stay). Found on 2026-11-12 in a simplification review, by
      sampling, not by reading every module.
      Triage 2026-11-15: stays open; list per module what would go, then decide.
      Triage 2026-11-17: step 1 (the list, docs only) is roadmap P49; the removal itself stays
      `decision` until the user has seen the list.
      **Step 1 result (2026-11-17; sampled reading of the four modules, line counts of
      `cleanup.py` about 1,300 / `uninstall.py` 430 / `install_check.py` 330 / `disk_space.py`
      260, tests 1,540 / 790 / 450 / 365). Per module what would go and the case it gives up;
      the deletion rules for user data and `NEVER_DELETED` stay in every option.**
      - `cleanup.py` – the unbound-photo check (`_PathCheck`, `_pass`, `_FolderWorker`, the
        probes, `_unchecked_notes`; about 500 lines in `cleanup.py` plus about two thirds of
        its tests). Simple rule instead: probe each root once (one `os.path.isdir` in a thread
        with a timeout, or none) and offer "unbound" rows only for photos whose root answers
        and whose parent folder exists and is not empty; otherwise offer nothing of that
        category and say so in one line. Goes: (a) the per-folder timeout worker with the
        "still hanging" bookkeeping (E37): a share that stops answering mid-pass stalls the scan
        until the OS gives up; (b) the second pass and the second probe after the first
        (a share that drops during the pass could make its photos look deleted: wrongly offered
        rows, deleted only after the user's confirmation and only cache rows or marks); (c)
        `_dead_link`/`_link_above` (junction or link to a disconnected drive inside a
        reachable root); (d) the fstab and mount-root logic of `_unmounted` (E54; the simple
        rule "parent folder empty or missing -> not checked" covers most of it); (e) the
        five different "not checked" notes become one; (f) the per-folder listing
        optimization (`_STAT_UP_TO`, listing instead of stats; slower on large network
        folders, correct). Keep: `_missing` (only a certain "not found" counts) and the
        root probe. The other categories (thumbnails, galleries, temp files, signatures,
        references, broken files) are not defensive handling of rare cases and stay.
      - `uninstall.py` – candidates: (a) `outside_leftovers` (lists, never deletes, caches
        of FrameScout run without its scripts, I10): drop, the user guide says where the
        caches are; (b) `_retry_writable` and the read-only handling (`programs_in_use`
        `clear_read_only`): a read-only file then ends in the failure list instead of being
        deleted; (c) `_held_open` on Windows via `_winapi`: replace by the existing locks
        (`search_running`, `app_running`) plus the failure list of `remove_items` (a running
        program then shows up as a failed delete, not before the confirmation). Keep: the
        protected-folder and `USER_DATA` logic, the links handling (it protects data outside
        the folder), `PRIVATE_PYTHON_EXIT_CODE` (needed for the clean uninstall).
      - `install_check.py` – the check is diagnostic only. Candidates: (a) `check_models`
        with the reachability probe of the model cache (information only: drop the probe or
        the whole check); (b) the `check_torch` subprocess variants (timeout, OSError,
        parse error each have their own text: one generic "PyTorch does not import: <last
        stderr line>"); (c) `check_program_files` (two-version-files case after extracting a
        ZIP over another version, I34/I42; a real case seen once, keep unless the user
        decides otherwise); (d) `_same_folder` through 8.3 short names and links. Keep:
        `check_environment`, `check_packages`, `check_writable`, `check_disk_space`.
      - `disk_space.py` – the estimates (`search_space_*`, `torch_install_needs`) are the
        feature; the defensive part is `low_space`: the root probe in threads (a hanging
        share), the volume identity by device number and size, `_existing_folder`. Simple
        rule: `shutil.disk_usage` of the nearest existing folder per need, add up needs by
        the same `usage` tuple, no probe. Gives up: a warning check that hangs the app for
        a dead share's timeout (only if the destination is on such a share; results and
        cache usually are not) and the exact merging of one drive reached by two paths.
        `analyzed_paths` stays (A44).
      Rough effect if all options are taken: about 700 lines of code and 1,100 lines of
      tests less; `cleanup.py` shrinks to about 700 lines. **Question for the user:** per
      module and lettered option, remove or keep (the cleanup root and folder guards are the
      only options that give up protection near user data: a wrongly "unbound" row is only
      a cache row or mark, and deletion needs the user's confirmation).
- [ ] `parked` **I46 – One place for dependencies: `pyproject.toml` with a lock file (simplification):**
      versions live in `requirements/requirements.txt`, `requirements-dev.txt`,
      `constraints.txt`, as constants in `framescout_core/torch_build.py` and
      `portable_python.py`, with tests that compare them. A `pyproject.toml` with a lock file
      (e.g. `uv.lock`) would be one source; `uv` could also download the private Python and
      choose the CPU/CUDA index, replacing parts of `Install-FrameScout.bat`,
      `install_torch.py` and `portable_python.py`. New tool and download in the installer
      (hold point); check the offline behavior, the checksum of the `uv` download and the
      clean uninstall first. Found on 2026-11-12 in a simplification review.
      Triage 2026-11-15: parked until the distribution (P5) is due; new tool in the installer.

### Features (from [docs/IDEAS.md](IDEAS.md))

- [ ] `decision` **F6 – "Not this" search texts per profile:** a profile "red car" also ranks
      toy cars or posters high; A20 covers rejected marks, but there is no way to say up front
      what a motif is not. Sketch: an optional "Exclude texts" field per profile; in
      `framescout_scoring` a crop's score drops by a weighted z-scored similarity to the best
      exclude text (`z_text - λ·max(0, z_exclude)`); the engine encodes them like custom
      prompts, no cache change. Affected: `app.py`, profile validation and `search_fingerprint`,
      `framescout_scoring`, `framescout_engine.py`, `assets/profiles.example.json`, tests, user
      guide. Risks: CLIP handles negation poorly, so it must be a separate query; a too strong λ
      buries real matches. **Question:** additive optional `profiles.json` field (schema change)
      and search quality (λ tuned on a local evaluation set, E32/E20). Size M.
- [ ] `decision` **F7 – Group near-duplicate and burst shots in the results:** bursts fill
      result pages with the same moment. Sketch: group ranked photos of one folder whose cached
      full-image embeddings have cosine ≥ ~0.95, show the best as the card ("+6 similar",
      expandable); numpy only; toggle "Group similar photos"; marking a group card could offer
      "apply to all in group". Affected: `framescout_scoring`, engine and
      `framescout_core.results.result_card` (additive `group` field in `results.json`, check the
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
- [ ] `ready` **F9 – A CSV export that Excel opens in columns in every locale:** the result
      list export (F5) writes a comma-separated CSV (RFC 4180). Excel splits a double-clicked
      CSV at the list separator of the system locale, which is `;` in German and other
      comma-decimal locales, so there every row lands in one column; the user guide points to
      Data → From Text/CSV. Options: a "Separator: comma / semicolon" choice next to the export
      button (a `setting_<name>` widget in `settings.json`), or a `sep=,` first line (Excel
      only, breaks other CSV readers and RFC 4180). With `;` the decimal point stays `.`, so
      Excel may still read the scores as text there. Affected: `framescout_core/exporting.py`
      (`export_csv`), `app.py` (`show_export`), user guide, `tests/test_export.py`.
      Decided 2026-11-17: a "comma / semicolon" choice (roadmap P51). Found in the review of
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
- [ ] `decision` **F33 – HTML gallery parity with the app:** the gallery has a fixed dark theme,
      no marks, no paging and no way back to the navigation. **Options:** (a) light/dark by
      `prefers-color-scheme`, file name first, link to the top; (b) also show marks (baked in at
      export, stale afterwards); (c) leave it a plain export. Affected:
      `framescout_engine.py`, user guide. F24 review §5. Size S–M.
      Triage 2026-11-13: not decided; assess again after F30, because in the browser pass the
      gallery (seven equal columns over the full width) was easier to scan than the app.
- [ ] `parked` **F36 – A folder dialog for the photo source:** the photo folders are a text
      area; the path has to be typed or pasted. Streamlit has no folder dialog. Sketch: a
      "Choose folder" button that opens the system dialog on the PC the app runs on.
      **Question:** how, without a new dependency (e.g. `tkinter`, if the private Python of
      the installer ships it; check first) and whether a dialog opened by the server process
      is acceptable. Affected: `app.py`, user guide. Found in the browser pass of 2026-11-13.
      Size S. Triage 2026-11-17: parked, because `tkinter` in the private Python is unchecked and
      a dialog from the server process is unreliable on Linux/WSL.
- [ ] `decision` **F45 – The best crop outlined in the large preview:** this part of F19 is not
      done, because neither the results nor the feature cache store a crop's box (the engine
      computes it in `crops_for` and keeps only label and embedding). Sketch: store the person
      box (relative coordinates) in the cache rows and in the result cards (`result_card`, an
      optional key), then draw it in the review dialog. **Question:** a cache signature or a
      new column and a result format change (hold point). Affected: `framescout_engine.py`,
      `framescout_core`, `framescout_ui/review.py`, user guide. Found in F19. Size M.
- [ ] `hardware` **F48 – One full search in WSL2:** run the Linux scripts of F47 on the home PC
      (WSL2, Ubuntu): install, start, a full search with the CPU build, then with CUDA (needs the
      Windows NVIDIA driver; unverified) and uninstall; fix what shows up, record the result in
      `docs/ARCHITECTURE.md` → "Verified status". Needs F47 PR 2 first. Progress 2026-11-16:
      one full search with the CPU build ran in WSL2 (Ubuntu) through the app: 4997 photos,
      3 profiles, 0 errors, about 5 minutes (lock and log timestamps), three HTML galleries
      written, results shown in the app. Still open: CUDA, `Check-FrameScout.sh`,
      `Uninstall-FrameScout.sh`, opening a gallery in the browser. For the CUDA run (F47 part
      3): that nvidia-smi in WSL2 reports the Windows driver's number (WSL is compared with
      the Windows minimums of `CUDA_BUILDS`), and whether the Linux CUDA wheels pull in packages that
      `requirements/constraints.txt` does not pin (e.g. `nvidia-*`, `triton`; the CPU
      environment in WSL2 has only pinned packages).
- [ ] `decision` **F49 – Choose which profiles a search runs:** a search always scores and exports
      every profile, so refining one profile replaces the other profiles' results too. Sketch: a
      checkbox "Include in the next search" per profile (default on), stored as a list of
      skipped profile names in `settings.json` (not `profiles.json`), a note in the summary before
      the start, the engine gets a filtered profile file or `--only-profile`; the results of
      skipped profiles stay, so `results.json` needs a merge rule. Affected:
      `framescout_ui/profiles.py`, `framescout_ui/run.py`, `framescout_core/settings.py`,
      `framescout_core/results.py`, maybe `framescout_engine.py`, user guide, ARCHITECTURE.
      Risks: results of different runs side by side must be visible per profile; interacts with
      F13; a renamed profile must not stay skipped. **Question:** merge semantics of `results.json`
      and a new CLI option. Size M. Idea of 2026-11-16.
- [ ] `ready` **F50 – Quick search with an example image:** "Find similar" works only from a result
      card, so a single outside example picture needs a profile and a full search. Sketch: an
      optional image upload next to the quick search text; the engine embeds only that image
      (model load, no analysis of the folders) and ranks the analyzed photos, alone or with the
      text through the reference weight; the upload lives in `results/quick/`, replaced by the next
      quick search, never copied into `references/`. Affected: `framescout_ui/run.py`,
      `framescout_core/quick.py`, `framescout_engine.py`, user guide, ARCHITECTURE. Risks: the quick
      search then needs a model load and the progress/stop handling of a run; HEIC/RAW uploads need
      the decoders; artwork-to-photo comparisons stay unreliable (caption). Size M. Idea of
      2026-11-16; not on the roadmap by user decision.
- [ ] `ready` **F51 – Recent quick search texts:** the quick search remembers only the last text.
      Sketch: keep the last 10 distinct texts in a small JSON file in `results/quick/` (atomic
      write; an unreadable file is ignored with a warning, never replaced), a selectbox above the
      text field, and "Save as profile" through the locked profile save (`ProfilesChangedError`,
      A13; a taken name gets a suffix). Affected: `framescout_core/quick.py`, `framescout_ui/run.py`,
      user guide, ARCHITECTURE (does cleanup keep the file). Size S. Idea of 2026-11-16; not on the
      roadmap by user decision.
- [ ] `decision` **F52 – Reuse analyses after the photo library moved:** cache rows are keyed by the
      resolved path, so a new drive, a renamed top folder or a changed drive letter makes every
      photo "not analyzed" (hours on a CPU-only PC). Sketch: for a photo without a valid row, copy
      the embeddings of a row of the same signature whose file is gone and whose name, size and
      `mtime_ns` are equal (old row stays until "Clean up storage"; marks are not moved, A21);
      the log says "N analyses reused from moved photos". Affected: `framescout_engine.py`, a
      helper tested on a temporary SQLite file, ARCHITECTURE ("Feature cache"). Risks: a wrong
      match silently gives a photo another photo's embedding; needs mtime-keeping copies; an index
      on size for 100,000 rows. **Question:** the match rule (a content hash would change the
      cache format). Size M. Idea of 2026-11-16.
- [ ] `ready` **F53 – Score distribution per profile:** users cannot tell whether good matches
      end at place 20 or continue past 150. Sketch: a collapsed small chart above a profile's
      results with a compact histogram (about 40 bins, written into `results.json` by the engine)
      and a marker at "Maximum matches"; the caption says scores are relative heuristics, never
      probabilities; Streamlit's built-in chart. Affected: `framescout_scoring`,
      `framescout_engine.py`, `framescout_ui/results.py`, user guide, ARCHITECTURE. Risks: a gap
      in the curve read as a certainty threshold; the results page is dense (A50/A51).
      Decided 2026-11-17: yes, roadmap P52 (additive `results.json` field, caption that scores
      are relative heuristics). Size S–M. Idea of 2026-11-16.
