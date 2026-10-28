#!/usr/bin/env bash
# Create (or re-open) the durable team directory for a feature-wave.
# Usage: wave-init.sh <slug> [repo-root]
# Idempotent: never overwrites an existing file. Prints the paths, BASE and the ports in use.
set -euo pipefail

slug="${1:-}"
[[ "$slug" =~ ^[a-z0-9][a-z0-9-]{1,48}$ ]] || { echo "usage: wave-init.sh <kebab-slug> [repo-root]" >&2; exit 2; }
root="${2:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
W="$root/.wave/$slug"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$W"/{research,reviews,audit,handoff,inbox}

base="(not a git repo)"; dirty="n/a"
if git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
  # Keep wave state out of git status without touching the tracked .gitignore.
  ex="$(git -C "$root" rev-parse --git-path info/exclude)"
  [[ "$ex" = /* || "$ex" =~ ^[A-Za-z]:[/\\] ]] || ex="$root/$ex"   # C:/… = absolute on Windows (Git Bash)
  mkdir -p "$(dirname "$ex")"
  grep -qxF '/.wave/' "$ex" 2>/dev/null || echo '/.wave/' >> "$ex"
  base="$(git -C "$root" rev-parse HEAD 2>/dev/null || echo '(no commits)')"
  dirty="$(git -C "$root" status --short 2>/dev/null | wc -l | tr -d ' ')"
fi

put() { [[ -e "$1" ]] || cat > "$1"; }

put "$W/STATUS.md" <<EOF
# Wave status: $slug — lead-owned ledger (source of truth after compaction or a session limit)
Started: $now · Repo: $root · Wave dir: $W

## Triage
Tier S/M/L — reason: · researchers: · builders per stage: · destructive: yes/no

## Baseline (before any edit)
BASE: $base · dirty files at start: $dirty (auditors exclude pre-existing dirty files)
typecheck / lint / test:
Commit policy (asked once at preflight): none | each green stage on <branch>

## Keep-working list (existing behaviours this wave must not break)
- K1 …

## Stage log (append: ISO time · stage · event · evidence · next step)
- $now · 0 · wave dir created

## Roster (name · role · model · owns · state: running/waiting/done/stopped/replaced · handoff)

## AC board (AC-id · stage · state: open/built/audited/verified · evidence pointer)

## Open decisions / escalations

## Cost (wave-cost.py at close)
EOF

put "$W/ASKS.md" <<EOF
# Asks ledger ($slug) — the user's words, verbatim. Final report goes item by item.
# ID · time · verbatim ask/issue/task · status: open/in-stage Sn/done/parked · evidence

- A1 · $now · "<the user's ask, verbatim>" · open ·
EOF

put "$W/BRIEF.md" <<'EOF'
# Team brief — read fully before touching anything

Repo: <root> · Spec: .wave/<slug>/spec.md · Wave dir: `$W` = .wave/<slug>/
Goal (ASKS IDs): <A1, …>
State at start (verified by the lead): <BASE, typecheck/lint/test baseline, known-red list>

## 0. Read first
- The project's CLAUDE.md (binding; the stricter rule wins), the spec's Contracts + your stage section, and your handoff note if one exists (continue from it, do not redo).
- `inbox/<you>.md`: every item without a RESOLVED line is yours.

## 1. Binding rules
- Intent guard: lead messages are info/questions; only "CHANGE MISSION" or "STOP" changes your mission.
- Edit only paths you own (§2) or were granted in §2. Re-read a file right before editing it.
- Lead-only: installs/lockfile, migrations/schema apply, root configs, CLAUDE.md, shared service restarts, git mutations.
- Keep the shared tree typecheck-clean after each edit batch; scoped checks only; big refactors in your scratch dir, land in one step.
- No stubs/TODOs/mocks in product code; root-cause fixes that address the class of failure; reproduce → fix → re-run the same check.
- No timers/sleeps/polling. Blocked only on a teammate → finish the rest, end your run with "WAITING ON <x>".
- <project-specific rules copied from CLAUDE.md that matter for this wave>

## 2. Ownership (one owner per path; unit tests follow their code's owner) and grants
| Teammate | Role | Stage | Owns (may edit) |
| --- | --- | --- | --- |
| lead | lead | all | root configs, CLAUDE.md, spec, STATUS.md, ASKS.md, contracts file, anything unowned |

Grants (lead only): <time · teammate · path · why>

## 3. Coordination
- Need a change in someone else's file → append to `inbox/<owner>.md`: `## <ISO-time> FROM <you> — <title>` + problem, evidence (command + output), exact diff. Then continue with other work.
- Re-read only your own inbox at every milestone; act; append `RESOLVED by <you>: …`.
- Timestamps: always `date -u +%Y-%m-%dT%H:%M:%SZ`, never guessed.

## 4. Runtime & tooling
| Teammate | Private ports | Scratch dir |
| --- | --- | --- |
Gate / scoped check / focused test / dev server commands: <exact commands, same as CI>
Hygiene: `timeout` on anything that can hang; wait with `tail -f <log> | grep -m1 '<final line>'`; never `pgrep -f`/`pkill -f`
a pattern your own command contains; kill only your own trees by PID or unique string; check `ss -ltnp` (macOS: `lsof -nP -iTCP -sTCP:LISTEN`; Windows: `netstat -ano -p tcp | grep LISTENING`) before binding;
long `test.setTimeout` ≠ hang; leave nothing running.

## 5. Lead decisions (reversible by the owner)
- L1 …

## 6. Definition of done (every teammate)
1. Every AC you own is met and proven by a real run.
2. Regression tests next to the code for every product fix.
3. Scoped checks green: <typecheck / lint / tests commands>.
4. `handoff/<you>.md` (≤60 lines) rewritten before EVERY run ends:
   `STATUS: DONE | WAITING ON <x> | BLOCKED <why> | IN PROGRESS` · done · open · next · files ·
   `EVIDENCE:` one line per AC — command → exit code + ≤10 lines of output (or DOM/HTTP excerpt).
5. Final message ≤6 lines: STATUS, files changed, checks with exact results, inbox items filed, open items. Never claim an unobserved pass.
EOF
# -i.tmp: the only in-place form GNU and BSD (macOS) sed both accept.
sed -i.tmp "s|<root>|$root|; s|<slug>|$slug|g" "$W/BRIEF.md" && rm -f "$W/BRIEF.md.tmp"

put "$W/inbox/lead.md" <<EOF
# Inbox: lead ($slug) — append only; format in BRIEF.md §3
EOF

put "$W/spec.md" <<'EOF'
# Spec: <title>
<!-- Budget: tier S ≤40 lines · M ≤80 · L ≤200. Signatures/schemas only. Rules: spec-phase.md -->
## Problem — ASKS IDs, why, current state (file:line)
## Approach (chosen) · Rejected alternatives (why)
## Before → after (refactors: simpler)
## Contracts — interfaces / signatures / API shapes / data model & migrations (expand → contract)
## Stage plan — per stage: "## Sn: <behaviour>" · Blocked by · Owns: paths → builder · ACs · fits one fresh context
## Acceptance criteria — AC-n | EARS sentence | verify: command / manual steps | stage | P0/P1
## Decisions — D-n | decision | source: USER (time, verbatim) / LEAD / CRITIC r<n>
## Risks & rollback
## Out of scope
## Left to the builder
## Assumptions
## Change log — time · change · why · ACs/owners affected
EOF

echo "wave dir: $W"
ls -1 "$W"
echo "BASE: $base (dirty files: $dirty)"
echo "--- listening TCP ports (avoid when assigning private ports):"
if command -v ss >/dev/null 2>&1; then
  (ss -ltnH 2>/dev/null | awk '{print $4}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '; echo) || true
elif command -v lsof >/dev/null 2>&1; then  # macOS: no ss
  (lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print $9}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '; echo) || true
else  # Windows (Git Bash): neither ss nor lsof
  (netstat -ano -p tcp 2>/dev/null | tr -d '\r' | awk '$4=="LISTENING"{print $2}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' '; echo) || true
fi
