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

### P48 – Workflow and tests (added 2026-11-17)
- [x] State machine row for a review with 0 findings in the `/roadmap` skill (I52; kind `docs`) – 2026-11-17
- [x] Fix the cleanup test that fails when the temporary folder is a mount point (I53; kind `code`) – 2026-11-17

### P49 – Simplify the rare-case handling (added 2026-11-17)
- [x] List per module (`cleanup.py`, `uninstall.py`, `install_check.py`, `disk_space.py`) what
      defensive handling would go; the user decides the removal afterwards (I44 step 1; kind `docs`) – 2026-11-17

### P50 – Interface follow-ups 2 (added 2026-11-17)
- [ ] Hygiene bundle: notices of "Export and copy" behind the popover, dangling " · " in a
      profile title, result cards in a narrow window, height of the "More" button
      (A55, A56, A57, A59; kind `code`)
- [ ] Tooltips that stay open and the squeezed header at 680–1100 px (A53, A54; kind `code`)

### P51 – Excel-friendly CSV (added 2026-11-17)
- [ ] "Separator: comma / semicolon" choice for the result export (F9; kind `code`)

### P52 – Score distribution (added 2026-11-17)
- [ ] Collapsed score histogram per profile with an additive `results.json` field (F53; kind
      `code`; the caption says scores are relative heuristics)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
