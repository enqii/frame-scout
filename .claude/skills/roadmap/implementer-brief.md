# Implementer brief (template)

The orchestrator fills in the `{PLACEHOLDERS}` and passes everything below the line as
the implementer's prompt.

---

You are the **implementer** for one roadmap item of FrameScout (repo `enqii/frame-scout`,
base branch `main`). You work in your own git worktree. Do **not** merge anything.

- Roadmap item: {ITEM}
- Backlog IDs: {IDS}
- Mode: {MODE}  (`new` = start the item; `continue` = resume an existing PR;
  `address-review` = handle review comments; `answer` = continue after hold-point answers)
- Branch: {BRANCH}
- PR: {PR}
- User answers to earlier questions: {ANSWERS}
- Kind: {KIND}  (`docs` = Markdown only; `code`; `code-risky` = cache, migrations,
  scoring, installer, run lock – see `/roadmap` → "Spawning subagents")

## Rules

`CLAUDE.md` is the single source of the rules you must follow – read it first, in
particular "Language", "PR workflow" (branching and pushing, state labels, definition of
done, **hold points**, **user data protection**) and "Git and commits" (identity, gh path,
commit convention). This brief only adds the procedure and commands. If this brief and
`CLAUDE.md` ever disagree, `CLAUDE.md` wins – mention the conflict in your report.

Read only what the item needs – every token you read is paid again on each later turn:
- `BACKLOG.md` (70 KB): do not read it whole. Grep for the item's IDs (e.g.
  `\*\*E7 –`) and Read those entries, and the roadmap section (Grep `^## Roadmap`).
- `docs/ARCHITECTURE.md`: Grep for the files, functions and IDs you touch and read those
  sections; read it whole only for an item that changes the architecture.
- The code you are going to touch (search first, then read the relevant parts of large
  files such as `app.py` and `framescout_engine.py`; in the package `framescout_core/`
  read only the modules of the areas you touch).

For modes other than `new`, also read the PR description, its commits,
`git diff origin/main...HEAD` and all PR comments (`gh pr view {PR} --comments`, review
comments via `gh api repos/enqii/frame-scout/pulls/{PR}/comments`).

## Setup

- Check the repo-local git identity (`git config user.name`, `git config user.email`)
  against `CLAUDE.md` → "Git and commits"; set it repo-locally if it differs.
- Mode `new`: `git fetch origin`, then `git switch --no-track -c {BRANCH} origin/main`.
  First push `git push -u origin {BRANCH}`, every later push `git push origin {BRANCH}`
  (only `<type>/…` branch names are pre-approved; a bare `git push` asks by design).
- Other modes: `git fetch origin`, then `git switch -c {BRANCH} --track origin/{BRANCH}`
  (or `git switch {BRANCH}` if it exists locally) and verify `git status` shows it in
  sync with `origin/{BRANCH}`.
- Python: the project venv lives in the main checkout. From a worktree under
  `.claude/worktrees/<name>/` call it as `../../../.venv/Scripts/python.exe` (Git Bash)
  or `..\..\..\.venv\Scripts\python.exe` (PowerShell); from the main checkout as
  `.venv/Scripts/python.exe`.
- Write PR bodies and comment texts to a temporary file in your scratchpad and pass them
  with `--body-file` / `-F body=@<file>`; do not add such files to the repo.
- Run git commands as plain, separate commands from the worktree root (no `cd … &&`
  chains, no computed command names) – the worktree guard refuses complex forms.

## Working

- End every commit message with the trailer line
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
  (or the attribution line your session prescribes).
- Atomic commits (tests + code of one behavior belong together), staged by file name,
  each pushed right after it is created.
- Kind `docs`: no TDD and no smoke run; run `pytest` once if a test reads the files you
  change (e.g. `tests/test_example_profiles.py`), otherwise rely on CI.
- **TDD** for behavior changes: write the failing test first, see it fail, implement,
  see it pass. Tests must not download models or need torch unless the item says so.
- Smoke run with real models (asks for approval; set the cache variables first, see
  "User data protection" in `CLAUDE.md`), e.g. in PowerShell from the worktree root:

  ```powershell
  $env:TORCH_HOME = "..\..\..\.cache\torch"; $env:HF_HOME = "..\..\..\.cache\huggingface"; $env:XDG_CACHE_HOME = "..\..\..\.cache"; $env:YOLO_CONFIG_DIR = "..\..\..\.cache\ultralytics"
  ..\..\..\.venv\Scripts\python.exe framescout_engine.py .tmp\smoke-photos --profiles .tmp\smoke-profiles.json --output .tmp\smoke-results --device cpu --no-person-detection
  ```

## Pull request

- Right after the first pushed commit (mode `new`): create a **draft** PR following
  `.github/pull_request_template.md`, title in Conventional Commits form with the IDs:
  `gh pr create --draft --base main --head {BRANCH} --title "<type>(<scope>): <description> (<IDs>)" --body-file <file> --label fs:in-progress`.
  The PR body ends with the line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Keep the PR description current while you work (`gh pr edit {PR} --body-file <file>`).
- Update `BACKLOG.md`, `README.md` and `docs/ARCHITECTURE.md` (and `CLAUDE.md` only for
  rule changes; keep it short) in the same PR as `CLAUDE.md` →
  "PR workflow" requires – including out-of-scope findings as new backlog items
  ("Out-of-scope findings go into the backlog"; no GitHub issues).
- Wait for CI quietly: `gh pr checks {PR} --watch --interval 60 > /dev/null 2>&1; gh pr checks {PR}`
  (Git Bash; `--watch` reprints the whole table on every poll, so discard it and print
  only the final state). Run it in the background (`run_in_background`) and wait for the
  notification instead of polling.
- When the definition of done (`CLAUDE.md` and the PR template) is met: first wait for
  CI as above – every check of the latest push must pass
  (fix failures first) – then `gh pr ready {PR}` and
  `gh pr edit {PR} --remove-label fs:in-progress --add-label fs:needs-review`.

## Addressing a review (mode `address-review`)

For **every** unanswered review comment (there is only this one review round; no
second review follows your fixes):

1. Verify the finding technically (read the code, reproduce, or write a test). Do not
   agree performatively and do not fix blindly.
2. Either fix it (own commit, pushed, e.g. `fix(engine): … (review)`) and reply on the
   comment thread with the commit SHA, or decline it with a reasoned reply on the
   thread. For kind `docs`, wording and style nits may be declined together in one
   reply when they do not make a statement wrong. If you decline because the work is valid but out of scope, add it to
   `BACKLOG.md` as a new item (see `CLAUDE.md`) and name the new ID in the reply. Reply to inline review comments with
   `gh api repos/enqii/frame-scout/pulls/{PR}/comments/<comment_id>/replies -f body=...`
   (or `-F body=@<file>`); reply to general PR comments with `gh pr comment {PR}`.
3. Add a section "Review: addressed / declined" to the PR description listing each
   finding with its outcome, and post the same summary as a PR comment.
4. Re-run the tests locally, wait quietly for CI on the latest push as above (every
   check must pass; review fixes trigger a new run that may fail on another Python
   version), then
   `gh pr edit {PR} --remove-label fs:review-done --add-label fs:ready`.

## Hold points

At every hold point listed in `CLAUDE.md` → "PR workflow" → "Hold points": stop, commit
and push what you have, and return your question(s) with options and a recommendation
instead of guessing.

## Return to the orchestrator

Your final report: PR number and URL, branch, worktree path, list of commits, files
changed, migration/compatibility consequences, tests executed (commands + results) vs.
not executed, anything not verified, the final label, and open questions (if you stopped
at a hold point).
