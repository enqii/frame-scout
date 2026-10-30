# FrameScout — Claude Code project onboarding

## Purpose and product direction
FrameScout is a **local, general-purpose AI image search** tool for large folders of photographs. Users describe a motif in natural language and/or supply example images; the app ranks likely matching local files. Use cases include people, cosplay, objects, vehicles, animals, landscapes and scenes. **Do not re-specialize the UI or algorithms for cosplay, PicDrop, a particular photographer, computer, or image source.** The user wants a convenient and eventually portable Windows application with a simple UI and a clean uninstall.

## Language
- **Project language is English** for everything in the repository and on GitHub: code, identifiers, code comments, UI, generated outputs, docs, commit messages, PR titles/descriptions, review comments and skills. CLIP prompts are English anyway.
- UI strings, the HTML gallery, engine log/error messages and the `.bat` messages are English since I7. Remaining German names, kept for compatibility: the legacy crop label `Gesamtbild` in old cache rows (shown as "Full image" via `framescout_core.crop_label`) and the thumbnail folder `results/vorschaubilder/` of older runs (no longer written; new runs use `results/thumbnails/`).
- Chat with the user may be in German.

## Status
Current baseline: **v1.1, prototype**, with a Streamlit frontend and a separate Python CLI engine. The git repository (`main` on `enqii/frame-scout`) is the source of truth; inspect the code before making changes. Verified: one full CPU-only end-to-end search on Windows (Python 3.14, I6) and one CUDA engine smoke run (I11); everything else is **not** runtime-verified (details: `docs/ARCHITECTURE.md` → "Verified status"). Treat syntax checks, unit tests and a real model run as distinct kinds of evidence, and do not call the app production-ready.

## Where things are
- `app.py` (Streamlit frontend), `framescout_engine.py` (CLI engine: models, embedding, person detection, cache, ranking, HTML export), `framescout_core/` (shared logic, one module per area, re-exported by `__init__.py`; **standard library only**), `framescout_scoring.py` (scoring, **numpy only**), `install_torch.py` + `Install-FrameScout.bat`/`Start-FrameScout.bat`, `tests/` (pytest, no torch), `profiles.example.json`, `requirements*.txt`, `constraints.txt` (exact pins of all packages), `README.md` (overview), `docs/USER-GUIDE.md` (user guide), `docs/DEVELOPMENT.md` (CLI, tests, evaluation tool), `ROADMAP.md` (order of work), `BACKLOG.md` (open items), `docs/BACKLOG-DONE.md` (finished items with their reports), `.claude/skills/roadmap/` (PR workflow orchestrator).
- **`docs/ARCHITECTURE.md`** holds the details: every file's responsibilities and the `framescout_core` functions, the search pipeline, cache signature, scoring, profiles schema, settings sync, run lock/status, start/stop, test coverage and known quirks. Read the sections relevant to the files you touch before changing code; search it instead of reading it whole.

## Gotchas (rules that are easy to break without reading the details)
- Settings widgets in `app.py` get their values through `st.session_state` with keys `setting_<name>`; never pass them `value=`/`index=` (PR #10 review).
- Change `framescout_core.ENGINE_TEMPLATE` whenever cached embeddings become incompatible for all models (preprocessing, crops); another model or weights is a new `framescout_core.MODELS` entry with its own `engine_id`; signature golden values for every model are pinned in `tests/test_signature.py`; cache rows of other signatures are never deleted automatically, only by the user's "Clean up storage" (E7/E11), which must never delete `framescout_core.NEVER_DELETED` files (e.g. `marks.json`).
- Search terms are **English only** (E3): hint text only, no language check, warning or translation without a new user decision.
- `torch`/`torchvision` pins in `requirements.txt` and `constraints.txt` must equal `framescout_core.TORCH_VERSION`/`TORCHVISION_VERSION` (a test checks both).
- CI installs only `requirements-dev.txt` and fails if torch is installed: tests must not need torch, Pillow or model downloads.
- `profiles.json` and `settings.json` are the user's files: never replace an unreadable file, never commit them; `framescout_core.create_from_example` never overwrites.
- `franchise` in profiles is a legacy field name meaning "Context / origin"; the CLI option `--character` is legacy too – keep backward compatibility.
- Scores are relative search heuristics, never certainty or identification.

## How to run (Windows)
1. Clone the repository (or download and extract the ZIP) into a directory you control. No Python needs to be installed: the installer downloads a private Python 3.14 into `.python` (the folder cannot be moved afterwards).
2. Double-click `Install-FrameScout.bat` (prefer keeping all packages inside `.venv`). It offers GPU support if it finds an NVIDIA driver; `Install-FrameScout.bat cpu|cuda` chooses the PyTorch build directly. Never run the `cuda` variant on a development PC without approval: it downloads about 2.5 GB.
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
On a fresh clone, `profiles.json` exists only after the first app start; use `--profiles .\profiles.example.json` until then. Do not claim these commands work on a given Python build without running them in that environment. For smoke runs during development, write output under `.tmp/` (e.g. `--output .\.tmp\smoke-results`), never into the user's `results/`.

## Engineering principles
1. Preserve general-purpose wording and behavior across UI, presets, prompts, docs, filenames and outputs.
2. Keep all user image data local; do not add cloud uploads, tracking, or network services without explicit consent. First use downloads model weights and pip packages.
3. Separate frontend and engine; maintain a working CLI and a usable CPU-only path (32 GB RAM and a dedicated GPU must **not** be prerequisites).
4. Save user state safely, validate paths and profiles, protect data during migrations; avoid overwriting `profiles.json` and user-selected photos/results.
5. Add focused tests without requiring full model downloads (coverage and gaps: `docs/ARCHITECTURE.md` → "Test coverage and known quirks").
6. Never conflate a similarity score with certainty. Explain that large group photos, subtle subjects and artwork-to-photo reference comparisons can yield false positives/negatives.

## Development workflow for Claude Code
- Roadmap work (`ROADMAP.md`) goes through the PR workflow below; start it with `/roadmap`. The skill is user-invoked only (so subagents can never start a second orchestrator): if the user asks in words to continue, resume or check the roadmap, ask them to type `/roadmap` instead of improvising the workflow.
- For ad-hoc requests: read the parts of `README.md`, `docs/USER-GUIDE.md`, `docs/DEVELOPMENT.md`, `ROADMAP.md`, `BACKLOG.md`, `docs/ARCHITECTURE.md` and the code that the request touches (search before reading whole files). Summarize the current code state and risks before changing architecture. If the request is unspecified, ask which improvement to implement next.
- For each change, report modified files, migration/backward-compatibility consequences, test commands and which tests were actually executed (vs. not executed).
- Keep `README.md` (short: details go to the user guide or `docs/DEVELOPMENT.md`), `docs/USER-GUIDE.md`, `docs/DEVELOPMENT.md`, `ROADMAP.md`, `BACKLOG.md` (add new findings with IDs; a finished item is checked off and **moved with its report** to `docs/BACKLOG-DONE.md`) and `docs/ARCHITECTURE.md` current when behavior changes. Never read these backlog files whole: search for the ID. `CLAUDE.md` holds only rules and gotchas: change it when a rule changes, and keep it short, since every session and subagent loads it on every turn.
- Avoid claiming the app is production-ready without an actual end-to-end test.

## PR workflow
The roadmap is implemented semi-autonomously, **one pull request per roadmap item**. The `/roadmap` skill (`.claude/skills/roadmap/SKILL.md`) is the orchestrator: it is stateless, reconstructs the current state from git and GitHub on every start and spawns subagents (implementer, reviewer) with the briefs in the same folder. **This section is the single source of the workflow rules**; the skill and the briefs contain procedures and commands and refer back here instead of repeating the rules.

- **Strictly sequential:** the next roadmap item is started only after the previous PR has been merged.
- **Branch naming:** `<type>/<id>-<short>`, e.g. `fix/a1-unique-reference-names`, `chore/p0-workflow-english`. Branch from an up-to-date `origin/main` without tracking it (`git switch --no-track -c <branch> origin/main`) and always push with the branch named (`git push [-u] origin <branch>`); never push to `main` directly, never force-push, never discard work you did not create.
- **Fresh agents per phase (I17):** one implementer context must not carry a whole item. Kinds `code`/`code-risky`: the implementer commits and pushes code and tests, posts a PR comment starting `Docs pending:` (item, commit SHAs, docs to update) and returns; a fresh agent (`docs-update`) then updates `README.md`, `docs/USER-GUIDE.md`, `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, `BACKLOG.md`/`docs/BACKLOG-DONE.md` and `ROADMAP.md` from the diff and the doc sections it touches and marks the PR ready. Review fixes always run in a fresh implementer (`address-review`), never by continuing the previous one. Kind `docs` has no separate docs step.
- **Commits:** atomic Conventional Commits (see below), each pushed immediately after it is created, so that no work exists only locally.
- **Draft PR early:** right after the first commit, open a draft PR (template: `.github/pull_request_template.md`) and label it `fs:in-progress`.
- **State labels** (exactly one per roadmap PR):
  | Label | Meaning |
  |---|---|
  | `fs:in-progress` | implementer is working on the branch |
  | `fs:needs-review` | implementation done, PR marked ready, waiting for the reviewer |
  | `fs:review-done` | reviewer posted `/code-review` findings as PR comments |
  | `fs:ready` | findings addressed or declined with reasons; waiting for the user's merge approval |
- **Review:** one review round per PR: a fresh reviewer agent runs `/code-review <level> <PR> --comment` (level `low` for PRs that change only Markdown files, otherwise `medium`; models per item kind: `/roadmap` → "Spawning subagents") and must not change code. After the review is addressed there is no second review round. The implementer then verifies every finding technically, fixes it or declines it with a reasoned reply on the comment thread, and summarizes "addressed / declined" in the PR.
- **Out-of-scope findings go into the backlog:** anything found while working on a PR that is outside its scope – valid review findings that are deferred, discovered limitations, new bugs – is added to `BACKLOG.md` **in the same PR** as a new item with the next free ID of its group (E/A/I; search `BACKLOG.md` and `docs/BACKLOG-DONE.md`, the highest ID plus one). A declined review reply that defers work names that backlog ID. `BACKLOG.md` is the single source of truth for open work; do not create GitHub issues.
- **Merge:** only after the user's explicit approval in chat and with all CI checks of the approved head commit green, as a rebase merge (`gh pr merge <PR> --rebase --delete-branch`), followed by worktree and branch cleanup and updating local `main` – the exact procedure is in `/roadmap` → "Merge".
- **Definition of done:** all checklist items of the PR template are true – summary and backlog IDs, modified files, migration/compatibility consequences, tests executed (with output) vs. not executed, CI checks green, `ROADMAP.md`/`BACKLOG.md`/`docs/BACKLOG-DONE.md`/`README.md`/`docs/USER-GUIDE.md`/`docs/DEVELOPMENT.md`/`docs/ARCHITECTURE.md` (and `CLAUDE.md` for rule changes) updated where needed, user data untouched, review findings addressed or declined.
- **Hold points** – the implementer stops and returns a question instead of guessing; the orchestrator asks the user (and posts the question as a PR comment once a PR exists):
  - product/design decisions (e.g. P4b stronger or multilingual search models, P4 gallery/UX, P5 distribution);
  - breaking changes: `profiles.json` schema, CLI options, cache invalidation, folder renames;
  - new dependencies or downloads, unless the roadmap item explicitly names them (e.g. `pytest` in step (1));
  - anything that cannot be verified locally (e.g. CUDA without an NVIDIA GPU) → the PR is marked "not runtime-tested";
  - changes to search quality → first a small local evaluation set (kept outside the repo).
- **User data protection:** never modify, delete or commit the user's working files: the local `profiles.json`, `settings.json`, `photos/`, `references/`, `results/`, `run.log`. `profiles.json` is gitignored since I7; never add it back to the repository (the shipped examples live in `profiles.example.json`). Stage files by name, never in bulk. Tests use pytest's `tmp_path`; smoke runs read and write only under `.tmp/` (no `..` in `--output`) and set `TORCH_HOME`, `HF_HOME`, `XDG_CACHE_HOME` and `YOLO_CONFIG_DIR` to the main checkout's `.cache/` first, as the `.bat` files do; a download that would still be needed is a hold point.
- **Pausing and resuming:** state lives in git and GitHub (commits, PR labels, comments), so `/roadmap` picks up on any PC; background subagents and unpushed worktree changes do not survive (procedure: `/roadmap` → "Pausing and resuming").
- **Permissions:** `.claude/settings.json` pre-approves the routine git/gh/pytest commands; pushes only as `git push [-u] origin <type>/…`; `gh pr merge`, bulk staging and engine smoke runs ask; force pushes, pushes naming `main` and `git reset --hard` are denied. The rules steer the agent but are **not** a security boundary (details: `docs/ARCHITECTURE.md` → "Workflow permissions"). Personal overrides go into `.claude/settings.local.json` (gitignored).

## Git and commits
- Repository: public GitHub repo `enqii/frame-scout` (AGPL-3.0), default branch `main`.
- Everything pushed or posted is public: commits, PR texts, review comments and pasted test output must not contain local paths with user names, machine details or other personal data; write paths relative to the checkout (or `%USERPROFILE%`, `<worktree>`).
- Git identity: repo-local `enqii <24801755+enqii@users.noreply.github.com>` (`git config user.name` / `user.email` in the repository). Never commit with the global (work) identity; check `git config user.email` in new clones and worktrees.
- GitHub CLI: `C:\Program Files\GitHub CLI\gh.exe` (may not be on `PATH`; in Git Bash use `"/c/Program Files/GitHub CLI/gh.exe"`).
- Commit messages **must** follow the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) specification: `<type>[optional scope][!]: <description>`, optional body, optional footers.
- Types: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `style`, `revert`. Breaking changes (e.g. incompatible `profiles.json` schema or CLI options) are marked with `!` and a `BREAKING CHANGE:` footer.
- Suggested scopes: `engine`, `app`, `install`, `profiles`, `deps`, `backlog`, `ci`.
- Description and body in English, imperative mood, lowercase start, no trailing period; reference backlog IDs where applicable, e.g. `fix(app): stop overwriting reference images (A1)`.
