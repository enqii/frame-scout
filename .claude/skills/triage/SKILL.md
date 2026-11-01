---
name: triage
description: Triage FrameScout's open work with the user - sort the feature ideas of docs/IDEAS.md and the open items of BACKLOG.md into the roadmap, tag the rest, and record the decisions in one docs-only pull request. Started only by the user typing /triage.
# User-invoked only: the user decides every line, and the skill edits the planning files.
disable-model-invocation: true
model: sonnet
---

# /triage – from idea to backlog to roadmap

You run the triage **together with the user**, in chat. You propose, the user decides;
you never move an item on your own. The result is one docs-only pull request.

The pipeline (rules: `CLAUDE.md` → "Triage"):

1. **Idea** (`docs/IDEAS.md`) → *take over* (becomes a backlog item), *discard* or *park*.
2. **Backlog** (`BACKLOG.md`) → every open item carries one status tag.
3. **Roadmap** (`ROADMAP.md`) → themed packages, one PR each. A rolling window of
   **about 10 open PRs at most**; it is not a second backlog.

## 1. Read the state

From the main checkout (`git fetch origin --prune`; fast-forward `main` if clean):

1. `ROADMAP.md` – count the open `- [ ]` PRs (the window has room for 10 minus that).
2. `BACKLOG.md` – every open item with its tag (untagged = not yet triaged).
3. `docs/IDEAS.md` – ideas without a `Disposition:` line.
4. Search `docs/BACKLOG-DONE.md` for the keywords of each idea (an idea may already be
   done or a duplicate; name the closest existing item).

Do not read `docs/BACKLOG-DONE.md` whole. Do not read code, except to answer a concrete
question about an item (search first).

## 2. Propose (one table, then discuss)

Show the user, in German, a compact proposal:

- **Ideas:** per idea a recommendation (take over / discard / park), its size (S/M/L)
  and hold point from the idea text.
- **Untagged or re-assessable backlog items:** a tag each (below).
- **Roadmap candidates:** the items that should enter the roadmap, **grouped into themed
  packages** (like P6/P8/P9: one PR per line, related IDs together, `minor` items bundled
  per area), in priority order, with the resulting number of open PRs.
- **Cleanup:** duplicates, items that can be closed, items to merge.

Priority for the roadmap, in this order:
1. Protection of user data.
2. Helps every user at low effort.
3. Unblocks other items, or belongs to one theme with them.
4. Hold-point items only when the decision is made (ask it in this triage with
   `AskUserQuestion`); otherwise tag `decision`.
5. `hardware` items form one block that runs on the home PC.

If the window would exceed 10 open PRs, propose what waits (tag `parked` or leave in
the backlog) instead of exceeding it.

Status tags (written in bold after the checkbox, `- [ ] \`tag\` **E15 – …**`):

| Tag | Meaning |
|---|---|
| `ready` | clear scope, can be implemented now |
| `decision` | needs a user decision first (hold point); name the question |
| `hardware` | needs the home PC (GPU, real models, timings) |
| `minor` | small, rare or cosmetic; bundled into a hygiene PR when it enters the roadmap |
| `parked` | deliberately not planned now; give the reason |

Ask the user with `AskUserQuestion` for every real decision (one question per decision,
your recommendation first). Do not ask about things the rules already settle.

## 3. Apply the decisions (one docs-only PR)

After the user has agreed to the plan:

1. Branch `chore/triage-<YYYYMMDD>` from `origin/main`
   (`git switch --no-track -c …`), repo-local git identity (see `CLAUDE.md`).
2. `docs/IDEAS.md`: add one line `Disposition: <take over → F<n> | discarded: <reason> |
   parked: <reason>> (<date>)` under the idea's heading. Nothing else of earlier sections
   is edited.
3. `BACKLOG.md`: new items for taken-over ideas in group **F** (next free number: search
   both backlog files), with the text of the idea reduced to problem, sketch, affected
   files, risks and hold point; the status tag on every triaged item; closed duplicates
   are removed and mentioned in the PR.
4. `ROADMAP.md`: new themed packages under "Open (priority order)" in the agreed order,
   each line naming its backlog IDs and the date (`added <date>`); keep the numbering
   scheme (`P<n>`).
5. Check the links and IDs: every ID named in `ROADMAP.md` exists in `BACKLOG.md` or
   `docs/BACKLOG-DONE.md`.
6. Commits: Conventional Commits, e.g. `docs(backlog): triage … (F1–F4)`, pushed after
   each commit (`git push -u origin chore/triage-<date>`). Stage files by name.
7. Open a **non-draft PR** with the template `.github/pull_request_template.md`
   (tests: "not applicable, Markdown only"). It is **not a roadmap PR**: no `fs:*`
   label and no review round, because the user decided every line in chat. Add the
   summary of decisions as a table (ID, decision, tag/roadmap package).
8. Wait for green CI (`gh pr checks <n>`), report to the user and **merge only after
   explicit approval** (`gh pr merge <n> --rebase --delete-branch --match-head-commit
   <headRefOid>`; follow `/roadmap` → "Merge" for the cleanup).

## 4. Rules

- The user's decision always wins; never re-litigate an earlier one.
- Never edit `CLAUDE.md` hold points or the PR workflow from here; propose a separate PR.
- Never create GitHub issues; `BACKLOG.md` is the single source of open work.
- Keep your context lean: this skill needs `ROADMAP.md`, `BACKLOG.md` and `docs/IDEAS.md`
  and nothing else. After the merge suggest `/clear`, then `/roadmap`.
