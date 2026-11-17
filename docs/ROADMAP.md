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

### P55 – Browser check of the interface (added 2026-11-17)
- [ ] Check the open parts of A52, A53 and A54 in a real browser: page change of the
      results, "Clean up storage" with entries, person crops, a long run, the state line at
      narrow widths (A58; kind `docs`)

### P56 – Simplify without losing a feature (added 2026-11-17)
- [ ] Remove the leftovers in `cleanup.py`, the quick search and `run_status.py`: no
      behavior change (F57 C, E, F; kind `code`)

### P57 – Remove the own uninstaller (added 2026-11-17)
- [ ] Remove `framescout_uninstall.py`, `framescout_core/uninstall.py`,
      `Uninstall-FrameScout.bat/.sh` and their tests; README and user guide say that
      uninstalling means deleting the folder, and what stays outside it (I57, F56 (2); kind
      `code-risky`; I19 is closed by it)

### P58 – Simplify the photo scan and the RAW fallback (added 2026-11-17)
- [ ] Remove the RAW fallback for truncated JPEGs and the path identities of the photo
      scan (F57 A, B; kind `code`)

### P59 – Drop the legacy names (added 2026-11-17)
- [ ] One migration with a backup, then remove `Gesamtbild`, `results/vorschaubilder/`,
      `LEGACY_PHOTO_FOLDER`, the profile field `franchise` and the CLI option `--character`
      (I43; kind `code-risky`; breaking: `profiles.json` schema and CLI, decided 2026-11-17)

### P4b – Search models (evaluate at home first; paused by user decision 2026-10-27)
- [ ] Evaluate the offered search models and trim the list (E32; the user labels a new
      pool at home, search quality is a hold point) (tooling done 2026-10-26 in PR #32;
      labelling, metrics and trimming remain)
- [ ] Optional multilingual CLIP model (`xlm-roberta-base-ViT-B-32`), built on the model
      choice of E22 (E21)
