# FrameScout — Claude Code project onboarding

## Purpose and product direction
FrameScout is a **local, general-purpose AI image search** tool for large folders of photographs. Users describe a motif in natural language and/or supply example images; the app ranks likely matching local files. Use cases include people, cosplay, objects, vehicles, animals, landscapes and scenes. **Do not re-specialize the UI or algorithms for cosplay, PicDrop, a particular photographer, computer, or image source.** The user wants a convenient and eventually portable Windows application with a simple UI and a clean uninstall.

## Language
- **Project language is English** for everything in the repository and on GitHub: code, identifiers, code comments, UI, generated outputs, docs, commit messages, PR titles/descriptions, review comments and skills. CLIP prompts are English anyway.
- Exception until backlog item **I7** is done: the UI strings in `app.py`, the HTML gallery and log messages of `framescout_engine.py` and the `.bat` messages are still German. Do not translate them outside of I7; quote them verbatim (with an English gloss) in docs.
- Chat with the user may be in German.

## Status
Current baseline: **v1.1, prototype**, with a Streamlit frontend and a separate Python CLI engine. The git repository (`main` on `enqii/frame-scout`) is the source of truth; inspect the code before making changes.

One full end-to-end search run on Windows has been confirmed (I6): `run.log` from the original checkout shows 4,997 photos, 6 search profiles, CLIP on CPU, YOLO person detection enabled, 0 errors (2,609 new analyses + 2,388 from cache, i.e. a resumed run) and 6 HTML galleries written. The project `.venv` used for that run is Python 3.14.8 with torch 2.14.1+cpu (per `.venv/pyvenv.cfg` and the installed torch package; `run.log` itself does not record versions). The log also shows the QuickGELU warning (E1). This is a single CPU-only run, not a test suite: CUDA, other Python versions, a fresh install on another machine and the edge cases in the backlog are **not** verified. Treat syntax checks, unit tests and a real model run as distinct kinds of evidence, and do not call the app production-ready.

## Files and responsibilities
- `app.py`: Streamlit frontend. Tabs (current German UI): Suchprofile (search profiles), Fotoquelle (photo source), KI-Einstellungen (AI settings), Suche & Ergebnisse (search & results). Handles profile CRUD, reference uploads, in-session settings, hardware display, analysis process, progress/log UI and HTML downloads.
- `framescout_engine.py`: standalone CLI. Parses arguments, loads models, embeds images, optionally detects persons, caches embeddings, ranks and exports HTML galleries.
- `framescout_core.py`: shared by app and engine, **standard library only** (importable without torch/Streamlit): `EXT`, `slugify`, `profile_slugs` (unique result file names, used by both), `write_new_file` (reference uploads without overwriting), `generic_prompts` and `load_profiles` (profile loading/validation, used by the engine). Put logic here when both sides need it or it should be unit-tested without models.
- `tests/`, `pytest.ini`, `requirements-dev.txt`: pytest suite for `framescout_core` (no torch, no model download); dev dependency `pytest`.
- `profiles.json`: persisted profile list (currently both the shipped example and the user's working file; see I7). Back it up before overwriting user changes.
- `requirements.txt`: Streamlit, numpy, Pillow, torch, open_clip_torch, ultralytics, psutil; versions currently loosely constrained.
- `Install-FrameScout.bat`: checks installed Python 3.14/3.13/3.12 (in that order), creates project-local `.venv`, installs requirements, performs imports.
- `Start-FrameScout.bat`: launches app via that venv on `127.0.0.1:8501`.
- `README.md`: English user guide (GitHub start page).
- `BACKLOG.md`: known weaknesses (IDs E/A/I) and the prioritized roadmap that drives the PR workflow.
- `.claude/skills/roadmap/`: the `/roadmap` orchestrator skill plus implementer/reviewer briefs. `.claude/settings.json`: shared permission rules for the workflow.
- `.github/pull_request_template.md`: definition-of-done checklist for every PR.
- `.github/workflows/tests.yml`: CI – runs `pytest` (plus a `compileall` syntax check of all Python files outside dot-directories) on `windows-latest` for Python 3.12/3.13/3.14 on every pull request and push to `main`. It installs only `requirements-dev.txt` and fails if torch is installed, so tests must not need torch or model downloads. Green CI is unit-test and syntax evidence only, not a model run.
- Runtime data (generated, not in the repo): `photos/` (default input), `references/`, `results/`, `results/cache.sqlite3`, `results/vorschaubilder/`, `run.log`, `.cache/`, `.tmp/`, `.venv/`, `yolo11n.pt`.

## How to run (Windows)
1. Clone the repository (or download and extract the ZIP) into a directory you control. Install a compatible Python if needed.
2. Double-click `Install-FrameScout.bat` (prefer keeping all packages inside `.venv`).
3. Double-click `Start-FrameScout.bat`; local browser URL `http://127.0.0.1:8501`.
4. In the app, choose an existing local folder (including subfolders), configure search profiles, review AI settings, start the search and open HTML results from `results/`.
5. ZIP/downloaded online albums need to be separately downloaded/extracted by the user; FrameScout itself has no online-service integration.

Manual commands for development (after installation):
```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
.\.venv\Scripts\python.exe framescout_engine.py .\photos --profiles .\profiles.json --output .\results --device cpu --batch-size 8 --top 150
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # once
.\.venv\Scripts\python.exe -m pytest
```
Do not claim these commands work on a given Python build without running them in that environment. For smoke runs during development, write output under `.tmp/` (e.g. `--output .\.tmp\smoke-results`), never into the user's `results/`.

## Current search pipeline
- Uses OpenCLIP `ViT-B-32`, `pretrained='openai'`, for normalized text and image embeddings. No LLM is required. Four generic English prompt templates are derived from each profile's name and optional context, plus extra templates if `features` is provided; user-defined `prompts` are appended.
- Optional Ultralytics `yolo11n.pt` person detection (`classes=[0]`) extracts individual person crops **in addition to the full original image**. Detection is deliberately optional for non-person motifs; the detector currently runs on CPU.
- Text similarity = maximum cosine similarity across prompt vectors for a whole image/crop. If reference images exist, visual similarity = max over reference vectors; final score is `(1-reference_weight)*text_score + reference_weight*visual_score` (default reference weight .35). The best full-image/crop score represents a source photo. Scores are relative search heuristics, not probabilities or guaranteed identification.
- Feature rows are stored in `results/cache.sqlite3` per resolved file path + engine/config signature, checked against modification nanoseconds and size. Image embeddings are serialized in float16; profile queries can reuse existing image features. Changes to detector settings can invalidate the cached feature signature.
- Outputs one ranked `.html` file per profile (`<slug>.html` from `framescout_core.profile_slugs`: ASCII transliteration, `-2`, `-3`, … on collisions in profile order, hash fallback), with separate JPEG thumbnails in `results/vorschaubilder/` and `file://` links to originals. Keep the output folder intact; exporting an HTML file on its own does **not** embed thumbnails. Local paths may not work on another computer.
- Supported inputs: JPG, JPEG, PNG, WebP, BMP, TIF, TIFF, recursively. The engine excludes the output folder if nested in the input root.

## Profiles schema
```json
{
  "profiles": [
    {
      "name": "Red car",
      "franchise": "Vehicles",
      "features": "red bodywork, four wheels",
      "reference_images": [],
      "prompts": []
    }
  ]
}
```
`franchise` is a legacy internal field name; in the UI it means optional **Kontext / Herkunft** (context / origin), not necessarily a media franchise. Reference paths are interpreted relative to the profile JSON file directory. For new profiles, `app.py` uploads references into `references/<slug>/` (`framescout_core.slugify`; profiles with the same slug share the folder, see A1). Uploads are named `reference-<n>` with the next free number and never overwrite an existing file. Never silently delete or overwrite user profiles/references. There is also a legacy CLI option `--character`; consider backward compatibility before renaming it.

## Current UI / runtime details
- Settings in `st.session_state` (not persisted across sessions): input folder default `BASE/photos`, device `auto|cpu|cuda`, batch 8, top 150, person detection on, maximum 12 persons, confidence .30, reference weight .35.
- The frontend spawns the engine via `subprocess.Popen`, redirects stdout/stderr to `run.log` and polls it with a Streamlit fragment every two seconds. The start/stop process handle lives in the current Streamlit session, **not** in a robust background job manager. Browser/session lifecycle and concurrent sessions need careful design before claiming resilience.
- Stop currently calls `terminate()` and falls back to `kill()` after a timeout; each analyzed photo is committed to SQLite, but abrupt termination and log/results state should be tested.
- Hardware info is detected dynamically via `platform`, `os`, `psutil` and `torch.cuda`; `auto` chooses CUDA if PyTorch detects it, otherwise CPU. Do not hardcode the CPU/GPU model or the user's RAM. A GPU may exist without CUDA support.
- The Windows batch scripts set cache/temp environment variables under the project directory (`TORCH_HOME`, `HF_HOME`, `YOLO_CONFIG_DIR`, `XDG_CACHE_HOME`, `TMP`, `TEMP`), aiming for easy cleanup. Some dependencies may still leave user-level caches; do not promise perfect portability or no residual files.

## Engineering principles / known areas to test
1. Preserve general-purpose wording and behavior across UI, presets, prompts, docs, filenames and outputs.
2. Keep all user image data local; do not add cloud uploads, tracking, or network services without explicit consent. First use downloads model weights and pip packages.
3. Separate frontend and engine; maintain a working CLI and a usable CPU-only path (32 GB RAM and a dedicated GPU must **not** be prerequisites).
4. Save user state safely, validate paths and profiles, protect data during migrations; avoid overwriting `profiles.json` and user-selected photos/results.
5. Add focused tests without requiring full model downloads. Profile loading, prompt generation and slug handling are covered by `tests/` (via `framescout_core`); still missing: cache signature/reuse, scoring and progress interpretation (A11). Add a small integration smoke test for real models when feasible.
6. Potential current quirks to investigate rather than assume solved (most are tracked in `BACKLOG.md`): result file names must stay derived from `framescout_core.profile_slugs` on both sides (app downloads and engine export), and the app re-derives them from the current profile list, which can point at a stale gallery after edits (A12); profiles with the same slug share one reference folder (A1); Streamlit settings are session-only; result file downloads do not contain thumbnails; exceptions during model load may leave only `run.log`; Python 3.14 has been verified for one CPU run only; asynchronous stop/progress robustness; multiple simultaneous sessions; absolute paths/HTML link portability. The UI's dynamic system information is informational, not a hardware benchmark.
7. Never conflate a similarity score with certainty. Explain that large group photos, subtle subjects and artwork-to-photo reference comparisons can yield false positives/negatives.

## Development workflow for Claude Code
- Roadmap work (`BACKLOG.md` → "Roadmap") goes through the PR workflow below; start it with `/roadmap`. The skill is user-invoked only (so subagents can never start a second orchestrator): if the user asks in words to continue, resume or check the roadmap, ask them to type `/roadmap` instead of improvising the workflow.
- For ad-hoc requests: first read `README.md`, `BACKLOG.md`, `app.py`, `framescout_engine.py`, `profiles.json`, `requirements.txt` and both `.bat` files. Summarize the current code state and risks before changing architecture. If the request is unspecified, ask which improvement to implement next.
- For each change, report modified files, migration/backward-compatibility consequences, test commands and which tests were actually executed (vs. not executed).
- Keep `README.md`, `BACKLOG.md` (check off items, add new findings with IDs) and this `CLAUDE.md` current when behavior changes.
- Avoid claiming the app is production-ready without an actual end-to-end test.

## PR workflow
The roadmap is implemented semi-autonomously, **one pull request per roadmap item**. The `/roadmap` skill (`.claude/skills/roadmap/SKILL.md`) is the orchestrator: it is stateless, reconstructs the current state from git and GitHub on every start and spawns subagents (implementer, reviewer) with the briefs in the same folder. **This section is the single source of the workflow rules**; the skill and the briefs contain procedures and commands and refer back here instead of repeating the rules.

- **Strictly sequential:** the next roadmap item is started only after the previous PR has been merged.
- **Branch naming:** `<type>/<id>-<short>`, e.g. `fix/a1-unique-reference-names`, `chore/p0-workflow-english`. Branch from an up-to-date `origin/main` without tracking it (`git switch --no-track -c <branch> origin/main`) and always push with the branch named (`git push [-u] origin <branch>`); never push to `main` directly, never force-push, never discard work you did not create.
- **Commits:** atomic Conventional Commits (see below), each pushed immediately after it is created, so that no work exists only locally.
- **Draft PR early:** right after the first commit, open a draft PR (template: `.github/pull_request_template.md`) and label it `fs:in-progress`.
- **State labels** (exactly one per roadmap PR):
  | Label | Meaning |
  |---|---|
  | `fs:in-progress` | implementer is working on the branch |
  | `fs:needs-review` | implementation done, PR marked ready, waiting for the reviewer |
  | `fs:review-done` | reviewer posted `/code-review` findings as PR comments |
  | `fs:ready` | findings addressed or declined with reasons; waiting for the user's merge approval |
- **Review:** a fresh reviewer agent runs `/code-review medium <PR> --comment` and must not change code. The implementer then verifies every finding technically, fixes it or declines it with a reasoned reply on the comment thread, and summarizes "addressed / declined" in the PR.
- **Out-of-scope findings go into the backlog:** anything found while working on a PR that is outside its scope – valid review findings that are deferred, discovered limitations, new bugs – is added to `BACKLOG.md` **in the same PR** as a new item with the next free ID of its group (E/A/I). A declined review reply that defers work names that backlog ID. `BACKLOG.md` is the single source of truth for open work; do not create GitHub issues.
- **Merge:** only after the user's explicit approval in chat, as a rebase merge (`gh pr merge <PR> --rebase --delete-branch`), followed by worktree and branch cleanup and updating local `main` – the exact procedure is in `/roadmap` → "Merge".
- **Definition of done:** all checklist items of the PR template are true – summary and backlog IDs, modified files, migration/compatibility consequences, tests executed (with output) vs. not executed, CI checks green, `BACKLOG.md`/`README.md`/`CLAUDE.md` updated where needed, user data untouched, review findings addressed or declined.
- **Hold points** – the implementer stops and returns a question instead of guessing; the orchestrator asks the user (and posts the question as a PR comment once a PR exists):
  - product/design decisions (e.g. P3 multilingual search or stronger models, P4 gallery/UX, P5 distribution);
  - breaking changes: `profiles.json` schema, CLI options, cache invalidation, folder renames;
  - new dependencies or downloads, unless the roadmap item explicitly names them (e.g. `pytest` in step (1));
  - anything that cannot be verified locally (e.g. CUDA without an NVIDIA GPU) → the PR is marked "not runtime-tested";
  - changes to search quality → first a small local evaluation set (kept outside the repo).
- **User data protection:** never modify, delete or commit the user's working files: the local `profiles.json`, `photos/`, `references/`, `results/`, `run.log`. The tracked example `profiles.json` changes only in a PR whose roadmap item covers it (I5/I7); stage files by name, never in bulk. Tests use pytest's `tmp_path`; smoke runs read and write only under `.tmp/` (no `..` in `--output`) and set `TORCH_HOME`, `HF_HOME`, `XDG_CACHE_HOME` and `YOLO_CONFIG_DIR` to the main checkout's `.cache/` first, as the `.bat` files do; a download that would still be needed is a hold point.
- **Pausing and resuming:**
  - Same PC: `claude --continue` or `claude --resume` restores the orchestrator session. Background subagents do **not** survive exiting Claude Code, but their pushed commits and PR comments do; `/roadmap` picks up from the PR labels.
  - Other PC: clone the repo, run `Install-FrameScout.bat`, start Claude Code in the folder and run `/roadmap`; it reconstructs the state from GitHub.
  - Not transferable: unpushed local work (worktrees under `.claude/worktrees/`) and subagent context.
- **Permissions:** `.claude/settings.json` pre-approves the routine git/gh/pytest commands of this workflow. Pushes are pre-approved only as `git push [-u] origin <type>/…`; a bare `git push`, `gh pr merge`, force/reset variants of `git branch`/`git switch`, bulk staging (`git add -A`/`.`, `git commit -a`, anything naming `profiles.json`) and engine smoke runs ask; force pushes, `--mirror`/`--all`/`--delete`, pushes naming `main` and `git reset --hard` are denied. Rules are evaluated deny → ask → allow and match the command text with `*` wildcards; they steer the agent but are **not** a security boundary (`git -C . push`, `sh -c …` or an absolute path to `git` are not matched, and `main` cannot be branch-protected on the current GitHub plan, see I8). Personal overrides go into `.claude/settings.local.json` (gitignored).

## Git and commits
- Repository: private GitHub repo `enqii/frame-scout`, default branch `main`.
- Git identity: repo-local `enqii <24801755+enqii@users.noreply.github.com>` (`git config user.name` / `user.email` in the repository). Never commit with the global (work) identity; check `git config user.email` in new clones and worktrees.
- GitHub CLI: `C:\Program Files\GitHub CLI\gh.exe` (may not be on `PATH`; in Git Bash use `"/c/Program Files/GitHub CLI/gh.exe"`).
- Commit messages **must** follow the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) specification: `<type>[optional scope][!]: <description>`, optional body, optional footers.
- Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `style`, `revert`. Breaking changes (e.g. incompatible `profiles.json` schema or CLI options) are marked with `!` and a `BREAKING CHANGE:` footer.
- Suggested scopes: `engine`, `app`, `install`, `profiles`, `deps`, `backlog`, `ci`.
- Description and body in English, imperative mood, lowercase start, no trailing period; reference backlog IDs where applicable, e.g. `fix(app): stop overwriting reference images (A1)`.
