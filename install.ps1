# claude-shipyard installer - Windows 10/11, Claude Code NATIVE (commands run in Git Bash).
# Run it through install.cmd (install/update) or doctor.cmd (check only, changes nothing).
# This file MUST stay ASCII: Windows PowerShell 5.1 reads a BOM-less file as ANSI.
#   -Check      only check this machine and the installed copy; change nothing
#   -Dest <dir> target .claude dir (default %USERPROFILE%\.claude)
#   -NoEnv      do not set user env vars / git config / settings.json
#   -NoRules    do not touch CLAUDE.md
param(
  [switch]$Check,
  [string]$Dest = (Join-Path $env:USERPROFILE '.claude'),
  [switch]$NoEnv,
  [switch]$NoRules
)

$ErrorActionPreference = 'Continue'   # 'Stop' turns every stderr line of a native command into a fatal error
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = Join-Path $here 'install-log.txt'
$results = New-Object System.Collections.ArrayList
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$PyYaml = 'pyyaml==6.0.2'

function Say([string]$level, [string]$name, [string]$msg) {
  [void]$results.Add([pscustomobject]@{ Level = $level; Name = $name; Msg = $msg })
  $color = @{ PASS = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Gray' }[$level]
  Write-Host ('[{0}] {1}: {2}' -f $level, $name, $msg) -ForegroundColor $color
  Add-Content -Path $log -Value ('[{0}] {1}: {2}' -f $level, $name, $msg) -Encoding UTF8
}

# Run a native command; returns @{ Code; Out }. Never throws (missing command -> Code 9999).
function Run([string]$exe, [string[]]$argv) {
  try {
    $out = & $exe @argv 2>&1 | ForEach-Object { "$_" }
    return @{ Code = $LASTEXITCODE; Out = (($out | Out-String).Trim()) }
  } catch {
    return @{ Code = 9999; Out = $_.Exception.Message }
  }
}

function ToSlash([string]$p) { return ($p -replace '\\', '/') }

Set-Content -Path $log -Value ('install.ps1 ' + (Get-Date -Format s) + ' Check=' + $Check + ' Dest=' + $Dest) -Encoding UTF8

# ---------------------------------------------------------------- 0. checkout layout
if (-not (Test-Path (Join-Path $here 'skills\feature-wave'))) {
  Say FAIL 'checkout' 'skills\feature-wave not found next to install.ps1. Clone the repo (or extract the WHOLE zip) and run install.cmd from its root.'
  exit 1
}
try { Get-ChildItem -Path $here -Recurse -File | Unblock-File -ErrorAction SilentlyContinue } catch { }
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
Say INFO 'windows' ("{0} build {1}; PowerShell {2}" -f $os.Caption, $os.BuildNumber, $PSVersionTable.PSVersion)
$crlf = Select-String -Path (Join-Path $here 'skills\*\scripts\*.sh') -Pattern "`r" -List -ErrorAction SilentlyContinue
if ($crlf) {
  Say FAIL 'line-endings' ('.sh files have CRLF (git core.autocrlf?). Re-clone with: git clone -c core.autocrlf=false ... Files: ' + (($crlf | ForEach-Object { $_.Path }) -join ', '))
}

# ---------------------------------------------------------------- 1. Git Bash
$bash = $null
$cands = @()
if ($env:CLAUDE_CODE_GIT_BASH_PATH) { $cands += $env:CLAUDE_CODE_GIT_BASH_PATH }
$cands += (Join-Path $env:ProgramFiles 'Git\bin\bash.exe')
if (${env:ProgramFiles(x86)}) { $cands += (Join-Path ${env:ProgramFiles(x86)} 'Git\bin\bash.exe') }
$cands += (Join-Path $env:LOCALAPPDATA 'Programs\Git\bin\bash.exe')
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { $cands += (Join-Path (Split-Path (Split-Path $git.Source)) 'bin\bash.exe') }
foreach ($c in $cands) {
  if ($c -and (Test-Path $c) -and ($c -notmatch '\\System32\\')) { $bash = (Resolve-Path $c).Path; break }   # System32\bash.exe = WSL
}
if (-not $bash) {
  Say FAIL 'git-bash' 'Git for Windows is not installed. Install it from https://git-scm.com/download/win and run again.'
} else {
  Say PASS 'git-bash' $bash
  if ($env:CLAUDE_CODE_GIT_BASH_PATH -ne $bash) {
    if ($Check -or $NoEnv) {
      Say WARN 'git-bash-env' "CLAUDE_CODE_GIT_BASH_PATH does not point to Git Bash (now: '$($env:CLAUDE_CODE_GIT_BASH_PATH)'). install.cmd sets it."
    } else {
      [Environment]::SetEnvironmentVariable('CLAUDE_CODE_GIT_BASH_PATH', $bash, 'User')
      Say PASS 'git-bash-env' 'Set CLAUDE_CODE_GIT_BASH_PATH (User). Restart terminals / Claude Code to pick it up.'
    }
  }
}

# ---------------------------------------------------------------- 2. Node
$node = Run 'node' @('--version')
if ($node.Code -ne 0) {
  Say WARN 'node' 'node not found - needed for browser tests (acceptance-testing). Install Node.js LTS from https://nodejs.org'
} else {
  $major = [int](($node.Out -replace '^v', '').Split('.')[0])
  if ($major -lt 18) { Say WARN 'node' "$($node.Out) - Playwright needs Node >= 18" } else { Say PASS 'node' $node.Out }
}

# ---------------------------------------------------------------- 3. a REAL Python (not the Microsoft Store stub)
$py = $null
# No double quotes inside -c: PowerShell 5.1 strips them when calling native programs -> SyntaxError.
$probe = 'import sys; print(sys.executable); print(''%d.%d'' % sys.version_info[:2])'
foreach ($pc in @(@('py', '-3'), @('python'), @('python3'))) {
  $argv = @()
  if ($pc.Count -gt 1) { $argv += $pc[1..($pc.Count - 1)] }
  $r = Run $pc[0] ($argv + @('-c', $probe))
  if ($r.Code -eq 0 -and $r.Out) {
    $lines = $r.Out -split "`r?`n"
    $v = [version]($lines[-1].Trim())
    if ($v -ge [version]'3.8') { $py = $lines[0].Trim(); Say PASS 'python' "$py ($v)"; break }
    Say WARN 'python' "$($lines[0]) ($v) is too old, need >= 3.8"
  }
}
if (-not $py) {
  Say FAIL 'python' 'No working Python >= 3.8. Install from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then turn off Settings > Apps > App execution aliases > python.exe / python3.exe.'
}

# ---------------------------------------------------------------- 4. copy skills + agents (backup first)
$skillsDst = Join-Path $Dest 'skills'
$agentsDst = Join-Path $Dest 'agents'
$skillNames = @('feature-wave', 'acceptance-testing')
if (-not $Check) {
  $bak = Join-Path $Dest ('backup\shipyard-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
  New-Item -ItemType Directory -Force -Path $skillsDst, $agentsDst | Out-Null
  $moved = 0
  foreach ($s in $skillNames) {
    $t = Join-Path $skillsDst $s
    if (Test-Path $t) {
      Remove-Item (Join-Path $t '.venv') -Recurse -Force -ErrorAction SilentlyContinue   # rebuilt below
      New-Item -ItemType Directory -Force -Path (Join-Path $bak 'skills') | Out-Null
      Move-Item $t (Join-Path $bak "skills\$s"); $moved++
    }
    Copy-Item (Join-Path $here "skills\$s") $t -Recurse -Force
  }
  foreach ($f in (Get-ChildItem (Join-Path $here 'agents') -Filter *.md -File)) {
    $t = Join-Path $agentsDst $f.Name
    if (Test-Path $t) { New-Item -ItemType Directory -Force -Path (Join-Path $bak 'agents') | Out-Null; Copy-Item $t (Join-Path $bak "agents\$($f.Name)"); $moved++ }
    Copy-Item $f.FullName $t -Force
  }
  if ($moved -gt 0) { Say INFO 'backup' "previous copies ($moved) -> $bak" }
  Say PASS 'copy' ("skills: " + ($skillNames -join ', ') + " -> $skillsDst ; agents -> $agentsDst")
} else {
  foreach ($s in $skillNames) {
    if (Test-Path (Join-Path $skillsDst "$s\SKILL.md")) { Say PASS "skill $s" 'installed' } else { Say FAIL "skill $s" 'not installed' }
  }
}

# ---------------------------------------------------------------- 5. PyYAML in a private venv (qa.py re-runs itself there)
$venv = Join-Path $skillsDst 'acceptance-testing\.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
if ($py) {
  if ((Test-Path $venvPy) -and ((Run $venvPy @('-c', 'import yaml')).Code -eq 0)) { Say PASS 'pyyaml' "venv $venv" }
  elseif ($Check) { Say WARN 'pyyaml' "missing - install.cmd creates $venv" }
  else {
    $mk = Run $py @('-m', 'venv', $venv)
    $pip = Run $venvPy @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', $PyYaml)
    Add-Content -Path $log -Value ($mk.Out + "`n" + $pip.Out) -Encoding UTF8
    if ((Run $venvPy @('-c', 'import yaml')).Code -eq 0) { Say PASS 'pyyaml' "installed $PyYaml into $venv" }
    else { Say FAIL 'pyyaml' "could not create $venv (see install-log.txt)" }
  }
}

# ---------------------------------------------------------------- 6. long paths (Playwright under .qa\node_modules)
$lp = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
if ($lp -eq 1) { Say PASS 'long-paths' 'LongPathsEnabled=1' } else {
  Say WARN 'long-paths' 'LongPathsEnabled is off. PowerShell as Administrator: New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force'
}
if ($git) {
  $gl = Run 'git' @('config', '--global', '--get', 'core.longpaths')
  if ($gl.Out -eq 'true') { Say PASS 'git-longpaths' 'core.longpaths=true' }
  elseif ($Check -or $NoEnv) { Say WARN 'git-longpaths' 'git config --global core.longpaths true (install.cmd sets it)' }
  else { Run 'git' @('config', '--global', 'core.longpaths', 'true') | Out-Null; Say PASS 'git-longpaths' 'set core.longpaths=true' }
}

# ---------------------------------------------------------------- 7. report rules -> CLAUDE.md (between marker lines)
$rulesSrc = Join-Path $here 'rules\CLAUDE.md'
$rulesDst = Join-Path $Dest 'CLAUDE.md'
$rb = '<!-- claude-shipyard:rules:begin -->'
$re = '<!-- claude-shipyard:rules:end -->'
$block = $rb + "`n" + ([IO.File]::ReadAllText($rulesSrc, [Text.Encoding]::UTF8)).Trim() + "`n" + $re
$cur = ''
if (Test-Path $rulesDst) { $cur = ([IO.File]::ReadAllText($rulesDst, [Text.Encoding]::UTF8)).Replace("`r`n", "`n") }
$i = $cur.IndexOf($rb); $j = $cur.IndexOf($re)
if ($i -ge 0 -and $j -gt $i) { $new = $cur.Substring(0, $i) + $block + $cur.Substring($j + $re.Length) }
elseif ($cur.Trim()) { $new = $cur.TrimEnd() + "`n`n" + $block + "`n" }
else { $new = $block + "`n" }
if ($new -eq $cur) { Say PASS 'rules' "$rulesDst has the current report rules" }
elseif ($NoRules) { Say PASS 'rules' 'skipped (-NoRules)' }
elseif ($Check) { Say WARN 'rules' "$rulesDst lacks the current report rules - install.cmd writes them" }
else {
  if (Test-Path $rulesDst) { Copy-Item $rulesDst ($rulesDst + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
  [IO.File]::WriteAllText($rulesDst, $new, $utf8NoBom)
  Say PASS 'rules' "wrote report rules into $rulesDst (between claude-shipyard markers; .bak kept)"
}

# ---------------------------------------------------------------- 8. settings.json: Agent Teams (feature-wave)
$settings = Join-Path $Dest 'settings.json'
if ($py) {
  $tmpPy = Join-Path $env:TEMP 'shipyard-settings.py'
  $code = @'
import json, os, shutil, sys, time
p, write = sys.argv[1], sys.argv[2] == '1'
d = {}
if os.path.exists(p):
    try:
        with open(p, encoding='utf-8-sig') as f:
            d = json.load(f)
    except ValueError as e:
        print('INVALID ' + str(e)); sys.exit(0)
if (d.get('env') or {}).get('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS') == '1':
    print('OK'); sys.exit(0)
if not write:
    print('MISSING'); sys.exit(0)
if os.path.exists(p):
    shutil.copy(p, p + '.bak-' + time.strftime('%Y%m%d-%H%M%S'))
os.makedirs(os.path.dirname(p), exist_ok=True)
d.setdefault('env', {})['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS'] = '1'
with open(p, 'w', encoding='utf-8', newline='\n') as f:
    json.dump(d, f, ensure_ascii=False, indent=2); f.write('\n')
print('UPDATED')
'@
  [IO.File]::WriteAllText($tmpPy, $code, $utf8NoBom)
  $w = '1'; if ($Check -or $NoEnv) { $w = '0' }
  $s = Run $py @($tmpPy, $settings, $w)
  Remove-Item $tmpPy -ErrorAction SilentlyContinue
  switch -Regex ($s.Out) {
    '^OK' { Say PASS 'agent-teams' 'settings.json env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1' }
    '^UPDATED' { Say PASS 'agent-teams' "added CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 to $settings (.bak kept)" }
    '^MISSING' { Say WARN 'agent-teams' 'settings.json lacks env CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 (feature-wave teams need it). install.cmd adds it.' }
    default { Say WARN 'agent-teams' "cannot read $settings ($($s.Out)). Add to its env section: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = 1" }
  }
}

# ---------------------------------------------------------------- 9. self-test inside Git Bash
if ($bash -and $py -and (Test-Path (Join-Path $skillsDst 'acceptance-testing'))) {
  $vsh = Join-Path $env:TEMP 'shipyard-selftest.sh'
  $body = @'
set -u
D="__DEST__"; PY="__PY__"
FW="$D/skills/feature-wave"; AT="$D/skills/acceptance-testing"
r() { if "$@" >/tmp/shipyard-v.out 2>&1; then echo "PASS|$N|ok"; else echo "FAIL|$N|exit $?: $(head -c 300 /tmp/shipyard-v.out | tr '\n|' '  ')"; fi; }
[ "$(type -P timeout)" = "/usr/bin/timeout" ] && echo "PASS|timeout|/usr/bin/timeout" || echo "FAIL|timeout|$(type -P timeout) - must be Git Bash /usr/bin/timeout"
command -v netstat >/dev/null && echo "PASS|netstat|ok" || echo "FAIL|netstat|missing"
if python3 -c 'import sys' >/dev/null 2>&1; then echo "PASS|python3-in-bash|$(command -v python3)"; else echo "WARN|python3-in-bash|python3 is missing or the Store stub - Claude must use py -3 / python (windows.md)"; fi
if grep -rlI $'\r' "$FW/scripts" "$AT/scripts" >/tmp/shipyard-v.out 2>/dev/null; then echo "FAIL|crlf|CRLF in: $(tr '\n' ' ' </tmp/shipyard-v.out)"; else echo "PASS|crlf|LF"; fi
N=bash-syntax; r bash -n "$FW/scripts/wave-init.sh" "$AT/scripts/pw-setup.sh"
out="$("$PY" "$FW/scripts/wave-cost.py" 2>&1)"; case "$out" in *Usage*) echo "PASS|wave-cost.py|ok";; *) echo "FAIL|wave-cost.py|$(echo "$out" | head -c 300 | tr '\n|' '  ')";; esac
T="$(mktemp -d)"; cd "$T" && git init -q . && git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
N=wave-init.sh; r bash "$FW/scripts/wave-init.sh" shipyard-selftest "$T"
grep -q 'listening TCP ports' /tmp/shipyard-v.out && echo "PASS|wave-init-ports|$(grep -A1 'listening TCP ports' /tmp/shipyard-v.out | tail -1 | cut -c1-60)..." || echo "WARN|wave-init-ports|no port list"
[ -f "$T/.wave/shipyard-selftest/BRIEF.md" ] && ! grep -q '<root>' "$T/.wave/shipyard-selftest/BRIEF.md" && echo "PASS|wave-brief|filled" || echo "FAIL|wave-brief|missing or placeholders left"
grep -q '/.wave/' "$T/.git/info/exclude" && echo "PASS|wave-exclude|.git/info/exclude" || echo "FAIL|wave-exclude|.wave not git-excluded"
N=qa-init; r "$PY" -I "$AT/scripts/qa.py" init shipyard-selftest --root "$T"
N=qa-status; r "$PY" -I "$AT/scripts/qa.py" status shipyard-selftest --root "$T"
N=qa-report-plan; r "$PY" -I "$AT/scripts/qa.py" report shipyard-selftest --plan --root "$T"
cd / && rm -rf "$T"
'@
  $body = $body.Replace('__DEST__', (ToSlash $Dest)).Replace('__PY__', (ToSlash $py)).Replace("`r`n", "`n")
  [IO.File]::WriteAllText($vsh, $body, $utf8NoBom)
  $v = Run $bash @('-l', (ToSlash $vsh))
  Remove-Item $vsh -ErrorAction SilentlyContinue
  foreach ($line in ($v.Out -split "`r?`n")) {
    $p = $line.Split('|', 3)
    if ($p.Count -eq 3 -and @('PASS', 'FAIL', 'WARN') -contains $p[0]) { Say $p[0] ('selftest ' + $p[1]) $p[2] }
    elseif ($line.Trim()) { Add-Content -Path $log -Value ('  ' + $line) -Encoding UTF8 }
  }
} elseif (-not $Check) {
  Say WARN 'selftest' 'skipped (Git Bash or Python missing)'
}

# ---------------------------------------------------------------- summary
$fail = @($results | Where-Object Level -eq 'FAIL').Count
$warn = @($results | Where-Object Level -eq 'WARN').Count
Write-Host ''
if ($fail -eq 0) {
  Write-Host ("OK ({0} warning(s)). Restart Claude Code, then use /feature-wave and /acceptance-testing." -f $warn) -ForegroundColor Green
} else {
  Write-Host ("{0} problem(s), {1} warning(s). Fix the [FAIL] lines and run install.cmd again. Send install-log.txt if you need help." -f $fail, $warn) -ForegroundColor Red
}
Add-Content -Path $log -Value ("RESULT fail=$fail warn=$warn") -Encoding UTF8
if ($fail -gt 0) { exit 1 } else { exit 0 }
