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
- [ ] **E8 – Cache key = absolute path:** moving the photo folder forces a complete
      recomputation.
- [ ] **E9 – `yolo11n.pt` ends up in the project root** instead of `.cache/`; not documented.
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
- [ ] **E12 – Skipped photos leave gaps in the gallery:** a photo whose thumbnail fails
      (deleted since scoring, unreadable) is skipped after the top-N cut, so the gallery
      shows e.g. #2, #3, #4 and fewer than `--top` cards although lower-ranked photos
      exist. Fix idea: rank only the photos that got a card and fill up to `--top`.
      Also: `ensure_thumbnail` repeats the `stat()` done during scoring; the mtime could
      be kept with the score (PR #6 review). Since P4 (A) the app's result gallery shows
      the same gaps: `results.json` keeps the ranks of the HTML gallery.
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
- [ ] **E24 – An interrupted export leaves galleries newer than `results.json`:** the
      engine writes `results.json` only after all galleries, so a search stopped while it
      writes the galleries has already replaced some HTML files, while the app still shows
      the previous complete search (its date is shown, and the status says that the last
      run did not finish). Opening such a gallery from the app shows the newer, partial
      result. Fix idea: write the galleries under temporary names and publish them
      together with `results.json` at the end. Found in PR #14.
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
- [ ] **E26 – Other temporary files of a stopped run stay in `results/`:** the atomic
      writes of `run-status.json` and `results.json` (and of `marks.json` by the app) go
      through `<name>.<random>.tmp`; `terminate()`/`kill()` during such a write leaves that
      file behind, like the thumbnails of E13. They are small and rare, and the cleanup
      of E7 does not remove them (an app session may be writing `marks.json` at that
      moment). Fix idea: remove `run-status.json.*.tmp` and `results.json.*.tmp` older than
      a minute in `auto_cleanup`. Found in PR #18.
- [ ] **E27 – Ultralytics sends usage analytics:** with person detection the engine runs
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
- [ ] **E28 – Ultralytics installs packages at run time:** importing `ultralytics`
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
- [ ] **E29 – HEIC/RAW support as optional extras:** E25 made `pillow-heif` and `rawpy`
      required in `requirements.txt` (user decision at the PR #26 hold point; the user may
      want them optional later). Idea: a separate requirements file, a question in
      `Install-FrameScout.bat`, and the engine's existing fallback (formats without their
      package are skipped with a note). Roadmap candidate, not scheduled.
- [ ] **E30 – A RAW file is lost when its JPEG partner is broken:** E25 skips a RAW file
      when a JPEG/HEIC of the same name is in the same folder, by names only. If that
      JPEG is truncated or corrupt (e.g. a card or transfer error), the engine logs it as an
      `ERROR` and the shot is missing from the search, although its RAW file is fine
      (documented in the README). Fix idea: when a partner fails to decode, analyze its
      skipped RAW file instead (the scan already lists them in `PhotoScan.raw_pairs`); the
      cache and the gallery would then show the RAW path for that shot. Found in the PR #26
      review.

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
      (2026-10-23, P4 (A): the app shows the date of the search whose results it shows and
      marks a profile changed, renamed or deleted since, from `results.json` (A12). Still
      open: deleting a profile without confirmation.)
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
      it and switching to `width` belong together in this item. The result gallery of P4
      (A) uses `use_container_width` for its buttons as well.)
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
- [ ] **A13 – Concurrent profile edits are lost:** the app reads `profiles.json` on every
      rerun and saves its whole list, so an edit made in another tab/session (or by hand)
      between that read and a save is overwritten; `profiles.json.bak` holds only the
      state before the last save. Fix idea: save only if the file is unchanged since it
      was read (mtime/hash), otherwise reload and ask. More than one backup generation
      (rotating `.bak` files, a one-time copy before the v3 conversion) also belongs
      here; for now the user chose a single `profiles.json.bak` (PR #6 review).
- [x] **A14 – Unreferenced reference files accumulate:** removing reference images from a
      profile, deleting a profile or a failed save of `profiles.json` after the upload
      leaves the files in `references/` (deliberately – nothing is deleted silently).
      Fix idea: list files no profile references and offer to delete them, with the
      user's consent; part of the cleanup in P4.
      (done 2026-10-25 with E7: "Clean up storage" lists the image files in `references/`
      that neither `profiles.json` nor `profiles.json.bak` names, by name and unselected;
      `profiles.json` is read again just before deleting, emptied folders are removed, and
      the category is not offered if either file cannot be read.)
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
- [ ] **A21 – Marks follow the absolute photo path:** `results/marks.json` keys a mark by
      the photo's full path, like the cache (E8). After moving or renaming the photo folder
      (or a subfolder, or the photo) the old marks no longer apply: they stay in the file
      but are not shown, are counted as "not among the results of this search" and fail
      with "the photo no longer exists" when copied. Fix idea: key by the path relative
      to the photo folder and match a moved folder, or offer to carry marks over. Found
      in the PR of A17.
- [ ] **A22 – Marks of a deleted profile pass to a new profile of the same name:** marks
      (A17) and the saved copy folder are keyed by the profile name only. Deleting a
      profile keeps them (FrameScout never deletes user data silently), so a profile
      created later under the same name shows the old marks and copies them, and a
      profile renamed to that name gets them merged into its own (`rename_marks`; its own
      marks win for the same photo). Fix options, each a user decision: delete or archive
      a profile's marks when it is deleted (asking in the app first), or give profiles a
      stable id in `profiles.json` (schema change, hold point). Found in the review of
      PR #16.
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
- [ ] **A25 – Only one photo folder per search:** user question on 2026-10-25. The app and
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

### P3b – Agent context (before further features)
Smaller files to read per change, so implementer and reviewer agents keep less context
(added 2026-10-25 at the user's request, placed before the remaining P4 items).
- [x] Reflow `docs/ARCHITECTURE.md` into short lines and sub-sections (I14) (done 2026-10-26)
- [x] Split `framescout_core.py` into a package of modules per area, re-exporting the
      names; no behavior change (I15) (done 2026-10-26)

### P4 – UX
The item "Result gallery in the app, mark matches/copy them to a folder, "open folder",
ZIP export with thumbnails" is split into three pull requests, in this order (user
decision in PR #14):
- [x] (A) Result gallery in the app: the engine writes `results/results.json`; the app shows
      the last search as a thumbnail grid with "Open", "Folder", "Open gallery in
      browser" and "Open results folder", and marks profiles changed since (A12, part of A8)
      (done 2026-10-23; macOS/Linux untested: A19)
- [x] (B) Mark matches and copy them to a folder (A17) (done 2026-10-25; marks in
      `results/marks.json`, three states; feedback into the search: A20)
- [~] (C) ZIP export with thumbnails (open decision: A18) – deferred by user decision
      2026-10-25, skipped by `/roadmap`
- [x] Cleanup of cache/thumbnails/orphaned HTML files and reference files (E7, E11, A14);
      never delete `results/marks.json` (A17) (done 2026-10-25; also E13, E23; HEIC/RAW
      split out into the next item by user decision)
- [x] Optional HEIC/RAW support (E25; new dependencies: a hold point) (done 2026-10-26 in
      PR #26; also AVIF; packages required by user decision, optional extras: E29)
- [ ] Turn off Ultralytics' usage analytics and run-time package installs (E27, E28; own
      PR after E25, user decision at the PR #26 hold point)
- [ ] Several photo folders per search (A25; changes `results.json` and the CLI: a hold point)

### P4b – Search models (evaluate at home first)
- [ ] Optional stronger models (ViT-B-16, ViT-L-14, SigLIP) with a CPU runtime note (E22;
      investigation, candidates and user decisions recorded there)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of the previous item (E21)

### P5 – Distribution
- [ ] Pinned dependencies (I12), portable Python variant, uninstall script
