# Implementer brief (template)

The orchestrator does not copy this file. It spawns the implementer with a short prompt
that gives the placeholder values and tells it to read this brief and follow it. The
implementer reads everything below the line and substitutes the values from its prompt for
the `{PLACEHOLDERS}` (`{ITEM}`, `{IDS}`, `{MODE}`, `{BRANCH}`, `{PR}`, `{ANSWERS}`, `{KIND}`).

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
- `docs/BACKLOG.md` (open items, large) and `docs/BACKLOG-DONE.md` (finished items, one line each):
  do not read them whole. Grep both for the item's IDs (e.g. `\*\*E7 –`) and Read those
  entries. `docs/ROADMAP.md` is short (about 50 lines) and may be read whole.
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

- End every commit message with the `Co-Authored-By:` trailer that your session prescribes
  (its attribution reminder names your own model); do not copy a trailer from this brief,
  an older commit or another agent.
- Atomic commits (tests + code of one behavior belong together), staged by file name,
  each pushed right after it is created.
- Kind `docs`: no TDD and no smoke run; run `pytest` once if a test reads the files you
  change (e.g. `tests/test_example_profiles.py`), otherwise rely on CI.
- **TDD** for behavior changes: write the failing test first, see it fail, implement,
  see it pass. Tests must not download models or need torch unless the item says so.
  Test only what is necessary (`CLAUDE.md` → "Engineering principles" 5): no tests for
  message wording or hypothetical cases; a removed feature takes its tests with it.
- Code comments and docstrings you write or touch state what and why, never history:
  no backlog IDs, "(review)", dates or "user decision" notes (`CLAUDE.md` principle 8).
- Smoke run with real models (asks for approval; set the cache variables first, see
  "User data protection" in `CLAUDE.md`), e.g. in PowerShell from the worktree root:

  ```powershell
  $env:TORCH_HOME = "..\..\..\.cache\torch"; $env:HF_HOME = "..\..\..\.cache\huggingface"; $env:XDG_CACHE_HOME = "..\..\..\.cache"; $env:YOLO_CONFIG_DIR = "..\..\..\.cache\ultralytics"
  ..\..\..\.venv\Scripts\python.exe framescout_engine.py .tmp\smoke-photos --profiles .tmp\smoke-profiles.json --output .tmp\smoke-results --device cpu --no-person-detection
  ```

- **Long runs** (an engine or `framescout_eval.py run` over many photos, more than a few
  minutes): a background command of your session ends with your session, and the run with
  it (I13). Start it detached instead: write a `.cmd` file under `.tmp\` with the Write
  tool (ASCII only, `@echo off` first) that sets the cache variables above with
  `set "NAME=<absolute path>"` and runs the command with every path in double quotes and
  its output redirected (`> "<log>" 2>&1`) to a log under `.tmp\`, then start it with
  `$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = 'cmd /c "<absolute path of the .cmd>"'; CurrentDirectory = '<worktree>'}`.
  In this single-quoted PowerShell string write a `'` in a path as `''`; a path with
  spaces needs nothing more than the double quotes shown. Check `$r.ReturnValue -eq 0`
  (else the process did not start: report the value) and, a few seconds later, that the
  log exists and is not empty; `$r.ProcessId` is the process id. Wait for its end before you return – with a background
  command that loops until the process is gone or `<output>\run-status.json` shows a final
  phase (`finished`/`failed`/`interrupted`) – and report the log's last lines. If you
  must return earlier, report the process id, the log and the status file so that the
  next agent can wait for it.

## Pull request

- Right after the first pushed commit (mode `new`): create a **draft** PR following
  `.github/pull_request_template.md`, title in Conventional Commits form with the IDs:
  `gh pr create --draft --base main --head {BRANCH} --title "<type>(<scope>): <description> (<IDs>)" --body-file <file> --label fs:in-progress`.
  The PR body ends with the line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- Keep the PR description current while you work (`gh pr edit {PR} --body-file <file>`; if it fails with the Projects-classic GraphQL error, use the REST fallback in `SKILL.md` → "Tooling notes").
- Documentation (`docs/ROADMAP.md`, `docs/BACKLOG.md`, `docs/BACKLOG-DONE.md`, `README.md`, `docs/USER-GUIDE.md`, `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, and `CLAUDE.md` only
  for rule changes; keep it short; out-of-scope findings as new backlog items, no GitHub
  issues) belongs in the same PR and is written by you, after the code and tests: search the
  doc sections you touch, do not read the files whole. A finished item moves to `docs/BACKLOG-DONE.md` as one line (ID, title, date, PR link; the PR number is known once the draft PR exists, so add the line after that; an item without a PR says "no PR" and keeps a short report in the line, never a placeholder or an invented number).
- Before you return (every mode), delete your own smoke and scratch data under the
  worktree's `.tmp/` (gitignored leftovers make the orchestrator's worktree removal need
  `--force`, I38) and the Python caches you created (`__pycache__/`, `.pytest_cache/`,
  I48), and check `git status --porcelain --ignored` is empty.
- Wait for CI quietly: `gh pr checks {PR} --watch --interval 60 > /dev/null 2>&1; gh pr checks {PR}`
  (Git Bash; `--watch` reprints the whole table on every poll, so discard it and print
  only the final state). Run it in the background (`run_in_background`) and wait for the
  notification instead of polling.
- When the definition of done (`CLAUDE.md` and the PR template) is met: first wait for
  CI as above – every check of the latest push must pass
  (fix failures first) – then `gh pr ready {PR}`. The label stays `fs:in-progress`.

## Addressing a review (mode `address-review`)

You are always a fresh agent, never a continuation of the implementer: read the PR text,
diff and unanswered review comments yourself, and update the docs your fixes affect.

For **every** unanswered review comment (there is only this one review round; no
second review follows your fixes):

1. Verify the finding technically (read the code, reproduce, or write a test). Do not
   agree performatively and do not fix blindly.
2. Either fix it (own commit, pushed, e.g. `fix(engine): … (review)`) and reply on the
   comment thread with the commit SHA, or decline it with a reasoned reply on the
   thread. For kind `docs`, wording and style nits may be declined together in one
   reply when they do not make a statement wrong. If you decline because the work is valid but out of scope, add it to
   `docs/BACKLOG.md` as a new item (see `CLAUDE.md`) and name the new ID in the reply. Reply to inline review comments with
   `gh api repos/enqii/frame-scout/pulls/{PR}/comments/<comment_id>/replies -f body=...`
   (or `-F body=@<file>`); a general PR comment has no thread: answer each one with its own
   `gh pr comment {PR}` that starts with `Re: finding <n>` (or quotes it). Older PRs may have
   all findings in one numbered general comment: answer them in one `gh pr comment` that
   repeats each number with its outcome.
3. Add a section "Review: addressed / declined" to the PR description listing each
   finding with its outcome, and post the same summary as a PR comment.
4. Re-run the tests locally, wait quietly for CI on the latest push as above (every
   check must pass), then
   `gh pr edit {PR} --remove-label fs:in-progress --add-label fs:ready`. If it fails with the Projects-classic GraphQL error, use the REST fallback in `SKILL.md` → "Tooling notes".

## Hold points

At every hold point listed in `CLAUDE.md` → "PR workflow" → "Hold points": stop, commit
and push what you have, and return your question(s) with options and a recommendation
instead of guessing.

## Return to the orchestrator

Your final report: PR number and URL, branch, worktree path, list of commits, files
changed, migration/compatibility consequences, tests executed (commands + results) vs.
not executed, anything not verified, the final label, and open questions (if you stopped
at a hold point).
