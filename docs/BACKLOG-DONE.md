# FrameScout – Finished backlog items

Items of [BACKLOG.md](../BACKLOG.md) that are done, with their reports (what was decided,
measured and left open). Moved here unchanged when their pull request was merged. Open
follow-ups that a report names have their own IDs in `BACKLOG.md`. The roadmap lines of
finished work are in [ROADMAP.md](../ROADMAP.md) → "Done".

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
      and the photo is skipped; thumbnail names are unchanged. Rank gaps: fixed by E12.)
- [x] **E7 – No cleanup:** `thumbnails/`, `cache.sqlite3` (deleted files, old
      signatures) and HTML files of renamed/deleted profiles grow without bound. Since
      I7 the thumbnail folder of older versions, `vorschaubilder/`, is no longer written
      but stays in `results/` (galleries of profiles that were not regenerated still
      link it). A cleanup must never delete `results/marks.json` (the user's marks, A17)
      or `marks.json.lock`.
      (done 2026-10-25, user decisions at the PR #18 hold point: "Clean up storage" in the
      "Search & results" tab scans and lists per category count, size and a checkbox, and
      deletes the selected categories permanently (no Recycle Bin) after a confirmation,
      holding `results/run.lock` (refused while a search runs; no search starts during
      it); under the lock everything is checked again and only what the scan showed and
      still qualifies is deleted. Categories: temporary thumbnails (E13), orphaned
      galleries (`*.html` in `results/` with the `<title>FrameScout – ` marker, neither in
      `results.json` nor the gallery of a current profile), thumbnails neither
      `results.json` nor a kept gallery links (both thumbnail folders; an emptied
      `vorschaubilder/` goes too; thumbnails only orphaned galleries link go only together
      with them), cache rows of deleted photos inside the current photo folder (only if it
      exists), cache rows of older engine versions or unknown settings and of other
      settings of this version (E11, the latter unselected), compacting (`VACUUM`), and
      unreferenced reference images (A14, unselected). Galleries and thumbnails are not
      offered if `results.json` or `profiles.json` cannot be read. At the end of every
      finished search the engine removes temporary and unreferenced thumbnails itself
      (every HTML file counts as kept there). Never deleted: `marks.json(.lock)`,
      `run.lock`, `run-status.json`, `results.json`, the cache file, `settings.json`,
      `profiles.json(.bak)`. Cache rows of photos outside the current photo folder are
      never offered. Other temporary files: E26; other tabs during a cleanup: A23.)
- [x] **E8 – Cache key = absolute path:** moving the photo folder forces a complete
      recomputation.
      (closed 2026-10-28 as won't do – renamed/moved photos count as new; superseded by
      the unbound-entries cleanup. User decision: "Wenn sich an Dateien/Ordnern etwas
      ändert (umbenennen, verschieben), dann ist es weg. Dann kann das im Cache enthalten
      bleiben, falls die Dateien doch wiederhergestellt werden. Die Funktion zum Aufräumen
      zeigt dann 'ungebundene' Fotos an und man kann die bereinigen." (If files or folders
      change (rename, move), the entries are gone for the search; they may stay in the
      cache in case the files come back; the cleanup shows "unbound" photos and the user
      can clean them up.) No migration, no cache key or `marks.json` change. PR #40
      (`b238c24`, `2052e39`): "Clean up storage" offers "Cache entries of unbound photos"
      (every cache row whose photo no longer exists, in any folder; off by default since the review, user decision)
      and "Marks of unbound photos" (new `framescout_core.remove_marks`; one category
      checkbox, off by default); photos on an unreachable drive or share are not checked
      (root probe, 5 s timeout), see `docs/ARCHITECTURE.md` → "Storage cleanup". Tests:
      811 passed, 1 skipped; `AppTest` smoke run, not a real browser or disconnected
      drive. Remaining: E37, A35.)
- [x] **E10 – Duplicate check before `strip()`:** "Joker" and " Joker" are not recognized as
      equal. (done 2026-10-21 in `framescout_core.load_profiles`; such a hand-edited
      `profiles.json` is now rejected instead of merging both profiles into one gallery.)
- [x] **E11 – Dead cache rows after an `ENGINE` bump:** after E1 (v4 → v5) every v4 row
      (GELU embeddings) stays in `results/cache.sqlite3` and can never be reused, so the
      file roughly doubles on the first run after the update and never shrinks. The
      `signature` column is a hash, so rows of old engine versions can only be found for
      setting combinations that are known in advance (e.g. the v1.1 defaults). Fix idea:
      store `ENGINE` in its own column, then delete rows of other engine versions and
      `VACUUM` – only with the user's consent (the cache is user data). Part of the
      cleanup in E7.
      (done 2026-10-25: a side table `signatures(signature PK, engine, settings)` that the
      engine fills on every run (`framescout_core.prepare_cache`); the features table is
      unchanged and `ENGINE` was not bumped, so older versions keep reading the cache.
      Rows written before are classified by `known_signatures` (the current signatures for
      every value of the app's widgets with the default YOLO model); a row matching none
      is offered as "older version or unknown settings (e.g. CLI)". Deleting needs the
      user's selection and confirmation in "Clean up storage" (E7), `VACUUM` is optional.
      Other models of E22: see there.)
- [x] **E13 – Interrupted thumbnail writes leave temporary files:** since PR #6 a
      thumbnail is written as `thumbnails/<hash>.jpg.<random>.jpg` and renamed when
      complete. The app's Stop button ends the engine with `terminate()`/`kill()`, which
      on Windows skips the `finally` that removes the temporary file, so each stop
      during the export can leave one such file; it is never reused (no broken
      thumbnail), only clutter. Fix idea: a recognizable `.tmp` name that the next run
      (or the cleanup of E7) removes. Since A4 only one engine at a time uses an output
      folder (`run.lock`), so a run holding the lock can remove such files safely.
      (done 2026-10-25: the existing temporary name `<hash>.jpg.<random>.jpg` is
      recognizable, so the name is unchanged; the engine removes such files at the end of
      every finished search, and "Clean up storage" (E7) offers them too.)
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
- [x] **E22 – Only one CLIP model, no stronger option:** FrameScout always used OpenAI
      CLIP ViT-B/32. **Done (PR #31, 2026-10-26): the plumbing and three optional
      candidates;** which of them stay is E32. Delivered as planned below, with these user
      decisions: the registry offers the default plus `vit-b-16-datacomp`,
      `vit-l-14-datacomp` and `vit-b-16-siglip` (SigLIP 2 and the others of the table were
      not offered); `transformers>=5.21.0` is in `requirements.txt`; downloads were
      approved for these three only; evaluation is done by the user later on this PC with
      new labels, as a follow-up PR (E32), so the candidates are marked "not evaluated".
      New: `framescout_core/models.py` (`MODELS`, `model_problem`), `ENGINE_TEMPLATE` and
      `engine_id(model)` (the default's `ENGINE` is unchanged: no re-analysis), the cleanup
      category "Cache entries of other search models" (default off), the settings key
      `model`, the engine option `--model`, the "Search model" selectbox, the model in log,
      gallery note and `results.json`. Verified: CPU smoke runs of all four models with 3
      synthetic images; **not verified:** search quality, CUDA, person detection with the
      new models, a run without `transformers`, `Install-FrameScout.bat` with the new
      requirement. **Review of PR #31 (addressed):** the app starts the engine with
      `PYTHONIOENCODING=utf-8` and the engine escapes characters its output cannot encode
      (the "·" of a model label crashed a search on a cp932 code page and showed as "�" in
      `run.log` on cp1252; non-ASCII profile names and paths were garbled there before);
      Start is disabled while the chosen model lacks its package; a cleanup scan is dropped
      when the AI settings or folders change; results of another model than the chosen one
      get a note; `scan_cleanup`/`clean_up` require `current_model`; `embedding_size` and
      the aliases `CLIP_MODEL`/`CLIP_PRETRAINED` were removed. Not fixable here, documented
      in the README: a cleanup in a FrameScout version before E22 counts the rows of the
      optional models as "older versions" (selected). Investigated in PR #13 (no weights
      downloaded).
      **User decisions (PR #13):** the default stays `ViT-B-32-quickgelu`/`openai`; if a
      SigLIP model is chosen, `transformers` goes into `requirements.txt`; the
      evaluation runs on the user's home PC, so the roadmap item moved behind P4; the
      list of offered models is still open.
      **Candidates** (open_clip 3.3.0 names). CPU time: `encode_image`, batch 8, random
      weights (weights do not change the speed), Core Ultra 9 285K with 12 torch
      threads; every row measured, repeated runs differ by up to ~5 %; a typical laptop
      CPU is probably 3–5× slower, the factor is the portable part. RAM: fp32
      parameters. ImageNet: zero-shot top-1 from open_clip's
      `docs/openclip_results.csv`. Flickr: Flickr30k image retrieval R@1 (a text finds
      its image, FrameScout's task) from `docs/openclip_retrieval_results.csv`.

  | Model / weights | Download | RAM | CPU ms/crop | Factor | ImageNet | Flickr | Extra dependency | License |
  |---|---|---|---|---|---|---|---|---|
  | `ViT-B-32-quickgelu` / `openai` (default) | 605 MB | 0.6 GB | 10.7 | 1× | 63.3 % | 0.59 | – | MIT |
  | `ViT-B-16` / `datacomp_xl_s13b_b90k` | 599 MB | 0.6 GB | 41.4 | ~4× | 73.5 % | 0.68 | – | MIT |
  | `ViT-B-16-SigLIP` / `webli` | 813 MB | 0.8 GB | 42.6 | ~4× | 76.0 % | 0.75 | `transformers` | Apache-2.0 |
  | `ViT-B-16-SigLIP2` / `webli` (224 px; `-256`: 54.8 ms) | 1.50 GB + 34 MB tokenizer | 1.5 GB | 42.2 | ~4× | ~78 % (paper, unverified) | – | `transformers` | Apache-2.0, multilingual |
  | `ViT-B-32-SigLIP2-256` / `webli` | 1.51 GB | 1.5 GB | 14.1 | ~1.3× | ~74 % (paper, unverified) | – | `transformers` | Apache-2.0, multilingual |
  | `ViT-L-14` / `datacomp_xl_s13b_b90k` | 1.71 GB | 1.7 GB | 190.4 | ~18× | 79.2 % | 0.73 | – | MIT |
  | `ViT-L-14-quickgelu` / `openai` | 1.71 GB | 1.7 GB | 200.9–204.9 | ~19× | 75.5 % | 0.65 | – | MIT |

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
      model side by side (~10–15 MB per model for 5,000 photos, depending on the
      embedding size, 512 or 768; since PR #18 the cleanup's `classify_signatures` counts
      every engine other than `ENGINE` as "older version", default selected, so rows of
      the other registered models need a category of their own there, unselected); the
      model name in the log line and the gallery note; the QuickGELU config check of
      `test_signature.py` for every registry entry. Input size: the engine passes
      `getattr(model.visual, 'image_size', 224)` to `draft_size` and silently falls back
      to 224 (448 px drafting); open_clip's timm towers (SigLIP) set `image_size` from
      their config, but record each model's input size in the registry and test it
      against the open_clip config (no weights needed), so a 256/384 px model is never
      drafted too small. The z-scores (E5) absorb the score scales; only the raw-score
      fallback shows other numbers (SigLIP cosines are lower).
      **Evaluation plan** (search-quality hold point; E20): implement the plumbing
      first, then run each candidate with `--model` into `.tmp/`. The existing labels
      (`.tmp/eval-labels/` in the original checkout, not in the repository: five usable
      profiles on the ~5,000 cosplay photos) judge only the top 40 of ViT-B/32 variants,
      so each model needs a new labelling pool (about 100–250 judgments per model), then
      AP@40 per profile and a re-check of the reference weight (0.3, E5) per model. Add a
      second, non-cosplay collection (E20). On another PC, the labels, the photos and
      the tooling have to be brought along or made anew.
- [x] **E23 – Cleanup must keep what `results.json` references:** since P4 (A) the app
      shows the last search from `results/results.json`, whose cards name thumbnails in
      `results/thumbnails/` and the galleries' HTML files. The cleanup of E7 must not
      delete thumbnails or galleries still listed there (nor those linked by HTML
      galleries that are kept), or the app shows "No thumbnail".
      (done 2026-10-25 with E7: galleries and thumbnails listed in `results.json` or
      linked by a kept HTML file are never deleted, and neither category is offered if
      `results.json` cannot be read.)
- [x] **E25 – No HEIC/HEIF or camera RAW photos:** the engine reads only `EXT` (JPG, PNG,
      WebP, BMP, TIFF), so photos from many phones (HEIC) and cameras (CR2/CR3, NEF, ARW,
      DNG, …) are skipped without a note. Supporting them needs new dependencies (e.g.
      `pillow-heif`; `rawpy` for RAW, which decodes slowly and may need the embedded
      preview instead), and so is a hold point; the cache, thumbnails and "Open" (an
      `EXT` check) would follow the new extensions. Split out of the cleanup roadmap item
      (user decision at the PR #18 hold point).
      Investigation (2026-10-26, open decisions at the hold point of the E25 PR):
      - Candidates, all with `cp314-win_amd64` wheels on PyPI: `pi-heif` 1.4.0 (BSD-3,
        about 2.4 MB, decode-only build of `pillow-heif`, the package Ultralytics uses),
        `pillow-heif` 1.8.1 (BSD-3, about 6.6 MB, also encodes; its wheels bundle the
        GPL x265 encoder, a concern for a redistributed portable build in P5), `rawpy`
        0.27.1 (MIT, about 0.9 MB, bundles LibRaw under LGPL-2.1/CDDL-1.0; needs numpy).
      - RAW decoding: `rawpy` can return the camera's embedded JPEG preview
        (`extract_thumb`, fast, often full size, decodable at reduced scale like any
        JPEG) or decode the sensor data (`postprocess`, about 1–3 s per photo on a CPU,
        colors of LibRaw's defaults rather than the camera's).
      - AVIF needs no new package: the venv's Pillow 12.3 reads it
        (`PIL.features.check('avif')`).
      - Cache: new extensions only add rows, the signature and `ENGINE` stay; a later
        change of the RAW decoding would change their embeddings and so need an `ENGINE`
        bump. Cameras often write RAW+JPEG pairs of the same shot, which would then
        appear twice in the results. Browsers cannot show HEIC/RAW files, so the HTML
        gallery link of such a photo downloads it or hands it to the OS instead of
        showing it (the thumbnails are JPEG and work).
      User decisions (PR #26 hold point): `pillow-heif`; `rawpy` with the embedded JPEG
      preview and a half-size decode as fallback; extensions `.dng .cr2 .cr3 .nef .arw
      .orf .rw2 .raf .pef .srw`; both packages required in `requirements.txt` (optional
      extras later: E29); a RAW file with a JPEG/HEIC of the same name in its folder is
      skipped; `.avif` added; the log names the skipped files. Ultralytics' analytics and
      auto-install (E27, E28) get their own PR after this one.
      (Done 2026-10-26 in PR #26: `framescout_core.scan_photos`, `open_raw` in the
      engine, the app's photo count. Also uses the preview only if its longer edge has at
      least 1024 pixels, else the half-size decode. An installation without the packages
      skips those formats with a note. Checked in CPU smoke runs with and without person
      detection on CC0 RAW samples (CR2, CR3, NEF, ARW, DNG), HEIC files made with
      pillow-heif and AVIF; not checked: a RAW file stored rotated or without a usable
      preview, HEIC from a real phone – see `docs/ARCHITECTURE.md` → "Photo formats".)
- [x] **E27 – Ultralytics sends usage analytics:** with person detection the engine runs
      `YOLO.predict`, and Ultralytics registers its analytics callbacks on every
      predictor (`ultralytics/utils/callbacks/base.py`, `add_integration_callbacks`):
      at the end of a prediction it posts an anonymous event (CPU, device, versions,
      model name, image count, speeds; no images or paths) to Google Analytics, at most
      every 30 s, while its setting `sync` is `true` (the default; it is `true` in the
      project's `.cache/ultralytics/Ultralytics/settings.json`). This breaks engineering
      principle 2 (no tracking without consent). Fix idea: turn `sync` off before the
      first prediction (e.g. `ultralytics.settings.update({'sync': False})` in the
      engine, or in the `.bat` files and the app's engine environment), with a test
      that does not need ultralytics. Found in the E25 PR.
      (Done 2026-10-26: the engine imports Ultralytics only through
      `framescout_core.import_detector_class`, which sets `YOLO_OFFLINE=true` first; that
      turns off the analytics, Sentry and update checks without writing Ultralytics'
      settings file, and model downloads still work – see `docs/ARCHITECTURE.md` →
      "Environment variables and caches".)
- [x] **E28 – Ultralytics installs packages at run time:** importing `ultralytics`
      replaces `PIL.Image.open` for the whole engine process (`ultralytics/utils/patches.py`);
      the first file Pillow cannot identify (e.g. a broken `.jpg`) makes it run
      `check_requirements("pi-heif")`, which pip-installs `pi-heif` into the venv
      (`YOLO_AUTOINSTALL` is `true` by default). That is how `pi_heif` 1.4.0 got into the
      project venv (`pip show` lists no package requiring it). Other code paths of
      Ultralytics may auto-install more packages the same way. This is a download and a
      venv change without consent (engineering principle 2 and the hold points). Fix
      idea: set `YOLO_AUTOINSTALL=false` in the `.bat` files and the app's engine
      environment (and say in the README how to set it for manual runs, like I10).
      Found in the E25 PR.
      (Done 2026-10-26: `import_detector_class` also sets `YOLO_AUTOINSTALL=false`, in the
      engine itself, so manual runs need no setting, and puts the original
      `PIL.Image.open` back after the import, so an unreadable file no longer triggers the
      `pi-heif` install. An already installed `pi_heif` stays in an existing venv; it is
      unused and goes with the venv.)
- [x] **E16 – Every engine start contacts the Hugging Face Hub:** the log shows
      "You are sending unauthenticated requests to the HF Hub" on each run although the
      CLIP weights are in `.cache/huggingface`: OpenCLIP checks the hub for a newer file.
      No image data is sent, but the run needs (or waits for) the network, which is
      surprising for a local tool. Fix idea: set `HF_HUB_OFFLINE=1` once the weights are
      cached (or try offline first and fall back to a download), in the engine or the
      `.bat` files; check the behavior without internet access.
      (Done 2026-10-28, PR #41, roadmap P7 (A): the engine imports open_clip only through
      `framescout_core.import_open_clip`, which sets `HF_HUB_OFFLINE=1` before the import
      when `model_cached` finds every Hub file of the model in the cache (the weights and,
      for SigLIP, the tokenizer files in the snapshot of `refs/main`) and the user set
      neither `HF_HUB_OFFLINE` nor `TRANSFORMERS_OFFLINE` (also on the constants of an
      already imported huggingface_hub). If loading fails offline because a cache file is
      missing (`hub_file_error`; other errors are raised as they are),
      `load_with_hub_fallback` prints a note, goes online and loads again; an uncached model
      loads online as before. The variables are set in the engine process, so the `.bat`
      files and `app.py` are unchanged. Checked with the default model, CPU, network blocked
      by a dead proxy: no Hub lines; SigLIP loaded offline from the cache in a Python check.
      Not run: the first download and the fallback with real files (E38). See `docs/ARCHITECTURE.md` → "Environment variables
      and caches".)
- [x] **E31 – Every search contacts the Hugging Face Hub:** loading the CLIP weights with
      open_clip goes through `huggingface_hub`, which asks the Hub for the model files on
      every run even when they are in `.cache/huggingface` (the log shows "You are sending
      unauthenticated requests to the HF Hub"). No images or paths are sent, but it is a
      network request per search (with a user agent naming library versions) and makes
      the search fail or wait without a network. Fix idea: once the weights are cached,
      set `HF_HUB_OFFLINE=1` (and `HF_HUB_DISABLE_TELEMETRY=1`) for the engine, keeping the
      first-run download; check how open_clip behaves offline. Found in the E27/E28 PR.
      Since E22 (PR #31) this applies to every search model, including the SigLIP
      tokenizer.
      (Closed 2026-10-28 as a duplicate of E16, fixed together with it in PR #41;
      `HF_HUB_DISABLE_TELEMETRY=1` is set as well.)
- [x] **E33 – Hugging Face warning about symlinks in `run.log` on Windows:** without
      Windows Developer Mode, `huggingface_hub` prints a long "cache-system uses symlinks"
      `UserWarning` into `run.log` at the first download of each model and stores the files
      without symlinks (more disk space). Fix idea: set `HF_HUB_DISABLE_SYMLINKS_WARNING=1`
      in the `.bat` files and the engine's environment and mention it in the README. Found
      in the E22 smoke runs.
      (Done 2026-10-28, PR #41: `import_open_clip` sets `HF_HUB_DISABLE_SYMLINKS_WARNING=1`
      with `setdefault` in the engine process, so manual runs need no setting and the
      `.bat` files are unchanged; the files are still stored as copies without Developer
      Mode. Mentioned in the README.)
- [x] **E9 – `yolo11n.pt` ends up in the project root** instead of `.cache/`; not documented.
      (Done 2026-10-29, PR #42, roadmap P7 (B): the detector is created with
      `YOLO(framescout_core.yolo_weights(name, <engine folder>, cwd, os.environ, log))`: a
      path or URL as given; a bare name from the `YOLO_CONFIG_DIR` folder (default
      `.cache/ultralytics/`) if present; an old `yolo11n.pt` (default name only) in the
      project folder is moved there once unless a copy is there already, used in place with a
      log line if the move fails; a file of that name in the working folder is used as before; otherwise the cache
      path, where Ultralytics downloads it. The cache signature still gets `--yolo-model`
      unchanged, so nothing is invalidated. Unit-tested; no run with real models.)
- [x] **E12 – Skipped photos leave gaps in the gallery:** a photo whose thumbnail fails
      (deleted since scoring, unreadable) is skipped after the top-N cut, so the gallery
      shows e.g. #2, #3, #4 and fewer than `--top` cards although lower-ranked photos
      exist. Fix idea: rank only the photos that got a card and fill up to `--top`.
      Also: `ensure_thumbnail` repeats the `stat()` done during scoring; the mtime could
      be kept with the score (PR #6 review). Since P4 (A) the app's result gallery shows
      the same gaps: `results.json` keeps the ranks of the HTML gallery.
      (Done 2026-10-30, PR #44, roadmap P8 (A): `framescout_core.gallery_cards(ranked, top,
      thumbnail)` yields `(rank, item, thumbnail name)` for the first `top` photos that get
      a thumbnail; ranks count only shown photos, lower-ranked photos fill up, and it stops
      trying once the gallery is full. The engine export passes the full sorted ranking
      (no `[:args.top]` cut) through it, so HTML galleries and `results.json` have
      contiguous ranks and still show `--top` cards if enough photos exist. Export progress
      keeps the total `sum(min(--top, photos))`; every photo tried counts, also a skipped
      one, capped at the profile's share, so the total is reached without a jump and the
      status stays fresh during a run of skipped photos (review). `SkippedPhotos` tries and
      logs each skipped photo once per export and logs only the first 50 one by one, then
      a count, so a vanished photo folder cannot flood the log (review). Not done: the
      "Also" part (reuse the scoring mtime instead of the `stat()` in `ensure_thumbnail`):
      that `stat()` is what detects a photo deleted since scoring; without it an existing
      or legacy thumbnail would still produce a card for a deleted photo. No CLI,
      `profiles.json`, cache signature or `results.json` format change. Unit-tested; engine
      smoke run with a simulated thumbnail failure of the best photo gave cards #1–#5 for
      `--top 5`; after the review a second smoke run with five failing photos, two profiles
      and a log limit of 1 gave two full `Top 5` galleries with ranks 1–5, one logged
      photo plus the count line, and export progress 1–10 of 10.)
- [x] **E24 – An interrupted export leaves galleries newer than `results.json`:** the
      engine writes `results.json` only after all galleries, so a search stopped while it
      writes the galleries has already replaced some HTML files, while the app still shows
      the previous complete search (its date is shown, and the status says that the last
      run did not finish). Opening such a gallery from the app shows the newer, partial
      result. Fix idea: write the galleries under temporary names and publish them
      together with `results.json` at the end. Found in PR #14.
      (Done 2026-10-30, PR #45, roadmap P8 (B): the engine keeps each gallery's HTML in
      memory and calls `framescout_core.publish_export(output, pages, document)` at the
      end. It writes all galleries and `results.json` in full to `<name>.<random>.tmp`
      (fsync), then renames them in profile order, `results.json` last
      (`_common._publish_together`, each rename retried 40 x 50 ms). A stop or failure while
      writing leaves the previous galleries and `results.json`; a rename that fails every
      retry gives the files renamed before it their previous content back (review of PR #45).
      `write_results` was removed: `publish_export` is the only writer of `results.json`.
      The gallery path lines in
      the log now come after the export. Galleries are written as bytes: `\n` line ends on
      Windows too. Residual window of the renames: E45. No CLI, `profiles.json`, cache or
      `results.json` format change. Unit-tested; CPU engine smoke run with 4 synthetic
      photos and 2 profiles; a real stop during the export was not reproduced.)
- [x] **E26 – Other temporary files of a stopped run stay in `results/`:** the atomic
      writes of `run-status.json` and `results.json` (and of `marks.json` by the app) go
      through `<name>.<random>.tmp`; `terminate()`/`kill()` during such a write leaves that
      file behind, like the thumbnails of E13. They are small and rare, and the cleanup
      of E7 does not remove them (an app session may be writing `marks.json` at that
      moment). Fix idea: remove `run-status.json.*.tmp` and `results.json.*.tmp` older than
      a minute in `auto_cleanup`. Found in PR #18.
      (Done 2026-10-30, PR #45, roadmap P8 (B): `auto_cleanup(results, now=None)` also
      removes `run-status.json.*.tmp`, `results.json.*.tmp`, `marks.json.*.tmp` and
      `<slug>.html.*.tmp` (profile slugs `[a-z0-9-]+` only; random part exactly 8 chars of
      `[a-z0-9_]`) that are at least `STALE_TEMP_AGE` = 60 s old, even if `results.json`
      cannot be read; the age limit protects a write an app session is doing right now and
      is measured against the results folder's file system clock (the mtime of a probe
      file), so a network share whose clock runs behind does not break it (review of PR
      #45). Every cleanup summary gets `temporary`; the
      engine log line reads "Removed N unused thumbnails or temporary files (size)". The
      app's "Clean up storage" is unchanged. Temporary files of the app's writes in the
      project folder: E44. Unit-tested; the same smoke run removed two stale temporary
      files and kept a fresh one.)
- [x] **E30 – A RAW file is lost when its JPEG partner is broken:** E25 skips a RAW file
      when a JPEG/HEIC of the same name is in the same folder, by names only. If that
      JPEG cannot be decoded (e.g. a corrupt file; a merely truncated one usually still
      decodes, see E46), the engine logs it as an
      `ERROR` and the shot is missing from the search, although its RAW file is fine
      (documented in the README). Fix idea: when a partner fails to decode, analyze its
      skipped RAW file instead (the scan already lists them in `PhotoScan.raw_pairs`); the
      cache and the gallery would then show the RAW path for that shot. Found in the PR #26
      review.
      (Done 2026-10-30, PR #46, roadmap P8 (C): `raw_fallbacks(scan)` and `RawFallback`
      in `framescout_core/photos.py` map a partner to its skipped RAW file (first in
      sorted order if several). A partner that fails in the cache scan, in decoding or in
      storing is logged as `ERROR` and deferred; after all photos the engine analyzes its
      RAW file instead, unless another photo of the shot was analyzed (review), once per
      shot, through the cache check and the decoding threads like any photo, and counts
      the shot once. Cache row, gallery card, thumbnail, link and `--scores-file` use the
      RAW path; a repaired JPEG wins again on the next run. Truncated JPEGs: E46. No
      cache, CLI or profiles change. Unit-tested (9 tests in `test_photos.py`); the engine
      side is **not runtime-tested** (no RAW sample locally).)

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
- [x] **A7 – CUDA never available:** pip installs torch `+cpu`; "cuda" can still be selected.
      (done 2026-10-21: `Install-FrameScout.bat` offers the CUDA build of PyTorch (I3); the
      app offers "cuda" only if `torch.cuda.is_available()`, falls back to "auto" for a
      stale setting and tells a CPU build of PyTorch from a CUDA build that finds no usable
      GPU (no GPU, or a driver too old for the build); the hint (`cuda_hint`, also in the
      engine's error for `--device cuda`) says to close FrameScout, run
      `Install-FrameScout.bat cuda` (or update the driver) and start FrameScout again. On a
      GPU: one engine smoke run; the app's device choice there is untested, I11.)
- [x] **A9 – Minor issues:** duplicate `import os`; `EXT` duplicated in app and engine;
      `use_container_width` possibly deprecated (Streamlit 1.66).
      (done 2026-10-21: duplicate import removed, `EXT` lives in `framescout_core`;
      `use_container_width` moved to A10.)
- [x] **A11 – Progress bar parses German log text:** the app reads progress from `run.log`
      with a regex on `Neu:`/`Cache:`/`Fehler:`. Translating the engine log (I7) breaks
      the progress bar unless both change together; a machine-readable progress line or
      status file (see P2) plus a test for the progress interpretation would decouple it.
      (partly done 2026-10-21: the line format lives in `framescout_core.progress_line`,
      the app parses it with `parse_progress`, both tested; the line is English now.
      Still open: a machine-readable status file (P2).)
      (done 2026-10-21 with A4/A5: the app reads the progress from `run-status.json`;
      `parse_progress` is removed, the progress line stays in the log for people.)
- [x] **A12 – Gallery downloads are re-derived from the current profile list:** the app
      maps profiles to `<slug>.html` with `profile_slugs` on the *current*
      `profiles.json`. After deleting, renaming or reordering profiles with colliding
      slugs, a button can serve another (deleted) profile's stale gallery, e.g. delete
      "Rotes Auto" → "rotes auto!" now maps to the old `rotes-auto.html`. Fix: the engine
      writes a manifest (profile name → file, run timestamp) that the app reads – a new
      output format, so a design decision; fits the status file of P2 and A8 ("results
      without reference to the profile state"). Since A4 the engine writes
      `results/run-status.json`; the manifest could become part of it.
      (done 2026-10-23 in P4 (A), user decision in PR #14: the engine writes
      `results/results.json` after the galleries – run start and end, photo folder,
      settings and per profile its name, a fingerprint of its search texts and reference
      image paths (`framescout_core.search_fingerprint`; relative to the project folder, so moving it changes nothing), the gallery file and every card;
      a separate file, not part of the status file. The app shows the galleries of that
      search under the names they were made for and marks a profile changed, renamed or
      deleted since. Results folders without the file list their HTML files by name.
      Partial exports: E24.)
- [x] **A14 – Unreferenced reference files accumulate:** removing reference images from a
      profile, deleting a profile or a failed save of `profiles.json` after the upload
      leaves the files in `references/` (deliberately – nothing is deleted silently).
      Fix idea: list files no profile references and offer to delete them, with the
      user's consent; part of the cleanup in P4.
      (done 2026-10-25 with E7: "Clean up storage" lists the image files in `references/`
      that neither `profiles.json` nor `profiles.json.bak` names, by name and unselected;
      `profiles.json` is read again just before deleting, emptied folders are removed, and
      the category is not offered if either file cannot be read.)
- [x] **A16 – An empty photo folder searches the app's working directory:** `Path('')`
      is `.`, so with the folder field emptied, "Start search" is enabled and the engine
      gets the folder the app was started in – with `Start-FrameScout.bat` the project
      folder, including `.venv/` (whose packages ship PNG files) and `references/`.
      Older than A8, but since A8 an empty field is also saved in `settings.json` and comes
      back after a restart. Fix: treat an empty or whitespace-only folder as missing in the
      app (and possibly reject it in the engine). Found in PR #10.
      (done 2026-10-26 in PR #28 (A25) for the app: empty or blank lines of the folder
      field are no folders, an empty list shows "Enter a photo folder" and disables Start.
      The engine still takes an empty argument typed on the command line as `.`.)
- [x] **A17 – Marks and copying (roadmap P4 (B)): decided.** Asked in PR #14, deferred to
      P4 (B) and answered by the user on 2026-10-25 (user decision). FrameScout ranks
      candidates, not certain hits; a mark records what the user checked.
      - Q4 – meaning: per profile, keyed by profile name + photo path, kept across later
        searches; a renamed profile keeps its marks. States: **three** (match / no match /
        open), with an option to hide photos marked as no match (not the recommended two
        states); using rejects as feedback for the search: A20. Storage:
        **`results/marks.json`** (not the recommended project-folder file), written
        atomically under a lock (`marks.json.lock`) and treated as user data: the engine
        never writes it, and the cleanup of E7 must never delete it.
      - Q5 – copying: copy only (`shutil.copy2`, keeps the date), never move or delete
        originals, never overwrite in the target; the same name and content is skipped as
        "already there", the same name with other content becomes `name (2).jpg`. Target
        folder: an editable field, prefilled with `<Pictures>\FrameScout\<profile slug>`
        (the gallery's slug; the Pictures folder from Windows, also when it was moved)
        and saved per profile in `settings.json` (`copy_folders`). Layout: flat. A
        target inside the photo folder (of the shown search or the current setting) is
        refused with an explanation.
      - UI: below each gallery card a three-state control (Undecided / Match / No match;
        "Undecided" is the open state, so it does not read like the "Open" button, review);
        below the gallery "Marked: N photos of "<profile>"", "Copy to folder", "Copy N
        marked photos", "Open target folder" and the summary "20 copied · 2 already there
        · 1 renamed · 0 failed".
      (done 2026-10-25: `framescout_core.read_marks`/`save_marks`/`rename_marks`,
      `copy_target`/`copy_photos`/`copy_summary_text`/`default_copy_folder` and
      `read_copy_folders`/`save_copy_folder`/`rename_copy_folder`, used by `app.py`.
      Galleries of profiles that are no longer search profiles (renamed or deleted) cannot
      be marked, so no marks are left under an old name; their existing marks can still
      be copied. Checked with Streamlit's `AppTest`, not yet in a browser. Marks follow
      the absolute photo path: A21.)
- [x] **A23 – Other tabs show a cleanup as a running search:** "Clean up storage" (E7)
      holds `results/run.lock` while it deletes, and the app derives "a search is running"
      from that lock, so another open tab shows "Search running" and disables its controls
      for that moment (a Start there is refused with "A search is already running, or the
      storage is being cleaned up."). Harmless and short, except for a `VACUUM` of a large
      cache. Fix idea: a cleanup status the app can tell apart, e.g. a phase "cleaning" in
      a separate status file. Found in PR #18.
      (done 2026-10-25 in the review of PR #18: `clean_up` registers its results folder in
      the process (`framescout_core.cleanup_running`; app sessions are threads of one
      process), so another tab shows "The storage is being cleaned up" instead of a running
      search and disables "Stop search"; Start stays disabled until the lock is free. A
      cleanup in another process, e.g. a second app instance, still looks like a search.)
- [x] **A25 – Only one photo folder per search:** user question on 2026-10-25. The app and
      the engine take a single folder (`settings.json` key `photo_folder`, one positional
      engine argument, `root.rglob('*')`); photos on several drives or in several event
      folders need one parent folder or shortcuts/junctions inside the folder (not
      checked whether `rglob` follows them). Changing the folder works: the next search
      scans only the new folder and analyzes its photos from scratch; the old folder's
      rows stay in `cache.sqlite3` and are reused when it is chosen again (E8); the last
      results stay shown until the next search replaces `results.json`; marks stay in
      `marks.json` but are not shown for other photos (A21); the cleanup never offers
      cache rows of photos outside the current folder (E7), so they only grow. Idea: a
      list of folders. The cache and marks are keyed by absolute path and the engine
      already works on a list of paths, so neither needs a format change. Work needed:
      `photo_folders` in `settings.json` (the old `photo_folder` is read as a list of one;
      validated like the other settings); several folders as engine arguments; a list
      editor in the app with the per-folder photo count (A6: counting on every rerun is
      already slow); `results.json` records the folders (today `photo_folder`; the app
      must still read format 1); the copy-target check and the cleanup of cache rows
      treat every listed folder as a source. Questions for the user (hold point, new
      `results.json` and CLI format): whether to keep `photo_folder` in the CLI/JSON
      for compatibility; what the gallery shows to tell sources apart (relative path
      today). Risks: a disconnected drive must not count as deleted photos (the cleanup
      already refuses a missing folder, but only for one); overlapping or nested folders
      must be deduplicated by resolved path; the same file reachable by two paths would
      be analyzed twice.
      (done 2026-10-26 in PR #28, user decisions at its hold point: the engine takes
      `folder` with `nargs='+'`, drops folders listed twice or nested in another listed
      folder, leaves out missing folders with a note (an error only if none exists) and
      refuses an output folder equal to a listed one; `results.json` format 2 with
      `photo_folders` (format 1 still read, older apps reject format 2: a breaking change);
      `settings.json` key `photo_folders`, the old `photo_folder` read as a list of one and
      replaced on the next save; the app's text area has one folder per line with the
      photo count per folder; gallery names get the folder name as prefix with several
      folders; copy target check and cleanup use every listed folder, missing folders are
      skipped with a note. No cache signature, `ENGINE` or marks change. Same folder by
      another path: A28; junctions: A29.)

- [x] **A13 – Concurrent profile edits are lost** (the concurrent-edit part; more than
      one backup generation is A30): the app read `profiles.json` on every rerun and saved
      its whole list, so an edit made in another tab/session (or by hand) between that
      read and a save was overwritten.
      (done 2026-10-27: `read_profiles_versioned` returns the profiles and a version (the
      SHA-256 of the file's bytes; `None` for a missing file); `save_profiles(...,
      expected=version)` compares it under a `RunLock` on `profiles.json.lock` (waits up
      to `PROFILES_LOCK_TIMEOUT` = 5 s, then `OSError`) and raises `ProfilesChangedError`
      without writing anything if the file changed, was created or was deleted since.
      The app keeps the version its profile forms showed in `st.session_state.profiles_shown`
      (updated after the forms are drawn, so an interrupted run refuses a save instead of
      losing one, and by the session's own save to the version `save_profiles` returns);
      a refused save resets the edit forms (new widget keys) and shows "Your changes were
      not saved … make your changes again" at the top of the profile tab, and the page
      then shows the current profiles. Reading and saving `profiles.json` retry a
      transient Windows `OSError` like the settings file. Without `expected` a save is
      unchecked, as before. No format change: `profiles.json` is unchanged, the new empty
      `profiles.json.lock` is gitignored and in `NEVER_DELETED`. The user kept the single
      `profiles.json.bak` (hold point), so the generations go to A30; found on the way:
      A31, A32. Tests: 786 passed, 1 skipped (`tests/test_profile_file.py`); the refused
      save in the app was checked once with Streamlit's `AppTest`, not in two real
      browser tabs.)

- [x] **A8 – UX gaps:** deleting a profile without confirmation; settings only per
      session; results without timestamp/reference to the profile state.
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
      at the same moment keep both changes (second review). Invalid values fall back to
      their defaults with a warning and are removed with the next save, an unreadable file
      is never replaced (the page keeps the settings it shows), and a saved device PyTorch
      cannot use is used as "auto" but stays saved until another device or "Use auto from
      now on" is chosen.
      2026-10-23, P4 (A): the app shows the date of the search whose results it shows and
      marks a profile changed, renamed or deleted since, from `results.json` (A12).
      done 2026-10-27, P6 (B): the last open part, deleting a profile without
      confirmation, see A22. Nothing of A8 remains open; what a running search was
      started with is not recorded in the status file (not pursued).)

- [x] **A22 – Marks of a deleted profile pass to a new profile of the same name:** marks
      (A17) and the saved copy folder are keyed by the profile name only; deleting a
      profile kept them, so a profile created later under the same name showed the old
      marks and copied them, and a profile renamed to that name got them merged into its
      own (`rename_marks`). Found in the review of PR #16.
      (done 2026-10-27, P6 (B), user decisions: an inline two-step confirmation (no
      `st.dialog`), marks deleted after the confirmation with their count named, only the
      saved copy folder entry of `settings.json` removed (never the folder or the copies),
      no stable profile id and no schema change. "Delete profile" stores
      `st.session_state.delete_pending = (name, saves)` and shows a warning below the
      form (`deletion_consequences`: the number of marks with the match/no-match split or
      why they cannot be deleted; the copy folder entry goes, folder and copies stay;
      reference images stay because `profiles.json.bak` still names them and "Clean up
      storage" can delete them later) with "Delete for good" (primary, disabled while a
      search runs) and "Cancel". Any save since the click (also one refused by A13) or the
      profile's disappearance ends the question. After the deletion is saved,
      `forget_profile` calls `framescout_core.delete_marks` (all marks of the profile
      under the marks lock like `rename_marks`; returns their count; an unreadable file
      raises `ValueError` and is never replaced) and `forget_copy_folder` (removes only
      the `copy_folders[name]` entry under the settings lock, writes nothing without an
      entry) and drops the session's unsaved copy folder of that name; a part that fails
      is named in the notice at the top of the profile tab. The gallery hint for a missing
      profile now says that deleting a profile deletes its marks. `marks.json` stays in
      `NEVER_DELETED`. No `profiles.json`, CLI or cache change. Review fixes (same PR):
      a gallery drawn before the deletion or a rename can no longer save marks or a copy
      folder under the old name (see A33); clicking "Delete profile" reruns at once, so
      only one question is shown; the question also names a copy folder typed in this
      session but not saved (`copy_folders_unsaved`), which is forgotten too; the number
      of marks the question named is kept (`delete_marks_named`) and a different number
      deleted is named in the notice; `carry_over` and `forget_profile` share
      `change_name_data`/`add_notice`. Tests: 798 passed, 1 skipped
      (`tests/test_marks.py`, `tests/test_copy.py`, `tests/test_profile_file.py`); the app
      flow was checked with Streamlit's `AppTest` on a scratch copy, not in a real
      browser. Remaining: A34 (marks of profiles deleted before this change stay in
      `marks.json`).)

- [x] **A21 – Marks follow the absolute photo path:** `results/marks.json` keys a mark by
      the photo's full path, like the cache (E8). After moving or renaming the photo folder
      (or a subfolder, or the photo) the old marks no longer apply: they stay in the file
      but are not shown, are counted as "not among the results of this search" and fail
      with "the photo no longer exists" when copied. Found in the PR of A17.
      (closed 2026-10-28 as won't do – renamed/moved photos count as new; superseded by
      the unbound-entries cleanup, same user decision as E8. Such marks stay in the file
      until the user selects "Marks of unbound photos" in "Clean up storage", which
      removes only them. PR #40.)

- [x] **A33 – The gallery of a deleted profile's old results still offers "Copy to folder":**
      typing a folder there saved it under the deleted name in `settings.json`, so a later
      profile of that name got it again (the rest of A22). The review of the PR of A22
      found the same for a gallery drawn before its profile was deleted or renamed
      (another tab): its mark control and copy field were still live and their callbacks
      wrote under the old name. Found in the PR of A22.
      (done 2026-10-27 in the PR of A22: `framescout_core.require_profile` raises
      `UnknownProfileError` for a name that is not in `profiles.json` now;
      `save_marks`/`save_copy_folder(..., profiles_file=...)` check it under their lock,
      and the app's `set_mark`/`set_copy_folder` pass `PROFILES`, so nothing is written
      and the gallery shows why; a deletion or rename saves `profiles.json` first and then
      changes these files under the same locks, so no save in between is missed. The
      "Copy to folder" field is disabled for a profile that is no longer a search profile.
      Tests in `tests/test_marks.py`, `tests/test_copy.py`, `tests/test_profile_file.py`;
      the stale-tab click itself was not reproduced in a browser.)

### Installation / project

- [x] **I1 – No git repository.** (done 2026-10-20)
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
- [x] **I12 – Fresh installs can get untested major versions:** `requirements.txt` sets only
      minimum versions apart from torch/torchvision (user decision in PR #8), so a fresh
      install takes the newest release, e.g. Pillow 13.0.0 was on PyPI while the venv of
      PR #8 had 12.3.0 (PR #8 review; the venv has 13.0.0 now, and the smoke runs of E25,
      E22 and I11 used it). Upper bounds on the major version (`<13`) or a lock file would
      keep installs on tested versions; part of the pinned dependencies of P5.
      (done 2026-10-26, part A of P5: new `constraints.txt` pins all 84 packages of the
      dependency closure of `requirements.txt` exactly (`name==version`, no hashes; torch
      and torchvision without a local label, so `+cpu`, `+cu126` and `+cu130` match);
      `Install-FrameScout.bat` runs `pip install -r requirements.txt -c constraints.txt`
      and sets `PIP_CONSTRAINT` for `install_torch.py` (I18).
      `requirements.txt` keeps its ranges without upper bounds (I3 decision); a plain
      `pip install -r requirements.txt` still takes the newest releases, and the
      missing-package message of a search model names `-c constraints.txt`. Refreshing the
      pins is manual in a PR of its own (no Dependabot; procedure in the header of
      `constraints.txt`, including a check of the CUDA wheels' metadata).
      `tests/test_constraints.py` checks the pins (exact, sorted) against
      `requirements.txt` and the installer's command lines, `test_torch_install.py` the
      torch pins against `TORCH_VERSION`/`TORCHVISION_VERSION`; transitive completeness is
      only checked by the dry-run at refresh time. Verified: pip dry-run for Python 3.12,
      3.13 and 3.14 (win_amd64, wheels only), a CPU engine run on 22 photos (incl. 2 HEIC)
      with the pinned versions on Python 3.14; the Requires-Dist of the `+cpu`, `+cu126` and
      `+cu130` wheels (cp312 to cp314) on the PyTorch index allow every pin (PR #33
      review). Not run: `Install-FrameScout.bat` on a fresh clone, the CUDA installer
      variant, a real install on 3.12/3.13, a camera RAW photo, the `+cpu` torch build.)
- [x] **I18 – `install_torch.py` ignores `constraints.txt`:** it installs torch with its
      dependencies from PyPI in their newest versions, and the next installer step moves
      them to the pins (an extra download and reinstall of e.g. numpy, Pillow, sympy on a
      fresh install). Passing `-c constraints.txt` to its pip command would avoid that; left
      out of I12 because `install_torch.py` stayed unchanged by decision. Small and optional.
      (done 2026-10-26 in PR #33 after its review, without changing `install_torch.py`'s
      code: `Install-FrameScout.bat` sets `PIP_CONSTRAINT=constraints.txt` after creating
      the venv, and the pip call of `install_torch.py` inherits it. Relative, because pip
      splits the variable at whitespace; both pip calls run in the install folder. A test
      checks the order venv, variable, `install_torch.py`. Verified: pip dry-run of the
      `+cpu` install on Python 3.14 with the variable set resolves torch, torchvision and
      their 11 dependencies all to their pins; the requirements step against the project
      venv with the variable and `-c` installs nothing. Not run: the installer itself, the
      CUDA variant (only its wheel metadata), Python 3.12/3.13.)
- [x] **I14 – `docs/ARCHITECTURE.md` cannot be searched cheaply:** the file has 35 KB in
      68 lines; whole paragraphs are single lines of up to 3,747 characters, so a Grep hit
      returns about as much text as a section, and the implementer brief's rule "Grep for
      the files, functions and IDs you touch and read those sections" saves little agent
      context. Fix: wrap the text at about 90 characters like the other docs and split the
      long sections ("Files and responsibilities", "Current UI / runtime details", "Test
      coverage and known quirks") into `###` sub-sections per file or topic, so a Grep hit
      or a Read of one sub-section returns only what an item needs. Content unchanged
      (Markdown only). Also update the stale size note "47 KB" for `BACKLOG.md` (now about
      62 KB) in the `/roadmap` skill and the implementer brief. Found on 2026-10-25 while
      checking whether splitting the code saves agent context.
- [x] **I15 – `framescout_core.py` is too large to read for one change:** 2,375 lines /
      111 KB (roughly 30k tokens) covering about ten unrelated areas: slugs and reference
      moves, atomic file writes, the PyTorch build and devices, run lock and status,
      batching, profiles, settings, results and gallery helpers, marks, copying, cleanup.
      An agent that reads it whole for a focused change keeps all of it in its context for
      every later turn (implementer and reviewer alike). Fix: turn it into a package
      `framescout_core/` with one module per area and a shared internal module for the
      helpers several areas use (`_publish_via_temp`, `_publish_new`,
      `_replace_with_retry`, the JSON and lock helpers); `framescout_core/__init__.py`
      re-exports the names, so `import framescout_core` and `framescout_core.<name>` in
      `app.py`, the engine, `install_torch.py` and the tests keep working. Constraints:
      standard library only in every module (CI); behavior unchanged and no cache
      signature change (`ENGINE` and the golden values in `tests/test_signature.py`
      untouched). About a dozen tests patch private helpers on the package
      (`monkeypatch.setattr(framescout_core, '_publish_new' | '_remove_file' | '_missing'
      | '_copy_new' | '_unreferenced_references', …)`); after a re-export such a patch no
      longer reaches the module that calls the helper, so the test silently stops testing
      the failure path: patch the defining module instead and check that each such test
      still fails when the guarded code is broken. (Patches of `framescout_core.os`,
      `.shutil` and `.Path` change the shared module or class and keep working.) Update
      the module map in `docs/ARCHITECTURE.md` and "Where things are" in `CLAUDE.md`;
      `git blame` of the moved functions then points at the move commit (note it in the
      PR). Not part of this item: splitting `app.py` (1,085 lines, e.g. one module per
      tab), since the tabs share `st.session_state` keys and the `setting_<name>` rule, so
      the gain is smaller and the risk larger; reconsider after I15. Do I14 first.
      (done 2026-10-26: package `framescout_core/` with 15 area modules and `_common.py`,
      every statement moved unchanged (AST-compared); private helpers are not re-exported,
      so a stale patch of a private helper on the package now fails instead of silently
      missing; a patch of a re-exported public name on the package (e.g. `read_profiles`)
      still succeeds without reaching the modules that import it, documented in
      `docs/ARCHITECTURE.md`; the patching tests target the defining module and were
      checked to fail with the patch bypassed; `tests/test_core_package.py` checks that
      every public name of an area module is re-exported)
- [x] **I17 – One implementer carries the whole item in one growing context:** the
      implementer of A25 (PR #28, Opus, effort high) ended at 290k tokens of context
      after 129 API calls and 233 tool calls (105 Edit, 71 Bash, 27 Read); it grew
      steadily from 42k with no compaction and no error loops, and hit the user's
      session limit once (56 minutes' pause). Measured parts: about 80k tokens of tool
      results, about 113k of the agent's own output (edits, commands and thinking, which
      stays in context for the whole tool loop). Two steps ran late with the full
      context: the documentation updates (`README.md`, `docs/ARCHITECTURE.md`,
      `BACKLOG.md`) started at about 230k, and the review fixes ran in the same agent
      (`/roadmap` continues the implementer with `SendMessage` while it is alive),
      starting at 249k, so every call of that phase sent over 250k tokens. Fix:
      (1) `address-review` always spawns a fresh implementer that reads the PR text,
      diff and unanswered review comments itself, never continues the previous one;
      (2) the implementer commits the code and tests and then hands the documentation
      updates to a fresh agent (or returns, and `/roadmap` spawns one) with a short
      brief: the item, the commits, which docs to update; that agent reads only the
      diff and the doc sections it touches. Update the PR workflow in `CLAUDE.md` (the
      single source of the rules), the state table and spawning section of `/roadmap`
      and the implementer brief, plus a docs brief if (2) needs one. Expected: a
      fresh agent starts at about 60–80k instead of 250k; an item like A25 should end
      at about 150–180k per agent (estimate, not measured). Not part of this item:
      lower effort for implementers, splitting large items. Found on 2026-10-26 by
      analyzing the transcript of the PR #28 implementer.
- [x] **I22 – `BACKLOG.md` is too large to read per change:** at about 98 KB (1,200
      lines) it exceeded the read limit of the Read tool, and every implementer and reviewer
      that looked up an item paid for the long reports of finished items. (Done 2026-10-27:
      the file was split by state. `BACKLOG.md` holds the open items, `docs/BACKLOG-DONE.md`
      the finished ones with their reports, `ROADMAP.md` the roadmap with the open items
      first. IDs and their text are unchanged; no item was rewritten except for moving it.)
- [x] **I20 – The uninstall script depends on the `py` launcher:** it looked for Python
      3.14/3.13/3.12 through `py -<version>` and could not run without it (it printed manual
      steps). Part C of P5 (portable Python variant) must give it the portable interpreter
      and decide how a portable build is uninstalled. Found on 2026-10-27 in P5 part B.
      (Done 2026-10-27 in P5 part C, PR #36: `Uninstall-FrameScout.bat` runs the script with
      `.python\python.exe` if present, otherwise with the `py` launcher (installations of
      older installers; manual steps if neither exists). `.python` is an uninstall item
      ("private Python", `UNINSTALL_FIRST`: `python.exe`, `pythonw.exe`). A running Python
      cannot delete itself, so `framescout_core.running_python` finds the `.python` item
      when the interpreter runs from it (not for a link); the script deletes everything
      else, lists `.python` as "deleted last, when this script has ended" and exits with
      `PRIVATE_PYTHON_EXIT_CODE` = 3, only after `yes` and not in a dry run, after
      failures or when `.python` was skipped. The `.bat` then deletes `python.exe`,
      `pythonw.exe` and `.python` itself (`rmdir /s /q`) and reports a leftover with exit
      code 1. Tests: `tests/test_uninstall.py`. Runtime-checked under `.tmp` with the real
      private Python; not against a full installation with PyTorch.)
- [x] **I21 – `Install-FrameScout.bat` breaks in a folder with `!` in its path:** it used
      `setlocal EnableDelayedExpansion`, so cmd dropped the `!` from `cd /d "%~dp0"` and from
      every `%CD%` (`TORCH_HOME`, `HF_HOME`, `PIP_CACHE_DIR`, `TMP`, ...): the `cd` failed
      and the caches pointed to a folder that did not exist (or another one). Shown for the
      uninstaller in a dry run on a scratch copy (`Fo!to (old)\fs`: it ran the script of
      the current directory); `Uninstall-FrameScout.bat` was fixed in PR #34. Found on
      2026-10-27 in the review of PR #34. (Done 2026-10-27 in P5 part C, PR #36: the
      installer uses no delayed expansion, `goto` instead of blocks, and the folder path
      is never used inside parentheses. `tests/test_installer.py` checks both, like the
      uninstaller's test; runtime-checked in a folder `Fo!to (old)\fs`.)
- [x] **I24 – The installer takes any `.python` with `python.exe` for complete (minor):** a
      `.python` that lost files in `Lib` (e.g. an interrupted manual delete) makes only the
      `venv` step fail; the message then says to delete `.python` and `.venv`. Possible fix:
      check `.python\python.exe -I -c "import venv, ensurepip"` before using it and download
      the package again otherwise. Found on 2026-10-27 in P5 part C. (Done 2026-10-27 in
      P5 part C, PR #36, with the review finding that `.python` was reused without checking
      its version: before reusing `.python`, the installer runs
      `.python\python.exe -I -c "import sys, platform, venv, ensurepip; ..."` with
      `PYTHON_VERSION`; if it fails or reports another version, `.python` is deleted and
      downloaded again. The check runs only when no working `.venv` exists, so a working
      installation is never changed. Tests: `tests/test_installer.py` (the check's code also
      runs on the test Python); runtime-checked under `.tmp` with `Lib\venv` removed from
      the real private Python and with the version 3.14.8 against 3.14.9.)
- [x] **I10 – Manual runs leave files in the user profile:** importing Ultralytics without
      `YOLO_CONFIG_DIR` writes `%APPDATA%\Ultralytics\settings.json` (seen in PR #8 when a
      development command imported it). The `.bat` files and the app set the variable, but
      the manual engine command in `README.md` and `CLAUDE.md` does not, and the same
      applies to `TORCH_HOME`, `HF_HOME` and `XDG_CACHE_HOME` (model downloads land in the
      user profile). This is a gap for a clean uninstall. Fix idea: the engine sets these
      variables to the project's `.cache/` when they are unset (`os.environ.setdefault`
      before importing torch, open_clip and ultralytics), or a documented PowerShell snippet.
      (Done 2026-10-29, PR #42, roadmap P7 (B): `framescout_core.default_cache_env` fills
      `TORCH_HOME`, `HF_HOME`, `XDG_CACHE_HOME` and `YOLO_CONFIG_DIR` with the project's
      `.cache/` subfolders when they are unset or empty, at module level in
      `framescout_engine.py` before numpy/torch/open_clip/Ultralytics are imported; a value
      the user set is kept. The `.bat` files and the app still set them themselves (the app
      overrides, the engine only fills gaps); `app.py` takes the paths from
      `cache_paths`. Manual runs no longer use the user profile's `.cache` or
      `%APPDATA%\Ultralytics`; weights downloaded there earlier are not reused or touched.
      Follow-ups: E39, I25. Unit-tested; engine-import subprocess tests ran locally with
      torch; no run with real models.)
- [x] **I26 – Review comments could be lost, worktrees piled up:** a reviewer whose `/code-review`
      returned only a findings list posted nothing yet set `fs:review-done`, and leftover
      worktrees and `worktree-agent-*` branches had to be cleaned up by hand. Found on
      2026-10-29 in the PR workflow. (Done 2026-10-29, user decision in chat: the reviewer
      checks that the findings are on the PR and otherwise posts them itself as one numbered
      comment, never runs a second review, and swaps the label only afterwards; the
      orchestrator treats "not posted" as not done and posts the reported findings itself;
      `address-review` answers a numbered comment in one comment. `/roadmap` has a fixed
      worktree cleanup step (clean, fully pushed worktrees are removed, dead locks are
      unlocked, merged `worktree-agent-*` branches are deleted with `-d`). Markdown only,
      nothing executed; `.claude/settings.json` is unchanged, so `git worktree remove` and
      `git branch -D` still ask. Follow-ups: I27, I28, I29. E40–E43 and A36 in the same PR are PR #42's out-of-round findings.)
- [x] **I27 – Routine worktree commands still ask for approval:** `/roadmap` cleans up
      worktrees and `worktree-agent-*` branches as a fixed step (I26), but
      `.claude/settings.json` did not pre-approve the commands. Found in the PR of I26.
      (Done 2026-10-30, user decision in chat: `git worktree unlock/remove/prune`,
      `git branch -d` and `git branch -D` are allowed without a prompt; `git worktree remove`
      with `-f`/`--force` still asks; `git branch -d/-D main` is denied. `/roadmap` section 4
      updated. Checked only that `settings.json` is valid JSON; not exercised in a real
      `/roadmap` run.)
- [x] **I8 – No branch protection for `main`:** GitHub returns HTTP 403 "Upgrade to GitHub
      Pro or make this repository public to enable this feature" for the private repo, so
      `main` is protected only by the workflow rule (merge only on explicit user approval)
      and the deny rules in `.claude/settings.json`, which are not a security boundary.
      Options: GitHub Pro, making the repository public, or accepting the workflow rule.
      User decision → hold point. (Done 2026-10-30, user decision in chat: the repository
      is public since 2026-10-30 (PR #47 added the license and security policy first). The
      ruleset `protect main` on the default branch blocks deletion and force pushes, needs
      linear history and a pull request (no approval required, rebase merges only) and
      the three `pytest (Windows, Python 3.1x)` checks; repository admins may bypass it only
      when merging a pull request (`gh pr merge --admin`), never with a direct push. The
      repository allows only rebase merges; secret scanning with push protection,
      Dependabot alerts and private vulnerability reporting are on; Actions are limited to
      GitHub-owned actions pinned to a SHA, and workflows of outside contributors' pull
      requests need approval. Dependabot security and version updates stay off (I9).
      `.claude/settings.json` denies `gh pr merge --admin`. Settings checked with
      `gh api repos/enqii/frame-scout/rulesets` and the repository's settings endpoints.)

- [x] **A28 – The same photo folder by another path is searched twice:** A25 compared
      folders by resolved path only, so a mapped drive letter and the UNC path of one
      share, two drive letters or a `subst` drive for one folder, and the same file
      through a hard link were analyzed, cached and ranked twice. Found in PR #28.
      (done 2026-10-30 in PR #50: `distinct_folders` also compares `os.stat` identities
      (`st_dev`, `st_ino`) of the listed folders and of their ancestor folders; a folder
      that is the same as, or inside, another listed folder by another path is dropped
      with a note; without an identity (missing folder, `st_ino` 0, stat error) the
      path comparison applies as before. The scan deduplicates supported files by
      identity plus size and modification time (hard links, file symlinks; different
      photos with a repeated file id stay apart; one `os.stat` per walked folder and per
      photo file, which replaces the stat per entry of `rglob`). Review fix: ancestors are
      stat'ed only for a folder with an identity. No change to `profiles.json`,
      `settings.json`, CLI, `ENGINE` or `marks.json`. Unit tests inject identities; real
      mapped/UNC/subst drives were not tested. Silent dropping of duplicates: A37.)
- [x] **A29 – Junctions and links inside a photo folder are followed:** `Path.rglob('*')`
      follows directory junctions on Python 3.14, so a junction into another listed
      folder or into the same folder found photos twice or walked a cycle. Found in PR #28.
      (done 2026-10-30 in PR #50, without a user decision: links are still followed, so
      event folders linked into a parent keep working, but nothing is found twice.
      `scan_each_folder` walks with `os.scandir`; each folder once by identity, all real
      subfolders of all listed folders before any link, so links into walked folders
      and loops add nothing and a photo reachable both ways is listed by its real path,
      counted for the folder it is really in. The output folder is left out wherever it
      is reached (listed, inside a listed folder, through a link or another path); folders
      and files without a file id are compared by their real path, so a link loop ends
      there too; a folder that cannot be read is tried again through another path (review
      fixes). `scan_photos` and `scan_folders` are built on it; the app counts per folder
      from one `scan_each_folder` call. A photo earlier found through a link path is now
      only found by its real path, so cache rows and marks under the link path are no
      longer used (A21). Needs `DirEntry.is_junction` (Python 3.12+). The "skip links"
      option was not needed. The app's per-folder count was checked once manually with
      Streamlit's `AppTest` (a junction between two listed folders; not part of the test
      suite, so the `app.py` change has no automated test); the folder symlink test is
      skipped without privilege.)
- [x] **A6 – Folder count on every rerun:** `rglob` over the whole photo folder on every
      interaction; slow for large folders/network drives.
      (closed 2026-10-30 as a duplicate of A27, fixed in PR #53)
- [x] **A27 – The photo folder is scanned on every rerun:** the "Photo source" tab counted
      the photos at module level, so every widget interaction walked the whole photo tree
      again. Found in the PR #26 review.
      (done 2026-10-30 in PR #53; A6 was the same problem, see above. The count is
      remembered per browser session: `framescout_core.remembered_scans` (stdlib only)
      keeps the `scan_each_folder` result in `st.session_state['photo_count']`, keyed on
      the folder paths, the readable formats and the output folder, and scans again only
      when that key changes, on the new "Recount" button, or in a new session. The
      existing folders are still checked with `is_dir` on every run, so a reconnected
      drive recounts, and with no existing folder the remembered count is dropped, so
      the same folder is counted again when it is back (review). UX choice: no automatic
      refresh within a session; the caption "Counted at HH:MM:SS" shows the age and
      "Recount" refreshes it. The search itself always scans again, so a stale count
      never affects results. Alternatives not chosen: recount after a fixed age (a TTL),
      recount after each finished search. No change to `profiles.json`, `settings.json`,
      CLI, `ENGINE` or results. Tested with unit tests of `remembered_scans` and one
      Streamlit `AppTest` run; not tested in a real browser or on a large/network
      folder.)
