# FrameScout – UI/UX review

A one-time assessment of the whole interface (the Streamlit app `app.py` and the HTML
galleries written by `framescout_engine.py`), made for backlog item F24 / roadmap P28.
It is a **proposal**: nothing was rebuilt, no code changed. The follow-ups are backlog items
(F27–F33) with options; the user decides which of them become roadmap PRs, and also decides
F19 (one-photo review mode) after reading this.

Basis: reading the code (`app.py` at about 2,000 lines, the gallery export in
`framescout_engine.py`), not a usability test with real users and not a visual check in a
browser. Judgements about "feels crowded" are therefore estimates from the element count and
order; a quick screenshot pass should come with the first rebuild PR.

## Constraints for every follow-up

- Keep the `setting_<name>` session keys and the rule that widgets get values only through
  `st.session_state` (`CLAUDE.md` → Gotchas); keep `settings.json`, `profiles.json`,
  `results.json` and `marks.json` unchanged unless an item says otherwise.
- General-purpose wording: no cosplay or photographer-specific labels. The legacy field
  `franchise` stays internal; the UI says "Context / origin".
- The CLI engine stays independent of the frontend; the HTML galleries stay standalone files
  (local thumbnails, no server, no network).
- A rebuild touches many screens at once and `app.py` is large (A46 plans a split, A47 asks for
  the framework decision before distribution). Order matters: restructure the code (A46)
  before or together with a layout rebuild, not after, and do not invest in styling while A47
  is open.

## What the interface consists of today

Four tabs: **Search profiles** (expander per profile with an edit form, a "New search profile"
form below), **Photo source** (folder list, photo count, and since F18 the "Analyze ahead"
section), **AI settings** (ten widgets, a hint box, "Check installation"), **Search & results**
(start/stop, status and log, quick search, quick results, profile results, copy, export,
"Clean up storage" with cache check). A result card in the app has: thumbnail, rank/score/crop
label, detail lines, closest search text (several texts), then the buttons Open, Folder, Find
similar and a three-state mark control. The HTML gallery is one static page per profile.

## Findings

Severity: **High** hurts the main flow, **Medium** costs time or clarity, **Low** polish.

### 1. Information hierarchy

- **High – "Search & results" is the whole second half of the app.** It holds seven unrelated
  jobs in one scroll: start/stop, progress and log, quick search with its own result gallery,
  the profile results, copy, export and storage maintenance. The page is long, the same words
  ("Open gallery in browser", "Open results folder", page selector) appear twice (quick and
  profile results), and a user who only wants to see results scrolls past the status area
  every time.
- **High – the results block starts with a wall of controls and notes.** Before the first
  photo come: a profile selector, one or two caption lines, up to three info boxes (other
  model, changed profile, missing profile), a caption about other profiles, three buttons,
  mark warnings, a "hide" checkbox, a progress caption, "Go to the first undecided photo", the
  page selector, a hidden-count caption and a caption explaining Open/Folder and marking. On a
  normal laptop screen the first thumbnail is likely below the fold. Most of it is only needed
  in exceptional states.
- **Medium – "Copy marked matches" and "Export" sit below the 48 cards of a page.** They act
  on the whole profile (all marks), not on the page, yet they are reached by scrolling past
  the grid, and the page selector exists only above the grid (no pager below, so going on
  after the last card means scrolling back up).
- **Medium – "Clean up storage" and the cache check are in the results tab.** They are
  maintenance and belong to neither "search" nor "results"; they are disabled during a run and
  rarely used.
- **Medium – "Analyze ahead" lives in "Photo source", its progress and Stop in "Search &
  results"** (already noted in the report of F18). The user starts a long job in one tab and
  must switch tabs to see it run.
- **Low – the page title and sub-line are fine, but nothing says what to do first.** The
  tab order implies profiles, folder, settings, run, but there is no cue which of these is
  still missing (see 4).

### 2. Actions per card

- **Medium – five controls per card** (Open, Folder, Find similar, three mark states) times 48
  cards: 240 widgets per page, each a Streamlit rerun target. Heavy for the browser and visually
  dense; "Open" and "Folder" are equal in weight to the mark control although marking is the
  main task.
- **Medium – the thumbnail itself is not clickable** (an `st.image`). In the HTML gallery it is
  a link to the original, so the two behave differently.
- **Medium – small thumbnails limit marking** (the reason for F19). Four columns of a wide
  layout give roughly 300 px images; subtle differences (a prop, a plate number) need the big
  picture. Options for F19 are in follow-up F31.
- **Low – button labels are terse** ("Open", "Folder"): the tooltip explains them, the label
  could read "Open photo" / "Show in folder".
- **Low – mark colours** are injected by a style block that rides in a caption (A38, A45); it
  works but is fragile against Streamlit updates and not checked in other browsers.

### 3. Tabs and sections

- **Medium – a flat settings tab.** Ten widgets in one list without grouping: model, device,
  batch size, priority, number of results are the everyday ones; person detection and its three
  sub-settings, and the reference weight are expert settings. The person sub-settings stay
  editable while person detection is off. A "Reset to defaults" sentence and a recommendation
  box close the tab.
- **Medium – the settings are spread over two tabs.** The photo folders are saved in the same
  `settings.json` but live in "Photo source"; "AI settings" says "The photo folders stay as
  they are" on its reset button. Honest, but a hint that the model of the split is unclear.
- **Medium – new profile form below the list.** With many profiles the "New search profile"
  form is far down; each profile is an expander holding a full form (four text fields, an
  uploader, a checkbox, two buttons).
- **Low – quick search is a second search mode in the run tab**, with its own results
  gallery. It is useful, but a first-time user cannot tell when to use it instead of a profile.

### 4. Guidance and state feedback

- **High – disabled controls do not say why.** While a search runs, nearly every widget in
  every tab is disabled; only the "Search & results" tab shows the running state. A user on
  "AI settings" sees greyed widgets and no explanation. A global status line near the title
  ("Search running – open Search & results") would remove this.
- **Medium – Start can be disabled for reasons shown in another tab** (no existing photo
  folder is a warning in "Photo source", a missing model package in "AI settings"); the
  start area shows only some of them.
- **Medium – long explanatory captions** (the "Analyze ahead" text is one 100-word block, the
  quick-search text and the AI settings notes are similar). They are accurate but dense; most
  could be a short sentence plus a "More" expander or help tooltip.
- **Low – the English-only search hint** is correct and required (E3) but a permanent info box
  on top of the profile tab, also for users who already read it.

### 5. Consistency between the app and the HTML gallery

| Aspect | App | HTML gallery |
|---|---|---|
| Card text | rank, caption, label, detail, closest text, relative path | rank, score, label, detail, closest text, file name link, relative path |
| Thumbnail click | nothing | opens the original |
| Marks | yes (three states) | not shown |
| Paging | 48 per page | the whole top N on one page |
| Theme | follows the Streamlit theme | fixed dark; ignores a light system theme |
| Navigation | profile selector | link row to the other profiles, no link back from a card |
| Explanatory text | repeated notes in captions | one paragraph on top |

- **Medium – marks are the heart of the review workflow but invisible in the gallery** that is
  meant to be shared or opened elsewhere. Showing them needs `marks.json` to be baked into the
  page at export time (stale afterwards) or read at open time (not possible for a static file
  without script and file access); this is a design decision, not an obvious fix.
- **Low – the gallery has no responsive text size, no light theme, no keyboard focus styling**
  and uses `#bbb` on `#292929` for small text (contrast is acceptable but small).
- **Low – the two result views are built from copied code** (`show_results` and
  `show_quick_results` draw the card the same way with small differences); a change to the card
  must be made twice, which is how inconsistencies creep in.

### 6. Accessibility and platform

- Mark state is shown by colour and by the label of the selected segment, so it is not
  colour-only. Image alt text exists in the gallery (the relative path).
- The app relies on Streamlit's own widgets, so keyboard handling is whatever Streamlit offers;
  there are no custom shortcuts (and none can be added without a new dependency, see F19).
- Emoji in the title is harmless; the Stop/Start labels use symbols (▶, ■) with text.

## What works well (keep)

- The clear separation of profile, source, settings and run for a first run.
- Honest wording about scores, the explicit state notes (changed profile, other model).
- The review progress line and "Go to the first undecided photo" (F20): a good model for
  compact, state-driven helpers.
- The fragments: card buttons rerun only the results part.
- Safety copy: copy-only, never overwrite; the delete confirmation with consequences.

## Design skills

Checked with `npx skills find` (search only, nothing installed; installing is a new
dependency and a hold point). Candidates:

| Skill | Source | Installs | Note |
|---|---|---|---|
| `improving-streamlit-design` | `streamlit/agent-skills` (the Streamlit organisation) | 3 | on topic, little used |
| `ui-ux-reviewer` | `arjenschwarz/agentic-coding` | 405 | generic UI review, unknown author |

Neither has a track record the `find-skills` guidance would call established, and their
contents were not read. Recommendation: do not install either for this review; if the user
decides on a Streamlit rebuild, look at the Streamlit one again then (it is by the framework's
authors) before the first rebuild PR.

## Proposed follow-ups

Each is a backlog item (F27–F33) with a status tag and size; none is started. Suggested
order if the user wants the rebuild in steps: F27 first (cheap, fixes the worst feedback gap),
then F28 and F29 together (the largest gain), then the rest.

| ID | Proposal | Options | Size |
|---|---|---|---|
| F27 | A global state line near the title and reasons for disabled controls | (a) one status line while a run is active; (b) also a "What is missing to start" line under the Start button | S |
| F28 | Split "Search & results" | (a) five tabs: profiles, source, settings, search, results; storage maintenance into settings; (b) keep four tabs, move quick search into its own expander and storage into settings; (c) leave | M |
| F29 | Compact results header and bottom actions | (a) a one-row toolbar (gallery, folder, download in a popover), exceptional-state notes collapsed; copy and export in an expander above the grid; a pager below the grid; (b) only the pager and the notes | M |
| F30 | Share the card drawing between profile and quick results | one `draw_card()` with options; simplification, no visible change except fewer inconsistencies | S |
| F31 | Where F19 (large preview) lives | (a) a "Review" toggle on the results tab, one photo at a time; (b) a dialog (`st.dialog`) opened from a card; (c) fewer, larger columns as a cheap substitute | S–M |
| F32 | Settings grouping | basic settings first, "Person detection" and "Reference weight" in an expander, sub-settings disabled while detection is off | S |
| F33 | HTML gallery parity | (a) light/dark by `prefers-color-scheme`, clickable "back to top", file name first; (b) also show marks (design decision, see above); (c) leave as a plain export | S–M |

## Open questions for the user

1. Is the goal a modest tidy-up (F27, F29(b), F30, F32) or a restructuring of the tabs (F28)?
2. Should the HTML gallery stay a plain export (F33(c)) or grow toward the app?
3. F19 first as a toggle or a dialog? (F31, depends on F29: a toolbar that is already compact
   leaves room for a mode switch.)
4. A47 (frontend framework) before any larger rebuild, or after?
