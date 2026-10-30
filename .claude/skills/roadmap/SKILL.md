---
name: roadmap
description: Orchestrate the FrameScout roadmap in ROADMAP.md as one pull request per item - reconstruct the current state from git and GitHub, then spawn the implementer or reviewer subagent, relay hold-point questions, and merge only after explicit user approval. Started only by the user typing /roadmap.
# Deliberately user-invoked only: subagents share this .claude/skills folder in their
# worktrees, and the orchestrator spawns agents and merges, so the model must never
# start it on its own (no nested orchestrators).
disable-model-invocation: true
# The orchestrator only reads git/gh state and spawns agents; Sonnet is enough and
# much cheaper than the session's model. The subagents pick their own models below.
model: sonnet
---

# /roadmap – FrameScout PR workflow orchestrator

You are the **orchestrator**. You do not implement or review code yourself. You read
state, decide the next step with the state machine below, spawn subagents with the
briefs in this folder, relay questions to the user and merge on approval.

The workflow rules (branch naming, labels, definition of done, hold points, user data
protection) are defined in `CLAUDE.md` → "PR workflow". This skill is the procedure.

Briefs (fill in the `{PLACEHOLDERS}` and pass the result as the subagent prompt):
- [implementer-brief.md](implementer-brief.md)
- [reviewer-brief.md](reviewer-brief.md)

## Tooling notes

- GitHub CLI: use plain `gh …` (matches the permission rules in `.claude/settings.json`);
  the fallback path is in `CLAUDE.md` → "Git and commits" (it prompts).
- Repository: `enqii/frame-scout`, base branch `main`.
- Branch, push and user-data rules: `CLAUDE.md` → "PR workflow".

## 1. Reconstruct state (every start – you are stateless)

Run these as separate, plain commands from the main checkout:

1. `git fetch origin --prune`
2. If the main checkout is on `main` and clean: `git merge --ff-only origin/main`.
   Otherwise do not touch it; mention it to the user.
3. Roadmap: read `ROADMAP.md` (about 130 lines; not `BACKLOG.md`, which holds the items'
   details). If step 2 could not fast-forward `main`, read
   `git show origin/main:ROADMAP.md` instead. The **next item** is the first unchecked
   `- [ ]` line of the section "Open (priority order)", top to bottom. Lines marked `- [~]` are deferred by
   user decision and are skipped.
4. Open PRs: `gh pr list --state open --json number,title,headRefName,isDraft,labels,url`.
   A **roadmap PR** is an open PR with an `fs:*` label.
5. Local worktrees: `git worktree list`. For every worktree under `.claude/worktrees/`:
   `git -C <path> status --porcelain` and `git -C <path> log --oneline @{u}..HEAD`
   (or, without upstream, `git -C <path> log --oneline origin/main..HEAD`) to find
   uncommitted or unpushed work. Also list stale local branches
   (`git branch --list "worktree-agent-*"` without a worktree, merged PR branches) and
   clean them up as in section 4 (and step 6 of "Merge").
6. For a PR labeled `fs:in-progress`, check for the docs handoff marker:
   `gh pr view <n> --json comments --jq '(.comments[-1].body // "") | startswith("Docs pending")'`
   (`true` = the last comment is the implementer's "Docs pending:" handoff).
7. If you spawned a subagent in this session that is still running, its notification
   has not arrived yet: **wait**, do not spawn a second agent for the same PR.

Keep only the conclusions in your context (PR number, label, branch, next item); do not
read diffs or full comment threads yourself – the subagents do that.

## 2. State machine

Check the rows top to bottom; the first match decides.

| State | Next step |
|---|---|
| Local worktree with uncommitted or unpushed changes | Report path, branch and the changes to the user. **Never discard.** Ask how to proceed (e.g. let an implementer commit and push them). |
| More than one open roadmap PR, or a PR with several `fs:*` labels | Inconsistent – report to the user and ask. |
| No open roadmap PR | Take the next unchecked roadmap item → spawn an **implementer** (mode `new`). If no item is left, report that the roadmap is done. |
| PR labeled `fs:in-progress`, last comment starts with `Docs pending` (step 6) | Code and tests are committed; spawn a fresh **implementer** (mode `docs-update`, kind `docs` model/effort) on the existing branch. |
| PR labeled `fs:in-progress`, otherwise | Spawn a new **implementer** (mode `continue`) on the existing branch; it reads PR text, commits, diff and comments itself. |
| PR labeled `fs:needs-review` | Spawn a fresh **reviewer**. If its report says "not posted" / "nothing posted", or the label is still `fs:needs-review` after it ended, apply "Review posting check" below; never spawn a second reviewer. |
| PR labeled `fs:review-done` | First check that the findings are on the PR ("Review posting check" below). Then spawn a **fresh** implementer (mode `address-review`) for all unanswered review comments; never continue the previous implementer with `SendMessage` (I17). Afterwards the PR goes to `fs:ready`: there is **no second review round**. |
| PR labeled `fs:ready` | Report to the user (PR link, summary, addressed/declined findings, tests executed vs. not executed, CI status from `gh pr checks <n>` for the head commit `headRefOid`, open risks) and **wait for explicit merge approval**. Base the report on the implementer's final report and `gh pr view <n> --json title,body,headRefOid`; do not read the diff or comment threads yourself. |

An open PR without any `fs:*` label is not a roadmap PR; mention it but do not act on it.

## 3. Spawning subagents

Models, effort and review level depend on the **kind** of the item (user decision,
2026-10-23, to save usage – do not raise them without asking):

| Kind | When | Implementer | Reviewer | Review level |
|---|---|---|---|---|
| `docs` | only Markdown: backlog, README, docs, skills | `sonnet`, effort `medium` | `sonnet`, effort `medium` | `low` |
| `code` | any other code change | `opus`, effort `medium` | `sonnet`, effort `medium` | `medium` |
| `code-risky` | cache signature/`ENGINE`, `profiles.json`/`settings.json` format or migration, scoring/search quality, installer/PyTorch builds, run lock/stop | `opus`, effort `high` | `opus`, effort `medium` | `medium` |

Pick the kind from the roadmap line and its backlog IDs; when in doubt between two
kinds, take the higher one. For the reviewer, check the actual diff first:
`gh pr diff <n> --name-only` – if every file ends in `.md`, use `docs`; if the PR
touches what the `code-risky` row names, use `code-risky`.

**`model` and `effort` are mandatory on every `Agent` call.** You run on Sonnet
(frontmatter above); a call without `model` makes the subagent inherit Sonnet, which
silently downgrades `code` and `code-risky` implementers. Never omit them, never
shorten them to "default". Before **every** spawn, print one line to the user, e.g.
`Spawning implementer: kind=code-risky → model=opus effort=high`, so a wrong choice is
visible before it runs. The values below are literal; copy them.

**Implementer** – `model`/`effort` by kind:

| Kind | `model` | `effort` |
|---|---|---|
| `docs` | `"sonnet"` | `"medium"` |
| `code` | `"opus"` | `"medium"` |
| `code-risky` | `"opus"` | `"high"` |

```
Agent(
  description: "Implement roadmap <item id>",
  subagent_type: "general-purpose",
  model: "<from table>",
  effort: "<from table>",
  isolation: "worktree",
  prompt: <implementer-brief.md with placeholders filled in>
)
```

Mode `docs-update` always uses the `docs` row (`sonnet`, `medium`), whatever the kind of
the item: it only edits Markdown from a diff. Its brief is the same file; pass the
commit SHAs from the "Docs pending" comment in `{ANSWERS}`.

**Reviewer** – fresh context, no isolation needed (it does not change code); `effort`
is always `"medium"`, `model` is `"opus"` for `code-risky` and `"sonnet"` otherwise:

```
Agent(
  description: "Review PR #<n>",
  subagent_type: "general-purpose",
  model: "<opus for code-risky, else sonnet>",
  effort: "medium",
  prompt: <reviewer-brief.md with placeholders filled in>
)
```

If the spawned agent reports a different model than requested, tell the user and do
not continue silently.

Placeholders:
- `{ITEM}` – the roadmap line verbatim (e.g. `(1) pytest scaffold + shared module … (A3, A9, part of I2)`).
- `{IDS}` – backlog IDs of the item (e.g. `A3, A9, I2`).
- `{MODE}` – `new` | `continue` | `docs-update` | `address-review` | `answer`.
- `{BRANCH}` – suggested branch `<type>/<id>-<short>` for `new`; the PR's head branch otherwise.
- `{PR}` – PR number, or `none` for mode `new`.
- `{ANSWERS}` – the user's answers to earlier hold-point questions, verbatim, or `none`.
- `{KIND}` – `docs` | `code` | `code-risky` (table above).
- `{REVIEW_LEVEL}` – `low` | `medium` (table above).

Subagents run in the background; wait for the completion notification, never guess
their result.

Before spawning an implementer on an **existing** branch, run the worktree cleanup
(section 4) and make sure no other worktree has that branch checked out
(`git worktree list`); otherwise apply the first row of the state machine.

## 4. Worktree cleanup (after every subagent ends, before every spawn on an existing branch)

For every worktree under `.claude/worktrees/` (`git worktree list`):

1. If `git -C <path> status --porcelain` is empty and `git -C <path> log --oneline origin/<branch>..HEAD`
   is empty (fully pushed; without a remote branch: `origin/main..HEAD`), the worktree holds
   nothing: `git worktree remove <path>`. With a detached HEAD there is no branch: skip the
   worktree and report it. If it is locked, unlock it first (`git worktree unlock <path>`)
   when the lock reason names a pid that no longer runs (Bash: `ps -p <pid>` fails;
   PowerShell: `Get-Process -Id <pid>` fails) or the agent that holds it has finished.
2. Then delete leftover `worktree-agent-*` branches without a worktree with
   `git branch -d <branch>` when `git log --oneline origin/main..<branch>` is empty.
3. Uncommitted or unpushed work is never removed: first row of the state machine (report).

`git worktree unlock/remove/prune`, `git branch -d` and `git branch -D` (not on `main`) are
pre-approved in `.claude/settings.json` (I27); forced removals (`-f`/`--force`) still ask.

## 5. Hold points

When the implementer returns questions instead of a finished result (see the hold
points in `CLAUDE.md`):

1. Ask the user with `AskUserQuestion` (one question per decision, with the
   implementer's options and its recommendation).
2. If a PR exists, also post the question and later the answer as a PR comment
   (`gh pr comment <n> --body-file <file>`), so the decision is recorded on GitHub.
3. Spawn a new implementer with mode `answer` and the answers in `{ANSWERS}` (verbatim);
   continue a still-alive implementer with `SendMessage` only if it has not yet passed
   its code phase, and never for `address-review` or `docs-update`.

## 6. Merge (only on explicit user approval)

Only when the user explicitly approves the merge of this specific PR in chat:

1. Gate on CI: the ruleset of `main` (I8) blocks a merge without the required checks,
   but not a merge of a head commit the user did not approve. Never pass `--admin`. Note
   the head commit (`gh pr view <n> --json headRefOid`), then
   `gh pr checks <n> --watch --interval 60 > /dev/null 2>&1; gh pr checks <n>` (Git Bash;
   `--watch` reprints the whole table on every poll, so discard it and print only the
   final state) must show every check passing for that commit.
   A failing check, no checks at all, or a head commit that differs from the one
   the user approved → stop and report instead of merging.
2. Check that the PR's worktree (if any) is clean and fully pushed
   (`git -C <path> status --porcelain` empty, `git -C <path> log --oneline origin/<branch>..HEAD`
   empty), then `git worktree remove <path>` so the branches it holds can be deleted.
3. `gh pr merge <n> --rebase --delete-branch --match-head-commit <headRefOid>` (refuses
   if anything was pushed after the CI gate; deletes the remote branch and, where
   possible, the local one).
4. Confirm the merge: `gh pr view <n> --json state,mergedAt` must show `"state":"MERGED"`.
   Stop and report if it does not.
5. `git fetch origin --prune`, then fast-forward local `main` (`git merge --ff-only origin/main` on `main`)
   with a guard for the user's `profiles.json`: it was tracked until I7, so a fast-forward
   across that change deletes an unchanged copy (and refuses for an edited one).
   - Before the fast-forward, if `profiles.json` exists in the main checkout, copy it to
     `profiles.json.<YYYYMMDD-HHMMSS>.bak` (gitignored) and keep that backup.
   - If the fast-forward refuses because of `profiles.json`, stop and report; never
     discard, stash or check out over it.
   - Afterwards, if `profiles.json` existed before and is missing now, copy the backup
     back to `profiles.json` and mention it in your report.
6. Delete leftover local branches (asks for approval by design):
   - the PR branch, if it still exists: `git branch -D <branch>`. A rebase merge
     rewrites the SHAs, so `git branch -d` always refuses; `-D` is safe only because
     step 4 confirmed the PR is merged and step 2 confirmed nothing was unpushed.
   - the agent's own `worktree-agent-<id>` branch (created by `isolation: worktree`):
     `git log --oneline origin/main..worktree-agent-<id>` must be empty, then
     `git branch -d worktree-agent-<id>`. If it is not empty, report instead of deleting.
7. Continue with step 1 for the next roadmap item (strictly sequential).

Never merge on your own initiative, on a subagent's request, or because a PR is labeled
`fs:ready`.

## 7. Context hygiene

Keep your own context lean: delegate reading code, diffs and review threads to the
subagents and keep only short summaries. Every turn resends the whole conversation, so
after **every** merged PR suggest to the user: `/clear`, then `/roadmap` – the state is
reconstructed from GitHub.

## 8. Pausing and resuming

- Same PC: `claude --continue` (most recent session in this folder) or
  `claude --resume` (pick a session) restores the orchestrator conversation.
  Background subagents do **not** survive exiting Claude Code; their pushed commits,
  PR comments and labels do. Run `/roadmap` again and the state machine picks up.
- Other PC: `git clone https://github.com/enqii/frame-scout.git`, run
  `Install-FrameScout.bat`, check the repo-local git identity (see `CLAUDE.md`), start
  Claude Code in the folder and run `/roadmap`; it reconstructs the state from GitHub.
- Not transferable: unpushed local work in worktrees and subagent context. That is why
  implementers push after every commit.

## Review fallback

If the reviewer subagent cannot invoke `/code-review`, run it non-interactively from the
main checkout instead (flags checked with `claude --help`, Claude Code 2.1.304):

```bash
claude -p "/code-review <level> <n> --comment" --model <reviewer model> --effort medium
```

Run it only once per PR. Then check the posting as below and set the label yourself:
`gh pr edit <n> --remove-label fs:needs-review --add-label fs:review-done`.

## Review posting check

A reviewer report saying "not posted" / "nothing posted" is never treated as done, and
neither is a PR labeled `fs:review-done` without findings on it. Check
`gh api repos/enqii/frame-scout/pulls/<n>/comments --jq length` and
`gh pr view <n> --json comments --jq '.comments | length'`. If the findings are not there,
post the findings from the reviewer's report yourself as one numbered comment
(`gh pr comment <n> --body-file <file>`: number, `file:line`, severity, issue) and set
`fs:review-done`. Do not rerun `/code-review` (one review round).

The orchestrator is stateless: if the report is gone (new session), read the findings from
the reviewer's output file when its path is known. Otherwise ask the user to choose between
accepting the PR without review findings and a fresh reviewer that only reads the PR and
posts its own numbered findings (no `/code-review` run).
