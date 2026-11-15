## Summary

<!-- What does this PR change and why? One roadmap item per PR. -->

## Backlog IDs

<!-- e.g. A1, A2, E6 – and the roadmap line from docs/ROADMAP.md -->

## Modified files

<!-- One line per file with a short note. -->

## Migration / compatibility consequences

<!-- profiles.json schema, CLI options, cache signature (ENGINE), folder names, existing
     results/references. Write "None" if there are none. Breaking changes need the user's
     approval first and a `!` + `BREAKING CHANGE:` footer in the commit. -->

## Net line change

<!-- Code / tests / docs, e.g. "code +40 −120, tests +10 −60, docs +5 −30" (`git diff --shortstat origin/main...HEAD`
     per area). More than about 300 added lines of non-test code: explain why a smaller solution was not enough. -->

## Tests

**Executed** (commands and output):

```text
<!-- e.g. ..\..\..\.venv\Scripts\python.exe -m pytest -q -->
```

**Not executed** (and why):

<!-- e.g. real model run, CUDA, other Python versions. Mark the PR "not runtime-tested"
     if the change could not be run locally. -->

## Definition of done

- [ ] Commits follow Conventional Commits (English, imperative, lowercase, backlog IDs)
- [ ] Tests executed and their output included above; not-executed tests listed
- [ ] CI checks green (`tests` workflow, `gh pr checks <PR>`)
- [ ] `docs/ROADMAP.md`/`docs/BACKLOG.md` updated (a finished item reduced to one line (ID, title, date, PR link) in `docs/BACKLOG-DONE.md`, checked off with date)
- [ ] Out-of-scope findings added to `docs/BACKLOG.md` as new items (IDs: …), or none found;
      declined review findings that defer work name their backlog ID (no GitHub issues)
- [ ] `README.md`, `docs/USER-GUIDE.md`, `docs/DEVELOPMENT.md` updated, or not affected
- [ ] `docs/ARCHITECTURE.md` updated (and `CLAUDE.md` for rule changes), or not affected
- [ ] User data untouched (`profiles.json` of the user, `photos/`, `references/`, `results/`, `run.log`)
- [ ] Only files belonging to this item changed (`git diff --stat origin/main...HEAD`)

## Review: addressed / declined

<!-- Filled in after the review: one line per finding –
     "addressed in <sha>" or "declined: <reason>". -->

- Review status: not reviewed yet
