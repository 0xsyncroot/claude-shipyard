---
name: feature-wave
description: 'Agent-team workflow for substantial, multi-subsystem work whose scope is unclear or blast radius is high — building, refactoring, migrating, integrating, or debugging a feature across several files or subsystems. The lead triages into a tier (S/M/L), runs a few fact-only researchers, asks at most 4 decision questions, writes ONE short spec (EARS acceptance criteria + vertical stage plan), gates it with a self-check and one critic, then delivers stage by stage — task-sized builder teammates with disjoint ownership, a lead gate, a diff-based independent audit and a smoke run per stage, final runtime QA. Durable on-disk state (.wave/<slug>/) survives compaction and usage limits. Triggers: "build feature", "implement X", "design and build", "add/refactor/migrate X", "clean up / rewrite X", "chia team", "agent team". Do NOT use for small, single-file, well-understood changes — do those directly.'
argument-hint: <feature or problem description>
allowed-tools: Read Glob Grep Edit Write Bash Agent SendMessage ListAgents TaskStop AskUserQuestion Skill
disallowed-tools: ScheduleWakeup CronCreate
---

# Feature Wave (agent team): $ARGUMENTS

Waves already in this repo (newest first — resume one instead of starting over, see `recovery.md`): !`ls -1t .wave 2>/dev/null | head -5 | tr '\n' ' ' | grep . || echo none`

You are the **lead**. You triage, write the spec, own the ledgers, route messages, run the gates and verify claims yourself. Teammates do the parallel work. Order: triage → research → clarify → spec → critique → per stage (foundation → build → gate → audit → smoke → commit?) → final QA → close. Testing runs **in parallel** with the build through the `acceptance-testing` skill (test design starts when the spec is ratified). No production code while design questions are open. Nothing is done until it has run for real.

Reference files (read when you reach that phase): [`spec-phase.md`](spec-phase.md) — research briefs, clarify, spec rules, self-check, critic loop · [`team-protocol.md`](team-protocol.md) — build loop, coordination files, shared tree, ports, verification, cost levers · [`prompts.md`](prompts.md) — spawn/message templates · [`recovery.md`](recovery.md) — limits, dead/silent/duplicate agents, compaction, resume.

Roles are custom agents in `~/.claude/agents/`: `wave-researcher`, `wave-critic`, `wave-auditor` (read-only, spawned **unnamed** as plain subagents — cheaper, results come back as notifications, continue them with `SendMessage` to the agent ID) and `wave-builder` (spawned **named** as teammates — they coordinate). Test roles (`test-designer`, `test-reviewer`, `test-executor`) belong to the `acceptance-testing` skill; read its SKILL.md once at Phase 2e. Always `run_in_background: true`, one message per batch. Never use `Plan`/`Explore` for work that must write files. The Workflow tool only on explicit user request, read-only fan-out.

## Token rules (every phase)

Past runs: subagents used 4× the lead's tokens; builders alone 77%; the 10% longest-lived agents 65%. Cost grows with context × turns, so:
1. **Smallest tier, fewest agents.** Defaults below are ceilings, not targets.
2. **Context budget ~200k per agent.** One task per builder. A finished or bloated agent is stopped; more work goes to a fresh `<name>-2` started from its handoff note. `autoCompactWindow` in the agent definitions is only the safety net.
3. **Pointers, not paste.** Missions ≤40 lines that point at files. Teammates return ≤6 lines; details live in their files.
4. **Scoped reading.** Builders read the spec core + their own stage section + their own inbox. Auditors read the diff, not the repo.
5. **Model:** researchers run `sonnet` (definition); builders, critics, auditors and test agents run the session model. Write the model choice into STATUS for every batch.
6. **Cache expires after 5 min idle.** Batch messages to one teammate. A large-context teammate idle >5 min with more work → stop it and respawn from its handoff rather than waking it.
7. **Release on verification.** Stop each agent (`TaskStop`) as soon as its result is verified and nothing is pending for it.

## User-facing rules

- **ASKS.md** is the user's ledger: every ask, issue or added task, verbatim, with an ID (A1, A2…), status and evidence. Mid-run additions go there first, then into the current stage or the backlog — never redirect running teammates with them. The final report goes item by item through ASKS.md.
- **Decision provenance.** Mark a decision `USER` only with the user's verbatim words and time; everything else is `LEAD` (or `CRITIC`). Never write "the owner decided" for something the user did not say.
- **Visibility.** At each stage boundary tell the user in 3 lines: done (with evidence) · next · ETA. Before any run expected to exceed 30 min, say what it is, why it takes that long, and offer a quicker smoke first.
- **Simplicity.** Prefer the simplest change that meets the acceptance criteria. When a fix adds or removes a rule, guard or exception, list it. Fixes target the class of failure, not one instance.
- Answer user questions yourself; report in the user's language.

## Phase 0 — Triage & preflight (always first)

State one line: **"Tier S/M/L — [reason]; researchers N; builders ≤N per stage; destructive: yes/no."**

| Tier | When | Research | Critic | Builders | Spec |
|---|---|---|---|---|---|
| Direct | one file / pinpointable bug | — do it without this skill | | | |
| S | 2–3 files, design clear | 0 | self-check only | lead or 1 | ≤40 lines |
| M | one subsystem, some unknowns | 1–2 | 1 | ≤2 per stage | ≤80 lines |
| L | multi-subsystem, unclear scope, high blast radius | 3–4 | 1 (+1 lens if destructive/safety) | ≤3 per stage | ≤200 lines |
| + destructive | migration, delete, rewrite, config removal | any tier + human checkpoint (2d) | | | |

Step up a tier when research shows more scope; log it in STATUS.

**One writer, not parallel builders,** unless all hold: ≥2 slices with disjoint files; contracts locked; no slice needs another's output within the stage; each slice is ≥ ~30 min of work. Sequential chains, one big shared bug, or implicit design choices not yet locked (naming, UI style, data shape) → 1 builder + independent audit.

Preflight (lead, serial, cheap):
1. `${CLAUDE_SKILL_DIR}/scripts/wave-init.sh <slug>` → `.wave/<slug>/` (STATUS.md, ASKS.md, BRIEF.md, spec.md, inbox/, research/, reviews/, audit/, handoff/), git-excluded, records BASE and prints ports in use. If the project keeps team state elsewhere, use that and say so.
2. STATUS.md: tier line, baseline (`git status --short | wc -l`, typecheck/lint/test result or known-red list). ASKS.md: the ask verbatim as A1. **Keep-working list**: existing behaviours this wave must not break (from the user's words and a quick probe).
3. One AskUserQuestion now only for blocking facts not in the code, plus the **commit policy** (commit each green stage? which branch? — default: no commits). Design questions wait for Phase 2a.
4. `ListAgents` — stop or reuse leftovers before spawning.

## Phase 1 — Research (tier M/L)

Map the terrain yourself first (1–2 `codegraph explore` calls or a quick grep). Spawn researchers only for real unknowns: one non-overlapping slice each, 2–4 **objective questions** per slice (do not reveal the intended design — researchers then return opinions instead of facts), all in ONE message. Each writes `research/<key>.md` (facts with `file:line`, unknowns, key files) and returns ≤300 words. Always include runtime/ops (cron, docker, env, deploy, ports) for worker/infra/refactor work. Do not poll; a failed slice → respawn only that key or proceed and note it. Details: `spec-phase.md`.

## Phase 2 — Clarify, spec, critique (lead-owned)

- **2a Clarify.** From the research, list choices that would change architecture, data model, tests or UX. Ask ≤4 in one AskUserQuestion, each with a recommended option first and one line on why it matters. Never ask what the code answers. Unanswered → the lead picks and records it under Assumptions.
- **2b Spec.** Write `spec.md` from its template within the tier's line budget: problem + ask IDs · approach + rejected alternatives · before→after (refactors must get simpler) · contracts (signatures/schemas only) · **stage plan** (vertical slices S1..Sn, each verifiable on its own: owns paths · ACs · blocked-by) · **acceptance criteria** (`AC-n | EARS sentence | verify: command or manual steps | stage`) · decisions with provenance · risks & rollback · out of scope · left to the builder. Detail belongs to builders, not the spec.
- **2c Critique.** Run the self-check in `spec-phase.md` first (it removes the mechanical blockers critics otherwise spend a round on). Then one `wave-critic` (a second lens only for destructive/safety work): ≤5 blockers, each with evidence and what a wrong guess would change. Revise the spec **in place**, keep the previous version as `spec.r<n>.md`, and send the critic the diff. A second round only when a blocker touched contracts, data model or a destructive step. Cap 2 rounds, then the lead rules and records it. Never build an unratified spec.
- **2d Human checkpoint.** Before any destructive step show the ratified spec summary via AskUserQuestion and get explicit confirmation. Archive before deleting only what git cannot restore (released data, untracked files, external state).
- **2e Test design in parallel (user-facing or multi-surface waves).** Right after ratification follow `~/.claude/skills/acceptance-testing/SKILL.md` in wave mode: `qa.py init <slug> --wave <slug>`, spawn `test-designer` (named `td-<slug>`) in the same message as the first stage's builders, then `test-reviewer`. Test cases must be `ready` per stage before that stage's gate. Pure non-runtime waves (docs, types-only) skip testing and say so.

## Phase 3 — Deliver stage by stage

For each stage S1..Sn of the spec (details in `team-protocol.md`):
1. **Foundation** (first stage, and whenever contracts change; lead or one builder, serial): lock shared contracts in one file; pre-split convergence points (registries, route/command tables) so slices never edit the same hotspot; the wave's only dependency install; gate scripts that equal the CI commands; finish `BRIEF.md` (ownership, private ports + scratch per teammate, scoped checks, lead decisions, done definition). Typecheck green before builders start.
2. **Build.** Spawn the stage's builders in ONE message (`wave-builder`, named by slice), one task-sized slice each. Test design (2e) keeps running alongside; `test-executor` may automate regression TCs for existing screens now (baseline before this stage touches them). Builders coordinate via `inbox/<owner>.md` and keep `handoff/<name>.md` with `STATUS` + `EVIDENCE`. Lead-only ops stay with the lead (installs, migrations, root configs, CLAUDE.md, shared restarts, git mutations).
3. **Lead loop** — react to notifications only: idle notices need no reply; a report → check its EVIDENCE and re-run one decisive command, update STATUS; resolve inbox items to the lead; resume WAITING teammates when their dependency lands; move ownership of a hot file early.
4. **Gate.** Full typecheck + lint + tests on the merged tree → `TREE CLEAN` in STATUS. Failures go to the owner. Long runs → background + completion notification.
5. **Audit.** One `wave-auditor` (two lenses for safety-critical stages) on the stage's diff from BASE + its ACs + the builders' evidence → PASS/GAPS. Fix loop: rounds 1–2 → the builder if still alive with small context, otherwise a fresh `<name>-fix` from the handoff; round 3 → fresh agent. Cap 3, then the lead rules or escalates. Audit PASS is necessary, not sufficient.
6. **Smoke.** Run this stage's P0 test cases (`qa.py select <slug> --stage <Sn>` → `test-executor`), which include the user's own scenarios and the keep-working items the stage touches. Defects go to the stage's builders now, while they still hold the context; the BUG file carries the re-run command they must pass before claiming fixed. Repeat runs or full sweeps only after the smoke is clean.
7. **Close the stage.** Commit only if the policy says so; archive resolved inbox items; STATUS + ASKS updated; 3-line user update; stop every agent of the stage.

## Phase 4 — Final acceptance testing (mandatory)

Follow `acceptance-testing` T4–T6 on the merged tree: full run of all `ready` TCs (UI in a real browser; API/data on real endpoints; worker/cron confirmed on schedule) → defects to owners → confirmation + regression re-runs from `qa.py select` → final full run on the hand-over build → `qa.py report <slug>` (test + build report in one HTML page). The exit criteria of that skill are this wave's done definition. **Verify P0 "done" claims yourself** (open the evidence). A defect reopened 3 times → tell the user. Skip only for pure non-runtime changes (docs, types-only) and say so.

## Phase 5 — Close

`ListAgents` → stop every agent → no stray processes or ports (`ss -ltnp` for the BRIEF's ports) → cost report `python3 -I ${CLAUDE_SKILL_DIR}/scripts/wave-cost.py ${CLAUDE_SESSION_ID}` into STATUS → final STATUS entry. Report to the user in their language: each ASKS item with status and evidence · files changed + before→after (refactors) · tests added · each AC one line, verified at runtime with evidence · the test report path (`.qa/<slug>/report.html`) and its verdict · what you ran and observed · known limitations and open decisions · cost by role.

## Hard stops (scan list — phases above are authoritative)

- Triage first; smallest tier; ceilings, not targets. One writer unless the parallel test passes.
- STATUS.md and ASKS.md are the source of truth; update after every phase event. Teammates keep handoff notes current every run.
- One owner per path; changes to others' files go through their inbox; lead-only ops stay with the lead.
- Shared tree stays typecheck-clean; the lead declares TREE CLEAN before audit, QA lanes or commits.
- Private ports + scratch per teammate; `timeout` everything that can hang; never a self-matching `pkill -f`/`pgrep -f`; leave nothing running.
- macOS has no `ss`, `timeout` or `setsid` by default: ports → `lsof -nP -iTCP -sTCP:LISTEN`; `timeout` → `gtimeout` (`brew install coreutils`); background → `nohup <cmd> > log 2>&1 &` + record `$!`; `ps -o pid,etime,command`.
- Windows (Claude Code native runs commands in Git Bash): read [`windows.md`](windows.md) once per session — no `ss`/`pkill`/`setsid`, `python3` may be the Microsoft Store stub, `taskkill //F //T //PID` for process trees.
- No ScheduleWakeup/cron, foreground sleeps or polling (only the stall watchdog in `team-protocol.md`). Blocked teammates end with WAITING ON and get resumed.
- Never accept "done" without EVIDENCE plus one re-run; no report after 2 nudges → replace from the handoff note or do it yourself.
- Classifier/permission denial → stop that action and tell the user; never route around it or edit CLAUDE.md to unblock agents.
- Root-cause fixes; no stubs/mocks/TODOs/dead code; real tests on real inputs; correctness before performance.
- Human checkpoint before destructive steps. Loops are bounded: critic 2 rounds · audit 3 rounds → then the lead rules or escalates.
