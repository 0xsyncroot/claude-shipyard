#!/usr/bin/env bash
# claude-shipyard installer — macOS / Linux / WSL. Copies the skills + agents into ~/.claude, writes the
# report rules into ~/.claude/CLAUDE.md (between marker lines), enables Agent Teams, then self-tests.
# Safe to re-run: previous copies are moved to ~/.claude/backup/shipyard-<time>/.
#
#   ./install.sh                 install / update
#   ./install.sh --check         only check this machine and the installed copy; change nothing
#   ./install.sh --dest DIR      install into DIR instead of ~/.claude
#   --no-rules                   do not touch CLAUDE.md
#   --no-settings                do not touch settings.json
#
# Written for bash 3.2 (macOS default): no associative arrays, no ${x,,}, no mapfile.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude"; CHECK=0; RULES=1; SETTINGS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK=1 ;;
    --dest) DEST="$2"; shift ;;
    --no-rules) RULES=0 ;;
    --no-settings) SETTINGS=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

SKILLS="feature-wave acceptance-testing"
PYYAML="pyyaml==6.0.2"
BEGIN='<!-- claude-shipyard:rules:begin -->'
END='<!-- claude-shipyard:rules:end -->'
FAIL=0; WARN=0
if [ -t 1 ]; then G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else G=; Y=; R=; N=; fi
pass() { echo "${G}[PASS]${N} $1: $2"; }
warn() { echo "${Y}[WARN]${N} $1: $2"; WARN=$((WARN+1)); }
fail() { echo "${R}[FAIL]${N} $1: $2"; FAIL=$((FAIL+1)); }
have() { command -v "$1" >/dev/null 2>&1; }
OS="$(uname -s)"

[ -d "$HERE/skills/feature-wave" ] || { echo "run install.sh from the claude-shipyard checkout" >&2; exit 2; }
echo "claude-shipyard → $DEST  ($OS$([ $CHECK = 1 ] && echo ', check only'))"

# ---------------------------------------------------------------- 1. tools on this machine
have git && pass git "$(git --version)" || fail git "missing (macOS: xcode-select --install)"
if have node; then
  v="$(node --version)"; maj="${v#v}"; maj="${maj%%.*}"
  [ "$maj" -ge 18 ] 2>/dev/null && pass node "$v" || warn node "$v — Playwright needs Node >= 18"
else warn node "missing — needed for browser tests (acceptance-testing). https://nodejs.org or: brew install node"; fi
PY=""
if have python3 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
  PY="$(command -v python3)"; pass python3 "$($PY --version 2>&1)"
else fail python3 "Python >= 3.8 required (qa.py, wave-cost.py). macOS: xcode-select --install or brew install python"; fi
if have timeout; then pass timeout "$(command -v timeout)"
elif have gtimeout; then pass timeout "gtimeout (coreutils) — skills say \`timeout\`; Claude uses gtimeout on macOS"
else warn timeout "no timeout/gtimeout — macOS: brew install coreutils (skills wrap long commands in timeout)"; fi
if have ss || have lsof; then pass ports "$(have ss && echo ss || echo lsof)"; else warn ports "neither ss nor lsof found"; fi

# ---------------------------------------------------------------- 2. copy skills + agents (backup first)
if [ $CHECK = 0 ]; then
  ts="$(date +%Y%m%d-%H%M%S)"; BAK="$DEST/backup/shipyard-$ts"; moved=0
  mkdir -p "$DEST/skills" "$DEST/agents"
  for s in $SKILLS; do
    if [ -d "$DEST/skills/$s" ]; then
      rm -rf "$DEST/skills/$s/.venv"            # rebuilt below; never worth backing up
      mkdir -p "$BAK/skills"; mv "$DEST/skills/$s" "$BAK/skills/$s"; moved=$((moved+1))
    fi
    cp -R "$HERE/skills/$s" "$DEST/skills/$s"
    chmod +x "$DEST/skills/$s"/scripts/* 2>/dev/null || true
  done
  for f in "$HERE"/agents/*.md; do
    b="$(basename "$f")"
    if [ -f "$DEST/agents/$b" ] && ! cmp -s "$f" "$DEST/agents/$b"; then
      mkdir -p "$BAK/agents"; cp "$DEST/agents/$b" "$BAK/agents/$b"; moved=$((moved+1))
    fi
    cp "$f" "$DEST/agents/$b"
  done
  [ $moved -gt 0 ] && echo "      previous copies ($moved) → $BAK"
  pass copy "skills: $SKILLS · agents: $(ls "$HERE"/agents | tr '\n' ' ')"
else
  for s in $SKILLS; do
    if [ -d "$DEST/skills/$s" ]; then
      if diff -rq -x .venv -x __pycache__ "$HERE/skills/$s" "$DEST/skills/$s" >/dev/null 2>&1; then pass "skill $s" "installed, same as this checkout"
      else warn "skill $s" "installed copy differs from this checkout (./install.sh updates it)"; fi
    else fail "skill $s" "not installed"; fi
  done
fi

# ---------------------------------------------------------------- 3. PyYAML in a private venv (qa.py re-execs into it)
VENV="$DEST/skills/acceptance-testing/.venv"
if [ -n "$PY" ]; then
  if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import yaml' 2>/dev/null; then pass pyyaml "venv $VENV"
  elif "$PY" -I -c 'import yaml' 2>/dev/null; then pass pyyaml "system python has it"
  elif [ $CHECK = 1 ]; then warn pyyaml "missing — ./install.sh creates $VENV"
  else
    if "$PY" -m venv "$VENV" >/dev/null 2>&1 && "$VENV/bin/python" -m pip install -q --disable-pip-version-check "$PYYAML" >/dev/null 2>&1; then
      pass pyyaml "installed $PYYAML into $VENV"
    else fail pyyaml "could not create $VENV ($PY -m venv / pip). Try: $PY -m pip install --user pyyaml"; fi
  fi
fi

# ---------------------------------------------------------------- 4. report rules → CLAUDE.md (between markers)
if [ -n "$PY" ]; then
  mode=write; { [ $CHECK = 1 ] || [ $RULES = 0 ]; } && mode=check
  out="$("$PY" - "$HERE/rules/CLAUDE.md" "$DEST/CLAUDE.md" "$mode" "$BEGIN" "$END" <<'PYEOF'
import os, shutil, sys, time
src, dst, mode, b, e = sys.argv[1:6]
block = b + '\n' + open(src, encoding='utf-8').read().strip() + '\n' + e
cur = open(dst, encoding='utf-8').read().replace('\r\n', '\n') if os.path.exists(dst) else ''
if b in cur and e in cur and cur.index(b) < cur.index(e):
    new = cur[:cur.index(b)] + block + cur[cur.index(e) + len(e):]
elif cur.strip():
    new = cur.rstrip() + '\n\n' + block + '\n'
else:
    new = block + '\n'
if new == cur:
    print('SAME'); sys.exit(0)
if mode == 'check':
    print('DIFF'); sys.exit(0)
if os.path.exists(dst):
    shutil.copy(dst, dst + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
os.makedirs(os.path.dirname(dst), exist_ok=True)
open(dst, 'w', encoding='utf-8', newline='\n').write(new)
print('WROTE')
PYEOF
)"
  case "$out" in
    SAME) pass rules "$DEST/CLAUDE.md has the current report rules" ;;
    WROTE) pass rules "wrote report rules into $DEST/CLAUDE.md (between claude-shipyard markers; .bak kept)" ;;
    DIFF) if [ $RULES = 0 ]; then pass rules "skipped (--no-rules)"; else warn rules "$DEST/CLAUDE.md lacks the current rules — ./install.sh writes them"; fi ;;
    *) fail rules "$out" ;;
  esac
fi

# ---------------------------------------------------------------- 5. settings.json: Agent Teams (feature-wave)
if [ -n "$PY" ]; then
  mode=write; { [ $CHECK = 1 ] || [ $SETTINGS = 0 ]; } && mode=check
  out="$("$PY" - "$DEST/settings.json" "$mode" <<'PYEOF'
import json, os, shutil, sys, time
p, mode = sys.argv[1:3]
d = {}
if os.path.exists(p):
    try:
        d = json.load(open(p, encoding='utf-8-sig'))
    except ValueError as ex:
        print('INVALID ' + str(ex)); sys.exit(0)
if (d.get('env') or {}).get('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS') == '1':
    print('OK'); sys.exit(0)
if mode == 'check':
    print('MISSING'); sys.exit(0)
if os.path.exists(p):
    shutil.copy(p, p + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
d.setdefault('env', {})['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] = '1'
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, 'w', encoding='utf-8', newline='\n') as f:
    json.dump(d, f, ensure_ascii=False, indent=2); f.write('\n')
print('UPDATED')
PYEOF
)"
  case "$out" in
    OK) pass agent-teams "settings.json env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1" ;;
    UPDATED) pass agent-teams "added CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 to $DEST/settings.json (.bak kept)" ;;
    MISSING) warn agent-teams "settings.json lacks env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 (feature-wave teams need it)" ;;
    *) warn agent-teams "cannot read $DEST/settings.json ($out) — add \"env\": {\"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS\": \"1\"} by hand" ;;
  esac
fi

# ---------------------------------------------------------------- 6. self-test on a throwaway repo
FW="$DEST/skills/feature-wave"; AT="$DEST/skills/acceptance-testing"
if [ -d "$FW" ] && [ -d "$AT" ] && [ -n "$PY" ]; then
  T="$(mktemp -d)"; LOG="$T/selftest.log"
  st() { local name="$1"; shift; if "$@" >>"$LOG" 2>&1; then pass "selftest $name" ok; else fail "selftest $name" "exit $? — see $LOG"; KEEP=1; fi; }
  KEEP=0
  st bash-syntax bash -n "$FW/scripts/wave-init.sh" "$AT/scripts/pw-setup.sh"
  ( cd "$T" && git init -q . && git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init ) >>"$LOG" 2>&1
  st wave-init bash "$FW/scripts/wave-init.sh" shipyard-selftest "$T"
  [ -f "$T/.wave/shipyard-selftest/BRIEF.md" ] && ! grep -q '<root>' "$T/.wave/shipyard-selftest/BRIEF.md" \
    && pass "selftest wave-brief" "BRIEF.md filled" || { fail "selftest wave-brief" "BRIEF.md missing or placeholders left"; KEEP=1; }
  grep -q '/.wave/' "$T/.git/info/exclude" && pass "selftest wave-exclude" ".wave git-excluded" || { fail "selftest wave-exclude" ".wave not in .git/info/exclude"; KEEP=1; }
  "$PY" "$FW/scripts/wave-cost.py" >"$T/wc.out" 2>&1; grep -q Usage "$T/wc.out" && pass "selftest wave-cost" ok || { fail "selftest wave-cost" "$(head -c 200 "$T/wc.out")"; KEEP=1; }
  st qa-init "$PY" -I "$AT/scripts/qa.py" init shipyard-selftest --root "$T"
  st qa-status "$PY" -I "$AT/scripts/qa.py" status shipyard-selftest --root "$T"
  st qa-report-plan "$PY" -I "$AT/scripts/qa.py" report shipyard-selftest --plan --root "$T"
  [ $KEEP = 0 ] && rm -rf "$T" || echo "      self-test files kept in $T"
fi

echo
if [ $FAIL = 0 ]; then
  echo "${G}OK${N} ($WARN warning(s)). Restart Claude Code, then use /feature-wave and /acceptance-testing."
  [ $CHECK = 0 ] && echo "Browser tests: run once per project → bash ~/.claude/skills/acceptance-testing/scripts/pw-setup.sh"
  exit 0
fi
echo "${R}$FAIL problem(s)${N}, $WARN warning(s). Fix the [FAIL] lines and run ./install.sh again."
exit 1
