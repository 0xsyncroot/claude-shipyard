# Test case review (T2) — for test-reviewer

ISTQB static testing of testware. The reviewer did not write the cases. It reads `test-basis.md`, `testcases.yml`, the test basis sources (spec/ASKS/diff) and the code only where an impact claim needs checking. It never edits the cases.

## Procedure

1. Run `qa.py lint <slug>` (and `--spec <spec.md>` in wave mode). Every lint error is a finding; do not re-check what lint already proves.
2. Walk the checklist below. Each finding: `F-n · blocker|major|minor · TC/basis id · problem · evidence (file:line or spec line) · what the designer should change`.
3. Write `.qa/<slug>/reviews/review-r<n>.md`; verdict APPROVE when no blocker or major remains.
4. Re-review (round 2): only the findings listed + TCs whose `changes:` grew. Cap 2 rounds; the lead rules on what remains.

## Checklist

**Coverage**
- [ ] Every ask / AC / keep / rule item has ≥1 TC; every P0 AC has a negative or security TC (or a stated `n/a`).
- [ ] Impact analysis is real: sample ≥3 IMP items and confirm the `reaches:` with `codegraph explore` / grep. Look for missing entry points — shared components, shared packages, DTOs, migrations used by other apps. A missed caller is a blocker.
- [ ] Changed files in the diff that no IMP covers (lint warning) are explained or added.
- [ ] Roles: guest / normal user / owner / admin / suspended — each that the feature touches has a TC.
- [ ] Every listed viewport/surface is exercised by the UI cases.
- [ ] Old data: features touching existing rows have a TC with pre-existing data.

**Correctness of each TC**
- [ ] Expected results come from the requirement, not from the code's current behaviour (compare with the spec line).
- [ ] Each `expected` is observable and specific (quoted text, number, row predicate); no vague words.
- [ ] Oracle independence: the check does not just read back the fixture it seeded.
- [ ] Preconditions and data are complete enough that an executor needs no guess; seeded data uses the profile prefix and has cleanup.
- [ ] The technique fits (limits → BVA; condition combos → decision table; lifecycle → state transition).
- [ ] Priority follows the rules in `test-design.md` §7.
- [ ] Project rules are present as TCs: audit-log row per self-mutation, owner-only authorization in SQL, identity from session, never-fabricate data, UI style guide.

**Economy**
- [ ] No duplicates; data-only variants merged into a data table.
- [ ] `manual:` only with a real reason.
- [ ] Nothing out of scope (spec "Out of scope") is tested as if required.

## Output file

```
# Test case review <slug> round <n>
lint: <errors/warnings summary>
## Findings — F-n · severity · id · problem · evidence · change
## Coverage notes — basis items with thin coverage (non-blocking)
## Verdict: APPROVE | REVISE
```
Final message to the lead (≤120 words): verdict, counts by severity, the blocker IDs, file path.
