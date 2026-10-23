# FrameScout – Backlog

Result of the code analysis from 2026-10-20 (state v1.1). Work through the items one by
one and check them off here. IDs (E = engine, A = app, I = installation/project) are
referenced in commits, pull requests and discussions.

## Known weaknesses

### Engine (`framescout_engine.py`)

- [x] **E1 – QuickGELU mismatch:** `create_model_and_transforms('ViT-B-32', pretrained='openai')`
      emits the warning `QuickGELU mismatch`; the OpenAI weights run with GELU instead of
      QuickGELU → worse embeddings. Fix: `ViT-B-32-quickgelu` or `force_quick_gelu=True`,
      bump the `ENGINE` signature (the cache is rebuilt once).
      (done 2026-10-21: `ViT-B-32-quickgelu`, same weights file; model name, `ENGINE` (v5)
      and `feature_signature` live in `framescout_core` with tests. Every photo is
      analyzed once more after the update; the v4 rows stay in `cache.sqlite3` (E11).)
- [x] **E2 – No batching across images:** `embed_images` only receives the crops of a single
      photo, so the batch size has almost no effect. Also: no parallel decoding, full
      resolution (no `Image.draft`), YOLO hard-coded to `device='cpu'`.
      (done 2026-10-21: photos are stat-ed, decoded, searched for persons and preprocessed
      in four threads, two with person detection (at most two full-resolution photos in
      memory), at most `max(2 × threads, --batch-size + threads)` photos ahead
      (`framescout_core.prefetch`); the crops of several photos go through CLIP in one pass
      of at most `--batch-size` crops (`group_batches`), one SQLite transaction per group,
      photo by photo after a failure (`store_group`). Without person detection JPEGs and
      all gallery thumbnails are decoded with `Image.draft` at twice the target size
      (`draft_size`); with person detection photos keep full resolution (E15). On a
      ~200-photo sample (CPU) the features with detection are identical, without detection
      cosine ≥ 0.999, gallery scores differ by ≤ 0.004. Cache signature: unchanged with
      detection; without detection it names the drafted decoding (user decision in the
      review), so the first such run analyzes every photo once more and the old rows stay
      in `cache.sqlite3` like after E1 (E11). Whole runs incl. model load and export took
      44 s → 19 s with and 30 s → 10–15 s without person detection. YOLO device: E14;
      thread counts on small CPUs: E17.)
- [x] **E3 – German motif names in English prompts:** e.g. "A photograph of Rotes Auto
      (Fahrzeuge)." – OpenAI CLIP practically only understands English, while the UI
      placeholders were German (English since I7).
      (done 2026-10-23 by communication, user decision in PR #12: FrameScout supports
      English search terms only. The profile tab shows a hint and labels the motif,
      context, features and custom search text fields "in English"; README section
      "Search terms in English". Hint text only: no check of the input, no warning, no
      translation, no extra profile field. Measured with the current model on one
      collection (about 5,000 cosplay photos, PR #12 comment): German queries found the
      nearest English query for 25 of 40 everyday words; the German and English top 50
      agreed by 0–58 % for 16 motifs of the collection; "Sword" AP@40 0.721 vs
      "Schwert" 0.000 (German top 40 mostly unlabelled, so a lower bound). Multilingual
      model: E21.)
- [x] **E4 – Maximum instead of mean over prompts:** prone to noise; a generic prompt can
      dominate. An averaged prompt ensemble is common practice.
      (done 2026-10-23: `framescout_scoring.text_queries` averages the generated templates,
      including the `features` templates, into one query; custom prompts stay queries of
      their own and the best query counts (user decision in PR #11). On the local
      evaluation set (PR #11, E20) text-only AP@40 over five profiles went 0.753 → 0.786,
      better for two profiles, worse for one, mixed for one, equal for one.)
- [x] **E5 – Mixed score scales:** text cosine ≈ 0.2–0.35, image-to-image ≈ 0.5–0.9; the
      reference weight therefore has a much stronger effect than its nominal value.
      (done 2026-10-23: per profile and run, text and reference scores are z-scored
      separately over all crops of the search before the weight combines them, raw scores
      below 10 crops or without spread (`framescout_scoring.rank_photos`); the gallery
      shows the score with the raw text and image similarity. Measured spread: reference
      scores about twice as wide as text scores. Default reference weight 0.35 → 0.3
      (`DEFAULT_REFERENCE_WEIGHT`, best on the evaluation set, user decision); a value
      saved in `settings.json` is not migrated. With references AP@40 over three profiles
      went 0.683 (main) → 0.782. No cache change.)
- [x] **E6 – `path.stat()` outside `try`** in the export (line ~264): a file deleted in the
      meantime aborts the entire HTML export.
      (done 2026-10-21: `framescout_core.ensure_thumbnail` logs "Thumbnail not possible"
      and the photo is skipped; thumbnail names are unchanged. Rank gaps: E12.)
- [ ] **E7 – No cleanup:** `thumbnails/`, `cache.sqlite3` (deleted files, old
      signatures) and HTML files of renamed/deleted profiles grow without bound. Since
      I7 the thumbnail folder of older versions, `vorschaubilder/`, is no longer written
      but stays in `results/` (galleries of profiles that were not regenerated still
      link it).
- [ ] **E8 – Cache key = absolute path:** moving the photo folder forces a complete
      recomputation.
- [ ] **E9 – `yolo11n.pt` ends up in the project root** instead of `.cache/`; not documented.
- [x] **E10 – Duplicate check before `strip()`:** "Joker" and " Joker" are not recognized as
      equal. (done 2026-10-21 in `framescout_core.load_profiles`; such a hand-edited
      `profiles.json` is now rejected instead of merging both profiles into one gallery.)
- [ ] **E11 – Dead cache rows after an `ENGINE` bump:** after E1 (v4 → v5) every v4 row
      (GELU embeddings) stays in `results/cache.sqlite3` and can never be reused, so the
      file roughly doubles on the first run after the update and never shrinks. The
      `signature` column is a hash, so rows of old engine versions can only be found for
      setting combinations that are known in advance (e.g. the v1.1 defaults). Fix idea:
      store `ENGINE` in its own column, then delete rows of other engine versions and
      `VACUUM` – only with the user's consent (the cache is user data). Part of the
      cleanup in E7.
- [ ] **E12 – Skipped photos leave gaps in the gallery:** a photo whose thumbnail fails
      (deleted since scoring, unreadable) is skipped after the top-N cut, so the gallery
      shows e.g. #2, #3, #4 and fewer than `--top` cards although lower-ranked photos
      exist. Fix idea: rank only the photos that got a card and fill up to `--top`.
      Also: `ensure_thumbnail` repeats the `stat()` done during scoring; the mtime could
      be kept with the score (PR #6 review).
- [ ] **E13 – Interrupted thumbnail writes leave temporary files:** since PR #6 a
      thumbnail is written as `thumbnails/<hash>.jpg.<random>.jpg` and renamed when
      complete. The app's Stop button ends the engine with `terminate()`/`kill()`, which
      on Windows skips the `finally` that removes the temporary file, so each stop
      during the export can leave one such file; it is never reused (no broken
      thumbnail), only clutter. Fix idea: a recognizable `.tmp` name that the next run
      (or the cleanup of E7) removes. Since A4 only one engine at a time uses an output
      folder (`run.lock`), so a run holding the lock can remove such files safely.
- [x] **E14 – YOLO runs on the CPU, one photo at a time:** `crops_for` passes
      `device='cpu'` to the detector, even when CLIP runs on CUDA, and since E2 the decoding
      threads share one detector under a lock, so detection is serialized. With person
      detection on (the default) it is now the slowest step on the CPU: `--batch-size` 1, 8
      and 32 took 26 s, 23 s and 24 s for the same 202 photos. Fix idea: run YOLO on the
      CLIP device and pass it several photos per call; part of the roadmap item "YOLO on
      GPU". CUDA cannot be verified on the development PC (no CUDA torch, A7).
      (done 2026-10-21: the detector runs on the CLIP device, `framescout_core.detection_options`;
      on the CPU the cached features are unchanged (same signature, identical vectors on
      40 photos). On a GPU only one smoke run so far (I11). Several photos per call: E18.)
- [ ] **E15 – No `Image.draft` with person detection:** since E2 photos are decoded at
      reduced scale only without person detection; with detection they keep full
      resolution, because a person crop in a group photo can be smaller than CLIP's
      224 px input after scaling. Drafting to a larger size (e.g. both edges ≥ 1280 px)
      would speed up the decoding of large photos (≥ ~10 MP), but changes the person crops
      and needs an evaluation with group photos (search quality) and possibly scaling the
      minimum crop size of 35×70 px with the draft factor.
- [ ] **E16 – Every engine start contacts the Hugging Face Hub:** the log shows
      "You are sending unauthenticated requests to the HF Hub" on each run although the
      CLIP weights are in `.cache/huggingface`: OpenCLIP checks the hub for a newer file.
      No image data is sent, but the run needs (or waits for) the network, which is
      surprising for a local tool. Fix idea: set `HF_HUB_OFFLINE=1` once the weights are
      cached (or try offline first and fall back to a download), in the engine or the
      `.bat` files; check the behavior without internet access.
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
      the README depends on the selected model. SigLIP 2 (a candidate of E22) has a
      multilingual tokenizer and training data and may cover this item as well; check
      it with German queries before adding `xlm-roberta-base-ViT-B-32`. A download and a
      new dependency are hold points.
- [ ] **E22 – Only one CLIP model, no stronger option:** FrameScout always uses OpenAI
      CLIP ViT-B/32. Investigated in PR #13 (no weights downloaded; continue from here).
      **User decisions (PR #13):** the default stays `ViT-B-32-quickgelu`/`openai`; if a
      SigLIP model is chosen, `transformers` goes into `requirements.txt`; the
      evaluation runs on the user's home PC, so the roadmap item moved behind P4; the
      list of offered models is still open.
      **Candidates** (open_clip 3.3.0 names). CPU time: `encode_image`, batch 8, random
      weights (weights do not change the speed), Core Ultra 9 285K with 12 torch
      threads; every row measured, repeated runs differ by up to ~5 %; a typical laptop
      CPU is probably 3–5× slower, the factor is the portable part. RAM: fp32 parameters. ImageNet zero-shot and Flickr30k retrieval from
      open_clip's `docs/openclip_results.csv`.

  | Model / weights | Download | RAM | CPU ms/crop | Factor | ImageNet | Flickr | Extra dependency | License |
  |---|---|---|---|---|---|---|---|---|
  | `ViT-B-32-quickgelu` / `openai` (default) | 605 MB | 0.6 GB | 10.7 | 1× | 63.3 % | 0.69 | – | MIT |
  | `ViT-B-16` / `datacomp_xl_s13b_b90k` | 599 MB | 0.6 GB | 41.4 | ~4× | 73.5 % | 0.76 | – | MIT |
  | `ViT-B-16-SigLIP` / `webli` | 813 MB | 0.8 GB | 42.6 | ~4× | 76.0 % | 0.82 | `transformers` | Apache-2.0 |
  | `ViT-B-16-SigLIP2` / `webli` (224 px; `-256`: 54.8 ms) | 1.50 GB + 34 MB tokenizer | 1.5 GB | 42.2 | ~4× | ~78 % (paper, unverified) | – | `transformers` | Apache-2.0, multilingual |
  | `ViT-B-32-SigLIP2-256` / `webli` | 1.51 GB | 1.5 GB | 14.1 | ~1.3× | ~74 % (paper, unverified) | – | `transformers` | Apache-2.0, multilingual |
  | `ViT-L-14` / `datacomp_xl_s13b_b90k` | 1.71 GB | 1.7 GB | 190.4 | ~18× | 79.2 % | 0.81 | – | MIT |
  | `ViT-L-14-quickgelu` / `openai` | 1.71 GB | 1.7 GB | 200.9–204.9 | ~19× | 75.5 % | 0.75 | – | MIT |

  Left out: Apple's DFN2B weights (best B/16 and L/14 figures, but license
      `apple-amlr`, research only) and `ViT-SO400M-14-SigLIP` (3.5 GB, ~24×, 82.0 %: not
      worth it on a CPU). The DataComp repositories ship only `.bin` (pickle) weights.
      `transformers` 5.x needs `huggingface-hub>=1.31,<3` (2.2.0 installed) and
      `tokenizers` 0.23 (abi3 wheel); about 16 MB, Python 3.14 untested; the SigLIP
      tokenizers ship `tokenizer.json`, so `sentencepiece` should not be needed
      (unverified). Speed matters only for the first analysis and new photos: cached
      features keep later searches fast. Whole runs on this PC with person detection
      (1.85 crops per photo on the ~5,000-photo collection), estimated from the E2 timings
      and the per-crop times, not run: default ~7 min, B/16 class ~12 min, L/14
      ~35–40 min.
      **Planned plumbing:** a `MODELS` registry in `framescout_core` (stable key →
      open_clip name, pretrained tag, label, download size, CPU factor, extra
      dependency, `multilingual` flag); `engine_id(model)` returns exactly today's
      `ENGINE` for the default, so its `feature_signature` stays identical (golden test)
      and no photo is analyzed again; `feature_signature(..., model=DEFAULT_MODEL)`; a new
      optional engine option `--model <key>` with the registry keys (no free-text names);
      settings key `model` (validated like `device`); a selectbox in the AI settings tab
      whose labels show the CPU factor and the first-use download size, and a caption
      that a new model analyzes every photo once while the cache keeps the rows of each
      model side by side (never deleted, E11; ~14 MB per model for 5,000 photos); the
      model name in the log line and the gallery note; the QuickGELU config check of
      `test_signature.py` for every registry entry. Already model-independent:
      `draft_size` reads the model's input size, the z-scores (E5) absorb the score
      scales; only the raw-score fallback shows other numbers (SigLIP cosines are lower).
      **Evaluation plan** (search-quality hold point; E20): implement the plumbing
      first, then run each candidate with `--model` into `.tmp/`. The existing labels
      (`.tmp/eval-labels/` in the original checkout, not in the repository: five usable
      profiles on the ~5,000 cosplay photos) judge only the top 40 of ViT-B/32 variants,
      so each model needs a new labelling pool (about 100–250 judgments per model), then
      AP@40 per profile and a re-check of the reference weight (0.3, E5) per model. Add a
      second, non-cosplay collection (E20). On another PC, the labels, the photos and
      the tooling have to be brought along or made anew.

### App (`app.py`)

- [x] **A1 – Reference images get overwritten:** uploads are always named `reference-1…n`;
      a second upload overwrites the first ones. Profiles with the same slug
      (e.g. "Rotes Auto"/"rotes-auto") share the folder.
      (partly done 2026-10-21: uploads take the next free `reference-<n>` name and never
      overwrite a file – needed because transliteration made more names share a folder,
      e.g. "Bär"/"Baer" → `references/baer/`. Still open: one folder per profile.)
      (done 2026-10-21: `framescout_core.reference_folder` uses `references/<slug>/`, or
      `<slug>-2`, `-3`, … if that folder holds references of another profile. On a
      rename, the profile's own files under `references/` move to the folder of the new
      name (user decision in the review: the folder follows the name): hard link or
      copy first, save `profiles.json`, then remove the old names, so a crash never leaves
      paths to missing files; `profiles.json.bak` is updated to the new paths before the
      old names go (user decision, review round 2). Files of other profiles, leftovers
      and paths outside `references/` stay; a folder shared before A1 is split only when
      one of its profiles is renamed. Leftover files: A14.)
- [x] **A2 – `profiles.json` data loss:** `read_profiles` does not know the v3 format
      (returns `[]`, the next save overwrites the file). A JSON list → `AttributeError`
      (not caught). No backup before saving.
      (done 2026-10-21: `framescout_core.read_profiles` converts v3 and validates like the
      engine – an unreadable file stops the app instead of being saved over;
      `save_profiles` keeps the previous file as `profiles.json.bak` (one generation) and
      writes atomically; editing keeps keys the form does not show. Concurrent edits: A13.)
- [x] **A3 – Slugs app ≠ engine:** the engine appends `-2` on collisions and uses a hash
      fallback, the app uses `profile` without deduplication → downloads missing or
      mismatched. Umlauts are dropped ("Bär" → `b-r`).
      (done 2026-10-21: app and engine use `framescout_core.slugify`/`profile_slugs`;
      "Bär" → `baer`, "Café" → `cafe`, hash fallback for names such as "猫", Windows
      device names get `-profile`, at most 60 characters. Galleries under the old slugs
      (e.g. `b-r.html`) stay in `results/` until cleanup exists (E7).)
- [x] **A4 – Process handle only in the session:** browser reload → the run is orphaned,
      stopping is impossible, a second start is possible → two processes write to the
      same `run.log` (which gets truncated) and the same SQLite file ("database is
      locked"). Also applies to multiple tabs.
      (done 2026-10-21: the engine holds an operating-system lock on
      `<output>/run.lock` (`framescout_core.RunLock`: Windows byte-range lock, `flock`
      elsewhere), which the system releases when the process ends in any way, also after
      `kill()`; a second engine on the same output folder waits five seconds and exits
      with code 3. It writes `<output>/run-status.json` (`StatusReporter`: process id,
      phase, progress, final phase and exit code). The app derives "running" from the lock
      and that file on every rerun and every two seconds (`run_active`), so a reload,
      another tab or session shows the run, keeps the controls disabled and can stop it
      (by the process id from the file, checked to be the engine, with child processes:
      the venv's `python.exe` is a launcher whose child is the engine). Start holds the
      lock while it truncates `run.log`, spawns the engine and writes the status
      "starting", so two starts at the same moment cannot both succeed. A stop from the
      app is marked "Stopped in the app" in the status file. Verified with real runs:
      a parallel CLI start exits with 3, a killed run frees the lock, a new Streamlit
      session (AppTest) shows and stops a run started by another one.)
      (manual browser check, user report 2026-10-21: start a search, reload the page,
      open a second tab, press Stop – successful. Closing the `Start-FrameScout.bat`
      window during a run is still not tested.)
- [x] **A5 – Progress only for the analysis phase:** scoring, thumbnails and HTML export run
      afterwards without any indication while the bar is already full.
      (done 2026-10-21: the status file has the phase – starting, looking for photos,
      loading the models, analyzing, scoring, writing galleries – and the progress of
      each (photos, then gallery cards); the app shows it (`status_text`,
      `status_fraction`), and after the run "finished", "failed" with the error message
      or "interrupted". The log names the scoring and export phases as well.)
- [ ] **A6 – Folder count on every rerun:** `rglob` over the whole photo folder on every
      interaction; slow for large folders/network drives.
- [x] **A7 – CUDA never available:** pip installs torch `+cpu`; "cuda" can still be selected.
      (done 2026-10-21: `Install-FrameScout.bat` offers the CUDA build of PyTorch (I3); the
      app offers "cuda" only if `torch.cuda.is_available()`, falls back to "auto" for a
      stale setting and tells a CPU build of PyTorch from a CUDA build that finds no usable
      GPU (no GPU, or a driver too old for the build); the hint (`cuda_hint`, also in the
      engine's error for `--device cuda`) says to close FrameScout, run
      `Install-FrameScout.bat cuda` (or update the driver) and start FrameScout again. On a
      GPU: one engine smoke run; the app's device choice there is untested, I11.)
- [ ] **A8 – UX gaps:** deleting a profile without confirmation; settings only per session;
      results without timestamp/reference to the profile state. Since A4 a reload shows a
      running search again, but the settings and the photo folder it was started with are
      back at their defaults (the status file does not record them).
      (partly done 2026-10-21: the settings – photo folder, device, batch size, top,
      person detection with its maximum and confidence, reference weight – are kept in
      `settings.json` in the project folder (gitignored), so a reload, a restart, another
      tab or session shows them, also for a running search. The app reads the file on
      every rerun (retrying a read that fails while another session replaces it) and
      saves the values changed in a page run merged into the current file
      (`framescout_core.read_settings`/`save_settings`); only values that differ from the
      defaults are written, so the default photo folder follows a moved project folder.
      The widgets have keys and get the saved values through their session state (passed
      as `value=`, every save gave them a new identity and dropped the next change, PR #10
      review; the session-only settings before A8 had the same bug: in a browser every
      second change of a setting jumped back to the first). `reconcile_settings` tells a
      change made in a session from another session's save, so the latest action wins;
      a Start in a page run that took over another session's values is refused once with
      a note, so a search never runs with settings the user has not seen. Saves hold a
      lock (`settings.json.lock`) around their read-merge-write, so two sessions saving
      at the same moment keep both changes (second review). Invalid values fall back to their defaults with a warning
      and are removed with the next save, an unreadable file is never replaced (the page
      keeps the settings it shows), and a saved device PyTorch cannot use is used as
      "auto" but stays saved until another device or "Use auto from now on" is chosen.
      Still open: deleting a profile without confirmation; results without timestamp or
      reference to the profile state, see A12.)
- [x] **A9 – Minor issues:** duplicate `import os`; `EXT` duplicated in app and engine;
      `use_container_width` possibly deprecated (Streamlit 1.66).
      (done 2026-10-21: duplicate import removed, `EXT` lives in `framescout_core`;
      `use_container_width` moved to A10.)
- [ ] **A10 – `use_container_width` is deprecated:** in Streamlit 1.66 the `st.button`
      docstring marks it as deprecated in favor of `width="stretch"` (no runtime warning
      yet; it still works). `width` for buttons is newer than the current floor
      `streamlit>=1.40` (the release notes name 1.48 – not verified), so switching needs
      a raised minimum version → do it together with I3.
      (I3 is done, but the user kept the Streamlit floor at `>=1.40` in PR #8: raising
      it and switching to `width` belong together in this item.)
- [x] **A11 – Progress bar parses German log text:** the app reads progress from `run.log`
      with a regex on `Neu:`/`Cache:`/`Fehler:`. Translating the engine log (I7) breaks
      the progress bar unless both change together; a machine-readable progress line or
      status file (see P2) plus a test for the progress interpretation would decouple it.
      (partly done 2026-10-21: the line format lives in `framescout_core.progress_line`,
      the app parses it with `parse_progress`, both tested; the line is English now.
      Still open: a machine-readable status file (P2).)
      (done 2026-10-21 with A4/A5: the app reads the progress from `run-status.json`;
      `parse_progress` is removed, the progress line stays in the log for people.)
- [ ] **A12 – Gallery downloads are re-derived from the current profile list:** the app
      maps profiles to `<slug>.html` with `profile_slugs` on the *current*
      `profiles.json`. After deleting, renaming or reordering profiles with colliding
      slugs, a button can serve another (deleted) profile's stale gallery, e.g. delete
      "Rotes Auto" → "rotes auto!" now maps to the old `rotes-auto.html`. Fix: the engine
      writes a manifest (profile name → file, run timestamp) that the app reads – a new
      output format, so a design decision; fits the status file of P2 and A8 ("results
      without reference to the profile state"). Since A4 the engine writes
      `results/run-status.json`; the manifest could become part of it.
- [ ] **A13 – Concurrent profile edits are lost:** the app reads `profiles.json` on every
      rerun and saves its whole list, so an edit made in another tab/session (or by hand)
      between that read and a save is overwritten; `profiles.json.bak` holds only the
      state before the last save. Fix idea: save only if the file is unchanged since it
      was read (mtime/hash), otherwise reload and ask. More than one backup generation
      (rotating `.bak` files, a one-time copy before the v3 conversion) also belongs
      here; for now the user chose a single `profiles.json.bak` (PR #6 review).
- [ ] **A14 – Unreferenced reference files accumulate:** removing reference images from a
      profile, deleting a profile or a failed save of `profiles.json` after the upload
      leaves the files in `references/` (deliberately – nothing is deleted silently).
      Fix idea: list files no profile references and offer to delete them, with the
      user's consent; part of the cleanup in P4.
- [ ] **A15 – Reference folder and gallery file can get different suffixes:**
      `reference_folder` adds `-2`, `-3`, … when another profile's references occupy the
      folder, `profile_slugs` adds them by profile order. The same profile can therefore
      have `references/red-car-2/` but `red-car.html` (or the reverse). Nothing breaks,
      but the names are harder to explain. Fix idea: derive the folder from
      `profile_slugs` with a fallback for occupied folders – note that the order-based
      slugs change when profiles are deleted or reordered, which would then move folders
      (design decision, PR #6 review).
- [ ] **A16 – An empty photo folder searches the app's working directory:** `Path('')`
      is `.`, so with the folder field emptied, "Start search" is enabled and the engine
      gets the folder the app was started in – with `Start-FrameScout.bat` the project
      folder, including `.venv/` (whose packages ship PNG files) and `references/`.
      Older than A8, but since A8 an empty field is also saved in `settings.json` and comes
      back after a restart. Fix: treat an empty or whitespace-only folder as missing in the
      app (and possibly reject it in the engine). Found in PR #10.

### Installation / project

- [x] **I1 – No git repository.** (done 2026-10-20)
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
- [x] **I3 – `requirements.txt` unpinned;** no CUDA option in the installer.
      (done 2026-10-21: `torch==2.14.1` and `torchvision==0.29.1` are pinned
      (`framescout_core.TORCH_VERSION`/`TORCHVISION_VERSION`, a test keeps both in sync);
      the other packages have the versions of the verified runs as minimum, Streamlit keeps
      `>=1.40` (A10); no upper bounds (user decision, I12). `Install-FrameScout.bat
      [cpu|cuda]` installs PyTorch first with `install_torch.py` from the PyTorch index
      (dependencies also from PyPI). Without an argument an installed CUDA build is kept,
      otherwise it asks only if `nvidia-smi` finds an NVIDIA driver; for CUDA
      `framescout_core.cuda_build` picks `cu130` (compute capability ≥ 7.5, driver ≥ 580)
      or `cu126` (5.0 to 9.x, driver ≥ 528.33), preferring a build for every GPU, else the
      one for the most capable GPU; if none fits, an installed CUDA build is kept,
      otherwise the CPU build is installed. Only an explicit `cpu` replaces a CUDA build
      (PR #8 review); a matching build is not downloaded again (PyPI's CPU wheels without
      `+cpu` count as the CPU build). The support limits are from the CUDA/PyTorch
      documentation as known, not verified (I11: one smoke run with `cu130` on one GPU).
      Full locking incl. transitive dependencies: P5.)
- [ ] **I4 – Installer requires the `py` launcher;** without it, the misleading message
      "Python 3.12 to 3.14 not found." is shown.
- [x] **I5 – Example profiles/placeholders lean towards cosplay** (Joker, Harley Quinn, 2B,
      "Batman / DC Comics") – contradicts the general-purpose product goal.
      (done 2026-10-21: `profiles.example.json` ships Red car, Golden retriever, Mountain
      landscape, Bicycle, Birthday cake and Person with umbrella; the context
      placeholder is "e.g. vehicles, pets, nature".)
- [x] **I6 – Update `CLAUDE.md`:** record the successful end-to-end run (`run.log`: 4,997
      photos, 6 profiles, 0 errors; `.venv`: Python 3.14.8, torch 2.14.1+cpu).
      (done 2026-10-20)
- [x] **I7 – Project language English:** translate the UI strings in `app.py`, the HTML
      gallery and log/error messages in `framescout_engine.py`, the `.bat` messages, code
      comments (including `.gitattributes`). Open decisions to resolve in that PR:
      - Rename `results/vorschaubilder/` → `results/thumbnails/`? Existing HTML results
        link the old folder → needs a migration (or keep reading the old folder).
      - `profiles.json` is both the shipped example and the user's working file. Proposal:
        ship `profiles.example.json` (English, neutral examples; I5), gitignore
        `profiles.json` and create it from the example on first start without ever
        touching an existing file.
      - E3 stays relevant: translating the UI does not make users enter English motif
        names.
      - The legacy `franchise` field and the `--character` CLI option stay for
        compatibility.
      (done 2026-10-21: UI, HTML gallery, engine log/error messages and `--help`,
      profile validation messages, `.bat` messages and the `.gitattributes` comment are
      English. The crop label is "Full image"; old cache rows with "Gesamtbild" are
      shown as "Full image", so the cache stays valid. Decisions: new runs write
      thumbnails to `results/thumbnails/`, the old `vorschaubilder/` is left alone (E7);
      `profiles.example.json` is shipped, `profiles.json` is gitignored and created by
      the app on the first start without ever replacing an existing file (breaking for
      existing checkouts: back up `profiles.json` before pulling). The UI placeholders
      are English now, which nudges users towards English motif names (E3), but does
      not enforce it.)
- [ ] **I8 – No branch protection for `main`:** GitHub returns HTTP 403 "Upgrade to GitHub
      Pro or make this repository public to enable this feature" for the private repo, so
      `main` is protected only by the workflow rule (merge only on explicit user approval)
      and the deny rules in `.claude/settings.json`, which are not a security boundary.
      Options: GitHub Pro, making the repository public, or accepting the workflow rule.
      User decision → hold point.
- [ ] **I9 – CI action pins are updated by hand only:** `.github/workflows/tests.yml`
      pins `actions/checkout` and `actions/setup-python` to commit SHAs (with a version
      comment). That avoids moved tags, but security and runtime updates
      (e.g. a Node.js deprecation on the runners) only arrive when someone bumps
      the SHAs. Options: periodic manual bump, or Dependabot for `github-actions`.
      Dependabot opens its own PRs outside the one-PR-per-roadmap-item workflow, so
      this is a workflow decision → hold point.
- [ ] **I10 – Manual runs leave files in the user profile:** importing Ultralytics without
      `YOLO_CONFIG_DIR` writes `%APPDATA%\Ultralytics\settings.json` (seen in PR #8 when a
      development command imported it). The `.bat` files and the app set the variable, but
      the manual engine command in `README.md` and `CLAUDE.md` does not, and the same
      applies to `TORCH_HOME`, `HF_HOME` and `XDG_CACHE_HOME` (model downloads land in the
      user profile). This is a gap for a clean uninstall. Fix idea: the engine sets these
      variables to the project's `.cache/` when they are unset (`os.environ.setdefault`
      before importing torch, open_clip and ultralytics), or a documented PowerShell snippet.
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
- [ ] **I12 – Fresh installs can get untested major versions:** `requirements.txt` sets only
      minimum versions apart from torch/torchvision (user decision in PR #8), so a fresh
      install takes the newest release, e.g. Pillow 13.0.0 is on PyPI while the verified
      venv has 12.3.0 (PR #8 review). Upper bounds on the major version (`<13`) or a lock
      file would keep installs on tested versions; part of the pinned dependencies of P5.
- [ ] **I13 – Background runs die with the agent session:** a long engine run that an
      agent starts as a background command of Claude Code ends when that agent session
      ends; the first evaluation run of PR #11 stopped at 1,110 of 4,997 photos (stale
      `run-status.json` in phase "analyzing", the lock released by the OS). It completed
      when started detached through WMI (`Win32_Process.Create` with a `.cmd` file that
      sets the cache variables). Long smoke or evaluation runs in the PR workflow should be
      started detached (and the agent should wait for their end) — document it in the
      implementer brief or `CLAUDE.md`.

## Roadmap (priority)

Each unchecked item is implemented in its own pull request, strictly one after another
(see the PR workflow in `CLAUDE.md` and the `/roadmap` skill).

### P0 – Foundation and correctness
- [x] Git repository + private GitHub repo (I1)
- [x] (0) PR workflow (`/roadmap` skill, briefs, permission settings, PR template, labels)
      + English docs incl. `CLAUDE.md` update (I6)
- [x] (1) `pytest` scaffold + shared module `framescout_core.py` (slug, `EXT`, profile
      loading/validation) with tests, no model download (A3, A9, part of I2)
      (done 2026-10-21)
- [x] (2) CI: GitHub Action running `pytest` on a Windows runner without torch/model
      download (part of I2) (done 2026-10-21)
- [x] (3) English UI and outputs, neutral example profiles (I7, I5) (done 2026-10-21)
- [x] (4) QuickGELU fix + `ENGINE` bump, cache rebuilt once (E1) (done 2026-10-21)
- [x] (5) Data-loss fixes: unique reference names (A1), robust `read_profiles` + `.bak`
      (A2), E6 (done 2026-10-21)

### P1 – Performance
- [x] Batching across images, parallel decoding, `Image.draft` (E2) (done 2026-10-21)
- [x] Installer option for CUDA torch, YOLO on GPU (A7, I3, E14) (done 2026-10-21; one
      GPU smoke run so far, I11)

### P2 – Robust runs
- [x] Engine writes a status/lock file (PID, phase, progress); the app reconnects after a
      reload and prevents parallel starts (A4, A5) (done 2026-10-21)
- [x] Persist settings in `settings.json` (A8) (done 2026-10-21; A8 itself is partly open)

### P3 – Search quality
- [x] Average the prompt ensemble, normalize scores per profile (E4, E5) (done 2026-10-23;
      evaluation limits: E20)
- [x] Solve the German-language problem: English search terms only, said in the app and
      the README (E3) (done 2026-10-23; multilingual CLIP or an "English search term"
      field were not chosen, multilingual model: E21)

Stronger and multilingual models moved to P4b (user decision in PR #13: evaluate them
on the user's home PC first).

### P4 – UX
- [ ] Result gallery in the app, mark matches/copy them to a folder, "open folder",
      ZIP export with thumbnails
- [ ] Cleanup of cache/thumbnails/orphaned HTML files and reference files (E7, E11, A14);
      optional HEIC/RAW support

### P4b – Search models (evaluate at home first)
- [ ] Optional stronger models (ViT-B-16, ViT-L-14, SigLIP) with a CPU runtime note (E22;
      investigation, candidates and user decisions recorded there)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of the previous item (E21)

### P5 – Distribution
- [ ] Pinned dependencies (I12), portable Python variant, uninstall script
