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

### P29 – Detector weights (added 2026-11-12)
- [x] Log which detector weights file was loaded (E60)

### P30 – Mark colors (added 2026-11-13)
- [x] The mark colors apply again with the pinned Streamlit, checked in a browser (A49)

### P31 – Split `app.py` (added 2026-11-13)
- [x] Move the areas of `app.py` into modules without changing behavior, before the UI
      rebuild (A46) (2026-11-13)

### P32 – Run state (added 2026-11-13)
- [x] A state line next to the title and what a search still needs at the Start button (F27) (2026-11-14)

### P33 – Tabs and settings (added 2026-11-13)
- [x] (A) Five tabs: results on their own, storage maintenance in the settings, "Analyze
      ahead" in the search tab (F28) (2026-11-14)
- [x] (B) Group the AI settings (F32) (2026-11-14)

### P34 – Quick search in the results view (added 2026-11-13)
- [x] The result of a quick search or "Find similar" is an entry of the results selector
      (F34) (2026-11-14)

### P35 – Result card (added 2026-11-13)
- [ ] One card for both views: equal cells, "Match"/"No" as the main buttons, the other
      actions in a popover, a visible mark state, full window width (F30)

### P36 – Results toolbar (added 2026-11-13)
- [ ] One toolbar row above the photos, a pager below the grid, copy and export in a
      popover (F29)

### P37 – Review dialog (added 2026-11-13)
- [ ] One photo at a time with a large preview in a dialog (F19)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
