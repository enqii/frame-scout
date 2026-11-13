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

### P23 – Workflow fixes (added 2026-11-12)
- [x] Reviewer verifies its findings are on the PR before the label swap; agent worktrees no
      longer block the user's manual test (I37, I38; kind `docs`)

### P24 – Hygiene: engine and core (added 2026-11-12)
- [x] A truncated HEIC/AVIF fails instead of becoming a black image; the quick search counts
      partners and the app's count consistently (E59, E61; done 2026-11-12, PR #96)

### P25 – Results view (added 2026-11-12)
- [x] (A) Review progress per profile and "jump to the first open photo" (F20; done
      2026-11-12, PR #98)
- [x] (B) Show which search text matched a result (F17; kind `code-risky`; done
      2026-11-12, PR #99)

### P26 – Analyze ahead (added 2026-11-12)
- [x] "Analyze photos now" and `--analyze-only` without a search (F18; done 2026-11-13, PR #100)

### P27 – Start (added 2026-11-12)
- [x] Start handles a busy port and an already running app (F22; done 2026-11-13, PR #101)

### P28 – UI/UX review (added 2026-11-12)
- [ ] Assess the whole user interface and write the findings down, no rebuild; follow-up PRs
      are decided afterwards (F24; kind `docs`)

### P29 – Detector weights (added 2026-11-12)
- [ ] Log which detector weights file was loaded (E60)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
