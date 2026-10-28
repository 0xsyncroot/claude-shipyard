# Test implementation & execution (T3–T5) — for test-executor

## Contents
- 1 Setup once per repo
- 2 Start / reuse the app
- 3 Implementing a TC as a Playwright test
- 4 Healing rules
- 5 Run sequence and speed
- 6 Collect results; manual and mobile lane
- 7 Defect reports
- 8 Fix loop: confirmation + regression
- 9 Visual comparison
- 10 Hygiene

## 1 Setup once per repo

- `qa.py init <slug>` wrote `.qa/profile.yml`, `.qa/playwright.config.ts`, `.qa/lib/evidence.ts`. `bash <skill>/scripts/pw-setup.sh` installs the pinned `@playwright/test` + `yaml` into `.qa/node_modules` and the Chromium build it needs (already cached → no download).
- Project helpers live in `.qa/lib/` and are reused by every run: `auth.ts` (session per role → `storageState` files), `db.ts` (query helper from `profile.db`), `data.ts` (seed + cleanup with `profile.test_data.prefix`). Write them once from the profile; extend, never fork per feature.
- Auth: a `setup` step logs in / mints a session once per role and saves `.qa/.auth/<role>.json`; tests use `test.use({ storageState })`. Never log in through the UI in every test unless login is what the TC tests.

## 2 Start / reuse the app

- If the lead says the dev stack is running (wave mode usually), use it; check the profile `health` URLs first (`curl -sf`). Otherwise start with the profile `start` commands in the background with a known PID, wait on the health URL with `timeout`.
- Never build into a directory a running dev server uses. Never point at production.

## 3 Implementing a TC as a Playwright test

Explore before writing (Playwright "generator" pattern): open the page in the state the TC needs, read the accessibility tree (`page.locator('body').ariaSnapshot()`) or a screenshot, then write the steps with what is really there.

```ts
import { test, expect } from '@playwright/test';
import { shot, watchPage } from '../../lib/evidence';

test('TC-W-003 owner sees report evidence thumbnails', { tag: ['@TC-W-003', '@P0', '@AC-4'] }, async ({ page }, info) => {
  const watch = watchPage(page);                       // console errors + 5xx
  await page.goto('/k/' + data.listingId);
  await page.getByRole('button', { name: 'Báo cáo' }).click();
  await expect(page.getByRole('dialog', { name: 'Báo cáo đánh giá' })).toBeVisible();
  await shot(page, info, 'dialog-open');               // evidence for "ui:" expected
  expect.soft(await db.count(`... = $1`, [data.reviewId])).toBe(1);   // "db:" expected
  watch.assertClean();                                  // "console:" expected
});
```

- One `test()` per TC; title starts with the TC id; tags `@<TC-id>`, `@<priority>`, `@<basis ids>`. `qa.py lint --impl` checks every `ready` TC has its tag in `tests/`.
- Locators: `getByRole` / `getByLabel` / `getByText` with the exact UI text from the TC. CSS/XPath only for things without a role (a map canvas) — comment why.
- Web-first assertions (`await expect(locator).toBeVisible()`); `expect.soft` so one run reports every failing expected line. No `waitForTimeout` except a commented, measured reason.
- Every `ui:`/`visual:` expected gets a `shot()` at that moment; `db:`/`net:`/`audit:` expected are asserted in code, and the value is attached (`info.attach('db', { body })`).
- Data: seed in `beforeAll`/`beforeEach` with the prefix, clean in `afterAll` even on failure. Tests must not depend on each other's data or order. Use production-length text in fixtures (long court names, long notes): short fixture text hid a real layout overflow for a whole release.
- An environment that cannot reach a branch (e.g. a routing service not running locally) → record that row `blocked` in `manual.yml` with the reason; never fake it. It shows as a residual risk in the report.
- Data-driven TC: loop over `data` rows inside the spec, `test.step('<row>')` per row.

## 4 Healing rules

Allowed without asking: a locator that changed name/role while the user-visible behaviour is the same; a wait for a real async state. Not allowed: changing or deleting an `expected` line, loosening an assertion, adding `test.skip`/`fixme` to get green. If the behaviour itself differs from the TC → it is a defect (§7) or a test-case question for the lead — never a heal.

## 5 Run sequence and speed

```
cd .qa && QA_SLUG=<slug> QA_RUN=<run-id> timeout <budget> npx playwright test <filters>
python3 -I <skill>/scripts/qa.py collect <slug> --run <run-id>
```
Run ids: `r01-dry`, `r02-smoke`, `r03-full`, `r04-retest-BUG-002`… (sortable, unique).
File filters are regexes over the whole path: `npx playwright test report` also matches `.qa/<slug>/…` if the slug contains "report". Filter with `report.spec` or `--grep`.

**Parallel executors on one DB:** give each its own data scope (e.g. `QA_SCOPE=web` / `QA_SCOPE=adm`, prefix `e2e-qa-<scope>-`) and make the project teardown clean only that scope — otherwise one executor's teardown deletes the other's data mid-run. Manual cleanup without tests: `QA_SCOPE=<s> QA_SLUG=<slug> QA_RUN=cleanup npx playwright test --grep @__none__ --pass-with-no-tests` (global teardown still runs).

**Final run = one run id with every ready TC** (all specs, one scope) plus a `manual.yml` that carries the manual/blocked rows (gates, mobile lane, branches the environment cannot reach) — that is the run the exit criteria read.

1. **Dry**: `--list` — every ready TC has a test; tests compile.
2. **Smoke**: `--grep @P0 --max-failures=<n>` — the whole P0 set, fail fast on environment breakage. In wave mode: per stage, right after its gate, `--grep "@P0.*@S<n>|@S<n>.*@P0"` or the TC list from `qa.py select <slug> --stage S<n>`.
3. **Full**: all ready TCs, only after the smoke is clean (or its failures are filed).
4. **Flaky check**: a failure you cannot explain → `--repeat-each 3 --grep @<TC>`; report the ratio.

Speed levers (use them; record which in STATUS):
- File each defect **as soon as it reproduces twice** — do not wait for the run to finish; builders start fixing while you continue.
- `workers` from `profile.run.workers` (default 1). Raise it only when every test seeds its own data and no test asserts global counts.
- Reuse `storageState`; reuse the running dev stack; one browser (Chromium) unless the profile lists more.
- Re-runs use `qa.py select` (confirmation + regression), not the full suite; the full suite runs once at the end on the hand-over build.
- Long run (> 30 min) → tell the lead the ETA first and run it in the background with a completion line to wait on.

## 6 Collect results; manual and mobile lane

- `qa.py collect` reads `runs/<id>/pw.json` (+ `manual.yml`), maps tests to TC ids by tag, and writes `runs/<id>/results.json` (status per TC per viewport, error excerpt, evidence paths). The report reads only `results.json`.
- `manual.yml` (TCs marked `manual:` and the mobile lane):
  ```yaml
  - tc: TC-M-004
    status: pass        # pass | fail | blocked | skipped
    viewport: android-1080x2400
    actual: "Sheet shows '3/3 ảnh'; 'Gửi báo cáo' disabled"
    evidence: [evidence/TC-M-004/sheet.png, evidence/TC-M-004/db.txt]
  ```
- Mobile lane (Android emulator): `adb exec-out screencap -p > evidence/<TC>/<step>.png`, `adb shell uiautomator dump` for the node tree (assert on text/enabled from the dump, not on the picture alone), `adb shell input tap/text`. iOS simulator only if the profile says it exists. The installed build must be the hand-over build — record its version.
- Look at the screenshots of every P0 result before reporting it (a green assertion with a broken screen is a FAIL).
- Something odd outside any TC (exploratory observation) → note it in `inbox/lead.md` with repro steps; the lead adds a TC and reproduces before any BUG is filed.

## 7 Defect reports

Template `templates/defect.md` → `.qa/<slug>/defects/BUG-<nnn>.md`. Fields follow ISTQB CTFL v4 §5.5: id, title, date, author, test object (build/commit) and environment, context (TC, run, role, viewport), steps to reproduce, expected vs actual, evidence (screenshot, trace, console, network, DB excerpt), severity, priority, status, references (TC, basis ids), owner.

- Severity (impact): **S1** blocker — data loss, security hole, P0 flow impossible · **S2** major — a P0/P1 rule wrong, no workaround · **S3** minor — workaround exists / cosmetic on a key screen · **S4** trivial.
- Priority (fix order): P0 now · P1 this round · P2 may defer (user OK).
- Reproduce twice before filing. One defect per file. Neutral wording, facts only; a root-cause hint (`file:line`) is welcome, a fix is not.
- Owner: wave mode → the owner of the path from BRIEF §2; append to `.wave/<slug>/inbox/<owner>.md`: `## <ISO> FROM tx-<surface> — BUG-nnn <title>` + the BUG path + the exact re-run command (from `qa.py select <slug> --bug BUG-nnn`). Standalone → `owner: dev`, listed in the report's hand-off section.
- Lifecycle: `new → open → fixed → retest → closed` · `retest → reopened → fixed…` · `deferred` (user OK, verbatim) · `rejected` (works as specified — lead decision with reason). Append a `history:` line on every change.

## 8 Fix loop: confirmation + regression

1. A builder/dev marks the fix (wave: inbox `RESOLVED by …: <commit or files>`; the builder already re-ran the TC command from the BUG file — required before claiming fixed).
2. Lead/executor: `qa.py select <slug> --since <BASE-or-last-retest-commit>` → TC list + reasons + `--grep` pattern:
   - **confirmation**: TCs of every `fixed`/`reopened` BUG;
   - **regression**: TCs covering IMP items whose `changed:` match files changed since the given revision, TCs sharing a basis item with the confirmation TCs, and all P0;
   - **warning**: changed files no IMP covers → the designer adds IMP items before the run.
3. Run, collect, set each BUG `closed` (pass, evidence) or `reopened` (fail, new evidence, `reopen_count+1`). `reopen_count` 3 → escalate to the lead/user.
4. Batch: one retest run per fix batch, not per bug, unless a P0 blocks everything.
5. Final: when no S1/S2 is open → one full run of all ready TCs on the hand-over build → `qa.py report`.

## 9 Visual comparison

- Built in: the report shows, for every TC that failed earlier and passes now, the last failing and the latest screenshot side by side, and for every BUG its evidence vs the confirmation evidence.
- Optional baseline of existing screens (IMP/K regressions): capture them once before the change lands (wave mode: before the stage that touches them; standalone: a `git worktree` at BASE on other ports, only when the lead approves the extra build time). Use `expect(page).toHaveScreenshot({ mask: [dynamic regions], maxDiffPixelRatio: 0.01 })`; snapshots go to `.qa/<slug>/baseline/`. Same OS/browser for baseline and compare.

## 10 Hygiene

`timeout` on every run; own ports only; wait on background runs with `tail -f <log> | grep -m1 '<final line>'`; never `pkill -f` a pattern your own command contains; delete prefixed test data at the end (`profile.test_data.cleanup`) and confirm 0 rows remain; leave nothing running. Before ending each run, rewrite `.qa/<slug>/handoff/<name>.md` (≤60 lines): STATUS · done · open · next · EVIDENCE (run ids, counts, BUG ids).
