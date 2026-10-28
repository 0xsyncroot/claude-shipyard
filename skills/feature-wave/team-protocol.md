# Team protocol — how the lead runs the build

Distilled from real team runs (7 projects; 560 subagents across 13 waves, 2026-09/10). Every rule exists because its absence cost a run.

## Contents
- Durable state
- Spawning (named vs unnamed, model, worktrees)
- Stage loop
- The lead event loop
- Coordination files (inbox, handoff)
- Shared tree & shared runtime
- Ports, processes, waiting
- Verifying claims
- Cost levers

## Durable state

Everything that must survive compaction, a usage limit or a new session lives in `.wave/<slug>/` (created by `scripts/wave-init.sh`):

| File | Owner | Purpose |
|---|---|---|
| `STATUS.md` | lead | Ledger: tier, BASE, baseline, commit policy, keep-working list, stage log, roster (name · role · model · owns · state · handoff), AC board, open decisions. **Update after every phase event.** First thing to read on resume. |
| `ASKS.md` | lead | The user's asks/issues/added tasks verbatim with IDs, status, evidence. The final report follows it. |
| `spec.md` (+ `spec.r<n>.md`) | lead | Ratified design: stage plan, ACs, decisions with provenance, change log. |
| `BRIEF.md` | lead | Binding team rules: ownership, private ports/scratch, scoped checks, lead decisions, done definition. |
| `research/<key>.md` | researcher | Facts with `file:line`. |
| `reviews/` | critic | `critic-<lens>-r<n>.md`, `spec-delta-r<n>.diff`. |
| `audit/` | auditor | `audit-<stage>-r<n>.md`: AC table + routed gaps + verdict. |
| `inbox/<owner>.md` | everyone appends | Open requests TO that owner. Resolved items move to `inbox/_archive.md` at stage end. |
| `handoff/<name>.md` | each teammate | ≤60 lines, updated before every run ends: STATUS · done · open · next · files · EVIDENCE. |

The lead works from these files, not chat memory. Notifications can be summarized away by compaction; the files cannot.

## Spawning

- **Read-only roles unnamed, writers named.** `wave-researcher`, `wave-critic`, `wave-auditor`: Agent call **without** `name` → plain background subagent; its final report arrives as a notification; continue it with `SendMessage` to the agent ID; it honours `omitClaudeMd`. `wave-builder`, `test-designer`, `test-executor`: Agent call **with** a unique short `name` (`b-api`, `b-web`, `td-<slug>`, `tx-web`) → teammate addressable by name. A replacement is `<name>-2`; a fix agent `<name>-fix`.
- All agents of a batch in ONE assistant message; always `run_in_background: true` and a 3–5 word `description`.
- **Model:** researchers `sonnet` (definition default). Builders, critics, auditors and test agents run the session model (the user's choice, 2026-10-23). Write each batch's models into STATUS.
- Teammates cannot spawn agents (the `wave-*` types disallow Agent/Workflow). Fan-out is always the lead's.
- **Worktrees** only when two live slices must mutate the same files, or for a parallel stage run apart from main. Pitfalls: `isolation` on the call turns a named teammate into a plain subagent; a worktree branches from the default branch, so uncommitted foundation work is invisible unless `worktree.baseRef: "head"` or the foundation is committed (needs the commit policy); a worktree is a fresh checkout (re-install deps, copy `.env`); ports, databases and caches are NOT isolated. Pattern that worked: builder in worktree → `patches/<slice>.patch` → lead applies on an integration tree, resolves conflicts, runs the gate.

## Stage loop

Each stage of the spec runs: foundation (if contracts are new or changed) → builders → gate → audit on the diff → smoke → stage close. Keep a stage small enough that its builders finish within their context budget; split it rather than run builders for hundreds of turns. One stage's audit/smoke may overlap with the next stage's build only when their files are disjoint.

Stage close: commit per policy · move resolved inbox items to `_archive.md` · STATUS stage log + AC board · ASKS statuses · 3-line user update (done + evidence · next · ETA) · stop the stage's agents.

## The lead event loop

Teammates finish asynchronously; each completion or idle state arrives as a notification that wakes the lead. **Never ScheduleWakeup, sleep, Monitor-poll or "check back later" for teammates.**

On each notification:
1. **Idle notice without a new result** (40–75% of past traffic) → no reply. If its work is verified and nothing is pending for it, `TaskStop` it now.
2. **Report** → read its EVIDENCE in the handoff; re-run the one decisive command; then record it in STATUS. A report without EVIDENCE is not done.
3. **Inbox** → read `inbox/lead.md`: rule, apply lead-only ops, append `RESOLVED by lead: …`. Items between teammates need no relay unless one is WAITING.
4. **WAITING ON <x>** → note it; when x lands, `SendMessage` the waiting teammate: "<x> landed at <evidence>; continue from your handoff note." If it has been idle >5 min with a large context, respawn it from its handoff instead (cache expired; waking it rewrites the whole prefix).
5. **Bottleneck** (several teammates waiting on one owner's file) → transfer or split ownership; record in BRIEF §2.
6. **Truncated result** → read its handoff/report file, or ask for the rest once.

Stall watchdog (a wake-up on a condition, not a timer): when every teammate has gone quiet and you would otherwise end your turn with nothing pending, start ONE background shell that exits only when no owned file has changed for 15 min, e.g. `run_in_background: bash -c 'while find <owned paths> -type f -mmin -15 | grep -q .; do sleep 60; done; echo STALL'`. Its exit wakes you → read handoff notes and processes of the quiet teammates → nudge or replace.

A teammate idle **without a result you have seen** → one `SendMessage`: "send your final report" before assuming failure.

The user may write mid-run: answer yourself. New asks → ASKS.md, then the current stage or the backlog. Never forward them to teammates as missions (a mid-run question once made 7 builders abandon their work).

Messaging discipline:
- Put tasks in files (BRIEF, spec, inbox) and send short pointers. Batch everything for one teammate into one message.
- A message that changes a mission starts with `CHANGE MISSION:`; a halt with `STOP:`. Anything else is info.
- Before resuming or spawning, reconcile STATUS roster + `ListAgents` + handoff notes; never spawn a second copy of a live teammate, never re-spawn a slice whose handoff says `STATUS: DONE` with green evidence.

## Coordination files

- **Inbox:** `inbox/<owner>.md`, append-only: `## <ISO-time> FROM <name> — <title>` then problem · evidence (command + output) · exact diff. The owner reads only its own inbox at every milestone and appends `RESOLVED by <name>: …`. Nobody edits another owner's file directly. (A shared requests.md grew to 326KB and every teammate kept re-reading it.)
- **Handoff:** `handoff/<name>.md`, ≤60 lines, rewritten before every run ends:
  ```
  STATUS: DONE | WAITING ON <who/what> | BLOCKED <why> | IN PROGRESS
  Done: …   Open: …   Next: …   Files: …
  EVIDENCE:
  - AC-3: `<command>` → exit 0; <≤10 lines of output or DOM/HTTP excerpt>
  ```
  It is the resume contract: a replacement must be able to continue from the note alone.
- Grants: the lead records any one-off permission to edit another owner's file in BRIEF §2.
- Timestamps from `date -u +%Y-%m-%dT%H:%M:%SZ` only.

## Shared tree & shared runtime (the #1 failure source)

- Half-finished edits turn everyone's typecheck red. Rule: typecheck-clean after every edit batch; scoped checks only while others edit; big refactors in `<scratch>/<name>/`, landed in one step.
- Gate scripts are the CI commands (format checks included) and print ≤20 lines; full logs go to a file.
- The lead declares `TREE CLEAN` (full typecheck + lint + tests on the merged tree) before audit, QA lanes or commits.
- **Lead-only operations:** dependency install / lockfile, migrations & schema applies (with the restart they need; expand → contract), root configs, `CLAUDE.md`, restarting shared services, git commit/stash/reset/checkout/clean/apply. One installer per wave (the foundation).
- No lead temp files inside typechecked paths — use scratch. No production build into a directory a running dev server uses (`.next`, `dist`).

## Ports, processes, waiting

- BRIEF §4 assigns each teammate a private port block and scratch dir; check `ss -ltnp` first. Selftests must bind their own port and fail if it is taken — a test once passed against a squatter process.
- Everything that can hang runs under `timeout` or in the background with a completion notification. Dev servers are background processes with a known PID.
- Wait on a background run with `tail -f <log> | grep -m1 '<final summary line>'` — never `while pgrep -f <pattern>` or `pkill -f <pattern>` where your own command line contains the pattern (it matches itself: never exits / kills its own shell, exit 144).
- Kill whole trees: by PID group, or `pkill -9 -f <string unique to that run>`. Killing a `pnpm` wrapper leaves children alive.
- Log silence ≠ hang: grep the test for `setTimeout`/budget tables before killing.
- Leave nothing running at the end of a run (teammates) or the wave (lead: check the BRIEF ports).

## Verifying claims

- "Done" reports have been false (a web teammate reported all asks done; screenshots showed every ask still broken). Done = EVIDENCE in the handoff + the lead's re-run of the decisive check; for UI one real-click pass per P0 AC (headless Playwright against a fresh build, real DOM).
- Smoke before sweep: one run per P0 AC with the user's scenario; repeat runs, `--repeat-each` or full lanes only once the smoke is clean. Tell the user the ETA before anything >30 min.
- Re-check the keep-working list items a stage touched; regressions against old behaviour were the user's most frequent complaint.
- No report after **2 nudges** → replace from the handoff note or do the slice yourself.
- Oracles must not contain the answer they measure.

## Cost levers

Measured on 13 waves: subagent cache-read 20.0B tokens vs lead 4.9B; builders 77% of the subagent share; the 10% longest-lived agents 65%; 69 agents peaked above 500k context. Cost ≈ context × turns, so lifetime is the lever.
- **Context budget ~200k per agent.** Task-sized slices; stop finished agents; new work → fresh agent from the handoff; `autoCompactWindow: 200000` in builder/test/auditor definitions is the safety net. Simulation on the past runs: −54% total, −60% for builders (upper bound).
- **Right-size:** tier ceilings; ≤3 builders per stage; no teammate for a 10-minute task the lead can do.
- **Short in, short out:** missions ≤40 lines of pointers; returns ≤6 lines; never paste research or spec text into a mission.
- **Cache:** subagent/teammate cache lives 5 min. Batch messages; respawn rather than wake a large idle teammate.
- **Fix rounds:** rounds 1–2 resume the builder only while it is alive with a small context; otherwise and in round 3, a fresh fix agent with the gap list + handoff.
- **Slice by volume:** no research/audit slice over ~1.5k lines of dense code (an oversized audit once burned 961k tokens and stalled 50 min). Auditors read the diff from BASE.
- `maxTurns` caps stop runaways; a capped agent returns partial work you can continue.
- **Measure:** `scripts/wave-cost.py <session-id>` prints agents, turns, peak context and cache tokens per role; put it in STATUS at close and compare waves.
