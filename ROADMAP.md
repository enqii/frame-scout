# FrameScout – Roadmap

Order of work. Each unchecked item is implemented in its own pull request, strictly one
after another (see the PR workflow in `CLAUDE.md` and the `/roadmap` skill). The open
items come first, in priority order; the next item is the first `- [ ]` line.
The list is a rolling window of about 10 open PRs at most, filled by `/triage` (see
`CLAUDE.md` → "Triage"); everything else stays in the backlog.
The items' IDs (E/A/I/F) are described in [BACKLOG.md](BACKLOG.md) (open) and
[docs/BACKLOG-DONE.md](docs/BACKLOG-DONE.md) (finished). Packages whose lines are all
done are in [docs/ROADMAP-DONE.md](docs/ROADMAP-DONE.md).

## Open (priority order)

### P10 – Checks on the home PC (needs the user's hardware; before P4b)
- [x] (A) Run the CUDA path and the evaluation tool with real models and fix what shows up
      (I11, E34, E35; a PR "runtime-tested on the home PC") (done 2026-11-01 in PR #56: E34
      confirmed, E35 fixed; open follow-ups: I11 rest (fresh CUDA install, cu126, other GPUs),
      E32 labelling data, E47, E48, A39)
- [~] (B) Measure thread counts and YOLO batches on a real CPU and GPU (E17, E18; changing
      detection results is a hold point) – deferred 2026-11-02 by user: needs home PC hardware

### P15 – Orientation during runs (added 2026-11-03)
- [x] (A) Remaining-time estimate and a summary before the start (F12)
- [x] (B) "Check installation" self-test (F15)

### P16 – Hygiene (`minor` items bundled per area, added 2026-11-03)
- [x] (A) Evaluation tool: E36, E49, E51, I25 (done 2026-11-04 in PR #73)
- [x] (B) Engine and cache: E37, E39, E40, E44, E46, E50 (done 2026-11-04 in PR #74)
- [x] (C) App: A34, A38, A40, A41, A42, A43 (done 2026-11-04 in PR #77; A38 not verified in a browser, follow-up A45)
- [ ] (D) Installer: I4, I16

### P17 – Repository layout (added 2026-11-03)
- [ ] Scoring module outside the package (I30)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
