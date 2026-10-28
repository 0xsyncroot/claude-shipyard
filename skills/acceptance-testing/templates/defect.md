---
id: BUG-001
title: "<what is wrong, where — one line>"
severity: S2          # S1 blocker | S2 major | S3 minor | S4 trivial
priority: P1          # P0 now | P1 this round | P2 may defer (user OK)
status: new           # new | open | fixed | retest | closed | reopened | deferred | rejected
owner: <builder name | dev>
tcs: [TC-W-001]
covers: [AC-1]
found_run: r02-smoke
build: <commit sha>
environment: "<surface url>, chromium <ver>, viewport <name>, role <role>"
fix_commit: ""
reopen_count: 0
history:
  - "<ISO> new — found in r02-smoke by tx-web"
---
## Steps to reproduce
1. …

## Expected
(from the TC / basis item, quoted)

## Actual
…

## Evidence
- runs/r02-smoke/evidence/TC-W-001/… .png
- console / network / DB excerpt (≤10 lines)

## Re-run command (builder runs this before claiming fixed)
`cd .qa && QA_SLUG=<slug> QA_RUN=dev-BUG-001 npx playwright test --grep "@TC-W-001"`

## Root-cause hint (optional, never a fix)
