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

### P18 – Repository layout, step 2 (added 2026-11-06)
- [x] Group the loose root files into `requirements/`, `assets/` and `docs/`, update every
      path in installer, CI, tests, skills and docs (I31; kind `code-risky`)

### P19 – Hygiene (`minor` items bundled per area, added 2026-11-06)
- [ ] (A) Engine: E53, E54, E56, E57
- [ ] (B) App: A44, F16
- [ ] (C) Installer: I34, I35, I36 (kind `code-risky`)

### P20 – Cache variables (added 2026-11-06)
- [ ] The app and the CLI honour cache variables the user set; the engine sets its defaults
      in `main()`, not on import; a `yolo11n.pt` in the working folder wins (E41, E42, A36;
      kind `code-risky`)

### P21 – Quick search (added 2026-11-06)
- [ ] Quick search over the analyzed photos without a profile, result in `results/quick/` (F10)

### P22 – Find similar (added 2026-11-06)
- [ ] "Find similar" from a result card, builds on P21 (F11)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
