# Test analysis & design (T1) — for test-designer

ISTQB: *analysis* decides **what** to test (test basis → basis items), *design* decides **how** (test cases). Output: `.qa/<slug>/test-basis.md` (human notes + impact evidence) and `.qa/<slug>/testcases.yml` (source of truth, schema in `templates/testcases.yml`). Run `qa.py lint <slug>` after every edit batch.

## Contents
- 1 Test basis by mode
- 2 Basis items and IDs
- 3 Impact analysis (affected features)
- 4 What to test — category checklist
- 5 Techniques
- 6 Writing a test case
- 7 Priorities and size
- 8 Designing in parallel with the build
- 9 Changing cases after review

## 1 Test basis by mode

| Mode | Read | Do not read |
|---|---|---|
| wave | `.wave/<slug>/spec.md` (Problem, Contracts, Stage plan, ACs, Decisions, Out of scope), `ASKS.md`, STATUS keep-working list, project CLAUDE.md | builders' handoffs, research files (opinions of the build, not the requirement) |
| standalone | the user's description / ticket, `git diff <BASE>..HEAD --stat` then the changed files, project CLAUDE.md, existing docs for the feature | — |

The requirement is the oracle. If the code does something the requirement does not say, that is a question for the lead (`inbox/lead.md` or STATUS Open questions), not a new expected result.

## 2 Basis items and IDs

Every item gets one row in `basis:` with `id`, `kind`, `text` (verbatim where the source is the user or spec), `priority`, `source` (`file:line`).

| kind | ID | From |
|---|---|---|
| `ac` | `AC-n` (same number as the spec) | spec acceptance criteria; standalone: write EARS-style criteria from the ask and mark `source: DERIVED` |
| `ask` | `A-n` | ASKS.md items / the user's own scenarios, verbatim |
| `keep` | `K-n` | keep-working list: existing behaviour that must not break |
| `impact` | `IMP-n` | impact analysis (§3), with `changed:` paths and `reaches:` entry points |
| `rule` | `R-n` | project rules that apply to this feature (CLAUDE.md: audit-log row per self-mutation, owner-only gates, identity from session, never-fabricate, UI style guide…) |
| `risk` | `RISK-n` | product risks you found (likelihood × impact high) that no AC states: concurrency, double submit, data migration of old rows, timezone, offline |

User scenarios beat invented ones: every `ask` with a scenario gets a TC that replays it word for word.

## 3 Impact analysis (affected features)

Goal: list every existing user-facing entry point the change can alter, with evidence.

1. **Changed set.** Wave: the stage plan's owned paths + contracts (planned) — refresh with `git diff --name-only <BASE>` as stages land. Standalone: `git diff --name-only <BASE>..HEAD` (+ uncommitted).
2. **Trace to entry points.** For each changed symbol: `codegraph explore "<symbol>"` (or `codegraph explore "who calls <symbol>"`) → follow callers up to a route/page/screen/API handler/cron job. Without `.codegraph/`, use grep for imports. Shared packages (DTOs, shared helpers, api-client, db schema) fan out to every app that imports them — check each app.
3. **Data impact.** Migrations, backfills, changed enums or defaults: old rows must still display and behave (a TC with pre-existing data, not only fresh data).
4. **Write IMP items**, one per entry point group:
   ```yaml
   - id: IMP-3
     kind: impact
     text: "ReportDialog is also used by the chat-report and profile-report flows"
     changed: [apps/web/components/ReportDialog.tsx]
     reaches: ["/k/[id] chat → Báo cáo", "/ho-so/[username] → Báo cáo"]
     evidence: "codegraph: ReportDialog ← ChatHeader (apps/web/components/chat/ChatHeader.tsx:88) ← ProfileActions (…:41)"
     priority: P1
   ```
   No evidence → `evidence: ASSUMPTION — <why>`; the reviewer will challenge it.
5. `changed:` entries are path prefixes or globs; `qa.py select` uses them to pick regression TCs after each fix, and warns about changed files no IMP covers — so keep them accurate.

## 4 What to test — category checklist

Walk this list for every P0/P1 basis item; write a TC where it applies, skip silently where it does not.

- **Functional / business rule:** the happy path end-to-end as the user would do it; each rule branch (decision table); lifecycle states and forbidden transitions (state transition); limits (0, 1, max, max+1); defaults; persistence after reload; URL/view state survives reload and back.
- **UI:** each listed viewport; empty / loading / error / long text / Vietnamese diacritics / very large numbers; exact copy text (quote it); one primary action per screen; no overflow or clipped text; disabled vs enabled states; focus and keyboard reach for the main controls; dark mode if the product has it; consistency with the project style guide.
- **Negative:** invalid input classes; missing required fields; double submit; back/refresh mid-flow; expired session; server error where it can be provoked without mocks; slow network only if the spec talks about it.
- **Security (from the project rules):** acting on another user's object by changing the id in the URL/body (IDOR) → 403/404, no data; role without permission (guest, non-owner, suspended); identity fields in the body ignored; user text rendered without HTML injection; junk ids → 404, not 500; rate limits if the spec sets them.
- **Data:** the DB row written matches what the user entered; audit-log row with the right action/actor; nothing written on a rejected request; cleanup/retention rules; no PII or fabricated values shown.
- **Regression:** every IMP and K item: the old flow still works with old and new data.
- **Cross-surface:** the same object shows the same state on web / admin / mobile where the feature spans them.
- **Observability of failure:** P0 flows end with no console errors and no 5xx in the network log.

## 5 Techniques (ISTQB black-box + experience-based)

| Technique | Use when | Example |
|---|---|---|
| Equivalence partitioning (EP) | input has classes treated alike | price: empty / 0 / normal / non-numeric |
| Boundary value analysis (BVA) | ordered limits | max 3 photos → 2, 3, 4 |
| Decision table | ≥2 conditions combine | owner? × listing expired? × logged in? |
| State transition | lifecycle (draft→open→full→over) | invalid jump full→draft is rejected |
| Use case / scenario | end-to-end user goal | user's own scenario from ASKS |
| Error guessing | known failure classes of this codebase | memory notes, past BUG files, CLAUDE.md gotchas |
| Checklist-based | UI and project rules | §4 list, style guide |
| Exploratory (charter) | after scripted runs pass, time-boxed | `type: exploratory`, `automation: manual: charter` |

Record the technique in each TC (`technique:`); the reviewer checks the choice.

## 6 Writing a test case

- One objective per TC. ≤12 steps; longer → split. Data-driven variants of the same flow → one TC with a `data:` table, the spec loops over it.
- Steps in user language with the exact UI text the user clicks (`Click "Gửi báo cáo"`). Paths/ids as placeholders `{listing}` defined in `data:`/`preconditions:`.
- `expected:` lines start with a kind: `ui:` `url:` `net:` `db:` `audit:` `console:` `file:` `visual:`. Each is observable and specific: quoted text, a number, a row predicate. Banned without a quote or number: "đúng", "bình thường", "ok", "works", "correctly", "properly", "as expected", "hiển thị đầy đủ".
- The oracle comes from the requirement, not from the code: never copy the implementation's current output as the expected value.
- `preconditions:` say which role/session, which data exists (seeded with the profile prefix), feature flags/settings.
- `automation:` the spec file that will implement it (`tests/<area>.spec.ts`), or `manual: <reason>` (e.g. native OS dialog, physical device) — manual is the exception and needs a reason.
- `stage:` (wave mode) the stage whose gate makes the TC runnable.
- `status: draft` until the reviewer approves; then `ready`. Removed by a spec change → `obsolete` (keep the row).

## 7 Priorities and size

- **P0**: happy path of every P0 AC/ask; the key negative and security case of each; regression of P0 features the change reaches.
- **P1**: other ACs, other IMP/K regressions, data and audit checks.
- **P2**: cosmetic, rare edges, exploratory.
- No quota. Coverage, not count, is the gate: typically 2–5 TCs per P0 AC and ≥1 per IMP/K/R item. Duplicates (same steps, same expected) are removed, not counted.

## 8 Designing in parallel with the build (wave mode)

- Start right after the spec is ratified; you need no running app. Everything except locators can be written now.
- Order your work by stage: S1's cases first, so they are `ready` when S1's gate turns `TREE CLEAN`.
- Regression TCs for existing screens (IMP/K) can be handed to the executor early: they can be automated and run **before** the stage touching them lands — that run is the baseline for later comparison.
- A testability gap (control with no accessible name, no way to seed a state) → `inbox/lead.md`; never ask builders directly and never design around it silently.
- After each spec change: `qa.py lint <slug> --spec .wave/<slug>/spec.md` lists ACs added/removed/reworded; update basis + cases, add a `changes:` line to each touched TC.

## 9 Changing cases after review

Edit in place, append to the TC's `changes:` list `"<ISO> <who>: <what> — <why>"`, set `status: draft` again if `expected` changed, and send only the changed IDs to the reviewer.
