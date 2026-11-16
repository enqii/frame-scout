# FrameScout – Roadmap

Order of work. Each unchecked item is implemented in its own pull request, strictly one
after another (see the PR workflow in `CLAUDE.md` and the `/roadmap` skill). The open
items come first, in priority order; the next item is the first `- [ ]` line.
The list is a rolling window of about 10 open PRs at most, filled by `/triage` (see
`CLAUDE.md` → "Triage"); everything else stays in the backlog.
The items' IDs (E/A/I/F) are described in [docs/BACKLOG.md](BACKLOG.md) (open) and
[docs/BACKLOG-DONE.md](BACKLOG-DONE.md) (finished). Packages whose lines are all
done are in [docs/ROADMAP-DONE.md](ROADMAP-DONE.md).

## Open (priority order)

### P10 – Checks on the home PC (needs the user's hardware; before P4b)
- [x] (A) Run the CUDA path and the evaluation tool with real models and fix what shows up
      (I11, E34, E35; a PR "runtime-tested on the home PC") (done 2026-11-01 in PR #56: E34
      confirmed, E35 fixed; open follow-ups: I11 rest (fresh CUDA install, cu126, other GPUs),
      E32 labelling data, E47, E48, A39)
- [~] (B) Measure thread counts and YOLO batches on a real CPU and GPU (E17, E18; changing
      detection results is a hold point) – deferred 2026-11-02 by user: needs home PC hardware

### P44 – Simplify (added 2026-11-16)
- [x] Support Python 3.14 only: one CI job, no version fallbacks, shorter docs (I50; kind `code`)
      (done 2026-11-16 in PR #129)
- [x] Delete or shorten outdated documents: `docs/UI-REVIEW.md`, the closed ideas in
      `docs/IDEAS.md` (I51; kind `docs`; adapts the rule in `CLAUDE.md` → "Triage")
      (done 2026-11-16 in PR #130)

### P45 – Workflow (added 2026-11-16)
- [x] Subagents read their brief themselves instead of the orchestrator copying it (I49; kind `docs`)
      (done 2026-11-16 in PR #131)

### P46 – Interface follow-ups (added 2026-11-16)
- [x] Reasons for the other disabled run buttons (F37; kind `code`)
      (done 2026-11-16 in PR #133)
- [x] Hygiene bundle: pre-search count of partner photos, long captions, popover "More" closes,
      narrower popover "Export and copy" (A48, A51, F41, F43; kind `code`)
      (done 2026-11-16 in PR #134)
- [x] Second browser pass over the parts not looked at; findings become backlog items (A52; kind `docs`)
      (done 2026-11-16 in PR #135)

### P47 – Linux (WSL) (added 2026-11-16; private Python 3.14 like Windows, user decision)
- [x] `ubuntu-latest` in the CI matrix and fix what fails (F47 part 1; kind `code`)
      (done 2026-11-16 in PR #136)
- [x] `.sh` scripts for install, start, check and uninstall with a private Python 3.14 and its
      checksum (F47 part 2; kind `code-risky`; new download approved 2026-11-16)
      (done 2026-11-16 in PR #137)
- [ ] Linux driver minimums, uninstaller paths, platform-specific messages (F47 part 3; kind
      `code`; the run in WSL2 is F48, not scheduled)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
