# Spec phase — research, clarify, spec, critique

Distilled from 13 real waves (2026-09/10) plus Spec Kit, Kiro, superpowers, HumanLayer and Anthropic's harness posts. Past specs ran 9–90KB and every teammate re-read them; critic round 1 returned REVISE almost every time, mostly for mechanical gaps. The rules below keep the spec short and catch those gaps before a critic is paid for.

## Contents
- Research — briefs that return facts, not opinions
- Clarify — ≤4 decision questions
- Spec — budget, sections, EARS acceptance criteria, stage plan
- Self-check — run before any critic
- Critic loop — one critic, ≤5 blockers, diff-based re-review
- Changing the spec during the build

## Research

- Map first yourself (1–2 `codegraph explore` calls or a grep) so researchers only get real unknowns. Tier M: 1–2 researchers. Tier L: 3–4.
- Slices do not overlap: architecture & data flow · data model & migration risk · API/contract surface & callers · deps & integrations · edge cases & failure modes · tests & CI · conventions/prior art · runtime/ops. Pick only the ones with open questions.
- Each brief has four parts: **objective questions** (2–4, about how the code is, not what to build — a researcher who knows the target design returns opinions), boundaries (paths, read-only, ~25 tool calls), the 3–5 project rules that matter (researchers run without CLAUDE.md), output path.
- Output: `research/<key>.md` ≤120 lines — facts with `file:line`, constraints, risks, unknowns, 5–10 key files. No recommendations. Message to the lead ≤300 words.
- Spawn unnamed (`wave-researcher`, plain subagent, sonnet by definition), all in one message. Read each file once when its notification arrives; do not re-derive what it already proved.

## Clarify

- After research, list the choices that would change architecture, data model, tests or UX and that the code cannot answer.
- Ask ≤4 in ONE AskUserQuestion (the tool's limit). Each: the decision as a question, recommended option first with "(Recommended)", one line on why it matters. Never ask what the code or the earlier conversation answers.
- Record each answer verbatim in the spec's Decisions table as `USER (time): "<words>"`. Unanswered or skipped → the lead picks, marks it `LEAD`, lists it under Assumptions. At most 3 open markers may remain in the spec; everything else becomes an assumption.

## Spec

Budget: tier S ≤40 lines · M ≤80 · L ≤200. Contracts carry signatures and schemas, never bodies. Anything a competent builder can decide goes under "Left to the builder".

Sections (template created by `wave-init.sh`):
- **Problem** — ASKS IDs covered, the why, current state with `file:line`.
- **Approach** — chosen + 1–2 rejected alternatives with the reason.
- **Before → after** — refactors must get simpler (fewer files/paths/rules).
- **Contracts** — interfaces, signatures, API shapes, data model; migrations expand → contract.
- **Stage plan** — vertical slices, each verifiable on its own:
  ```
  ## S2: <end-to-end behaviour from the user's view>
  Blocked by: S1 (or none)   Owns: <paths> → <builder>   ACs: AC-3, AC-4   One fresh context: yes
  ```
  Name hot shared files explicitly (lockfiles, root configs, schema/migrations, i18n/copy modules, generated fixtures, registries) and give each one owner.
- **Acceptance criteria** — one row each, EARS form, runtime-observable:
  ```
  AC-1 | When a user submits an expired token, the API shall return 401 with code TOKEN_EXPIRED | verify: pytest tests/auth/test_expiry.py::test_401 | S1 | P0
  AC-2 | While the queue is paused, the worker shall not dequeue jobs | verify: manual — pause via /admin, enqueue 3, observe 0 processed for 60 s | S2 | P1
  AC-3 | If the upstream times out, then the service shall retry ≤3 times and log RETRY_EXHAUSTED | verify: <cmd> | S2 | P0
  ```
  EARS patterns: Ubiquitous "The <system> shall …" · "While <state>, …" · "When <trigger>, …" · "Where <feature>, …" · "If <condition>, then …". Keep-working items from preflight become ACs too.
- **Decisions** — `D-n | decision | source: USER (time, verbatim) / LEAD / CRITIC r<n>`.
- **Risks & rollback** · **Out of scope** · **Left to the builder** · **Assumptions** · **Change log**.

## Self-check (lead, before any critic)

```
[ ] Every ASKS item maps to an AC or an explicit out-of-scope line
[ ] Every AC is EARS-shaped, runtime-observable, has a verify command or manual steps, a stage and a priority
[ ] Every stage has ≥1 automated AC and fits one fresh builder context
[ ] Every owned path has exactly one owner; hot shared files named and owned
[ ] Names and signatures identical across contracts, stage plan and ACs
[ ] No placeholders: TBD, "handle edge cases", "appropriate validation", ???, adjectives without numbers
[ ] Every USER decision has verbatim words; nothing attributed to the user that they did not say
[ ] Within the line budget; ≤3 open markers; rollback and out-of-scope stated
[ ] Simplest approach that meets the ACs; added/removed rules or exceptions listed
```

## Critic loop

- One `wave-critic`, spawned unnamed. Choose the lens from the biggest risk: correctness & contracts (default) · runtime/ops & failure modes · safety & product rules · simplicity & scope. A second critic with a different lens only for destructive, migration or safety-critical work.
- The critic answers as the engineer who must build from this spec without asking the author: ≤5 blockers, each with evidence (`spec line` / `file:line`) and what a wrong guess would change in the build. Non-blocking points go under Notes and do not block. "Nothing important left" → APPROVE.
- Revise **in place**. Before editing, copy `spec.md` → `spec.r<n>.md`. After editing, `diff -u spec.r<n>.md spec.md > reviews/spec-delta-r<n+1>.diff` and send the same critic (by agent ID) the diff path. Appending fixes at the end of the spec confused critics in past runs (they re-read the old section and flagged it unchanged).
- Round 2 only when a blocker touched contracts, data model or a destructive step. Cap 2 rounds, then the lead rules on what remains and records each ruling as `LEAD` in Decisions. Escalate to the user only safety or scope questions.
- Stop the critic once the spec is ratified.

## Changing the spec during the build

Implementation teaches things. Change the spec openly: edit in place, add a Change log line (time · what · why · ACs and owners affected), notify affected owners through their inbox. Never change contracts silently; a contract change sends the stage back through Foundation.
