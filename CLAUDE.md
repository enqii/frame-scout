# FrameScout — Claude Code project onboarding

## Purpose and product direction
FrameScout is a **local, general-purpose AI image search** tool for large folders of photographs. Users describe a motif in natural language and/or supply example images; the app ranks likely matching local files. Use cases include people, cosplay, objects, vehicles, animals, landscapes and scenes. **Do not re-specialize the UI or algorithms for cosplay, PicDrop, a particular photographer, computer, or image source.** The user wants a convenient and eventually portable Windows application with a simple UI and a clean uninstall. Development and UI communication are primarily in German; English CLIP prompts are acceptable.

Current baseline: **v1.1, prototype**, with a Streamlit frontend and a separate Python CLI engine. It has *not* been confirmed through an end-to-end Windows/Python 3.14 search with downloaded model weights. Treat syntax and archive checks as distinct from a successful runtime test. The shipped ZIP is the source of truth; inspect the code before making changes.

## Files and responsibilities
- `app.py`: Streamlit frontend. Tabs: Suchprofile, Fotoquelle, KI-Einstellungen, Suche & Ergebnisse. Handles profile CRUD, reference uploads, in-session settings, hardware display, analysis process, progress/log UI and HTML downloads.
- `framescout_engine.py`: standalone CLI. Parses profiles/arguments, loads models, embeds images, optionally detects persons, caches embeddings, ranks and exports HTML galleries.
- `profiles.json`: persisted profile list. Back it up before overwriting user changes.
- `requirements.txt`: Streamlit, numpy, Pillow, torch, open_clip_torch, ultralytics, psutil; versions currently loosely constrained.
- `Install-FrameScout.bat`: checks installed Python 3.14/3.13/3.12 (in that order), creates project-local `.venv`, installs requirements, performs imports.
- `Start-FrameScout.bat`: launches app via that venv on `127.0.0.1:8501`.
- `README.txt`: current German user guide.
- Runtime data (generated, not shipped): `photos/` (default input), `references/`, `results/`, `results/cache.sqlite3`, `results/vorschaubilder/`, `run.log`, `.cache/`, `.tmp/`, `.venv/`.

## How to run (Windows)
1. Extract project ZIP to a directory you control. Install compatible Python if needed.
2. Double-click `Install-FrameScout.bat` (prefer keeping all packages inside `.venv`).
3. Double-click `Start-FrameScout.bat`; local browser URL `http://127.0.0.1:8501`.
4. In app, choose an existing local folder (including subfolders), configure search profiles, review AI settings, start search and open HTML results from `results/`.
5. ZIP/downloaded online albums need to be separately downloaded/extracted by the user; FrameScout itself has no online-service integration.

Manual command for development (after installation):
```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150
```
Do not claim these commands work on a given Python build without running them in that environment.

## Current search pipeline
- Uses OpenCLIP `ViT-B-32`, `pretrained='openai'`, for normalized text and image embeddings. No LLM is required. Four generic English prompt templates are derived from each profile's name and optional context, plus extra templates if `features` is provided; user-defined `prompts` are appended.
- Optional Ultralytics `yolo11n.pt` person detection (`classes=[0]`) extracts individual person crops **in addition to the full original image**. Detection is deliberately optional for non-person motifs; detector currently runs on CPU.
- Text similarity = maximum cosine similarity across prompt vectors for a whole image/crop. If reference images exist, visual similarity = max over reference vectors; final score is `(1-reference_weight)*text_score + reference_weight*visual_score` (default reference weight .35). The best full-image/crop score represents a source photo. Scores are relative search heuristics, not probabilities or guaranteed identification.
- Feature rows stored in `results/cache.sqlite3` per resolved file path + engine/config signature, checked against modification nanoseconds and size. Image embeddings are serialized in float16; profile queries can reuse existing image features. Changes to detector settings can invalidate the cached feature signature.
- Outputs one ranked `.html` file per profile, with separate JPEG thumbnails in `results/vorschaubilder/` and `file://` links to originals. Keep the output folder intact; exporting an HTML file on its own does **not** embed thumbnails. Local paths may not work on another computer.
- Supported inputs: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF, recursively. The engine excludes the output folder if nested in the input root.

## Profiles schema
```json
{
  "profiles": [
    {
      "name": "Rotes Auto",
      "franchise": "Fahrzeuge",
      "features": "red bodywork, four wheels",
      "reference_images": [],
      "prompts": []
    }
  ]
}
```
`franchise` is a legacy internal field name; in the UI it means optional **Kontext / Herkunft**, not necessarily a media franchise. Reference paths are interpreted relative to the profile JSON file directory. For new profiles, `app.py` uploads references into `references/<slug>/`. Never silently delete or overwrite user profiles/references. There is also a CLI `--character` legacy option; consider backward compatibility before renaming it.

## Current UI / runtime details
- Settings in `st.session_state` (not persisted across all sessions): input folder default `BASE/photos`, device `auto|cpu|cuda`, batch 8, top 150, person detection on, maximum 12 persons, confidence .30, reference weight .35.
- The frontend spawns the engine via `subprocess.Popen`, redirects stdout/stderr to `run.log` and polls it with a Streamlit fragment every two seconds. Start/stop process handle lives in the current Streamlit session, **not** a robust background job manager. Browser/session lifecycle and concurrent sessions need careful design before claiming resilience.
- Stop currently calls `terminate()` and falls back to `kill()` after timeout; each analyzed photo is committed to SQLite, but abrupt termination and log/results state should be tested.
- Hardware info is detected dynamically via `platform`, `os`, `psutil` and `torch.cuda`; `auto` chooses CUDA if PyTorch detects it, otherwise CPU. Do not hardcode model of CPU/GPU or user's RAM. A GPU may exist without CUDA support.
- Windows batch scripts set cache/temp environment variables under the project directory (`TORCH_HOME`, `HF_HOME`, `YOLO_CONFIG_DIR`, `XDG_CACHE_HOME`, `TMP`, `TEMP`), aiming for easy cleanup. Some dependencies may still leave user-level caches; do not promise perfect portability or no residual files.

## Engineering principles / known areas to test
1. Preserve general-purpose wording and behavior across UI, presets, prompts, docs, filenames and outputs.
2. Keep all user image data local; do not add cloud uploads, tracking, or network services without explicit consent. First use downloads model weights and pip packages.
3. Separate frontend and engine; maintain working CLI and a usable CPU-only path (32 GB RAM and dedicated GPU must **not** be prerequisites).
4. Save user state safely, validate paths and profiles, protect data during migrations; avoid overwriting `profiles.json` and user-selected photos/results.
5. Add focused tests for profile loading, prompt generation, cache signature/reuse, scoring, unique filename/slug handling, and progress interpretation without requiring full model downloads. Add a small integration smoke test for real models when feasible.
6. Potential current quirks to investigate rather than assume solved: `app.py` has a duplicate `import os`; UI `unique_slug` and engine `slugify` should stay aligned especially for non-ASCII names; uploaded reference filenames (`reference-1...`) may overwrite existing files on subsequent uploads; Streamlit settings are session-only; result file downloads do not contain thumbnails; exceptions during model load may leave only `run.log`; install/runtime compatibility on Python 3.14 needs real verification; asynchronous stop/progress robustness; multiple simultaneous sessions; absolute paths/HTML link portability. The UI's dynamic system information is informational, not a hardware benchmark.
7. Never conflate a similarity score with certainty. Explain that large group photos, subtle subjects and artwork-to-photo reference comparisons can yield false positives/negatives.

## Immediate development workflow for Claude Code
First read `README.txt`, `app.py`, `framescout_engine.py`, `profiles.json`, `requirements.txt` and both `.bat` files. Summarize the current code state and risks before changing architecture. Ask which next improvement to implement if the user's request is unspecified. For each change, report modified files, migration/backward-compatibility consequences, test commands and which tests were actually executed. Keep README and this CLAUDE.md current when behavior changes. Avoid claiming the app is production-ready without an actual end-to-end test.
