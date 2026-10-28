# Spawn & message templates

Role behaviour lives in `~/.claude/agents/wave-*.md`, so missions carry only the specifics: ≤40 lines, pointers to files, never pasted research or spec text. Fill `<…>`. `W` = `.wave/<slug>` (absolute path in real missions). Read-only roles are spawned **without** `name` (plain subagent; continue by agent ID); writers **with** `name` (teammate).

## Research (Phase 1) — all in ONE message, unnamed

```
Agent({ subagent_type: "wave-researcher", run_in_background: true,
  description: "Research <key> slice",
  prompt: `Repo <repo>. Slice: <key>. Answer as facts, do not propose designs.
Questions: 1) <how does X flow from A to B?> 2) <which files define Y?> 3) <what covers Z?>
Boundaries: read-only, paths <dirs>, ~25 tool calls. Out of scope: <neighbouring slices>.
Project rules that matter here (CLAUDE.md is not loaded): <3–5 rules>.
Already known (do not re-derive): <facts the lead verified>.
Write <W>/research/<key>.md.` })
```

## Critic (Phase 2c) — one, unnamed

```
Agent({ subagent_type: "wave-critic", run_in_background: true,
  description: "Critique spec <lens>",
  prompt: `Critique <W>/spec.md through the lens: <lens — what to attack>.
Research evidence: <W>/research/. Write <W>/reviews/critic-<lens>-r1.md.` })
```
Re-review (same critic, by agent ID — keeps its context):
```
SendMessage({ to: "<critic agent id>", message: `Round <n>. Diff: <W>/reviews/spec-delta-r<n>.diff (spec edited in place).
Check only that each earlier blocker is resolved and the diff adds none. Write <W>/reviews/critic-<lens>-r<n>.md.` })
```

## Foundation (Phase 3.1) — serial, one builder or the lead

```
Agent({ subagent_type: "wave-builder", name: "b-foundation", run_in_background: true,
  description: "Lock contracts and scaffold",
  prompt: `Foundation of wave "<slug>", stage <S1>. Spec: <W>/spec.md (Contracts, Stage plan).
Do, in order: (1) lock every shared type/interface/signature in <contracts file>;
(2) pre-split convergence points so slices never share a hotspot: <registries/route tables>;
(3) scaffold <new packages/dirs> with real files; (4) you are the ONLY installer: <exact install command>;
(5) gate scripts = CI commands, ≤20-line output: <commands>; (6) typecheck green: <command>.
Archive first only what git cannot restore: <paths or "none">. Do not implement slice logic.
Handoff: <W>/handoff/b-foundation.md.` })
```

## Builders (Phase 3.2) — the stage's batch in ONE message, named

```
Agent({ subagent_type: "wave-builder", name: "b-<slice>", run_in_background: true,
  description: "Build <slice> slice",
  prompt: `Wave "<slug>", stage <Sn>. BRIEF (binding): <W>/BRIEF.md. Read from the spec only: Contracts + "## <Sn>" + the ACs below.
You own: <paths> (BRIEF §2). Ports: <api>/<web>. Scratch: <scratch>/b-<slice>/. Inbox: <W>/inbox/b-<slice>.md.
Build: <what, 3–6 lines, referencing spec sections>.
ACs you own (user's words where they exist): <AC-ids + text + verify>.
Scoped checks: <typecheck/lint/test commands for your paths>.
Dependencies: <none | "needs X from b-y — do the rest first; if still missing, end with WAITING ON b-y: X">.
Handoff: <W>/handoff/b-<slice>.md (STATUS + EVIDENCE per AC).` })
```

## Auditor (Phase 3.5) — one per stage, unnamed

```
Agent({ subagent_type: "wave-auditor", run_in_background: true,
  description: "Audit stage <Sn>",
  prompt: `Audit wave "<slug>" stage <Sn>, lens: <spec conformance & rules | safety>.
Diff: git diff <BASE> -- <stage paths> (BASE in <W>/STATUS.md). ACs: <AC-ids> in <W>/spec.md.
Builders' evidence: <W>/handoff/<names>.md. Ownership for routing gaps: <W>/BRIEF.md §2. TREE CLEAN at <time>.
Ports if you must run anything: <ports>. Write <W>/audit/audit-<Sn>-r1.md.` })
```
Re-audit: `SendMessage({ to: "<auditor agent id>", message: "Gaps <ids> fixed (see inbox/_archive.md <times>). Re-audit only those + regressions in what the fixes touched. Write …-r<n>.md." })`

## Testing (2e, stage smoke, Phase 4) — see the acceptance-testing skill

Spawn templates for `test-designer`, `test-reviewer`, `test-executor` live in `~/.claude/skills/acceptance-testing/SKILL.md` (Roles) and its reference files. Wave-specific pointers to include in every test mission: `.wave/<slug>/spec.md` (ACs, stage plan), `ASKS.md`, STATUS keep-working list, BRIEF ports, `inbox/<owner>.md` for defects, run dir `.qa/<slug>/`.

## Routing a gap / failure to its owner

Live builder with a small context (rounds 1–2):
```
SendMessage({ to: "b-<slice>", message: `Gap <id> (<P0/P1>) from <audit file or gate>: <one line>. Evidence: <command → output, or file:line>.
Expected: <behaviour>. Fix the class of failure at the root, re-run <check>, update handoff EVIDENCE, report.` })
```
Otherwise (builder stopped, large context, or round 3) — fresh fix agent:
```
Agent({ subagent_type: "wave-builder", name: "b-<slice>-fix", run_in_background: true,
  description: "Fix <slice> audit gaps",
  prompt: `Fix gaps <ids> in <W>/audit/audit-<Sn>-r<n>.md for slice b-<slice>. BRIEF: <W>/BRIEF.md. Handoff: <W>/handoff/b-<slice>.md.
You own exactly b-<slice>'s paths. Verify current tree state (git diff -- <paths>) first. Root-cause each gap; re-run its check.
Handoff: <W>/handoff/b-<slice>.md (keep the same file, update STATUS + EVIDENCE).` })
```

## Resume after a dependency landed

```
SendMessage({ to: "b-<slice>", message: "<x> landed (<evidence>). Continue from your handoff note <W>/handoff/b-<slice>.md." })
```
Idle >5 min with a large context → use the Replacement template instead (the cache has expired).

## Replacement teammate (dead, silent after 2 nudges, bloated, or after a usage-limit reset)

```
Agent({ subagent_type: "wave-builder", name: "b-<slice>-2", run_in_background: true,
  description: "Resume <slice> slice",
  prompt: `You replace b-<slice> in wave "<slug>". Do not redo finished work.
Read in order: <W>/BRIEF.md, the spec's Contracts + "## <Sn>", <W>/handoff/b-<slice>.md, open items in <W>/inbox/b-<slice>.md.
Verify the tree state of your paths (git diff -- <paths>, scoped checks) before editing — the note may be stale.
You own exactly b-<slice>'s paths. Handoff: <W>/handoff/b-<slice>.md (keep updating the same file).` })
```
Update the STATUS roster: `b-<slice>` → replaced by `b-<slice>-2`.
