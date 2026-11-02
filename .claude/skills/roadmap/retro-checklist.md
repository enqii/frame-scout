# Retrospective checklist (read only when `/roadmap` section 7 runs)

Goal: find cheap improvements to the workflow, not to the product code. Report only what
you can point to. If a signal is not available to you, say so instead of guessing.

## Signals you can read (the orchestrator is stateless)

- PR: `gh pr view <n> --json commits,labels,comments,reviews,additions,deletions,changedFiles`
  and `gh api repos/enqii/frame-scout/pulls/<n>/comments --jq length`.
- Number of commits vs. atomic units of work; fixup or "review" commits; review findings
  accepted vs. declined (reply threads).
- Which fallbacks or hold points fired (review fallback, posting check, CI failure,
  `profiles.json` guard, worktree cleanup problems).
- The subagent reports in this session (what they said they struggled with, repeated
  reads, retries, tool denials, permission prompts).
- The user's messages in this session: every correction, manual step or "no, do it like
  this" is a candidate.

## Areas

1. **Manual interventions:** anything the user had to do or fix by hand; permission
   prompts that a safe allow rule could remove.
2. **Flow:** steps that waited, repeated or were skipped; wrong state-machine decision;
   avoidable round trips between agents.
3. **Unnecessary activity:** work nobody used (long reports, duplicate reads, reviews of
   trivial PRs, docs steps with nothing to do).
4. **Context and usage:** large outputs that entered the orchestrator context; briefs
   that are longer than needed; things that should be delegated or summarized. Estimate
   only; mark it as a guess.
5. **Performance and cost:** slow commands (CI waits, polling), model choice per kind that
   looks too big or too small for what it did. Estimate only; mark it as a guess.
6. **Quality of results:** defects found late (in review or after merge) that an earlier
   phase or the brief could have caught.
7. **Docs and rules:** a rule in `CLAUDE.md`, the skill or the briefs that was unclear,
   contradictory or ignored.

## Output rules

- At most 5 bullets: observation → evidence → proposed change → effort (S/M/L).
- Prefer removing or shortening instructions over adding new ones; a proposal that adds
  text must say what it replaces or why the cost is worth it.
- No proposals that weaken the hold points, user data protection or the merge approval.
