# Recovery playbook

Principle: **salvage from disk, never restart from scratch.** Files in the tree, research/spec/audit files and handoff notes are the expensive part already paid for.

| Symptom | Cause (seen in past runs) | Do this |
|---|---|---|
| Many teammates end at once with a limit error (or "Not logged in") | Session/weekly usage limit (the most common real killer) | **Not retryable** — do not nudge, respawn or start a phase while the limit is active. Record in STATUS which teammates were mid-task; check the tree compiles; note known-red. After the reset: reconcile (below), then **spawn replacements from handoff notes** — old teammates rarely resumed after a reset, fresh ones from a handoff note worked. |
| One agent returns empty / "request timed out" / "connection lost" | Transient API error | `SendMessage` it once: "continue from your handoff note". Nothing after 2 nudges → replacement `<name>-2`. |
| Teammate reports "done" without EVIDENCE, or you're not sure | Over-claiming | Not done. Re-run its decisive check yourself; for UI one real-click pass. Log the result in STATUS, not the claim. |
| Agent has run hundreds of turns / context very large | Slice too big, or the same builder kept for fixes | Let it finish the current item and update its handoff, then `TaskStop`; continue with `<name>-2` from the note. Split the remaining work into smaller tasks or a new stage. |
| Waking a teammate after a long wait is slow and costly | Its cache expired (5 min idle) and the whole prefix is rewritten | For large contexts respawn from the handoff instead of waking. Batch messages so each teammate wakes once. |
| Teammate silent for a long time | Long build/test, or stuck | Check its handoff note and processes (`ps -o pid,etime,cmd -u $USER | grep <its scratch dir or port>`) before nudging. Silence alone is not failure. |
| Two copies of one teammate | Lead re-spawned or messaged while the original ran | `TaskStop` the newer copy; diff its edits against the owner's handoff; note it in the owner's inbox. Always reconcile before any resume. |
| Teammate went off-mission after a lead message | Message read as a new mission | Reply `CHANGE MISSION:` with the original mission pointer; next time prefix info clearly and keep user questions to yourself. |
| Critic flags a fixed blocker as unchanged | Fix was appended elsewhere; critic re-read the old section | Edit the spec in place and send the critic the `spec-delta` diff (`spec-phase.md`). |
| Critic loop won't converge | Spec too big or lenses overlapping | After 2 rounds: split into ratified core + follow-up stage, record LEAD rulings, escalate only safety/scope questions. |
| User: "I never decided that" | A LEAD choice was recorded as the user's | Correct the Decisions row to `LEAD`, tell the user what you chose and why, ask only if it changes the build. Never cite the user without verbatim words. |
| User: "it worked before, now it's worse" | Regression outside the stage's ACs | Add the behaviour to the keep-working list and as an AC; reproduce on BASE vs now; fix as a P0 gap before the next stage. |
| Typecheck red, not in my slice | A teammate's half-finished edit | Scoped checks only while others edit; tell the owner via its inbox with the exact error; TREE CLEAN only after the owner lands. |
| Port in use / EADDRINUSE / selftest green against the wrong server | Orphan process, or two teammates on one port | `ss -ltnp | grep :<port>` → identify the owner by its cmd line → kill that tree by PID or unique string. Enforce the BRIEF port table. |
| A `pkill -f`/`pgrep -f` loop killed its own shell (exit 144) or never exits | Pattern matched its own command line | Kill by PID or a string unique to the target; wait with `tail -f log | grep -m1 '<final line>'`. |
| Run looks hung | Long `test.setTimeout`s by design, or a real hang (module-load DB connection, dev server) | Grep the test's timeout/budget first. Real hang → kill the tree, rerun with `timeout`, extract pure logic from connection side effects. |
| Auto-mode classifier denies a spawn or action | Safety policy — often right after editing CLAUDE.md or when probing third-party accounts | Stop that action; do not rephrase or route it through another agent. Tell the user what was blocked and why; ask for their resource or for them to apply the rule change. |
| Lead context compacted mid-wave | Long wave | Re-read STATUS.md, ASKS.md, BRIEF.md, `inbox/lead.md`; reconcile; continue the event loop. |
| New session resumes a wave | Session ended / resumed later | The skill header lists waves in this repo. Read STATUS → ASKS → BRIEF → handoff notes → open inbox items; verify the baseline (typecheck/tests) before spawning; reconcile; spawn replacements from handoff notes; log "resumed" in STATUS. |
| Workflow run died (only if the user asked for a Workflow) | One node failure aborts the run | `TaskStop`, then `Workflow({ scriptPath, resumeFromRunId })`; never `SendMessage` a workflow agent. Prefer finishing the remainder with teammates. |

**Reconcile before any spawn after a resume, compaction or limit:** STATUS roster vs `ListAgents` vs `handoff/*.md`. A slice with `STATUS: DONE` and green evidence is not re-spawned; a live teammate is not duplicated; in-process teammates do not survive `/resume`, so a roster entry without a live agent gets a `<name>-2` from its note.
