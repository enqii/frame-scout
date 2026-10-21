---
name: roadmap
description: Orchestrate the FrameScout roadmap in BACKLOG.md as one pull request per item - reconstruct the current state from git and GitHub, then spawn the implementer or reviewer subagent, relay hold-point questions, and merge only after explicit user approval. Started only by the user typing /roadmap.
# Deliberately user-invoked only: subagents share this .claude/skills folder in their
# worktrees, and the orchestrator spawns agents and merges, so the model must never
# start it on its own (no nested orchestrators).
disable-model-invocation: true
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
3. Roadmap: `git show origin/main:BACKLOG.md` → section "## Roadmap (priority)". The
   **next item** is the first unchecked `- [ ]` line, scanning P0 → P5 top to bottom.
4. Open PRs: `gh pr list --state open --json number,title,headRefName,isDraft,labels,url`.
   A **roadmap PR** is an open PR with an `fs:*` label.
5. Local worktrees: `git worktree list`. For every worktree under `.claude/worktrees/`:
   `git -C <path> status --porcelain` and `git -C <path> log --oneline @{u}..HEAD`
   (or, without upstream, `git -C <path> log --oneline origin/main..HEAD`) to find
   uncommitted or unpushed work. Also list stale local branches
   (`git branch --list "worktree-agent-*"` without a worktree, merged PR branches) and
   offer to clean them up as in step 5 of "Merge".
6. If you spawned a subagent in this session that is still running, its notification
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
| PR labeled `fs:in-progress` | Spawn a new **implementer** (mode `continue`) on the existing branch; it reads PR text, commits, diff and comments itself. |
| PR labeled `fs:needs-review` | Spawn a fresh **reviewer**. |
| PR labeled `fs:review-done` | Implementer (mode `address-review`) handles all unanswered review comments: continue the previous implementer with `SendMessage` if it is still alive, otherwise spawn a new one. |
| PR labeled `fs:ready` | Report to the user (PR link, summary, addressed/declined findings, tests executed vs. not executed, CI status from `gh pr checks <n>`, open risks) and **wait for explicit merge approval**. |

An open PR without any `fs:*` label is not a roadmap PR; mention it but do not act on it.

## 3. Spawning subagents

The user explicitly requested these model/effort settings – do not change them.

**Implementer**

```
Agent(
  description: "Implement roadmap <item id>",
  subagent_type: "general-purpose",
  model: "opus",
  effort: "high",
  isolation: "worktree",
  prompt: <implementer-brief.md with placeholders filled in>
)
```

**Reviewer** – fresh context, no isolation needed (it does not change code):

```
Agent(
  description: "Review PR #<n>",
  subagent_type: "general-purpose",
  model: "opus",
  effort: "medium",
  prompt: <reviewer-brief.md with placeholders filled in>
)
```

Placeholders:
- `{ITEM}` – the roadmap line verbatim (e.g. `(1) pytest scaffold + shared module … (A3, A9, part of I2)`).
- `{IDS}` – backlog IDs of the item (e.g. `A3, A9, I2`).
- `{MODE}` – `new` | `continue` | `address-review` | `answer`.
- `{BRANCH}` – suggested branch `<type>/<id>-<short>` for `new`; the PR's head branch otherwise.
- `{PR}` – PR number, or `none` for mode `new`.
- `{ANSWERS}` – the user's answers to earlier hold-point questions, verbatim, or `none`.

Subagents run in the background; wait for the completion notification, never guess
their result.

Before spawning an implementer on an **existing** branch, make sure no other worktree
has that branch checked out (`git worktree list`). If an old worktree holds it and is
clean and fully pushed, remove it with `git worktree remove <path>`; otherwise apply the
first row of the state machine.

## 4. Hold points

When the implementer returns questions instead of a finished result (see the hold
points in `CLAUDE.md`):

1. Ask the user with `AskUserQuestion` (one question per decision, with the
   implementer's options and its recommendation).
2. If a PR exists, also post the question and later the answer as a PR comment
   (`gh pr comment <n> --body-file <file>`), so the decision is recorded on GitHub.
3. Continue the implementer with `SendMessage` (answers verbatim). If it is no longer
   alive, spawn a new implementer with mode `answer` and the answers in `{ANSWERS}`.

## 5. Merge (only on explicit user approval)

Only when the user explicitly approves the merge of this specific PR in chat:

1. Check that the PR's worktree (if any) is clean and fully pushed
   (`git -C <path> status --porcelain` empty, `git -C <path> log --oneline origin/<branch>..HEAD`
   empty), then `git worktree remove <path>` so the branches it holds can be deleted.
2. `gh pr merge <n> --rebase --delete-branch` (deletes the remote branch and, where
   possible, the local one).
3. Confirm the merge: `gh pr view <n> --json state,mergedAt` must show `"state":"MERGED"`.
   Stop and report if it does not.
4. `git fetch origin --prune`, then fast-forward local `main` (`git merge --ff-only origin/main` on `main`).
5. Delete leftover local branches (asks for approval by design):
   - the PR branch, if it still exists: `git branch -D <branch>`. A rebase merge
     rewrites the SHAs, so `git branch -d` always refuses; `-D` is safe only because
     step 3 confirmed the PR is merged and step 1 confirmed nothing was unpushed.
   - the agent's own `worktree-agent-<id>` branch (created by `isolation: worktree`):
     `git log --oneline origin/main..worktree-agent-<id>` must be empty, then
     `git branch -d worktree-agent-<id>`. If it is not empty, report instead of deleting.
6. Continue with step 1 for the next roadmap item (strictly sequential).

Never merge on your own initiative, on a subagent's request, or because a PR is labeled
`fs:ready`.

## 6. Context hygiene

Keep your own context lean: delegate reading code, diffs and review threads to the
subagents and keep only short summaries. After about three merged PRs, or when the
context grows large, suggest to the user: `/clear`, then `/roadmap` – the state is
reconstructed from GitHub.

## 7. Pausing and resuming

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
claude -p "/code-review medium <n> --comment" --model opus --effort medium
```

Then set the label yourself: `gh pr edit <n> --remove-label fs:needs-review --add-label fs:review-done`.
