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

### P11 – Safety of marks and cache (added 2026-11-02)
- [x] Backup of `marks.json` with a restore offer, and a cache health check (F1)
      (done 2026-11-02 in PR #60; follow-ups E50, A40)

### P12 – Lighter runs (added 2026-11-02)
- [x] (A) No person detector load when nothing needs analysis (F2)
      (done 2026-11-02 in PR #62)
- [x] (B) Free disk space check before installing and searching (F3)
      (done 2026-11-02 in PR #64; follow-ups I33, E51)
- [x] (C) "Keep the PC responsive" option, measured together with P10 (B) (F4)
      (done 2026-11-02 in PR #65; the effect is not measured yet: follow-up E52, with E17)

### P13 – Export (added 2026-11-02)
- [x] Export a result list as CSV / file list (F5)
      (done 2026-11-03 in PR #67; follow-ups A41, A42)

### P14 – Hygiene (`minor` items bundled per area, added 2026-11-02)
- [x] (A) Evaluation tool and workflow: E47, E48, I13, I28, I29
      (done 2026-11-03 in PR #68)
- [x] (B) App: A31, A32, A37, A39
      (done 2026-11-03 in PR #69)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)

### P4 – UX (deferred)
- [~] (C) ZIP export with thumbnails (open decision: A18) – deferred by user decision
      2026-10-25, skipped by `/roadmap`
