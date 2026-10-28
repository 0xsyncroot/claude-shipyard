---
name: acceptance-testing
description: 'Acceptance and regression testing of a built (or being-built) feature, run by agents in a real browser. Follows the ISTQB test process (analysis → design → implementation → execution → completion) and ISO/IEC/IEEE 29119-3 documents. Derives test cases from the acceptance criteria, user asks and a code-impact analysis (UI, business rules, negative, security, data, regression of affected features) into testcases.yml, gets them independently reviewed, automates them with Playwright, runs them with screenshot/trace evidence, files defect reports to the build team, re-runs confirmation + regression tests after each fix until the exit criteria hold, and writes an HTML test completion report. Test design can run in parallel with the build (ATDD) inside a feature-wave, or standalone after dev finishes. Triggers: "test tính năng", "QA", "kiểm thử", "nghiệm thu", "test case", "testcase", "regression", "bàn giao", "acceptance test", "e2e test trên trình duyệt". Not for unit tests.'
argument-hint: <feature slug or description> [--wave <slug>]
allowed-tools: Read Glob Grep Edit Write Bash Agent SendMessage ListAgents TaskStop AskUserQuestion Skill
---

# Acceptance testing: $ARGUMENTS

Test runs already in this repo (resume one instead of starting over): !`ls -1t .qa 2>/dev/null | grep -v -e '^lib$' -e '^node_modules$' -e '\.' | head -5 | tr '\n' ' ' | grep . || echo none`

You are the **test lead**. You set up the run, own `STATUS.md`, route defects, run the gates and verify claims yourself. Agents do the volume work. Nothing passes until it was observed in the real app.

Reference files — read the one for the phase you are in: [`test-design.md`](test-design.md) (analysis, impact, techniques, case format) · [`test-review.md`](test-review.md) (review checklist, lint) · [`test-execution.md`](test-execution.md) (Playwright, evidence, defects, retest selection, mobile lane) · [`test-report.md`](test-report.md) (completion report). Templates in `templates/`. One CLI: `python3 -I ${CLAUDE_SKILL_DIR}/scripts/qa.py <init|lint|select|collect|status|report> --help`.

Terms used everywhere (ISTQB): **test basis** (what tests are derived from: ACs, asks, keep-working list, impact items, risks) · **test case** (TC) · **confirmation test** (re-run of the TC that found a defect, after its fix) · **regression test** (re-run of TCs for behaviour the fix or the feature could have broken) · **defect report** (BUG-n) · **exit criteria** · **test completion report**.

## Roles (custom agents in `~/.claude/agents/`)

| Agent | Spawn | Does | Never |
|---|---|---|---|
| `test-designer` | named `td-<slug>`, background | test analysis + design → `test-basis.md`, `testcases.yml`; fixes review findings | edit product code, run the app for results |
| `test-reviewer` | unnamed, background | independent review of the test cases → `reviews/review-r<n>.md` APPROVE/REVISE | edit test cases |
| `test-executor` | named `tx-<surface>`, ≤2, background | automation (`tests/*.spec.ts`), runs, evidence, defect reports, confirmation + regression runs | fix product code, weaken an expected result |

The test lead may do a role itself when it is ≤ ~20 min of work. Reviewer ≠ designer, always. Tokens: missions ≤40 lines of pointers, returns ≤6 lines, one task per agent, stop agents as soon as their result is verified (same levers as feature-wave).

Mission templates (≤40 lines, pointers only; `Q` = `.qa/<slug>` absolute):

```
Agent({ subagent_type: "test-designer", name: "td-<slug>", run_in_background: true, description: "Design tests <slug>",
  prompt: `Test run <slug> (mode <wave|standalone>). Run dir: <Q>. Test basis: <spec.md ACs + ASKS + keep-working | user ask verbatim + git diff <BASE>..HEAD>.
Surfaces/roles/viewports: <…>. Project rules that matter: <3–5 from CLAUDE.md>. Stage order: <S1, S2…>.
Write <Q>/test-basis.md + <Q>/testcases.yml; lint to 0 errors. Handoff: <Q>/handoff/td-<slug>.md.` })
Agent({ subagent_type: "test-reviewer", run_in_background: true, description: "Review tests <slug>",
  prompt: `Review <Q>/testcases.yml round <n> against <test basis paths>. Write <Q>/reviews/review-r<n>.md.` })
Agent({ subagent_type: "test-executor", name: "tx-<surface>", run_in_background: true, description: "Run tests <surface>",
  prompt: `Test run <slug>, surface <surface>. TCs: <ids | --grep | "stage Sn P0">. App: <urls/ports, running or start cmd>.
Run ids from <next id>. Defects → <.wave/<slug>/inbox/<owner>.md | <Q>/defects only>. Handoff: <Q>/handoff/tx-<surface>.md.` })
```

## Two modes

- **Inside a feature-wave** (`--wave <slug>`): start test design as soon as the spec is ratified, **in parallel with the build** (ATDD). Test basis = `.wave/<slug>/spec.md` ACs + `ASKS.md` + keep-working list + the stage plan's owned paths. Automation for a stage starts when that stage's gate is `TREE CLEAN`; that stage's P0 TCs are its smoke. Defects go to the owner's `inbox/<owner>.md` (pointer to the BUG file). Final execution = feature-wave Phase 4.
- **Standalone** (dev finished, no wave): test basis = the user's description/ticket + `git diff <BASE>..HEAD` + impact analysis. Ask the user once (AskUserQuestion) only for what the code cannot answer: BASE commit, which roles/accounts exist, out-of-scope areas. Defects go to `defects/` and the report's "Gửi team thi công" section; the user or dev fixes, then tells you.

## Release-time levers (speed · accuracy · coverage) — mandatory

Testing must not add a serial phase after the build. In wave mode the timeline is:

```
spec ratified ─┬─ build S1 ──gate──┬─ build S2 ──gate──┬─ … ── Phase 4 final run ── report
               └─ T1 design + T2 review (parallel)      │                   │
                  regression TCs automated + baseline ──┘ S1 smoke (its P0) └ S2 smoke …
```

- **Shift left:** design and review finish while S1 is being built; regression TCs for existing screens are automated and run first (baseline) before the stage touching them lands.
- **Per-stage smoke = the stage's P0 TCs**, run right after its gate. Defects found there are fixed inside the stage, while the builder still has the context — the cheapest fix there is.
- **Fail fast, file early:** smoke before full; `--max-failures`; each defect filed the moment it reproduces twice, so fixing starts while the run continues.
- **Builders self-verify:** every BUG file carries the exact re-run command; a builder runs it before claiming fixed. This removes most reopen rounds.
- **Selective re-runs:** `qa.py select` (confirmation + impact-based regression + P0) after each fix batch; the full suite runs once, on the hand-over build.
- **Accuracy gates:** independent reviewer for the cases; reproduce-twice for defects; the lead looks at P0 evidence; no healing of expected results.
- **Coverage gate:** `qa.py lint` — every basis item covered, P0 ACs have negative/security cases, changed files without an impact item are flagged.

## Workflow (copy into STATUS and tick)

```
- [ ] T0 Init       qa.py init <slug> [--wave <slug>]; profile ok; exit criteria written; BASE recorded
- [ ] T1 Design     test-designer: test-basis.md + testcases.yml; qa.py lint → 0 errors
- [ ] T2 Review     test-reviewer → APPROVE (≤2 rounds; then the lead rules); cases status=ready
- [ ] T3 Implement  test-executor: specs tagged @TC-id; dry run on what exists (per stage in wave mode)
- [ ] T4 Execute    smoke (all P0) → full run → qa.py collect; failures → BUG-n (reproduced twice)
- [ ] T5 Fix loop   fix lands → qa.py select → confirmation + regression run → collect; repeat
- [ ] T6 Complete   exit criteria met (or user-accepted deviations) → qa.py report → stop all agents
```

**T0 Init.** `qa.py init <slug>` creates `.qa/<slug>/` (git-excluded) and, once per repo, `.qa/profile.yml` + `.qa/playwright.config.ts`. Fill the profile from the project (CLAUDE.md, Makefile, `.env.example`): base URLs, start commands, health URLs, how to get a logged-in session per role, DB access, test-data prefix, cleanup. Then `bash ${CLAUDE_SKILL_DIR}/scripts/pw-setup.sh` (pinned Playwright into `.qa/node_modules`, never into the workspace or a scratchpad that disappears). Record in STATUS: mode, BASE, surfaces, roles, viewports, exit criteria (defaults below, edit only with reason).

**T1 Design** — see `test-design.md`. Every basis item gets an ID (AC-n, A-n, K-n, IMP-n, R-n). Impact analysis comes from the real code graph (`codegraph explore` callers of changed symbols → routes/screens/APIs), never from guessing. `qa.py lint` must report 0 errors before review.

**T2 Review** — see `test-review.md`. The reviewer did not write the cases. REVISE findings → designer fixes in place → re-review only the delta. Cap 2 rounds. To let the user look at the plan before execution: `qa.py report <slug> --plan` (optional; the user did not ask to approve each case).

**T3–T5** — see `test-execution.md`. Smoke before sweep. A test that is green while the screen shows the defect is a FAIL. An executor may repair a locator or a wait ("healing"); it may never change an `expected` to make a test pass — that is a test-case change: designer edits, reviewer approves, change log line.

**T5 fix loop.** For each fix: `qa.py select <slug> --since <fix-commit-or-BASE>` prints the TCs to re-run (the defect's TCs = confirmation; TCs whose impact items touch the changed files + all P0 = regression) and the `--grep` pattern. Re-run, collect, update the BUG status. A defect reopened 3 times → stop routing it, tell the user with the evidence.

**T6 Complete** — see `test-report.md`. `qa.py report <slug>` builds `report.html` (self-contained, evidence linked relatively). In wave mode the report includes the build summary from the wave's STATUS. Tell the user: verdict, counts, open defects, residual risks, report path.

## Exit criteria (defaults — edit in STATUS only with a reason)

1. Every test basis item is covered by ≥1 `ready` TC (`qa.py lint` coverage 100%).
2. 100% of P0 TCs executed and PASS in the latest run of the final build; ≥95% of P1 PASS.
3. 0 open defects of severity S1/S2. S3/S4 may stay open only as `deferred` with the user's verbatim OK.
4. No unexplained console errors or HTTP 5xx during P0 flows.
5. Every PASS has evidence (screenshot and/or DOM/DB/network excerpt) from the run that is reported.
6. Final regression run (all `ready` TCs) after the last fix, on the build that will be handed over.

## Hard rules

- Real app, real browser, real data paths. Unit tests are not evidence for a TC. Mocks only for third parties the team does not control (and say so in the TC).
- The oracle must not contain the answer: assert on what the user sees, the DB row the API wrote, the network response — not on the fixture you fed in.
- Test data carries the profile's prefix and is cleaned up by the run that made it. Never touch real users' rows; never run against production unless the user says so for that run.
- Identity in tests comes from a real session for that role (profile), never from a body field the product should ignore — that is itself a security TC.
- Every defect: reproduced twice, exact steps, expected vs actual, evidence, severity, priority, owner. One defect per BUG file.
- Never claim a PASS you did not observe in this run; flaky = run 3×, report the ratio, file it as a defect if it fails in product code.
- `timeout` everything that can hang; own ports only; never `pkill -f` a pattern your own command contains; leave nothing running except what the user asked to keep.
- macOS: ports → `lsof -nP -iTCP -sTCP:LISTEN`; `timeout` → `gtimeout` (`brew install coreutils`); no `setsid` → `nohup <cmd> > log 2>&1 &` + record `$!`.
- Windows (Claude Code native runs commands in Git Bash): read [`windows.md`](windows.md) once per session — no `ss`/`pkill`/`setsid`, `python3` may be the Microsoft Store stub, `taskkill //F //T //PID` for process trees.
- STATUS.md is the source of truth after compaction or a new session: read it first, reconcile with `ListAgents` and `qa.py status`, then continue.
- The project's CLAUDE.md rules are part of the test basis (e.g. audit-log row per self-mutation, owner-only gates, never-fabricate data) — they become TCs, not reviewer opinions.
- Report in the user's language.
