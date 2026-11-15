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

### P38 – Shrink the backlog archive (added 2026-11-15)
- [x] Reduce `docs/BACKLOG-DONE.md` to one line per ID and adapt the "moved with its report"
      rule (I40; kind `docs`) (done 2026-11-15 in PR #118)

### P39 – Shrink the architecture document (added 2026-11-15)
- [x] Cut `docs/ARCHITECTURE.md` to what the code cannot say (I39; kind `docs`)
      (done 2026-11-15 in PR #119)

### P40 – Rules against unneeded complexity (added 2026-11-15)
- [ ] Introduce the rules (a)–(e) in `CLAUDE.md`, the reviewer brief and the PR template (I47;
      kind `docs`)

### P41 – Lighter PR workflow (added 2026-11-15)
- [ ] Fold the docs step into the implementer, reduce the labels, shorten the workflow texts
      (I41; kind `docs`; workflow rule change, decided 2026-11-15)

### P42 – Mixed-versions guard (added 2026-11-15)
- [ ] Replace the guard by one version file checked by the installer and the start script
      (I42; kind `code-risky`; decided 2026-11-15)

### P43 – Package structure (added 2026-11-15)
- [ ] Flatten `framescout_core/__init__.py` and the `framescout_scoring` package (I45; after P42)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
